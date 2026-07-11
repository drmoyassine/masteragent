"""Pure unit tests for the knowledge hygiene & consolidation system.

These tests exercise the deterministic logic (similarity math, clustering,
embedding serialization, proposal validation, canonical-field aggregation,
policy gating, settings models, and the LLM proposal pipeline with a FAKE
provider) WITHOUT a database, server, or any paid/external API.

Integration tests that require a live PostgreSQL + Redis + running backend
(e.g. the full preview/apply HTTP round-trip, transaction rollback under real
FOR UPDATE locks) live in the HTTP-based suite (conftest.py) and are not
asserted here.
"""
import asyncio
import json
import sys
import os
import types

import pytest

# Ensure backend/ is importable when pytest runs from backend/tests.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory_similarity import (  # noqa: E402
    centroid, cohesion, connected_components, cosine_similarity, edges_at_threshold,
    l2_normalize, member_to_centroid, min_mean_max, pairwise_similarities, weak_links,
)
from memory_clustering import (  # noqa: E402
    accepted_proposal_groups, discover_candidate_groups, manual_group_metrics,
)
from memory_embedding import (  # noqa: E402
    CONSOLIDATABLE_KNOWLEDGE_CATEGORIES, EMBEDDING_VERSION, build_embedding_metadata,
    embed_knowledge_fields, get_embedding_version, is_embedding_compatible,
    merge_embedding_metadata, serialize_knowledge_for_embedding,
)
from memory_consolidation_prompts import (  # noqa: E402
    CONSOLIDATION_PROMPT_VERSION, RECOMMENDATIONS, build_system_prompt, build_user_prompt,
    validate_proposal,
)
from memory_consolidation_repository import aggregate_canonical_payload  # noqa: E402


# ─── fixtures (golden category source records) ──────────────────────────────

def _row(kid, category, **kw):
    base = {
        "id": kid, "category": category, "name": f"{kid}-name", "summary": f"{kid} summary",
        "content": f"{kid} content", "signals": [], "tags": [], "metadata": {},
        "embedding": None, "status": "active", "version": 1, "visibility": "shared",
        "source_intelligence_ids": [], "source_ai_interaction_ids": [], "merge_count": 0,
        "merged_from": [], "updated_at": None, "evidence_breadth": 1,
    }
    base.update(kw)
    return base


GOLDEN = {
    "best_practices": lambda: _row("bp1", "best_practices", content="Send a same-day reply to leads.", signals=["response"]),
    "lessons_learned": lambda: _row("ll1", "lessons_learned", content="Missing a visa deadline lost the enrollment.", signals=["risk"]),
    "trade_knowledge": lambda: _row("tk1", "trade_knowledge", content="Kuwait visa requires a sponsor.", signals=["visa"], metadata={"facets": {"jurisdiction": "Kuwait"}}),
    "skill": lambda: _row("sk1", "skill", content="---\nname: x\ndescription: y\n---\n# X\nprocedure", metadata={"procedure": "do thing", "trigger_desc": "when x"}),
    "playbook": lambda: _row("pb1", "playbook", content="---\nname: p\ndescription: d\n---\n# P", metadata={"trigger_conditions": ["t1"], "steps": [{"order": 1, "action": "a"}]}),
}


def _proposal(recommendation="merge", **kw):
    p = {
        "recommendation": recommendation, "confidence": 0.9, "rationale": "r",
        "canonical": {"name": "Canonical", "summary": "s", "content": "c", "signals": ["a"], "tags": ["t"], "metadata": {}},
        "preserved_information": ["x"], "removed_repetition": ["y"], "unreconciled_information": [],
        "contradictions": [], "warnings": [], "source_traceability": [], "split_recommendations": [],
    }
    p.update(kw)
    return p


# ─── similarity primitives ───────────────────────────────────────────────────

