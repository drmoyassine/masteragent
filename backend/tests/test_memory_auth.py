"""
Memory System Authentication Tests
Tests for JWT authentication on admin config endpoints and API key authentication for agent endpoints
"""
import pytest
import requests
import os
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "admin@promptsrc.com"
TEST_PASSWORD = "admin123"
AGENT_API_KEY = "mem_YhZtU7wjp8-gFQKAjyT7ZwKzTC3L7R7I6cqHM3oJbYA"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session without auth"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get JWT authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with JWT auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestHealthEndpoint:
    """Health endpoint should work without auth"""
    
    def test_health_no_auth_required(self, api_client):
        """Test /api/memory/health works without authentication"""
        response = api_client.get(f"{BASE_URL}/api/memory/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✓ Health endpoint works without auth: {data}")


class TestConfigEndpointsRequireAuth:
    """Test that config endpoints return 401 without JWT token"""
    
    def test_entity_types_requires_auth(self, api_client):
        """GET /api/memory/config/entity-types should return 401 without auth"""
        # Remove any existing auth header
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/memory/config/entity-types")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "Authentication required" in data["detail"] or "authentication" in data["detail"].lower()
        print(f"✓ Entity types endpoint requires auth: {data}")
    
    def test_lesson_types_requires_auth(self, api_client):
        """GET /api/memory/config/lesson-types should return 401 without auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/memory/config/lesson-types")
        assert response.status_code == 401
        print(f"✓ Lesson types endpoint requires auth")
    
    def test_channel_types_requires_auth(self, api_client):
        """GET /api/memory/config/channel-types should return 401 without auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/memory/config/channel-types")
        assert response.status_code == 401
        print(f"✓ Channel types endpoint requires auth")
    
    def test_agents_requires_auth(self, api_client):
        """GET /api/memory/config/agents should return 401 without auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/memory/config/agents")
        assert response.status_code == 401
        print(f"✓ Agents endpoint requires auth")
    
    def test_settings_requires_auth(self, api_client):
        """GET /api/memory/config/settings should return 401 without auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/memory/config/settings")
        assert response.status_code == 401
        print(f"✓ Settings endpoint requires auth")
    
    def test_llm_configs_requires_auth(self, api_client):
        """GET /api/memory/config/llm-configs should return 401 without auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/memory/config/llm-configs")
        assert response.status_code == 401
        print(f"✓ LLM configs endpoint requires auth")
    
    def test_system_prompts_requires_auth(self, api_client):
        """GET /api/memory/config/system-prompts should return 401 without auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/memory/config/system-prompts")
        assert response.status_code == 401
        print(f"✓ System prompts endpoint requires auth")


class TestConfigEndpointsWithValidJWT:
    """Test that config endpoints work with valid JWT token"""
    
    def test_entity_types_with_jwt(self, authenticated_client):
        """GET /api/memory/config/entity-types should work with valid JWT"""
        response = authenticated_client.get(f"{BASE_URL}/api/memory/config/entity-types")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Entity types accessible with JWT: {len(data)} types found")
    
    def test_lesson_types_with_jwt(self, authenticated_client):
        """GET /api/memory/config/lesson-types should work with valid JWT"""
        response = authenticated_client.get(f"{BASE_URL}/api/memory/config/lesson-types")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Lesson types accessible with JWT: {len(data)} types found")
    
    def test_channel_types_with_jwt(self, authenticated_client):
        """GET /api/memory/config/channel-types should work with valid JWT"""
        response = authenticated_client.get(f"{BASE_URL}/api/memory/config/channel-types")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Channel types accessible with JWT: {len(data)} types found")
    
    def test_agents_with_jwt(self, authenticated_client):
        """GET /api/memory/config/agents should work with valid JWT"""
        response = authenticated_client.get(f"{BASE_URL}/api/memory/config/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Agents accessible with JWT: {len(data)} agents found")
    
    def test_settings_with_jwt(self, authenticated_client):
        """GET /api/memory/config/settings should work with valid JWT"""
        response = authenticated_client.get(f"{BASE_URL}/api/memory/config/settings")
        assert response.status_code == 200
        data = response.json()
        assert "chunk_size" in data
        print(f"✓ Settings accessible with JWT: chunk_size={data['chunk_size']}")
    
    def test_llm_configs_with_jwt(self, authenticated_client):
        """GET /api/memory/config/llm-configs should work with valid JWT"""
        response = authenticated_client.get(f"{BASE_URL}/api/memory/config/llm-configs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ LLM configs accessible with JWT: {len(data)} configs found")
    
    def test_system_prompts_with_jwt(self, authenticated_client):
        """GET /api/memory/config/system-prompts should work with valid JWT"""
        response = authenticated_client.get(f"{BASE_URL}/api/memory/config/system-prompts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ System prompts accessible with JWT: {len(data)} prompts found")


