# Asynchronous Provider Batch Processing for All Knowledge Operations

## Status

Implemented on 2026-07-14. This document supersedes the earlier embedding-first
provider-batch plan and is retained as the implementation and QA contract.

Delivered in this implementation:

- additive preview, provider-run, request-manifest, and request-source schema;
- provider-neutral transport contract and OpenAI Batch adapter;
- mutation-free expiring review, deterministic request identity, persisted
  submission, provider reconciliation, restart recovery, cancellation, pause,
  resume, fresh-snapshot retry, request error inspection, usage capture, and
  provider-file cleanup;
- discounted asynchronous execution for embedding backfill, declarative
  Knowledge generation, consolidation proposals, and facet backfill;
- asynchronous local hygiene analysis for `analysis_only`;
- version-guarded and idempotent local application through existing domain
  validation/writer contracts;
- Operations UI capability checks, batch review, submission, live local/provider
  states, controls, and detailed history;
- synchronous calibration and legacy operation endpoints retained unchanged.
- exhaustive `All eligible` execution through a durable parent operation and as
  many provider-safe child batches as required;
- bounded, streamed preparation controlled by
  `PROVIDER_BATCH_PREPARATION_CHUNK_RECORDS` (an internal memory guard, never a
  user workload cap);
- lightweight sampled previews with extrapolated request, token, child-job, and
  cost estimates instead of materializing the full production manifest;
- configured provider-account selection, per-run model override, and per-run
  input/output or embedding price snapshots without changing shared prompts;
- parent-level pause, resume, cancellation, progress aggregation, child lineage,
  restart recovery, and actual-token cost calculation.

The `run_all_knowledge_generation` operation keeps telemetry, playbook, and
skill producers registered in the shared operation. Its first discounted remote
stage processes finite declarative evidence groups; dependent multi-stage
producer work continues through the existing producer pathways. This is shown
as a review warning instead of being silently represented as discounted work.

## Objective

Add a complete asynchronous execution path to the Knowledge Operations UI for
every current operation, while preserving the existing synchronous calibration
path and every operation's current prompts, models, serializers, validation,
lineage, idempotency, and database semantics.

Provider batch processing is a transport and billing option. It must not become
a second implementation of Knowledge generation, facet extraction, hygiene, or
embedding persistence.

The first remote adapter is OpenAI Batch. The orchestration layer must remain
provider-neutral so another provider can be added without changing operation
services or UI semantics.

## Definition of complete support

The current Knowledge Operations UI exposes four operation types. All four are
in scope:

| UI operation | Operation key | Work performed | Asynchronous execution |
|---|---|---|---|
| Embedding backfill | `knowledge_embedding_backfill` | Generate missing or stale embeddings across interactions, memories, intelligence, and Knowledge | Remote provider batch through `/v1/embeddings` |
| Knowledge generation | `run_all_knowledge_generation` | Run declarative, telemetry, skill, and playbook generation pathways | Remote provider batch for LLM requests, followed by local validation and persistence |
| Knowledge hygiene | `knowledge_hygiene_run` | Discover candidates, form clusters, and optionally generate consolidation proposals | Local asynchronous analysis for `analysis_only`; remote provider batch for proposal generation |
| Facet backfill | `backfill_facets` | Populate governed facets on eligible active Knowledge | Remote provider batch for structured LLM extraction |

Supporting all operation types does not mean every stage must be sent to an AI
provider. Deterministic database analysis remains local. The UI must explain the
actual execution path rather than label local work as a discounted provider
batch.

The following related actions remain supported but are not provider-batch jobs:

- Export approved Knowledge: local file generation.
- Manual consolidation preview: interactive and must return immediately.
- Manual consolidation apply: transactional and user-confirmed.
- Creation-time evidence routing and consolidation: latency-sensitive.
- Interactive document parsing and Knowledge-draft generation.
- Interaction retention: local database maintenance.

## Required user experience

### 1. Select an operation

The existing operation selector remains the entry point.

### 2. Select an execution mode

The UI presents only modes supported by the chosen operation:

- **Synchronous calibration**: small, immediate, request-bound run.
- **Asynchronous discounted batch**: submit provider work and return immediately.
- **Asynchronous local analysis**: background processing without a provider;
  shown for hygiene `analysis_only`.
