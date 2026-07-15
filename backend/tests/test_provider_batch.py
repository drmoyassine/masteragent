import json
import asyncio
from contextlib import contextmanager
import pytest

import memory_operation_service as operation_service
from services.provider_batch import OpenAIBatchAdapter, parse_jsonl
from memory_operation_service import (
    _bounded_total, _extract_result, _local_from_provider, _pricing, _provider_safe_manifest,
)


def test_batch_target_query_matches_additive_llm_config_schema(monkeypatch):
    queries = []

    class Cursor:
        def execute(self, query, params=None):
            queries.append(query)

        def fetchall(self):
            return []

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_db():
        yield Connection()

    monkeypatch.setattr(operation_service, "get_memory_db_context", fake_db)
    monkeypatch.setattr(operation_service, "_provider_config", lambda operation: {})

    assert operation_service._configured_batch_targets("knowledge_embedding_backfill") == []
    assert queries
    assert "c.name" not in queries[0]
    assert "c.task_type AS config_name" in queries[0]


def test_capabilities_isolates_optional_target_enumeration_failure(monkeypatch):
    class Capability:
        supported = True
        provider = "test"
        reason = None

    monkeypatch.setattr(operation_service, "_provider_config", lambda operation: {
        "id": "cfg", "provider": "test", "model_name": "model", "extra_config": {},
    })
    monkeypatch.setattr(operation_service, "provider_adapter", lambda config: type("Adapter", (), {"capabilities": lambda self: Capability()})())
    monkeypatch.setattr(operation_service, "_configured_batch_targets", lambda operation: (_ for _ in ()).throw(RuntimeError("schema mismatch")))

    result = operation_service.capabilities()

    assert set(result) == operation_service.OPERATION_KEYS
    assert all(item["provider_batch"] is False for item in result.values())
    assert all(item["targets"] == [] for item in result.values())


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


def test_run_pricing_overrides_config_without_mutating_it():
    config = {"extra_config": {"batch_input_cost_per_million": 1.0}}
    resolved = _pricing(config, {"pricing": {
        "batch_input_cost_per_million": "0.5",
        "batch_output_cost_per_million": "2.0",
    }})
    assert resolved["batch_input_cost_per_million"] == .5
    assert resolved["batch_output_cost_per_million"] == 2.0
    assert config["extra_config"]["batch_input_cost_per_million"] == 1.0
    with pytest.raises(ValueError):
        _pricing(config, {"pricing": {"batch_input_cost_per_million": -1}})


def test_provider_safe_manifest_splits_without_dropping_source_inputs():
    class Caps:
        max_requests = 2
        max_file_bytes = 10_000
        max_embedding_inputs = 3
    manifest = [
        {"custom_id": "one", "url": "/v1/embeddings", "body": {"input": ["a", "b"]}},
        {"custom_id": "two", "url": "/v1/embeddings", "body": {"input": ["c", "d"]}},
    ]
    selected = _provider_safe_manifest(manifest, Caps(), "knowledge_embedding_backfill", 2)
    assert [item["custom_id"] for item in selected] == ["one"]


def test_all_eligible_workload_is_not_silently_capped():
    assert _bounded_total({"run_all": True, "max_records": 2_500_000}) == 2_500_000
