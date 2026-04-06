"""
test_interactions.py — Tier 0: Interaction ingestion & retrieval

Tests:
  - POST /api/memory/interactions   (agent key auth)
  - GET  /api/memory/interactions   (admin JWT)
  - GET  /api/memory/memories       (admin JWT)
  - POST /api/memory/search         (agent key)
  - GET  /api/memory/timeline/{type}/{id}
"""
import pytest


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
        assert resp.status_code == 200, resp.text
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
        assert resp.status_code == 200, resp.text
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

    def test_list_memories(self, agent, base_url):
        resp = agent.get(f"{base_url}/api/memory/memories",
                         params={"entity_type": "contact", "entity_id": "test-contact-001"})
        assert resp.status_code in (200, 404), resp.text
        print("✓ Memories endpoint accessible")

    def test_list_insights(self, admin, base_url):
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
    """Entity timeline endpoint."""

    def test_timeline_requires_api_key(self, api_client, base_url):
        api_client.headers.pop("X-API-Key", None)
        api_client.headers.pop("Authorization", None)
        resp = api_client.get(f"{base_url}/api/memory/timeline",
                              params={"entity_type": "contact", "entity_id": "test-contact-001"})
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Timeline requires API key")

    def test_timeline_returns_valid_shape(self, agent, base_url):
        resp = agent.get(f"{base_url}/api/memory/timeline/contact/test-contact-001")
        assert resp.status_code in (200, 404), resp.text
        if resp.status_code == 200:
            data = resp.json()
            assert "entries" in data or isinstance(data, list)
        print(f"✓ Timeline endpoint: {resp.status_code}")
