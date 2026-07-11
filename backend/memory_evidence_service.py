"""Cheap source-first novelty routing before Knowledge-generation LLM calls."""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Dict, List, Sequence

from memory_evidence_repository import (
    link_evidence_to_canonical,
    load_linked_historical_sources,
    resolve_active_canonical,
    update_bundle_analysis,
    upsert_bundle,
)
from memory_similarity import cosine_similarity, l2_normalize


def _vector(value: Any) -> List[float]:
    if value is None: return []
    if hasattr(value, "tolist"): return [float(x) for x in value.tolist()]
    if isinstance(value, str):
        return [float(x) for x in value.strip("[]").split(",") if x.strip()]
    return [float(x) for x in value]


def _centroid(vectors: Sequence[Sequence[float]]) -> List[float]:
    normalized = [l2_normalize(v) for v in vectors if v]
    if not normalized: return []
    dims = len(normalized[0])
    if any(len(v) != dims for v in normalized): return []
    return l2_normalize([sum(v[i] for v in normalized) / len(normalized) for i in range(dims)])


def analyze_evidence(
    *, pathway: str, sources: Sequence[Dict[str, Any]], settings: Dict[str, Any],
    entity_type: str | None = None, outcome_signature: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    compatible = [s for s in sources if _vector(s.get("embedding"))]
    if not compatible:
        return {"bundle_id": None, "route": "new_generation", "metrics": {"reason": "missing_embeddings"}}
    model = compatible[0].get("embedding_model")
    version = int(compatible[0].get("embedding_version") or 1)
    dims = len(_vector(compatible[0]["embedding"]))
    compatible = [s for s in compatible if
                  len(_vector(s.get("embedding"))) == dims and
                  (s.get("embedding_model") in (None, model)) and
                  int(s.get("embedding_version") or version) == version]
    centroid = _centroid([_vector(s["embedding"]) for s in compatible])
    context_digest = hashlib.sha256(str(outcome_signature or {}).encode()).hexdigest()
    bundle_id = upsert_bundle(
        pathway=pathway, sources=compatible, aggregate_embedding=centroid,
        embedding_model=model or "legacy", embedding_version=version,
        entity_type=entity_type,
        entity_ids=[s.get("entity_id") for s in compatible if s.get("entity_id")],
        context_digest=context_digest, outcome_signature=outcome_signature,
    )
    pathway_categories = {
        "declarative_knowledge": ["best_practices", "lessons_learned", "trade_knowledge"],
        "playbook_extraction": ["playbook"],
        "skill_extraction": ["skill"],
    }
    categories = pathway_categories.get(pathway)
    historical_by_type = {
        st: load_linked_historical_sources(
            st, [s["source_id"] for s in compatible if s["source_type"] == st], categories,
        )
        for st in {s["source_type"] for s in compatible}
    }
    best = []
    for source in compatible:
        sv = _vector(source["embedding"])
        candidates = []
        for old in historical_by_type.get(source["source_type"], []):
            ov = _vector(old.get("embedding"))
            if len(ov) != len(sv): continue
            canonical = resolve_active_canonical(old["knowledge_id"])
            if canonical:
                candidates.append((cosine_similarity(sv, ov), canonical, ov, old["id"]))
        if candidates:
            best.append(max(candidates, key=lambda item: (item[0], item[1], item[3])))
    similarities = [b[0] for b in best]
    canonical_counts = Counter(b[1] for b in best)
    canonical_id = canonical_counts.most_common(1)[0][0] if canonical_counts else None
    matched_vectors = [b[2] for b in best if b[1] == canonical_id]
    centroid_similarity = cosine_similarity(centroid, _centroid(matched_vectors)) if matched_vectors else 0.0
    member_average = sum(similarities) / len(similarities) if similarities else 0.0
    aggregate = 0.5 * centroid_similarity + 0.5 * member_average
    low = float(settings.get("knowledge_evidence_low_threshold", 0.78))
    high = float(settings.get("knowledge_evidence_high_threshold", 0.95))
    required_coverage = float(settings.get("knowledge_evidence_high_coverage", 0.90))
    high_coverage = sum(1 for score in similarities if score >= high) / len(compatible)
    one_canonical = bool(canonical_counts) and len(canonical_counts) == 1
    if aggregate >= high and high_coverage >= required_coverage and one_canonical:
        route = "evidence_link"
    elif aggregate >= low and canonical_id:
        route = "revision_assessment"
    else:
        route = "new_generation"
    metrics = {
        "aggregate_similarity": round(aggregate, 6),
        "centroid_similarity": round(centroid_similarity, 6),
        "member_min": round(min(similarities), 6) if similarities else 0.0,
        "member_average": round(member_average, 6),
        "member_max": round(max(similarities), 6) if similarities else 0.0,
        "high_coverage": round(high_coverage, 6),
        "source_count": len(sources), "compatible_source_count": len(compatible),
        "canonical_distribution": dict(canonical_counts),
        "mode": settings.get("knowledge_evidence_routing_mode", "analysis_only"),
    }
    result = {"bundle_id": bundle_id, "route": route, "metrics": metrics,
              "canonical_knowledge_id": canonical_id,
              "matched_knowledge_ids": sorted(canonical_counts)}
    update_bundle_analysis(bundle_id, result)
    return result


def apply_high_similarity_link(result: Dict[str, Any], sources: Sequence[Dict[str, Any]], settings: Dict[str, Any]) -> str | None:
    if result.get("route") != "evidence_link" or settings.get("knowledge_evidence_routing_mode") != "enforced":
        return None
    return link_evidence_to_canonical(
        bundle_id=result["bundle_id"], canonical_id=result["canonical_knowledge_id"],
        sources=sources, metrics=result["metrics"], settings={
            "low": settings.get("knowledge_evidence_low_threshold", 0.78),
            "high": settings.get("knowledge_evidence_high_threshold", 0.95),
            "coverage": settings.get("knowledge_evidence_high_coverage", 0.90),
        },
    )
