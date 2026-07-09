"""Safe bounded HTTP retrieval for agent-supplied document URLs."""
import asyncio
import ipaddress
import os
import socket
from urllib.parse import urljoin, urlparse

import httpx


class UnsafeURL(ValueError):
    pass


async def validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeURL("Only public HTTP(S) URLs without embedded credentials are allowed")
    if os.environ.get("ALLOW_PRIVATE_DOCUMENT_URLS", "false").lower() in {"1", "true", "yes"}:
        return
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise UnsafeURL("Private document URLs are not allowed")
    try:
        results = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443)
    except socket.gaierror as exc:
        raise UnsafeURL("Document URL host could not be resolved") from exc
    for result in results:
        ip = ipaddress.ip_address(result[4][0])
        if not ip.is_global:
            raise UnsafeURL("Private, loopback, link-local, and reserved addresses are not allowed")


async def fetch_document(url: str) -> bytes:
    """Fetch a URL with validated redirects and a strict byte ceiling."""
    max_bytes = int(os.environ.get("MAX_DOCUMENT_BYTES", str(25 * 1024 * 1024)))
    current = url
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        for _ in range(6):
            await validate_public_http_url(current)
            async with client.stream("GET", current, headers={"Accept": "application/pdf,image/*,application/octet-stream"}) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeURL("Document redirect had no destination")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and int(length) > max_bytes:
                    raise UnsafeURL("Document exceeds the configured size limit")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > max_bytes:
                        raise UnsafeURL("Document exceeds the configured size limit")
                return bytes(chunks)
    raise UnsafeURL("Too many document redirects")
