"""
test_pipeline_gates.py — TASK-261 step-3 letter-list cases the repaired
pre-existing files did not pin:

  (b-tail) claim-ledger lifecycle: single daily winner, failed-claim reopen,
           15-min stale-running reclaim, and the queue runner's completed-claim
           duplicate no-op.
  (c)      orphan-sweeper gating: enriched rows and fresh pendings are NOT
           replayed (a replay duplicates attachment text and re-bills vision
           OCR); only stuck un-enriched pendings/staled queues re-enqueue.
  (d)      compaction raise on LLM failure + quarantine/empty-husk exclusion
           (and the double-run guard against a duplicated delivery).
  (e)      bulk-reprocess heals a quarantined husk: interactions re-armed,
           poison-pill generation_cycle stamps PRESERVED, husk row deleted.
  (f)      /search/semantic: 503 on embedding-provider failure, 200 on success
           (a broken provider is availability, not "no results").
  (g)      /pipeline-health endpoint sanity with live counters.

All DB writes land on the hermetic stack's throwaway Postgres with unique
entity ids / job names per test — no cross-test interference.
"""
import dataclasses
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from core.storage import get_memory_db_context
from memory.queue import JOBS


class MockJob:
    """Same duck-type as test_memory_queue.MockJob (kept local: jobs differ)."""

    def __init__(self, name, data, attempts=1, attempts_made=0):
        self.id = f"test-{uuid.uuid4().hex[:8]}"
        self.name = name
        self.data = data
        self.opts = {"attempts": attempts}
        self.attemptsMade = attempts_made


def _insert_interaction_row(cursor, *, entity_type="contact", entity_id,
                            status="pending", is_enriched=False, created_at=None,
                            processing_errors=None):
    iid = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO interactions (id, interaction_type, content,
            primary_entity_type, primary_entity_id, status, is_enriched,
            created_at, "timestamp", processing_errors)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (iid, "test_event", "gate-test content", entity_type, entity_id,
         status, is_enriched, created_at, created_at,
         json.dumps(processing_errors or {})),
    )
    return iid


def _insert_memory(*, entity_type, entity_id, interaction_date, content_summary,
                   processing_errors, interaction_ids=None):
    from memory_system.store.writes import insert_memory
    return insert_memory(
        memory_id=str(uuid.uuid4()),
        interaction_date=interaction_date,
        entity_type=entity_type,
        entity_id=entity_id,
        interaction_ids=interaction_ids or [],
        content_summary=content_summary,
        related_entities=[],
        intents=[],
        relationships=[],
        embedding=None,
        processing_errors=processing_errors,
    )


def _delete_entity_rows(cursor, entity_id, *, job_name=None):
    cursor.execute("DELETE FROM intelligence WHERE primary_entity_id = %s", (entity_id,))
    cursor.execute("DELETE FROM memories WHERE primary_entity_id = %s", (entity_id,))
    cursor.execute("DELETE FROM interactions WHERE primary_entity_id = %s", (entity_id,))
    if job_name:
        cursor.execute("DELETE FROM memory_job_log WHERE job_name = %s", (job_name,))


# ── (b-tail) Claim-ledger lifecycle ──────────────────────────────────────────

