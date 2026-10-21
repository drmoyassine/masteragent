"""Thin client for the self-hosted liteparse parse runner (DEC-110).

When PARSE_RUNNER_URL + PARSE_RUNNER_API_KEY are configured, parse_document
delegates to the runner — whose local PP-OCRv4 OCR handles text layers and
scans without a vision call — and keeps the in-process parser (including the
budget-gated call_llm_vision OCR leg) as the fallback. Net effect: most vision
spend disappears while TASK-260's budget gate and usage ledger stay intact —
the runner is never given a VLM config, so every LLM call masteragent pays
for still flows through its own seam.

The same credentials drive the runner's /transcribe endpoint (TASK-274):
audio attachments never touch /parse — they take the STT lane, so WhatsApp
voice notes are transcribed by the runner's local cascade + cloud-STT
escalation instead of a separate n8n-side Gemini call.

Failure posture is deliberately soft: unconfigured / unreachable / non-200 /
honest-empty results all return None and the caller falls through to the
in-process parser. Nothing in the ingestion path can break BECAUSE the runner
exists (DEC-106 never-drop lives at the interaction layer and is untouched).
"""
import base64
import logging
import os
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# The runner enforces its own 110s whole-request deadline; a 120s client
# timeout sees it through (runner README's client guidance).
_RUNNER_TIMEOUT = httpx.Timeout(120.0)
_RUNNER_MAX_PAGES_CAP = 50  # server-side clamp; stay inside it


def runner_configured() -> bool:
    return bool(os.environ.get("PARSE_RUNNER_URL") and os.environ.get("PARSE_RUNNER_API_KEY"))


async def _post_parse(payload: dict) -> Tuple[int, dict]:
    """HTTP seam — tests patch this. Returns (status_code, json_body)."""
    async with httpx.AsyncClient(timeout=_RUNNER_TIMEOUT) as client:
        resp = await client.post(
            os.environ["PARSE_RUNNER_URL"].rstrip("/") + "/parse",
            headers={"X-API-Key": os.environ["PARSE_RUNNER_API_KEY"]},
            json=payload,
        )
        try:
            body = resp.json()
        except Exception:
            body = {}
        return resp.status_code, body


async def parse_via_runner(
    file_content: bytes,
    filename: str,
    mime_type: str,
    max_pages: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Delegate one document to the runner.

    Returns parse_document's result shape on a usable (non-empty) result, or
    None when the runner is unconfigured / unavailable / errored / honestly
    empty. An empty runner text falls back rather than terminating: the
    in-process parser's vision leg may still find text the local OCR missed,
    and the ingestion path records parse_failed only after both attempts.
    """
    if not runner_configured():
        return None

    options: Dict[str, Any] = {}
    if max_pages is not None:
        options["maxPages"] = max(1, min(int(max_pages), _RUNNER_MAX_PAGES_CAP))
    payload = {
        "data": base64.b64encode(file_content).decode("ascii"),
        "filename": filename,
        "options": options,
    }

    try:
        status, body = await _post_parse(payload)
    except Exception as exc:
        logger.warning("parse runner unavailable (%s); falling back in-process", exc)
        return None
    if status != 200:
        logger.warning("parse runner returned HTTP %s; falling back in-process", status)
        return None

    text = (body.get("text") or "").strip()
    if not text:
        logger.info(
            "parse runner returned no text (source=%s, warnings=%s); falling back in-process",
            body.get("source"), body.get("warnings"),
        )
        return None

    source = body.get("source", "")
    page_count = int(body.get("page_count") or 0)
    return {
        "text": text,
        "pages": page_count,
        "parsed_pages": page_count,
        "has_images": source in ("ocr", "vlm") or mime_type.startswith("image/"),
        "metadata": {
            "engine": "liteparse-runner",
            "runner_source": source,
            "runner_kind": body.get("kind"),
            "runner_warnings": body.get("warnings") or [],
            "duration_ms": body.get("duration_ms"),
        },
    }


async def _post_transcribe(payload: dict) -> Tuple[int, dict]:
    """HTTP seam — tests patch this. Returns (status_code, json_body)."""
    async with httpx.AsyncClient(timeout=_RUNNER_TIMEOUT) as client:
        resp = await client.post(
            os.environ["PARSE_RUNNER_URL"].rstrip("/") + "/transcribe",
            headers={"X-API-Key": os.environ["PARSE_RUNNER_API_KEY"]},
            json=payload,
        )
        try:
            body = resp.json()
        except Exception:
            body = {}
        return resp.status_code, body


async def transcribe_via_runner(
    file_content: bytes,
    filename: str,
    mime_type: str,
) -> Optional[Dict[str, Any]]:
    """Delegate one audio clip to the runner's /transcribe endpoint.

    Returns parse_document's result shape on a usable transcript, or None
    when the runner is unconfigured / unavailable / errored / honestly
    empty. Unlike documents there is NO in-process fallback — the browser
    STT is client-side and the vision LLM cannot hear — so None becomes
    parse_failed at the interaction layer, which is the DEC-106-never-drop
    way to record "we could not transcribe this clip" instead of
    hallucinating silence.

    No language hint is sent: WhatsApp voice notes are mixed en/ar and the
    runner applies its own env-configured STT defaults (DEC-087 amendment).
    """
    if not runner_configured():
        return None

    payload = {
        "data": base64.b64encode(file_content).decode("ascii"),
        "filename": filename,
    }

    try:
        status, body = await _post_transcribe(payload)
    except Exception as exc:
        logger.warning("transcribe runner unavailable (%s) for %s [%s]", exc, filename, mime_type)
        return None
    if status != 200:
        logger.warning(
            "transcribe runner returned HTTP %s for %s [%s] (%s)",
            status, filename, mime_type, str(body.get("error") or "")[:200],
        )
        return None

    text = (body.get("text") or "").strip()
    if not text:
        logger.info(
            "transcribe runner returned no text (engine=%s, warnings=%s)",
            body.get("engine"), body.get("warnings"),
        )
        return None

    return {
        "text": text,
        "pages": 0,
        "parsed_pages": 0,
        "has_images": False,
        "metadata": {
            "engine": "liteparse-runner-stt",
            "runner_stt_engine": body.get("engine"),
            "language": body.get("language"),
            "confidence": body.get("confidence"),
            "runner_warnings": body.get("warnings") or [],
            "duration_ms": body.get("duration_ms"),
        },
    }