- **Automatic**: future policy-based selection; hidden until production
  calibration is complete.

`Asynchronous discounted batch` must be disabled with an explicit reason when:

- the configured provider has no batch adapter;
- credentials are missing or invalid;
- the configured model or endpoint is unsupported;
- the operation has no remote requests in the selected mode;
- another conflicting run owns the same finite source snapshot;
- the global provider-batch feature flag is off.

### 3. Configure a finite workload

Retain the product terminology already locked for operations:

- **Records per Batch**: application processing group and maximum records placed
  in one provider request. Operation-specific validation still applies.
- **Batches per Run**: a number or **All eligible records**.

The UI calculates and displays:

- maximum source records;
- eligible source records in the finite snapshot;
- application batches/provider request lines;
- provider batch jobs required after endpoint, provider, model, file-size, and
  provider-limit partitioning;
- excluded empty, stale, protected, retired, already-claimed, or incompatible
  records;
- estimated input/output tokens and cost where pricing metadata is configured;
- provider completion window and retention notice.

### 4. Review before submission

`Review batch` performs a mutation-free preflight and returns:

- operation and pathway breakdown;
- provider, endpoint, model, prompt version, and embedding version;
- source record count and source-version snapshot;
- request count and provider-job count;
- invalid or oversized source count;
- estimated usage and price;
- warnings, unsupported partitions, and fallback policy;
- a manifest checksum.

The preview expires. Submission rejects a stale preview and requires regeneration.

### 5. Submit and monitor

`Submit asynchronous batch` creates a durable parent operation and returns
immediately. Short-lived recovery cycles discover the accepted finite snapshot,
prepare one bounded manifest, persist its requests and source lineage, upload it,
and create a provider child batch. The cycle repeats until every accepted source
has been prepared. Provider request, embedding-input, and file-size limits create
additional child batches automatically; they never defer the remaining workload
to a separate user submission.

The Active Knowledge Operations panel shows:

- preparing;
- uploading;
- validating;
- submitted;
- provider in progress;
- finalizing;
- importing results;
- applying results;
- paused;
- completed;
- partially completed;
- failed;
- expired;
- cancelling;
- cancelled.

The panel must show provider state separately from local worker state. A run
waiting at the provider is not an active long-running Python worker.

The parent operation displays sources prepared versus selected, provider request
count, child provider-job count, applied/failed results, model, estimated cost,
and child status. Child runs remain inspectable for provider IDs and request-level
errors.

### 6. Operate the run

Users can:

- pause future provider-batch submissions;
- cancel submitted provider batches;
- resume unresolved work;
- retry only failed, expired, missing, or stale-rejected requests after review;
- open request-level error summaries;
- compare estimated and actual usage;
- navigate from a run to generated Knowledge, facet updates, proposals, or
  affected source records.

## Non-negotiable compatibility rules

Asynchronous execution must not change:

- prompt-manager resolution or prompt text;
- provider account and model selection;
- thinking/reasoning settings;
- maximum output-token settings;
- governed facet schema;
- category-aware Knowledge contracts;
- SKILL.md-inspired skill and playbook structures;
- embedding serialization;
- source eligibility and activation policy;
- confidence and quality calculation;
- candidate similarity and clustering controls;
- consolidation review/application policy;
- evidence, provenance, source links, and lineage;
- retired-record filtering;
- stale-source/version checks;
- transactional boundaries;
- synchronous APIs and existing queue job names.

Existing endpoints remain backward compatible. They become thin wrappers around
the shared operation service instead of maintaining separate behavior.

## Architecture

```text
Knowledge Operations UI
        |
        v
operation_service.preview(operation, options)
        |
        +--> finite source snapshot
        +--> shared operation request builder
        +--> manifest + estimates + capability checks
        |
        v
operation_service.submit(preview_id, execution_mode)
        |
        +--> synchronous executor
        +--> local asynchronous executor
        +--> provider batch executor
                    |
                    v
            provider adapter(s)
                    |
                    v
             persisted provider state
                    |
                    v
              reconciliation worker
                    |
                    v
          shared parser/validator/applier
```

