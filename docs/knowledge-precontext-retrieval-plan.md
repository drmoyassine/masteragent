# Knowledge Pre-Context Retrieval — Implementation Plan (Sprint 2.5)

> **Status**: Planned, ready to implement. Self-contained — no prior conversation needed.
> **Author handoff**: written 2026-07-06 for a separate implementing agent.
> **Companion**: [knowledge-pipeline-map.md](knowledge-pipeline-map.md) (overall knowledge system), [knowledge-tier-productionization.md](knowledge-tier-productionization.md) (how Tier 3 went live).

---

## 0. Problem being solved

`GET /api/memory/get-context` injects knowledge for an entity, but today it:
- Returns **full `content`** for up to 30 records (whole SKILL.md for playbooks) → token bloat at scale.
- Sources purely by **semantic similarity + quality** — no structured filtering by domain (country/program/university/etc.).
- Provides **no instruction** to the agent on how to use, pull, or extend knowledge.
- `list_knowledge` ([backend/memory/agent.py:784](../backend/memory/agent.py)) accepts `entity_type`/`entity_subtype` params but **ignores them** (stubbed, never built).
- There is **no agent-facing `GET /knowledge/{id}`** for on-demand full-record pull.
- get-context **never reads `entity_profiles`**, so no CRM-derived filtering.

This plan makes pre-context injection a **lean, governed, filterable index** the orchestrator agent scans to decide what full records to pull on demand, with an always-present instruction skill that prevents the agent from misreading a sparse index as "no knowledge / no capability."

---

## 1. Locked design decisions (do not relitigate)

1. **Knowledge stays global.** Records are not owned by an entity. Relevance = facet-match + semantic similarity, not ownership. (A "CompEng entry requirements at University X, Malaysia" record applies to any relevant contact.)

2. **Hard filter applies to the WHOLE knowledge table** for pre-context — declarative knowledge, playbooks, AND skills (all categories are the accumulated experiential body). Not a sub-slice. **One exemption:** the pinned knowledge-management skill (WS-3), always injected regardless of filter.

3. **Filtering is FACETS-ONLY.** The only dimension an agent can filter/query by is `metadata.facets` — governed on three levels:
   - **Keys** controlled by a configurable `knowledge_facets_schema` (enumerable set).
   - **Values** normalized at extraction (canonical casing/spelling).
   - **Vocabulary** discoverable via `GET /knowledge/facets` (distinct values in use).
   Agents **never** filter on `tags`.

4. **`tags` is off the agent surface entirely.** Ungoverned freeform → false-negative risk if used as a filter. Tags become a **human/admin-only** annotation shown in the dashboard, never in the agent-facing payload, never a query dimension. (Column stays as-is now; **drop it at the npm refactor**, not now — see §8.)

5. **`metadata` structure** (single JSONB, three clear roles, no duplication):
   ```json
   {
     "facets": { "country": "Malaysia", "program": "Computer Engineering", "level": "postgraduate" },
     "steps": [ ... ], "procedure": "...", "trigger_conditions": [ ... ],   // operational, top-level
     "always_inject": true                                                    // WS-3 pinned skill only
   }
   ```
   `facets` = structured filter dimensions. Operational keys stay top-level. **Do NOT nest tags under facets. Do NOT copy facet values into the `tags` column.**

6. **Facet codification does NOT modify the generation prompts.** A **separate `facet_extraction` step** runs after content is generated and writes `metadata.facets`. The storytelling record (`content`/`summary`) stays byte-identical. This preserves the zero-regression guarantee on memory/intelligence/knowledge generation.

7. **Facet schema is configurable per entity type** (like `knowledge_signals_prompt`). Seed a study-abroad default; admin refines in UI.

