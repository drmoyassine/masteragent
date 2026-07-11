# Knowledge Settings and Pipeline Refactor — Implementation Plan

**Status:** Implemented in workspace; production activation pending deployment checklist
**Delivery report:** `knowledge-settings-and-pipeline-refactor-delivery-report.md`
**Decision source:** `knowledge-settings-ui-refactor-decisions.md` (KD-001 through KD-018)
**Baseline:** `main` after Knowledge Hygiene hardening commit `3caaae2`
**Scope:** Backend generation, source-novelty routing, embeddings, facets, quality, retrieval, settings migration, and Knowledge settings UI

## 1. Objective

Deliver one coherent Knowledge lifecycle and one understandable administration surface:

```text
Persist source evidence and embeddings
    → cheap pre-generation evidence-similarity routing
    → full generation, evidence revision, or evidence-only link
    → shared Knowledge hygiene/consolidation when a new record exists
    → Approved or Draft policy
    → index-based agent retrieval, with full always-on Knowledge
```

The implementation must remove all legacy direct dedup/refine paths, preserve production data and APIs through additive migrations, and reorganize the Knowledge settings page into:

1. Knowledge Generation;
2. Knowledge Maintenance;
3. Knowledge Retrieval.

## 2. Non-negotiable product behavior

1. All Knowledge-producing pathways inherit one global schedule, token budget, confidence threshold, evidence threshold, and approval policy. Pathway/entity overrides use `override → global` resolution.
2. Product terminology is **Approved** versus **Draft**. Persisted/API `status='active'` remains the backward-compatible representation of Approved.
3. Embeddings persist for all tiers:
   - Tier 0 interactions/telemetry;
   - Tier 1 memories;
   - Tier 2 intelligence;
   - Tier 3 Knowledge.
4. Before an expensive generation LLM call, compare new source evidence against previously processed evidence of the same type and trace matches to canonical Knowledge through source IDs and Knowledge lineage.
5. Evidence routing defaults:
   - `< 0.78`: normal new-Knowledge generation;
   - `0.78–<0.95`: evidence revision assessment;
   - `>= 0.95`: evidence-only link when all deterministic safeguards pass.
6. Similarity never directly rewrites Knowledge. Moderate revisions are structured, validated, versioned, audited, provenance-linked, and transactional.
7. All post-generation consolidation uses the existing shared hygiene preview/apply/lineage/reversal services. No producer contains private merge behavior.
8. Generated facets are part of the main structured generation result. Normal generation must not make a second facet LLM call.
9. Quality uses the versioned four-component model in §10.
10. Ordinary agent-retrieved Knowledge is always a lean index. Active `always_inject` Knowledge is always injected in full and bypasses ordinary filters/caps.
11. Retired Knowledge never appears in agent retrieval, semantic/full-text endpoints, or prior context.

## 3. Terminology and states

### 3.1 Knowledge status

| Product label | Stored value | Agent-visible | Meaning |
|---|---:|---:|---|
| Draft | `draft` | No | Generated or manually created, awaiting approval |
| Approved | `active` | Yes | Approved manually or by configured policy |
| Retired | `retired` | No | Historical source absorbed by consolidation or explicitly retired |

Do not introduce `approved` as a stored status in this delivery. Accept it only as an optional API input alias if useful, normalize it to `active`, and continue returning `active` on compatibility APIs.

### 3.2 Evidence route

Use these stable route identifiers:

- `new_generation`
- `revision_assessment`
- `evidence_link`
- `manual_review`
- `route_error`

### 3.3 Generation pathways

Use stable pathway IDs separate from Knowledge categories:

- `declarative_knowledge`
- `telemetry_reflection`
- `playbook_extraction`
- `skill_extraction`
- `manual_creation`
- `import`

The stored categories remain the existing codebase allowlist:

- `best_practices`
- `lessons_learned`
- `trade_knowledge`
- `skill`
- `playbook`

## 4. Additive schema changes

All startup DDL must remain idempotent. Do not drop legacy columns in this delivery.

### 4.1 Embedding provenance on all tiers

Add to `interactions`, `memories`, `intelligence`, and `knowledge`:

```sql
embedding_model       TEXT
embedding_version     INTEGER
embedding_dimensions  INTEGER
embedded_at           TIMESTAMPTZ
```

Rules:

- Stamp all four fields whenever an embedding is written.
- Clear all four only if an administrator explicitly invalidates an embedding.
- Stop clearing `interactions.embedding` after memory processing.
- Preserve the existing Knowledge `metadata.embedding` block for compatibility during migration; explicit columns become authoritative.
- Candidate comparison requires model, version, and dimensions to match.

