"""services/embeddings.py — Embedding generation via admin-configured API"""
import logging
from typing import List

import httpx

from services.config_helpers import get_llm_config

logger = logging.getLogger(__name__)


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
                json={"model": model, "input": text},
            )
            if response.status_code == 200:
                return response.json()["data"][0]["embedding"]
            logger.error(f"Embedding call failed: {response.status_code}")
            raise RuntimeError(f"Embedding call failed: {response.status_code} - {response.text}")
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
                json={"model": model, "input": texts},
            )
            if response.status_code == 200:
                return [item["embedding"] for item in response.json()["data"]]
            logger.error(f"Batch embedding failed: {response.status_code}")
            raise RuntimeError(f"Batch embedding failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Batch embedding error: {e}")
        raise RuntimeError(str(e))
    return []