class TestSimilarity:
    def test_cosine_identical_and_orthogonal(self):
        assert cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)
        assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
        assert cosine_similarity([1, 1], [-1, -1]) == pytest.approx(-1.0)

    def test_cosine_zero_vector_is_zero(self):
        assert cosine_similarity([0, 0], [1, 1]) == 0.0
        assert cosine_similarity([], [1]) == 0.0

    def test_l2_normalize(self):
        n = l2_normalize([3, 4])
        assert n[0] == pytest.approx(0.6) and n[1] == pytest.approx(0.8)
        assert l2_normalize([0, 0]) == [0.0, 0.0]

    def test_pairwise_deterministic_and_complete(self):
        vecs = {"b": [1, 0], "a": [1, 0], "c": [0, 1]}
        edges = pairwise_similarities(vecs)
        # 3 choose 2 = 3 edges, sorted by (a,b)
        ids = [(a, b) for a, b, _ in edges]
        assert ids == [("a", "b"), ("a", "c"), ("b", "c")]
        assert all(-1.0 <= s <= 1.0 for _, _, s in edges)

    def test_min_mean_max(self):
        assert min_mean_max([0.1, 0.5, 0.9]) == (0.1, pytest.approx(0.5), 0.9)
        assert min_mean_max([]) == (0.0, 0.0, 0.0)

    def test_centroid_and_member_to_centroid(self):
        vecs = {"a": [1, 0], "b": [1, 0]}
        c = centroid(vecs)
        m2c = member_to_centroid(vecs, c)
        assert m2c["a"] == pytest.approx(1.0)

    def test_edges_threshold_and_weak_links(self):
        pair = pairwise_similarities({"a": [1, 0], "b": [0.99, 0.01], "c": [0, 1]})
        hi = edges_at_threshold(pair, 0.9)
        assert any(a == "a" and b == "b" for a, b, _ in hi)
        assert not any(a == "a" and b == "c" for a, b, _ in hi)
        wl = weak_links({"a": 0.9, "c": 0.1}, 0.5)
        assert wl == ["c"]

    def test_connected_components_deterministic(self):
        edges = [("a", "b", 0.99), ("b", "c", 0.95)]
        comps = connected_components(["c", "b", "a", "d"], edges)
        sets = [set(c) for c in comps]
        assert {"a", "b", "c"} in sets
        assert {"d"} in sets
        # ordering deterministic by min id
        assert [min(c) for c in comps] == sorted(min(c) for c in comps)


# ─── clustering (§14.3 algorithm) ────────────────────────────────────────────