Indexes:

- retain flexible-dimension behavior;
- add partial indexes on records with non-null embeddings and provenance where useful;
- do not create a fixed-dimension vector index until the configured production dimension is verified.

### 4.2 Evidence bundles

Create `knowledge_evidence_bundles`:

```text
id                      text primary key
pathway                 text not null
source_types            text[] not null
source_digest           text not null
entity_type             text
entity_ids              text[]
window_started_at       timestamptz
window_ended_at         timestamptz
aggregate_embedding     vector
embedding_model         text
embedding_version       integer
embedding_dimensions    integer
context_digest          text
outcome_signature       jsonb
status                  text
route                   text
route_metrics           jsonb
matched_bundle_ids      text[]
matched_knowledge_ids   text[]
canonical_knowledge_id  text
generation_run_id       text
error                   jsonb
created_at              timestamptz
updated_at              timestamptz
```

Allowed bundle statuses:

- `pending`
- `analyzed`
- `generated`
- `revised`
- `linked`
- `manual_review`
- `failed`

Create deterministic uniqueness on `(pathway, source_digest)`. Reprocessing the same normalized evidence set must reuse or safely reject the existing bundle.

Create `knowledge_evidence_bundle_members`:

```text
bundle_id              text not null
source_type            text not null
source_id              text not null
source_role            text not null
ordinal                integer
entity_type            text
entity_id              text
source_timestamp       timestamptz
embedding_model        text
embedding_version      integer
embedding_dimensions   integer
created_at             timestamptz
primary key (bundle_id, source_type, source_id, source_role)
```

`source_role` distinguishes primary evidence from contextual telemetry or derived-parent Knowledge. This supports playbook/skill pathways that consume mixed intelligence, telemetry, and Knowledge sources without collapsing their provenance into an ambiguous ID array.

### 4.3 Normalized Knowledge source links

Create `knowledge_source_links`:

```text
knowledge_id          text not null
source_type           text not null
source_id             text not null
bundle_id             text
source_role           text not null
linked_by_event_id    text
created_at            timestamptz
primary key (knowledge_id, source_type, source_id, source_role)
```

This table is authoritative for cross-pathway provenance. Continue dual-writing existing `source_intelligence_ids` and `source_ai_interaction_ids` arrays for API/backward compatibility. Backfill links from existing arrays and playbook/skill metadata idempotently.

### 4.4 Evidence events

Create `knowledge_evidence_events` for immutable audit:

```text
id                    text primary key
bundle_id             text not null
knowledge_id          text
event_type            text not null
actor_type            text
actor_id              text
origin                text
similarity_settings   jsonb
route_metrics         jsonb
source_ids            text[]
previous_snapshot     jsonb
approved_output       jsonb
model_provider        text
model_name            text
prompt_version        text
created_at            timestamptz
```

Event types:

- `generation_started`
- `generation_skipped_evidence_linked`
- `revision_proposed`
- `revision_no_change`
- `revision_applied`
- `new_knowledge_created`
- `route_failed`

### 4.5 Knowledge approval and quality fields

Add to `knowledge`:

```text
approved_at          timestamptz
approved_by_type     text
approved_by_id       text
approval_origin      text
quality_version      integer
quality_components   jsonb
facet_schema_version integer
facet_status         text
facet_provenance     jsonb
generation_state     text
```

Approval origins:

- `manual`
- `generation_policy`
- `consolidation`
- `import`
- `system`

Generation states:

- `pending_hygiene`
- `ready`
- `requires_review`
- `failed`

Newly generated candidates are stored as Draft with `generation_state='pending_hygiene'`. Approval policy is evaluated only after initial post-generation hygiene determines that the candidate can remain separate or an approved consolidation/revision completes.

Backfill existing `active` records with `approval_origin='system'` and a migration timestamp only when approval fields are null. Do not pretend a historical human approver exists.

### 4.6 Facet backfill state

Either create `knowledge_facet_backfill_items` or store sufficient status/provenance on Knowledge. It must distinguish:

- `pending`
- `succeeded`
- `no_facet`
- `failed`

Include schema version, attempts, last error, and timestamps. A `no_facet` record must not be retried until the facet schema version changes or an administrator explicitly requests retry.

## 5. Canonical settings and compatibility migration

### 5.1 New canonical settings

Add:

