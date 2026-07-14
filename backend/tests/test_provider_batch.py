import json
import asyncio

from services.provider_batch import OpenAIBatchAdapter, parse_jsonl
from memory_operation_service import _extract_result, _local_from_provider


def test_openai_jsonl_preserves_custom_ids_and_request_bodies():
    content = OpenAIBatchAdapter.jsonl([
        {"custom_id": "one", "url": "/v1/embeddings", "body": {"model": "m", "input": ["a"]}},
        {"custom_id": "two", "url": "/v1/embeddings", "body": {"model": "m", "input": ["b"]}},
    ])
    lines = [json.loads(line) for line in content.decode().splitlines()]
    assert [line["custom_id"] for line in lines] == ["one", "two"]
    assert lines[0] == {"custom_id": "one", "method": "POST", "url": "/v1/embeddings",
                        "body": {"model": "m", "input": ["a"]}}


def test_jsonl_results_are_read_by_identity_not_position():
    content = b'{"custom_id":"two","response":{"status_code":200,"body":{"data":[]}}}\n' \
              b'{"custom_id":"one","response":{"status_code":200,"body":{"data":[]}}}\n'
    async def collect():
        return [row async for row in parse_jsonl(content)]
    rows = asyncio.run(collect())
    assert [row["custom_id"] for row in rows] == ["two", "one"]


def test_provider_status_maps_to_explicit_local_state():
    assert _local_from_provider("validating") == "provider_validating"
    assert _local_from_provider("in_progress") == "provider_in_progress"
    assert _local_from_provider("finalizing") == "provider_finalizing"
    assert _local_from_provider("completed") == "importing"
    assert _local_from_provider("expired") == "expired"


def test_result_parser_separates_usage_and_errors():
    result, usage, error = _extract_result({"response": {"status_code": 200, "body": {
        "choices": [{"message": {"content": '{"ok":true}'}}], "usage": {"total_tokens": 12}
    }}})
    assert result == '{"ok":true}'
    assert usage["total_tokens"] == 12
    assert error is None

    result, _, error = _extract_result({"response": {"status_code": 400, "body": {
        "error": {"message": "bad input"}
    }}})
    assert result is None
    assert error["message"] == "bad input"