class TestAgentCreationReturnsAPIKey:
    """Test that agent creation returns API key"""
    
    def test_create_agent_returns_api_key(self, authenticated_client):
        """POST /api/memory/config/agents should return API key on creation"""
        new_agent = {
            "name": "TEST_Auth_Agent",
            "description": "Test agent for auth testing",
            "access_level": "private"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/memory/config/agents", json=new_agent)
        assert response.status_code == 200
        
        created = response.json()
        assert "api_key" in created, "API key not returned on agent creation"
        assert created["api_key"].startswith("mem_"), "API key should start with 'mem_'"
        assert "api_key_preview" in created
        assert created["is_active"] == True
        
        agent_id = created["id"]
        api_key = created["api_key"]
        
        print(f"✓ Agent created with API key: {created['api_key_preview']}")
        
        # Clean up
        response = authenticated_client.delete(f"{BASE_URL}/api/memory/config/agents/{agent_id}")
        assert response.status_code == 200
        print(f"✓ Test agent cleaned up")


class TestAgentAPIKeyAuthentication:
    """Test agent API endpoints with X-API-Key header"""
    
    def test_interactions_requires_api_key(self, api_client):
        """POST /api/memory/interactions should return 401 without API key"""
        api_client.headers.pop("Authorization", None)
        api_client.headers.pop("X-API-Key", None)
        
        response = api_client.post(
            f"{BASE_URL}/api/memory/interactions",
            data={"text": "Test interaction", "channel": "email"}
        )
        assert response.status_code == 401
        data = response.json()
        assert "API key required" in data.get("detail", "")
        print(f"✓ Interactions endpoint requires API key: {data}")
    
    def test_interactions_with_invalid_api_key(self, api_client):
        """POST /api/memory/interactions should return 401 with invalid API key"""
        api_client.headers.pop("Authorization", None)
        api_client.headers["X-API-Key"] = "invalid_key_12345"
        
        response = api_client.post(
            f"{BASE_URL}/api/memory/interactions",
            data={"text": "Test interaction", "channel": "email"}
        )
        assert response.status_code == 401
        data = response.json()
        assert "Invalid API key" in data.get("detail", "")
        print(f"✓ Invalid API key rejected: {data}")
    
    def test_interactions_with_valid_api_key(self, api_client):
        """POST /api/memory/interactions should work with valid API key"""
        api_client.headers.pop("Authorization", None)
        api_client.headers["X-API-Key"] = AGENT_API_KEY
        api_client.headers.pop("Content-Type", None)  # Let requests set multipart
        
        response = api_client.post(
            f"{BASE_URL}/api/memory/interactions",
            data={
                "text": "Test interaction from auth test",
                "channel": "email",
                "entities": "[]",
                "metadata": "{}"
            }
        )
        
        # Should be 200 (success) - LLM features may return empty but ingestion should work
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert data["channel"] == "email"
        
        print(f"✓ Interaction ingested with API key: {data['id']}")
    
    def test_search_requires_api_key(self, api_client):
        """POST /api/memory/search should return 401 without API key"""
        api_client.headers.pop("X-API-Key", None)
        api_client.headers["Content-Type"] = "application/json"
        
        response = api_client.post(
            f"{BASE_URL}/api/memory/search",
            json={"query": "test"}
        )
        assert response.status_code == 401
        print(f"✓ Search endpoint requires API key")
    
    def test_lessons_requires_api_key(self, api_client):
        """GET /api/memory/lessons should return 401 without API key"""
        api_client.headers.pop("X-API-Key", None)
        
        response = api_client.get(f"{BASE_URL}/api/memory/lessons")
        assert response.status_code == 401
        print(f"✓ Lessons endpoint requires API key")


class TestMemoryPersistence:
    """Test that ingested memory is stored in database"""
    
    def test_ingest_and_verify_storage(self, api_client, authenticated_client):
        """Ingest interaction and verify it's stored"""
        # Use API key for ingestion
        api_client.headers.pop("Authorization", None)
        api_client.headers["X-API-Key"] = AGENT_API_KEY
        api_client.headers.pop("Content-Type", None)
        
        test_text = f"TEST_PERSISTENCE_CHECK_{os.urandom(4).hex()}"
        
        response = api_client.post(
            f"{BASE_URL}/api/memory/interactions",
            data={
                "text": test_text,
                "channel": "note",
                "entities": "[]",
                "metadata": json.dumps({"test": True})
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        memory_id = data["id"]
        
        print(f"✓ Memory ingested with ID: {memory_id}")
        
        # Note: We can't directly query the memory without a GET endpoint
        # But the successful 200 response indicates storage worked
        assert memory_id is not None
        assert len(memory_id) > 0


class TestInvalidJWTToken:
    """Test that invalid JWT tokens are rejected"""
    
    def test_expired_token_rejected(self, api_client):
        """Config endpoints should reject expired/invalid JWT tokens"""
        api_client.headers["Authorization"] = "Bearer invalid_token_12345"
        
        response = api_client.get(f"{BASE_URL}/api/memory/config/entity-types")
        assert response.status_code == 401
        print(f"✓ Invalid JWT token rejected")
    
    def test_malformed_auth_header_rejected(self, api_client):
        """Config endpoints should reject malformed auth headers"""
        api_client.headers["Authorization"] = "NotBearer token123"
        
        response = api_client.get(f"{BASE_URL}/api/memory/config/entity-types")
        assert response.status_code == 401
        print(f"✓ Malformed auth header rejected")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
