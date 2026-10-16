"""services/llm.py — OpenAI-compatible LLM calls"""
import json
import logging
from typing import Optional

import httpx

from services.config_helpers import get_llm_config, resolve_api_key
from services.budget import BudgetExceededError, check_budget, record_llm_usage
from services.job_safety import ProviderStopError, provider_stop_from_response, record_provider_stop

logger = logging.getLogger(__name__)

_THINK_TOOL = {
    "type": "function",
    "function": {
        "name": "think",
        "description": (
            "Use this tool to reason, analyze, and reflect before producing your final output. "
            "Call it as many times as needed to think through the problem thoroughly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "Your internal reasoning, analysis, or reflection step.",
                }
            },
            "required": ["reasoning"],
        },
    },
}


def parse_llm_json(result_text: str, context: str = ""):
    """Parse JSON from an LLM response, tolerating markdown code fences.

    Generation pipelines treat a parse failure as a failed run; without the
    raw output in the log there is no way to diagnose why. Raises ValueError
    so existing except-blocks handle it like any other LLM failure.
    """
    text = (result_text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rstrip()
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        label = f" ({context})" if context else ""
        logger.error(f"LLM JSON parse failed{label}: {e}. Raw output: {result_text[:2000]!r}")
        raise ValueError(f"LLM returned unparseable JSON: {e}")


def _build_llm_headers(api_key: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


# Reasoning-model families reject custom temperature ("Only the default (1)
# value is supported") and reject function tools unless reasoning_effort is
# sent explicitly. Detected by name so existing and future config rows are
# protected without a data migration per task_type. An explicit
# extra_config.temperature always wins (null = omit the parameter).
REASONING_MODEL_PATTERNS = (
    "luna",        # GLM reasoning family (e.g. gpt-6-luna)
    "gpt-5",
    "o1",
    "o3",
    "o4-",
    "deepseek-r",
    "qwq",
)


def _is_reasoning_model(model: str) -> bool:
    name = (model or "").lower()
    return any(pattern in name for pattern in REASONING_MODEL_PATTERNS)


def _temperature_for(config: dict, default: float):
    """Resolve request temperature. Explicit extra_config.temperature wins
    (null = omit); when the key is absent, omit for reasoning-model families
    and fall back to `default` otherwise."""
    extra = (config or {}).get("extra_config") or {}
    if "temperature" in extra:
        return extra.get("temperature")
    if _is_reasoning_model((config or {}).get("model_name", "")):
        return None
    return default


def _reasoning_effort_for(config: dict) -> Optional[str]:
    """reasoning_effort to send alongside tool calls, or None. Reasoning
    families reject function tools unless reasoning_effort is explicit
    ("none" = no native reasoning, think-tool steps still work); a config
    value overrides the safe default."""
    if not _is_reasoning_model((config or {}).get("model_name", "")):
        return None
    configured = (config or {}).get("extra_config") or {}
    return configured.get("reasoning_effort") or "none"


async def call_llm(
    prompt: str,
    system_prompt: str = None,
    max_tokens: int = 1000,
    task_type: str = "summarization",
    config_id: Optional[str] = None
) -> str:
    """Call OpenAI-compatible LLM using admin-configured settings."""
    if config_id:
        from services.config_helpers import get_llm_config_by_id
        config = get_llm_config_by_id(config_id)
    else:
        config = get_llm_config(task_type)
        
    if not config:
        logger.warning(f"LLM config not configured for {task_type}/{config_id}")
        return ""

    api_key = resolve_api_key(config)
    api_base = config.get("api_base_url", "https://api.openai.com/v1").rstrip("/")
    model = config.get("model_name", "gpt-4o-mini")
    provider = config.get("provider", "")

    # TASK-260: enforce the daily/monthly LLM budget before spending.
    check_budget(task_type)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Use max_completion_tokens as it's supported by all major providers now.
    # Temperature: config-overridable via extra_config_json; null OMITS the
    # parameter entirely; absent key omits for reasoning-model families
    # (they reject custom values — "Only the default (1) value is supported").
    temperature = _temperature_for(config, 0.3)
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            request_body = {
                "model": model,
                "messages": messages,
                "max_completion_tokens": max_tokens,
            }
            if temperature is not None:
                request_body["temperature"] = temperature

            response = await client.post(
                f"{api_base}/chat/completions",
                headers=_build_llm_headers(api_key),
                json=request_body,
            )
            if response.status_code == 200:
                data = response.json()
                record_llm_usage(task_type, model, config, data.get("usage"))
                return data["choices"][0]["message"]["content"]
            provider_stop = provider_stop_from_response(
                response.status_code, response.text, response.headers.get("retry-after")
            )
            if provider_stop:
                record_provider_stop(provider_stop, source=f"llm:{task_type}")
                raise provider_stop
            logger.error(f"LLM call failed: {response.status_code} - {response.text}")
            raise RuntimeError(f"LLM call failed: {response.status_code} - {response.text}")
    except (ProviderStopError, BudgetExceededError):
        raise
    except Exception as e:
        logger.error(f"LLM call error: {e}")
        raise RuntimeError(str(e))


async def call_llm_with_thinking(
    prompt: str,
    system_prompt: str = None,
    max_tokens: int = 1000,
    task_type: str = "summarization",
    config_id: Optional[str] = None,
    max_think_steps: int = 5,
) -> str:
    """Call LLM with n8n-style Think tool. Model reasons via think() calls before final output."""
    if config_id:
        from services.config_helpers import get_llm_config_by_id
        config = get_llm_config_by_id(config_id)
    else:
        config = get_llm_config(task_type)

    if not config:
        logger.warning(f"LLM config not configured for {task_type}/{config_id}")
        return ""

    api_key = resolve_api_key(config)
    api_base = config.get("api_base_url", "https://api.openai.com/v1").rstrip("/")
    model = config.get("model_name", "gpt-4o-mini")

    # TASK-260: enforce the daily/monthly LLM budget before spending.
    check_budget(task_type)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    think_steps = 0
    temperature = _temperature_for(config, 0.3)
    reasoning_effort = _reasoning_effort_for(config)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            while True:
                request_body = {
                    "model": model,
                    "messages": messages,
                    "max_completion_tokens": max_tokens,
                    "tools": [_THINK_TOOL],
                    "tool_choice": "auto",
                }
                if temperature is not None:
                    request_body["temperature"] = temperature
                if reasoning_effort is not None:
                    # Reasoning families reject function tools unless
                    # reasoning_effort is sent explicitly.
                    request_body["reasoning_effort"] = reasoning_effort

                response = await client.post(
                    f"{api_base}/chat/completions",
                    headers=_build_llm_headers(api_key),
                    json=request_body,
                )
                if response.status_code != 200:
                    provider_stop = provider_stop_from_response(
                        response.status_code, response.text, response.headers.get("retry-after")
                    )
                    if provider_stop:
                        record_provider_stop(provider_stop, source=f"llm:{task_type}")
                        raise provider_stop
                    logger.error(f"LLM thinking call failed: {response.status_code} - {response.text}")
                    raise RuntimeError(f"LLM call failed: {response.status_code} - {response.text}")

                data = response.json()
                record_llm_usage(task_type, model, config, data.get("usage"))
                choice = data["choices"][0]
                assistant_message = choice["message"]
                tool_calls = assistant_message.get("tool_calls") or []

                if not tool_calls:
                    return assistant_message.get("content") or ""

                # Append assistant message and echo each think() call back as a tool result
                messages.append(assistant_message)
                for tc in tool_calls:
                    if tc["function"]["name"] == "think":
                        reasoning = json.loads(tc["function"]["arguments"]).get("reasoning", "")
                        think_steps += 1
                        logger.debug(f"[think step {think_steps}] {reasoning[:120]}")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": reasoning,
                        })

                if think_steps >= max_think_steps:
                    # Budget exhausted — force final answer without tools
                    final_body = {
                        "model": model,
                        "messages": messages,
                        "max_completion_tokens": max_tokens,
                    }
                    if temperature is not None:
                        final_body["temperature"] = temperature
                    final_resp = await client.post(
                        f"{api_base}/chat/completions",
                        headers=_build_llm_headers(api_key),
                        json=final_body,
                    )
                    if final_resp.status_code == 200:
                        final_data = final_resp.json()
                        record_llm_usage(task_type, model, config, final_data.get("usage"))
                        return final_data["choices"][0]["message"].get("content") or ""
                    provider_stop = provider_stop_from_response(
                        final_resp.status_code, final_resp.text, final_resp.headers.get("retry-after")
                    )
                    if provider_stop:
                        record_provider_stop(provider_stop, source=f"llm:{task_type}")
                        raise provider_stop
                    raise RuntimeError(f"Final LLM call failed: {final_resp.status_code}")

    except (ProviderStopError, BudgetExceededError):
        raise
    except Exception as e:
        logger.error(f"LLM thinking call error: {e}")
        raise RuntimeError(str(e))


