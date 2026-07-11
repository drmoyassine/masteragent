"""memory_clustering.py — Candidate discovery + deterministic cluster splitting.

Embedding similarity is used ONLY to discover and group automated candidates.
The semantic merge decision always comes from the category-aware LLM proposal
in the consolidation service — never from these groupings.

Algorithm (§14.3 of the plan):

  1. Partition records by category (cross-category consolidation is unsupported).
  2. Within a category, sort by ID, compute all pairwise cosine similarities,
     keep edges at or above the candidate threshold, find deterministic
     connected components (union-find).
  3. A component is *accepted* for an LLM proposal only when its size is at
     most the configured maximum, its cohesion (average all-pairs similarity)
     is at least the configured minimum, and no member-to-centroid similarity
     is below the weak-link threshold.
  4. Otherwise repeatedly remove the lowest-similarity edge (ties broken by
     sorted endpoint IDs) and recompute components until every resulting
     component passes or becomes a singleton.
  5. A still-oversized component is divided deterministically (lowest-ID seed,
     then greedily add the remaining member with the highest average similarity
     to the current subgroup). These size-forced groups are marked
     ``manual_review`` — they are never auto-applied.
  6. Singletons are analysis results only; they never invoke the LLM.

Manual selection (the Knowledge-table workflow) bypasses the threshold and
splitting rules but still reports every metric and requires a single category.

Everything here is deterministic: shuffled input produces identical output.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Sequence, Set

from memory_similarity import (
    centroid,
    cohesion,
    connected_components,
    edges_at_threshold,
    member_to_centroid,
    pairwise_similarities,
)

logger = logging.getLogger(__name__)


def _group_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal projection of a knowledge row used for grouping/metrics."""
    return {
        "id": rec.get("id"),
        "category": rec.get("category") or "trade_knowledge",
        "embedding": rec.get("embedding"),
    }


def _metrics_for(members: Sequence[str], pair_all: Sequence, vectors: Dict[str, Any]) -> Dict[str, Any]:
    """Full metric bundle for a set of member IDs (deterministic)."""
    member_set = set(members)
    sims = [s for a, b, s in pair_all if a in member_set and b in member_set]
    cent = centroid({k: vectors[k] for k in members if k in vectors})
    m2c = member_to_centroid({k: vectors[k] for k in members if k in vectors}, cent) if cent else {}
    weak = sorted([k for k, sim in m2c.items() if sim == 0.0])  # placeholder; real weak set filled by caller
    mn = min(sims) if sims else 0.0
    mx = max(sims) if sims else 0.0
    mean = cohesion(sims)
    return {
        "pairwise_min": mn,
        "pairwise_mean": mean,
        "pairwise_max": mx,
        "cohesion": mean,
        "centroid_similarity": m2c,
        "weak_links": weak,
    }


def _passes_quality(
    members: Sequence[str],
    pair_all: Sequence,
    vectors: Dict[str, Any],
    *,
    min_cohesion: float,
    weak_link_threshold: float,
) -> bool:
    """True when a multi-member component meets cohesion + weak-link gates.

    Size is NOT checked here — oversized-but-cohesive components are size-split
    to ``manual_review`` rather than broken apart by removing good edges (§14.3).
    """
    if len(members) < 2:
        return True
    member_set = set(members)
    sims = [s for a, b, s in pair_all if a in member_set and b in member_set]
    if not sims:
        return False
    if cohesion(sims) < min_cohesion:
        return False
    cent = centroid({k: vectors[k] for k in members if k in vectors})
    m2c = member_to_centroid({k: vectors[k] for k in members if k in vectors}, cent) if cent else {}
    if any(sim < weak_link_threshold for sim in m2c.values()):
        return False
    return True


def _weak_links_of(members: Sequence[str], vectors: Dict[str, Any], weak_link_threshold: float) -> List[str]:
    cent = centroid({k: vectors[k] for k in members if k in vectors})
    if not cent:
        return []
    m2c = member_to_centroid({k: vectors[k] for k in members if k in vectors}, cent)
    return sorted([k for k, sim in m2c.items() if sim < weak_link_threshold])


