# Knowledge Hygiene & Consolidation — Delivery Report

**Feature:** Cluster-based knowledge hygiene & consolidation system (replaces legacy pairwise dedup)
**Plan reference:** `pairwise-to-clustering-knowledge-hygiene-plan.md`
**Delivery:** PR #48 — commit `8ce57e0`, merged to `main` (`98eff5e`) on 2026-07-11
**Status:** ✅ Implemented & deployable · ❌ Not yet deployed to VPS (no deployment access this session)

---

## 0. Executive summary

Embedding similarity now **only discovers and groups** candidate knowledge records. The merge decision always comes from a category-aware LLM proposal (`knowledge_consolidation` task) plus deterministic safety checks and review policy. The legacy pairwise dedup retirement loop is **removed**; backward-compatible job/route names delegate to the new hygiene system.

All six work packages (PR 1–6) are implemented in one continuous delivery. The PR labels are review checkpoints, not handoffs or TODOs.

> **Production rollout is `manual_only` by default.** `auto_conservative`, `auto_synthesis`, and creation-time consolidation ship **disabled**; enabling them in the admin UI requires no further code change or deployment.

---

## 1. Files changed

### 1.1 New backend modules (7)

| File | Responsibility |
|---|---|
| `backend/memory_embedding.py` | One deterministic category-aware embedding-serialization path for all 5 categories (skill/playbook include operational fields: triggers, steps, procedure, prerequisites, tools, permissions, safety, etc.). Records model / dimensions / version / timestamp in `knowledge.metadata.embedding` (`EMBEDDING_VERSION = 2`). |
| `backend/memory_similarity.py` | Pure standard-library vector primitives — cosine, L2-normalize, pairwise min/mean/max, centroid, member-to-centroid, threshold edges, weak-link detection, deterministic union-find connected components. **No numpy/scipy/sklearn.** |
| `backend/memory_clustering.py` | Candidate discovery + the §14.3 splitting algorithm: edge-removal for cohesion/weak-link failures; oversized-but-cohesive components size-split to `manual_review` (never auto-applied); singletons are analysis-only. Deterministic under shuffled input. |
| `backend/memory_consolidation_prompts.py` | Shared base prompt + per-category preservation rules; strict Pydantic proposal schema (§5.2); one repair retry. Prompt version pinned (`v1`). |
| `backend/memory_consolidation_repository.py` | All SQL. Preview/event/audit persistence + the **single transactional apply** (advisory lock → `SELECT … FOR UPDATE` in ID order → stale-preview rejection → atomic retire → mark applied) and dependency-validated reversal. |
| `backend/memory_consolidation_service.py` | The one orchestration boundary (`preview` / `apply` / `regenerate` / `reverse` / `discover_and_propose` / `creation_time_propose`) used by every caller. |
| `backend/memory_embedding_backfill.py` | Resumable, idempotent, content-preserving embedding backfill — batches of 50, per-record error capture, version-guarded UPDATE. |

### 1.2 New frontend components (2)

| File | Responsibility |
|---|---|
| `frontend/src/components/memory/KnowledgeConsolidationDialog.jsx` | 5-step flow: Sources → Generate/Review Proposal → Edit Canonical → Confirm → Result. Shows min/avg/max similarity, per-member centroid similarity, embedding compatibility, LLM recommendation/confidence/rationale, retained info, removed repetition, warnings, contradictions, unreconciled info, per-source traceability; visually flags edits; offers update-existing vs create-new. |
| `frontend/src/components/memory/KnowledgeLineagePanel.jsx` | Rendered inside `KnowledgeInspector` for canonical + retired records: successor (`merged_into`), predecessors (`merged_from`), event detail, admin **Reverse consolidation** action. |

### 1.3 Modified backend (15)

