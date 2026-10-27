"""
test_interactions.py — Tier 0: Interaction ingestion & retrieval

Tests:
  - POST /api/memory/interactions   (agent key auth)
  - GET  /api/memory/interactions   (admin JWT)
  - GET  /api/memory/memories       (admin JWT)
  - POST /api/memory/search         (agent key)
  - GET  /api/memory/admin/timeline/{type}/{id}   (admin JWT)
"""
import os

import pytest  # noqa: F401  (marker parity with the other suite files)


class TestInteractionIngestion:
    """Interaction creation via new 4-tier schema."""

    def test_ingest_basic_interaction(self, agent, base_url):
        resp = agent.post(f"{base_url}/api/memory/interactions", json={
            "interaction_type": "crm_note",
            "content": "Test interaction — automated test suite",
            "primary_entity_type": "contact",
            "primary_entity_id": "test-contact-001",
            "source": "api",
        })
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert "id" in data
        assert data.get("status") == "pending"
        print(f"✓ Interaction created: {data['id']}")

    def test_ingest_with_metadata(self, agent, base_url):
        resp = agent.post(f"{base_url}/api/memory/interactions", json={
            "interaction_type": "email_received",
            "content": "Subject: Follow up\n\nHello, following up on our last meeting.",
            "primary_entity_type": "contact",
            "primary_entity_id": "test-contact-001",
            "primary_entity_subtype": "lead",
            "agent_name": "email_sync",
            "metadata": {"sender": "john@example.com", "subject": "Follow up"},
            "metadata_field_map": {"summary_field": "subject"},
            "source": "api",
        })
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert "id" in data
        print(f"✓ Interaction with metadata created: {data['id']}")

    def test_ingest_requires_api_key(self, api_client, base_url):
        api_client.headers.pop("X-API-Key", None)
        api_client.headers.pop("Authorization", None)
        resp = api_client.post(f"{base_url}/api/memory/interactions", json={
            "interaction_type": "crm_note",
            "content": "Should be rejected",
            "primary_entity_type": "contact",
            "primary_entity_id": "test-001",
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Interactions endpoint rejects unauthenticated requests")

    def test_ingest_invalid_body_returns_422(self, agent, base_url):
        resp = agent.post(f"{base_url}/api/memory/interactions", json={
            "interaction_type": "crm_note",
            # missing required fields: content, primary_entity_type, primary_entity_id
        })
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"
        print("✓ Missing required fields returns 422")


class TestCrmDedupReplay:
    """TASK-258 conflict-replay path (metadata.crm_dedup_key).

    Regression (verified review finding 10-27): a duplicate comm fire landing
    AFTER enrichment must NOT clobber the stored transcript back to the bare
    placeholder — replays are never re-enqueued, so the loss would be permanent.
    Exercises the real ON CONFLICT tail against the real partial unique index
    (both built at hermetic boot), so it needs the hermetic stack's direct DB
    access to simulate the enrichment UPDATE.
    """

    def test_replay_preserves_enriched_content(self, agent, base_url):
        if os.environ.get("MEMORY_TEST_BASE_URL") or not os.environ.get("DATABASE_URL"):
            pytest.skip("hermetic-only: needs direct DB access to simulate enrichment")
        import psycopg2

        entity = "test-contact-dedup-replay"
        payload = {
            "interaction_type": "whatsapp_message",
            "content": "[Incoming voice note — transcript pending]",
            "primary_entity_type": "contact",
            "primary_entity_id": entity,
            "metadata": {"crm_dedup_key": f"pytest-dedup-replay|c-{entity}|whatsapp_message"},
            "source": "n8n:whatsapp_agent",
        }
        first = agent.post(f"{base_url}/api/memory/interactions", json=payload)
        assert first.status_code == 202, first.text
        original_id = first.json()["id"]

        # Simulate the enrichment UPDATE (memory_system/ingest/ingestion.py):
        # the transcript lands and is_enriched flips — the exact state a late
        # duplicate comm fire replays against.
        enriched = (
            "[Incoming voice note — transcript pending]"
            "\n\n---\n[Attachment (audio/ogg): voice_note.ogg]\nthe real transcript"
        )
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE interactions SET content = %s, is_enriched = TRUE WHERE id = %s",
                    (enriched, original_id),
                )
            conn.commit()
        finally:
            conn.close()

        replay = agent.post(f"{base_url}/api/memory/interactions", json=payload)
        assert replay.status_code == 202, replay.text
        assert replay.json()["id"] == original_id, "replay must collapse onto the existing row"

        listed = agent.get(f"{base_url}/api/memory/interactions",
                           params={"entity_type": "contact", "entity_id": entity})
        assert listed.status_code == 200, listed.text
        row = next(r for r in listed.json()["interactions"] if r["id"] == original_id)
        assert row["content"] == enriched, "dedup replay clobbered enriched content"
        print("✓ Dedup replay kept enriched content")


class TestInteractionBulkIngestion:
    """Bulk interaction ingestion via /interactions/bulk."""

    def test_bulk_ingest_happy_path(self, agent, base_url):
        items = [
            {
                "interaction_type": f"internal_ai_thought" if i == 0 else "internal_ai_tool_call",
                "content": f"row-{i}",
                "primary_entity_type": "contact",
                "primary_entity_id": "test-contact-bulk-001",
                "metadata": {"trace_id": "trace-abc", "step": i},
                "source": "n8n:whatsapp_agent",
            }
            for i in range(5)
        ]
        resp = agent.post(f"{base_url}/api/memory/interactions/bulk", json={"items": items})
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert data["count"] == 5
        assert len(data["ids"]) == 5
        assert all(isinstance(i, str) for i in data["ids"])
        print(f"✓ Bulk ingested 5 interactions: trace={data['ids'][0]}…")

    def test_bulk_ingest_rejects_oversized_batch(self, agent, base_url):
        items = [{
            "interaction_type": "internal_ai_tool_call",
            "content": "x",
            "primary_entity_type": "contact",
            "primary_entity_id": "test-001",
        } for _ in range(101)]
        resp = agent.post(f"{base_url}/api/memory/interactions/bulk", json={"items": items})
        assert resp.status_code == 422, f"Expected 422 for >100 items, got {resp.status_code}"
        print("✓ Bulk endpoint rejects batches over 100 items")

    def test_bulk_ingest_idempotency_key_replays_original_result(self, agent, base_url):
        payload = {"items": [{
            "interaction_type": "internal_ai_thought",
            "content": "idempotent trace row",
            "primary_entity_type": "contact",
            "primary_entity_id": "test-contact-bulk-idempotent",
            "source": "n8n:tasks_agent",
        }]}
        headers = {"Idempotency-Key": "pytest-bulk-idempotency-1"}
        first = agent.post(f"{base_url}/api/memory/interactions/bulk", json=payload, headers=headers)
        second = agent.post(f"{base_url}/api/memory/interactions/bulk", json=payload, headers=headers)
        assert first.status_code == 202, first.text
        assert second.status_code == 202, second.text
        assert second.json()["ids"] == first.json()["ids"]
        assert second.json()["replayed"] is True
        assert second.headers.get("Idempotent-Replayed") == "true"

    def test_bulk_ingest_rejects_reused_key_with_different_payload(self, agent, base_url):
        headers = {"Idempotency-Key": "pytest-bulk-idempotency-conflict"}
        base = {
            "interaction_type": "internal_ai_thought",
            "primary_entity_type": "contact",
            "primary_entity_id": "test-contact-bulk-idempotent",
            "source": "n8n:tasks_agent",
        }
        first = agent.post(f"{base_url}/api/memory/interactions/bulk", json={"items": [{**base, "content": "one"}]}, headers=headers)
        conflict = agent.post(f"{base_url}/api/memory/interactions/bulk", json={"items": [{**base, "content": "two"}]}, headers=headers)
        assert first.status_code == 202, first.text
        assert conflict.status_code == 409, conflict.text

    def test_bulk_ingest_rejects_empty_batch(self, agent, base_url):
        resp = agent.post(f"{base_url}/api/memory/interactions/bulk", json={"items": []})
        assert resp.status_code == 422, f"Expected 422 for empty items, got {resp.status_code}"
        print("✓ Bulk endpoint rejects empty batches")

    def test_bulk_ingest_requires_api_key(self, api_client, base_url):
        api_client.headers.pop("X-API-Key", None)
        api_client.headers.pop("Authorization", None)
        resp = api_client.post(f"{base_url}/api/memory/interactions/bulk", json={
            "items": [{
                "interaction_type": "internal_ai_tool_call",
                "content": "nope",
                "primary_entity_type": "contact",
                "primary_entity_id": "test-001",
            }]
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Bulk endpoint rejects unauthenticated requests")


class TestInteractionRetrieval:
    """Admin read of interactions."""

    def test_list_interactions(self, admin, base_url):
        resp = admin.get(f"{base_url}/api/memory/interactions")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "interactions" in data or isinstance(data, list), "Unexpected response shape"
        interactions = data.get("interactions", data) if isinstance(data, dict) else data
        print(f"✓ Admin list interactions: {len(interactions)} records")

    def test_list_interactions_requires_auth(self, api_client, base_url):
        api_client.headers.pop("Authorization", None)
        api_client.headers.pop("X-API-Key", None)
        resp = api_client.get(f"{base_url}/api/memory/interactions")
        assert resp.status_code == 401
        print("✓ Interactions list requires admin auth")

    def test_agent_can_list_interactions(self, agent, base_url):
        # GET /interactions accepts an agent API key as well as admin JWT
        # (the CRM/tasks n8n agents read a contact's timeline here).
        resp = agent.get(
            f"{base_url}/api/memory/interactions",
            params={"entity_type": "contact", "entity_id": "test-contact-001"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "interactions" in data, "Unexpected response shape"
        print(f"✓ Agent list interactions: {len(data['interactions'])} records")

    def test_list_memories(self, agent, base_url):
        resp = agent.get(f"{base_url}/api/memory/memories",
                         params={"entity_type": "contact", "entity_id": "test-contact-001"})
        assert resp.status_code in (200, 404), resp.text
        print("✓ Memories endpoint accessible")

    def test_list_intelligence(self, admin, base_url):
        resp = admin.get(f"{base_url}/api/memory/insights")
        assert resp.status_code in (200, 404), resp.text
        print("✓ Insights endpoint accessible")


class TestSearch:
    """Semantic search across tiers."""

    def test_search_requires_api_key(self, api_client, base_url):
        api_client.headers.pop("X-API-Key", None)
        api_client.headers.pop("Authorization", None)
        resp = api_client.post(f"{base_url}/api/memory/search", json={"query": "test"})
        assert resp.status_code == 401
        print("✓ Search requires API key")

    def test_search_returns_results_shape(self, agent, base_url):
        resp = agent.post(f"{base_url}/api/memory/search", json={
            "query": "test contact interaction",
            "entity_type": "contact",
            "limit": 5,
        })
        assert resp.status_code in (200, 503), resp.text  # 503 if embedding not configured
        if resp.status_code == 200:
            data = resp.json()
            assert "results" in data or isinstance(data, list)
        print(f"✓ Search endpoint responded: {resp.status_code}")

    def test_search_empty_query_422(self, agent, base_url):
        resp = agent.post(f"{base_url}/api/memory/search", json={})
        assert resp.status_code == 422
        print("✓ Empty search query returns 422")


class TestTimeline:
    """Admin entity-timeline endpoint (GET /api/memory/admin/timeline/{type}/{id})."""

    def test_timeline_requires_auth(self, api_client, base_url):
        api_client.headers.pop("X-API-Key", None)
        api_client.headers.pop("Authorization", None)
        resp = api_client.get(f"{base_url}/api/memory/admin/timeline/contact/test-contact-001")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Admin timeline requires auth")

    def test_timeline_returns_valid_shape(self, admin, base_url):
        resp = admin.get(f"{base_url}/api/memory/admin/timeline/contact/test-contact-001",
                         params={"limit": 50})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "entries" in data and "total" in data
        for entry in data["entries"]:
            assert all(k in entry for k in ("id", "timestamp", "interaction_type"))
            break
        print(f"✓ Admin timeline returned {data['total']} entries")
