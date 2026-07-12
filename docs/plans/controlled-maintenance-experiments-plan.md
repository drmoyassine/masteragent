# Controlled Maintenance Experiments and Dry-Run Plan

## Purpose

Provide a safe, repeatable way to calibrate maintenance workloads before enabling production-scale processing. The same controls must work for embedding backfill, knowledge generation, hygiene analysis, and governed-facet backfill.

The system must never require an operator to choose between “do nothing” and “drain the entire backlog.” Every maintenance action must support a bounded experiment first.

## Current gaps

The current UI actions are not sufficiently bounded:

- Embedding backfill queues an unbounded resumable run. The worker uses provider batches of up to 25 records, but the UI cannot set a maximum record count or batch count.
- “Run now” performs one knowledge-generation pass; “Process backlog” can run up to 50 generation rounds. Neither exposes a run limit.
- “Analyze now” scans the eligible knowledge corpus in one hygiene run. It has no record or cluster limit.
- Facet backfill processes up to 1,000 records per invocation, but the UI does not expose that limit or show a controlled repeat count.
- Recent runs show queue status but not requested limits, progress, throughput, cost, or stop reason.

## Product behavior after implementation

Every maintenance action opens a run-control dialog before queueing work. The dialog shows:

- operation name and scope;
- eligible-record estimate;
- dry-run or apply mode;
- records per internal batch;
- maximum records for this run;
- maximum batches or rounds;
- optional category/entity filters;
- estimated provider calls and token range when available;
- current provider-stop state and queue capacity;
- an explicit confirmation before queueing.

The defaults are deliberately small and calibration-oriented. An operator must explicitly choose a larger limit for production processing.

## Shared run-control contract

Add a common `MaintenanceRunOptions` structure used by all four operations:

```json
{
  "dry_run": true,
  "batch_size": 25,
  "max_records": 1000,
  "max_batches": 40,
  "max_rounds": 1,
  "category": null,
  "entity_type": null,
  "stop_on_error_rate": 0.10,
  "stop_on_provider_stop": true
}
```

Rules:

- `max_records`, `max_batches`, and `max_rounds` are hard upper bounds.
- The first reached limit stops the run cleanly.
- A missing limit is not interpreted as unlimited for user-triggered runs; it uses a safe configured default.
- Scheduled production jobs may use a separately configured production limit.
- The worker records the requested options and the effective limits in the run log.
- Repeating a run is resumable and idempotent; already-current records are skipped.
- Only one singleton run of the same operation may execute at a time.
- Provider-stop, credit exhaustion, rate-limit, database failure, or excessive error rate stops the run without corrupting records.

## Operation-specific behavior

### A. Embedding backfill

Backend changes:

- Accept run options in the queue payload.
- Pass `batch_size` and `max_records` into `run_embedding_backfill`.
- Preserve the hard provider API cap of 25 inputs per request unless explicitly and safely increased.
- Return processed, succeeded, failed, skipped, batches, elapsed time, and per-tier counts.
- Add a preview endpoint that estimates stale records and eligible records by tier before queueing.

UI defaults:

- dry run/preview first;
- batch size: 25 records;
- max records: 1,000;
- max batches: 40;
- production drain: a separate explicit action, not the calibration default.

Dry-run semantics:

- Query and sample eligible records.
- Estimate token volume and provider calls.
- Do not call the embedding provider and do not update vectors.

### B. Knowledge generation

Backend changes:

- Extend `run-knowledge-check` with `max_rounds`, `max_records`, and `dry_run`.
- Propagate limits into declarative, playbook, skill, and telemetry pathways.
- Keep `Run now` as one bounded round.
- Replace the current unqualified backlog drain with a dialog-driven bounded drain.
- Count every generated, skipped, failed, and provider-blocked item.

UI defaults:

- Run now: one round, maximum one batch per entity type.
- Calibration backlog: one to three rounds.
- Production backlog: explicit operator choice after calibration.

Dry-run semantics:

- Count eligible confirmed intelligence, telemetry windows, and playbook clusters.
- Do not call generation LLMs.
- Do not create or update knowledge.

### C. Hygiene analysis and consolidation proposals

Backend changes:

- Add `max_records`, `max_clusters`, and optional category filters to the analyze request.
- Apply limits during candidate loading, not after loading the complete corpus.
- Preserve deterministic ordering so repeated samples are reproducible.
- `analysis_only` must never call the LLM or mutate knowledge.
- `proposal_only` may call the LLM but must not apply changes.
- Store the limits, sample scope, embedding version, thresholds, and mode in the hygiene run snapshot.

UI defaults:

- analysis-only;
- one category or a 1,000–5,000 record sample;
- maximum 100 candidate clusters;
- no automatic application.

