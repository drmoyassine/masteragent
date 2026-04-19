"""
test_admin.py — Phase 4: Admin CRUD for Insights, Lessons, EntityTypeConfig

Tests:
  - GET/POST/PATCH/DELETE  /api/memory/insights
  - GET/POST/PATCH/DELETE  /api/memory/lessons
  - GET/PATCH              /api/memory/entity-type-config/{entity_type}
  - POST                   /api/memory/trigger/compact/{entity_type}/{entity_id}
  - POST                   /api/memory/trigger/generate-memories
  - GET                    /api/memory/audit-log
"""
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def test_insight(admin, base_url):
    """Create a test insight and delete it after the test."""
    resp = admin.post(f"{base_url}/api/memory/insights", json={
        "primary_entity_type": "contact",
        "primary_entity_id": "test-contact-001",
        "name": "TEST Insight",
        "insight_type": "behavior_pattern",
        "content": "Contact consistently responds within 24h — test insight.",
        "summary": "Fast responder",
    })
    assert resp.status_code in (200, 201), f"Insight creation failed: {resp.text}"
    insight = resp.json()
    yield insight
    admin.delete(f"{base_url}/api/memory/insights/{insight['id']}")


@pytest.fixture
def test_lesson(admin, base_url):
    """Create a test lesson and delete it after the test."""
    resp = admin.post(f"{base_url}/api/memory/lessons", json={
        "name": "TEST Lesson",
        "lesson_type": "process",
        "content": "Always follow up within 48h of initial contact — test lesson.",
        "summary": "48h follow-up rule",
        "tags": ["follow-up", "test"],
    })
    assert resp.status_code in (200, 201), f"Lesson creation failed: {resp.text}"
    lesson = resp.json()
    yield lesson
    admin.delete(f"{base_url}/api/memory/lessons/{lesson['id']}")


# ── Insights CRUD ─────────────────────────────────────────────────────────────

