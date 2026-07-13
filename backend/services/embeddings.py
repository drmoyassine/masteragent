"""services/embeddings.py — Embedding generation via admin-configured API"""
import logging
import os
from typing import List

import httpx

from services.config_helpers import get_llm_config
from services.job_safety import ProviderStopError, provider_stop_from_response, record_provider_stop

logger = logging.getLogger(__name__)

# OpenAI embedding models accept a maximum of 8192 tokens per input. A
# conservative character cap prevents oversized records from rejecting an
# otherwise valid batch; the batch backfill also isolates any provider error
# that remains after this guard.
try:
    _MAX_INPUT_CHARS = max(1000, int(os.getenv("EMBEDDING_MAX_INPUT_CHARS", "12000")))
except (TypeError, ValueError):
    _MAX_INPUT_CHARS = 12000
    logger.warning("Invalid EMBEDDING_MAX_INPUT_CHARS; using %d", _MAX_INPUT_CHARS)


def _bounded_input(text: str) -> str:
    value = str(text or "")
    if len(value) <= _MAX_INPUT_CHARS:
        return value
    logger.warning(
        "Truncating embedding input from %d to %d characters",
        len(value), _MAX_INPUT_CHARS,
    )
    return value[:_MAX_INPUT_CHARS]


async def generate_embedding(text: str) -> List[float]:
    """Generate embedding using admin-configured API."""
    config = get_llm_config("embedding")
    if not config:
        logger.warning("Embedding config not configured")
        return []

    api_key = config.get("api_key_encrypted", "")
    api_base = config.get("api_base_url", "https://api.openai.com/v1").rstrip("/")
    model = config.get("model_name", "text-embedding-3-small")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base}/embeddings",
                headers=headers,
                json={"model": model, "input": _bounded_input(text)},
            )
            if response.status_code == 200:
                return response.json()["data"][0]["embedding"]
            provider_stop = provider_stop_from_response(
                response.status_code, response.text, response.headers.get("retry-after")
            )
            if provider_stop:
                record_provider_stop(provider_stop, source="embedding")
                raise provider_stop
            logger.error(f"Embedding call failed: {response.status_code}")
            raise RuntimeError(f"Embedding call failed: {response.status_code} - {response.text}")
    except ProviderStopError:
        raise
    except Exception as e:
        logger.error(f"Embedding call error: {e}")
        raise RuntimeError(str(e))
    return []


async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts in a single API call."""
    config = get_llm_config("embedding")
    if not config or not texts:
        return []

    api_key = config.get("api_key_encrypted", "")
    api_base = config.get("api_base_url", "https://api.openai.com/v1").rstrip("/")
    model = config.get("model_name", "text-embedding-3-small")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{api_base}/embeddings",
                headers=headers,
                json={"model": model, "input": [_bounded_input(text) for text in texts]},
            )
            if response.status_code == 200:
                # Pair vectors to input rows by the provider's explicit index,
                # rather than assuming response ordering.
                data = sorted(response.json().get("data", []), key=lambda item: item.get("index", 0))
                vectors = [item["embedding"] for item in data]
                if len(vectors) != len(texts):
                    raise RuntimeError(
                        f"Batch embedding response count mismatch: expected {len(texts)}, got {len(vectors)}"
                    )
                return vectors
            provider_stop = provider_stop_from_response(
                response.status_code, response.text, response.headers.get("retry-after")
            )
            if provider_stop:
                record_provider_stop(provider_stop, source="embedding_backfill")
                raise provider_stop
            logger.error(f"Batch embedding failed: {response.status_code}")
            raise RuntimeError(f"Batch embedding failed: {response.status_code} - {response.text}")
    except ProviderStopError:
        raise
    except Exception as e:
        logger.error(f"Batch embedding error: {e}")
        raise RuntimeError(str(e))
    return []
