"""
Memory System API Tests
Tests for the Agent-Facing Memory System extension of Prompt Manager
Covers: LLM Configs, Entity Types, Lesson Types, Channel Types, Agents, Settings
"""
import pytest
import requests
import os
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ai-memory-vault-7.preview.emergentagent.com')

# Test credentials
TEST_EMAIL = "admin@promptsrc.com"
TEST_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestMemoryHealth:
    """Memory System Health Check Tests"""
    
    def test_memory_health_endpoint(self, api_client):
        """Test /api/memory/health returns healthy status"""
        response = api_client.get(f"{BASE_URL}/api/memory/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        print(f"✓ Memory health check passed: {data}")


class TestLLMConfigs:
    """LLM Configuration API Tests"""
    
    def test_list_llm_configs(self, api_client):
        """Test GET /api/memory/config/llm-configs returns all configs"""
        response = api_client.get(f"{BASE_URL}/api/memory/config/llm-configs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 5  # Should have 5 default configs
        
        # Verify expected task types exist
        task_types = [config["task_type"] for config in data]
        expected_tasks = ["summarization", "embedding", "vision", "entity_extraction", "pii_scrubbing"]
        for task in expected_tasks:
            assert task in task_types, f"Missing task type: {task}"
        
        print(f"✓ Found {len(data)} LLM configs: {task_types}")
    
    def test_llm_config_structure(self, api_client):
        """Test LLM config response structure"""
        response = api_client.get(f"{BASE_URL}/api/memory/config/llm-configs")
        assert response.status_code == 200
        data = response.json()
        
        # Check first config has required fields
        config = data[0]
        required_fields = ["id", "task_type", "provider", "name", "is_active", "created_at", "updated_at"]
        for field in required_fields:
            assert field in config, f"Missing field: {field}"
        
        print(f"✓ LLM config structure validated: {list(config.keys())}")
    
    def test_update_llm_config(self, api_client):
        """Test PUT /api/memory/config/llm-configs/{id} updates config"""
        # First get existing configs
        response = api_client.get(f"{BASE_URL}/api/memory/config/llm-configs")
        assert response.status_code == 200
        configs = response.json()
        
        # Find summarization config to update
        summarization_config = next((c for c in configs if c["task_type"] == "summarization"), None)
        assert summarization_config is not None, "Summarization config not found"
        
        config_id = summarization_config["id"]
        
        # Update the config
        update_data = {
            "name": "Updated Summarizer Test",
            "model_name": "gpt-4o-mini-test"
        }
        response = api_client.put(f"{BASE_URL}/api/memory/config/llm-configs/{config_id}", json=update_data)
        assert response.status_code == 200
        
        updated = response.json()
        assert updated["name"] == "Updated Summarizer Test"
        assert updated["model_name"] == "gpt-4o-mini-test"
        
        # Restore original name
        restore_data = {
            "name": "OpenAI Summarizer (Configure)",
            "model_name": "gpt-4o-mini"
        }
        api_client.put(f"{BASE_URL}/api/memory/config/llm-configs/{config_id}", json=restore_data)
        
        print(f"✓ LLM config update successful for {config_id}")


class TestEntityTypes:
    """Entity Types API Tests"""
    
    def test_list_entity_types(self, api_client):
        """Test GET /api/memory/config/entity-types returns all types"""
        response = api_client.get(f"{BASE_URL}/api/memory/config/entity-types")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3  # Should have Contact, Organization, Program
        
        names = [t["name"] for t in data]
        expected = ["Contact", "Organization", "Program"]
        for name in expected:
            assert name in names, f"Missing entity type: {name}"
        
        print(f"✓ Found {len(data)} entity types: {names}")
    
    def test_create_and_delete_entity_type(self, api_client):
        """Test POST and DELETE /api/memory/config/entity-types"""
        # Create new entity type
        new_type = {
            "name": "TEST_Project",
            "description": "Test project entity type",
            "icon": "folder"
        }
        response = api_client.post(f"{BASE_URL}/api/memory/config/entity-types", json=new_type)
        assert response.status_code == 200
        
        created = response.json()
        assert created["name"] == "TEST_Project"
        assert "id" in created
        type_id = created["id"]
        
        # Verify it exists
        response = api_client.get(f"{BASE_URL}/api/memory/config/entity-types")
        types = response.json()
        assert any(t["id"] == type_id for t in types)
        
        # Delete it
        response = api_client.delete(f"{BASE_URL}/api/memory/config/entity-types/{type_id}")
        assert response.status_code == 200
        
        # Verify deletion
        response = api_client.get(f"{BASE_URL}/api/memory/config/entity-types")
        types = response.json()
        assert not any(t["id"] == type_id for t in types)
        
        print(f"✓ Entity type CRUD operations successful")


class TestEntitySubtypes:
    """Entity Subtypes API Tests"""
    
    def test_list_entity_subtypes(self, api_client):
        """Test GET /api/memory/config/entity-types/{id}/subtypes"""
        # First get Contact entity type
        response = api_client.get(f"{BASE_URL}/api/memory/config/entity-types")
        types = response.json()
        contact_type = next((t for t in types if t["name"] == "Contact"), None)
        assert contact_type is not None, "Contact entity type not found"
        
        # Get subtypes
        response = api_client.get(f"{BASE_URL}/api/memory/config/entity-types/{contact_type['id']}/subtypes")
        assert response.status_code == 200
        subtypes = response.json()
        assert isinstance(subtypes, list)
        
        # Should have default subtypes
        subtype_names = [s["name"] for s in subtypes]
        expected = ["Lead", "Partner", "Provider", "Internal", "Other"]
        for name in expected:
            assert name in subtype_names, f"Missing subtype: {name}"
        
        print(f"✓ Found {len(subtypes)} subtypes for Contact: {subtype_names}")


class TestLessonTypes:
    """Lesson Types API Tests"""
    
    def test_list_lesson_types(self, api_client):
        """Test GET /api/memory/config/lesson-types"""
        response = api_client.get(f"{BASE_URL}/api/memory/config/lesson-types")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 5  # Should have default lesson types
        
        names = [t["name"] for t in data]
        expected = ["Process", "Risk", "Sales", "Product", "Support"]
        for name in expected:
            assert name in names, f"Missing lesson type: {name}"
        
        print(f"✓ Found {len(data)} lesson types: {names}")
    
    def test_create_and_delete_lesson_type(self, api_client):
        """Test POST and DELETE /api/memory/config/lesson-types"""
        new_type = {
            "name": "TEST_Compliance",
            "description": "Test compliance lessons",
            "color": "#FF5733"
        }
        response = api_client.post(f"{BASE_URL}/api/memory/config/lesson-types", json=new_type)
        assert response.status_code == 200
        
        created = response.json()
        assert created["name"] == "TEST_Compliance"
        type_id = created["id"]
        
        # Delete it
        response = api_client.delete(f"{BASE_URL}/api/memory/config/lesson-types/{type_id}")
        assert response.status_code == 200
        
        print(f"✓ Lesson type CRUD operations successful")


class TestChannelTypes:
    """Channel Types API Tests"""
    
    def test_list_channel_types(self, api_client):
        """Test GET /api/memory/config/channel-types"""
        response = api_client.get(f"{BASE_URL}/api/memory/config/channel-types")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 6  # Should have default channel types
        
        names = [t["name"] for t in data]
        expected = ["email", "call", "meeting", "chat", "document", "note"]
        for name in expected:
            assert name in names, f"Missing channel type: {name}"
        
        print(f"✓ Found {len(data)} channel types: {names}")
    
    def test_create_and_delete_channel_type(self, api_client):
        """Test POST and DELETE /api/memory/config/channel-types"""
        new_channel = {
            "name": "TEST_slack",
            "description": "Test Slack channel",
            "icon": "slack"
        }
        response = api_client.post(f"{BASE_URL}/api/memory/config/channel-types", json=new_channel)
        assert response.status_code == 200
        
        created = response.json()
        assert created["name"] == "TEST_slack"
        channel_id = created["id"]
        
        # Delete it
        response = api_client.delete(f"{BASE_URL}/api/memory/config/channel-types/{channel_id}")
        assert response.status_code == 200
        
        print(f"✓ Channel type CRUD operations successful")


class TestAgents:
    """Agents API Tests"""
    
    def test_list_agents(self, api_client):
        """Test GET /api/memory/config/agents"""
        response = api_client.get(f"{BASE_URL}/api/memory/config/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Found {len(data)} agents")
    
    def test_create_agent_returns_api_key(self, api_client):
        """Test POST /api/memory/config/agents returns API key"""
        new_agent = {
            "name": "TEST_Email_Sync_Agent",
            "description": "Test agent for email sync",
            "access_level": "private"
        }
        response = api_client.post(f"{BASE_URL}/api/memory/config/agents", json=new_agent)
        assert response.status_code == 200
        
        created = response.json()
        assert created["name"] == "TEST_Email_Sync_Agent"
        assert "api_key" in created, "API key not returned on agent creation"
        assert created["api_key"].startswith("mem_"), "API key should start with 'mem_'"
        assert "api_key_preview" in created
        assert created["is_active"] == True
        
        agent_id = created["id"]
        api_key = created["api_key"]
        
        print(f"✓ Agent created with API key: {created['api_key_preview']}")
        
        # Clean up - delete the test agent
        response = api_client.delete(f"{BASE_URL}/api/memory/config/agents/{agent_id}")
        assert response.status_code == 200
        
        print(f"✓ Agent CRUD operations successful")
    
    def test_update_agent_status(self, api_client):
        """Test PATCH /api/memory/config/agents/{id} to toggle active status"""
        # Create agent
        new_agent = {
            "name": "TEST_Toggle_Agent",
            "description": "Test agent for toggle",
            "access_level": "private"
        }
        response = api_client.post(f"{BASE_URL}/api/memory/config/agents", json=new_agent)
        assert response.status_code == 200
        agent_id = response.json()["id"]
        
        # Toggle to inactive
        response = api_client.patch(f"{BASE_URL}/api/memory/config/agents/{agent_id}?is_active=false")
        assert response.status_code == 200
        
        # Verify status changed
        response = api_client.get(f"{BASE_URL}/api/memory/config/agents")
        agents = response.json()
        agent = next((a for a in agents if a["id"] == agent_id), None)
        assert agent is not None
        assert agent["is_active"] == False
        
        # Clean up
        api_client.delete(f"{BASE_URL}/api/memory/config/agents/{agent_id}")
        
        print(f"✓ Agent status toggle successful")


class TestMemorySettings:
    """Memory Settings API Tests"""
    
    def test_get_settings(self, api_client):
        """Test GET /api/memory/config/settings"""
        response = api_client.get(f"{BASE_URL}/api/memory/config/settings")
        assert response.status_code == 200
        data = response.json()
        
        # Verify expected fields
        expected_fields = [
            "chunk_size", "chunk_overlap",
            "auto_lesson_enabled", "auto_lesson_threshold", "lesson_approval_required",
            "pii_scrubbing_enabled", "auto_share_scrubbed",
            "rate_limit_enabled", "rate_limit_per_minute",
            "default_agent_access"
        ]
        for field in expected_fields:
            assert field in data, f"Missing settings field: {field}"
        
        print(f"✓ Memory settings retrieved: chunk_size={data['chunk_size']}, pii_enabled={data['pii_scrubbing_enabled']}")
    
    def test_update_settings(self, api_client):
        """Test PUT /api/memory/config/settings"""
        # Get current settings
        response = api_client.get(f"{BASE_URL}/api/memory/config/settings")
        original = response.json()
        
        # Update chunk size
        update_data = {"chunk_size": 500}
        response = api_client.put(f"{BASE_URL}/api/memory/config/settings", json=update_data)
        assert response.status_code == 200
        
        updated = response.json()
        assert updated["chunk_size"] == 500
        
        # Restore original
        restore_data = {"chunk_size": original["chunk_size"]}
        api_client.put(f"{BASE_URL}/api/memory/config/settings", json=restore_data)
        
        print(f"✓ Memory settings update successful")


class TestSystemPrompts:
    """System Prompts API Tests"""
    
    def test_list_system_prompts(self, api_client):
        """Test GET /api/memory/config/system-prompts"""
        response = api_client.get(f"{BASE_URL}/api/memory/config/system-prompts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Should have default prompts
        prompt_types = [p["prompt_type"] for p in data]
        expected = ["summarization", "lesson_extraction", "entity_extraction"]
        for ptype in expected:
            assert ptype in prompt_types, f"Missing prompt type: {ptype}"
        
        print(f"✓ Found {len(data)} system prompts: {prompt_types}")


class TestAuthenticationRequired:
    """Test endpoints that should work without auth (config endpoints)"""
    
    def test_config_endpoints_accessible(self, api_client):
        """Config endpoints should be accessible without auth for admin UI"""
        endpoints = [
            "/api/memory/config/llm-configs",
            "/api/memory/config/entity-types",
            "/api/memory/config/lesson-types",
            "/api/memory/config/channel-types",
            "/api/memory/config/agents",
            "/api/memory/config/settings",
            "/api/memory/config/system-prompts"
        ]
        
        for endpoint in endpoints:
            response = api_client.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 200, f"Endpoint {endpoint} failed with {response.status_code}"
        
        print(f"✓ All {len(endpoints)} config endpoints accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