class TestClustering:
    def _recs(self):
        return [
            {"id": "a", "category": "trade_knowledge", "embedding": [1.0, 0.0, 0.0]},
            {"id": "b", "category": "trade_knowledge", "embedding": [0.99, 0.01, 0.0]},
            {"id": "c", "category": "trade_knowledge", "embedding": [0.0, 1.0, 0.0]},
            {"id": "d", "category": "trade_knowledge", "embedding": [0.0, 0.99, 0.01]},
            {"id": "e", "category": "trade_knowledge", "embedding": [0.0, 0.0, 1.0]},
        ]

    def test_two_tight_pairs_plus_singleton(self):
        g = discover_candidate_groups(self._recs(), threshold=0.95, min_size=2, max_size=5, min_cohesion=0.7, weak_link_threshold=0.5)
        accepted = accepted_proposal_groups(g, 2)
        assert len(accepted) == 2
        member_sets = {frozenset(x["member_ids"]) for x in accepted}
        assert frozenset({"a", "b"}) in member_sets
        assert frozenset({"c", "d"}) in member_sets

    def test_deterministic_under_shuffle(self):
        import random
        g = discover_candidate_groups(self._recs(), threshold=0.95, min_size=2, max_size=5, min_cohesion=0.7, weak_link_threshold=0.5)
        shuf = list(self._recs())
        random.shuffle(shuf)
        g2 = discover_candidate_groups(shuf, threshold=0.95, min_size=2, max_size=5, min_cohesion=0.7, weak_link_threshold=0.5)
        norm = lambda groups: sorted([(x["status"], tuple(sorted(x["member_ids"]))) for x in groups])
        assert norm(g) == norm(g2)

    def test_category_partitioning(self):
        recs = [
            {"id": "a", "category": "trade_knowledge", "embedding": [1.0, 0.0]},
            {"id": "b", "category": "best_practices", "embedding": [1.0, 0.0]},
        ]
        g = discover_candidate_groups(recs, threshold=0.5, min_size=2, max_size=5, min_cohesion=0.4, weak_link_threshold=0.3)
        # Never grouped cross-category → both singletons
        assert all(x["status"] == "singleton" for x in g)

    def test_oversize_component_forced_to_manual_review(self):
        # 4 near-identical records with max_size=2 → size-forced manual_review subgroups
        recs = [{"id": chr(ord('a') + i), "category": "trade_knowledge", "embedding": [1.0, float(i) * 0.0001, 0.0]} for i in range(4)]
        g = discover_candidate_groups(recs, threshold=0.9, min_size=2, max_size=2, min_cohesion=0.5, weak_link_threshold=0.3)
        accepted = accepted_proposal_groups(g, 2)
        assert accepted == []  # none auto-accepted (all manual_review)
        manual = [x for x in g if x["status"] == "manual_review"]
        assert manual and all(x["split_reason"] == "size_forced" for x in manual)
        # every subgroup ≤ max_size
        assert all(len(x["member_ids"]) <= 2 for x in manual)

    def test_weak_chain_splits(self):
        # a-b tight, b-c tight, but a-c weak → at high min_cohesion the trio splits
        recs = [
            {"id": "a", "category": "trade_knowledge", "embedding": [1.0, 0.0, 0.0]},
            {"id": "b", "category": "trade_knowledge", "embedding": [0.7, 0.7, 0.0]},
            {"id": "c", "category": "trade_knowledge", "embedding": [0.0, 1.0, 0.0]},
        ]
        g = discover_candidate_groups(recs, threshold=0.3, min_size=2, max_size=5, min_cohesion=0.9, weak_link_threshold=0.6)
        # No accepted group survives the high cohesion bar; results are singletons or manual_review
        assert accepted_proposal_groups(g, 2) == []

    def test_manual_group_metrics_reports_all(self):
        recs = self._recs()[:2]
        m = manual_group_metrics(recs)
        assert m["status"] == "manual"
        assert "cohesion" in m["metrics"] and "pairwise_min" in m["metrics"]
        assert m["category"] == "trade_knowledge"


# ─── embedding serialization ─────────────────────────────────────────────────

class TestEmbeddingSerialization:
    def test_declarative_deterministic(self):
        r = GOLDEN["best_practices"]()
        assert serialize_knowledge_for_embedding(r) == serialize_knowledge_for_embedding(r)

    def test_skill_includes_operational_fields(self):
        r = GOLDEN["skill"]()
        text = serialize_knowledge_for_embedding(r)
        assert "Procedure" in text and "When to use" in text

    def test_playbook_includes_steps_and_triggers(self):
        r = GOLDEN["playbook"]()
        text = serialize_knowledge_for_embedding(r)
        assert "When to use" in text and "Steps" in text

    def test_trade_knowledge_includes_facets(self):
        r = GOLDEN["trade_knowledge"]()
        assert "jurisdiction" in serialize_knowledge_for_embedding(r)

    def test_metadata_stamp_preserves_other_keys(self):
        meta = {"facets": {"a": 1}, "always_inject": True}
        stamped = merge_embedding_metadata(meta, model="m", vector=[0.1, 0.2], version=2)
        assert stamped["facets"] == {"a": 1}
        assert stamped["always_inject"] is True
        assert stamped["embedding"]["model"] == "m"
        assert stamped["embedding"]["version"] == 2
        assert stamped["embedding"]["dimensions"] == 2

    def test_version_compat(self):
        r = {"embedding": [0.1], "metadata": {"embedding": {"version": 2}}}
        assert is_embedding_compatible(r, 2) is True
        assert is_embedding_compatible(r, 3) is False
        assert is_embedding_compatible({"embedding": None, "metadata": {}}, 2) is False
        # legacy row without block → version 1
        assert get_embedding_version({"metadata": {}}) == 1

    def test_all_five_categories_supported(self):
        for cat in CONSOLIDATABLE_KNOWLEDGE_CATEGORIES:
            r = _row(f"x-{cat}", cat)
            assert isinstance(serialize_knowledge_for_embedding(r), str)


