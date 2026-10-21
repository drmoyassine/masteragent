"""
test_parse_runner.py — liteparse runner delegation (DEC-110).

parse_document must prefer the configured runner (local OCR, no vision call),
fall back to the in-process parser on every runner non-result, and never let
the runner break the ingestion contract:
  1. Unconfigured env → no HTTP at all, in-process path serves the document.
  2. Runner 200 + text → mapped into parse_document's result shape.
  3. Runner 200 + honest-empty text → falls back (vision leg may still find it).
  4. Runner HTTP error / exception / non-200 → falls back.
  5. max_pages passes through clamped to the server-side 1–50 range.
  6. Prompt overrides and progress callbacks bypass the runner entirely
     (in-process-only features).
"""
from unittest.mock import AsyncMock, patch

import pytest

from services.parse_runner import parse_via_runner, runner_configured

_ENV = {"PARSE_RUNNER_URL": "http://runner.test:9999", "PARSE_RUNNER_API_KEY": "test-key"}


def _configured(monkeypatch):
    for k, v in _ENV.items():
        monkeypatch.setenv(k, v)


def _unconfigured(monkeypatch):
    monkeypatch.delenv("PARSE_RUNNER_URL", raising=False)
    monkeypatch.delenv("PARSE_RUNNER_API_KEY", raising=False)


def _runner_body(text="parsed text", source="native", kind="pdf", pages=2):
    return {"text": text, "kind": kind, "source": source,
            "page_count": pages, "warnings": [], "duration_ms": 42.5}


class TestRunnerClient:

    @pytest.mark.asyncio
    async def test_unconfigured_returns_none_without_http(self, monkeypatch):
        _unconfigured(monkeypatch)
        assert runner_configured() is False
        with patch("services.parse_runner._post_parse", new_callable=AsyncMock) as mock_post:
            assert await parse_via_runner(b"pdf-bytes", "scan.pdf", "application/pdf") is None
        mock_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_maps_to_parse_document_shape(self, monkeypatch):
        _configured(monkeypatch)
        with patch("services.parse_runner._post_parse",
                   new_callable=AsyncMock, return_value=(200, _runner_body(source="ocr"))):
            result = await parse_via_runner(b"img-bytes", "scan.pdf", "application/pdf")
        assert result is not None
        assert result["text"] == "parsed text"
        assert result["pages"] == 2
        assert result["parsed_pages"] == 2
        assert result["has_images"] is True  # ocr source ⇒ images were involved
        assert result["metadata"]["engine"] == "liteparse-runner"
        assert result["metadata"]["runner_source"] == "ocr"

    @pytest.mark.asyncio
    async def test_honest_empty_text_falls_back(self, monkeypatch):
        """Empty text + warnings is an honest no-text — the caller must fall
        back to the in-process parser (budgeted vision OCR) before giving up."""
        _configured(monkeypatch)
        with patch("services.parse_runner._post_parse", new_callable=AsyncMock,
                   return_value=(200, _runner_body(text="", source="none"))):
            result = await parse_via_runner(b"blurry", "photo.jpg", "image/jpeg")
        assert result is None

    @pytest.mark.asyncio
    async def test_non_200_falls_back(self, monkeypatch):
        _configured(monkeypatch)
        for status in (401, 413, 500, 503):
            with patch("services.parse_runner._post_parse", new_callable=AsyncMock,
                       return_value=(status, {"error": "x"})):
                assert await parse_via_runner(b"d", "f.pdf", "application/pdf") is None, status

    @pytest.mark.asyncio
    async def test_runner_unreachable_falls_back(self, monkeypatch):
        _configured(monkeypatch)
        with patch("services.parse_runner._post_parse",
                   new_callable=AsyncMock, side_effect=RuntimeError("connect timeout")):
            assert await parse_via_runner(b"d", "f.pdf", "application/pdf") is None

    @pytest.mark.asyncio
    async def test_max_pages_clamped_to_server_range(self, monkeypatch):
        _configured(monkeypatch)
        with patch("services.parse_runner._post_parse", new_callable=AsyncMock,
                   return_value=(200, _runner_body())) as mock_post:
            await parse_via_runner(b"d", "big.pdf", "application/pdf", max_pages=99)
        assert mock_post.call_args.args[0]["options"]["maxPages"] == 50

        with patch("services.parse_runner._post_parse", new_callable=AsyncMock,
                   return_value=(200, _runner_body())) as mock_post:
            await parse_via_runner(b"d", "big.pdf", "application/pdf", max_pages=None)
        assert mock_post.call_args.args[0]["options"] == {}


