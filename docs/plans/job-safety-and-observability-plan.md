# Job Safety and Observability

## Shipped safety baseline

- Long-running maintenance jobs use a singleton lease: embedding, facet, and telemetry backfills, hygiene analysis, consolidation, playbook extraction, and all-pathway backlog processing cannot run concurrently with another job of the same type.
- Every backfill is bounded and resumable. Embeddings use provider-native batches; facet and telemetry processing retain their existing bounded limits and idempotency records.
- Provider rate limits and exhausted credits are classified as global job stops, not per-record failures.
- The worker stops the affected job without retry storms, records a `blocked` pipeline-run outcome, and leaves unprocessed source records eligible for a later manual retry.
- A persistent system alert is shown to administrators across the application. Rate-limit alerts expire after the provider retry window; credit/quota alerts remain until an administrator resolves them after fixing billing or quota.

## Job-log next increment

The existing `memory_pipeline_runs` table is the append-only event foundation. The next UI increment should provide a dedicated **Jobs** page with:

1. queued, running, completed, skipped, blocked, and failed status;
2. queue job ID, initiator, start/end times, duration, parameters, progress, and result counts;
3. a link from an active alert to the jobs stopped by it;
4. retry and cancel actions where the job is safely resumable;
5. retention and export controls.

Do not remove the singleton lease or provider-stop alert when adding this UI. The future job model should extend these protections rather than replace them.