class TestClaimLedger:
    JOB = "test_claim_gate_job"

    def _cleanup(self, job_name):
        with get_memory_db_context() as conn:
            conn.cursor().execute(
                "DELETE FROM memory_job_log WHERE job_name = %s", (job_name,))

    def test_single_daily_winner(self, base_url):
        from memory_system.distill.generation import claim_job_date
        day = datetime.now(timezone.utc).date() - timedelta(days=1)
        try:
            assert claim_job_date(self.JOB, day) is True
            # Same-day second claim refused — across replicas or loop ticks.
            assert claim_job_date(self.JOB, day) is False
            # A new date claims fresh.
            assert claim_job_date(self.JOB, day + timedelta(days=1)) is True
        finally:
            self._cleanup(self.JOB)

    def test_failed_claim_reopens_same_day(self, base_url):
        from memory_system.distill.generation import claim_job_date, fail_job_date
        day = datetime.now(timezone.utc).date() - timedelta(days=1)
        try:
            assert claim_job_date(self.JOB, day) is True
            fail_job_date(self.JOB, day, RuntimeError("boom"))
            # failed → the WHERE clause's status='failed' arm re-admits.
            assert claim_job_date(self.JOB, day) is True
        finally:
            self._cleanup(self.JOB)

    def test_stale_running_claim_reclaimed_after_window(self, base_url):
        from memory_system.distill.generation import claim_job_date
        day = datetime.now(timezone.utc).date() - timedelta(days=1)
        try:
            assert claim_job_date(self.JOB, day) is True
            with get_memory_db_context() as conn:
                conn.cursor().execute(
                    "UPDATE memory_job_log SET last_run = NOW() - INTERVAL '20 minutes' "
                    "WHERE job_name = %s", (self.JOB,))
            # 15-min reclaim: the claimant is presumed dead.
            assert claim_job_date(self.JOB, day) is True
            # A fresh running claim is NOT reclaimable.
            with get_memory_db_context() as conn:
                conn.cursor().execute(
                    "UPDATE memory_job_log SET last_run = NOW() "
                    "WHERE job_name = %s", (self.JOB,))
            assert claim_job_date(self.JOB, day) is False
        finally:
            self._cleanup(self.JOB)

    @pytest.mark.asyncio
    async def test_runner_noops_when_claim_completed(self, base_url):
        """The 15-min reclaim can re-fire a job whose day already completed —
        the runner must no-op the duplicate pickup instead of double-running."""
        from memory.queue import _process_bulk_job
        from memory_system.distill.generation import claim_job_date, complete_job_date

        day = datetime.now(timezone.utc).date() - timedelta(days=1)
        try:
            assert claim_job_date(self.JOB, day) is True
            complete_job_date(self.JOB, day)

            handler = AsyncMock()
            spec = dataclasses.replace(JOBS["run_intelligence_sweep"], handler=handler)
            job = MockJob("run_intelligence_sweep", {
                "min_count": 2,
                "job_claim": {"name": self.JOB, "date": day.isoformat()},
            })
            with patch.dict("memory.queue.JOBS", {"run_intelligence_sweep": spec}):
                result = await _process_bulk_job(job, "token")

            assert result == {"status": "skipped", "reason": "claim_completed"}
            handler.assert_not_awaited()
        finally:
            self._cleanup(self.JOB)


# ── (c) Orphan-sweeper gating ────────────────────────────────────────────────

class TestOrphanSweeperGating:
    @pytest.mark.asyncio
    async def test_enriched_and_fresh_rows_not_replayed(self, base_url):
        from memory_system.distill.generation import run_orphan_sweeper

        entity_id = f"sweep-{uuid.uuid4().hex[:8]}"
        stale = datetime.now(timezone.utc) - timedelta(hours=7)
        fresh = datetime.now(timezone.utc)

        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            stale_pending = _insert_interaction_row(
                cursor, entity_id=entity_id, status="pending",
                is_enriched=False, created_at=stale)
            enriched = _insert_interaction_row(
                cursor, entity_id=entity_id, status="pending",
                is_enriched=True, created_at=stale)
            fresh_pending = _insert_interaction_row(
                cursor, entity_id=entity_id, status="pending",
                is_enriched=False, created_at=fresh)
            stale_queued = _insert_interaction_row(
                cursor, entity_id=entity_id, status="queued",
                is_enriched=False, created_at=stale)

        try:
            with patch("memory.queue.memory_bulk_queue.add", new_callable=AsyncMock) as mock_add, \
                 patch("memory.queue.job_options", return_value={}):
                await run_orphan_sweeper()

            requeued = {call.args[1]["interaction_id"]
                        for call in mock_add.await_args_list}
            # Stuck un-enriched pendings AND stale 'queued' rows re-enqueue…
            assert requeued == {stale_pending, stale_queued}
            # …enriched rows resting in 'pending' await distillation and must
            # NOT replay (duplicate attachment text, re-billed vision OCR);
            # fresh pendings aren't orphans yet.
            assert enriched not in requeued
            assert fresh_pending not in requeued
        finally:
            with get_memory_db_context() as conn:
                _delete_entity_rows(conn.cursor(), entity_id)


# ── (d) Compaction: raise + quarantine exclusion + double-run guard ─────────