class TestParseDocumentDelegation:

    @pytest.mark.asyncio
    async def test_parse_document_prefers_runner_result(self, monkeypatch):
        _configured(monkeypatch)
        sentinel = {"text": "runner text", "pages": 1, "parsed_pages": 1,
                    "has_images": False, "metadata": {"engine": "liteparse-runner"}}
        with patch("services.parse_runner.parse_via_runner",
                   new_callable=AsyncMock, return_value=sentinel) as mock_runner, \
             patch("services.parse_runner._post_parse", new_callable=AsyncMock) as mock_post:
            from services.processing import parse_document
            result = await parse_document(b"%PDF-not-really", "doc.pdf", "application/pdf")
        assert result is sentinel
        mock_runner.assert_awaited_once()
        mock_post.assert_not_called()  # parse_document goes through the seam wrapper

    @pytest.mark.asyncio
    async def test_prompt_override_bypasses_runner(self, monkeypatch):
        _configured(monkeypatch)
        with patch("services.parse_runner.parse_via_runner",
                   new_callable=AsyncMock) as mock_runner:
            from services.processing import parse_document
            result = await parse_document(
                b"plain text body", "note.txt", "text/plain", prompt="custom prompt")
        mock_runner.assert_not_called()
        assert result["text"] == "plain text body"

    @pytest.mark.asyncio
    async def test_progress_callback_bypasses_runner(self, monkeypatch):
        _configured(monkeypatch)
        async def _progress(done, total):
            pass
        with patch("services.parse_runner.parse_via_runner",
                   new_callable=AsyncMock) as mock_runner:
            from services.processing import parse_document
            result = await parse_document(
                b"plain text body", "note.txt", "text/plain", progress_callback=_progress)
        mock_runner.assert_not_called()
        assert result["text"] == "plain text body"

    @pytest.mark.asyncio
    async def test_unconfigured_parse_document_uses_in_process_path(self, monkeypatch):
        _unconfigured(monkeypatch)
        from services.processing import parse_document
        result = await parse_document(b"plain text body", "note.txt", "text/plain")
        assert result["text"] == "plain text body"


