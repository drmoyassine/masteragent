# Firecrawl Service Performance and Memory Optimization

**Status:** Planned investigation; Firecrawl changes are not yet implemented.

**MasterAgent memory incident:** Resolved and under observation. The evidence showed that MasterAgent was not leaking application memory. PostgreSQL had populated several GiB of reclaimable Linux file cache while scanning the 7 GB `interactions` table. MasterAgent itself remained approximately 100–110 MiB, Redis approximately 80 MiB, and PostgreSQL process/anonymous memory was only a few tens of MiB. PostgreSQL shared-memory and container limits were added to the Compose configuration; production observation continues.

## Purpose

Apply the lessons from the MasterAgent incident to the separate Firecrawl stack without guessing, flushing live work, or reducing crawl quality. The objective is to identify the component that owns sustained memory, distinguish process memory from filesystem cache, bound queues and workers, and validate every change with a controlled production rollout.

## Evidence already collected

The VPS-wide Docker snapshot included the following Firecrawl-related services:

| Service | Observed memory | Other observation |
|---|---:|---|
| `management_firecrawl-rabbitmq-1` | ~124 MiB in the later snapshot; an earlier snapshot showed approximately ~880 MiB | Must inspect queue payloads, ready/unacknowledged messages, consumers, and retention. |
| `management_firecrawl-playwright-service-1` | ~132 MiB, with a 4 GiB container limit | Browser concurrency and abandoned contexts remain suspects. |
| `management_firecrawl-nuq-postgres-1` | ~114 MiB | Block I/O was approximately 796 MiB cumulative; inspect database/cache separately. |
| `management_firecrawl-foundationdb-1` | ~31 MiB | Low in the captured snapshot; verify growth over time. |
| `management_firecrawl-redis-1` | ~6 MiB | Low in the captured snapshot; still inspect key and expiry growth. |

The earlier production observation that prompted this plan reported the Firecrawl API as approximately **2.9 GiB** and RabbitMQ as approximately **880 MiB**. Those values are baselines to verify, not conclusions: Docker memory includes file cache, and a single snapshot cannot identify a leak.

## Lessons carried forward from MasterAgent

1. **Identify the owner before changing anything.** Capture all containers during the spike; do not infer that the application process owns aggregate memory.
2. **Separate anonymous/process memory from file cache.** Read each container's cgroup `memory.stat`. Large `file` with small `anon` indicates reclaimable filesystem cache, not a Python/Node heap leak.
3. **Treat Docker block I/O as cumulative.** A large block-I/O number is not an active operation or current RAM usage.
4. **Capture evidence before restart.** Restarting can clear caches and hide the workload that caused the growth.
5. **Bound queues and completed history.** BullMQ completed jobs previously grew to 1.77 million records and consumed Redis memory; retention must be explicit and bounded.
6. **Use bounded, resumable maintenance.** Every cleanup or backfill needs a batch limit, maximum batches/records, checkpoint, pause/cancel behavior, provider-stop handling, and visible run status.
7. **Increase shared memory before maintenance.** PostgreSQL vacuum failed with a 64 MiB Docker `/dev/shm`; Firecrawl services need equivalent checks before browser/database maintenance.
8. **Do not use restarts or cache flushing as the fix.** They are diagnostic/recovery actions only; the permanent fix is workload, retention, concurrency, and memory-bound control.

## Investigation plan

### 1. Establish a spike-time baseline

Capture at least five samples, 30–60 seconds apart, during growth:

- `docker stats` for every Firecrawl container;
- cgroup `memory.current` and `memory.stat` (`anon`, `file`, `shmem`, `slab`);
- process/thread counts and open file descriptors;
- CPU, network, and block I/O deltas rather than cumulative totals;
- Firecrawl API, worker, Playwright, RabbitMQ, Redis, and database logs.

For each sample record the active workload: crawl count, browser pages, URLs, retries, failed jobs, queue age, and response payload size.

### 2. Inspect RabbitMQ safely

Record, without purging:

- queue names and message counts;
- ready versus unacknowledged messages;
- oldest message age;
- consumer and channel counts;
- dead-letter and retry queues;
- message payload size and persistence mode;
- publisher/consumer rates.

Classify queues before changing retention. Only completed/expired work may be removed; active, retrying, delayed, or unacknowledged work must remain recoverable.

### 3. Inspect Firecrawl API and browser workers

Determine whether memory is:

- Node/JS heap (`anon` growth, heap snapshots, GC pressure);
- browser processes or leaked Playwright contexts/pages;
- response/document buffers and unbounded concurrency;
- filesystem cache from downloaded pages or artifacts;
- retry storms caused by timeouts or upstream rate limits.

Measure active browser contexts, pages per context, crawl concurrency, request timeout, retry count, maximum document size, screenshot/PDF retention, and worker restart count.

### 4. Inspect Firecrawl persistence services

For NUQ PostgreSQL, FoundationDB, and Redis, capture:

- container memory split (`anon` versus `file`);
- database/table/index sizes and dead tuples;
- active queries and query duration;
- queue/key counts, expiry coverage, and largest keys;
- write/read rates and compaction/checkpoint activity.

Do not assume a low Redis dataset means the Firecrawl API is healthy, and do not assume a large PostgreSQL file cache is a leak.

## Remediation design

### Queue and retention controls

- Configure finite retention for completed and failed jobs.
- Add dead-letter handling and maximum retry counts.
- Add queue age and depth alerts.
- Bound payload size; store large documents/artifacts outside queue messages.
- Make cleanup resumable, idempotent, and safe to stop at a checkpoint.

### Concurrency and backpressure

- Start with conservative API, worker, and browser concurrency.
- Enforce a global in-flight crawl/page limit.
- Apply per-domain and provider rate limits.
- Reject or defer new work when queue age, memory, or browser counts exceed limits.
- Ensure timeouts close pages, contexts, streams, and HTTP responses.

### Memory limits

- Set explicit per-service memory limits only after measuring normal peaks.
- Keep a dedicated shared-memory allowance for Playwright and database operations.
- Use restart policies only as a safety net, with alerts and a reason code.
- Prefer reclaimable cache limits and workload reduction over indiscriminate host cache flushing.

### Observability

Add a service-level dashboard or job log containing:

- current/peak memory and CPU;
- anonymous versus file cache;
- queue depth, oldest item, ready/unacknowledged counts;
- active crawls, browser contexts/pages, retries, failures, and timeouts;
- database and Redis sizes;
- deployment/restart history;
- rate-limit, credit-exhaustion, and backpressure events.

Alerts must be sticky and visible when memory limits, provider rate limits, queue age, or repeated worker failures stop work.

## Controlled rollout

1. Run an analysis-only baseline for a representative crawl sample.
2. Apply queue retention and concurrency changes to a staging or bounded production slice.
3. Observe for at least one normal workload cycle and one peak cycle.
4. Compare crawl success, latency, retries, content completeness, memory slope, CPU, and queue age with the baseline.
5. Roll back one control at a time if correctness or latency regresses.
6. Only then raise limits or enable broader concurrency.

## Acceptance criteria

- The component responsible for sustained memory growth is identified with cgroup/process evidence.
- No queue purge or destructive cleanup occurs without classifying active work.
- Completed/failed queue retention is bounded and verified over time.
- Browser contexts/pages and retry behavior remain bounded.
- Each service has an explicit memory/shared-memory policy and rollback procedure.
- Crawl correctness, document parsing, retries, and rate-limit handling do not regress.
- Memory slope remains stable during representative and peak workloads.
- MasterAgent remains in the observation window with no renewed unexplained anonymous-memory growth.

## Deferred implementation tasks

- Build the Firecrawl spike sampler and persistent jobs/resource log.
- Add RabbitMQ/Redis/NUQ inspection commands and dashboards.
- Add service-specific environment controls for concurrency, retention, payload size, and memory limits.
- Add automated tests for queue cleanup, retry/dead-letter behavior, browser cleanup, and safe shutdown.
- Schedule a production observation review after the first controlled rollout.
