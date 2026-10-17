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