No provider adapter may write operation results directly to Knowledge tables.
All results return through the existing domain validators and writers.

## Shared operation contract

Implement an operation adapter for every operation:

```python
class KnowledgeOperationAdapter(Protocol):
    operation_key: str

    def discover(self, options) -> SourceSnapshot: ...
    def build_requests(self, snapshot, settings) -> list[OperationRequest]: ...
    def estimate(self, requests) -> OperationEstimate: ...
    def validate_result(self, manifest_request, result) -> ValidatedResult: ...
    def apply_result(self, manifest_request, validated_result) -> ApplyResult: ...
```

The synchronous and provider-batch executors consume the same
`OperationRequest`. Tests must prove that the provider request body is equivalent
in both modes apart from transport fields such as `custom_id`, `method`, and URL.

## Provider-neutral batch contract

```python
class ProviderBatchAdapter(Protocol):
    provider_key: str

    def capabilities(self) -> BatchCapabilities: ...
    async def upload(self, requests, metadata) -> UploadedManifest: ...
    async def submit(self, upload, endpoint, metadata) -> ProviderBatchHandle: ...
    async def status(self, handle) -> ProviderBatchStatus: ...
    async def results(self, handle) -> Iterable[ProviderBatchResult]: ...
    async def cancel(self, handle) -> ProviderBatchStatus: ...
    async def delete_files(self, handle) -> None: ...
```

Capabilities include supported endpoints/models, completion windows, maximum
requests, maximum inputs, maximum file bytes, output expiry controls,
cancellation support, and whether output ordering is guaranteed.

Core operation code must contain no OpenAI-specific URLs or response parsing.

## Persistent schema

All migrations are additive and idempotent.

### `memory_operation_previews`

Stores mutation-free review data:

- ID, operation key, actor, and origin;
- options and execution mode;
- settings/model/prompt/embedding snapshots;
- source snapshot checksum;
- request/record/token/cost estimates;
- warnings and exclusions;
- expiration and creation timestamps.

### `memory_provider_batch_runs`

One local run may own multiple provider batches because requests can differ by
provider, endpoint, model, or provider limits.

Store:

- local pipeline run ID and preview ID;
- operation key and pathway;
- provider, endpoint, model, and completion window;
- provider batch/input/output/error file IDs;
- local and provider status;
- request counts and timestamps;
- estimated and actual usage/cost;
- manifest checksum;
- pause/cancel flags;
- provider error and sticky-alert linkage;
- last poll, next poll, lease owner, and lease expiry.

### `memory_provider_batch_requests`

Request-level manifest and idempotency record:

- deterministic `custom_id`;
- provider-batch run ID;
- operation and pathway;
- request ordinal and request hash;
- source snapshot/version hash;
- prompt/model/embedding/facet-schema versions;
- status and attempt number;
- provider response/request ID;
- usage and error summary;
- validation and apply timestamps;
- applied output references.

### `memory_provider_batch_request_sources`

Many-to-many mapping because one Knowledge-generation or hygiene request may use
multiple source records:

- manifest request ID;
- source type and ID;
- source version/update timestamp;
- source role;
- evidence-bundle or cluster membership metadata.

### Existing `memory_pipeline_runs`

Extend additively with execution mode, provider state summary, current provider
batch count, and operation-result navigation. Detailed provider state remains in
the new tables.

## Deterministic request identity

Every provider request receives a unique deterministic `custom_id` derived from:

- operation key and pathway;
- source or group identity;
- source snapshot checksum;
- provider/endpoint/model;
- prompt, embedding, or facet-schema version;
- attempt number.

A result is eligible for application only when:

- its `custom_id` exists in the persisted manifest;
- the response belongs to the expected provider batch;
- the request has not already been applied;
- all required source records still exist;
- source versions still match, or the operation's explicit stale policy permits
  a harmless skip;
- provider output passes operation-specific schema and safety validation.

Provider output order must never be trusted. Duplicate result delivery is a
no-op. Missing results remain retryable.

## OpenAI Batch adapter

The OpenAI adapter must:

1. Serialize JSONL using the shared request bodies.
2. Upload files with `purpose=batch`.
3. Create batches with the supported completion window.
4. Persist the provider batch ID before returning success.
5. Poll using bounded backoff.
6. Download output and error files.
7. Map every line by `custom_id`.
8. Support cancellation and partial outputs.
9. Delete provider files according to configured retention.
10. Record provider request IDs and usage without logging source content.

Current OpenAI constraints to enforce through adapter capabilities, not scattered
hard-coded UI rules:

- JSONL input;
- `24h` completion window;
- supported Batch endpoints including `/v1/embeddings`, `/v1/responses`, and
  `/v1/chat/completions`;
- up to 50,000 requests and 200 MB per input file;
- no more than 50,000 total embedding inputs in an embedding batch;
- embedding per-input and per-request token/input limits;
- cancellation can produce partial results.

One provider batch contains one endpoint. For operational consistency, also
partition by provider account and model. A single local operation run may
therefore create multiple provider batches.

Official references:

- https://platform.openai.com/docs/api-reference/batch/object
- https://platform.openai.com/docs/api-reference/files/object
- https://platform.openai.com/docs/api-reference/embeddings

## Operation-specific behavior

### 1. Embedding backfill

#### Discovery

- Cover interactions, memories, intelligence, and Knowledge.
- Use the shared embedding provider/model/version.
- Select only missing or stale compatible records.
- Exclude permanently empty serialized inputs before manifest creation.
- Partition by tier only where required for result application or observability.

#### Request building

- Use the existing canonical serializers and input truncation/token guards.
- Preserve current `Records per Batch` grouping.
- Each manifest request can contain multiple embedding inputs but must map each
  returned vector to one source record deterministically.

#### Application

- Validate vector presence, dimensions, provider model, and source version.
- Update embedding and provenance fields using the existing conditional writers.
- Never change content, status, quality, or lineage.
- A failed input does not discard successful vectors from the same provider job.

### 2. Knowledge generation

Support every enabled generation pathway:

- confirmed-intelligence declarative generation;
- telemetry reflection;
- skill extraction;
- playbook extraction;
- future registered generation pathways using the same adapter contract.

#### Discovery

- Reuse each pathway's current evidence threshold, schedule eligibility,
  pre-generation evidence routing, activation policy, and source claims.
- Create finite source/evidence bundles before submission.
- A source is claimed for the run but is not marked consumed merely because a
  provider request was submitted.

#### Request building

- Resolve the exact pathway prompt, model, reasoning, confidence, facet schema,
  output-token budget, category contract, and existing Knowledge references.
- Preserve SKILL.md-inspired fields for skill/playbook outputs.
- Partition provider batches by pathway, endpoint, provider, model, and prompt
  version.

#### Application

- Parse with the same structured-response parser used synchronously.
- Apply global/pathway confidence and validation rules.
- Run the same pre-create evidence/consolidation routing policy.
- Create, revise, skip, or route to consolidation using existing shared services.
- Preserve evidence links and source pathway.
- Mark source claims complete only after the corresponding validated result is
  applied or deterministically rejected.
- Re-delivery must not create a duplicate Knowledge record.

### 3. Knowledge hygiene

#### `analysis_only`

- Candidate discovery, similarity graphs, component splitting, cohesion, and
  metrics remain local.
- Run through the asynchronous local executor.
- The UI must say **Asynchronous local analysis**, not discounted provider batch.
- Persist the same hygiene-run, cluster, and member records as today.

#### `proposal_only` and `manual_only`

- Run deterministic discovery locally first.
- Freeze proposed cluster membership and source versions.
- Build category-aware LLM proposal requests for provider batch submission.
- Partition by category, prompt version, provider, model, and endpoint.
- Import into the existing consolidation preview/proposal schema.
- Never mutate Knowledge records automatically in these modes.

#### `auto_conservative` and `auto_synthesis`

- Provider batch may generate proposals.
- Imported proposals must pass the same deterministic policy gates,
  contradiction policy, confidence policy, category automation policy, and stale
  checks.
- Application must call the existing shared transactional consolidation service.
- No provider result directly retires or rewrites Knowledge.
- Initial rollout keeps auto modes disabled.

### 4. Facet backfill

#### Discovery