8. **Query facets come from three sources**, hybrid:
   - **Explicit** params from the n8n orchestrator (primary; it knows the contact's interest).
   - **Entity-profile-derived** — get-context maps `entity_profiles.properties` fields to facets automatically.
   - **Semantic** conversation vector — the always-on ranker (already built).
   Resolved facets → **hard filter** (pre-context). The `search` endpoint keeps a `strict=false` option so the agent's "broaden" step works.

9. **Epistemic contract** (authored into the WS-3 skill): pre-context knowledge is accumulated *experiential* knowledge — a **subset** of capability. **Absence of matches ≠ absence of knowledge ≠ absence of capability.** Fallback ladder: (1) broaden — re-query `/search/semantic` with facets dropped; (2) use assigned tools per system prompt; (3) delegate to the counselor sub-agent.

10. **Everything defaults to current behavior** until enabled. No mid-rollout regression.

---

## 2. Current-state code map (where to work)

| Concern | Location |
|---|---|
| get-context (knowledge block = lines ~480-543) | `backend/memory/agent.py:382` |
| `list_knowledge` (ignores entity filters — fix) | `backend/memory/agent.py:784` |
| Agent knowledge routes (POST/GET list; **no GET-by-id**) | `backend/memory/agent.py:763+` |
| Admin `GET /knowledge/{id}` (admin-only; can reuse `require_admin_or_agent`) | `backend/memory/admin.py:308` |
| Knowledge search (add facet filter) | `backend/services/search.py` `search_knowledge_by_vector/_fulltext` |
| `SearchRequest` model | `backend/memory_models.py:482` |
| `insert_knowledge` (renders SKILL.md) | `backend/memory_db_writes.py` |
| Knowledge creation pathways (call facet extraction from each) | `memory_knowledge.py`, `memory_playbooks.py`, `memory_hermes.py`, admin import in `memory/admin.py` |
| knowledge table schema + migrations | `backend/memory_db.py:273` (CREATE) + `:738` (ALTER) |
| entity type config (`knowledge_signals_prompt` pattern) | `backend/memory_db.py` `memory_entity_type_config`, `backend/memory/config.py` |
| `entity_profiles.properties` (CRM blob) | written by `memory_ingestion.py::_sync_entity_profile` |
| settings table + model + UI | `memory_db.py` `memory_settings`, `memory_models.py` `MemorySettingsUpdate`, `frontend/src/components/settings/MemorySettings.jsx` |
| SKILL.md render/parse | `backend/memory_skill_md.py` |

**DO NOT TOUCH**: any `inline_system_prompt` on `memory_llm_configs` for memory/intelligence/knowledge generation. Those are admin-owned and quality-frozen.

---

## 3. Workstreams (sequenced)

### WS-1 — Lean index injection mode
**Goal**: get-context can inject a lean index instead of full content.

- New setting `context_knowledge_mode`: `full` (default, = today's behavior exactly) | `index`.
  - Add column to `memory_settings` (`TEXT DEFAULT 'full'`), field on `MemorySettingsUpdate`, input on Knowledge settings tab.
- In get-context ([agent.py:480-543](../backend/memory/agent.py)), when `index`:
  - Each knowledge item = `{ id, name, category, signals, summary, facets }` where `facets = metadata->'facets'`.
  - **Drop** `content`, `tags`, and heavy metadata (`steps`, `procedure`, `trigger_conditions`).
  - `full` mode returns exactly today's shape (no change).
- Keep the existing relevance ranking + `context_knowledge_count` cap + fallback query.

**Acceptance**: with `context_knowledge_mode=index`, payload `knowledge[]` items carry no `content`; `full` mode is byte-identical to current output.

### WS-2 — On-demand retrieval + vocabulary endpoints
**Goal**: the agent can pull a full record and discover the facet vocabulary.

- `GET /api/memory/knowledge/{id}` (agent-facing, `verify_agent_key`): returns the full record incl. `content` (SKILL.md for skill/playbook), `metadata`, `signals`, `quality_score`, `merge_count`, `version`, `category`. (Distinct from the admin route; may share a helper.)
- `GET /api/memory/knowledge/facets` (agent + admin via `require_admin_or_agent`):
  - No param → `{ country: [...distinct values...], program: [...], ... }` for every schema key that has values in use.
  - `?key=country` → `["Malaysia", "United Kingdom", ...]`.
  - Values pulled from `metadata->'facets'` across `status='active'` records.
- **Fix `list_knowledge`** ([agent.py:784](../backend/memory/agent.py)): actually apply `entity_type`/`entity_subtype` (via facet match or drop the dead params), and add `category` + `facets` (JSON) + `strict` (bool, default false) query params.

**Acceptance**: agent key can `GET /knowledge/{id}` for a full record and `GET /knowledge/facets` for the live vocabulary; `list_knowledge` filters are no longer ignored.

### WS-3 — Pinned, always-on knowledge-management skill
**Goal**: an ever-present, UI-editable instruction that governs how the agent uses knowledge.

- Seed one knowledge record at startup (idempotent, only if absent):
  - `category='skill'`, `source_pathway='system'`, `status='active'`, `visibility='shared'`, `metadata.always_inject=true`.
  - `content` = a SKILL.md document (use `render_skill_md`) teaching the protocol (see §4).
- get-context injection: **prepend** all `metadata->>'always_inject' = 'true'` skills to the `knowledge[]` array **before** applying the facet hard filter and cap — i.e., always present, filter-exempt, not counted against `context_knowledge_count`. Works in both `full` and `index` modes (in index mode, still include its `content`/body so the instruction is actually readable — this record is the exception that carries its body).
- Editable through the normal Knowledge UI (it's a regular skill row); exports as SKILL.md via existing endpoint. Admin can revise the protocol without code changes.

**Acceptance**: every get-context response contains the management skill first, even when the facet filter matches zero other records.

### WS-4 — Facet codification (creation-side)
**Goal**: knowledge records carry structured `metadata.facets` — without touching generation prompts.

- New per-entity-type config `knowledge_facets_schema` (JSONB on `memory_entity_type_config`, nullable). Shape:
  ```json
  [
    {"key": "country", "label": "Country", "description": "Country the info pertains to", "examples": ["Malaysia", "United Kingdom"]},
    {"key": "university", "label": "University", "description": "Institution name"},
    {"key": "program", "label": "Program / Major", "description": "Field of study or program"},
    {"key": "field_of_study", "label": "Field", "description": "Broad discipline"},
    {"key": "level", "label": "Level", "description": "undergraduate | postgraduate | foundation | phd"},
    {"key": "requirement_type", "label": "Requirement type", "description": "entry | english | visa | financial | document"},
    {"key": "intake", "label": "Intake", "description": "Intake term/year if specific"}
  ]
  ```
  Seed this study-abroad default for the `contact` entity type (and/or a global default) on startup if absent.
- New shared async helper `extract_facets(name, content, summary, entity_type) -> dict`:
  - Reads the entity type's `knowledge_facets_schema`; if none, returns `{}` (no-op).
  - One LLM call (separate from generation): "Given this knowledge text and these facet keys with descriptions, extract a value for each key that is clearly present; omit keys not present; normalize values to canonical form (proper casing, full names). Return JSON `{key: value}`."
  - Uses `parse_llm_json`; on any failure returns `{}` (never blocks creation).
- Call it in **every** creation pathway, writing `metadata['facets']` before `insert_knowledge`: batch (`generate_knowledge_from_intelligence`), playbook + skill (`memory_playbooks`), Hermes (`memory_hermes`), import (admin). Gate behind setting `facet_extraction_enabled` (default `TRUE` — facets are additive metadata, no content regression; the only cost is one extra low-frequency LLM call).
- **Backfill**: `POST /api/memory/trigger/backfill-facets` (admin) → queue job that runs `extract_facets` over existing `status='active'` records missing `metadata.facets`. Add a "Backfill Facets" button on the Knowledge tab.

**Acceptance**: newly created knowledge has `metadata.facets` populated per schema; backfill populates existing records; generation `content`/`summary` unchanged.

### WS-5 — Facet-aware retrieval (retrieval-side)
**Goal**: get-context and search hard-filter on governed facets, broaden semantically.

- **get-context** new query params: `knowledge_facets` (JSON object, e.g. `{"country":"Malaysia"}`), `knowledge_category`.
  - Resolve facets: explicit param → else derive from `entity_profiles.properties` (map configured fields to facet keys via a `profile_facet_map` in entity config, optional) → else none.
  - When facets resolved: **hard filter** `metadata @> '{"facets": {...}}'` (JSONB containment, GIN-indexed) AND-combined with category if given. Applies to ALL categories.
  - The WS-3 always_inject skill(s) bypass this filter (prepended before it).
  - When no facets resolved: current semantic+quality behavior (no regression).
- **search** (`search_knowledge_by_vector`/`_fulltext` + `SearchRequest`): add `knowledge_facets` (dict) + `strict` (bool, default `false`). `strict=true` → hard containment filter; `strict=false` → facets ignored (pure semantic — the agent's "broaden" path).
- Add GIN index: `CREATE INDEX IF NOT EXISTS idx_knowledge_metadata_gin ON knowledge USING gin (metadata jsonb_path_ops)`.

**Acceptance**: get-context with `knowledge_facets={"country":"Malaysia"}` returns only Malaysia-faceted records (+ the pinned skill); `/search/semantic` with `strict=false` ignores facets for broadening.

---

## 4. The knowledge-management skill — required content

Author this into WS-3's seeded SKILL.md `content` (admin-editable afterward). It MUST teach:

1. **What this is**: "The knowledge below is *experiential* knowledge this organization has accumulated from past interactions (best practices, lessons, trade knowledge, playbooks, skills). It is a **subset** of what you know and can do — not the whole of it."
2. **How it was selected**: "It was filtered to the current conversation's context (facets such as country/program). It is an **index**: each item shows `id, name, category, signals, summary, facets` — not full content."
3. **Critical caveat**: "**Absence of matches here does NOT mean the knowledge or capability is absent.** A sparse or empty list means only that we have not yet codified experiential knowledge matching these exact facets."
4. **How to pull full content**: "If an index entry looks relevant, retrieve the full record via the knowledge sub-agent node (`GET /knowledge/{id}`) before acting on it."
5. **Fallback ladder when the index is thin**:
   - (a) **Broaden** — re-query `/search/semantic` with the strict facets dropped (`strict=false`) to find near-matches.
   - (b) **Use your assigned tools** per the system prompt.
   - (c) **Delegate** to the specialized counselor sub-agent to source/find the information.
6. **Facet discipline**: "Valid facet keys are: {list}. Do **not** invent facet values — use values seen in the index, the contact's CRM profile, or `GET /knowledge/facets`. If unsure, broaden semantically."
7. **Contributing back**: how to submit feedback (`POST /knowledge/{id}/feedback`) and how new knowledge is created (it is generated automatically from interactions; the agent's job is to *use and delegate*, not manually write knowledge unless instructed).

Keep it concise and imperative. This skill is the guardrail that makes the hard filter safe.

---

## 5. New settings summary (all default = current behavior)

| Setting | Default | Effect |
|---|---|---|
| `context_knowledge_mode` | `full` | `index` = lean index injection (WS-1) |
| `facet_extraction_enabled` | `TRUE` | run facet extraction on knowledge creation (WS-4) |
| (existing) `context_knowledge_count` | 30 | injection cap |
| (existing) `context_knowledge_min_similarity` | 0.0 | similarity floor |

New per-entity-type config: `knowledge_facets_schema` (JSONB), optional `profile_facet_map` (JSONB).
New endpoints: `GET /knowledge/{id}` (agent), `GET /knowledge/facets`, `POST /trigger/backfill-facets`.
New index: `idx_knowledge_metadata_gin`.

---

## 6. Zero-regression checklist (enforce during implementation)

- [ ] No `inline_system_prompt` for memory/intelligence/knowledge generation modified.
- [ ] `context_knowledge_mode=full` output is byte-identical to pre-change get-context.
- [ ] `facet_extraction` failures return `{}` and never block or alter knowledge creation.
- [ ] get-context with no resolved facets behaves exactly as today (semantic+quality).
- [ ] `search` with `strict=false` (default) ignores facets.
- [ ] Every new column/endpoint is additive; `tags` column untouched.

---

## 7. Acceptance test (end-to-end, study-abroad)

1. Seed facet schema; backfill facets over existing knowledge → records get `metadata.facets`.
2. Create knowledge about "CompEng entry requirements, University X, Malaysia" → `metadata.facets = {country: Malaysia, university: University X, program: Computer Engineering, requirement_type: entry}`.
3. `get-context?entity_type=contact&entity_id=...&knowledge_facets={"country":"Malaysia"}&context_knowledge_mode=index` → returns the pinned management skill first, then only Malaysia-faceted index items (no `content`).
4. Agent pulls a full record via `GET /knowledge/{id}`.
5. `get-context` for a UK contact → Malaysia records absent; management skill still present and instructs broaden/delegate.
6. `GET /knowledge/facets?key=country` → `["Malaysia", ...]`.

---

## 8. Deferred to npm refactor (`mastermemory`)

- **Drop the `tags` column**; fold any freeform labels into `metadata.tags` in the clean-slate schema (no migration cost there). Until then, `tags` stays as a human/admin-only field, off the agent surface. Recorded in [mastermemory-npm-migration.md](mastermemory-npm-migration.md).
