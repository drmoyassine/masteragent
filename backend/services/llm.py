"""services/llm.py — OpenAI-compatible LLM calls"""
import logging
from typing import Optional

import httpx

from services.config_helpers import get_llm_config

logger = logging.getLogger(__name__)


def _build_llm_headers(api_key: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def call_llm(
    prompt: str,
    system_prompt: str = None,
    max_tokens: int = 1000,
    task_type: str = "summarization",
) -> str:
    """Call OpenAI-compatible LLM using admin-configured settings."""
    config = get_llm_config(task_type)
    if not config:
        logger.warning(f"LLM config for {task_type} not configured")
        return ""

    api_key = config.get("api_key_encrypted", "")
    api_base = config.get("api_base_url", "https://api.openai.com/v1").rstrip("/")
    model = config.get("model_name", "gpt-4o-mini")
    provider = config.get("provider", "")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Use max_completion_tokens as it's supported by all major providers now
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            request_body = {
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "max_completion_tokens": max_tokens,
            }

            response = await client.post(
                f"{api_base}/chat/completions",
                headers=_build_llm_headers(api_key),
                json=request_body,
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            logger.error(f"LLM call failed: {response.status_code} - {response.text}")
            raise RuntimeError(f"LLM call failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"LLM call error: {e}")
        raise RuntimeError(str(e))
    return ""


async def call_llm_vision(prompt: str, image_base64: str, mime_type: str = "image/png") -> str:
    """Call OpenAI-compatible LLM with vision for document parsing."""
    config = get_llm_config("vision")
    if not config:
        logger.warning("Vision LLM config not configured")
        return ""

    api_key = config.get("api_key_encrypted", "")
    api_base = config.get("api_base_url", "https://api.openai.com/v1").rstrip("/")
    model = config.get("model_name", "gpt-4o")
    provider = config.get("provider", "")

    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
    ]}]

    # Use max_completion_tokens as it's supported by all major providers now
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            request_body = {"model": model, "messages": messages, "temperature": 0.1, "max_completion_tokens": 4000}

            response = await client.post(
                f"{api_base}/chat/completions",
                headers=_build_llm_headers(api_key),
                json=request_body,
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            logger.error(f"Vision LLM call failed: {response.status_code}")
            raise RuntimeError(f"Vision LLM call failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Vision LLM call error: {e}")
        raise RuntimeError(str(e))
    return ""