# ─── proposal validation ─────────────────────────────────────────────────────

class TestProposalValidation:
    @pytest.mark.parametrize("rec", RECOMMENDATIONS)
    def test_each_recommendation_enum_accepted(self, rec):
        proposal, errs = validate_proposal(_proposal(recommendation=rec), "trade_knowledge")
        # non-merge recommendations don't require a canonical block
        if rec in ("merge", "merge_with_warnings"):
            assert not errs
        else:
            assert not errs  # canonical optional for these

    def test_merge_requires_canonical(self):
        _, errs = validate_proposal({"recommendation": "merge", "confidence": 0.9}, "trade_knowledge")
        assert errs and any("canonical" in e for e in errs)

    def test_invalid_recommendation_rejected(self):
        _, errs = validate_proposal({"recommendation": "bogus"}, "trade_knowledge")
        assert errs

    def test_confidence_clamped(self):
        proposal, _ = validate_proposal(_proposal(confidence=5.0), "trade_knowledge")
        assert 0.0 <= proposal.confidence <= 1.0

    def test_non_dict_rejected(self):
        _, errs = validate_proposal(["not", "an", "object"], "trade_knowledge")
        assert errs

    def test_prompts_carry_category_rules(self):
        sys_prompt = build_system_prompt("lessons_learned")
        assert "separate incidents" in sys_prompt.lower()
        assert "lessons_learned" in sys_prompt
        user = build_user_prompt([GOLDEN["trade_knowledge"]()], {"cohesion": 0.9, "pairwise_min": 0.8, "pairwise_max": 0.99, "weak_links": []}, "trade_knowledge")
        assert "GROUPING METRICS" in user and "trade_knowledge" in user

    def test_prompt_version_pinned(self):
        assert CONSOLIDATION_PROMPT_VERSION == "v1"


# ─── canonical field aggregation (§14.4) ─────────────────────────────────────

