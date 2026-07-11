"""Unit coverage for unified Knowledge policy, quality v2, and source routing."""
import memory_evidence_service as evidence
from memory_generation_policy import approval_status, resolve_generation_policy
from memory_quality import calculate_quality_v2


def test_generation_policy_precedence():
    settings = {
        "knowledge_generation_max_tokens": 1200,
        "knowledge_generation_min_confidence": 0.6,
        "knowledge_generation_pathway_overrides": {
            "telemetry_reflection": {"max_tokens": 1800, "min_confidence": 0.7},
        },
    }
    entity = {"knowledge_generation_overrides": {
        "telemetry_reflection": {"min_confidence": 0.8},
    }}
    result = resolve_generation_policy(
        "telemetry_reflection", settings=settings, entity_config=entity,
    )
    assert result["values"]["max_tokens"] == 1800
    assert result["sources"]["max_tokens"] == "pathway"
    assert result["values"]["min_confidence"] == 0.8
    assert result["sources"]["min_confidence"] == "entity"


def test_approval_names_map_to_stored_statuses():
    assert approval_status("approve_immediately") == "active"
    assert approval_status("create_as_draft") == "draft"


def test_quality_v2_is_explainable_and_spans_useful_range():
    weak = calculate_quality_v2(
        unique_bundle_count=0, diversity_count=0, success_count=0, failure_count=6,
        generation_confidence=0.2, provenance_completeness=0.0, approval_assurance=0.0,
    )
    strong = calculate_quality_v2(
        unique_bundle_count=10, diversity_count=5, success_count=20, failure_count=0,
        generation_confidence=0.98, provenance_completeness=1.0, approval_assurance=1.0,
    )
    assert weak["version"] == 2
    assert weak["score"] < 0.25
    assert strong["score"] > 0.9
    assert strong["score"] > weak["score"]
    assert set(strong["components"]) == {
        "evidence_strength", "outcome_feedback", "generation_confidence",
        "validation_provenance",
    }


def test_source_similarity_routes_before_generation(monkeypatch):
    monkeypatch.setattr(evidence, "upsert_bundle", lambda **_: "bundle-1")
    monkeypatch.setattr(evidence, "update_bundle_analysis", lambda *_: None)
    monkeypatch.setattr(evidence, "resolve_active_canonical", lambda kid: kid)
    monkeypatch.setattr(
        evidence, "load_linked_historical_sources",
        lambda *_: [{"id": "old", "embedding": [1.0, 0.0],
                     "knowledge_id": "canonical-1"}],
    )
    result = evidence.analyze_evidence(
        pathway="declarative_knowledge",
        sources=[{
            "source_type": "intelligence", "source_id": "new", "entity_id": "e1",
            "embedding": [1.0, 0.0], "embedding_model": "test", "embedding_version": 1,
        }],
        settings={
            "knowledge_evidence_low_threshold": 0.78,
            "knowledge_evidence_high_threshold": 0.95,
            "knowledge_evidence_high_coverage": 0.9,
            "knowledge_evidence_routing_mode": "analysis_only",
        },
    )
    assert result["route"] == "evidence_link"
    assert result["canonical_knowledge_id"] == "canonical-1"
    assert result["metrics"]["aggregate_similarity"] == 1.0