class TestStage2RunnerOwnedFormats:
    """DEC-110 stage 2: DOCX/XLSX are runner-owned — the in-process fallback
    honestly returns no text for them instead of keeping a second parser."""

    @pytest.mark.asyncio
    async def test_structured_formats_yield_no_text_in_fallback(self, monkeypatch):
        _unconfigured(monkeypatch)
        from services.processing import parse_document
        for mime in ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
            result = await parse_document(b"PK\x03\x04-not-really", "doc." + mime.split(".")[-1], mime)
            assert result["text"] == "", mime

    @pytest.mark.asyncio
    async def test_runner_still_serves_structured_formats(self, monkeypatch):
        _configured(monkeypatch)
        sentinel = {"text": "sheet contents", "pages": 1, "parsed_pages": 1,
                    "has_images": False, "metadata": {"engine": "liteparse-runner"}}
        with patch("services.parse_runner.parse_via_runner",
                   new_callable=AsyncMock, return_value=sentinel) as mock_runner:
            from services.processing import parse_document
            result = await parse_document(
                b"PK\x03\x04", "book.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        assert result is sentinel
        mock_runner.assert_awaited_once()


def _transcribe_body(text="hello from the voice note", engine="moonshine-tiny-en",
                     language="en", confidence=0.87):
    return {"text": text, "language": language, "engine": engine,
            "confidence": confidence, "warnings": [], "duration_ms": 1200.0}


class TestTranscribeClient:
    """TASK-274: audio takes the runner's /transcribe lane — same soft-fail
    posture as /parse, but with NO fallback (audio cannot fall through to an
    in-process parser, so None is the honest terminal result)."""

    @pytest.mark.asyncio
    async def test_unconfigured_returns_none_without_http(self, monkeypatch):
        from services.parse_runner import transcribe_via_runner
        _unconfigured(monkeypatch)
        with patch("services.parse_runner._post_transcribe", new_callable=AsyncMock) as mock_post:
            assert await transcribe_via_runner(b"ogg-bytes", "note.ogg", "audio/ogg") is None
        mock_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_maps_to_parse_document_shape(self, monkeypatch):
        from services.parse_runner import transcribe_via_runner
        _configured(monkeypatch)
        with patch("services.parse_runner._post_transcribe",
                   new_callable=AsyncMock, return_value=(200, _transcribe_body())):
            result = await transcribe_via_runner(b"ogg-bytes", "note.ogg", "audio/ogg")
        assert result is not None
        assert result["text"] == "hello from the voice note"
        assert result["pages"] == 0 and result["parsed_pages"] == 0
        assert result["has_images"] is False
        assert result["metadata"]["engine"] == "liteparse-runner-stt"
        assert result["metadata"]["runner_stt_engine"] == "moonshine-tiny-en"
        assert result["metadata"]["confidence"] == 0.87

    @pytest.mark.asyncio
    async def test_payload_carries_audio_not_options(self, monkeypatch):
        """No language hint is sent — the runner's env-configured STT defaults
        own language selection (mixed en/ar WhatsApp traffic)."""
        from services.parse_runner import transcribe_via_runner
        _configured(monkeypatch)
        with patch("services.parse_runner._post_transcribe",
                   new_callable=AsyncMock, return_value=(200, _transcribe_body())) as mock_post:
            await transcribe_via_runner(b"ogg-bytes", "note.ogg", "audio/ogg")
        payload = mock_post.call_args.args[0]
        assert set(payload.keys()) == {"data", "filename"}
        assert payload["filename"] == "note.ogg"

    @pytest.mark.asyncio
    async def test_empty_text_is_none_not_empty_shape(self, monkeypatch):
        from services.parse_runner import transcribe_via_runner
        _configured(monkeypatch)
        with patch("services.parse_runner._post_transcribe",
                   new_callable=AsyncMock,
                   return_value=(200, _transcribe_body(text="", engine="none"))):
            assert await transcribe_via_runner(b"silence", "note.ogg", "audio/ogg") is None

    @pytest.mark.asyncio
    async def test_non_200_is_none_including_undecodable_422(self, monkeypatch):
        from services.parse_runner import transcribe_via_runner
        _configured(monkeypatch)
        for status in (401, 413, 422, 500, 503):
            with patch("services.parse_runner._post_transcribe",
                       new_callable=AsyncMock, return_value=(status, {"error": "x"})):
                assert await transcribe_via_runner(b"d", "n.ogg", "audio/ogg") is None, status

    @pytest.mark.asyncio
    async def test_runner_unreachable_is_none(self, monkeypatch):
        from services.parse_runner import transcribe_via_runner
        _configured(monkeypatch)
        with patch("services.parse_runner._post_transcribe",
                   new_callable=AsyncMock, side_effect=RuntimeError("connect timeout")):
            assert await transcribe_via_runner(b"d", "n.ogg", "audio/ogg") is None


class TestAudioBranch:
    """parse_document routes audio/* to /transcribe BEFORE the /parse
    delegation — audio never reaches the document parser."""

    @pytest.mark.asyncio
    async def test_audio_takes_transcribe_lane_not_parse(self, monkeypatch):
        _configured(monkeypatch)
        sentinel = {"text": "transcript", "pages": 0, "parsed_pages": 0,
                    "has_images": False, "metadata": {"engine": "liteparse-runner-stt"}}
        with patch("services.parse_runner.parse_via_runner",
                   new_callable=AsyncMock) as mock_parse, \
             patch("services.parse_runner.transcribe_via_runner",
                   new_callable=AsyncMock, return_value=sentinel) as mock_transcribe:
            from services.processing import parse_document
            result = await parse_document(b"OggS-bytes", "note.ogg", "audio/ogg")
        assert result is sentinel
        mock_transcribe.assert_awaited_once()
        mock_parse.assert_not_called()

    @pytest.mark.asyncio
    async def test_audio_lane_ignores_prompt_override(self, monkeypatch):
        """Prompt overrides are in-process /parse features; audio runs its lane
        unconditionally — a stale prompt must not route a voice note into the
        document parser."""
        _configured(monkeypatch)
        with patch("services.parse_runner.parse_via_runner",
                   new_callable=AsyncMock) as mock_parse, \
             patch("services.parse_runner.transcribe_via_runner",
                   new_callable=AsyncMock, return_value=None) as mock_transcribe:
            from services.processing import parse_document
            result = await parse_document(
                b"OggS-bytes", "note.ogg", "audio/ogg", prompt="extract all text")
        mock_transcribe.assert_awaited_once()
        mock_parse.assert_not_called()
        assert result["text"] == ""  # miss is an honest empty → parse_failed

    @pytest.mark.asyncio
    async def test_audio_miss_returns_honest_empty(self, monkeypatch):
        _unconfigured(monkeypatch)
        from services.processing import parse_document
        result = await parse_document(b"OggS-bytes", "note.ogg", "audio/ogg")
        assert result["text"] == ""
        assert result["metadata"] == {}
