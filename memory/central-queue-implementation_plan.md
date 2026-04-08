# Complete Redis BullMQ Pipeline Architecture

> [!NOTE]
> **STATUS: FULLY IMPLEMENTED ✅**
> All 5 Sprints within this architecture have been successfully executed, verified via automated Pytest suites, and deployed to the GitHub repository.


The goal is to transition the entire Memory System's generation surface area from an assorted mix of synchronous background threads, blocking HTTP workers, and `asyncio.create_task()` background jobs into a unified, distributed Redis/BullMQ task queue.

This guarantees that **whether on-schedule or on-demand, no LLM invocations happen outside the queue**. The queue is the *only* component authorized to contact LLM Providers, ensuring absolute adherence to Rate Limit specifications (RPM), auto-retrying failures, shielding the FastAPI Web Server from I/O lockup, and providing a strictly deterministic sequence of operations.

## Enterprise Quality Standards
To ensure a bulletproof, enterprise-grade deployment, this implementation will enforce:
- **Dead Letter Queues (DLQ)**: Jobs failing beyond maximum retries must be sequestered for manual review, not silently dropped.
- **Graceful Shutdowns**: Workers must catch SIGINT/SIGTERM and drain or pause current executions gracefully to prevent corrupted entity context states.
- **Transactional Enqueueing**: Database commits MUST succeed before a job is pushed to Redis to prevent ghost jobs.
- **Observability**: Job execution times, failure rates, and RPM throttling metrics must be logged systematically.

---

## Blueprint & Sprints

### Phase 1: Core Worker Infrastructure (Sprint 1) ✅ COMPLETE
Establish the resilient task execution environment.

1. **Worker Router (`backend/memory/queue.py`)**
   - Expand `_process_bulk_job(job, token)` to handle scalable `job.name` routing:
     - `case "ingest_interaction" | "reprocess"`: `await process_interaction(...)`
     - `case "generate_memory"`: `await _generate_memory_for_entity(...)`
     - `case "generate_insight"`: `await compact_entity(...)`
     - `case "generate_lesson"`: `await run_lesson_check(...)` or `promote_to_lesson(...)`
   - Implement dynamic RPM rate limiting dynamically resolved from provider configs.
2. **Resiliency & Telemetry (`backend/memory/queue.py`)**
   - Wrap job execution in robust `try/except` bounds. Differentiate between `RateLimitException` (retryable) and `DataIntegrityException` (fatal).
   - Hook into BullMQ event listeners: `on('completed')`, `on('failed')`.
3. **Graceful Shutdown (`backend/server.py` & `queue.py`)**
   - Explicitly handle `await memory_bulk_worker.close()` during FastAPI application teardown, permitting active jobs up to 30 seconds to flush.

---

### Phase 2: Asynchronous Ingress (Sprint 2) ✅ COMPLETE
Decouple API and Webhook interfaces from processing logic.

1. **API Ingestion (`backend/memory/agent.py`)**
   - Strip `parse_document()` and `generate_embedding()` out of the `POST /interactions` synchronous block.
   - Restrict the endpoint to fast DB insertion (`status='pending'`).
   - Add transaction safety hook: Commit PG transaction, then invoke BullMQ: 
     `await memory_bulk_queue.add("ingest_interaction", {"interaction_id": id}, {"attempts": 3, "backoff": {"type": "exponential", "delay": 2000}})`
   - Change response protocol: Return `HTTP 202 Accepted`.
2. **Webhook Ingestion (`backend/memory/webhooks.py`)**
   - Add the identical enqueue call right after the `INSERT` query finishes inside `POST /webhooks/inbound/{source_id}`. This upgrades Webhooks from 'batch nightly' to 'real-time asynchronous' processing.

---

### Phase 3: Cron & Background Decoupling (Sprint 3) ✅ COMPLETE
Eliminate unmanaged native `asyncio` execution loops.