```text
knowledge_generation_enabled                boolean default true
knowledge_generation_time                   text default '03:00'
knowledge_generation_max_tokens             integer default 1200
knowledge_generation_min_confidence         float default 0.60
knowledge_generation_evidence_threshold     integer default 5
knowledge_generation_approval_policy        text default 'approve_immediately'
knowledge_generation_pathway_overrides      jsonb default '{}'

knowledge_evidence_routing_enabled           boolean default true
knowledge_evidence_routing_mode              text default 'analysis_only'
knowledge_evidence_low_threshold             float default 0.78
knowledge_evidence_high_threshold            float default 0.95
knowledge_evidence_high_coverage             float default 0.90

knowledge_quality_version                    integer default 2
knowledge_facet_schema_version               integer default 1
```

Allowed approval policies:

- `approve_immediately`
- `create_as_draft`

Allowed evidence routing modes:

- `analysis_only`
- `enforced`

### 5.2 Pathway override JSON

Use this shape:

```json
{
  "telemetry_reflection": {
    "enabled": true,
    "schedule_time": null,
    "max_tokens": null,
    "min_confidence": null,
    "evidence_threshold": null,
    "approval_policy": "inherit"
  }
}
```

`null` means inherit. Never copy the global value into override storage.

### 5.3 Effective settings resolver

Implement one pure resolver used by UI responses and all workers:

```python
effective = generation_policy.resolve(
    pathway="telemetry_reflection",
    entity_type=entity_type,
    settings=settings,
    entity_config=entity_config,
)
```

Resolution order:

```text
entity override → pathway override → global setting → code default
```

Return both effective values and their source (`entity`, `pathway`, `global`, `default`) for UI badges.

### 5.4 Legacy setting migration

On first startup with new canonical values unset:

| Canonical setting | Migration source |
|---|---|
| max tokens | `knowledge_max_tokens`, otherwise 1200 |
| min confidence | `extraction_confidence_threshold`, otherwise 0.60 |
| global schedule | `knowledge_generation_time`, otherwise `03:00` |
| evidence threshold | `knowledge_threshold`, otherwise 5 |
| approval policy | `knowledge_auto_activate=true` → approve; false → draft |

Seed pathway overrides only where an old pathway value materially differs from the migrated global value:

- `telemetry_reflection_max_tokens`
- `telemetry_reflection_confidence_min`
- `telemetry_reflection_time`
- `playbook_generation_time`
- entity `skill_auto_activate` / `playbook_auto_activate`

Compatibility rules:

- Keep old fields readable and writable for one release.
- Canonical values are authoritative after migration.
- Old writes must map to the relevant canonical/global or pathway override and emit a deprecation log.
- Never allow old and new settings to drive separate runtime behavior.

Legacy settings removed from runtime semantics:

- `dedup_similarity_threshold`
- `knowledge_creation_dedup_enabled`
- `knowledge_refine_on_merge`
- `knowledge_schedule_floor`
- `context_knowledge_mode`
- `consolidation_run_interval_days` as a legacy pairwise control; if retained, it schedules shared hygiene only.

## 6. Persistent embedding foundation

### 6.1 Writes

Route every embedding write through shared helpers that return vector plus provenance. Cover:

- interaction ingestion;
- memory creation/compaction;
- intelligence generation/manual creation;
- all Knowledge producers/imports/admin creation;
- Knowledge revision/consolidation;
- backfills.

Remove every processing-time statement that clears interaction embeddings.

### 6.2 Coverage and backfill

Extend the existing backfill service to all tiers or introduce one shared tier-aware backfill service.

Requirements:

- resumable batches;
- idempotent compare-and-update;
- model/version/dimension-aware selection;
- per-record failure capture;
- no infinite retry within one run;
- tier-specific coverage counts;
- optional tier selection;
- safe concurrency locks;
- no content/status mutation.

API/UI coverage must show, per tier:

- total eligible;
- compatible;
- missing;
- stale model/version/dimensions;
- failed last attempt;
- percentage ready.

Evidence routing cannot enter `enforced` mode until required source tiers meet configured coverage, recommended `>= 99%` for eligible recent sources.

## 7. Pre-generation evidence routing

### 7.1 Evidence bundle construction

For each generation attempt with structured source evidence:

1. Normalize and deterministically sort typed source references `(source_type, source_id, source_role)`.
2. Load persisted source embeddings and provenance.
3. Reject incompatible/missing embeddings from automatic routing and record why.
4. L2-normalize compatible member embeddings.
5. Compute aggregate centroid.
6. Store member IDs, scope, time window, context digest, outcome signature, and aggregate provenance.

Do not place raw source content in routing metrics. Evidence events may retain governed source IDs and snapshots according to existing audit policy. Manual creation/import without source evidence bypasses pre-generation source routing, persists complete provenance available to it, and enters post-creation Knowledge hygiene.

