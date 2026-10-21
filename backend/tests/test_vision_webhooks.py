"""
test_vision_webhooks.py — vision completion webhook delivery (006/TASK-274).

fire_vision_completion_webhooks is best-effort fire-once, but the secret
contract and the doc_type_filter semantics are load-bearing:
  1. A webhook configured with a secret is POSTed X-Webhook-Secret.
  2. A webhook without a secret is POSTed headerless (existing receivers must
     not see a new header).
  3. doc_type_filter is EXACT membership, not a prefix — the voice-transcript
     subscriber lists concrete audio mimes.
"""
import pytest

import services.vision_webhooks as vw


class _Resp:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = "ok"


class _Client:
    def __init__(self, status=200):
        self.calls = []
        self._status = status

    async def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _Resp(self._status)


class _AsyncClientCtor:
    """Stands in for httpx.AsyncClient: constructed with a timeout, used as
    an async context manager that yields the recording client."""

    def __init__(self, client):
        self._client = client

    def __call__(self, timeout=None):
        return self

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, *exc):
        return False


def _fire(monkeypatch, client, hooks):
    monkeypatch.setattr(vw, "_load_active_webhooks", lambda: hooks)
    monkeypatch.setattr(vw, "httpx", type(
        "H", (), {"AsyncClient": _AsyncClientCtor(client)})())


async def _fire_one(monkeypatch, client, hooks, mime_type="audio/ogg"):
    _fire(monkeypatch, client, hooks)
    await vw.fire_vision_completion_webhooks(
        entity_type="contact", entity_id="c-1", interaction_id="i-1",
        doc_url="https://cdn.example/note.ogg", filename="note.ogg",
        mime_type=mime_type, parsed_text="the transcript",
        source="WhatsApp Inbox WhatsApp", parsed_at="2026-10-21T00:00:00+00:00",
    )


class TestSecretHeader:

    @pytest.mark.asyncio
    async def test_secret_sent_as_header(self, monkeypatch):
        client = _Client()
        await _fire_one(monkeypatch, client, [
            {"id": "1", "name": "voice-transcripts", "url": "http://n8n/hook",
             "secret": "s3cr3t-value"},
        ])
        assert len(client.calls) == 1
        assert client.calls[0]["headers"] == {"X-Webhook-Secret": "s3cr3t-value"}

    @pytest.mark.asyncio
    async def test_no_secret_means_no_header(self, monkeypatch):
        client = _Client()
        await _fire_one(monkeypatch, client, [
            {"id": "1", "name": "legacy", "url": "http://n8n/hook", "secret": None},
        ])
        assert len(client.calls) == 1
        assert client.calls[0]["headers"] is None

    @pytest.mark.asyncio
    async def test_secret_not_leaked_into_payload(self, monkeypatch):
        """The secret rides the header only — never the JSON body, which the
        receiving workflow may re-broadcast (activity inserts, logs)."""
        client = _Client()
        await _fire_one(monkeypatch, client, [
            {"id": "1", "name": "voice-transcripts", "url": "http://n8n/hook",
             "secret": "s3cr3t-value"},
        ])
        assert "s3cr3t-value" not in str(client.calls[0]["json"])


class TestDocTypeFilter:

    @pytest.mark.asyncio
    async def test_exact_mime_membership_routes_voice_notes(self, monkeypatch):
        client = _Client()
        hooks = [{"id": "voice", "name": "voice", "url": "http://n8n/hook",
                  "doc_type_filter": ["audio/ogg", "audio/mpeg"], "secret": None}]
        await _fire_one(monkeypatch, client, hooks, mime_type="audio/ogg")
        await _fire_one(monkeypatch, client, hooks, mime_type="audio/mpeg")
        await _fire_one(monkeypatch, client, hooks, mime_type="image/png")
        assert len(client.calls) == 2  # the image parse is NOT a voice note

    @pytest.mark.asyncio
    async def test_empty_filter_receives_everything(self, monkeypatch):
        client = _Client()
        hooks = [{"id": "all", "name": "all", "url": "http://n8n/hook",
                  "doc_type_filter": None, "secret": None}]
        await _fire_one(monkeypatch, client, hooks, mime_type="audio/ogg")
        await _fire_one(monkeypatch, client, hooks, mime_type="application/pdf")
        assert len(client.calls) == 2