class TestCanonicalAggregation:
    def test_union_preserves_order_dedup(self):
        rows = [
            _row("a", "trade_knowledge", signals=["x", "y"], tags=["t1"], source_intelligence_ids=["i1"], merge_count=2, merged_from=[]),
            _row("b", "trade_knowledge", signals=["y", "z"], tags=["t2"], source_intelligence_ids=["i2"], merge_count=1, merged_from=[]),
        ]
        approved = {"name": "C", "summary": "s", "content": "c", "signals": ["q"], "tags": [], "metadata": {}}
        payload, contradictions, _ = aggregate_canonical_payload(
            source_rows=rows, approved=approved, canonical_target_id="a", strategy="update_existing",
            event_id="e1", preview_id="p1", model_name="m", prompt_version="v1", origin="manual",
        )
        # approved signals first, then aggregated (deduped, order-preserved)
        assert payload["signals"][0] == "q"
        assert set(payload["signals"]) == {"q", "x", "y", "z"}
        assert set(payload["source_intelligence_ids"]) == {"i1", "i2"}
        assert set(payload["merged_from"]) == {"a", "b"}
        # merge_count = sum(2+1) + absorbed(1) = 4
        assert payload["merge_count"] == 4
        assert payload["version"] == 2  # base version 1 + 1
        assert contradictions == []

    def test_facet_conflict_forces_contradiction(self):
        rows = [
            _row("a", "trade_knowledge", metadata={"facets": {"jurisdiction": "Kuwait"}}),
            _row("b", "trade_knowledge", metadata={"facets": {"jurisdiction": "UK"}}),
        ]
        approved = {"name": "C", "summary": "", "content": "c", "signals": [], "tags": [], "metadata": {}}
        payload, contradictions, _ = aggregate_canonical_payload(
            source_rows=rows, approved=approved, canonical_target_id=None, strategy="create_new",
            event_id="e1", preview_id="p1", model_name="m", prompt_version="v1", origin="manual",
        )
        assert any("jurisdiction" in c for c in contradictions)
        assert "consolidation_conflicts" in payload["metadata"]

    def test_llm_cannot_set_system_fields(self):
        # approved metadata carries a malicious lineage override → it must NOT win
        rows = [_row("a", "trade_knowledge", version=3)]
        approved = {"name": "C", "summary": "", "content": "c", "signals": [], "tags": [],
                    "metadata": {"consolidation": {"fake": True}, "version": 999, "status": "retired"}}
        payload, _, _ = aggregate_canonical_payload(
            source_rows=rows, approved=approved, canonical_target_id=None, strategy="create_new",
            event_id="e1", preview_id="p1", model_name="m", prompt_version="v1", origin="manual",
        )
        # version comes from source (3+1=4), not the LLM's 999
        assert payload["version"] == 4
        # status stays active, lineage block is overwritten by deterministic code
        assert payload["status"] == "active"
        assert payload["metadata"]["consolidation"]["event_id"] == "e1"


# ─── policy gating (auto-apply) ──────────────────────────────────────────────

class TestPolicyGating:
    def test_merge_high_confidence_no_contradictions_allowed(self):
        from memory_consolidation_service import _policy_allows_apply
        settings = {
            "knowledge_hygiene_min_auto_confidence": 0.9,
            "knowledge_hygiene_contradiction_policy": "warn_and_merge",
            "knowledge_hygiene_category_policies": {"trade_knowledge": "auto_conservative"},
        }
        assert _policy_allows_apply(_proposal(recommendation="merge", confidence=0.95), "trade_knowledge", settings) is True

    def test_low_confidence_blocked(self):
        from memory_consolidation_service import _policy_allows_apply
        settings = {"knowledge_hygiene_min_auto_confidence": 0.9, "knowledge_hygiene_contradiction_policy": "warn_and_merge"}
        assert _policy_allows_apply(_proposal(confidence=0.7), "trade_knowledge", settings) is False

    def test_contradictions_block(self):
        from memory_consolidation_service import _policy_allows_apply
        settings = {"knowledge_hygiene_min_auto_confidence": 0.5, "knowledge_hygiene_contradiction_policy": "warn_and_merge"}
        assert _policy_allows_apply(_proposal(confidence=0.9, contradictions=["c"]), "trade_knowledge", settings) is False

    def test_manual_review_policy_blocks(self):
        from memory_consolidation_service import _policy_allows_apply
        settings = {"knowledge_hygiene_min_auto_confidence": 0.5, "knowledge_hygiene_contradiction_policy": "manual_review"}
        assert _policy_allows_apply(_proposal(confidence=0.99), "trade_knowledge", settings) is False

    def test_category_policy_blocks(self):
        from memory_consolidation_service import _policy_allows_apply
        settings = {"knowledge_hygiene_min_auto_confidence": 0.5, "knowledge_hygiene_contradiction_policy": "warn_and_merge",
                    "knowledge_hygiene_category_policies": {"trade_knowledge": "manual_only"}}
        assert _policy_allows_apply(_proposal(confidence=0.99), "trade_knowledge", settings) is False


# ─── settings models ─────────────────────────────────────────────────────────

