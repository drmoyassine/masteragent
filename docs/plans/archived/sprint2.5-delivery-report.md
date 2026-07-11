# Sprint 2.5 — Knowledge Pre-Context Retrieval: Delivery Report

> **Status**: Implemented 2026-07-06 and archived. Branch `feat/sprint2.5-knowledge-precontext-retrieval`.
> **Spec**: [knowledge-precontext-retrieval-plan.md](knowledge-precontext-retrieval-plan.md). All five workstreams delivered.

---

## 1. What changed, in one paragraph

`GET /get-context` now injects knowledge as a **lean, governed, filterable index** instead of a flat blob of up to 30 full records. Knowledge records carry structured `metadata.facets` (country/program/university/level/…) extracted by a dedicated LLM step that **never touches the generation prompts**. Agents hard-filter on those governed facets, broaden semantically when the index is thin, and pull full records on demand via a new `GET /knowledge/{id}`. An always-on, UI-editable **Knowledge Management skill** is pinned first in every payload and teaches the epistemic contract: *absence of matches ≠ absence of knowledge ≠ absence of capability*. Everything defaults to prior behavior until the admin opts in.

---

## 2. Workstream delivery

### WS-1 — Lean index injection mode ✅
- New setting **`context_knowledge_mode`** (`full` default | `index`).
- In `index` mode each knowledge item = `{id, name, category, signals, summary, facets}` — **no `content`, no heavy metadata, no `tags`**.
- `full` mode is byte-identical to the pre-Sprint-2.5 payload.
- Relevance ranking, `context_knowledge_count` cap, similarity floor, and fallback query all preserved.

### WS-2 — On-demand retrieval + vocabulary endpoints ✅
- **`GET /api/memory/knowledge/{id}`** (agent key) — full record incl. `content` (SKILL.md for skill/playbook), `metadata`, `version`, `quality_score`.
- **`GET /api/memory/knowledge/facets`** (agent key) — governed vocabulary: no param → `{key: [values…]}`; `?key=country` → `[...]`. Uses `metadata->'facets'->>key`.
- **`list_knowledge` fixed**: dropped the dead `entity_type`/`entity_subtype` params; added real `category`, `facets` (JSON), `strict`, `status` filters; returns full unified-table columns.

### WS-3 — Pinned always-on Knowledge Management skill ✅
- Seeded at startup (idempotent, stable id `00000000-0000-0000-0000-knowledge-mgmt`): `category='skill'`, `metadata.always_inject=true`, `source_pathway='system'`, `quality_score=1.0`.
- Its SKILL.md body teaches: what experiential knowledge is, how it was facet-selected, the **absence≠absence≠absence** rule, on-demand pull, the **broaden → tools → delegate** fallback ladder, facet discipline, and feedback.
- get-context **prepends** all `metadata->>'always_inject'='true'` skills **before** the facet filter and cap — always present, filter-exempt, full-content in both modes.
- Editable in the normal Knowledge UI; exports as SKILL.md. (Verified: `always_inject` does not leak into the rendered body.)

### WS-4 — Facet codification (creation-side) ✅
- New global setting **`knowledge_facets_schema`** (JSONB) — seeded with a study-abroad default (`country, university, program, field_of_study, level, requirement_type, intake`). Editable via a JSON textarea in the UI.
- New async **`extract_facets(name, content, summary)`** ([memory_facets.py](../backend/memory_facets.py)): one LLM call, returns `{}`, gated by **`facet_extraction_enabled`** (default TRUE). Best-effort: returns `{}` on any failure → never blocks or alters creation.
- Wired into **every** creation pathway via `enrich_metadata_with_facets()`: batch generation, playbook extraction, skill decomposition, Hermes, marketplace import, admin manual create.
- **`POST /api/memory/trigger/backfill-facets`** + queue job + UI **Backfill Facets** button → runs extraction over existing active records missing `metadata.facets`.
- Facets live under `metadata.facets`; the SKILL.md renderer only reads operational keys, so facets never pollute the rendered document body. Generation `content`/`summary` untouched.

