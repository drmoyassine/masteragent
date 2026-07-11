# Memory, Intelligence & Knowledge Generation — Settings & Mechanics Reference

> **Accurate to `main` as of 2026-07-07.** Source-of-truth reference for every setting and
> mechanism that governs how interactions become memories, intelligence, and knowledge —
> all pathways, all valves, all defaults. Verified against the code, not assumed.
>
> Companion docs: [knowledge-pipeline-map.md](knowledge-pipeline-map.md),
> [knowledge-to-context-retrieval-report.md](plans/archived/knowledge-to-context-retrieval-report.md),
> [sprint2.5-delivery-report.md](plans/archived/sprint2.5-delivery-report.md).

---

## 1. The model in one paragraph

MasterAgent is an experiential-learning factory: raw **interactions** (Tier 0) are condensed
nightly into **memories** (Tier 1), memories into **intelligence** (Tier 2), and intelligence
into **knowledge** (Tier 3). Knowledge also has a direct first-class path from **AI telemetry**
and from cross-entity **playbook clustering**. Everything is driven by a per-tier
**dual-valve trigger** (schedule + threshold) running on a single in-process background loop,
with LLM prompts/models configured as DB rows (pipeline nodes) editable in the admin UI.

```
Interactions ──(memory gen)──▶ Memories ──(intelligence gen)──▶ Intelligence ──(knowledge gen)──▶ Knowledge
                                    │                                │                               ▲
                                    └─ threshold valve ──────────────┘                               │
                                                                       └─ threshold valve ─────────┘
                                                                       ┌───────────────────────────┘
AI Telemetry ───────────(telemetry reflection, nightly)──────────────▶ Knowledge (skill/playbook/knowledge)
Intelligence cluster (≥3 entities) ───(playbook extraction)──▶ Playbook ──▶ Skills
```

---

## 2. The dual-valve trigger model (the unifying concept)

Every learning tier has **two independent valves**, mirroring how memory generation has always
worked. Either valve alone fires the tier; together they mean "reflect every night on whatever
accumulated, **and** fire early when enough has piled up."

| Valve | What it does | Memory | Intelligence | Knowledge |
|---|---|---|---|---|
| **Schedule** | Nightly flush at a per-tier time, using a small **floor** so entities/types *below* the main threshold still get processed ("reflect on what we have") | ✅ | ✅ | ✅ |
| **Threshold** | Intra-day early-fire the moment enough precursor records accumulate (busy entities don't wait for night) | ✅ | ✅ | ✅ |

- Set the threshold to `0` (memory) / disable the schedule → **single-valve** mode.
- Both enabled (default) → **whichever-comes-first** mode.
- The schedule valve uses a **floor** (default 2), deliberately lower than the main threshold, so
  overnight reflection isn't blocked by the higher material bar.

> **Why both:** "every night we reflect and learn" (schedule) **without** missing fast-moving
> entities (threshold). Consolidation/dedup/decay is deliberately **not** on this cadence — it's
> a weekly maintenance job (§10).

---

## 3. The background scheduler — `memory_tasks.py::_background_loop`

A single async loop wakes **every 60 seconds** and checks each tier's configured `HH:MM` (UTC).
Each tier is guarded by its own `memory_job_log` row so it fires **exactly once per day**,
independently, staggered so they cascade the same night:

| Tier | Setting (time) | Default | Job enqueued | Notes |
|---|---|---|---|---|
| Memory 0→1 | `memory_generation_time` | `02:00` | `run_daily_memory_generation` (direct) | True flush — every entity with pending interactions |
| Intelligence 1→2 | `intelligence_generation_time` | `02:30` | `run_intelligence_sweep` `{min_count: floor}` | Floor-gated sweep |
| Knowledge 2→3 | `knowledge_generation_time` | `03:00` | `generate_knowledge` `{min_count: floor}` | Floor-gated sweep |
| Playbook extraction | `playbook_generation_time` | `03:30` | `extract_playbooks` | Cross-entity clustering (§9) |
| Telemetry reflection | `telemetry_reflection_time` | `04:00` | `reflect_telemetry` | First-class telemetry→knowledge (§7) |
| Consolidation | (piggybacks memory time) | weekly | `run_consolidation` | `consolidation_run_interval_days` (default 7) |

Each schedule valve has a companion `*_schedule_enabled` toggle (default `TRUE`). Disabling it
leaves only the intra-day threshold valve. **Idempotency**: `get_job_last_date(job_name)` /
`set_job_last_date` prevent double-fires across the 60s wake cycle.

**Threshold valves fire intra-day, independent of this loop** — they're invoked at the end of
the preceding tier's per-record generation (see §4–6).

---

## 4. Tier 0→1 — Memory generation

**What:** one memory per entity per day, summarizing that day's pending interactions (NER +
storytelling summary + embedding). One memory record covers all of an entity's interactions for
a given date (idempotent on `(date, entity_type, entity_id)`).

