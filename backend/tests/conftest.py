"""
conftest.py — Shared fixtures for the MasterAgent memory system test suite

Usage:
    cd backend
    pytest tests/ -v --tb=short

Environment:
    MEMORY_TEST_BASE_URL  — backend URL (default: http://localhost:8080)
    MEMORY_TEST_EMAIL     — admin email     (default: admin@promptsrc.com)
    MEMORY_TEST_PASSWORD  — admin password  (default: admin123)
    MEMORY_TEST_AGENT_KEY — pre-existing agent API key (optional, creates one if not set)
"""
import hashlib
import json
import os
import secrets

import pytest
import requests

BASE_URL = os.environ.get("MEMORY_TEST_BASE_URL", "http://localhost:8080").rstrip("/")
TEST_EMAIL = os.environ.get("MEMORY_TEST_EMAIL", "admin@promptsrc.com")
TEST_PASSWORD = os.environ.get("MEMORY_TEST_PASSWORD", "admin123")
PRESET_AGENT_KEY = os.environ.get("MEMORY_TEST_AGENT_KEY", "")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def auth_token(api_client):
    resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL, "password": TEST_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed ({resp.status_code}): {resp.text}")
    token = resp.json().get("token")
    if not token:
        pytest.skip("No token returned from login")
    return token


@pytest.fixture(scope="session")
def admin(api_client, auth_token):
    """Requests session with admin JWT."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    })
    return s


@pytest.fixture(scope="session")
def agent_api_key(admin):
    """
    Returns a test agent API key.
    Creates a temporary agent and deletes it at teardown.
    """
    if PRESET_AGENT_KEY:
        yield PRESET_AGENT_KEY
        return

    resp = admin.post(f"{BASE_URL}/api/memory/config/agents", json={
        "name": "TEST_Suite_Agent",
        "description": "Temporary agent for automated tests",
        "access_level": "private",
    })
    assert resp.status_code == 200, f"Could not create test agent: {resp.text}"
    data = resp.json()
    agent_id = data["id"]
    key = data["api_key"]
    yield key
    admin.delete(f"{BASE_URL}/api/memory/config/agents/{agent_id}")


@pytest.fixture(scope="session")
def agent(agent_api_key):
    """Requests session with agent X-API-Key."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-API-Key": agent_api_key,
    })
    return s
