"""
test_workspace.py — Phase 7: Entity Workspace Chat

Tests:
  - POST /api/memory/workspace/{type}/{id}/chat       (agent key)
  - POST /api/memory/workspace/{type}/{id}/chat/admin (admin JWT)
  - Auth rejection for both variants
"""
import pytest


class TestWorkspaceChatAuth:

    def test_agent_chat_requires_api_key(self, api_client, base_url):
        api_client.headers.pop("X-API-Key", None)
        api_client.headers.pop("Authorization", None)
        resp = api_client.post(
            f"{base_url}/api/memory/workspace/contact/test-001/chat",
            json={"message": "hello"}
        )
        assert resp.status_code == 401
        print("✓ Workspace chat requires API key")

    def test_admin_chat_requires_admin_auth(self, api_client, base_url):
        api_client.headers.pop("X-API-Key", None)
        api_client.headers.pop("Authorization", None)
        resp = api_client.post(
            f"{base_url}/api/memory/workspace/contact/test-001/chat/admin",
            json={"message": "hello"}
        )
        assert resp.status_code == 401
        print("✓ Admin workspace chat requires JWT")


class TestWorkspaceChatAgent:

    def test_basic_message(self, agent, base_url):
        """POST /workspace/{type}/{id}/chat returns a response."""
        resp = agent.post(
            f"{base_url}/api/memory/workspace/contact/test-contact-001/chat",
            json={
                "message": "What do we know about this contact?",
                "include_lessons": True,
            }
        )
        # 200 = success, 503 = LLM not configured
        assert resp.status_code in (200, 503), resp.text
        if resp.status_code == 200:
            data = resp.json()
            assert "response" in data
            assert "interaction_id" in data
            assert "actions_taken" in data
            assert isinstance(data["actions_taken"], list)
            print(f"✓ Workspace chat OK — context: {data.get('context_summary')}")
        else:
            print(f"✓ Workspace chat: LLM not configured (503) — endpoint reachable")

    def test_with_history(self, agent, base_url):
        """Conversation history is accepted."""
        resp = agent.post(
            f"{base_url}/api/memory/workspace/contact/test-contact-001/chat",
            json={
                "message": "Any follow-ups needed?",
                "history": [
                    {"role": "user", "content": "What do we know about this contact?"},
                    {"role": "assistant", "content": "They are a lead from Q1."},
                ],
            }
        )
        assert resp.status_code in (200, 503), resp.text
        print(f"✓ Workspace chat with history: {resp.status_code}")

    def test_missing_message_returns_422(self, agent, base_url):
        resp = agent.post(
            f"{base_url}/api/memory/workspace/contact/test-contact-001/chat",
            json={"include_lessons": True}  # no message field
        )
        assert resp.status_code == 422
        print("✓ Missing message returns 422")

    def test_with_nonexistent_skill(self, agent, base_url):
        """skill_name that doesn't exist should degrade gracefully."""
        resp = agent.post(
            f"{base_url}/api/memory/workspace/contact/test-contact-001/chat",
            json={
                "message": "Summarize this contact",
                "skill_name": "nonexistent-skill-xyz",
            }
        )
        # Should still work (falls back to default prompt)
        assert resp.status_code in (200, 503), resp.text
        print(f"✓ Unknown skill degrades gracefully: {resp.status_code}")


class TestWorkspaceChatAdmin:

    def test_admin_basic_message(self, admin, base_url):
        resp = admin.post(
            f"{base_url}/api/memory/workspace/contact/test-contact-001/chat/admin",
            json={"message": "Summarize what we know"}
        )
        assert resp.status_code in (200, 503), resp.text
        if resp.status_code == 200:
            data = resp.json()
            assert "response" in data
            assert "interaction_id" in data
        print(f"✓ Admin workspace chat: {resp.status_code}")

    def test_different_entity_types(self, admin, base_url):
        """Workspace should work for any entity type."""
        for entity_type in ["contact", "institution", "program"]:
            resp = admin.post(
                f"{base_url}/api/memory/workspace/{entity_type}/test-entity-001/chat/admin",
                json={"message": f"Test for {entity_type}"}
            )
            assert resp.status_code in (200, 503), f"{entity_type}: {resp.text}"
        print("✓ Workspace works for multiple entity types")
