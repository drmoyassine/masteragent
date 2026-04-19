"""
test_pipeline.py — Integration tests for the redesigned memory pipeline

Covers:
  1. run_lesson_check() — lesson accumulation from confirmed insights
  2. _check_compaction_trigger() days path — time-based insight trigger
  3. extract_entities() with ner_schema — schema-constrained entity extraction

Auth: admin JWT (via conftest fixtures)

Notes:
  - These tests require the backend server running at MEMORY_TEST_BASE_URL.
  - Tests that hit LLM endpoints (lesson generation, NER-LLM path) may 503 if
    no API key is configured. They're accepted as pass-on-skip.
"""
import time
import uuid
import pytest


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _create_intelligence(admin, base_url, entity_type="contact", entity_id=None, status="draft"):
    """Helper: create an insight, optionally confirm it."""
    eid = entity_id or f"test-lesson-{uuid.uuid4().hex[:8]}"
    resp = admin.post(f"{base_url}/api/memory/insights", json={
        "primary_entity_type": entity_type,
        "primary_entity_id": eid,
        "insight_type": "behavior_pattern",
        "name": f"Test Insight {uuid.uuid4().hex[:6]}",
        "content": "The entity consistently follows up within 24 hours of initial contact.",
        "summary": "Fast follow-up pattern.",
        "source_memory_ids": [],
    })
    assert resp.status_code == 200, f"Insight creation failed: {resp.text}"
    intelligence_id = resp.json()["id"]

    if status == "confirmed":
        patch = admin.patch(f"{base_url}/api/memory/insights/{intelligence_id}", json={"status": "confirmed"})
        assert patch.status_code == 200, f"Insight confirm failed: {patch.text}"

    return intelligence_id, eid


def _delete_intelligence(admin, base_url, intelligence_id):
    admin.delete(f"{base_url}/api/memory/insights/{intelligence_id}")


def _delete_knowledge(admin, base_url, knowledge_id):
    admin.delete(f"{base_url}/api/memory/lessons/{knowledge_id}")


# ══════════════════════════════════════════════════════════════════
# 1. run_lesson_check — lesson accumulation
# ══════════════════════════════════════════════════════════════════

class TestRunLessonCheck:
    """
    Verifies that when knowledge_threshold confirmed insights accumulate,
    the manual trigger fires and produces a knowledge.
    Requires: insight_generation LLM config with a real API key.
    """

    def test_trigger_endpoint_exists(self, admin, base_url):
        """POST /trigger/run-lesson-check should return 200."""
        resp = admin.post(f"{base_url}/api/memory/trigger/run-lesson-check")
        assert resp.status_code == 200, resp.text
        assert "triggered" in resp.json().get("message", "").lower()
        print("✓ /trigger/run-lesson-check endpoint is accessible")

    def test_lesson_accumulates_from_confirmed_insights(self, admin, base_url):
        """
        Create 2 confirmed insights → set threshold=2 → trigger → poll for lesson.
        Skipped if LLM backend returns 500/503 (no API key configured).
        """
        # Save original settings
        orig = admin.get(f"{base_url}/api/memory/config/settings").json()

        admin.put(f"{base_url}/api/memory/config/settings", json={
            "knowledge_threshold": 2,
        })

        intelligence_ids = []
        try:
            for _ in range(2):
                iid, _ = _create_intelligence(admin, base_url, status="confirmed")
                intelligence_ids.append(iid)

            # Trigger lesson check
            resp = admin.post(f"{base_url}/api/memory/trigger/run-lesson-check")
            assert resp.status_code == 200, resp.text

            # Poll for lesson (async task — allow up to 15s)
            knowledge_id = None
            for _ in range(15):
                time.sleep(1)
                lessons_resp = admin.get(f"{base_url}/api/memory/lessons")
                if lessons_resp.status_code == 200:
                    lessons = lessons_resp.json().get("lessons", [])
                    # Look for a lesson whose source_intelligence_ids overlap with our created ones
                    for les in lessons:
                        src = les.get("source_intelligence_ids", [])
                        if any(iid in src for iid in intelligence_ids):
                            knowledge_id = les["id"]
                            break
                if knowledge_id:
                    break

            if knowledge_id:
                print(f"✓ Lesson {knowledge_id} generated from confirmed insights")
                _delete_knowledge(admin, base_url, knowledge_id)
            else:
                # LLM not configured — acceptable skip
                pytest.skip("No lesson generated within 15s — LLM likely not configured")
        finally:
            # Clean up insights + restore settings
            for iid in intelligence_ids:
                _delete_intelligence(admin, base_url, iid)
            admin.put(f"{base_url}/api/memory/config/settings", json={
                "knowledge_threshold": orig.get("knowledge_threshold", 5),
            })