### Settings (global, `memory_settings`)
| Setting | Default | Effect |
|---|---|---|
| `memory_generation_time` | `02:00` | Schedule valve time (UTC) |
| `memory_generation_mode` | `ner_and_raw` | `ner_only` vs `ner_and_raw` (how much raw text feeds the prompt) |
| `memory_threshold` | `0` (disabled) | **Threshold valve:** >0 = fire when an entity accumulates this many pending interactions, intra-day |
| `memory_safe_boundary_types` | `["outgoing_whatsapp_message"]` | Threshold valve only fires when the latest interaction is one of these (don't split mid-conversation) |
| `memory_generation_interaction_types` | `["internal_ai_thought","internal_ai_tool_call"]` | Interaction types to **exclude** (AI telemetry must not become conversational memory) |
| `memory_generation_interaction_types_mode` | `exclude` | `exclude` (drop listed) or `include` (only listed) |
| `memory_generation_max_tokens` | `1200` | Cap on the memory-generation LLM output |

### Valves
- **Schedule:** at `memory_generation_time`, `run_daily_memory_generation` enqueues a
  `generate_memory` job for every entity with pending interactions from yesterday-or-older.
- **Threshold:** during ingestion, `_maybe_trigger_threshold_memory` fires when `memory_threshold>0`
  **AND** the latest interaction type ∈ `memory_safe_boundary_types` **AND** pending count ≥
  threshold **AND** no memory lock held. (Acquires the per-entity lock so outbound webhooks defer.)

### Mechanics
Per entity-day: filter interactions by `memory_generation_interaction_types` (mode), fetch
**prior memories** (`prior_context_chrono_count` + `prior_context_semantic_count`) to avoid
restating established facts, run the sequential **pipeline** (`memories` stage nodes:
entity_extraction → memory_generation → embedding, etc.), write one memory, mark interactions
`done`, then call `_check_compaction_trigger` (→ intelligence threshold valve, §5).

---

## 5. Tier 1→2 — Intelligence generation (compaction)

**What:** synthesize N uncompacted memories into 1–3 **intelligence** records (signals + content +
summary + embedding). Signals are validated against the entity type's vocabulary
(`intelligence_signals_prompt`).

### Settings
| Setting | Scope | Default | Effect |
|---|---|---|---|
| `intelligence_extraction_threshold` | global | `10` | **Threshold valve:** uncompacted memories to fire |
| `intelligence_extraction_threshold` | per-entity-type | `NULL`→global | Per-type override |
| `intelligence_schedule_enabled` | global | `TRUE` | Schedule valve on/off |
| `intelligence_generation_time` | global | `02:30` | Schedule valve time |
| `intelligence_schedule_floor` | global | `2` | Schedule sweep gate (lower than threshold) |
| `intelligence_auto_approve` | per-entity-type | `FALSE` | `TRUE` → intelligence lands `confirmed` (else `draft`) |
| `intelligence_max_tokens` | global | `1200` | LLM output cap |
| `intelligence_signals_prompt` | per-entity-type | seeded | The signal vocabulary the LLM must use |

### Valves
- **Schedule:** `run_intelligence_sweep` calls `run_compaction_check(min_count=floor)`, which runs
  `_check_compaction_trigger(..., override_threshold=floor)` for every entity — so entities with
  as few as `floor` (default 2) uncompacted memories get reflected on nightly, **below** the
  main threshold.
- **Threshold (intra-day):** after each memory is generated, `_check_compaction_trigger` fires
  with no override → uses `intelligence_extraction_threshold` (per-type or global). When met,
  enqueues `generate_insight`.

### Mechanics
`compact_entity`: take N most-recent uncompacted memories, fetch **prior intelligence** +
**prior knowledge** (to dedupe / build-on rather than restate), run the `intelligence` pipeline
node, parse JSON array of signals, validate signals against the vocabulary, embed, insert
(`draft` unless `intelligence_auto_approve`). After insert, enqueues `generate_knowledge`
(→ knowledge threshold valve, §6).

---

## 6. Tier 2→3 — Knowledge generation (synthesis)

**What:** synthesize N confirmed-but-unused intelligence into one **knowledge** record
(`best_practices | lessons_learned | trade_knowledge`): PII-scrubbed, generalized, embedded,
facet-extracted, deduped against prior knowledge.

### Settings
| Setting | Scope | Default | Effect |
|---|---|---|---|
| `knowledge_threshold` | global | `5` | **Threshold valve:** unused confirmed intelligence per entity-type to fire |
| `knowledge_extraction_threshold` | per-entity-type | `NULL`→global | Per-type override |
| `knowledge_schedule_enabled` | global | `TRUE` | Schedule valve on/off |
| `knowledge_generation_time` | global | `03:00` | Schedule valve time |
| `knowledge_schedule_floor` | global | `2` | Schedule sweep gate (lower than threshold) |
| `knowledge_max_tokens` | global | `1200` | LLM output cap (truncated JSON fails parse → skipped) |
| `knowledge_signals_prompt` | per-entity-type | seeded | Signal vocabulary for knowledge |
| `knowledge_refine_on_merge` | global | `TRUE` | On dedup match, LLM-merge into existing record (`version++`) instead of only counting |

### Valves
- **Schedule:** nightly `generate_knowledge {min_count: floor}` → `run_knowledge_check(min_count=floor)`
  processes every entity-type with ≥ `floor` unused confirmed intelligence, **below** the main threshold.
- **Threshold (intra-day):** after each intelligence record is created (`compact_entity`),
  `generate_knowledge` (no floor) is enqueued → uses `knowledge_threshold`/`knowledge_extraction_threshold`
  as the gate. (This is the chain that makes knowledge truly dual-valve.)

### Mechanics
`generate_knowledge_from_intelligence`: PII-scrub each intelligence item, fetch prior knowledge
(`prior_knowledge_semantic_count`) for dedup, run the `knowledge` pipeline node, validate signals,
embed, **extract governed facets** (`memory_facets.extract_facets` → `metadata.facets`), insert.
Dedup: new records whose embedding matches an existing one (≥ `dedup_similarity_threshold`) are
refined-in-place (`refine_or_increment_merge`) rather than duplicated.

**`drain` mode:** `run_knowledge_check(drain=True)` loops threshold-sized batches until the
confirmed-intelligence backlog is exhausted (50-round cap) — used for backfill.

---

## 7. Telemetry reflection — AI telemetry → skill/playbook/knowledge (first-class path)

**What:** gives AI telemetry (`internal_ai_thought` / `internal_ai_tool_call`) a **direct,
per-entity nightly path** to knowledge — independent of the cross-entity clustering that
subordinates it in the playbook pathway (§9). Telemetry that solved a novel problem for *one*
contact is no longer lost.

### Settings (global)
| Setting | Default | Effect |
|---|---|---|
| `telemetry_reflection_enabled` | `TRUE` | On/off |
| `telemetry_reflection_time` | `04:00` | Nightly time |
| `telemetry_reflection_confidence_min` | `0.6` | Discard candidates below this LLM confidence |
| `telemetry_reflection_max_tokens` | `1200` | LLM output cap |

### Mechanics (`memory_telemetry.py`)
For each entity that had telemetry on the target day (default: yesterday) and hasn't been
reflected on yet (idempotent via `telemetry_reflection_log`):
1. Fetch the day's **telemetry** + the day's **conversation** (outcome context — so reflection
   can judge whether the agent's actions/discoveries were effective).
2. One LLM **reflection** call → typed candidates: `skill | playbook | best_practices |
   lessons_learned | trade_knowledge` (zero is valid).
3. Confidence-gate, embed, **dedup** (`refine_on_merge` if a similar record exists — recurrence
   strengthens conviction via `merge_count`→quality), **extract facets**, insert as **draft**
   (`source_pathway="telemetry_reflected"`, `evidence_breadth=1`).

**Design principles:** reflection before codification (raw telemetry never dumped), recurrence
builds conviction (draft + merge machinery promotes over time), outcome-aware (conversation
included). See [the telemetry deep-dive](plans/archived/knowledge-to-context-retrieval-report.md) for why this
path was needed.

### Manual / backfill triggers
- **Nightly** (automatic): `reflect_telemetry` job at `telemetry_reflection_time` → reflects yesterday.
- **`POST /trigger/reflect-telemetry?reflection_date=YYYY-MM-DD`**: one-shot reflection on one day
  (defaults to yesterday). Note: idempotent — skips any `(entity, day)` already in
  `telemetry_reflection_log`; to **re-reflect** after editing the prompt, clear that day's log row first.
- **`POST /trigger/backfill-telemetry?max_days=N`**: process the accumulated historical backlog —
  loops `run_telemetry_reflection(date)` oldest-first over the most-recent N-day window; idempotent
  and resumable (re-trigger to continue further back).
- **Drain Backlog button** (`run-knowledge-check?drain=true`): enqueues `backfill_telemetry{max_days:30}`
  alongside the intelligence→knowledge drain — one click drains both backlogs
  (`?drain_telemetry=false` to skip telemetry).

---

## 8. All knowledge creation pathways (`source_pathway`)

Every pathway ends at `insert_knowledge`, which renders SKILL.md (skill/playbook) and runs facet
extraction — so all produce the unified `{name, category, signals, content, summary, facets}` shape.

| `source_pathway` | Pathway | Trigger |
|---|---|---|
| `experiential` | Batch synthesis (intelligence→knowledge) | §6 valves |
| `experiential` | Playbook extraction (cluster→playbook) | §9 nightly |
| `decomposed` | Skill decomposition (playbook→skills) | Auto after each playbook |
| `telemetry_reflected` | Telemetry reflection | §7 nightly |
| `admin_instructed` | Hermes (natural-language instruction) | `POST /instruct` (manual) |
| `imported` | Marketplace SKILL.md import | `POST /skills/import` / UI Install (manual) |
| `agent_created` / admin | Manual create | `POST /knowledge` (manual) |
| `system` | Always-on Knowledge Management skill | Startup seed (protected) |

---

## 9. Cross-entity playbook extraction (`memory_playbooks.py`)

**What:** when a signal recurs across **distinct entities**, extract a generalized **playbook**
(ordered steps + trigger conditions) and decompose it into **skills**.

### Settings
| Setting | Scope | Default | Effect |
|---|---|---|---|
| `playbook_schedule_enabled` / `playbook_generation_time` | global | `TRUE` / `03:30` | Nightly schedule |
| `playbook_extraction_interval_days` | global | `7` | (Legacy interval; nightly is default now) |
| `playbook_extraction_evidence_threshold` | global | `20` | Unlinked-intelligence override trigger |
| `extraction_min_entities` | per-entity-type | `3` | Min distinct entities a cluster must span |
| `dedup_similarity_threshold` | global | `0.85` | Pairwise cosine gate for clustering + dedup |
| `extraction_confidence_threshold` | global | `0.6` | Discard playbooks below this LLM confidence |
| `playbook_auto_activate` / `skill_auto_activate` | per-entity-type | `FALSE` | `TRUE` → land `active` (else `draft`) |

### Mechanics
Per entity-type: pairwise-cosine cluster confirmed+embedded intelligence across **distinct**
entities (union-find) → clusters spanning ≥ `extraction_min_entities` qualify → **enrich with AI
telemetry** for those entities within the cluster's time window → LLM extracts playbook →
confidence-gate → centroid-dedup → insert (`category=playbook`, SKILL.md, facets) →
**decompose** into 1–3 skills (`category=skill`, `source_pathway=decomposed`).

> Telemetry is a **passenger** here (prompt enrichment), not a driver — see §7 for the
> first-class telemetry path.

---

## 10. Lifecycle & maintenance (weekly, not nightly)

Consolidation is **pruning, not learning**, so it runs on `consolidation_run_interval_days`
(default 7), piggybacking the memory schedule time — deliberately off the nightly learning cadence.

| Setting | Default | Effect |
|---|---|---|
| `consolidation_run_interval_days` | `7` | Dedup/decay/quality-recompute cadence |
| `consolidation_similarity_threshold` | `0.80` | Merge near-duplicate knowledge (same category) |
| `decay_max_inactive_days` | `90` (per-type) | Retire stale playbook/skill records |

**`run_consolidation`** does: merge duplicate pairs (retire loser, `merge_count++`, refine
winner), **decay** (retire inactive playbooks/skills), **recompute quality_score**
(evidence 25% + outcome 30% + confidence 15% + merge-recurrence 20% + recency 10%).
`knowledge_refine_on_merge` (default `TRUE`) makes merges *update* the surviving record in place
rather than only counting.

---

## 11. The pipeline-node / LLM-config system (how prompts & models are configured)

Generation prompts and models are **DB rows** in `memory_llm_configs` (pipeline nodes), edited in
the admin UI (Memory Settings → pipeline editors). Each node: `task_type`, `pipeline_stage`,
`provider_id`, `model_name`, `inline_system_prompt`, `inline_schema`, `execution_order`,
`is_active`, optional `thinking_enabled`. The sequential executor (`memory_generation._execute_pipeline_node`)
runs nodes in `execution_order` against a shared mutable context.

| Stage | Nodes (typical) |
|---|---|
| `interactions` | vision (doc/OCR parsing) |
| `memories` | entity_extraction (NER) → memory_generation → embedding (+ optional pii_scrubbing, summarization) |
| `intelligence` | intelligence_generation (+ summarization) |
| `knowledge` | knowledge_generation (+ pii_scrubbing, playbook_generation, skill_generation) |

> **Zero-regression rule:** these `inline_system_prompt` values are admin-owned and quality-frozen;
> code changes never alter them. Only the *mechanics around them* (valves, facets, retrieval) change.

#### Node-vs-pathway truth (important)
The "pipeline" metaphor is accurate **only for the `memories` stage** (a real sequential executor loops nodes in order). The `intelligence` and `knowledge` stages are **not** sequential pipelines — each generation pathway **picks one node by `task_type`** and ignores the rest. Every knowledge-pathway prompt is now node-driven and admin-editable (seeded with the canonical default), resolved via `get_task_system_prompt(task_type, fallback)`:

| Pathway | Node (`task_type`) | Prompt source | Model source |
|---|---|---|---|
| Declarative synthesis | `knowledge_generation` | ✅ node prompt | ✅ node |
| Telemetry reflection | `telemetry_reflection` | ✅ node prompt | ✅ node |
| Playbook extraction | `playbook_generation` | ✅ node prompt (`{entity_count}`/`{entity_type}` placeholders) | ✅ node |
| Skill decomposition | `skill_generation` | ✅ node prompt | ✅ node |
| PII scrubbing | `pii_scrubbing` | ✅ node prompt (LLM-scrub mode) / `/redact` (zendata) | ✅ node |

The Knowledge Settings UI reflects this as **pathway cards** (Feeds on → Produces → Trigger + editable prompt/model per card), not an ordered draggable pipeline.

---

## 12. Settings reference

### Global (`memory_settings`) — generation-relevant
**Schedule/valve:** `memory_generation_time` (02:00), `memory_threshold` (0), `memory_safe_boundary_types`,
`intelligence_extraction_threshold` (10), `intelligence_schedule_enabled` (T), `intelligence_generation_time` (02:30),
`intelligence_schedule_floor` (2), `knowledge_threshold` (5), `knowledge_schedule_enabled` (T), `knowledge_generation_time` (03:00),
`knowledge_schedule_floor` (2), `playbook_schedule_enabled` (T), `playbook_generation_time` (03:30),
`telemetry_reflection_enabled` (T), `telemetry_reflection_time` (04:00), `telemetry_reflection_confidence_min` (0.6).
**Tokens:** `memory_generation_max_tokens` (1200), `intelligence_max_tokens` (1200), `knowledge_max_tokens` (1200),
`telemetry_reflection_max_tokens` (1200). **Quality/dedup:** `dedup_similarity_threshold` (0.85),
`extraction_confidence_threshold` (0.6), `consolidation_run_interval_days` (7), `consolidation_similarity_threshold` (0.80),
`knowledge_refine_on_merge` (T), `playbook_extraction_interval_days` (7), `playbook_extraction_evidence_threshold` (20).
**Prior context:** `prior_context_chrono_count` (2), `prior_context_semantic_count` (2), `prior_intelligence_chrono_count` (3),
`prior_intelligence_semantic_count` (2), `prior_knowledge_semantic_count` (3), `prior_knowledge_in_intelligence_count` (2).
**Memory filtering:** `memory_generation_mode` (ner_and_raw), `memory_generation_interaction_types`, `memory_generation_interaction_types_mode` (exclude).
**Retrieval (context injection):** `context_knowledge_mode` (full), `context_knowledge_count` (30), `context_knowledge_min_similarity` (0.0),
`facet_extraction_enabled` (T), `knowledge_facets_schema` (seeded), `profile_facet_map` (NULL/opt-in).

### Per-entity-type (`memory_entity_type_config`)
`intelligence_extraction_threshold` (NULL→10), `intelligence_auto_approve` (FALSE), `knowledge_extraction_threshold` (NULL→5),
`knowledge_auto_promote` (FALSE), `ner_enabled` (TRUE), `ner_confidence_threshold` (0.5), `ner_schema` (NULL),
`embedding_enabled` (TRUE), `pii_scrub_knowledge` (TRUE), `metadata_field_map` ({}), `intelligence_signals_prompt` (seeded),
`knowledge_signals_prompt` (seeded), `extraction_min_entities` (3), `playbook_auto_activate` (FALSE), `skill_auto_activate` (FALSE),
`decay_max_inactive_days` (90), `auto_activate_score_threshold` (NULL).

---

## 13. Manual triggers & backfill (admin)

All under `POST /api/memory/trigger/*` (admin JWT):

**Per-tier generation:** `generate-memories`, `run-intelligence-check`,
`run-knowledge-check` (with `?drain=true&drain_telemetry=true|false`), `extract-playbooks`,
`run-consolidation`, `reprocess-intelligence`, `compact/{type}/{id}`.

**Telemetry:** `backfill-telemetry?max_days=N` (historical date-loop backfill, idempotent +
resumable, most-recent N-day window), `reflect-telemetry?reflection_date=YYYY-MM-DD`
(one-shot reflection on one day; defaults to yesterday).

**Backfill / maintenance:** `backfill-facets` (governed facets on existing knowledge),
`backfill-profiles` (entity profiles from CRM blobs).

**The "Drain Backlog" button** = `run-knowledge-check?drain=true` and enqueues **both**
`generate_knowledge{drain:true}` (intelligence→knowledge, looped) **and**
`backfill_telemetry{max_days:30}` (AI-telemetry reflection, 30-day window) — one click
drains both experiential backlogs. Opt out of telemetry with `?drain_telemetry=false`.

---

## 14. Observability — `memory_pipeline_runs`

Every check/generation writes one row: `job, outcome (created|skipped|failed), reason_code
(below_threshold|no_confirmed_intelligence|llm_config_missing|parse_error|...), records_created,
detail JSONB`. Read via `GET /api/memory/admin/pipeline-runs`. Turns "why is nothing being
produced?" into a queryable record instead of a docker-logs dive.
