"""Provider-neutral asynchronous batch transport with an OpenAI adapter."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Iterable

import httpx

from services.job_safety import ProviderStopError, provider_stop_from_response, record_provider_stop


TERMINAL_PROVIDER_STATES = {"completed", "failed", "expired", "cancelled"}


@dataclass(frozen=True)
class BatchCapabilities:
    provider: str
    supported: bool
    reason: str | None
    endpoints: tuple[str, ...]
    completion_windows: tuple[str, ...]
    max_requests: int
    max_file_bytes: int
    max_embedding_inputs: int
    supports_cancel: bool = True


class OpenAIBatchAdapter:
    provider_key = "openai"

    def __init__(self, *, api_key: str, api_base: str = "https://api.openai.com/v1"):
        self.api_key = api_key or ""
        self.api_base = (api_base or "https://api.openai.com/v1").rstrip("/")

    def capabilities(self) -> BatchCapabilities:
        return BatchCapabilities(
            provider=self.provider_key,
            supported=bool(self.api_key),
            reason=None if self.api_key else "The configured OpenAI account has no API key.",
            endpoints=("/v1/embeddings", "/v1/chat/completions", "/v1/responses"),
            completion_windows=("24h",),
            max_requests=50_000,
            max_file_bytes=200 * 1024 * 1024,
            max_embedding_inputs=50_000,
        )

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def _raise(self, response: httpx.Response, source: str) -> None:
        stop = provider_stop_from_response(
            response.status_code, response.text, response.headers.get("retry-after")
        )
        if stop:
            record_provider_stop(stop, source=source)
            raise stop
        try:
            payload = response.json()
            error = payload.get("error") or {}
            summary = {key: error.get(key) for key in ("message", "type", "code", "param") if error.get(key) is not None}
        except Exception:
            summary = {"message": "Provider returned a non-JSON error response"}
        raise RuntimeError(f"OpenAI Batch {source} failed ({response.status_code}): {json.dumps(summary)}")

    @staticmethod
    def jsonl(requests: Iterable[Dict[str, Any]]) -> bytes:
        lines = []
        for request in requests:
            lines.append(json.dumps({
                "custom_id": request["custom_id"],
                "method": "POST",
                "url": request["url"],
                "body": request["body"],
            }, separators=(",", ":"), ensure_ascii=False))
        return ("\n".join(lines) + "\n").encode("utf-8")

    async def upload(self, requests: Iterable[Dict[str, Any]], filename: str) -> str:
        content = self.jsonl(requests)
        caps = self.capabilities()
        if len(content) > caps.max_file_bytes:
            raise ValueError(f"Provider input file exceeds {caps.max_file_bytes} bytes")
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.api_base}/files", headers=self.headers,
                data={"purpose": "batch"},
                files={"file": (filename, content, "application/jsonl")},
            )
        if response.status_code not in (200, 201):
            await self._raise(response, "upload")
        return response.json()["id"]

    async def submit(self, input_file_id: str, endpoint: str, completion_window: str = "24h",
                     metadata: Dict[str, str] | None = None) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.api_base}/batches", headers={**self.headers, "Content-Type": "application/json"},
                json={"input_file_id": input_file_id, "endpoint": endpoint,
                      "completion_window": completion_window, "metadata": metadata or {}},
            )
        if response.status_code not in (200, 201):
            await self._raise(response, "submit")
        return response.json()

    async def status(self, batch_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(f"{self.api_base}/batches/{batch_id}", headers=self.headers)
        if response.status_code != 200:
            await self._raise(response, "status")
        return response.json()

    async def cancel(self, batch_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self.api_base}/batches/{batch_id}/cancel", headers=self.headers)
        if response.status_code != 200:
            await self._raise(response, "cancel")
        return response.json()

    async def file_content(self, file_id: str) -> bytes:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(f"{self.api_base}/files/{file_id}/content", headers=self.headers)
        if response.status_code != 200:
            await self._raise(response, "download")
        return response.content

    async def delete_file(self, file_id: str) -> None:
        if not file_id:
            return
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(f"{self.api_base}/files/{file_id}", headers=self.headers)
        if response.status_code not in (200, 404):
            await self._raise(response, "file cleanup")


def provider_adapter(config: Dict[str, Any]):
    provider = str(config.get("provider") or "").lower()
    api_base = str(config.get("api_base_url") or "")
    if provider == "openai" or "api.openai.com" in api_base:
        return OpenAIBatchAdapter(
            api_key=config.get("api_key_encrypted", ""),
            api_base=api_base or "https://api.openai.com/v1",
        )
    raise ValueError(f"Provider '{provider or 'unknown'}' does not support asynchronous batch processing")


def parse_jsonl(content: bytes) -> AsyncIterator[Dict[str, Any]]:
    async def _iterator():
        for raw in content.decode("utf-8", errors="replace").splitlines():
            if raw.strip():
                yield json.loads(raw)
    return _iterator()
