# Knowledge Hygiene and Consolidation Implementation Plan

**Status:** Approved implementation specification
**Date:** 2026-07-11
**Audience:** Junior implementation agent, reviewer, and production operator
**Reference implementation:** MasterAgent Python backend
**Supersedes:** the earlier pairwise-to-clustering plan wherever requirements conflict.
**Execution mandate:** implement every work package in this document in one continuous coding session. The PR labels are review-sized checkpoints, not stopping points or future handoffs.

---

## 1. Product objective

Knowledge hygiene is a consolidation system, not a duplicate-removal job. It must identify groups of related knowledge, assess whether they can coherently become a stronger canonical record, produce an auditable LLM proposal, and apply an approved result transactionally.

The system supports:

- exact duplicates;
- near duplicates;
- overlapping records;
- complementary records;
- related records that can become one more complete canonical record.

Embedding similarity is used only to discover and group automated candidates. It never independently decides that records merge. The semantic decision comes from category-aware LLM assessment plus deterministic safety checks and review policy.

```text
Configured similarity threshold
  -> candidate edges and candidate groups
  -> cohesion, weak-link, category, and size safeguards
  -> category-aware LLM consolidation proposal
  -> review or automation policy
  -> one transactional canonicalization and lineage event
```

The legacy names `dedup`, `find_similar_existing`, and `dedup_similarity_threshold` may remain temporarily for API/configuration compatibility. New code, routes, logs, settings, and UI should use **knowledge hygiene**, **candidate discovery**, **consolidation proposal**, and **consolidation apply**.

## 2. Scope and compatibility constraints

### 2.1 Supported categories

The supported allowlist is exactly:

```python
CONSOLIDATABLE_KNOWLEDGE_CATEGORIES = {
    "best_practices",
    "lessons_learned",
    "trade_knowledge",
    "skill",
    "playbook",
}
```

The database uses singular `skill` and `playbook`; user-facing text may use “skills” and “playbooks.” Automated discovery partitions records by category. Cross-category consolidation is not supported in this release, including manual consolidation, and must return a clear validation error.

### 2.2 Non-negotiable compatibility rules

1. All schema changes are additive and idempotent in `backend/memory_db.py`.
2. Source records are never hard-deleted by consolidation.
3. Normal agent retrieval and prior-context injection return active records only. Administrators can view retired records and their canonical successor.
4. Existing skill/playbook storage remains valid: their `content` is SKILL.md and structured operational fields remain in metadata. The new code must support both current records and the expanded operational fields defined in this plan.
5. The existing generation, admin, Hermes, telemetry, import, and playbook paths must continue working when hygiene flags are disabled.
6. No LLM request may mutate knowledge. Preview and apply are distinct operations.
7. Manual, scheduled, admin-triggered, and creation-time workflows use one proposal service and one transactional apply service. There must be no second merge implementation.

## 3. Verified current-state gaps

The current code has creation-time nearest-neighbor behavior in `memory_knowledge.py`, `memory_telemetry.py`, `memory_playbooks.py`, `memory_hermes.py`, and admin/import paths. It selects one same-category match by vector similarity and calls `refine_or_increment_merge`.

Scheduled consolidation in `memory_consolidation.py` self-joins active records, processes at most 50 high-similarity pairs, increments one record, and retires the other. It does not perform a content merge for declarative knowledge, has no successor pointer, and can operate on stale pairs after earlier loop iterations retire rows.

The existing `knowledge_creation_dedup_threshold` setting is not the active threshold in all current paths; current code generally reads `dedup_similarity_threshold`. Preserve this legacy field while introducing the explicit hygiene settings below. Do not silently repurpose a production setting without migration/release notes.

## 4. Shared domain model and service boundary

Create `backend/memory_consolidation_service.py` as the single orchestration service. Put database operations in `backend/memory_consolidation_repository.py`, similarity primitives in `backend/memory_similarity.py`, clustering in `backend/memory_clustering.py`, embedding serialization in `backend/memory_embedding.py`, and category prompts/validation in `backend/memory_consolidation_prompts.py`. All callers use this boundary.

```python
proposal = await consolidation_service.preview(
    knowledge_ids=source_ids,
    options=ConsolidationOptions(...),
    origin="manual" | "scheduled" | "admin" | "creation_time",
    actor=actor_context,
)

result = await consolidation_service.apply(
    preview_id=proposal.id,
    approved_canonical=edited_canonical,
    canonical_strategy="update_existing" | "create_new",
    canonical_target_id="selected-source-id-or-null",
    actor=actor_context,
)
```

### 4.1 Preview contract

`preview` must:

1. Require at least two distinct IDs.
2. Load source records and validate category allowlist, one-category membership, statuses, and embedding policy.
3. For automated origin, enforce candidate/cohesion/size controls. For manual origin, compute similarity only as information; never reject solely for low similarity.
4. Snapshot every source ID, `version`, and `updated_at`.
5. Calculate pairwise minimum/average/maximum, centroid similarity, weak links, category compatibility, embedding-version compatibility, and cluster size.
6. Supply complete source records—not embeddings—to the LLM.
7. Persist an immutable preview record, source snapshot, metrics, LLM response, settings snapshot, model, prompt version, origin, and expiration.
8. Return no knowledge mutation.

### 4.2 Apply contract

`apply` must:

1. Load an unexpired preview and validate its state.
2. Acquire the consolidation lock, lock all source rows, and re-read them.
3. Reject a stale preview if any source is missing, inactive/retired, already merged, or has a changed `version` or `updated_at`.
4. Validate user-edited canonical output against the category schema before any mutation.
5. Create or update the canonical record, generate its embedding, write all lineage/audit rows, retire sources, and commit atomically.
6. Mark the preview applied only inside that transaction.
7. Safely reject a second application of the same preview. It must not create a second canonical record.

If LLM validation, embedding generation, row validation, or any database operation fails, roll back the entire operation. No source may be retired unless a valid canonical record and audit event exist in the same committed transaction.

## 5. Category-aware LLM assessment and rewrite

### 5.1 Complete LLM input

The service passes every source record’s available fields:

- ID, category, name, summary, content, signals, tags, metadata, governed facets;
- quality score, evidence breadth, source intelligence IDs, source AI interaction IDs, source pathway;
- created/updated timestamps, merge count, version, and current status;
- SKILL.md content and parsed operational fields for skills/playbooks.

Embeddings must not be passed as knowledge content. Similarity metrics may be supplied only as non-authoritative context, clearly labeled as retrieval/grouping evidence.

### 5.2 Required structured proposal output

Use JSON-schema validation or strict Pydantic models. The LLM result must contain:

```json
{
  "recommendation": "merge | merge_with_warnings | keep_separate | split_cluster | manual_review",
  "confidence": 0.0,
  "rationale": "...",
  "canonical": {
    "name": "...",
    "summary": "...",
    "content": "...",
    "signals": [],
    "tags": [],
    "metadata": {}
  },
  "preserved_information": [],
  "removed_repetition": [],
  "unreconciled_information": [],
  "contradictions": [],
  "warnings": [],
  "source_traceability": [
    {"source_id": "...", "retained_items": [], "omitted_as_repetition": []}
  ],
  "split_recommendations": []
}
```

The proposal must never invent claims, silently discard qualifications, or turn distinct incidents into one fabricated event. LLM confidence is not an automatic-apply decision by itself.

### 5.3 Prompt families and validation

Use a shared base prompt plus category-specific instructions. Version prompts and store the exact version in every preview.

| Category | Required preservation and validation |
|---|---|
| `best_practices` | Preserve recommendations, conditions, exceptions, scope, and the distinction between guidance that applies universally versus conditionally. |
| `lessons_learned` | Preserve causal context, evidence, incident distinctions, outcomes, and qualifications. Never fabricate a single incident from separate events. |
| `trade_knowledge` | Preserve jurisdiction, product, material, environment, domain, and governed contextual distinctions. Surface incompatible contexts as warnings/contradictions. |
| `skill` | Preserve purpose, inputs, outputs, tools, prerequisites, permissions, side effects, execution behavior, failure conditions, safety requirements, and applicable agents/environments. Parse and re-render SKILL.md where applicable. |
| `playbook` | Preserve triggers, prerequisites, ordered steps, branches, decisions, escalations, rollback, roles, tools/integrations, completion criteria, and exit conditions. Result must remain executable. |

For skills and playbooks, validate both the JSON canonical model and its rendered SKILL.md. A proposal that cannot render and parse successfully is invalid and cannot be applied.

## 6. Candidate discovery and clustering

### 6.1 Candidate discovery

The UI-configured similarity threshold ranges from 0 to 1 and is passed explicitly to each analysis/proposal run. It controls graph edges and candidate grouping only. It is not a merge threshold.

Automated candidate records must be:

- active;
- in the five-category allowlist;
- same category within one candidate graph;
- embedding-version compatible according to configured policy;
- not protected/excluded by metadata or policy;
- not already retired or merged.

Use shared similarity utilities in a new `backend/memory_similarity.py`:

- cosine similarity;
- pairwise min/mean/max;
- L2-normalized centroid and member-to-centroid similarities;
- threshold-edge generation;
- weak-link detection;
- deterministic ordering and component labels.

### 6.2 Cluster safeguards