class TestSettingsModels:
    def test_update_accepts_all_hygiene_fields(self):
        from memory_models import MemorySettingsUpdate
        data = MemorySettingsUpdate(
            knowledge_hygiene_enabled=False,
            knowledge_hygiene_similarity_threshold=0.9,
            knowledge_hygiene_max_cluster_size=8,
            knowledge_hygiene_mode="proposal_only",
            knowledge_hygiene_enabled_categories=["skill", "playbook"],
            knowledge_hygiene_category_policies={"skill": "auto_conservative"},
            knowledge_hygiene_creation_time_enabled=True,
        )
        assert data.knowledge_hygiene_mode == "proposal_only"
        assert data.knowledge_hygiene_similarity_threshold == 0.9

    def test_response_defaults_match_plan(self):
        from memory_models import MemorySettingsResponse
        r = MemorySettingsResponse()
        assert r.knowledge_hygiene_enabled is True
        assert r.knowledge_hygiene_similarity_threshold == 0.82
        assert r.knowledge_hygiene_max_cluster_size == 5
        assert r.knowledge_hygiene_mode == "manual_only"
        assert r.knowledge_hygiene_creation_time_enabled is False
        assert len(r.knowledge_hygiene_enabled_categories) == 5


# ─── request models + error codes ────────────────────────────────────────────

class TestRequestModels:
    def test_preview_request_defaults(self):
        from memory_models import ConsolidationPreviewRequest, ConsolidationOptions
        r = ConsolidationPreviewRequest(knowledge_ids=["a", "b"])
        assert r.origin == "manual"
        assert r.options is None
        opts = ConsolidationOptions()
        assert opts.canonical_strategy == "update_existing"

    def test_apply_request_requires_approved_canonical(self):
        from memory_models import ConsolidationApplyRequest, CanonicalFields
        r = ConsolidationApplyRequest(
            preview_id="p1",
            approved_canonical=CanonicalFields(name="X", content="Y"),
        )
        assert r.canonical_strategy == "update_existing"

    def test_consolidation_error_carries_status(self):
        from memory_consolidation_repository import ConsolidationError
        e = ConsolidationError("stale_preview", "changed", 409)
        assert e.code == "stale_preview" and e.status == 409


# ─── LLM proposal pipeline with FAKE provider ────────────────────────────────

class TestProposalGeneration:
    def _patch_llm(self, monkeypatch, responses):
        """Fake call_llm that returns queued responses; fail on external call."""
        calls = {"n": 0}

        async def fake_call_llm(prompt, system_prompt=None, max_tokens=1000, task_type="summarization", config_id=None):
            calls["n"] += 1
            if calls["n"] <= len(responses):
                return responses[calls["n"] - 1]
            raise AssertionError("call_llm invoked more times than expected (would hit paid API)")

        import memory_consolidation_service as svc
        import memory_services
        monkeypatch.setattr(memory_services, "call_llm", fake_call_llm, raising=True)
        monkeypatch.setattr(svc, "_settings", lambda: {"knowledge_max_tokens": 1600})
        monkeypatch.setattr(svc, "_llm_config", lambda: {"provider": "fake", "model_name": "fake-model"})
        return calls

    def test_happy_path_returns_validated_proposal(self, monkeypatch):
        self._patch_llm(monkeypatch, [json.dumps(_proposal(recommendation="merge", confidence=0.95))])
        import memory_consolidation_service as svc
        rows = [GOLDEN["best_practices"](), _row("bp2", "best_practices", content="related guidance")]
        metrics = {"cohesion": 0.9, "pairwise_min": 0.85, "pairwise_max": 0.99, "weak_links": []}
        proposal, raw, errs, model = asyncio.run(
            svc._generate_proposal(rows, metrics, "best_practices"))
        assert errs == []
        assert proposal["recommendation"] == "merge"
        assert proposal["confidence"] == 0.95
        assert model == "fake-model"

    def test_repair_retry_on_invalid_json(self, monkeypatch):
        # First response invalid, second valid → one repair retry succeeds.
        self._patch_llm(monkeypatch, ["not json at all", json.dumps(_proposal(recommendation="merge"))])
        import memory_consolidation_service as svc
        rows = [GOLDEN["trade_knowledge"](), _row("tk2", "trade_knowledge")]
        proposal, raw, errs, model = asyncio.run(
            svc._generate_proposal(rows, {"cohesion": 0.9, "pairwise_min": 0.8, "pairwise_max": 0.99, "weak_links": []}, "trade_knowledge"))
        assert errs == []
        assert proposal is not None

    def test_failed_after_retry(self, monkeypatch):
        self._patch_llm(monkeypatch, ["bad1", "bad2"])
        import memory_consolidation_service as svc
        rows = [GOLDEN["lessons_learned"](), _row("ll2", "lessons_learned")]
        proposal, raw, errs, model = asyncio.run(
            svc._generate_proposal(rows, {"cohesion": 0.9, "pairwise_min": 0.8, "pairwise_max": 0.99, "weak_links": []}, "lessons_learned"))
        assert errs and proposal is None

    def test_skill_proposal_validates_name_slug(self, monkeypatch):
        # canonical with a valid name → OK; the validator accepts skill category
        p = _proposal(recommendation="merge", confidence=0.9,
                      canonical={"name": "Valid Skill", "summary": "s", "content": "procedure body", "signals": [], "tags": [], "metadata": {}})
        proposal, errs = validate_proposal(p, "skill")
        assert not errs
        # slug round-trips
        from memory_skill_md import slugify
        assert slugify("Valid Skill") == "valid-skill"