### WS-5 — Facet-aware retrieval ✅
- get-context new params **`knowledge_facets`** (JSON) + **`knowledge_category`**.
- Facet resolution: explicit param → else **entity-profile-derived** via opt-in `profile_facet_map` → else none.
- Resolved facets → **hard filter** `metadata @> '{"facets":{…}}'` (GIN-indexed) across all categories; applies to declarative + playbooks + skills. Pinned skill exempt.
- `search/semantic` + `search/fulltext` accept `knowledge_facets` + **`strict`** (default `false` = ignore facets = the agent's broaden path; `true` = hard filter).
- New GIN index `idx_knowledge_metadata_gin ON knowledge USING gin (metadata jsonb_path_ops)`.

---

## 3. New settings, endpoints, schema (all additive)

**Settings (`memory_settings`, all default to prior behavior):**
| Setting | Default | Effect |
|---|---|---|
| `context_knowledge_mode` | `full` | `index` = lean injection |
| `facet_extraction_enabled` | `TRUE` | run facet extraction on creation |
| `knowledge_facets_schema` | seeded study-abroad | governed facet keys |
| `profile_facet_map` | `NULL` (opt-in) | facet_key → entity_profiles property |

**Endpoints (all additive):**
- `GET /api/memory/knowledge/{id}` (agent) — on-demand full record
- `GET /api/memory/knowledge/facets[?key=]` (agent) — governed vocabulary
- `POST /api/memory/trigger/backfill-facets` (admin)

**Schema:** GIN index on `knowledge.metadata`; no new tables; `tags` column untouched.

---

## 4. Zero-regression guarantees (verified)

- ✅ No `inline_system_prompt` for memory/intelligence/knowledge generation was modified.
- ✅ `context_knowledge_mode=full` (default) → get-context payload is the Sprint-2 shape (plus the always-on management skill prepended).
- ✅ `profile_facet_map` defaults to NULL (not seeded) → get-context derives no facets → **no hard filter** until the admin opts in or the orchestrator passes `knowledge_facets`. This was a deliberate fix: auto-seeding the map would have excluded un-facetted records before backfill.
- ✅ `facet_extraction` returns `{}` on any failure and never alters `content`/`summary`.
- ✅ `search` `strict=false` (default) ignores facets.
- ✅ `extract_facets` is gated and degrades to `{}` when disabled or unconfigured.
- ✅ Backend compiles clean across all 16 edited modules; `memory_facets`/`memory_skill_md`/`memory_dedup` have no top-level cycles (all heavy imports are lazy).
- ✅ Management-skill rendering round-trip tested: `always_inject` stays out of the SKILL.md body; all required protocol sections present; slug `knowledge-management-protocol`.

---

## 5. Files changed

**Backend (new):**
- `backend/memory_facets.py` — facets + management skill (core of WS-3/WS-4)

**Backend (edited):**
- `backend/memory_db.py` — 4 settings columns, GIN index, seed calls
- `backend/memory_models.py` — `MemorySettingsUpdate`/`SearchRequest` fields
- `backend/memory_db_writes.py` — (no change; facets flow via `metadata`)
- `backend/memory_knowledge.py`, `memory_playbooks.py`, `memory_hermes.py` — facet enrichment at creation
- `backend/memory/agent.py` — get-context rewrite (WS-1/3/5), `GET /knowledge/{id}`, `GET /knowledge/facets`, fixed `list_knowledge`, search facets/strict
- `backend/memory/admin.py` — facet enrichment in import + manual create, `POST /trigger/backfill-facets`
- `backend/memory/config.py` — JSONB field set for new settings
- `backend/memory/queue.py` — `backfill_facets` job
- `backend/services/search.py` — `facets`/`strict` on knowledge search

**Frontend (edited):**
- `frontend/src/lib/api.js` — `getKnowledgeById`, `getKnowledgeFacets`, `triggerBackfillFacets`
- `frontend/src/components/settings/MemorySettings.jsx` — injection-mode select, facet-extraction toggle, facets-schema + profile-map JSON editors, Backfill Facets button

**Docs:** `docs/knowledge-precontext-retrieval-plan.md` (the spec, ships with this branch).

---

## 6. Deploy + verification (acceptance test from the plan)

1. **Deploy** the merge → startup migration adds the 4 settings columns, the GIN index, seeds the facets schema + the Knowledge Management skill.
2. **Backfill facets** (Knowledge tab → *Backfill Facets*, or `POST /trigger/backfill-facets`) → existing records get `metadata.facets`. Watch `docker logs` for `Facet backfill complete: processed=… enriched=…`.
3. Create knowledge about "CompEng entry requirements, University X, Malaysia" → new record carries `metadata.facets = {country:"Malaysia", university:"University X", program:"Computer Engineering", requirement_type:"entry"}`.
4. `get-context?entity_type=contact&entity_id=…&context_knowledge_mode=index` → the management skill appears first (full), then lean index items (no `content`).
5. `get-context?…&knowledge_facets={"country":"Malaysia"}` → only Malaysia-faceted records (+ the pinned skill).
6. `GET /knowledge/{id}` → full record pulled on demand.
7. `GET /knowledge/facets?key=country` → `["Malaysia", …]`.
8. To **opt into automatic CRM-derived filtering**: set the *Profile → Facet Map* in the UI (e.g. `{"country":"country","program":"program","level":"level","university":"university"}`) to match your CRM field names — then every get-context for a contact auto-derives facets from their profile.

---

## 6b. Post-merge review fixes (2026-07-06)

A detailed review flagged and fixed the following in `feat/sprint2.5-review-fixes`:

1. **🔴 Facet false-negative (casing mismatch)** — `metadata @>` is an exact match, but profile-derived facet values used the raw CRM value (`str(v)`). A CRM `country="malaysia"` would hard-filter to **zero** records stored as `"Malaysia"` — the precise false-negative the facet design exists to prevent. **Fix**: `canonicalize_facets()` maps values to the stored spelling case-insensitively before filtering; profile-derived values that match nothing in the corpus are **dropped** (rather than filtering to zero).
2. **🔴 Governance skill was agent-mutable** — agents have `PATCH`/`DELETE /knowledge/{id}`; a single key could delete or de-flag the always-on management skill, removing governance for every agent. **Fix**: `_assert_agent_mutable()` returns 403 for `source_pathway='system'` or `always_inject=true` records on the agent PATCH/DELETE paths (admin endpoints unaffected).
3. **🟠 `extract_facets` value coercion** — LLM could return non-scalar values that never match a scalar `@>` filter. **Fix**: coerce to trimmed strings, drop list/dict/empty values.
4. **🟠 Backfill skipped empty-facet records** — matched only `facets IS NULL`, but disabled-extraction records have `facets={}`. **Fix**: match `COALESCE(metadata->'facets','{}') = '{}'`.
5. **🟠 Agent `POST /knowledge` deviation** — ignored `category`/`metadata`/`status` and never rendered SKILL.md or extracted facets. **Fix**: routed through `insert_knowledge` + `enrich_metadata_with_facets` (also fixes a latent `source_Intelligence_ids` attribute-name bug and JSONB metadata serialization on the agent PATCH).
6. **🟡 Management-skill wording** — said items are index-only; corrected to "may be index or full; treat absence of `content` as an index entry."

**Tenant isolation**: reviewed — single-org-per-deployment by design; knowledge is intentionally global/org-wide (a locked decision). `visibility='shared'` filtering correctly excludes `private`/`team`. No cross-tenant leak vector; the actionable item was governance-record protection (#2).

## 6c. WS-3 UI completion — Knowledge browser + always-on toggle + install (2026-07-06)

Closes the WS-3 shortfall flagged in review (skill install + always-on toggle were API-only, no UI). Branch `feat/knowledge-browser-always-on`:

- **Category sub-tabs** on the Knowledge tab (All · Best Practices · Lessons · Trade · Playbooks · Skills) for browsing each record type.
- **"Always On" toggle column** — flips `metadata.always_inject` per record via a new dedicated field on the admin knowledge PATCH (`always_inject: bool`, merged into JSONB without replacing the blob). Pinned records show a pin icon. **The system-governed management skill's toggle is disabled** (can't be un-pinned from the UI — it's `source_pathway='system'`). This is the mechanism for **transient/time-bound knowledge**: create a "limited-time offer" or "office-closed" record, flip Always On, flip it off when done.
- **Install dialog** (Skills/Playbooks sub-tabs) — paste a SKILL.md doc → `POST /skills/import` (dedup-merge, imported as draft).
- **Archive / Restore** actions — soft-archives via `status='retired'` instead of only hard delete; archived records show with a Restore action.
- **Backend**: `KnowledgeUpdate.always_inject` field + PATCH handler that merges the single key into existing metadata. Also fixed a **latent `source_Intelligence_ids` attribute-name bug** in the admin `create_knowledge` (capital-I field on `KnowledgeCreate`) that would have thrown on manual knowledge creation.

## 7. Known follow-ups (small, additive — not blocking)

- **System Monitor UI panel** for `/pipeline-runs` (data + endpoint exist from Sprint 2; no UI yet).
- **Knowledge-tab UI**: import dialog + per-record export button (API clients wired; endpoints live).
- The Knowledge Management skill is admin-editable; consider reviewing its wording post-deploy against real n8n counselor behavior.
- `tags` column drop deferred to the `mastermemory` npm refactor (recorded in [mastermemory-npm-migration.md](../../mastermemory-npm-migration.md)).

---

## 8. Note on shipping

The branch was committed locally on 2026-07-06; the initial push attempt failed due to a transient GitHub connectivity outage from the working environment. The commit (`feat/sprint2.5-knowledge-precontext-retrieval`) contains the full implementation + the plan doc + this report. Push/PR/merge should complete once connectivity is restored — or run:
```bash
git push -u origin feat/sprint2.5-knowledge-precontext-retrieval
gh pr create --fill-first && gh pr merge --merge --delete-branch
```