- Select active, eligible Knowledge lacking current governed facets.
- Snapshot Knowledge version and facet-schema version.
- Exclude retired, protected, already-current, or claimed records.

#### Request building

- Resolve the existing facet extraction prompt and configured LLM settings.
- Include the same Knowledge content and governed schema as synchronous mode.
- Require the existing structured output.

#### Application

- Validate keys and values against the governed schema.
- Discard unsupported/invented facets exactly as synchronous mode does.
- Apply through a source-version and facet-schema-version guard.
- Recompute quality only through the existing quality service when current
  synchronous behavior requires it.
- A stale record remains retryable and is not overwritten.

## Reconciliation worker

Do not hold a BullMQ worker or singleton database lock throughout the provider's
completion window.

Implement short-lived idempotent jobs:

- `provider_batch_prepare`;
- `provider_batch_submit`;
- `provider_batch_reconcile`;
- `provider_batch_import`;
- `provider_batch_apply`;
- `provider_batch_cancel`;
- `provider_batch_cleanup`.

Each job acquires a short database lease, performs one bounded transition, saves
state, and exits. Reconciliation runs:

- on a configured polling schedule;
- at application startup for non-terminal runs;
- when the user refreshes or requests an explicit status sync;
- from provider webhooks in a future optional enhancement.

Database state is authoritative. Redis/BullMQ contains wake-up work, not the sole
copy of provider-batch state.

## State machine

Allowed transitions must be explicit and tested:

```text
previewed
  -> preparing
  -> uploading
  -> submitted
  -> provider_validating
  -> provider_in_progress
  -> provider_finalizing
  -> importing
  -> applying
  -> completed | partially_completed

preparing/uploading/submitted/provider_*
  -> failed | expired | cancelling | cancelled

partially_completed/failed/expired/cancelled
  -> retry_preparing (unresolved requests only)
```

Terminal runs cannot return to running. Retry creates a new attempt linked to the
original manifest and includes only unresolved requests.

## Pause, cancel, and resume semantics

### Pause

- Stop preparing or submitting additional provider batches.
- Allow already-submitted provider batches to reach a terminal provider state.
- Import and safely apply completed results.
- Leave remaining partitions paused.

### Cancel

- Stop new submissions.
- Request provider cancellation for submitted non-terminal batches.
- Continue reconciliation until the provider reports a terminal state.
- Import any partial successful outputs.
- Leave unresolved requests eligible for retry.

### Resume

- Revalidate the source snapshot.
- Exclude already-applied requests.
- Rebuild only unresolved or explicitly retryable requests.
- Create a new attempt and provider batch; never reuse an expired input blindly.

## Failure and fallback policy

- Provider capability failure during preview: disable provider-batch submission.
- Upload/submission failure before the provider accepts the batch: optional
  synchronous fallback when configured and within synchronous safety limits.
- Any failure after provider acceptance: never silently fall back synchronously;
  reconcile first to avoid duplicate cost and duplicate writes.
- Rate limit or credit exhaustion: stop submission, persist the existing sticky
  system alert, and keep unresolved work retryable.
- Provider outage: back off without creating duplicate provider batches.
- Invalid request lines: isolate and report; valid lines continue.
- Expiry/cancellation: import partial results, then expose retry-unresolved.
- Application failure: keep the validated provider result and retry only local
  application; do not rebill the provider.

## Settings

Global defaults follow the established global-with-pathway-overrides design:

- `provider_batch_enabled` default `false`;
- `provider_batch_provider`;
- `provider_batch_poll_seconds`;
- `provider_batch_timeout_hours`;
- `provider_batch_max_concurrent_provider_jobs`;
- `provider_batch_max_requests_per_provider_job`;
- `provider_batch_output_retention_seconds`;
- `provider_batch_delete_files_after_import`;
- `provider_batch_allow_pre_acceptance_fallback`;
- `provider_batch_require_recent_calibration`;
- `provider_batch_calibration_max_age_days`.

Operation overrides:

- enabled/disabled;
- maximum records per batch;
- maximum batches per run;
- maximum concurrent provider jobs;
- a configured provider account and model override for the run; credentials are
  never accepted from or returned to the UI;