def _size_split(
    members: Sequence[str],
    pair_all: Sequence,
    max_size: int,
) -> List[List[str]]:
    """Deterministic greedy size-split for an oversized component.

    Seed each subgroup with its lowest-ID member, then repeatedly add the
    remaining member with the highest average similarity to the current
    subgroup until the subgroup reaches ``max_size``. Members without any
    internal edges go into the last subgroup. Deterministic: ties in average
    similarity are broken by ascending ID.
    """
    remaining = sorted(members)
    sim_index: Dict[frozenset, float] = {}
    for a, b, s in pair_all:
        sim_index[frozenset((a, b))] = s

    def avg_sim(candidate: str, subgroup: List[str]) -> float:
        vals = [sim_index.get(frozenset((candidate, m)), 0.0) for m in subgroup]
        return sum(vals) / len(vals) if vals else 0.0

    subgroups: List[List[str]] = []
    while remaining:
        subgroup = [remaining.pop(0)]  # lowest-ID seed
        while len(subgroup) < max_size and remaining:
            # pick the remaining member with the highest avg sim to the subgroup
            best = sorted(remaining, key=lambda c: (-avg_sim(c, subgroup), c))[0]
            remaining.remove(best)
            subgroup.append(best)
        subgroup.sort()
        subgroups.append(subgroup)
    return subgroups


def _resolve_component(
    comp_ids: Sequence[str],
    pair_all: Sequence,
    vectors: Dict[str, Any],
    *,
    max_size: int,
    min_cohesion: float,
    weak_link_threshold: float,
) -> List[Dict[str, Any]]:
    """Run edge-removal + size-split on one initial component → group list.

    Edge removal addresses ONLY cohesion/weak-link failures. Oversized-but-
    cohesive components are size-split to ``manual_review`` (size_forced) so a
    tight group is never broken apart by deleting its strongest edges.
    """
    comp_set = set(comp_ids)
    working = [(a, b, s) for a, b, s in pair_all if a in comp_set and b in comp_set]

    guard = 0
    while True:
        guard += 1
        if guard > 10000:  # safety against pathological input
            break
        comps = connected_components(comp_ids, working)
        failing = None
        for c in comps:
            # Only flag cohesion/weak-link failures of in-bounds (≤ max) components.
            if 1 < len(c) <= max_size and not _passes_quality(
                c, pair_all, vectors,
                min_cohesion=min_cohesion, weak_link_threshold=weak_link_threshold,
            ):
                failing = c
                break
        if failing is None or not working:
            break
        failing_set = set(failing)
        failing_edges = [e for e in working if e[0] in failing_set and e[1] in failing_set]
        if not failing_edges:
            break
        lowest = min(failing_edges, key=lambda e: (e[2], e[0], e[1]))
        working.remove(lowest)

    final_comps = connected_components(comp_ids, working)
    result: List[Dict[str, Any]] = []
    for c in final_comps:
        members = sorted(c)
        if len(members) == 1:
            result.append(_make_group(members, pair_all, vectors, "singleton", None))
        elif len(members) > max_size:
            # Oversized → deterministic size-split, never auto-applied.
            for subgroup in _size_split(members, working, max_size):
                result.append(_make_group(subgroup, pair_all, vectors, "manual_review", "size_forced",
                                          weak_link_threshold=weak_link_threshold))
        elif _passes_quality(c, pair_all, vectors, min_cohesion=min_cohesion,
                             weak_link_threshold=weak_link_threshold):
            result.append(_make_group(members, pair_all, vectors, "accepted", None,
                                      weak_link_threshold=weak_link_threshold))
        else:
            result.append(_make_group(members, pair_all, vectors, "manual_review", "low_cohesion_or_weak_link",
                                      weak_link_threshold=weak_link_threshold))
    return result


