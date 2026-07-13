# Provider Batch Processing for Maintenance Backfills

## Objective

Reduce maintenance cost and provider pressure by using asynchronous provider batch APIs for eligible, non-interactive backfill work while preserving the existing prompts, models, validation rules, checkpoints, lineage, and database semantics.

The first provider adapter is OpenAI Batch. The design must remain provider-neutral so another provider can be added without changing job implementations.

## Scope

### Eligible operations

- Embedding backfill across interactions, memories, intelligence, and knowledge.
- Governed facet backfill.
- Scheduled hygiene analysis and proposal generation.
- Other explicitly asynchronous maintenance jobs approved later.

### Excluded operations

- Manual consolidation preview and apply.
- Interactive document or knowledge-draft generation.
- Creation-time evidence routing.
- Any operation requiring an immediate response.

## Non-negotiable compatibility rule

Batch mode changes only request transport and provider billing. It must not change:

- Prompt text or prompt-template resolution.
- Model selection or structured response schema.
- Category-specific validation.
- Source-version checks.
- Idempotency behavior.
- Checkpoint and pause/cancel semantics.
- Lineage, audit, or transactional application rules.

The same request builder must produce the payload for synchronous and provider-batch execution.

## Execution model

```text
maintenance job selects bounded records
        ↓
shared request builder creates deterministic requests
        ↓
synchronous executor OR provider-batch executor
        ↓
result adapter maps custom_id → source record
        ↓
existing parser, validator, checkpoint, and writer
```

The provider batch is never allowed to write directly to the database. Results are validated and applied by the existing job code.

## Provider-neutral interface

Add an adapter equivalent to:

```python
batch_provider.submit(requests, endpoint, model, metadata) -> BatchHandle
batch_provider.status(handle) -> BatchStatus
batch_provider.results(handle) -> Iterable[BatchResult]
batch_provider.cancel(handle) -> BatchStatus
```

The adapter must expose capability checks, maximum request limits, expiry behavior, and whether output order is guaranteed. The core job must not contain OpenAI-specific HTTP calls.

## Request identity and safety

Every request must include a deterministic `custom_id` containing:

- Operation name;
- Source record ID;
- Source version or update timestamp;
- Embedding/model/prompt version;
- Attempt number.

Persist a request manifest before submission. A result may be applied only if:

- The custom ID exists in the manifest;
- The source still exists and has the expected version;
- The request has not already been applied;
- The provider result passed schema and safety validation.

Duplicate results must be safely ignored. A missing result must remain retryable.

## OpenAI implementation

OpenAI Batch accepts a JSONL input file and processes requests asynchronously within the supported completion window. It supports embeddings and chat-completion endpoints. Embedding batches must respect the provider’s documented maximum of 50,000 inputs per batch.

Implement:

1. JSONL serialization using the existing embedding and LLM request payloads.
2. File upload with batch purpose.
3. Batch creation and persisted provider batch ID.
4. Polling with bounded backoff.
5. Output and error-file retrieval.
6. `custom_id` result mapping.
7. Per-request success/failure handling.
8. Batch expiration, cancellation, and partial-result recovery.

The configured records-per-batch remains an application safety limit and may be lower than the provider maximum.

## Settings

Add global maintenance settings:

- `maintenance_execution_mode`: `synchronous | provider_batch | automatic`.
- `maintenance_batch_provider`: provider identifier.
- `maintenance_provider_batch_max_requests`.
- `maintenance_provider_batch_poll_seconds`.
- `maintenance_provider_batch_timeout_hours`.
- `maintenance_provider_batch_fallback_enabled`.
- `maintenance_provider_batch_max_concurrent_batches`.

Defaults must remain synchronous until production calibration is complete. `automatic` may select provider batch only for eligible non-interactive jobs and only when the adapter reports support.

## Run and audit records

Extend pipeline-run observability with:

- Execution mode and provider.
- Provider batch ID and input/output/error file IDs.
- Request count, completed count, failed count, and missing count.
- Submission, polling, completion, expiry, and cancellation timestamps.
- Estimated and actual input/output tokens and cost when available.
- Prompt/model/embedding versions.
- Manifest checksum.
- Fallback reason, if synchronous fallback occurred.

The existing live status card must show provider batch state without presenting a completed provider batch as an active local worker.

## Pause, cancel, resume

- Pause stops submission of the next provider batch and allows the current batch to finish or expire.
- Cancel requests provider cancellation when supported, then marks unresolved requests safely retryable.
- Resume creates a new bounded batch from the persisted manifest/checkpoint and never resubmits already-applied records.
- Provider outages, rate limits, credit exhaustion, and expiry stop the run safely and create the existing sticky system alert.

## Cost and calibration workflow

1. Run synchronous dry-run on a small sample.
2. Run provider-batch dry-run on an equivalent sample.
3. Compare latency, success rate, token counts, cost, and result equivalence.
4. Start with `provider_batch` only for embeddings.
5. Expand to facet and hygiene LLM jobs after result validation.
6. Enable `automatic` only after production proposals and failure recovery are reviewed.

The UI must show that provider batch processing is asynchronous and may take up to the provider’s completion window; it must not imply immediate completion.

## Tests and acceptance criteria

- Synchronous and batch request payloads are byte-equivalent apart from transport fields.
- Prompt versions and model settings are preserved.
- Results map correctly when provider output is shuffled.
- One failed request does not discard successful requests.
- Duplicate result delivery is idempotent.
- Stale source versions are rejected without mutation.
- Pause, cancel, resume, expiry, and provider failure are recoverable.
- Provider batch unsupported → configured synchronous fallback.
- Credit/rate-limit stop creates a sticky alert and retires no source record.
- Embedding batch cap and configured application limits are enforced.
- Manual preview/apply never uses provider batch mode.
- Existing maintenance UI reports the latest run consistently in the start and active-operation panels.

## Implementation order

1. Fix and test run-state selection and stale-run handling in the operations UI.
2. Add schema and run-observability fields additively.
3. Add provider-neutral adapter and synchronous compatibility adapter.
4. Implement OpenAI embedding batch transport.
5. Add result validation, checkpointing, and recovery.
6. Add batch controls and cost/status UI.
7. Implement chat-completion batch transport for eligible scheduled jobs.
8. Calibrate in production with small samples before enabling `automatic`.