- batch input/output price per million tokens, or embedding input price per
  million tokens, frozen into the run for estimates and audit;
- auto-selection policy.

Do not introduce independent prompt, confidence, token-budget, or schedule values
inside provider-batch settings. Those remain owned by the corresponding
Knowledge configuration.

## API contract

Add shared endpoints:

- `POST /api/memory/admin/knowledge/operations/preview`
- `POST /api/memory/admin/knowledge/operations/runs`
- `GET /api/memory/admin/knowledge/operations/runs/{run_id}`
- `POST /api/memory/admin/knowledge/operations/runs/{run_id}/sync-status`
- `POST /api/memory/admin/knowledge/operations/runs/{run_id}/pause`
- `POST /api/memory/admin/knowledge/operations/runs/{run_id}/resume`
- `POST /api/memory/admin/knowledge/operations/runs/{run_id}/cancel`
- `POST /api/memory/admin/knowledge/operations/runs/{run_id}/retry`
- `GET /api/memory/admin/knowledge/operations/runs/{run_id}/requests`

The preview endpoint never mutates sources or submits provider work.

Existing operation endpoints remain and call the shared service:

- embedding backfill;
- run Knowledge check;
- hygiene analyze;
- facet backfill.

## Cost and usage

- Estimate from the actual serialized manifest, not a universal average record.
- Use configured provider/model pricing metadata; do not hardcode permanent
  prices in operation code.
- Show synchronous and provider-batch estimates side by side.
- Persist provider-reported usage where available.
- Separate provider execution cost from local retry/import work.
- Label estimates as estimates until provider usage is imported.

## Security and data handling

- Use the existing encrypted provider credentials.
- Never persist API keys in manifests, JSONL, logs, or UI detail.
- Avoid logging source content or complete provider responses.
- Store request hashes and structured error summaries for audit.
- Delete local temporary JSONL immediately after upload.
- Apply configured provider-file deletion/expiry after import.
- Preserve tenant/agent scope in every manifest and source query.
- Admin authentication is required for preview, submit, cancel, retry, and
  request-level inspection.

## UI refactor

Update Knowledge Operations into four connected panels:

### Start operation

- Operation selector.
- Operation mode where hygiene requires it.
- Execution-mode selector filtered by capabilities.
- Records per Batch and Batches per Run.
- Review batch button.

### Review and submit

- Snapshot and exclusions.
- Provider partitions and estimates.
- Calibration comparison.
- Warnings and explicit confirmation.
- Submit action.

### Active operations

- Local and provider status.
- Progress and next poll.
- Pause/cancel/resume actions.
- Sticky provider errors.

### Operation history

- Inputs, requests, outputs, failures, usage, cost, duration, stop reason.
- Provider job IDs and timestamps.
- Expandable request errors without raw sensitive content.
- Retry unresolved and navigate to outputs.

The start button and Active Operations panel must use the same authoritative run
selection logic.

## Tests and acceptance criteria

### Shared orchestration

- Every UI operation has a registered operation adapter.
- Unsupported execution modes are hidden/blocked consistently in UI and API.
- Preview is mutation-free and expires.
- Submission rejects stale previews.
- Finite snapshots are deterministic under shuffled database input.
- Existing endpoints remain backward compatible.
- Synchronous behavior remains unchanged.

### Provider transport

- Synchronous and provider-batch bodies are equivalent apart from transport.
- JSONL is valid and provider limits are enforced before upload.
- Multiple endpoints/models produce separate provider batches under one run.
- Shuffled, duplicate, missing, partial, failed, and malformed provider results
  are handled correctly.
- Restart/redeploy recovers all non-terminal runs from PostgreSQL.
- No worker remains blocked while waiting at the provider.
- Provider files are deleted/expired according to policy.

### Embeddings

- All four tiers are supported.
- Empty sources generate no provider request and are not selected again.
- Oversized inputs follow the shared truncation/token policy.
- Vector count, dimensions, model, and source version are validated.
- Partial success applies only valid vectors.

### Knowledge generation

- Declarative, telemetry, skill, and playbook pathways are covered.
- Existing prompts/models/contracts are used.
- Confidence and activation rules are unchanged.
- Evidence links and source pathways are complete.
- Duplicate result delivery creates no duplicate Knowledge.
- Sources are not consumed before validated application.