### 7.2 Historical candidate discovery

Compare new bundles only with compatible processed evidence:

- same source type;
- same pathway unless an explicitly supported cross-pathway policy exists;
- compatible model/version/dimensions;
- appropriate entity type/scope;
- historical sources linked to Knowledge or a prior no-change/evidence-link event.

Trace historical source IDs through authoritative `knowledge_source_links`, while retaining compatibility checks against:

- `knowledge.source_intelligence_ids`;
- `knowledge.source_ai_interaction_ids`;
- `knowledge.merged_into` until the active canonical is reached.

Never choose a retired record as the revision/link target.

### 7.3 Metrics

For every new member, calculate its best compatible historical member match. Persist:

- centroid similarity;
- member minimum/average/maximum similarity;
- coverage at low threshold;
- coverage at high threshold;
- canonical distribution (how many matches resolve to each canonical);
- source/pathway compatibility;
- context/outcome conflict flags.

Define aggregate similarity initially as the mean of centroid similarity and matched-member average:

```text
aggregate = 0.5 × centroid_similarity + 0.5 × member_average_similarity
```

Keep the formula versioned in code and audit settings. Do not expose formula weights in normal UI.

### 7.4 Route selection

#### Low: normal generation

Choose `new_generation` when aggregate similarity is below `0.78` or no valid historical canonical is resolved.

Run the normal producer LLM. Persist the created Knowledge as Draft with `generation_state='pending_hygiene'`, then enter shared post-generation hygiene.

#### Moderate: revision assessment

Choose `revision_assessment` when:

- aggregate is `>= 0.78` and `< 0.95`; or
- aggregate is high but very-high safeguards fail; and
- at least one active canonical is resolved.

If matches resolve predominantly to exactly one canonical, call the evidence-revision service with:

- complete canonical Knowledge;
- all new source evidence;
- source provenance;
- route metrics;
- governed facets and category constraints.

Structured outcomes:

```text
no_change
revise
create_new
manual_review
```

If matches resolve to multiple canonicals, do not arbitrarily revise one. Generate a new candidate or create a manual/consolidation proposal using the shared hygiene service.

#### Very high: evidence-only link

Choose `evidence_link` without a generation LLM only when all conditions pass:

- aggregate similarity `>= 0.95`;
- high-threshold member coverage `>= 0.90`;
- compatible provenance for every member used in the decision;
- all significant matches resolve to one active canonical;
- no deterministic outcome/context conflict;
- canonical is not protected from evidence updates;
- routing mode is `enforced`.

Transactionally:

1. lock the bundle and canonical;
2. revalidate route metrics/source versions;
3. append unique source IDs to canonical provenance arrays or normalized evidence linkage;
4. update evidence breadth inputs;
5. write evidence event;
6. recalculate quality;
7. mark bundle linked;
8. commit atomically.

Do not change canonical content or increment legacy merge count.

Deterministic context/outcome conflicts include a changed structured success/failure outcome, incompatible governed jurisdiction/environment/product facets, or a changed source role. Any such difference forces the moderate route. Absence of structured context is not itself a conflict, but must be reported in route metrics.

### 7.5 Revision service

Implement revision preview and apply separately, following consolidation safety:

```python
proposal = evidence_revision_service.preview(bundle_id, canonical_id)
result = evidence_revision_service.apply(preview_id, approved_output)
```

Preview has TTL and source/canonical version snapshots. Apply locks and rejects stale inputs. LLM output must include:

- recommendation;
- proposed canonical fields if revision is needed;
- preserved information;
- new information added;
- contradictions/warnings;
- source-to-output traceability;
- confidence and rationale.

Manual/proposal/automatic policy must reuse the same deterministic gates as consolidation where applicable.

## 8. Shared generation orchestration

### 8.1 Global scheduled run

Replace separate knowledge/playbook/telemetry schedule triggers with one orchestrated Knowledge generation run. Default order:

1. declarative Knowledge from confirmed intelligence;
2. playbook extraction;
3. skill extraction from produced/updated playbooks;
4. telemetry reflection.

Each step checks `enabled`, resolves effective settings, records its own pipeline outcome, and does not prevent later independent pathways from running unless a shared infrastructure failure requires abort.

Manual pathway triggers remain available inside the pathway accordion and use the same services/settings.

### 8.2 One evidence threshold

Remove nightly floor override. Threshold-triggered and scheduled declarative generation use the same effective evidence threshold and batch size. Entity override remains supported through the resolver.

### 8.3 One token and confidence policy

