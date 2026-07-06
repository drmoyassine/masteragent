# Knowledge → Context Injection: Lifecycle & Retrieval Report

> **Created**: 2026-07-06. Source-of-truth walkthrough of how a knowledge index item
> (`{id, name, category, signals, summary, facets}`) is **created** (all pathways,
> including AI-telemetry → playbooks/skills) and **retrieved** into agent context,
> step by step, plus a design for making the retrieval pipeline configurable in the UI.
>
> Companion docs: [knowledge-pipeline-map.md](knowledge-pipeline-map.md),
> [knowledge-precontext-retrieval-plan.md](knowledge-precontext-retrieval-plan.md),
> [sprint2.5-delivery-report.md](sprint2.5-delivery-report.md).

---

## Part 0 — The shape being explained

Every knowledge record lives in one unified `knowledge` table. When injected in **index mode**,
each item is projected to:

```json
{ "id", "name", "category", "signals": [...], "summary", "facets": { "country": "Malaysia", ... } }
```

- `category` ∈ `best_practices | lessons_learned | trade_knowledge | skill | playbook`
- `signals` = domain topic tags (validated against the entity type's signal vocabulary)
- `summary` = the ≤1024-char discovery description (what it is + when it applies)
- `facets` = governed structured dimensions (`metadata.facets`), the hard-filter axis
- `content` (full body / SKILL.md) is **omitted** in index mode — pulled on demand via `GET /knowledge/{id}`

---

## Part 1 — Full lifecycle, step by step

### PHASE A — Message arrives → interaction is stored & embedded

1. **n8n receives** the user's WhatsApp/email message.
2. n8n `POST /api/memory/interactions` (`memory/agent.py::ingest_interaction`, HTTP 202). Row inserted `status='pending'`; a `ingest_interaction` job is queued.
3. Worker runs `memory_ingestion.py::process_interaction`: OCR/attachments, **computes an ephemeral embedding** of the content, marks `is_enriched=TRUE`. This embedding is what get-context later averages into the "conversation vector."
4. If the interaction is AI telemetry (`internal_ai_thought` / `internal_ai_tool_call`), it is stored the same way but **excluded from memory generation** (`memory_generation_interaction_types` = exclude). It is retained for the playbook pathway (Phase C-b).

> At this point NO knowledge is created. Knowledge is built asynchronously, in bulk, later.

### PHASE B — Interactions → Memories → Intelligence (the feeder tiers)

5. **Daily (or threshold)**: `memory_generation.py` condenses each entity's pending interactions into a **Memory** (Tier 1) — NER, embedding, storytelling summary. Prompts are admin-owned DB configs.
6. **Threshold reached** (≥ `intelligence_extraction_threshold` uncompacted memories): `memory_compaction.py::compact_entity` synthesizes **Intelligence** (Tier 2) — signals + content + summary + embedding, `status='draft'` unless `intelligence_auto_approve` (prod: on → `confirmed`).

### PHASE C — Intelligence/telemetry → Knowledge records (all creation pathways)

Every pathway ends at `memory_db_writes.py::insert_knowledge`, which (a) renders SKILL.md for skill/playbook categories, (b) is preceded by **facet extraction** (`memory_facets.py::enrich_metadata_with_facets` → `extract_facets`), writing `metadata.facets`. So **every pathway produces the index shape**.

**C-a — Batch synthesis (declarative knowledge)** — `experiential`
- `memory_knowledge.py::run_knowledge_check` (daily or manual/drain) fires when ≥ `knowledge_threshold` **confirmed** unused intelligence accumulate per entity type.
- `generate_knowledge_from_intelligence`: PII-scrub → dedup vs prior knowledge (prompt) → LLM synthesize `{name, category, signals, content, summary, tags}` → embed → **extract facets** → insert. `category` ∈ best_practices/lessons_learned/trade_knowledge.

**C-b — AI-telemetry → Playbook → Skills (procedural knowledge)** — `experiential` + `decomposed`
- **Trigger**: weekly (`playbook_extraction_interval_days`, default 7) OR when unlinked confirmed intelligence ≥ `playbook_extraction_evidence_threshold` (default 20). `memory_tasks.py` enqueues `extract_playbooks`.
- `memory_playbooks.py::run_playbook_check` → per entity type:
  1. **Cluster** confirmed+embedded intelligence by pairwise cosine (≥ `dedup_similarity_threshold`) across **distinct** entities (union-find). Clusters spanning ≥ `extraction_min_entities` (3) qualify.
  2. **Enrich with telemetry**: pull `internal_ai_thought` / `internal_ai_tool_call` interactions for those entities within the cluster's time window ±1h, not previously processed (`playbook_processed_interactions`). *This is where AI telemetry enters knowledge.*
  3. **LLM extracts a playbook**: `{name, description, trigger_conditions[], steps[{order,action}], confidence}`. Confidence-gated. Centroid-embedding dedup (refine-on-merge if match).
  4. **Insert** as `category='playbook'` → `insert_knowledge` renders SKILL.md, **extracts facets** into `metadata.facets`.
  5. **Decompose skills**: LLM turns playbook steps into 1–3 reusable skills (`{name, skill_type, trigger_desc, procedure}`) → each inserted as `category='skill'` (`source_pathway='decomposed'`), SKILL.md + facets.

**C-c — Hermes (admin natural-language)** — `admin_instructed`
- `POST /instruct` → `memory_hermes.py` routes free text to a category, builds metadata, **extracts facets**, dedup/refine, insert.

**C-d — Marketplace import** — `imported`
- `POST /skills/import` (or UI Install dialog) → parse SKILL.md → dedup-merge → **extract facets** → insert verbatim.

**C-e — Manual admin/agent create** — `agent_created` / admin
- `POST /knowledge` (admin or agent) → renders SKILL.md for skill/playbook → **extracts facets** → insert.

**C-f — System-seeded** — `system`
- The always-on **Knowledge Management skill** (`metadata.always_inject=true`), seeded at startup, protected from agent mutation.

### PHASE D — Lifecycle maintenance (keeps the index lean & fresh)

7. **Weekly consolidation** (`memory_consolidation.py`): merge near-duplicates (retire loser, `merge_count++`, refine winner), **decay** stale playbooks/skills, **recompute quality_score** (used in ranking).
8. **Refine-on-merge**: when a new precursor matches an existing record, it's LLM-merged in place (`version++`) rather than duplicated.
9. **Facet backfill** (`POST /trigger/backfill-facets`): populates `metadata.facets` on records that predate facet extraction.

### PHASE E — Retrieval: message → injected knowledge index (the hot path)

When n8n needs context (typically on each inbound user message), it calls
`GET /api/memory/get-context?entity_type=contact&entity_id=…` with optional
`knowledge_facets`, `knowledge_category`. Inside `memory/agent.py::get_context`:

1. **Load settings** — `context_knowledge_mode` (full|index), `context_knowledge_count` (cap, 30), `context_knowledge_min_similarity` (floor, 0).
2. **Resolve facets** (hard filter axis):
   - explicit `knowledge_facets` param (n8n knows the contact's interest), **else**
   - derive from `entity_profiles.properties` via `profile_facet_map` (opt-in), **else** none.
   - **Canonicalize** values to stored casing (`canonicalize_facets`) so `metadata @>` doesn't silently miss; profile-derived unmatched values are dropped.
3. **Build conversation vector** — `AVG(embedding)` over the entity's **10 most recent embedded interactions** (from Phase A). This is the semantic "what is this conversation about" signal. No new embedding call.
4. **Pinned query** — fetch all `always_inject=true` records (management skill, active pinned records). **Exempt from facet filter and cap.**
5. **Main query** — active, shared, `NOT always_inject`, with `metadata @> facets` (hard filter, GIN-indexed) + optional category + optional similarity floor. Ranked by:
   ```
   score = relevance * 0.7 + quality_score * 0.3      (when conversation vector exists)
   score = quality_score                               (fallback: no embeddings)
   ```
   `LIMIT context_knowledge_count`. On any SQL error → falls back to pure `quality_score DESC`.
6. **Project** — pinned records always full-content; the rest are `_full_item` (full mode) or `_index_item` (`{id,name,category,signals,summary,facets}`, index mode).
7. **Return** `knowledge[]` in the payload alongside interactions/memories/intelligence.
8. **Agent decides**: reads the pinned Knowledge Management skill (the protocol), scans the lean index, and for any relevant item calls `GET /knowledge/{id}` to pull full content/SKILL.md before acting. If the index is thin → broaden (`/search/semantic?strict=false`) → use tools → delegate.

**Net path from a user message**: message → (async, pre-existing) interactions already embedded → get-context averages last-10 embeddings into a conversation vector → hard-filter by governed facets → rank relevance×0.7 + quality×0.3 → cap → project to lean index → agent pulls full records on demand. Pinned always-on records bypass the filter and cap.

---

## Part 2 — Making retrieval configurable in the Knowledge Settings UI

### 2.1 What's configurable **today** (already shipped)

| Control | Setting | Effect |
|---|---|---|
| Injection mode | `context_knowledge_mode` | full vs lean index |
| Injection cap | `context_knowledge_count` | max records injected |
| Relevance floor | `context_knowledge_min_similarity` | drop below cosine X |
| Facet extraction | `facet_extraction_enabled` | codify facets on creation |
| Facet schema | `knowledge_facets_schema` | governed keys |
| Profile→facet map | `profile_facet_map` | CRM auto-derivation |

### 2.2 What is **hardcoded** and should become configurable

These constants currently live in `get_context` SQL and are the real "retrieval intelligence" knobs:

1. **Ranking weights** `0.7 / 0.3` (relevance vs quality) — hardcoded.
2. **Conversation-vector window** `LIMIT 10` recent interactions — hardcoded.
3. **Per-category caps** — none; one flat cap mixes declarative + playbooks + skills.
4. **Facet filter strictness** — always hard AND; no "boost instead of exclude" option.
5. **Signal-overlap boost** — not implemented (entity's live intelligence signals ∩ knowledge signals).
6. **Recency weighting** in ranking — not applied to knowledge (decay handles retirement only).

### 2.3 Proposed design — "Retrieval Recipe" (smart, elegant, simple)

A single **Retrieval** card in Knowledge Settings, expressing the whole pipeline as one readable formula plus a few governed toggles. The guiding principle: **the agent is the final decider; retrieval only ranks and gates — never hides capability** (the pinned management skill enforces this).

**Block 1 — Injection**
- Mode: `full | index` (existing).
- Total cap: `context_knowledge_count` (existing).
- **Per-category caps** (new, optional): e.g. `≤2 playbooks, ≤3 skills, ≤5 declarative, + always-on`. Empty = use total cap only. Prevents one category from crowding out others.

**Block 2 — Ranking formula** (new — expose the weights)
- Three sliders that **sum to 1.0** (auto-normalized), shown as a live formula:
  `score = relevance·{w_rel} + quality·{w_qual} + recency·{w_rec}`
  Defaults `0.7 / 0.3 / 0.0` (identical to today). Recency = decay over a configurable half-life.
- **Conversation window** (new): N recent interactions to average (default 10).
- **Signal boost** (new toggle): add `+w_sig` when a record's `signals` overlap the entity's recent intelligence signals. Off by default.

**Block 3 — Facet filtering** (new — strictness policy)
- Mode: `strict (hard filter) | boost (rank up, don't exclude) | off`. Default `strict` (current behavior) but now switchable — `boost` is the "never hide, just prefer" mode that pairs naturally with the epistemic contract.
- Similarity floor (existing).
- Source priority: explicit param → profile-derived (existing, made visible).

**Block 4 — Live Preview** (the elegance multiplier)
- An entity picker + "Preview injection" button that calls get-context with the *unsaved* recipe and shows the exact ranked `knowledge[]` the agent would receive, with each record's `relevance / quality / recency / final score` broken out. Turns an abstract formula into something you can *see and tune*. Reuses the existing `/pipeline-runs`-style read pattern.

### 2.4 Why this is "powerful yet simple"

- **One formula, not a maze**: the entire ranking is one line the admin reads and adjusts with sliders that always sum to 1. No hidden magic.
- **Governed, not free-form**: facets stay the only agent-filterable axis; the recipe tunes *ranking and gating*, never introduces ungoverned fields.
- **Safe by construction**: `boost` mode + the always-on management skill mean a mis-tuned recipe degrades gracefully (agent still gets *something* + the protocol to broaden/delegate) — it can never produce "the agent thinks it has no knowledge."
- **Backwards-compatible**: every default equals current behavior; the card is inert until touched.
- **Observable**: Live Preview closes the loop — you tune, you see, you save.

### 2.5 Implementation sketch (for a later sprint)

1. **Settings**: add `context_rank_weights` (JSONB `{relevance,quality,recency}`), `context_conversation_window` (int), `context_per_category_caps` (JSONB), `context_facet_mode` (`strict|boost|off`), `context_signal_boost` (float). All default to current behavior.
2. **get_context**: replace the hardcoded `0.7/0.3`, `LIMIT 10`, and single-cap with these settings; implement `boost` as an additive term instead of a WHERE clause; apply per-category caps as a post-rank slice.
3. **Preview endpoint**: `POST /api/memory/context-preview` (admin) — runs the resolution + ranking with a supplied recipe, returns ranked records + per-record score breakdown, no side effects.
4. **UI**: one "Retrieval" card in the Knowledge tab: injection block, three-slider formula, facet-mode selector, per-category caps, and the Live Preview panel.

---

## Part 3 — One-glance summary

**Creation** (all roads → `insert_knowledge` → SKILL.md render + facet extraction → the index shape):
`interactions → memories → intelligence → { batch synthesis | telemetry-clustered playbooks → decomposed skills | Hermes | import | manual | system-seeded }`

**Retrieval** (per message):
`recent interaction embeddings → AVG conversation vector → resolve+canonicalize governed facets → [pinned always-on, filter-exempt] + [hard-filter by facets → rank relevance·0.7 + quality·0.3 → cap] → lean index → agent pulls full records on demand`

**Configurable future**: a single **Retrieval Recipe** card — injection mode/caps, a 3-slider ranking formula (relevance/quality/recency + optional signal boost), facet strictness (strict/boost/off), and a Live Preview — that exposes today's hardcoded constants as governed, observable knobs without ever letting retrieval hide capability from the agent.