### Hygiene

- `analysis_only` uses local asynchronous execution without provider billing.
- Proposal modes batch only frozen eligible clusters.
- Category prompts and structured proposal validation are preserved.
- Proposal import never retires Knowledge directly.
- Auto modes, when enabled, call the shared transactional apply service.

### Facets

- Current governed schema and extraction prompt are used.
- Unsupported facets are rejected.
- Source and facet-schema version changes reject stale results.
- Quality recalculation matches synchronous behavior.

### Operations and recovery

- Pause stops future submission and safely completes current provider jobs.
- Cancel imports partial results and leaves unresolved requests retryable.
- Resume/retry never resubmits already-applied requests.
- Local apply failure retries without another provider charge.
- Credit/rate-limit errors create sticky alerts.
- Active/history panels never show stale or contradictory status.

## Implementation order

The work can be delivered in separate commits/PRs during one implementation run,
but the feature is not complete until all stages below are shipped.

### PR 1 — Schema, state machine, and shared APIs

- Add preview, provider-run, manifest-request, and request-source tables.
- Extend pipeline-run observability.
- Add shared preview/run/status/control endpoints.
- Add operation and provider adapter registries.
- Preserve legacy endpoint wrappers.

### PR 2 — Shared request builders and executors

- Extract current synchronous request builders per operation.
- Add synchronous compatibility executor.
- Add local asynchronous executor.
- Add provider-neutral batch executor.
- Prove request equivalence.

### PR 3 — OpenAI adapter and reconciliation

- JSONL upload/submission/status/results/cancel/file cleanup.
- Short-lived reconciliation jobs and startup recovery.
- Sticky provider failure integration.
- Pause/cancel/resume/retry state transitions.

### PR 4 — Embedding backfill

- All four tiers.
- Input validation and provider-limit partitioning.
- Result mapping and guarded persistence.
- Calibration comparison.

### PR 5 — Facet backfill

- Shared structured request builder.
- Batch result validation against governed facets.
- Guarded update and quality behavior.

### PR 6 — Knowledge generation

- Declarative, telemetry, skill, and playbook pathway adapters.
- Evidence-bundle manifests and source claims.
- Structured parsing, activation, evidence, and idempotent creation/revision.

### PR 7 — Knowledge hygiene

- Local `analysis_only` execution.
- Provider-batch proposal generation.
- Shared proposal import and optional policy-gated transactional apply.

### PR 8 — Complete Operations UI

- Capability-aware execution modes.
- Review/estimate/submit workflow.
- Provider state, controls, history, errors, costs, and output navigation.
- Responsive and accessible states with help tooltips.

### PR 9 — Verification and rollout controls

- Full unit, integration, failure-injection, and UI tests.
- Feature flags and safe defaults.
- Production calibration checklist and operational documentation.

## Rollout

1. Deploy schema and reconciliation with provider submission disabled.
2. Verify synchronous regression suite for every operation.
3. Calibrate embeddings synchronously and through a small provider batch.
4. Test restart, cancellation, expiry, partial output, and local apply retry.
5. Enable larger embedding batches.
6. Calibrate facet extraction against identical samples.
7. Calibrate every Knowledge generation pathway.
8. Enable hygiene proposal batching; keep auto-apply disabled.
9. Enable `automatic` selection only after operation-specific equivalence and
   recovery evidence is approved.

## Final product requirement

Every Knowledge Operation must be executable through one shared operation
framework. Embedding backfill, facet backfill, Knowledge generation, and hygiene
proposal generation may use discounted asynchronous provider batches when the
configured provider supports them. Hygiene `analysis_only` must use asynchronous
local execution because it has no provider request. Synchronous calibration must
remain available. Provider batching may alter transport, latency, and billing,
but it must not alter prompts, models, source selection, validation, Knowledge
contracts, facets, quality, consolidation policy, evidence, lineage, or
transactional behavior. All runs must be previewable, finite, observable,
recoverable after restart, pausable, cancellable, resumable, idempotent, and safe
under partial, duplicate, missing, stale, expired, or failed provider results.