Every producer passes effective `max_tokens` and validates a required `confidence` field using effective `min_confidence`.

Update declarative generation schema to include confidence. Validate/clamp consistently; invalid or absent confidence makes the structured result invalid and eligible for one repair retry, not silent default `0.5`.

### 8.4 Approval policy

Every producer resolves approval policy after initial post-generation hygiene. A generated record must never become agent-visible while `generation_state='pending_hygiene'` or `requires_review`.

When hygiene finds no eligible related Knowledge, recommends `keep_separate`, or an approved consolidation/revision leaves a standalone candidate, apply the resolved policy. On Approved transition:

- persist `status='active'`;
- stamp approval audit fields;
- record whether approval was policy-driven or manual.

On Draft creation:

- persist `status='draft'`;
- approval fields remain null.

If hygiene requires manual review, keep the record Draft with `generation_state='requires_review'` regardless of the Approve-immediately policy. After review, apply the approved operation and then resolve final status.

Manual draft → Approved uses one service that stamps audit fields and recalculates quality.

### 8.5 Remove legacy generation behavior

Delete runtime calls to:

- `find_similar_existing` for direct producer dedup;
- `increment_merge` from producers;
- `refine_or_increment_merge` from producers;
- generation-time “Existing Knowledge (do NOT duplicate)” prior lookup.

Keep temporary deprecated shims only if external imports require them, and make them delegate or no-op with warnings. No shim may mutate Knowledge using legacy semantics.

## 9. Facets

### 9.1 Primary generation output

All category-aware generation schemas include:

```json
{
  "facets": {
    "country": "Malaysia"
  },
  "confidence": 0.82
}
```

Inject the current governed schema and schema version into the prompt. Validation rules:

- allow configured keys only;
- scalar or configured field type only;
- normalize controlled values where configured;
- omit unsupported/uncertain values;
- never invent;
- preserve explicit caller facets;
- generated facets fill only missing keys.

Store `facet_status`, schema version, and validation provenance.

### 9.2 Manual/import/backfill

Manual and import payload facets are authoritative after deterministic validation. When facets are absent, an administrator may explicitly request extraction.

Backfill:

- processes active and Draft records as configured;
- skips Retired unless explicitly requested for audit preparation;
- records `no_facet` rather than repeatedly retrying;
- retries failed only on explicit request or newer schema version;
- never overwrites explicit facets.

### 9.3 Retrieval semantics

- Explicit request/API facets: strict JSONB filter.
- Profile-derived facets: ranking boost, never hard exclusion.
- Always-on Knowledge: bypasses both.

Profile boost must be deterministic and visible in retrieval diagnostics. Start with:

```text
base_score = 0.70 × semantic_relevance + 0.30 × quality_score
profile_match_ratio = matching_profile_facets / supplied_profile_facets
final_score = min(1, base_score + 0.05 × profile_match_ratio)
```

When no compatible semantic score exists, quality-only degraded fallback remains authoritative and the profile boost may still reorder but never exclude. Version the ranking formula and keep profile contribution bounded at 5%.

## 10. Quality model v2

### 10.1 Components

```text
quality =
    0.35 × evidence_strength
  + 0.30 × outcome_feedback
  + 0.20 × generation_confidence
  + 0.15 × validation_provenance
```

Clamp every component and final score to `[0,1]`.

### 10.2 Evidence strength

Use unique evidence bundles and diversity, not raw telemetry-event volume:

```text
volume = min(log1p(unique_bundle_count) / log1p(10), 1)
diversity = min(distinct_entity_or_session_count / 5, 1)
evidence_strength = 0.6 × volume + 0.4 × diversity
```

Store counts in component details. Consolidation unions unique evidence; evidence-only link adds one bundle once.

### 10.3 Bayesian outcome feedback

Use a neutral Beta prior:

```text
outcome_feedback = (success_count + 2) / (success_count + failure_count + 4)
```

No feedback yields `0.5`; a single event cannot produce an extreme score.

Feedback submission must transactionally update counters, component breakdown, and final score.

### 10.4 Generation confidence

Use the evidence-weighted mean of validated producer confidences associated with active evidence bundles. For manual/imported content without model confidence, use neutral `0.5` and surface missing-confidence coverage; do not pretend it was LLM-scored.

### 10.5 Validation and provenance

Compute from explicit facts, versioned in code. Initial breakdown:

- 50% source provenance completeness;
- 25% embedding/facet/schema provenance completeness;
- 25% approval assurance:
  - manual approval: `1.0`;
  - configured automatic approval: `0.7`;
  - Draft: `0.0`.

System-governed seeded records may set an explicit system validation value with audit origin.

