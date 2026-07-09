"""Regression tests for the security-hardening compatibility layer.

These tests are unit-level and do not require the live integration server used
by the rest of the memory suite.
"""
import asyncio
import hashlib
import hmac
from pathlib import Path

import pytest
from fastapi import HTTPException

from core import auth
from core.auth import hash_api_key
from core.safe_paths import safe_join, validate_relative_storage_path, validate_storage_component
from core.secrets import decrypt_secret, encrypt_secret, is_encrypted
from core.url_security import UnsafeURL, validate_public_http_url
from memory.webhooks import _verify_signature


def test_secret_envelope_round_trip_and_plaintext_compatibility(monkeypatch):
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "unit-test-key")
    encrypted = encrypt_secret("provider-secret")
    assert is_encrypted(encrypted)
    assert "provider-secret" not in encrypted
    assert decrypt_secret(encrypted) == "provider-secret"
    assert decrypt_secret("legacy-plaintext") == "legacy-plaintext"


def test_prompt_api_keys_are_one_way_hashed():
    raw = "pm_example-secret"
    assert hash_api_key(raw) == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in hash_api_key(raw)


@pytest.mark.parametrize("value", ["..", ".", "a/b", "a\\b", "", "bad\nname"])
def test_storage_components_reject_traversal(value):
    with pytest.raises(ValueError):
        validate_storage_component(value, "version")


def test_safe_join_stays_inside_root(tmp_path: Path):
    assert safe_join(tmp_path, "prompts", "demo").is_relative_to(tmp_path.resolve())
    with pytest.raises(ValueError):
        safe_join(tmp_path, "..", "escape")
    assert validate_relative_storage_path("prompts/demo") == "prompts/demo"


def test_admin_dependency_rejects_non_admin(monkeypatch):
    monkeypatch.setattr(auth, "require_auth", lambda authorization=None: {"id": "user", "is_admin": False})
    with pytest.raises(HTTPException) as exc:
        auth.require_admin_auth("Bearer token")
    assert exc.value.status_code == 403


def test_webhook_accepts_standard_and_legacy_signatures():
    body = b'{"event":"created"}'
    secret = "returned-signing-secret"
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()
    standard = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    legacy = hmac.new(secret_hash.encode(), body, hashlib.sha256).hexdigest()
    assert _verify_signature(body, f"sha256={standard}", secret_hash, secret)
    assert _verify_signature(body, f"sha256={legacy}", secret_hash, secret)
    assert not _verify_signature(body, "sha256=bad", secret_hash, secret)
    timestamp = "1700000000"
    timestamped = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    assert _verify_signature(body, f"sha256={timestamped}", secret_hash, secret, timestamp)


def test_document_url_rejects_localhost(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_DOCUMENT_URLS", "false")
    with pytest.raises(UnsafeURL):
        asyncio.run(validate_public_http_url("http://localhost/internal"))
