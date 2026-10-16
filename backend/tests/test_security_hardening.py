"""TASK-259 — security hardening regression tests.

Covers:
  1. MCP_SERVICE_KEY demotion — the service key authenticates as the
     mcp-service identity WITHOUT is_admin; admin routes refuse it.
  2. Webhook HMAC — signatures verify against the plaintext secret ONLY;
     a copy of the stored secret_hash column must never authenticate
     anything; legacy rows without a decryptable secret fail closed.
  3. Agent PATCH surface — InteractionUpdateAgent carries no entity/status
     fields and rejects smuggled ones (422 semantics via pydantic).
  4. Workspace actions — intelligence updates address only retrieval-fed ids.
  5. Outbound webhook conditions — frozen column allowlist at the API (400)
     and a silent-drop sanitizer at runtime.
  6. Provider keys — decrypt at the point of use; plaintext passthrough and
     envelope roundtrip via the real core.secrets; corrupt envelope fails loud.
  7. Token versioning — tver claim semantics; signup defaults closed.
"""
import asyncio
import hashlib
import hmac

import pytest
from fastapi import HTTPException

import core.auth as core_auth
from core.auth import (
    require_auth, require_admin_auth, verify_jwt_token,
    create_access_token, _token_version_valid,
)
from core.secrets import encrypt_secret
from memory.webhooks import _verify_signature, _secret_hash_prefix
from services.config_helpers import resolve_api_key
from services.outbound_webhooks import CONDITION_COLUMNS, _sanitize_conditions


# ── 1. MCP_SERVICE_KEY demotion ──────────────────────────────────────────────

def test_service_key_authenticates_without_admin(monkeypatch):
    monkeypatch.setattr(core_auth, "_MCP_SERVICE_KEY", "svc-test-key")
    user = require_auth("Bearer svc-test-key")
    assert user["id"] == "mcp-service"
    assert not user.get("is_admin")


def test_service_key_cannot_reach_admin_routes(monkeypatch):
    monkeypatch.setattr(core_auth, "_MCP_SERVICE_KEY", "svc-test-key")
    with pytest.raises(HTTPException) as exc:
        require_admin_auth("Bearer svc-test-key")
    assert exc.value.status_code == 403


def test_service_key_via_api_key_header_is_service_not_admin(monkeypatch):
    """The X-API-Key form (core.auth.verify_api_key) returns a service row
    without is_admin — it never carried it, assert it stays that way."""
    monkeypatch.setattr(core_auth, "_MCP_SERVICE_KEY", "svc-test-key")
    row = asyncio.run(core_auth.verify_api_key("svc-test-key"))
    assert row["id"] == "mcp-service"
    assert not row.get("is_admin")


# ── 2. Webhook HMAC: plaintext-only verification ─────────────────────────────

SECRET = "probe-signing-secret"
BODY = b'{"hello": "world"}'
TS = "1760652000"


