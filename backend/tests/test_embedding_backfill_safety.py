"""Focused regression tests for embedding backfill input and lock safety."""
import asyncio

import pytest

import memory_embedding_backfill
from services.embeddings import _bounded_inputs
from services.job_safety import _maintenance_stale_minutes


def test_batch_input_validation_rejects_blank_locally():
    with pytest.raises(ValueError, match="cannot be empty"):
        _bounded_inputs(["valid", "   "])


def test_isolated_embedding_skips_blank_without_provider_request(monkeypatch):
    calls = []

    async def fake_embed(texts):
        calls.append(texts)
        return [[float(index)] for index, _ in enumerate(texts)]

    monkeypatch.setattr(memory_embedding_backfill, "_embed_batch", fake_embed)
    vectors, failures = asyncio.run(
        memory_embedding_backfill._embed_batch_isolated(["first", "", "third"])
    )

    assert calls == [["first", "third"]]
    assert vectors == [[0.0], None, [1.0]]
    assert failures == {1: "Embedding source text is empty"}


def test_maintenance_stale_minutes_has_safe_fallback(monkeypatch):
    monkeypatch.setenv("MAINTENANCE_LOCK_STALE_MINUTES", "invalid")
    assert _maintenance_stale_minutes() == 30
    monkeypatch.setenv("MAINTENANCE_LOCK_STALE_MINUTES", "1")
    assert _maintenance_stale_minutes() == 5