class TestCompactionGates:
    _CANNED = '[{"name": "Gate Insight", "signals": [], "content": "C", "summary": "S"}]'

    def _compact_patches(self):
        return [
            patch("memory_system.distill.compaction.call_llm",
                  new_callable=AsyncMock, return_value=self._CANNED),
            patch("memory_system.distill.compaction.generate_embedding",
                  new_callable=AsyncMock, return_value=None),
            patch("memory_system.distill.compaction.fetch_prior_intelligence",
                  new_callable=AsyncMock, return_value=""),
            patch("memory_system.distill.compaction.fetch_prior_knowledge_semantic",
                  new_callable=AsyncMock, return_value=""),
        ]

    @pytest.mark.asyncio
    async def test_quarantined_and_empty_husks_excluded(self, base_url):
        from memory_system.distill.compaction import compact_entity

        entity_id = f"cmp-{uuid.uuid4().hex[:8]}"
        day0 = datetime.now(timezone.utc).date()
        clean_ids = []
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            try:
                for i in range(10):
                    day = str(day0 - timedelta(days=i + 2))
                    clean_ids.append(_insert_memory(
                        entity_type="contact", entity_id=entity_id,
                        interaction_date=day,
                        content_summary=f"clean summary {i}",
                        processing_errors={}))
                quarantine_id = _insert_memory(
                    entity_type="contact", entity_id=entity_id,
                    interaction_date=str(day0 - timedelta(days=1)),
                    content_summary="",
                    processing_errors={"quarantine": "test quarantine"})
                empty_id = _insert_memory(
                    entity_type="contact", entity_id=entity_id,
                    interaction_date=str(day0),
                    content_summary="", processing_errors={})

                patches = self._compact_patches()
                with patches[0], patches[1], patches[2], patches[3]:
                    await compact_entity("contact", entity_id)

                cursor.execute(
                    "SELECT source_memory_ids FROM intelligence "
                    "WHERE primary_entity_type = 'contact' AND primary_entity_id = %s",
                    (entity_id,))
                rows = cursor.fetchall()
                assert len(rows) == 1, f"expected exactly one intelligence row, got {len(rows)}"
                cited = set(rows[0]["source_memory_ids"] or [])
                assert cited == set(clean_ids), (
                    "compaction cited quarantined/empty husks or missed clean memories")
                assert quarantine_id not in cited and empty_id not in cited

                # Consumed memories are marked compacted; husks stay untouched.
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM memories "
                    "WHERE primary_entity_id = %s AND compacted = TRUE", (entity_id,))
                assert cursor.fetchone()["cnt"] == len(clean_ids)

                # Double-run guard: a duplicated delivery must not clone rows.
                with patches[0], patches[1], patches[2], patches[3]:
                    await compact_entity("contact", entity_id)
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM intelligence "
                    "WHERE primary_entity_type = 'contact' AND primary_entity_id = %s",
                    (entity_id,))
                assert cursor.fetchone()["cnt"] == 1
            finally:
                _delete_entity_rows(cursor, entity_id)

    @pytest.mark.asyncio
    async def test_llm_failure_raises_and_logs_failed_run(self, base_url):
        from memory_system.distill.compaction import compact_entity

        entity_id = f"cmpf-{uuid.uuid4().hex[:8]}"
        day = str(datetime.now(timezone.utc).date() - timedelta(days=2))
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            try:
                _insert_memory(entity_type="contact", entity_id=entity_id,
                               interaction_date=day,
                               content_summary="clean summary", processing_errors={})

                with patch("memory_system.distill.compaction.call_llm",
                           new_callable=AsyncMock,
                           side_effect=RuntimeError("LLM down")), \
                     patch("memory_system.distill.compaction.generate_embedding",
                           new_callable=AsyncMock, return_value=None), \
                     patch("memory_system.distill.compaction.fetch_prior_intelligence",
                           new_callable=AsyncMock, return_value=""), \
                     patch("memory_system.distill.compaction.fetch_prior_knowledge_semantic",
                           new_callable=AsyncMock, return_value=""), \
                     patch("memory_system.distill.compaction.log_pipeline_run") as mock_log:
                    with pytest.raises(RuntimeError, match="LLM down"):
                        await compact_entity("contact", entity_id)

                failed = [c for c in mock_log.call_args_list
                          if len(c.args) >= 2 and c.args[1] == "failed"]
                assert failed, "LLM failure must record a failed pipeline run"

                # The memories stay uncompacted for the retry.
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM memories "
                    "WHERE primary_entity_id = %s AND compacted = TRUE", (entity_id,))
                assert cursor.fetchone()["cnt"] == 0
            finally:
                _delete_entity_rows(cursor, entity_id)


# ── (e) Bulk-reprocess heals a quarantined husk ──────────────────────────────