| File | Change |
|---|---|
| `backend/memory_db.py` | Additive schema: 4 knowledge lineage columns + 3 indexes; **7 new tables** (§2); 15 hygiene settings columns; seeds `knowledge_consolidation` LLM config from `knowledge_generation`. |
| `backend/memory_db_writes.py` | `insert_knowledge` stamps embedding provenance; creation-time consolidation hook (fire-and-forget enqueue when `knowledge_hygiene_creation_time_enabled`). |
| `backend/memory/admin.py` | 11 new authenticated admin routes (§3). |
| `backend/memory/config.py` | Hygiene JSONB fields added to `JSONB_FIELDS` for settings write. |
| `backend/memory/queue.py` | New jobs: `knowledge_hygiene_run`, `knowledge_embedding_backfill`, `creation_time_consolidation`; legacy `run_consolidation` delegates to hygiene. |
| `backend/memory_consolidation.py` | `run_consolidation` now runs hygiene discovery (mode-gated) + decay + quality recompute; **pairwise retirement loop removed**. |
| `backend/memory_models.py` | Hygiene fields on `MemorySettingsUpdate`/`MemorySettingsResponse`; `ConsolidationOptions`, `CanonicalFields`, `ConsolidationPreviewRequest`, `ConsolidationApplyRequest`, `ConsolidationAnalyzeRequest`. |
| `backend/memory_dedup.py` | Embedding via canonical serializer; provenance stamped on refine update. |
| `backend/memory_knowledge.py`, `memory_telemetry.py`, `memory_playbooks.py`, `memory_hermes.py` | All creation paths route embeddings through the canonical serializer. |
| `backend/memory/agent.py`, `memory_prior_context.py`, `services/search.py` | Agent retrieval / search / get-context / prior-context hard active-only (retired records never leak). |

### 1.4 Modified frontend (5)
`KnowledgeTab.jsx` (multi-select Merge/Consolidate action, 2+ same-category), `KnowledgeInspector.jsx` (lineage panel), `MemorySettings.jsx` (full hygiene card + embedding coverage + Analyze now / Backfill), `MemoryExplorerPage.jsx` (dialog state wiring), `lib/api.js` (11 endpoints).

### 1.5 Tests (1 new file)
`backend/tests/test_knowledge_consolidation.py` — **62 pure unit tests** after post-delivery QA hardening.

---

## 2. Schema additions (additive, idempotent)

All DDL uses `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE … ADD COLUMN IF NOT EXISTS`. Created automatically on backend startup — no separate migration command.

### 2.1 Knowledge lineage columns
```sql
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS merged_into TEXT;
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS merged_from TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS consolidation_event_id TEXT;
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS consolidation_protected BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_knowledge_merged_into ON knowledge(merged_into);
CREATE INDEX IF NOT EXISTS idx_knowledge_consolidation_event ON knowledge(consolidation_event_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_merged_from ON knowledge USING GIN (merged_from);
```

### 2.2 New tables (7)
1. `knowledge_hygiene_runs` — run metadata, settings snapshot, mode, counts, status, actor/origin.
2. `knowledge_hygiene_clusters` — run/category, member_ids, centroid (vector), min/avg/max similarity, cohesion, weak_links, split_reason, proposal_id, status.
3. `knowledge_hygiene_cluster_members` — (cluster_id, knowledge_id), similarity_to_centroid, role, decision_reason.
4. `knowledge_consolidation_previews` — origin, actor, category, state, source_ids, source_snapshot, metrics, options, settings_snapshot, model/prompt, raw_response, proposal, validation_errors, expires_at, applied_event_id.
5. `knowledge_consolidation_preview_sources` — (preview_id, knowledge_id), source_version, source_updated_at, source_status, source_snapshot.
6. `knowledge_consolidation_events` — preview_id, action, canonical_id, strategy, model/prompt, similarity_threshold, proposed/approved output, user_edits, warnings, contradictions, reversed_event_id.
7. `knowledge_consolidation_event_sources` — (event_id, knowledge_id), role, original_snapshot, source_traceability, merged_into.

**Foreign keys:** only internal cascade cleanups (cluster→run, member→cluster, preview_source→preview, event_source→event). **No FK from audit/lineage tables to `knowledge`** and none on `knowledge.merged_into`, so recovery survives later manual deletion.