Use threshold edges plus deterministic connected components as candidate proposals, then validate/split components before LLM preview:

- minimum cluster size;
- configurable maximum cluster size, default 5;
- minimum cohesion;
- weak-link detection;
- minimum pairwise checks where configured;
- centroid similarity;
- category and governed-facet compatibility;
- deterministic component splitting.

Large or weakly connected components must be split into cohesive subgroups or submitted as `manual_review`; they must not become one giant canonical record. Candidate splitting is permitted to use pairwise metrics because it is a grouping safeguard, not a merge decision.

### 6.3 Operational modes

| Mode | Discovery | LLM preview | Apply |
|---|---|---|---|
| `analysis_only` | Yes | No | Never |
| `proposal_only` | Yes | Yes | Never |
| `manual_only` | Yes/manual selection | Yes | Human confirmation required |
| `auto_conservative` | Yes | Yes | Only when all conservative policy gates pass |
| `auto_synthesis` | Yes | Yes | Broader policy-controlled automated application |

First production rollout must be `proposal_only` or `manual_only`.

## 7. Schema and audit design

All DDL follows the repository’s idempotent ALTER-after-CREATE style.

### 7.1 Additive knowledge columns

- `merged_into TEXT NULL`
- `merged_from TEXT[] NOT NULL DEFAULT '{}'`
- `consolidation_event_id TEXT NULL`
- `consolidation_protected BOOLEAN NOT NULL DEFAULT FALSE`

Do not overwrite original source content or metadata. A retired source keeps all original fields and points to its canonical successor.

### 7.2 New tables

Use UUID/text IDs consistently with existing tables.

1. `knowledge_hygiene_runs`: run metadata, explicit settings snapshot, category filters, mode, counts, status, timestamps, actor/origin.
2. `knowledge_hygiene_clusters`: run ID, category, member count, metrics, threshold, cohesion/splitting decision, candidate status.
3. `knowledge_hygiene_cluster_members`: run/cluster/source IDs, role, metrics, ejection/split reason.
4. `knowledge_consolidation_previews`: preview ID, expiration, origin, actor, category, source snapshot, metrics, settings/model/prompt snapshot, raw/validated proposal, state.
5. `knowledge_consolidation_preview_sources`: preview ID, source ID, source version, source updated timestamp, source status snapshot.
6. `knowledge_consolidation_events`: applied event, preview ID, canonical ID, strategy, actor, origin, thresholds/settings, model/prompt, proposed output, approved output, user edits, warnings/contradictions, applied timestamp, reversible state.
7. `knowledge_consolidation_event_sources`: event ID, source ID, original serialized snapshot, merged_into ID, source traceability, retention/removal notes.

Persist the latest centroid map in `knowledge_hygiene_clusters` for automated and creation-time candidate lookup. It must remain rebuildable and must not replace run/audit history.

## 8. Manual knowledge-table workflow

Implement this before automatic application.

1. The knowledge table supports multi-select of two or more rows.
2. Bulk actions show **Merge / Consolidate**.
3. The backend rejects mixed categories with an explicit explanation. Low similarity is displayed but does not block manual selection.
4. A review screen shows records, statuses, similarity metrics, compatibility checks, source details, and the LLM recommendation.
5. User clicks Generate Proposal; this calls preview only.
6. User can inspect retained information, removed repetition, warnings, contradictions, and source-to-output traceability.
7. User may edit canonical fields and regenerate a preview.
8. User chooses either:
   - update one selected active record; or
   - create a new canonical record and retire all selected sources.
9. User confirms apply. The UI handles stale-preview rejection by offering regeneration, never by applying outdated content.
10. After success, the UI displays canonical lineage and provides admin navigation from each retired source to its successor.

The API should expose separate endpoints equivalent to:

```text
POST /api/memory/admin/knowledge/consolidations/preview
GET  /api/memory/admin/knowledge/consolidations/previews/{preview_id}
POST /api/memory/admin/knowledge/consolidations/previews/{preview_id}/regenerate
POST /api/memory/admin/knowledge/consolidations/apply
GET  /api/memory/admin/knowledge/consolidations/events/{event_id}
```

Use the repository’s existing admin authorization dependency. Agent-facing endpoints must not receive apply authority by default.

## 9. Canonical strategies and transactional application

### 9.1 Update existing

One user-selected source remains active and receives the approved canonical content. Record its pre-merge state in the consolidation event. Retire all other sources.

### 9.2 Create new

Insert a new canonical knowledge record, then retire every selected source. The new record includes full source lineage and the aggregation of evidence/provenance permitted by category policy.

### 9.3 Transaction algorithm