# ─── repository pure helpers ─────────────────────────────────────────────────

class TestRepositoryHelpers:
    def test_normalize_ts_handles_iso_and_datetime(self):
        from datetime import datetime, timezone
        from memory_consolidation_repository import _normalize_ts
        assert _normalize_ts(None) is None
        d = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert _normalize_ts(d).startswith("2026-01-01T00:00:00")
        assert _normalize_ts("2026-01-01T00:00:00Z").startswith("2026-01-01")

    def test_distinct_ids_preserves_order_dedups(self):
        from memory_consolidation_service import _distinct_ids
        assert _distinct_ids(["a", "b", "a", "c", None]) == ["a", "b", "c"]

    def test_validate_source_set_rejects_mixed_categories(self):
        from memory_consolidation_service import _validate_source_set
        from memory_consolidation_repository import ConsolidationError
        rows = [_row("a", "skill"), _row("b", "playbook")]
        with pytest.raises(ConsolidationError) as exc:
            _validate_source_set(rows, origin="manual")
        assert exc.value.code == "mixed_categories" and exc.value.status == 400

    def test_validate_source_set_rejects_non_allowlist_category(self):
        from memory_consolidation_service import _validate_source_set
        from memory_consolidation_repository import ConsolidationError
        rows = [_row("a", "other"), _row("b", "other")]
        with pytest.raises(ConsolidationError) as exc:
            _validate_source_set(rows, origin="manual")
        assert exc.value.code == "invalid_category"

    def test_validate_source_set_rejects_retired(self):
        from memory_consolidation_service import _validate_source_set
        from memory_consolidation_repository import ConsolidationError
        rows = [_row("a", "skill", status="retired"), _row("b", "skill")]
        with pytest.raises(ConsolidationError) as exc:
            _validate_source_set(rows, origin="manual")
        assert exc.value.code == "invalid_status"

    def test_validate_approved_canonical_requires_name_and_content(self):
        from memory_consolidation_service import _validate_approved_canonical
        from memory_consolidation_repository import ConsolidationError
        with pytest.raises(ConsolidationError) as exc:
            _validate_approved_canonical({"name": "", "content": ""}, "trade_knowledge")
        assert exc.value.code == "invalid_canonical" and exc.value.status == 422


# ─── embedding version constant ──────────────────────────────────────────────

def test_embedding_version_matches_default_setting():
    from memory_models import MemorySettingsResponse
    assert MemorySettingsResponse().knowledge_hygiene_embedding_version == EMBEDDING_VERSION
