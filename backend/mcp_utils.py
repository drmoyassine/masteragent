"""
mcp_utils.py — Helpers for the MCP servers mounted by server.py.

Two responsibilities:

1. sanitize_tools_for_gemini(tools)
   FastAPI emits Pydantic v2 schemas where Optional[X] becomes
   ``anyOf: [{type: X}, {type: "null"}]`` (or, in older paths,
   ``type: ["X", "null"]``). Google's Gemini API rejects both because its
   protobuf-backed schema only accepts a single string ``type`` and does not
   know ``anyOf``/``allOf``/``oneOf``. This walker rewrites tool inputSchemas
   in place so they are Gemini-compatible while staying valid JSON Schema for
   every other client (OpenAI, Anthropic).

2. verify_mcp_service_key
   FastAPI dependency that protects the MCP endpoint themselves. Requires
   incoming requests to carry ``X-API-Key: <MCP_SERVICE_KEY>`` (the same key
   the rest of the API accepts on the memory routes).
"""
from __future__ import annotations

import os
import logging
from typing import Any

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)


# Keys Gemini's function-declaration schema understands. Anything else is
# stripped so we don't leak unsupported constructs into the tool definition.
_GEMINI_ALLOWED_KEYS = {
    "type",
    "format",
    "description",
    "enum",
    "properties",
    "required",
    "items",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "default",
    "title",
}


def _pick_non_null_branch(branches: list[dict]) -> dict | None:
    """Return the first branch whose ``type`` is not ``"null"``."""
    for b in branches:
        if isinstance(b, dict) and b.get("type") != "null":
            return b
    return None


def _sanitize_schema(node: Any) -> Any:
    """Recursively rewrite a JSON Schema node to Gemini-compatible form.

    Mutates dicts/lists in place where possible and returns the (possibly
    new) value the parent should hold.
    """
    if isinstance(node, list):
        return [_sanitize_schema(item) for item in node]

    if not isinstance(node, dict):
        return node

    # 1. anyOf / oneOf with a null branch → flatten to the non-null branch.
    #    Do NOT add nullable — n8n/langchain re-converts nullable to type arrays.
    for combiner in ("anyOf", "oneOf"):
        if combiner in node and isinstance(node[combiner], list):
            branches = node.pop(combiner)
            chosen = _pick_non_null_branch(branches) or (branches[0] if branches else {})
            # Merge chosen branch's keys into this node (chosen wins on type/format)
            for k, v in chosen.items():
                node.setdefault(k, v)
                if k in ("type", "format", "items", "properties", "enum"):
                    node[k] = v

    # 2. allOf with a single branch → merge it; multi-branch allOf is rare in
    #    FastAPI output, but if it happens we keep the first to stay valid.
    if "allOf" in node and isinstance(node["allOf"], list):
        branches = node.pop("allOf")
        if branches and isinstance(branches[0], dict):
            for k, v in branches[0].items():
                node.setdefault(k, v)

    # 3. type as a list → take first non-null
    if isinstance(node.get("type"), list):
        types = [t for t in node["type"] if t != "null"]
        node["type"] = types[0] if types else "string"

    # 4. Recurse into nested schemas.
    if "properties" in node and isinstance(node["properties"], dict):
        node["properties"] = {
            k: _sanitize_schema(v) for k, v in node["properties"].items()
        }
    if "items" in node:
        node["items"] = _sanitize_schema(node["items"])

    # 5. Default object type if missing (Gemini requires a type on each node).
    if "properties" in node and "type" not in node:
        node["type"] = "object"
    if "items" in node and "type" not in node:
        node["type"] = "array"

    # 6. Strip default:null — semantically wrong without nullable and can
    #    trigger langchain/n8n to re-introduce anyOf/type arrays.
    if node.get("default") is None and "default" in node:
        node.pop("default")

    # 7. Strip unsupported keys at this level.
    for k in list(node.keys()):
        if k not in _GEMINI_ALLOWED_KEYS:
            node.pop(k, None)

    return node


def sanitize_tools_for_gemini(tools: list) -> None:
    """Walk every tool's inputSchema and rewrite in place."""
    for tool in tools:
        schema = getattr(tool, "inputSchema", None)
        if isinstance(schema, dict):
            tool.inputSchema = _sanitize_schema(schema)
    logger.info(
        "Sanitized %d MCP tool schemas for Gemini compatibility", len(tools)
    )


# ─────────────────────────────────────────────
# MCP endpoint auth
# ─────────────────────────────────────────────

_MCP_SERVICE_KEY: str = os.environ.get("MCP_SERVICE_KEY", "")


async def verify_mcp_service_key(
    x_api_key: str = Header(None, alias="X-API-Key"),
    authorization: str = Header(None),
) -> dict:
    """Require ``X-API-Key: <MCP_SERVICE_KEY>`` (or ``Authorization: Bearer``).

    Mounted as the FastAPI dependency on both ``/api/prompts/mcp`` and
    ``/api/memory/mcp`` so n8n / other MCP clients must authenticate before
    listing or invoking tools.
    """
    if not _MCP_SERVICE_KEY:
        # Fail closed: refuse to serve MCP without a configured key.
        raise HTTPException(
            status_code=503,
            detail="MCP service key not configured on server",
        )

    if x_api_key and x_api_key == _MCP_SERVICE_KEY:
        return {"id": "mcp-service", "auth": "x-api-key"}

    if authorization and authorization == f"Bearer {_MCP_SERVICE_KEY}":
        return {"id": "mcp-service", "auth": "bearer"}

    raise HTTPException(status_code=401, detail="Invalid or missing MCP credentials")