### 2.3 Settings columns (15)
`knowledge_hygiene_enabled`, `knowledge_hygiene_enabled_categories` (JSONB), `knowledge_hygiene_similarity_threshold`, `knowledge_hygiene_min_cluster_size`, `knowledge_hygiene_max_cluster_size`, `knowledge_hygiene_min_cluster_cohesion`, `knowledge_hygiene_weak_link_threshold`, `knowledge_hygiene_embedding_version`, `knowledge_hygiene_mode`, `knowledge_hygiene_preview_ttl_minutes`, `knowledge_hygiene_min_auto_confidence`, `knowledge_hygiene_contradiction_policy`, `knowledge_hygiene_default_canonical_strategy`, `knowledge_hygiene_creation_time_enabled`, `knowledge_hygiene_category_policies` (JSONB).

---

## 3. API surface (admin, authenticated)

All under `/api/memory/admin/knowledge/…`, guarded by `Depends(require_admin_auth)`.

| Method & path | Behavior | Status codes |
|---|---|---|
| `POST /consolidations/preview` | Synchronous non-mutating preview for 2+ same-category IDs | 200 / 400 invalid category/options / 404 missing source / 422 LLM |
| `GET /consolidations/previews/{id}` | Preview + source snapshots + metrics + proposal | 200 / 404 |
| `POST /consolidations/previews/{id}/regenerate` | Expire old, create fresh preview from current sources | 200 / 404 / 410 |
| `POST /consolidations/apply` | Apply approved canonical transactionally | 200 / 404 / 409 stale/applied/merged / 410 expired / 422 invalid canonical or embedding |
| `GET /consolidations/events/{id}` | Full lineage/audit detail | 200 / 404 |
| `POST /consolidations/events/{id}/reverse` | Reverse when dependency validation permits | 200 / 404 / 409 dependency conflict |
| `GET /consolidations/lineage/{knowledge_id}` | Successor / predecessors / event | 200 / 404 |
| `POST /consolidations/analyze` | Create run row + queue analysis/proposal job | 202 |
| `GET /hygiene-runs/{run_id}` | Run + clusters + members | 200 / 404 |
| `GET /consolidations/embedding-coverage` | Coverage gauge for settings UI | 200 |
| `POST /consolidations/backfill-embeddings` | Queue embedding backfill | 202 |

Agent-facing endpoints receive **no** apply authority.

---

## 4. Default settings (production-safe)

| Setting | Default |
|---|---|
| `knowledge_hygiene_enabled` | `true` |
| `knowledge_hygiene_enabled_categories` | all 5 (`best_practices`, `lessons_learned`, `trade_knowledge`, `skill`, `playbook`) |
| `knowledge_hygiene_similarity_threshold` | `0.82` |
| `knowledge_hygiene_min_cluster_size` / `max_cluster_size` | `2` / `5` |
| `knowledge_hygiene_min_cluster_cohesion` | `0.72` |
| `knowledge_hygiene_weak_link_threshold` | `0.65` |
| `knowledge_hygiene_embedding_version` | `2` |
| `knowledge_hygiene_mode` | **`manual_only`** |
| `knowledge_hygiene_preview_ttl_minutes` | `60` |
| `knowledge_hygiene_min_auto_confidence` | `0.90` |
| `knowledge_hygiene_contradiction_policy` | `manual_review` |
| `knowledge_hygiene_default_canonical_strategy` | `update_existing` |
| `knowledge_hygiene_creation_time_enabled` | **`false`** |
| `knowledge_hygiene_category_policies` | every category = `manual_only` |

Legacy `dedup_similarity_threshold` remains readable for backward compatibility; new hygiene code does not use it.

---

## 5. Verification results

Run from repo root with the plan's §18.2 commands.

| Check | Command | Result |
|---|---|---|
| Backend syntax | `python -m compileall backend` | ✅ clean |
| New unit suite | `python -m pytest backend/tests/test_knowledge_consolidation.py` | ✅ **62 passed** |
| Frontend tests | `npm test -- --watchAll=false` | ✅ 2 passed |
| Frontend build | `CI=true npm run build` | ✅ compiled successfully |
| Compose validate | `docker compose config --quiet` | ✅ OK |
| Whitespace | `git -c core.whitespace=cr-at-eol diff --check` | ✅ clean |