def _make_group(
    members: Sequence[str],
    pair_all: Sequence,
    vectors: Dict[str, Any],
    status: str,
    split_reason,
    *,
    weak_link_threshold: float = 0.65,
) -> Dict[str, Any]:
    metrics = _metrics_for(members, pair_all, vectors)
    weak = _weak_links_of(members, vectors, weak_link_threshold) if len(members) > 1 else []
    metrics["weak_links"] = weak
    cent = centroid({k: vectors[k] for k in members if k in vectors}) if len(members) > 1 else None
    return {
        "member_ids": list(members),
        "size": len(members),
        "status": status,
        "split_reason": split_reason,
        "metrics": metrics,
        "centroid": cent,
    }


def discover_candidate_groups(
    records: Iterable[Dict[str, Any]],
    *,
    threshold: float,
    min_size: int = 2,
    max_size: int = 5,
    min_cohesion: float = 0.72,
    weak_link_threshold: float = 0.65,
) -> List[Dict[str, Any]]:
    """Partition records by category and return deterministic candidate groups.

    Each group carries ``member_ids``, ``size``, ``status``
    (``accepted``/``manual_review``/``singleton``), ``split_reason``, and a
    ``metrics`` bundle (pairwise min/mean/max, cohesion, per-member centroid
    similarity, weak links). Singletons are returned for analysis but never
    proposed; the caller filters them out before LLM preview.
    """
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        g = _group_record(rec)
        if not g["embedding"]:
            continue  # no embedding → cannot participate in similarity grouping
        by_category.setdefault(g["category"], []).append(g)

    groups: List[Dict[str, Any]] = []
    for category in sorted(by_category.keys()):
        recs = by_category[category]
        ids = sorted(r["id"] for r in recs)
        vectors = {r["id"]: r["embedding"] for r in recs}
        pair_all = pairwise_similarities(vectors)
        edges = edges_at_threshold(pair_all, threshold)
        components = connected_components(ids, edges)
        # Attach category to every group for downstream partitioning.
        for comp in components:
            members = sorted(comp)
            if len(members) < 2:
                grp = _make_group(members, pair_all, vectors, "singleton", None)
            else:
                resolved = _resolve_component(
                    members, pair_all, vectors,
                    max_size=max_size, min_cohesion=min_cohesion,
                    weak_link_threshold=weak_link_threshold,
                )
                # _resolve_component may itself emit singletons when an edge
                # removal disconnects a member.
                if len(resolved) == 1 and resolved[0]["member_ids"] == members:
                    grp = resolved[0]
                    groups.append(_with_category(grp, category))
                    continue
                for grp in resolved:
                    groups.append(_with_category(grp, category))
                continue
            groups.append(_with_category(grp, category))
    return groups


def _with_category(group: Dict[str, Any], category: str) -> Dict[str, Any]:
    g = dict(group)
    g["category"] = category
    return g


def manual_group_metrics(
    records: Sequence[Dict[str, Any]], *, weak_link_threshold: float = 0.65
) -> Dict[str, Any]:
    """Metrics for a manually-selected set (single category, never rejected).

    Reports pairwise min/mean/max, cohesion, per-member centroid similarity,
    weak links, and the shared category. The caller validates that every
    record shares one category before calling this.
    """
    vectors = {r["id"]: r["embedding"] for r in records if r.get("embedding")}
    pair_all = pairwise_similarities(vectors)
    members = sorted(vectors.keys())
    metrics = _metrics_for(members, pair_all, vectors)
    metrics["weak_links"] = _weak_links_of(members, vectors, weak_link_threshold) if len(members) > 1 else []
    return {
        "category": (records[0].get("category") if records else None),
        "member_ids": sorted(r.get("id") for r in records if r.get("id")),
        "embedding_member_ids": members,
        "size": len(records),
        "status": "manual",
        "split_reason": None,
        "metrics": metrics,
        "embedding_compatible": all(r.get("embedding") for r in records),
    }


def accepted_proposal_groups(groups: Sequence[Dict[str, Any]], min_size: int) -> List[Dict[str, Any]]:
    """Groups accepted for automatic-policy consideration."""
    return [g for g in groups if g.get("status") == "accepted" and g.get("size", 0) >= min_size]