1. Acquire a global/advisory hygiene lock suitable for the PostgreSQL deployment.
2. Start transaction and lock every source row with `FOR UPDATE` in deterministic ID order.
3. Validate preview expiration, snapshot versions/timestamps/statuses, category, target strategy, and no prior merge.
4. Validate approved canonical output and category-specific structure.
5. Generate canonical embedding before retiring any sources. If it fails, abort.
6. Create/update canonical, preserving evidence IDs, provenance, signals, tags, facets, metadata, and required structured fields.
7. Insert event/audit rows and original-source snapshots.
8. Mark absorbed sources `retired`, set `merged_into`, and set the event ID.
9. Update canonical `merged_from`, version, metadata lineage, and timestamp.
10. Mark preview applied and commit.

Implement administrator-only reversal in the same delivery. It restores source statuses and an updated canonical record's pre-merge snapshot, or retires a newly created canonical, only after verifying that none of the affected records participated in a later consolidation. Reversal creates a new audit event; it never deletes the original event.

## 10. Settings and policies

Add settings with safe defaults and surface them in the existing admin settings UI:

- `knowledge_hygiene_enabled_categories` — five-category allowlist by default;
- `knowledge_hygiene_similarity_threshold` — 0..1 candidate edge threshold;
- `knowledge_hygiene_min_cluster_size`;
- `knowledge_hygiene_max_cluster_size` — default 5;
- `knowledge_hygiene_min_cluster_cohesion`;
- `knowledge_hygiene_embedding_version`;
- `knowledge_hygiene_mode`;
- `knowledge_hygiene_preview_ttl_minutes`;
- `knowledge_hygiene_llm_provider`, model, and prompt-version selector;
- `knowledge_hygiene_min_confidence_for_auto_apply`;
- `knowledge_hygiene_contradiction_policy`;
- `knowledge_hygiene_default_canonical_strategy`;
- category-specific automation policies.

Validate all numeric settings. Do not hardcode universal thresholds: calibrate on production dry-run data for the active embedding model and serialization version.

## 11. Single-session implementation sequence

Complete PR 1 through PR 6 below without stopping for review or requesting design decisions. Commit boundaries may follow the PR labels, but the implementation is not complete until every package, test, UI workflow, migration, and activation control passes the final definition of done in §18.

### PR 1 — Shared embedding and similarity foundation

Files: `services/embeddings.py`, new `memory_embedding.py`, new `memory_similarity.py`, all knowledge creation/update paths, `memory_db.py`, tests.

- Add one deterministic embedding serialization path for all five categories.
- Record embedding version, model, dimensions, and timestamp.
- Cover knowledge generation, telemetry, playbooks, skills, Hermes, admin CRUD/import, promotion, and consolidation updates.
- Add resumable/idempotent embedding backfill; it must not mutate content or status.
- Add pairwise, min/mean/max, centroid, and edge utilities.
- Do not merge or call a consolidation LLM.

### PR 2 — Preview, lineage, and audit schema

Files: `memory_db.py`, new repository/service models, tests.

- Add source/canonical lineage columns and all run, cluster, preview, and event tables.
- Store preview expiration and source version snapshots.
- Store actor, origin, model, prompt version, settings, threshold, raw proposal, validated proposal, approved output, and user edits.
- Keep DDL additive and idempotent.

### PR 3 — Candidate clustering and LLM proposal generation

Files: new `memory_clustering.py`, `memory_consolidation_service.py`, prompt/config helpers, admin trigger, tests.

- Support all five categories, partitioned by category.
- Accept the UI-configured similarity threshold.
- Build components, calculate safeguards, split weak/oversized groups, and create analysis reports.
- Implement category-aware structured LLM proposals.
- Implement `analysis_only` and `proposal_only` only. No knowledge mutation.

### PR 4 — Manual knowledge-table consolidation

Files: `memory/admin.py`, new/updated admin schemas/routes, `frontend/src` knowledge table/inspector components, service tests and frontend tests.

- Multi-selection and bulk action.
- Preview, review, edit, regenerate, target selection, stale-preview handling, transactional apply, lineage display.
- Manual same-category selections are permitted below the automated threshold.
- Use the shared service only.

### PR 5 — Controlled automated application

Files: scheduled consolidation and settings/UI wiring, shared service tests.

- Add `manual_only`, `auto_conservative`, and `auto_synthesis` policy execution.
- Use the same preview/apply service as manual UI.
- Add category-specific policy gates.
- Release as proposal-only/manual-only first; do not create a separate scheduler merge path.

### PR 6 — Creation-time consolidation

Files: all creation paths and shared service.

- Enable only after manual/scheduled behavior is production-proven.
- Use conservative discovery and the same preview/apply flow.
- Never merge into draft, retired, protected, or otherwise ineligible records.