def _sig(key: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()


def test_signature_from_plaintext_secret_verifies():
    assert _verify_signature(BODY, _sig(SECRET, BODY), "ignored", plaintext_secret=SECRET)


def test_signature_with_timestamp_verifies():
    signed = f"{TS}.".encode() + BODY
    assert _verify_signature(BODY, _sig(SECRET, signed), "ignored",
                             plaintext_secret=SECRET, timestamp=TS)


def test_stored_hash_as_key_no_longer_authenticates():
    """A DB dump (secret_hash column) must NOT be enough to forge signatures —
    the historical hash-as-key fallback is removed."""
    stored_hash = hashlib.sha256(SECRET.encode()).hexdigest()
    forged = _sig(stored_hash, BODY)  # attacker signs with the leaked column value
    assert not _verify_signature(BODY, forged, stored_hash, plaintext_secret=SECRET)


def test_legacy_row_without_plaintext_fails_closed():
    stored_hash = hashlib.sha256(SECRET.encode()).hexdigest()
    forged = _sig(stored_hash, BODY)
    assert not _verify_signature(BODY, forged, stored_hash, plaintext_secret=None)
    assert not _verify_signature(BODY, None, stored_hash, plaintext_secret=None)


def test_wrong_secret_signature_rejected():
    assert not _verify_signature(BODY, _sig("not-the-secret", BODY), "ignored",
                                 plaintext_secret=SECRET)


def test_hash_prefix_is_not_forgeable():
    """The verification-only prefix stores 12 hex chars — never enough to
    reconstruct a working HMAC key."""
    prefix = _secret_hash_prefix(SECRET)
    assert len(prefix) == 12
    forged = _sig(prefix, BODY)
    assert not _verify_signature(BODY, forged, prefix, plaintext_secret=SECRET)


# ── 3. InteractionUpdateAgent (agent PATCH surface) ──────────────────────────

def test_agent_update_accepts_allowed_fields_only():
    from memory_system.store.models import InteractionUpdateAgent
    u = InteractionUpdateAgent(interaction_type="note", content="refined")
    dumped = u.model_dump(exclude_unset=True)
    assert dumped == {"interaction_type": "note", "content": "refined"}


def test_agent_update_rejects_status_smuggling():
    from memory_system.store.models import InteractionUpdateAgent
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        InteractionUpdateAgent(status="done")


def test_agent_update_rejects_entity_smuggling():
    from memory_system.store.models import InteractionUpdateAgent
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        InteractionUpdateAgent(primary_entity_type="contact")
    with pytest.raises(ValidationError):
        InteractionUpdateAgent(primary_entity_id="abc")


# ── 4. Workspace actions: retrieval-fed allowlist ────────────────────────────

def test_workspace_update_rejects_id_not_in_context():
    """An id the retrieval never returned must be skipped WITHOUT touching the
    database (the allowlist check precedes any DB access), and the rejection
    must be audit-logged."""
    from memory.workspace import _execute_actions
    text = (
        "```action\n"
        '{"type": "update_intelligence", "id": "invented-id", "content": "x"}\n'
        "```"
    )
    called = {"db": False, "audit": []}

    import memory.workspace as ws
    real_ctx, real_audit = ws.get_memory_db_context, ws.log_audit

    def _tripwire():
        called["db"] = True
        raise AssertionError("DB must not be touched for non-allowlisted ids")

    ws.get_memory_db_context = _tripwire
    ws.log_audit = lambda *a, **kw: called["audit"].append((a[0], a[1]))
    try:
        results = asyncio.run(_execute_actions(
            text, "contact", "c1", {"id": "agent-x"},
            allowed_intelligence_ids={"real-id"},
        ))
    finally:
        ws.get_memory_db_context, ws.log_audit = real_ctx, real_audit
    assert results == []
    assert not called["db"]
    assert called["audit"] == [("agent-x", "workspace_action_rejected")]


def test_workspace_update_accepts_allowlisted_id(monkeypatch):
    """An allowlisted id passes the gate and reaches an entity-constrained
    UPDATE (stubbed at the DB boundary; the SQL shape is asserted)."""
    from memory.workspace import _execute_actions
    import memory.workspace as ws

    captured = {}

    class FakeCursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

    class FakeConn:
        def cursor(self):
            return FakeCursor()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(ws, "get_memory_db_context", lambda: FakeConn())
    monkeypatch.setattr(ws, "log_audit", lambda *a, **kw: None)
    text = (
        "```action\n"
        '{"type": "update_intelligence", "id": "real-id", "content": "x"}\n'
        "```"
    )
    results = asyncio.run(_execute_actions(
        text, "contact", "c1", {"id": "agent-x"},
        allowed_intelligence_ids={"real-id"},
    ))
    assert len(results) == 1 and results[0].id == "real-id"
    assert "primary_entity_type = %s" in captured["sql"]
    assert "primary_entity_id = %s" in captured["sql"]
    # Param tail: content, entity_type, entity_id, insight_id
    assert captured["params"] == ["x", "contact", "c1", "real-id"]


# ── 5. Outbound webhook condition allowlist ──────────────────────────────────

def test_condition_allowlist_is_frozen_and_sane():
    assert isinstance(CONDITION_COLUMNS, frozenset)
    assert "interaction_type" in CONDITION_COLUMNS
    assert "1=1; --" not in CONDITION_COLUMNS


def test_sanitize_conditions_drops_unknown_keys():
    clean = _sanitize_conditions(
        {"interaction_type": ["note"], "evil_key; DROP TABLE x": "v"},
        "test-webhook",
    )
    assert clean == {"interaction_type": ["note"]}


def test_sanitize_conditions_passes_known_keys():
    conds = {"source": "email", "has_attachments": True}
    assert _sanitize_conditions(conds, "w") == conds


def test_sanitize_conditions_handles_non_dict():
    assert _sanitize_conditions(None, "w") == {}
    assert _sanitize_conditions("[]", "w") == {}
    assert _sanitize_conditions([("a", 1)], "w") == {}


def test_admin_webhook_conditions_reject_unknown_key_with_400():
    from memory.admin import _validate_webhook_conditions
    with pytest.raises(HTTPException) as exc:
        _validate_webhook_conditions({"not_a_column": "x"})
    assert exc.value.status_code == 400
    # Valid conditions pass silently.
    _validate_webhook_conditions({"interaction_type": ["note"]})


# ── 6. Provider API keys: decrypt at the point of use ────────────────────────

def test_resolve_api_key_empty_cases():
    assert resolve_api_key(None) == ""
    assert resolve_api_key({}) == ""
    assert resolve_api_key({"api_key_encrypted": None}) == ""


def test_resolve_api_key_plaintext_passthrough():
    """Legacy rows stored pre-encryption must keep working."""
    assert resolve_api_key({"api_key_encrypted": "sk-legacy-plain"}) == "sk-legacy-plain"


def test_resolve_api_key_envelope_roundtrip():
    """A sealed envelope decrypts back to the original key (real core.secrets)."""
    sealed = encrypt_secret("sk-live-123")
    assert sealed != "sk-live-123"  # actually sealed
    assert resolve_api_key({"api_key_encrypted": sealed}) == "sk-live-123"


def test_resolve_api_key_corrupt_envelope_fails_loud():
    """An undecryptable envelope must raise, not degrade into an
    unauthenticated request."""
    with pytest.raises(ValueError):
        resolve_api_key({"api_key_encrypted": "enc:v1:not-a-valid-fernet-token"})


# ── 7. Token versioning (tver) + signup posture ──────────────────────────────

def test_verify_jwt_token_returns_full_payload():
    token = create_access_token(data={"sub": "user-1", "tver": 3})
    payload = verify_jwt_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["tver"] == 3


def test_token_version_valid_semantics():
    user = {"token_version": 3}
    token = create_access_token(data={"sub": "user-1", "tver": 3})
    payload = verify_jwt_token(token)
    assert _token_version_valid(payload, user)
    # Stale: row bumped after the token was issued.
    assert not _token_version_valid(payload, {"token_version": 4})
    # Missing claim (pre-deploy legacy token) is invalid — clean-slate.
    legacy = create_access_token(data={"sub": "user-1"})
    assert not _token_version_valid(verify_jwt_token(legacy), user)
    # Non-integer tver is invalid.
    assert not _token_version_valid({"tver": "abc"}, user)


def test_signup_defaults_to_closed(monkeypatch):
    """ALLOW_PUBLIC_SIGNUP unset (the deploy default) refuses signup before
    any database access."""
    from routes.auth import signup, UserCreate
    monkeypatch.delenv("ALLOW_PUBLIC_SIGNUP", raising=False)
    called = {"db": False}

    import routes.auth as ra
    real_ctx = ra.get_db_context

    def _tripwire():
        called["db"] = True
        raise AssertionError("signup must refuse before touching the DB")

    ra.get_db_context = _tripwire
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(signup(UserCreate(
                username="probe", email="probe@example.com", password="x" * 12,
            )))
    finally:
        ra.get_db_context = real_ctx
    assert exc.value.status_code == 403
    assert not called["db"]