### 10.6 Staleness

Remove record age from quality. Keep decay/freshness as a separate status/metric with category-aware policy. A durable lesson does not become lower quality solely because it is old.

### 10.7 Recalculation triggers

Recalculate transactionally after:

- creation;
- evidence link;
- revision;
- feedback;
- approval;
- consolidation/reversal;
- source/provenance repair;
- quality-version migration.

Provide resumable quality v2 backfill for all non-Retired records and optional Retired audit recomputation.

## 11. Retrieval

### 11.1 Ordinary Knowledge

Remove general full-mode output. Ordinary matched entries always return:

```json
{
  "id": "...",
  "name": "...",
  "category": "...",
  "signals": [],
  "summary": "...",
  "facets": {},
  "quality_score": 0.73
}
```

Do not include full content, heavy metadata, tags, or retired lineage. Full content remains available through the existing authorized Knowledge-by-ID endpoint.

### 11.2 Always-on Knowledge

Prepend every active/shared `always_inject=true` record in full. Always-on records bypass:

- semantic floor;
- explicit/profile facets;
- category filter;
- ordinary result limit.

Keep the existing protection against agent mutation of system-governed records.

### 11.3 Semantic ranking and floor

Persisted Tier 0 embeddings allow the current-conversation vector to remain available. Continue a versioned relevance/quality blend initially at 70/30.

Relevance floor rules:

- floor `0`: no semantic exclusion;
- floor `>0`: ordinary Knowledge without measurable compatible similarity is excluded;
- missing query vector or query failure: observable degraded quality-only fallback;
- fallback must state that the floor was not applied;
- never silently represent degraded results as semantic matches.

Start floor at `0` and expose distributions/diagnostics before calibration.

### 11.4 Compatibility

Ignore/deprecate incoming full-mode requests and return index output with a deprecation response header/log where applicable. Document this intentional product change. Keep always-on full content as the only exception.

## 12. Backend service boundaries

Recommended modules:

- `memory_generation_policy.py` — canonical settings/override resolution;
- `memory_evidence_repository.py` — bundle/event SQL;
- `memory_evidence_service.py` — bundle construction, candidate discovery, metrics, routing;
- `memory_evidence_revision_prompts.py` — category-aware structured revision;
- `memory_evidence_revision_service.py` — preview/apply;
- `memory_quality.py` — pure v2 calculation plus transactional update helper;
- existing `memory_embedding.py` — extend provenance helpers to all tiers;
- existing `memory_embedding_backfill.py` — make tier-aware or delegate to shared backfill;
- existing `memory_facets.py` — validation/backfill only, not normal-generation LLM extraction;
- existing `memory_consolidation_service.py` — remains the only post-generation consolidation boundary.

Do not duplicate SQL or mutation behavior across pathway modules. Producers adapt source data and call shared services.

## 13. API changes

Keep existing authenticated settings endpoints and add/extend:

```text
GET  /api/memory/admin/knowledge/generation/status
POST /api/memory/admin/knowledge/generation/run
GET  /api/memory/admin/knowledge/evidence-routing/coverage
GET  /api/memory/admin/knowledge/evidence-routing/runs/{id}
POST /api/memory/admin/knowledge/evidence-routing/analyze
GET  /api/memory/admin/embeddings/coverage?tier=all
POST /api/memory/admin/embeddings/backfill
GET  /api/memory/admin/knowledge/quality/coverage
POST /api/memory/admin/knowledge/quality/recalculate
GET  /api/memory/admin/knowledge/facets/coverage
POST /api/memory/admin/knowledge/facets/backfill
```

Use existing consolidation endpoints for post-generation hygiene. Evidence-revision preview/apply endpoints must be separate from generation and mutation, mirroring consolidation.

All action endpoints return a run/job ID. UI must poll/read run detail rather than showing only a toast.

## 14. Knowledge settings UI

Route remains:

```text
/app/settings?tab=memory&memoryTab=knowledge
```

Add nested URL state, for example `knowledgeSubtab=generation|maintenance|retrieval`, default `generation`. Preserve browser back/forward and direct links.

### 14.1 Knowledge Generation

Order exactly:

1. **Shared Global Generation Controls**
   - enabled;
   - global time;
   - maximum tokens;
   - minimum confidence;
   - evidence threshold;
   - Approve immediately / Create as draft.
2. **Generation Actions and Status**
   - Generate Next Batch;
   - Process Backlog;
   - backlog counts;
   - current/last run;
   - failures with links.
3. **Knowledge Generation Pathways**
   - declarative Knowledge;
   - telemetry reflection;
   - playbook extraction;
   - skill extraction.