## 12. Required tests and acceptance criteria

### 12.1 Cross-cutting tests

- exact, near-duplicate, overlapping, and complementary consolidation;
- LLM `keep_separate`, `split_cluster`, `manual_review`, and warning recommendations;
- contradictions and unresolved information;
- weak semantic chain requiring a split;
- oversized component handling;
- deterministic grouping despite shuffled input;
- category partitioning and mixed-category manual rejection;
- manual low-similarity selection allowed with warning;
- editable and regenerated proposal;
- preview expiration, source change, source retirement, and stale-preview rejection;
- update-existing and create-new canonical strategies;
- complete source/canonical/event lineage;
- evidence, provenance, signals, tags, and facets preserved;
- rollback for embedding, validation, and database failures;
- repeat apply safely rejected or idempotent;
- retired records excluded from agent retrieval and prior-context generation;
- administrators can access retired records and successor links;
- all callers demonstrably use the shared preview/apply service.

### 12.2 Category acceptance tests

| Category | Must prove |
|---|---|
| Best practices | Related guidance can strengthen one practice while conditions and exceptions remain intact. |
| Lessons learned | Causal details remain intact and separate incidents are never fabricated into one event. |
| Trade knowledge | Jurisdictions/materials/products/environments remain explicit and conflicts are surfaced. |
| Skills | Inputs, outputs, tools, prerequisites, permissions, side effects, failures, safety, and applicability survive; complementary skills only merge into a coherent operational contract. |
| Playbooks | Triggers, steps, branches, escalation, rollback, roles, tools, and completion criteria survive; output remains parseable and executable. |

## 13. Rollout and operational acceptance

1. Complete and verify all six work packages before deployment.
2. Deploy the completed build once. Startup creates the additive schema and safe default settings.
3. The production system starts in `manual_only`; inspect embedding coverage and run the resumable backfill from the UI.
4. Use **Analyze now** to inspect threshold distributions, cohesion, component sizes, and category samples without mutation.
5. Review generated proposals, especially skills and playbooks, then perform the first applications through the manual Knowledge-table workflow.
6. Measure proposal acceptance, fact-loss reports, contradiction rates, stale-preview rates, and retrieval quality.
7. Every mode and creation-time consolidation ships in this build. `auto_conservative`, `auto_synthesis`, and creation-time apply remain disabled until an administrator enables them in the UI; enabling them requires no later code change or deployment.

Production success is not “fewer rows.” It is: fewer redundant retrieval results, stronger canonical knowledge, preserved operational correctness, complete lineage, reversible audit evidence, and no unapproved content loss.

## 14. Fixed implementation decisions

This section removes choices that would otherwise require a follow-up.

### 14.1 Runtime and dependencies

- Use the existing FastAPI, psycopg, Redis/BullMQ-compatible queue, React, and admin authentication patterns.
- Do not add sklearn, scipy, HDBSCAN, FAISS, or a second queue.
- Use plain standard-library Python vector math. Do not add or depend on `numpy` for hygiene.
- Use the configured OpenAI-compatible LLM through `memory_services.call_llm` with task type `knowledge_consolidation`.
- Seed a `knowledge_consolidation` LLM config by copying the provider/model defaults used by `knowledge_generation`; do not copy credentials into new storage.
- Use `services.llm.parse_llm_json` followed by Pydantic validation. One repair retry is allowed for invalid JSON/schema; after that the preview is `failed` with the validation error.

### 14.2 Production-safe defaults

Add these exact `memory_settings` defaults and matching fields to both `MemorySettingsUpdate` and `MemorySettingsResponse` in `backend/memory_models.py`:

| Setting | Type | Default |
|---|---|---|
| `knowledge_hygiene_enabled` | boolean | `true` |
| `knowledge_hygiene_enabled_categories` | JSONB string array | all five canonical database category names |
| `knowledge_hygiene_similarity_threshold` | float 0..1 | `0.82` |
| `knowledge_hygiene_min_cluster_size` | integer >=2 | `2` |
| `knowledge_hygiene_max_cluster_size` | integer 2..20 | `5` |
| `knowledge_hygiene_min_cluster_cohesion` | float 0..1 | `0.72` |
| `knowledge_hygiene_weak_link_threshold` | float 0..1 | `0.65` |
| `knowledge_hygiene_embedding_version` | integer | `2` |
| `knowledge_hygiene_mode` | enum | `manual_only` |
| `knowledge_hygiene_preview_ttl_minutes` | integer 5..1440 | `60` |
| `knowledge_hygiene_min_auto_confidence` | float 0..1 | `0.90` |
| `knowledge_hygiene_contradiction_policy` | enum | `manual_review` |
| `knowledge_hygiene_default_canonical_strategy` | enum | `update_existing` |
| `knowledge_hygiene_creation_time_enabled` | boolean | `false` |
| `knowledge_hygiene_category_policies` | JSONB object | every category=`manual_only` |