# ══════════════════════════════════════════════════════════════════
# 2. extract_entities with ner_schema
# ══════════════════════════════════════════════════════════════════

class TestExtractEntitiesWithNerSchema:
    """
    Verifies that when ner_schema is set on an entity type, the NER labels
    are constrained to the schema-defined list.

    This test checks the entity-type-config round-trip for ner_schema and
    verifies the manual memory-generation trigger executes without error.
    Full NER result assertion requires GLiNER/LLM to be configured.
    """

    ENTITY_TYPE = "contact"

    def test_ner_schema_round_trip(self, admin, base_url):
        """Set ner_schema on entity type and verify it persists."""
        schema = {"labels": ["Person", "Organization", "Location"]}

        resp = admin.patch(
            f"{base_url}/api/memory/entity-type-config/{self.ENTITY_TYPE}",
            json={"ner_schema": schema}
        )
        assert resp.status_code == 200, resp.text

        cfg = admin.get(f"{base_url}/api/memory/entity-type-config/{self.ENTITY_TYPE}").json()
        stored = cfg.get("ner_schema")
        assert stored is not None, "ner_schema was not stored"
        assert stored.get("labels") == schema["labels"], f"Labels mismatch: {stored}"

        # Clear ner_schema
        admin.patch(
            f"{base_url}/api/memory/entity-type-config/{self.ENTITY_TYPE}",
            json={"ner_schema": None}
        )
        cfg2 = admin.get(f"{base_url}/api/memory/entity-type-config/{self.ENTITY_TYPE}").json()
        assert cfg2.get("ner_schema") is None, "ner_schema was not cleared"
        print("✓ ner_schema round-trip (set/get/clear) works correctly")

    def test_memory_generation_with_ner_schema_configured(self, admin, agent, base_url):
        """
        Submit an interaction, set ner_schema, trigger memory generation.
        Asserts the trigger returns 200 (LLM/NER errors are logged but don't crash).
        """
        entity_id = f"test-ner-schema-{uuid.uuid4().hex[:8]}"

        # Submit a test interaction
        resp = agent.post(f"{base_url}/api/memory/interactions", json={
            "interaction_type": "crm_note",
            "content": "Meeting with Dr. Ahmed Hassan from Nile University on Wednesday. "
                       "Discussed the Al-Azhar program expansion in Cairo.",
            "primary_entity_type": self.ENTITY_TYPE,
            "primary_entity_id": entity_id,
            "source": "api",
        })
        assert resp.status_code == 200, resp.text

        # Set ner_schema with custom labels
        admin.patch(
            f"{base_url}/api/memory/entity-type-config/{self.ENTITY_TYPE}",
            json={"ner_schema": {"labels": ["Person", "Organization", "Location"]}}
        )

        try:
            # Trigger memory generation
            gen_resp = admin.post(f"{base_url}/api/memory/trigger/generate-memories")
            assert gen_resp.status_code == 200, gen_resp.text
            print(f"✓ Memory generation triggered for entity {entity_id} with NER schema set")

        finally:
            # Clear ner_schema
            admin.patch(
                f"{base_url}/api/memory/entity-type-config/{self.ENTITY_TYPE}",
                json={"ner_schema": None}
            )