class TestInsightsCRUD:

    def test_list_intelligence(self, admin, base_url):
        resp = admin.get(f"{base_url}/api/memory/insights")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "insights" in data or isinstance(data, list)
        print("✓ List insights OK")

    def test_list_intelligence_requires_auth(self, api_client, base_url):
        api_client.headers.pop("Authorization", None)
        api_client.headers.pop("X-API-Key", None)
        resp = api_client.get(f"{base_url}/api/memory/insights")
        assert resp.status_code == 401
        print("✓ Insights list requires admin auth")

    def test_create_intelligence(self, admin, base_url):
        resp = admin.post(f"{base_url}/api/memory/insights", json={
            "primary_entity_type": "contact",
            "primary_entity_id": "test-contact-001",
            "name": "TEST Create Insight",
            "insight_type": "risk_signal",
            "content": "Insight content for create test",
        })
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        assert "id" in data
        intelligence_id = data["id"]
        # Cleanup
        admin.delete(f"{base_url}/api/memory/insights/{intelligence_id}")
        print(f"✓ Create insight OK: {intelligence_id}")

    def test_get_insight(self, admin, base_url, test_insight):
        intelligence_id = test_insight["id"]
        resp = admin.get(f"{base_url}/api/memory/insights/{intelligence_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == intelligence_id
        print(f"✓ Get insight OK: {intelligence_id}")

    def test_patch_insight(self, admin, base_url, test_insight):
        intelligence_id = test_insight["id"]
        resp = admin.patch(f"{base_url}/api/memory/insights/{intelligence_id}", json={
            "summary": "Updated summary via test",
            "status": "confirmed",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("summary") == "Updated summary via test" or data.get("updated") is True
        print(f"✓ Patch insight OK: {intelligence_id}")

    def test_promote_insight_to_lesson(self, admin, base_url, test_insight):
        intelligence_id = test_insight["id"]
        resp = admin.post(f"{base_url}/api/memory/insights/{intelligence_id}/promote")
        assert resp.status_code in (200, 201, 400), resp.text
        # 400 is acceptable if insight is already promoted / too short
        print(f"✓ Promote insight endpoint responded: {resp.status_code}")

    def test_delete_intelligence(self, admin, base_url):
        # Create fresh
        resp = admin.post(f"{base_url}/api/memory/insights", json={
            "primary_entity_type": "contact",
            "primary_entity_id": "test-contact-delete",
            "name": "TEST Delete Insight",
            "insight_type": "other",
            "content": "Will be deleted",
        })
        assert resp.status_code in (200, 201), resp.text
        intelligence_id = resp.json()["id"]
        # Delete
        resp = admin.delete(f"{base_url}/api/memory/insights/{intelligence_id}")
        assert resp.status_code in (200, 204), resp.text
        # Verify gone
        resp = admin.get(f"{base_url}/api/memory/insights/{intelligence_id}")
        assert resp.status_code == 404
        print("✓ Delete insight OK")

    def test_insight_filter_by_entity(self, admin, base_url):
        resp = admin.get(
            f"{base_url}/api/memory/insights",
            params={"entity_type": "contact", "entity_id": "test-contact-001"}
        )
        assert resp.status_code == 200, resp.text
        print("✓ Insights entity filter OK")


# ── Lessons CRUD ──────────────────────────────────────────────────────────────

class TestLessonsCRUD:

    def test_list_knowledge(self, admin, base_url):
        resp = admin.get(f"{base_url}/api/memory/lessons")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "lessons" in data or isinstance(data, list)
        print("✓ List lessons OK")

    def test_create_knowledge(self, admin, base_url):
        resp = admin.post(f"{base_url}/api/memory/lessons", json={
            "name": "TEST Create Lesson",
            "lesson_type": "sales",
            "content": "Lesson content for create test",
            "tags": ["test"],
        })
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        assert "id" in data
        knowledge_id = data["id"]
        admin.delete(f"{base_url}/api/memory/lessons/{knowledge_id}")
        print(f"✓ Create lesson OK: {knowledge_id}")

    def test_get_lesson(self, admin, base_url, test_lesson):
        knowledge_id = test_lesson["id"]
        resp = admin.get(f"{base_url}/api/memory/lessons/{knowledge_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == knowledge_id
        print(f"✓ Get lesson OK: {knowledge_id}")

    def test_patch_lesson(self, admin, base_url, test_lesson):
        knowledge_id = test_lesson["id"]
        resp = admin.patch(f"{base_url}/api/memory/lessons/{knowledge_id}", json={
            "summary": "Updated via test",
        })
        assert resp.status_code == 200, resp.text
        print(f"✓ Patch lesson OK: {knowledge_id}")

    def test_delete_knowledge(self, admin, base_url):
        resp = admin.post(f"{base_url}/api/memory/lessons", json={
            "name": "TEST Delete Lesson",
            "lesson_type": "other",
            "content": "Will be deleted",
        })
        assert resp.status_code in (200, 201), resp.text
        knowledge_id = resp.json()["id"]
        resp = admin.delete(f"{base_url}/api/memory/lessons/{knowledge_id}")
        assert resp.status_code in (200, 204), resp.text
        resp = admin.get(f"{base_url}/api/memory/lessons/{knowledge_id}")
        assert resp.status_code == 404
        print("✓ Delete lesson OK")


# ── Entity Type Config ─────────────────────────────────────────────────────────

class TestEntityTypeConfig:

    def test_get_contact_config(self, admin, base_url):
        resp = admin.get(f"{base_url}/api/memory/entity-type-config/contact")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "intelligence_extraction_threshold" in data
        assert "ner_enabled" in data
        print(f"✓ Entity type config for contact: threshold={data['intelligence_extraction_threshold']}")

    def test_patch_entity_type_config(self, admin, base_url):
        resp = admin.patch(f"{base_url}/api/memory/entity-type-config/contact", json={
            "intelligence_extraction_threshold": 15,
            "ner_confidence_threshold": 0.6,
        })
        assert resp.status_code == 200, resp.text
        # Restore
        admin.patch(f"{base_url}/api/memory/entity-type-config/contact", json={
            "intelligence_extraction_threshold": 10,
            "ner_confidence_threshold": 0.5,
        })
        print("✓ Entity type config patch OK")

    def test_entity_type_config_requires_auth(self, api_client, base_url):
        api_client.headers.pop("Authorization", None)
        api_client.headers.pop("X-API-Key", None)
        resp = api_client.get(f"{base_url}/api/memory/entity-type-config/contact")
        assert resp.status_code == 401
        print("✓ Entity type config requires admin auth")


# ── Manual Triggers ───────────────────────────────────────────────────────────

class TestManualTriggers:

    def test_trigger_generate_memories(self, admin, base_url):
        resp = admin.post(f"{base_url}/api/memory/trigger/generate-memories")
        assert resp.status_code in (200, 202), resp.text
        print(f"✓ Generate memories trigger: {resp.status_code}")

    def test_trigger_compact(self, admin, base_url):
        resp = admin.post(f"{base_url}/api/memory/trigger/compact/contact/test-contact-001")
        assert resp.status_code in (200, 202, 404), resp.text
        # 404 acceptable if entity has no memories yet
        print(f"✓ Compact trigger: {resp.status_code}")

    def test_triggers_require_auth(self, api_client, base_url):
        api_client.headers.pop("Authorization", None)
        resp = api_client.post(f"{base_url}/api/memory/trigger/generate-memories")
        assert resp.status_code == 401
        print("✓ Triggers require admin auth")


# ── Audit Log ─────────────────────────────────────────────────────────────────

class TestAuditLog:

    def test_list_audit_log(self, admin, base_url):
        resp = admin.get(f"{base_url}/api/memory/audit-log")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "entries" in data or isinstance(data, list)
        print("✓ Audit log accessible")

    def test_audit_log_requires_auth(self, api_client, base_url):
        api_client.headers.pop("Authorization", None)
        resp = api_client.get(f"{base_url}/api/memory/audit-log")
        assert resp.status_code == 401
        print("✓ Audit log requires admin auth")