class TestBulkReprocessHeal:
    def test_quarantined_husk_rearms_interactions_and_preserves_stamps(
            self, admin, base_url):
        entity_id = f"heal-{uuid.uuid4().hex[:8]}"
        day = str(datetime.now(timezone.utc).date() - timedelta(days=1))
        # Short-lived contexts: the rows MUST be committed before the endpoint
        # runs — the request is served on a pooled connection that cannot see
        # this test's open transaction.
        with get_memory_db_context() as conn:
            stamped = _insert_interaction_row(
                conn.cursor(), entity_id=entity_id, status="done",
                created_at=datetime.now(timezone.utc) - timedelta(days=1),
                processing_errors={"generation_cycle": 3})
            plain = _insert_interaction_row(
                conn.cursor(), entity_id=entity_id, status="done",
                created_at=datetime.now(timezone.utc) - timedelta(days=1))
        husk_id = _insert_memory(
            entity_type="contact", entity_id=entity_id,
            interaction_date=day, content_summary="",
            processing_errors={"quarantine": "generation failed 9 cycles"})

        try:
            with patch("memory.queue.memory_queue.add",
                       new_callable=AsyncMock) as mock_add:
                resp = admin.post(
                    f"{base_url}/api/memory/admin/memories/bulk-reprocess",
                    json={"memory_ids": [husk_id]})

            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["queued"] == 1, f"unexpected body: {body}"
            assert body["rearmed_interactions"] == 2, f"unexpected body: {body}"

            with get_memory_db_context() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, status, processing_errors FROM interactions "
                    "WHERE id = ANY(%s)", ([stamped, plain],))
                rows = {r["id"]: r for r in cursor.fetchall()}
                assert rows[stamped]["status"] == "pending"
                assert rows[plain]["status"] == "pending"
                # The poison-pill counter MUST survive the heal (it bounds the
                # automated retry churn the direct enqueue bypasses).
                assert (rows[stamped]["processing_errors"] or {}).get("generation_cycle") == 3

                cursor.execute("SELECT 1 FROM memories WHERE id = %s", (husk_id,))
                assert cursor.fetchone() is None, "quarantine husk must be deleted"

            assert mock_add.await_count == 1
            payload = mock_add.await_args.args[1]
            assert payload == {"entity_type": "contact", "entity_id": entity_id,
                               "interaction_date": day}
        finally:
            with get_memory_db_context() as conn:
                _delete_entity_rows(conn.cursor(), entity_id)


# ── (f) /search/semantic 503/200 flip ────────────────────────────────────────

class TestSearchAvailabilityContract:
    PATH = "/api/memory/search/semantic"

    def test_embedding_failure_is_503_not_empty_results(self, agent, base_url):
        with patch("memory.agent.generate_embedding",
                   new_callable=AsyncMock, return_value=[]):
            resp = agent.post(f"{base_url}{self.PATH}",
                              json={"query": "anything", "layers": ["memories"]})
        assert resp.status_code == 503
        assert "embedding" in resp.json()["detail"].lower()

    def test_embedding_success_flows_to_results(self, agent, base_url):
        with patch("memory.agent.generate_embedding",
                   new_callable=AsyncMock, return_value=[0.1] * 8), \
             patch("memory.agent.search_memories_by_vector",
                   new_callable=AsyncMock, return_value=[]) as mock_mem, \
             patch("memory.agent.search_intelligence_by_vector",
                   new_callable=AsyncMock, return_value=[]), \
             patch("memory.agent.search_knowledge_by_vector",
                   new_callable=AsyncMock, return_value=[]):
            resp = agent.post(
                f"{base_url}{self.PATH}",
                json={"query": "anything",
                      "layers": ["memories", "intelligence", "knowledge"]})
        assert resp.status_code == 200, resp.text
        assert resp.json()["results"] == []
        mock_mem.assert_awaited_once()


# ── (g) /pipeline-health sanity ──────────────────────────────────────────────

class TestPipelineHealth:
    PATH = "/api/memory/pipeline-health"

    def test_counts_reflect_inserted_rows(self, admin, base_url):
        before = admin.get(f"{base_url}{self.PATH}")
        assert before.status_code == 200, before.text
        before_json = before.json()
        for key in ("pending_interactions", "failed_interactions",
                    "pending_entity_days", "last_memory_at",
                    "empty_summary_memories", "memory_ops_queue"):
            assert key in before_json

        entity_id = f"ph-{uuid.uuid4().hex[:8]}"
        old = datetime.now(timezone.utc) - timedelta(days=2)
        try:
            with get_memory_db_context() as conn:
                cursor = conn.cursor()
                _insert_interaction_row(cursor, entity_id=entity_id,
                                        status="pending", created_at=old)
                _insert_interaction_row(cursor, entity_id=entity_id,
                                        status="failed", created_at=old)

            after = admin.get(f"{base_url}{self.PATH}").json()
            assert after["pending_interactions"] - before_json["pending_interactions"] >= 1
            assert after["failed_interactions"] - before_json["failed_interactions"] >= 1
            assert after["pending_entity_days"] >= 1
            # Queue counts ride the real BullMQ connection in the hermetic
            # stack (workers patched off, Redis up) — either shape is sane.
            assert after["memory_ops_queue"] is None or isinstance(
                after["memory_ops_queue"], dict)
        finally:
            with get_memory_db_context() as conn:
                _delete_entity_rows(conn.cursor(), entity_id)