Keep `dedup_similarity_threshold` readable for backward compatibility, but stop using it in new hygiene code. The settings UI labels the new threshold **Candidate similarity** and explains that it finds related records but does not decide merges.

### 14.3 Exact component splitting algorithm

For each category, sort records by ID, calculate all pairwise similarities, create edges at or above the configured candidate threshold, and find deterministic connected components with union-find.

For every component, calculate average all-pairs similarity as cohesion. A component is accepted for proposal only when its size is at most the configured maximum, cohesion is at least the configured minimum, and no member-to-centroid similarity is below the weak-link threshold.

If invalid, repeatedly remove the lowest-similarity graph edge, breaking ties by sorted endpoint IDs, and recompute connected components. Continue until every resulting component passes or becomes a singleton. A fully connected component still larger than the maximum is divided deterministically: choose the lowest-ID member as the first seed, repeatedly add the remaining member with the highest average similarity to the current subgroup until full, then start the next subgroup. Mark these size-forced groups `manual_review`; do not auto-apply them.

Singletons are analysis results only and never invoke the LLM. Manual selection bypasses the automated edge threshold and splitting rules but still reports all metrics and requires a single category.

### 14.4 Canonical field aggregation

The LLM proposes content; deterministic code preserves system fields:

- union and de-duplicate `source_intelligence_ids`, `source_ai_interaction_ids`, `signals`, `tags`, and `merged_from` while preserving first-seen order;
- merge governed facets only when values agree; conflicting values go to `metadata.consolidation_conflicts` and force manual review;
- store `metadata.consolidation` with event ID, source IDs, proposal ID, model, prompt version, and origin;
- set canonical `merge_count` to the sum of source merge counts plus the number of absorbed records;
- set `evidence_breadth` to at least the count of distinct evidence references;
- retain the canonical target's visibility and active status for update-existing; create-new defaults to shared/active;
- increment version exactly once on apply;
- never let LLM output set IDs, status, visibility, lineage, audit fields, quality counters, or timestamps.

## 15. Exact persistence contract

