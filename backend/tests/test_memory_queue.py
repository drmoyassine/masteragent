import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_agent_interaction_ingestion_queues_job():
    """Verify that hitting the interactions API endpoint enqueues a job without synchronous execution"""
    from memory.agent import ingest_interaction
    from memory_models import InteractionCreate

    # Mock dependencies
    req_body = InteractionCreate(
        interaction_type="test-event",
        content="Testing asynchronous decoupling",
        primary_entity_type="user",
        primary_entity_id="123"
    )
    
    mock_agent = {"id": "agent-1", "name": "Test Agent"}
    mock_response = MagicMock()
    
    with patch("memory.agent.check_rate_limit", return_value=True):
        with patch("memory.agent.get_memory_db_context") as mock_db:
            with patch("memory.queue.Queue.add", new_callable=AsyncMock) as mock_queue_add:
                with patch("memory.agent.log_audit"):
                    with patch("memory.agent.cache_interaction"):
                        # Execute API route seamlessly
                        response = await ingest_interaction(body=req_body, response=mock_response, agent=mock_agent)
                        
                        assert response.status == "pending"
                        assert mock_response.status_code == 202
                        
                        # Asset BullMQ received payload
                        mock_queue_add.assert_called_once()
                        args, kwargs = mock_queue_add.call_args
                        assert args[0] == "ingest_interaction"
                        assert "interaction_id" in args[1]
                        assert "exponential" in args[2]["backoff"]["type"]


@pytest.mark.asyncio
async def test_bullmq_worker_router():
    """Verify worker parses job payloads properly and branches to orchestrators"""
    from memory.queue import _process_bulk_job
    
    class MockJob:
        def __init__(self, name, data):
            self.id = "test-job-123"
            self.name = name
            self.data = data
            self.opts = {"attempts": 3}
            self.attemptsMade = 0

    mock_job = MockJob("promote_to_lesson", {"intelligence_id": "test-insight"})

    with patch("services.config_helpers.get_llm_config", return_value={"rate_limit_rpm": 60}):
        with patch("memory_tasks.promote_to_lesson", new_callable=AsyncMock) as mock_promote:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                
                # Execute queue worker fn directly
                await _process_bulk_job(mock_job, "token")
                
                # Verify branch
                mock_promote.assert_called_once_with("test-insight")
                mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_dead_letter_queue_failure_logic():
    """Verify DLQ transitions rows to 'failed' safely after max attempts"""
    from memory.queue import _process_bulk_job
    
    class MockFailureJob:
        def __init__(self, name, data):
            self.id = "test-job-fail"
            self.name = name
            self.data = data
            self.opts = {"attempts": 1}
            self.attemptsMade = 0

    mock_job = MockFailureJob("ingest_interaction", {"interaction_id": "bad-id"})
    
    # Mock error inside router
    with patch("memory_tasks.process_interaction", side_effect=Exception("Simulated API Down")):
        with patch("services.config_helpers.get_llm_config", return_value={}):
            with patch("core.storage.get_memory_db_context") as mock_db:
                mock_cursor = MagicMock()
                mock_db.return_value.__enter__.return_value.cursor.return_value = mock_cursor
                
                try:
                    await _process_bulk_job(mock_job, "token")
                except Exception:
                    pass # Expected
                    
                # Assert DLQ sql executed
                mock_cursor.execute.assert_called()
                sql_call = mock_cursor.execute.call_args[0][0]
                assert "UPDATE interactions SET status = 'failed'" in sql_call