### 5.1 Unit-test coverage (what QA can rely on)
- **Similarity:** cosine (identical/orthogonal/opposite/zero), L2-normalize, pairwise determinism + completeness, min/mean/max, centroid + member-to-centroid, threshold edges, weak links, deterministic connected components.
- **Clustering (§14.3):** two tight pairs + singleton; **deterministic under shuffle**; category partitioning (never cross-category); **oversize component → `manual_review` (size_forced)**; weak-chain split; manual-group metrics.
- **Embedding serialization:** deterministic per category; skills include procedure/when-to-use; playbooks include steps/triggers; trade-knowledge includes governed facets; metadata stamp preserves other keys; version compatibility; all 5 categories supported.
- **Proposal validation:** all 5 recommendation enums; merge requires canonical; invalid recommendation rejected; confidence clamped; non-dict rejected; prompts carry category rules; prompt version pinned.
- **Canonical aggregation (§14.4):** union/dedup preserves order; facet conflict → contradictions + `consolidation_conflicts`; **LLM cannot set version/status/lineage**; `merge_count = sum + absorbed`; `version = base + 1`.
- **Policy gating:** merge+high-confidence allowed; low-confidence blocked; contradictions block; `manual_review` policy blocks; category-policy blocks.
- **Settings models:** update accepts all fields; response defaults match plan; `embedding_version` matches setting default.
- **Request models + error codes:** preview/apply defaults; `ConsolidationError` carries status.
- **LLM pipeline (fake provider, no paid API):** happy path; repair retry on invalid JSON; fail-after-retry; skill name slug validation.

### 5.2 Tests not runnable in this environment
The **pre-existing HTTP integration suite** (`test_admin.py`, `test_memory_system.py`, `test_pipeline.py`, `test_webhooks.py`, `test_workspace.py`, `test_supabase_config.py`) requires a live backend at `localhost:8080`. Observed: 37 failed / 77 errors, **all `requests.exceptions.ConnectionError: … localhost:8080 … connection refused`**. Per plan §18.2 these are documented and **not** counted as passed. They will run normally once the backend is up (VPS or `docker compose up`).

---

## 6. Deployment

- **No separate SQL migration.** `init_memory_db()` creates all schema idempotently on backend startup and seeds safe defaults + the `knowledge_consolidation` LLM config (copied from `knowledge_generation`; no credentials duplicated).
- **Deploy command:** the repo's existing Docker-based deploy (`docker compose config` validates clean). No code change required to activate.
- **First startup sequence:** schema + settings created → starts `manual_only` (no automatic retirement) → embedding coverage visible in Settings → Knowledge Hygiene → **Backfill embeddings** runnable → **Analyze now** runnable → manual same-category consolidation works immediately, even before backfill completes.

---

## 7. Implemented-and-deployable vs deployed-to-VPS

- **Implemented & deployable:** ✅ all 6 work packages; schema; settings; UI; queue/scheduler; tests; build green; merged to `main`.
- **Deployed to VPS:** ❌ not this session (no VPS access). Startup migration + UI controls complete activation on the next deploy with **no additional coding**.

The coding agent does **not** claim production activation. It leaves a single deployable build in which startup migration and UI controls complete activation without additional coding.

---

## 8. Compatibility guarantees

1. Schema changes are additive and idempotent.
2. **Source records are never hard-deleted** — retired sources keep all original fields and point to their canonical successor.
3. Agent retrieval / search / get-context / prior-context return **active records only** (hard `status = 'active'`); admins can view retired records + successor links.
4. Existing skill/playbook storage remains valid (content = SKILL.md; structured fields in metadata); new code supports both current and expanded operational fields.
5. Generation, admin, Hermes, telemetry, import, and playbook paths continue working with hygiene flags disabled.
6. **No LLM request mutates knowledge** — preview and apply are distinct operations.
7. Manual, scheduled, admin-triggered, and creation-time workflows use **one** proposal service and **one** transactional apply service.

---

## 9. Production rollout checklist (for the operator)

