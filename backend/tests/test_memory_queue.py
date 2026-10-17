"""
test_memory_queue.py — BullMQ ingestion-queue unit tests (TASK-261).

Exercises memory.queue._process_bulk_job / _handle_failed against a mock Job
(no worker process, no real pipeline):
  1. The ingestion API only ENQUEUES — no synchronous pipeline execution.
  2. A picked-up job dispatches to its registered spec handler.
  3. An unknown job name degrades to a warning + default rpm — no crash.
  4. A provider hard-stop completes the job as blocked; the handler never runs.
  5. A final-attempt failure stamps the interactions DLQ row, then re-raises.
  6. _handle_failed stamps the sticky alert on the FINAL attempt only.

The gates (active_provider_stop / active_budget_block), the pipeline-run
logger, and the DB context are patched — all are function-level imports inside
_process_bulk_job, so patching the owning module attribute is authoritative.
The `base_url` fixture dependency guarantees the hermetic stack (and its env)
is up before any memory.* import resolves.
"""
import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memory.queue import JOBS


class MockJob:
    """Duck-typed bullmq Job: the queue touches id / name / data / opts /
    attemptsMade only."""

    def __init__(self, name, data, attempts=1, attempts_made=0):
        self.id = "test-job-1"
        self.name = name
        self.data = data
        self.opts = {"attempts": attempts}
        self.attemptsMade = attempts_made


@pytest.mark.asyncio
async def test_agent_interaction_ingestion_queues_job(base_url):
    """The ingestion endpoint path must enqueue a BullMQ job and answer
    202/pending without running the pipeline synchronously."""
    from memory.agent import ingest_interaction
    from memory_system.store.models import InteractionCreate

    req_body = InteractionCreate(
        interaction_type="test-event",
        content="Testing asynchronous decoupling",
        primary_entity_type="contact",
        primary_entity_id="123",
    )
    mock_agent = {"id": "agent-1", "name": "Test Agent"}
    mock_response = MagicMock()

    with patch("memory.agent.check_rate_limit", return_value=True), \
         patch("memory.agent.get_memory_db_context"), \
         patch("memory.queue.Queue.add", new_callable=AsyncMock) as mock_queue_add, \
         patch("memory.agent.log_audit"), \
         patch("memory.agent.cache_interaction"), \
         patch("memory.agent.grant_entity") as mock_grant:
        response = await ingest_interaction(body=req_body, response=mock_response, agent=mock_agent)

    assert response.status == "pending"
    assert mock_response.status_code == 202

    mock_queue_add.assert_called_once()
    args = mock_queue_add.call_args.args
    assert args[0] == "ingest_interaction"
    assert "interaction_id" in args[1]
    assert args[2]["backoff"]["type"] == "exponential"
    # TASK-259 item 6 follow-on: ingestion (not the write APIs) auto-claims.
    mock_grant.assert_called_once_with("agent-1", "contact", "123")


@pytest.mark.asyncio
async def test_bullmq_worker_dispatches_registered_handler(base_url):
    """A picked-up job dispatches to its registered spec handler; non-singleton
    jobs pass run_id=None."""
    from memory.queue import _process_bulk_job

    job = MockJob("ingest_interaction", {"interaction_id": "ix-1"}, attempts=3)
    handler = AsyncMock(return_value={"ok": 1})
    spec = dataclasses.replace(JOBS["ingest_interaction"], handler=handler)

    with patch.dict("memory.queue.JOBS", {"ingest_interaction": spec}), \
         patch("services.job_safety.active_provider_stop", return_value=None), \
         patch("services.budget.active_budget_block", return_value=None), \
         patch("services.config_helpers.get_llm_config", return_value={}), \
         patch("memory_system.store.writes.log_pipeline_run"), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        result = await _process_bulk_job(job, "token")

    assert result is None
    handler.assert_awaited_once_with(job, None)


@pytest.mark.asyncio
async def test_worker_unknown_job_name_does_not_crash(base_url):
    """An unregistered job name logs a warning and completes (default rpm)."""
    from memory.queue import _process_bulk_job

    job = MockJob("no_such_job", {})
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await _process_bulk_job(job, "token")

    assert result is None