The UI must display records scanned, compatible records, incompatible records, clusters found, clusters skipped, and elapsed time.

### D. Governed-facet backfill

Backend changes:

- Accept `batch_size` and `max_records` in the trigger payload.
- Preserve the current idempotent rule: only active records with missing or empty facets are eligible.
- Return processed, enriched, skipped, failed, and provider-stop counts.
- Stop safely when the configured error-rate threshold is exceeded.

UI defaults:

- batch size: 25;
- max records: 100 or 250;
- one invocation per calibration run.

The operator can repeat the run after reviewing the previous result. Concurrent facet backfills remain blocked by the singleton lock.

## Progress and observability

Extend `memory_pipeline_runs` and the job log with:

- run ID and operation;
- origin (`manual`, `scheduled`, `admin`, or `creation_time`);
- actor;
- requested and effective limits;
- dry-run flag;
- started, updated, and finished timestamps;
- records discovered, processed, succeeded, failed, skipped;
- batches/rounds completed;
- provider calls, token estimates, and rate-limit events when available;
- current cursor/checkpoint;
- stop reason;
- resume information.

The UI should show a sticky provider-stop/error banner and a live progress row. Refreshing the page must not lose the run state.

## Stop, pause, and resume

Implement:

- `pause` request: finish the current atomic record/batch, then stop;
- `cancel` request: stop after the current safe unit and mark the run cancelled;
- automatic stop on provider credit exhaustion, rate limit, repeated failures, database errors, or memory-pressure guard;
- resume from the persisted checkpoint without reprocessing successful records.

No source records may be retired or consolidated during a failed or cancelled run. Analysis artifacts may remain, clearly marked incomplete.

## Calibration procedure

1. Back up PostgreSQL and confirm Redis and disk headroom.
2. Confirm the shared embedding model/version and provider quota.
3. Disable creation-time consolidation and all automatic hygiene application.
4. Run a dry preview for each operation.
5. Run a small bounded sample:
   - embeddings: 1,000 records;
   - generation: 1 round;
   - hygiene analysis: 1,000–5,000 records;
   - facets: 100–250 records.
6. Review throughput, memory, Redis growth, provider calls, token estimates, failures, and result quality.
7. Increase limits gradually only when the previous run is healthy.
8. Run proposal-only hygiene and review representative proposals from all five categories.
9. Enable manual consolidation for approved proposals.
10. Enable automatic modes only after production evidence supports the policy gates.

## Acceptance tests

- A run cannot exceed `max_records`, `max_batches`, or `max_rounds`.
- A dry run makes no provider calls and no data mutations.
- A provider stop produces a visible sticky error and a resumable stopped run.
- Repeating a completed run does not reprocess current records.
- Two concurrent runs of the same singleton operation are safely rejected.
- A failed batch does not roll back successful prior batches or corrupt source records.
- Hygiene analysis never retires or updates knowledge.
- Proposal-only never applies a merge.
- Facet backfill updates only eligible active records.
- Progress and stop reasons survive page refresh and service restart.
- All run limits and settings are visible in the audit record.

## Rollout gates

Do not expose an unbounded “process all” action until:

- bounded runs are verified in production;
- queue retention and Redis memory are controlled;
- provider-stop handling has been observed successfully;
- per-tier embedding coverage is measurable;
- representative hygiene proposals have been manually reviewed;
- rollback and lineage checks pass.

## Implemented control surface

The first implementation slice now provides bounded queue payloads for embedding
backfill, knowledge generation, hygiene analysis, and facet backfill. The
maintenance tab shows a persistent live-status card that refreshes every five
seconds, including the latest state, checkpoint progress, stop reason, and the
requested token/cost estimate where one is available. The embedding card also
shows a pre-run estimate based on the selected record and provider batch limits.

Pause and cancel are persisted in `memory_job_controls` and are checked between
provider batches, generation rounds, hygiene clusters, and facet records. The
Resume action clears the stop flag; the operator then starts the next bounded
run, which safely continues from the idempotent stale/missing-record queries.
Provider credit and rate-limit stops remain separate sticky system alerts.

This slice intentionally does not expose an unbounded “process all” button. A
full dry-run preview dialog, exact provider billing reconciliation, and a
central historical jobs dashboard remain follow-up work; the run log stores the
requested limits and estimates so those features can be added without changing
worker semantics.

Operationally, the maintenance status API is available at
`GET /api/memory/pipeline-runs` and `GET /api/memory/maintenance-controls`.
Pause, cancel, and clear-stop commands use
`POST /api/memory/maintenance-controls/{job}/{command}`. The UI wraps these
endpoints, so operators normally do not need to call them directly.