Each accordion contains:

- enabled and readiness state;
- input/output description;
- effective values with source badges;
- override toggles/fields and reset-to-global;
- entity overrides where applicable;
- Prompt Manager link/system prompt;
- provider/model/thinking/execution settings;
- recent pathway run status;
- save validation.

Do not render pathway prompts/models/overrides elsewhere.

### 14.2 Knowledge Maintenance

Sections:

1. Evidence routing
   - analysis/enforced mode;
   - low/high thresholds and high coverage;
   - route distribution;
   - Analyze Evidence Routing.
2. Consolidation and hygiene
   - existing shared hygiene settings;
   - Analyze Now;
   - proposal/run status;
   - category policy controls;
   - creation-time/post-generation hygiene controls.
3. Embeddings
   - tier coverage table;
   - backfill/re-embed action;
   - model/version/dimension warnings.
4. Quality
   - v2 coverage;
   - component distributions;
   - feedback coverage;
   - recalculation/backfill.
5. Utilities
   - Export Pack;
   - audit/run links;
   - no direct automatic merge button.

### 14.3 Knowledge Retrieval

Sections:

1. Index retrieval
   - result cap;
   - semantic relevance floor;
   - current relevance/quality blend shown as informational unless deliberately made configurable later.
2. Always-on Knowledge
   - count/list/link to records;
   - explicit explanation that full content bypasses filters/cap.
3. Facets
   - governed schema form editor;
   - profile-property mapping form;
   - explicit strict vs profile boost explanation;
   - coverage/schema version;
   - versioned Backfill Facets action.
4. Advanced
   - raw facet JSON;
   - retrieval diagnostics.

Remove the full/index selector.

### 14.4 Controls moved elsewhere

- Move Memory Generation Interaction Types to Memories configuration.
- Move all queue concurrency controls to system-level Advanced / Performance.

## 15. Implementation sequence

These are review checkpoints within one implementation initiative, not optional follow-ups.

### PR 1 — Additive schema, canonical settings, and compatibility resolver

- schema in §4;
- canonical settings and migrations;
- effective resolver with source badges;
- approval audit fields/backfill;
- no behavior switch yet.

### PR 2 — Persistent embeddings and tier-wide backfill

- shared provenance writes;
- stop clearing Tier 0 embeddings;
- coverage/backfill APIs;
- compatibility gates;
- tests for every creation/update path.

### PR 3 — Evidence bundles and analysis-only routing

- repository/service/metrics;
- provenance traversal to canonical Knowledge;
- all pathways build bundles;
- analysis-only results and observability;
- no skipped LLM calls or revisions yet.

### PR 4 — Shared generation policy and legacy removal

- one schedule/orchestrator;
- global token/confidence/evidence/approval policy;
- pathway overrides;
- remove old prior-context and direct dedup/refine calls;
- structured confidence/facets in every generation output;
- keep evidence routing analysis-only initially.

### PR 5 — Evidence revision and enforced routing

- preview/apply service;
- no-change/revise/create-new/manual outcomes;
- transactional evidence-only links;
- quality recalculation hooks;
- post-generation shared hygiene;
- enforcement feature flag/mode.

### PR 6 — Facets, quality v2, and retrieval

- governed facet validation/provenance/backfill;
- quality v2 and backfill;
- feedback wiring;
- index-only ordinary retrieval;
- full always-on exception;
- strict floor semantics and degraded diagnostics.

### PR 7 — Three-subtab UI and control relocation

- exact UI structure in §14;
- pathway accordion ownership;
- run/coverage dashboards;
- move misplaced controls;
- remove superseded settings/cards;
- accessibility, responsive layout, URL persistence.

### PR 8 — Production migration verification and cleanup

- dry-run reports;
- compatibility tests;
- obsolete-code search proving no legacy mutation caller remains;
- documentation/environment reference updates;
- leave legacy DB columns intact but mark deprecated.

## 16. Rollout and safety gates

1. Deploy additive schema and canonical settings with routing `analysis_only`.
2. Backfill embeddings for all tiers and confirm coverage.
3. Compare routed outcomes against actual generation results without skipping calls.
4. Calibrate `0.78/0.95` by pathway/model distributions; document any approved override.
5. Enable moderate revision proposals in manual/proposal-only mode.
6. Review evidence-link false-positive risk. Enable enforced very-high skips only after acceptance samples pass.
7. Keep post-generation consolidation in `manual_only` or `proposal_only` until separately approved.
8. Run quality v2 shadow calculation before replacing retrieval ranking.
9. Switch ordinary retrieval to index-only after agent fetch-by-ID behavior is verified; always-on remains full.