Implement the following schema using `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Types are fixed as follows: every ID, identifier reference, enum, origin, actor, model, prompt version, status, role, reason, and error field is `TEXT`; identifier/category collections are `TEXT[]`; settings, snapshots, metrics, options, proposals, warnings, contradictions, traceability, validation errors, and edits are `JSONB`; counters are `INT`; similarities/confidence are `FLOAT`; timestamps are `TIMESTAMPTZ`; flags are `BOOLEAN`; centroids use the existing unbounded `vector` type. Primary IDs use `TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text`.

### 15.1 Knowledge columns

```sql
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS merged_into TEXT;
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS merged_from TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS consolidation_event_id TEXT;
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS consolidation_protected BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_knowledge_merged_into ON knowledge(merged_into);
CREATE INDEX IF NOT EXISTS idx_knowledge_consolidation_event ON knowledge(consolidation_event_id);
```

### 15.2 Required table columns

- `knowledge_hygiene_runs`: `id`, `origin`, `mode`, `status`, `settings_snapshot`, `embedding_version`, `categories`, `records_scanned`, `clusters_found`, `proposals_created`, `applied_count`, `failed_count`, `error`, `started_at`, `finished_at`, `created_by`.
- `knowledge_hygiene_clusters`: `id`, `run_id`, `category`, `member_ids`, `centroid`, `min_similarity`, `avg_similarity`, `max_similarity`, `cohesion`, `weak_links`, `split_reason`, `proposal_id`, `status`, `created_at`, `updated_at`.
- `knowledge_hygiene_cluster_members`: composite key `(cluster_id, knowledge_id)`, plus `run_id`, `similarity_to_centroid`, `min_member_similarity`, `role`, `decision_reason`.
- `knowledge_consolidation_previews`: `id`, `origin`, `actor_type`, `actor_id`, `category`, `state`, `source_ids`, `source_snapshot`, `metrics`, `options`, `settings_snapshot`, `model_provider`, `model_name`, `prompt_version`, `raw_response`, `proposal`, `validation_errors`, `expires_at`, `created_at`, `updated_at`, `applied_event_id`.
- `knowledge_consolidation_preview_sources`: composite key `(preview_id, knowledge_id)`, plus `source_version`, `source_updated_at`, `source_status`, `source_snapshot`.
- `knowledge_consolidation_events`: `id`, `preview_id`, `action`, `origin`, `actor_type`, `actor_id`, `category`, `canonical_id`, `canonical_strategy`, `model_provider`, `model_name`, `prompt_version`, `similarity_threshold`, `settings_snapshot`, `proposed_output`, `approved_output`, `user_edits`, `warnings`, `contradictions`, `reversed_event_id`, `created_at`.
- `knowledge_consolidation_event_sources`: composite key `(event_id, knowledge_id)`, plus `role`, `original_snapshot`, `source_traceability`, `merged_into`, `created_at`.

Use these foreign keys only: cluster rows reference their hygiene run with `ON DELETE CASCADE`; cluster-member rows reference their cluster with `ON DELETE CASCADE`; preview-source rows reference their preview with `ON DELETE CASCADE`; event-source rows reference their event with `ON DELETE CASCADE`. Do not add foreign keys from audit/lineage tables to `knowledge`, and do not add a foreign key on `knowledge.merged_into`, because recovery must survive later manual deletion. Add indexes for preview state/expiry, event canonical ID, cluster run/category, and source knowledge IDs.

Store vectors using the existing `vector` type without pinning dimensions. Store embedding model, dimensions, version, and timestamp in `knowledge.metadata.embedding` so configured embedding providers remain compatible.

## 16. Exact API and UI contract

### 16.1 Admin endpoints

Add these routes under the existing authenticated admin router:

| Method and path | Behavior |
|---|---|
| `POST /api/memory/admin/knowledge/consolidations/analyze` | Create the run row, queue `knowledge_hygiene_run`, and return HTTP 202 with run ID. |
| `GET /api/memory/admin/knowledge/hygiene-runs/{run_id}` | Return run, clusters, members, and proposal links. |
| `POST /api/memory/admin/knowledge/consolidations/preview` | Synchronously create a non-mutating preview for 2+ same-category IDs and return HTTP 200. |
| `GET /api/memory/admin/knowledge/consolidations/previews/{preview_id}` | Return preview, source snapshots, metrics, and proposal. |
| `POST /api/memory/admin/knowledge/consolidations/previews/{preview_id}/regenerate` | Expire the old preview, synchronously create a new preview from current source versions, and return HTTP 200 with the new preview. |
| `POST /api/memory/admin/knowledge/consolidations/apply` | Apply edited/approved canonical data transactionally. |
| `GET /api/memory/admin/knowledge/consolidations/events/{event_id}` | Return full lineage/audit detail. |
| `POST /api/memory/admin/knowledge/consolidations/events/{event_id}/reverse` | Reverse when dependency validation permits. |

Preview request:

```json
{
  "knowledge_ids": ["id-1", "id-2"],
  "origin": "manual",
  "options": {"canonical_strategy": "update_existing", "canonical_target_id": "id-1"}
}
```

Apply request:

```json
{
  "preview_id": "preview-id",
  "canonical_strategy": "update_existing",
  "canonical_target_id": "id-1",
  "approved_canonical": {"name": "...", "summary": "...", "content": "...", "signals": [], "tags": [], "metadata": {}}
}
```

Use status codes consistently: 400 invalid category/options, 404 missing preview/source, 409 stale/already-applied/dependency conflict, 410 expired preview, 422 invalid LLM or edited canonical structure, and 500 only for unexpected failures.

### 16.2 Frontend files and behavior

- Add API methods in `frontend/src/lib/api.js` for every endpoint above.
- Add `onConsolidate` beside bulk delete in `frontend/src/components/memory/KnowledgeTab.jsx`; enable it only for two or more selected records. Show a same-category validation message before calling the API.
- Manage dialog state and reloads in `frontend/src/pages/MemoryExplorerPage.jsx`.
- Create `frontend/src/components/memory/KnowledgeConsolidationDialog.jsx` with steps: Sources → Generate/Review Proposal → Edit Canonical → Confirm → Result.
- Create `frontend/src/components/memory/KnowledgeLineagePanel.jsx` and render it from `KnowledgeInspector.jsx` for canonical and retired records.
- Add hygiene mode, categories, threshold, cluster size/cohesion, TTL, confidence, contradiction policy, category automation policies, backfill progress, and **Analyze now** controls to the existing Knowledge settings tab.
- Do not restore the removed legacy one-click Consolidate button. “Analyze now” obeys the selected mode; manual application remains in the Knowledge table.
- Retired rows remain visible only in the admin Knowledge table when its status filter is retired/all. Agent endpoints, semantic/full-text search, get-context, and prior-context remain active-only.

The consolidation dialog must show min/average/max similarity, each member's centroid similarity, embedding compatibility, statuses, LLM recommendation, confidence, rationale, retained information, repetition removed, warnings, contradictions, unreconciled information, and per-source traceability. Edits must be visually identified in the confirmation step.

## 17. Queue, scheduler, migration, and activation

### 17.1 Replace legacy consolidation

- Replace `memory_consolidation.run_consolidation` internals with candidate analysis and shared-service preview/apply policy execution. Do not retain the pairwise retirement loop.
- Keep the `run_consolidation` queue job name and `/trigger/run-consolidation` route as backward-compatible aliases, but make them start a hygiene run using the configured mode.
- Update `memory/queue.py` to handle `knowledge_hygiene_run` and `knowledge_embedding_backfill`; the legacy job delegates to `knowledge_hygiene_run`.
- Update `memory_tasks.py` so the periodic schedule queues hygiene only when `knowledge_hygiene_enabled=true`. In `manual_only` or `proposal_only`, it never applies a proposal.
- Creation-time paths call the shared candidate/preview service only when `knowledge_hygiene_creation_time_enabled=true`. Default false means existing insert behavior remains available while production is calibrated.

Creation-time consolidation is asynchronous: insert the new knowledge record normally, discover same-category candidates, and enqueue a preview containing the new record and candidates. The queue worker calls the shared preview, policy, and apply methods. Generation requests must never wait for a consolidation LLM call. In `manual_only` this creates a reviewable proposal; in automatic modes it applies only when the common policy permits it.

### 17.2 Embedding backfill

Implement a resumable queue job with batches of 50 and per-record error capture. It selects active records whose `metadata.embedding.version` differs from the configured version, serializes all category-specific fields, generates embeddings in provider-supported batches, and updates only embedding metadata/vector after a version check. It records processed/succeeded/failed counts in a hygiene run.

The settings UI shows current-version coverage and exposes **Backfill embeddings**. Candidate automation excludes incompatible versions; manual preview allows them with a warning and calculates available metrics only. Backfill failure does not block manual consolidation because the LLM uses source content, but it blocks automatic application for the affected cluster.

### 17.3 One-deployment activation

Database initialization creates all schema automatically on backend startup. No separate SQL migration command is required. On first startup:

1. Seed missing settings and `knowledge_consolidation` task configuration.
2. Start in `manual_only`; no automatic source retirement occurs.
3. Display embedding coverage in settings and allow the backfill to run from the UI.
4. Allow manual same-category consolidation immediately, even before backfill.
5. Allow `analysis_only`/`proposal_only` scheduled runs as soon as compatible embeddings exist.
6. Expose all modes in settings so production can enable them without another code deployment.

The coding agent must not claim production activation if it lacks VPS/deployment access. It must still leave a single deployable build in which startup migration and UI controls complete activation without additional coding.

## 18. Unattended definition of done

The coding agent may stop only when all items below are true.

### 18.1 Code completion

- All six work packages are implemented; none are left as TODOs, stubs, future PRs, or pseudo-code.
- All five categories work through the same preview/apply service.
- Manual preview, edit, regenerate, both canonical strategies, apply, lineage display, and reversal work end to end.
- Scheduled, admin-triggered, automatic-policy, and creation-time code paths call the same service.
- Legacy pairwise destructive consolidation is removed; backward-compatible route/job names delegate to hygiene.
- Retired records are absent from all agent retrieval, external search, get-context, and prior-context paths.

### 18.2 Verification commands

Run from the repository root using PowerShell syntax:

```powershell
$python = "C:\Users\drmoy\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python -m compileall backend
Set-Location backend\tests
& $python -m pytest . -v --timeout=30
Set-Location ..\..\frontend
npm.cmd test -- --watchAll=false
$env:CI="true"
npm.cmd run build
Set-Location ..
docker compose config --quiet
git -c core.whitespace=cr-at-eol diff --check
```

If the integration suite requires a running database/server that is unavailable, the agent must still run every pure/unit test, document only that environmental limitation, and must not treat unrun integration tests as passed.

### 18.3 Required automated coverage

In addition to §12, tests must assert exact API error codes, preview immutability, prompt/schema validation retry, source-version race handling, transaction rollback, queue delegation, scheduler mode behavior, settings validation, embedding-backfill resume, frontend bulk-action enablement, multi-step dialog editing, and lineage/reversal dependency protection.

Use a fake LLM provider with fixed category fixtures and a fake embedding provider; tests must not call paid/external APIs. Include golden fixtures for each category and for every recommendation enum.

### 18.4 Handoff

The final handoff must list changed files, schema additions, default settings, test results, any tests not runnable due to environment, and the exact production deployment command already used by this repository. It must clearly distinguish “implemented and deployable” from “deployed to VPS.” No additional design question is permitted unless the repository contradicts this specification in a way that would cause data loss.