async def call_llm_vision(prompt: str, image_base64: str, mime_type: str = "image/png") -> str:
    """Call OpenAI-compatible LLM with vision for document parsing."""
    config = get_llm_config("vision")
    if not config:
        logger.warning("Vision LLM config not configured")
        return ""

    api_key = resolve_api_key(config)
    api_base = config.get("api_base_url", "https://api.openai.com/v1").rstrip("/")
    model = config.get("model_name", "gpt-4o")
    provider = config.get("provider", "")

    # TASK-260: vision calls share the global budget caps.
    check_budget("vision")

    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
    ]}]

    # Use max_completion_tokens as it's supported by all major providers now.
    # Same temperature rule as call_llm: extra_config_json overrides, null omits,
    # absent key omits for reasoning-model vision variants.
    temperature = _temperature_for(config, 0.1)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            request_body = {"model": model, "messages": messages, "max_completion_tokens": 4000}
            if temperature is not None:
                request_body["temperature"] = temperature

            response = await client.post(
                f"{api_base}/chat/completions",
                headers=_build_llm_headers(api_key),
                json=request_body,
            )
            if response.status_code == 200:
                data = response.json()
                record_llm_usage("vision", model, config, data.get("usage"))
                return data["choices"][0]["message"]["content"]
            provider_stop = provider_stop_from_response(
                response.status_code, response.text, response.headers.get("retry-after")
            )
            if provider_stop:
                record_provider_stop(provider_stop, source="vision")
                raise provider_stop
            logger.error(f"Vision LLM call failed: {response.status_code}")
            raise RuntimeError(f"Vision LLM call failed: {response.status_code} - {response.text}")
    except (ProviderStopError, BudgetExceededError):
        raise
    except Exception as e:
        logger.error(f"Vision LLM call error: {e}")
        raise RuntimeError(str(e))