1. Deploy the build once. Startup creates additive schema + safe defaults.
2. Confirm the system starts in `manual_only` (no automatic source retirement).
3. Inspect embedding coverage in Settings → Knowledge Hygiene; run **Backfill embeddings**.
4. Use **Analyze now** to inspect threshold distributions, cohesion, component sizes, and category samples — **no mutation**.
5. Review generated proposals (especially skills and playbooks); perform the first applications through the manual Knowledge-table workflow.
6. Measure proposal acceptance, fact-loss reports, contradiction rates, stale-preview rates, retrieval quality.
7. Only after calibration: enable `auto_conservative` / `auto_synthesis` / creation-time consolidation in the UI — **no code change or redeploy required**.

**Production success criteria (not "fewer rows"):** fewer redundant retrieval results, stronger canonical knowledge, preserved operational correctness, complete lineage, reversible audit evidence, and no unapproved content loss.

---

## 10. Known follow-ups / non-blocking notes

- The weekly schedule still queues `run_consolidation`, which now does hygiene discovery (gated) + decay + quality recompute. `_refine_playbook` is retained as inert dead code (no callers) — safe to remove in a later cleanup.
- Centroid vectors are stored best-effort on `knowledge_hygiene_clusters.centroid`; the operative grouping metrics are cohesion + member-to-centroid similarities (centroid persistence is an optimization for future automated/creation-time candidate lookup).
- Category-specific automation policies are surfaced in settings; per-category tuning can be calibrated against dry-run data before any auto mode is enabled.

---

## 11. Post-delivery critical review and hardening

A second implementation-level review found defects that the original delivery tests did not exercise. They are fixed in the working tree covered by this report; the original PR commit alone should not be promoted without these hardening changes.

### Correctness and data integrity fixes

- Audit snapshots now serialize database timestamps and vector values reliably.
- Canonical records now retain their consolidation event ID and operational skill/playbook representation on both canonical strategies.
- Reversal restores the complete pre-merge record state, including provenance, evidence, tags, signals, embedding, status, lineage, and governed metadata. It rejects missing dependencies and canonicals edited after consolidation.
- Apply locks the preview and accepts only a current `ready` preview. Applied previews cannot be regenerated or reapplied.
- Embedding backfill selects stale rows in SQL by version, model, and dimensions, cannot stop early behind a page of current rows, and cannot loop forever on one failed row.
- Automated eligibility no longer treats the candidate-discovery similarity threshold as a merge threshold.
- Clustering split decisions are deterministic and evaluate true all-pairs cohesion instead of only surviving graph edges.
- Manual similarity metrics are flattened consistently for prompts, UI display, and automated gates; the previous nested shape could incorrectly read cohesion as zero.
- Every discovered group is auditable; acceptable manual-review groups may receive proposals but never auto-apply.

### Safety and security fixes

- Manual requests cannot spoof consolidation origin or audit actor identity; the authenticated administrator is authoritative.
- The Analyze action is explicitly non-destructive and cannot submit an automatic-apply mode.
- Automatic application requires explicit queue authorization in addition to mode, category policy, confidence, contradiction policy, and deterministic gates.
- Consolidated sources and canonicals cannot be edited or hard-deleted through ordinary admin/agent mutation endpoints in ways that destroy reversible lineage. Reversal is the required lifecycle operation.
- Settings and request payloads now enforce ranges, enums, category allowlists, same-category selection, and cluster-size consistency.
- Failed admin queue submission marks the hygiene run failed instead of leaving a permanently running audit row. Scheduled discovery failures propagate to queue retry/dead-letter handling after safe maintenance completes.

### Product and UI fixes

- The manual workflow shows source metrics before incurring an LLM call, supports proposal regeneration, editable canonical metadata, and navigation from a retired source to its canonical successor.
- Category-specific automation policies, canonical strategy, and embedding version are visible in settings.
- Zero is now a valid UI value for configurable 0–1 thresholds.
- Active canonical events can be reversed from the lineage panel; failed proposals cannot advance to apply.

### Added regression coverage

The focused suite now has 62 passing tests, adding explicit checks for settings validation, nested-metric normalization, audit serialization, warning-enabled synthesis policy, and conservative contradiction blocking. The optimized frontend production build also compiles successfully after these changes.