No rollout gate may re-enable legacy direct dedup/refine behavior.

## 17. Required tests

### 17.1 Settings and migration

- canonical defaults;
- old values migrate correctly;
- materially different pathway values become overrides;
- `null` override inherits;
- entity → pathway → global resolution;
- legacy writes map once without split behavior;
- Approved UI maps to stored `active`;
- historical active approval backfill is truthful/system-origin.

### 17.2 Embeddings

- embeddings persist on all four tiers;
- interaction processing never clears embeddings;
- provenance stamped on create/update/revision/consolidation;
- missing/stale/model/dimension coverage;
- resumable/idempotent backfill;
- failed item does not loop indefinitely;
- incompatible embeddings never route automatically.

### 17.3 Evidence routing

- low route;
- moderate route;
- very-high route;
- high score with insufficient member coverage falls to moderate;
- high score resolving to multiple canonicals falls to moderate/manual;
- outcome/context conflict blocks evidence-only link;
- shuffled source order is deterministic;
- duplicate job is idempotent;
- stale source versions rejected;
- retired Knowledge resolves through `merged_into`;
- no canonical found triggers new generation;
- telemetry and intelligence source traversal;
- every pathway records complete source IDs;
- analysis-only never skips a generation call.

### 17.4 Revision and consolidation

- no-change links evidence without rewriting;
- revise preserves canonical information and adds traceable evidence;
- create-new proceeds to normal candidate/hygiene;
- manual-review does not mutate;
- preview TTL/staleness;
- transactional rollback on LLM validation, embedding, or DB failure;
- concurrent revision/consolidation conflict;
- lineage remains reversible;
- no legacy mutation function called.

### 17.5 Facets

- each generation category emits validated facets;
- unknown keys/types rejected or omitted;
- explicit facets never overwritten;
- generated facets fill missing only;
- no second facet LLM call during normal generation;
- manual/import extraction remains explicit;
- schema-version backfill;
- `no_facet` not retried on same version;
- explicit facets hard-filter;
- profile facets boost but never exclude;
- always-on bypasses facets.

### 17.6 Quality

- exact component/formula cases;
- no-feedback Bayesian neutral value;
- one success/failure not extreme;
- duplicate evidence bundle counts once;
- distinct evidence increases strength with diminishing returns;
- feedback recalculates immediately;
- manual versus automatic approval component;
- consolidation union and reversal;
- score version/components stored;
- backfill covers Draft and Approved without requiring embeddings;
- age alone does not reduce quality.

### 17.7 Retrieval

- ordinary Knowledge never includes full content;
- always-on Knowledge always includes full content;
- always-on bypasses cap/floor/facets/category;
- Draft/Retired never returned;
- floor `0` ranks without rejection;
- nonzero floor excludes missing/low similarity;
- degraded fallback is observable;
- full-mode request cannot restore ordinary full content;
- fetch-by-ID returns authorized full active record.

### 17.8 UI

- exactly three subtabs and direct URL persistence;
- Generation order matches KD-018;
- effective/inherited override badges;
- pathway prompt/model settings live only inside accordion;
- action returns and displays run ID/status;
- Maintenance coverage/run panels;
- Retrieval has no full/index selector;
- Approved/Draft terminology everywhere in UI;
- moved controls absent from Knowledge and present in new owner;
- keyboard/accessibility and narrow-screen behavior.

## 18. Acceptance criteria

Implementation is complete only when:

1. all locked decisions KD-001–KD-018 are represented in code and UI;
2. all four tiers retain compatible embeddings and report coverage;
3. every producer uses shared generation settings and evidence routing;
4. no producer calls legacy direct dedup/refine mutation;
5. source IDs trace to canonical Knowledge across consolidation lineage;
6. analysis-only routing is observable and enforced routing is safely gated;
7. generated facets require no second LLM call;
8. quality feedback and evidence changes recalculate v2 immediately;
9. ordinary retrieval is index-only and always-on Knowledge is full;
10. the Knowledge settings page has the exact three-subtab structure;
11. migrations are additive/idempotent and existing production settings are preserved;
12. backend focused tests, frontend tests/build, compose validation, and live integration smoke tests pass;
13. operator documentation explains rollout, defaults, compatibility aliases, and rollback.

## 19. Implementation blockers

There are no unresolved product decisions. The coding agent may implement without follow-up questions provided it follows this plan and the locked decision log. Threshold enforcement must still begin in analysis-only mode because calibration is an operational rollout gate, not a missing product decision.
