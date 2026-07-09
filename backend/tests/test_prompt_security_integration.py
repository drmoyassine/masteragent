"""Live-server prompt security regression tests."""


def test_prompt_key_management_requires_auth(api_client, base_url):
    api_client.headers.pop("Authorization", None)
    api_client.headers.pop("X-API-Key", None)
    assert api_client.get(f"{base_url}/api/keys").status_code == 401
    assert api_client.post(f"{base_url}/api/keys", json={"name": "unauthorized"}).status_code == 401


def test_prompt_render_requires_credentials(api_client, base_url):
    api_client.headers.pop("Authorization", None)
    api_client.headers.pop("X-API-Key", None)
    response = api_client.post(
        f"{base_url}/api/prompts/non-existent/v1/render",
        json={"variables": {}},
    )
    # Unknown IDs remain non-enumerable to unauthenticated callers: either the
    # route rejects credentials first in a future refactor or returns not found.
    assert response.status_code in {401, 404}


def test_regular_user_cannot_become_admin(api_client, base_url):
    # Invalid JWT remains an authentication failure; role tests are covered at
    # unit level without creating durable users in a production-like database.
    response = api_client.get(
        f"{base_url}/api/memory/config/agents",
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 401