@pytest.mark.asyncio
async def test_provider_stop_blocks_job_cleanly(base_url):
    """A provider hard-stop completes the job as a clean blocked row — the
    handler never runs and BullMQ is not asked to retry."""
    from memory.queue import _process_bulk_job

    job = MockJob("ingest_interaction", {"interaction_id": "ix-1"})
    handler = AsyncMock()
    spec = dataclasses.replace(JOBS["ingest_interaction"], handler=handler)

    with patch.dict("memory.queue.JOBS", {"ingest_interaction": spec}), \
         patch("services.job_safety.active_provider_stop",
               return_value={"code": "provider_disabled", "message": "all providers disabled"}), \
         patch("memory_system.store.writes.log_pipeline_run") as mock_log:
        result = await _process_bulk_job(job, "token")

    assert result == {"status": "blocked", "reason": "provider_disabled"}
    handler.assert_not_awaited()
    mock_log.assert_called_once()  # blocked run recorded


@pytest.mark.asyncio
async def test_dead_letter_queue_failure_logic(base_url):
    """A final-attempt failure stamps the interaction row failed via the DLQ
    SQL, records a failed pipeline run, then re-raises for BullMQ."""
    from memory.queue import _process_bulk_job

    async def _boom(_job, _run_id):
        raise RuntimeError("Simulated API Down")

    job = MockJob("ingest_interaction", {"interaction_id": "bad-id"}, attempts=1)
    spec = dataclasses.replace(JOBS["ingest_interaction"], handler=_boom)

    # get_memory_db_context is a @contextmanager: call → ctx object, `with`
    # → conn. return_value stands in for the ctx object; __enter__.return_value
    # is the yielded conn.
    mock_db = MagicMock()
    mock_cursor = mock_db.__enter__.return_value.cursor.return_value

    with patch.dict("memory.queue.JOBS", {"ingest_interaction": spec}), \
         patch("services.job_safety.active_provider_stop", return_value=None), \
         patch("services.budget.active_budget_block", return_value=None), \
         patch("memory_system.store.writes.log_pipeline_run"), \
         patch("core.storage.get_memory_db_context", return_value=mock_db), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RuntimeError, match="Simulated API Down"):
            await _process_bulk_job(job, "token")

    dlq_calls = [c for c in mock_cursor.execute.call_args_list
                 if "UPDATE interactions SET status = 'failed'" in c.args[0]]
    assert len(dlq_calls) == 1
    assert dlq_calls[0].args[1] == ('{"fatal_error": "Simulated API Down"}', "bad-id")


def test_handle_failed_alerts_only_on_final_attempt(base_url):
    """TASK-256 residual — the sticky queue-failure alert stamps on the FINAL
    attempt only; intermediate attempts return before touching the DB."""
    from memory.queue import _handle_failed

    # Non-final: job allows 3 attempts, this is attempt 1 → no DB access at all.
    early_job = MockJob("generate_memory", {}, attempts=3, attempts_made=0)
    with patch("core.storage.get_memory_db_context") as mock_db:
        _handle_failed(early_job, RuntimeError("attempt 1 of 3"))
    mock_db.assert_not_called()

    # Final: single-attempt job → alert upserted with the stable code.
    final_job = MockJob("generate_memory", {}, attempts=1, attempts_made=0)
    mock_db = MagicMock()
    mock_cursor = mock_db.__enter__.return_value.cursor.return_value
    with patch("core.storage.get_memory_db_context", return_value=mock_db):
        _handle_failed(final_job, RuntimeError("exhausted"))

    call = mock_cursor.execute.call_args
    assert "INSERT INTO memory_system_alerts" in call.args[0]
    assert "ON CONFLICT (code) DO UPDATE" in call.args[0]
    assert call.args[1][0] == "queue_job_failed:generate_memory"
    assert call.args[1][1] == "Queue job 'generate_memory' exhausted its retries"