1. **Daily Runner Iterator (`backend/memory_tasks.py`)**
   - Refactor `run_daily_memory_generation()`, `run_compaction_check()`, and `run_lesson_check()`.
   - Strip out direct LLM calls from the scheduler loop. The iterator should query the DB and strictly yield queue drops over the wire: 
     `await memory_bulk_queue.add("generate_memory", {"entity_type": e, "entity_id": i}, {"priority": 5})`
2. **Admin Triggers (`backend/memory/admin.py`)**
   - Update manual synchronous trigger endpoints (`/trigger/compact`, etc.) to directly drop bounded payloads into BullMQ and return 200 instantly.
   - Refactor `/insights/{insight_id}/promote` so it drops `"promote_to_lesson"` jobs sequentially instead of spawning detached `asyncio.create_task()` threads.

---

### Phase 4: Drift Recovery & DLQ (Sprint 4) ✅ COMPLETE
Build structural safeguards against systemic failures.

1. **The Orphan Sweeper (`backend/memory_tasks.py`)**
   - Add a lightweight daily sweeping function to the scheduler loop. 
   - Detect Interactions that have been stuck in `status='pending'` for over 6 hours (indicating a Redis eviction or Worker hard crash).
   - Re-enqueue these silently.
2. **Dead Letter Queue Handling**
   - If a job hits its exponential retry limit (e.g., 3 failed attempts), update its DB status from `pending` -> `failed` and populate the `processing_errors` JSON column with the stack trace for UI surfacing.

---

### Phase 5: Quality Assurance & Test Suite (Sprint 5) ✅ COMPLETE
Guarantee stability and regression-prevention using automated testing pipelines.

1. **Static Type Checking (Pyright)**
   - Enforce strict typing on `memory_bulk_queue.add()` payload dictionaries to prevent runtime key errors inside the worker.
   - Use `TypedDict` or `Pydantic` schemas for BullMQ job payload data definitions.
2. **Unit & Integration Testing (Pytest)**
   - **Mocks**: Introduce unit tests that patch `memory_bulk_queue.add` using `unittest.mock` to verify that `POST /interactions`, Webhooks, and Admin triggers successfully queue jobs without executing them.
   - **Worker Tests**: Abstract the `_process_bulk_job` inner logic so it can be invoked synchronously in `pytest` to validate state transformations.
   - **Database State**: Assert that records transition properly from `pending` to `done` or `failed` in local test databases.
3. **Frontend E2E (Vitest / Playwright)**
   - If applicable, implement tests ensuring that the UI handles HTTP 202 gracefully, rendering a "Processing" state until a polling sequence retrieves the final completed Interaction or Memory.

---

## User Review Required

> [!WARNING]
> By rendering `POST /interactions` asynchronous, eventual consistency is introduced. When a user or agent submits data, ephemeral querying (for vector embeddings) will miss this data for ~1–5 seconds while the queue churns. 
> Does your user interface (UI) or Agent execution flow gracefully handle a momentary loading/processing delay for newly submitted Vision bindings?

> [!IMPORTANT]
> A critical decision regarding BullMQ execution: Are you comfortable continuing with `concurrency=1` in your single Worker instance to guarantee 100% precision in RPM throttling, or do you have plans to scale Workers horizontally (which would require distributed Redis token-bucket rate limiting instead of native asyncio blocks)?

## Verification Plan

### CI/CD Pipeline Gates
- **Pyright**: Zero diagnostic errors allowed in `backend/memory` core loop.
- **Pytest**: Achieve 100% coverage on `queue.py` and `agent.py` route handlers. Running `pytest -v tests/memory_queue_test.py` must pass.

### System Integration Acceptance Tests
- **Scale & Throttling (E2E)**: Push 100 interaction payloads via bulk Admin UI. Assert that BullMQ spaces them out dynamically without API lockups.
- **Job Tolerance (E2E)**: Intentionally use invalid mock LLM credentials. Ensure `pytest` asserts the database status flags the job as `failed` after exactly 3 retries.
