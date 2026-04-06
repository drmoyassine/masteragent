"""
test_webhooks.py — Phase 5: Webhook source management + inbound receiver

Tests:
  - POST/GET/PATCH/DELETE  /api/memory/webhooks   (admin JWT)
  - POST /api/memory/webhooks/{id}/rotate-secret
  - POST /api/memory/webhooks/inbound/{id}        (HMAC-verified, no auth)
"""
import hashlib
import hmac
import json
import pytest


@pytest.fixture
def test_webhook_source(admin, base_url):
    """Create a webhook source and return {id, signing_secret}."""
    resp = admin.post(f"{base_url}/api/memory/webhooks", json={
        "name": "TEST Webhook Source",
        "source_system": "test_system",
        "default_interaction_type": "webhook_event",
        "default_entity_type": "contact",
        "metadata_field_map": {
            "entity_id_field": "contact_id",
            "content_field": "event_summary",
            "event_type_field": "event_name",
        },
        "event_types": [],
        "is_active": True,
    })
    assert resp.status_code in (200, 201), f"Webhook create failed: {resp.text}"
    data = resp.json()
    source_id = data["id"]
    signing_secret = data["signing_secret"]
    # Compute the stored hash (the key used in HMAC verification)
    signing_secret_hash = hashlib.sha256(signing_secret.encode()).hexdigest()
    yield {"id": source_id, "signing_secret": signing_secret, "signing_secret_hash": signing_secret_hash}
    admin.delete(f"{base_url}/api/memory/webhooks/{source_id}")


def _sign_payload(payload_bytes: bytes, secret_hash: str) -> str:
    """Compute X-Webhook-Signature header value using stored hash as HMAC key."""
    sig = hmac.new(secret_hash.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


class TestWebhookSourceManagement:

    def test_create_webhook_source(self, admin, base_url):
        resp = admin.post(f"{base_url}/api/memory/webhooks", json={
            "name": "TEST Create Source",
            "source_system": "custom",
            "default_entity_type": "contact",
            "default_interaction_type": "webhook_event",
        })
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        assert "id" in data
        assert "signing_secret" in data
        assert "inbound_url" in data
        source_id = data["id"]
        admin.delete(f"{base_url}/api/memory/webhooks/{source_id}")
        print(f"✓ Webhook source created: {source_id}")

    def test_create_requires_admin_auth(self, api_client, base_url):
        api_client.headers.pop("Authorization", None)
        resp = api_client.post(f"{base_url}/api/memory/webhooks", json={
            "name": "Should fail", "source_system": "test",
            "default_entity_type": "contact", "default_interaction_type": "webhook_event",
        })
        assert resp.status_code == 401
        print("✓ Webhook create requires admin auth")

    def test_list_webhook_sources(self, admin, base_url, test_webhook_source):
        resp = admin.get(f"{base_url}/api/memory/webhooks")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "sources" in data
        source_ids = [s["id"] for s in data["sources"]]
        assert test_webhook_source["id"] in source_ids
        print(f"✓ List webhook sources: {len(data['sources'])} found")

    def test_patch_webhook_source(self, admin, base_url, test_webhook_source):
        source_id = test_webhook_source["id"]
        resp = admin.patch(f"{base_url}/api/memory/webhooks/{source_id}", json={
            "name": "UPDATED Test Webhook",
        })
        assert resp.status_code == 200, resp.text
        print(f"✓ Patch webhook source OK: {source_id}")

    def test_rotate_secret(self, admin, base_url, test_webhook_source):
        source_id = test_webhook_source["id"]
        resp = admin.post(f"{base_url}/api/memory/webhooks/{source_id}/rotate-secret")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "signing_secret" in data
        assert data["signing_secret"] != test_webhook_source["signing_secret"]
        print(f"✓ Secret rotation OK for source {source_id}")

    def test_delete_webhook_source(self, admin, base_url):
        resp = admin.post(f"{base_url}/api/memory/webhooks", json={
            "name": "TEST Delete Source",
            "source_system": "ephemeral",
            "default_entity_type": "contact",
            "default_interaction_type": "webhook_event",
        })
        assert resp.status_code in (200, 201), resp.text
        source_id = resp.json()["id"]
        resp = admin.delete(f"{base_url}/api/memory/webhooks/{source_id}")
        assert resp.status_code in (200, 204), resp.text
        print("✓ Webhook source deletion OK")


class TestInboundWebhook:

    def test_valid_payload_creates_interaction(self, api_client, base_url, test_webhook_source):
        source_id = test_webhook_source["id"]
        secret_hash = test_webhook_source["signing_secret_hash"]

        payload = {
            "contact_id": "ext-cid-42",
            "event_name": "contact_updated",
            "event_summary": "Contact profile was updated by sales rep",
        }
        body = json.dumps(payload).encode()
        signature = _sign_payload(body, secret_hash)

        resp = api_client.post(
            f"{base_url}/api/memory/webhooks/inbound/{source_id}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("status") == "accepted"
        assert "interaction_id" in data
        print(f"✓ Inbound webhook accepted: {data['interaction_id']}")

    def test_missing_signature_rejected(self, api_client, base_url, test_webhook_source):
        source_id = test_webhook_source["id"]
        payload = {"contact_id": "test", "event_name": "test"}
        resp = api_client.post(
            f"{base_url}/api/memory/webhooks/inbound/{source_id}",
            json=payload,
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("✓ Missing signature rejected")

    def test_bad_signature_rejected(self, api_client, base_url, test_webhook_source):
        source_id = test_webhook_source["id"]
        payload = {"contact_id": "test", "event_name": "test"}
        body = json.dumps(payload).encode()

        resp = api_client.post(
            f"{base_url}/api/memory/webhooks/inbound/{source_id}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": "sha256=badhash",
            },
        )
        assert resp.status_code == 401
        print("✓ Bad signature rejected")

    def test_unknown_source_id_returns_404(self, api_client, base_url):
        payload = {"contact_id": "test", "event_name": "test"}
        body = json.dumps(payload).encode()
        resp = api_client.post(
            f"{base_url}/api/memory/webhooks/inbound/nonexistent-source-id",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": "sha256=doesntmatter",
            },
        )
        assert resp.status_code == 404
        print("✓ Unknown source ID returns 404")

    def test_whitelist_filters_event_type(self, admin, api_client, base_url):
        """Webhook with event_types whitelist should ignore non-listed events."""
        resp = admin.post(f"{base_url}/api/memory/webhooks", json={
            "name": "TEST Whitelist Source",
            "source_system": "test_whitelist",
            "default_entity_type": "contact",
            "default_interaction_type": "webhook_event",
            "metadata_field_map": {"entity_id_field": "contact_id"},
            "event_types": ["deal_closed"],
        })
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        source_id = data["id"]
        secret_hash = hashlib.sha256(data["signing_secret"].encode()).hexdigest()

        payload = {"contact_id": "cid-1", "event_name": "form_submitted"}
        body = json.dumps(payload).encode()
        signature = _sign_payload(body, secret_hash)

        resp = api_client.post(
            f"{base_url}/api/memory/webhooks/inbound/{source_id}",
            data=body,
            headers={"Content-Type": "application/json", "X-Webhook-Signature": signature},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ignored"
        print(f"✓ Non-whitelisted event ignored: {data.get('reason')}")

        admin.delete(f"{base_url}/api/memory/webhooks/{source_id}")
