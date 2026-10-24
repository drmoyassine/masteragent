"""memory_system.maintain.similarity.py — Pure standard-library vector similarity primitives.

No numpy / scipy / sklearn (per the implementation mandate). Everything here is
deterministic: input IDs are sorted before pairing and component labelling so
the same set of records always produces the same candidate edges, centroids,
and component groupings regardless of insertion order.

These primitives are grouping safeguards only — they never decide a merge. The
semantic merge decision always comes from the category-aware LLM proposal plus
deterministic safety checks in the consolidation service.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

Vector = Sequence[float]

try:  # Optional fast path — the runtime image ships numpy; the pure-python
    import numpy as _np  # loop below remains the portable source of truth.
except Exception:  # pragma: no cover
    _np = None

# A directed-agnostic edge: (id_a, id_b, similarity) with id_a < id_b by sort key.
Edge = Tuple[str, str, float]


# ─── basic vector math ───────────────────────────────────────────────────────

def _norm(v: Vector) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in v))


def l2_normalize(v: Vector) -> List[float]:
    """Return the L2-normalized vector (unit length). Zero vector → zeros."""
    n = _norm(v)
    if n == 0.0:
        return [0.0 for _ in v]
    return [float(x) / n for x in v]


def cosine_similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity in [-1, 1]. Returns 0.0 when either vector is zero.

    Vectors of mismatched length are compared over their common prefix so a
    dimension-pinned policy is never violated by a stray legacy record; callers
    that need strict equality check ``len(a) == len(b)`` first. Inputs arriving
    as pgvector text are parsed first (unparseable → 0.0, never a crash).
    """
    a = _parse_vector(a) or []
    b = _parse_vector(b) or []
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        ai = float(a[i])
        bi = float(b[i])
        dot += ai * bi
        na += ai * ai
        nb += bi * bi
    if na == 0.0 or nb == 0.0:
        return 0.0
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom == 0.0:
        return 0.0
    return dot / denom


# ─── pairwise + centroid aggregates ──────────────────────────────────────────

def _parse_vector(value: Any) -> Optional[List[float]]:
    """Pass sequences through; parse pgvector text ('[0.1,0.2,…]') to floats.

    Unparseable values return None and are dropped from pairwise scoring (they
    have no comparable geometry) instead of crashing the nightly job.
    """
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value.strip())
            if isinstance(parsed, list):
                return [float(x) for x in parsed]
        except Exception:
            return None
    return None


def pairwise_similarities(vectors: Dict[str, Vector], *, min_similarity: Optional[float] = None) -> List[Edge]:
    """Unique pairwise cosine similarities, deterministically ordered.

    Edges are returned sorted by ``(id_a, id_b)`` where ``id_a < id_b`` by
    Python string ordering — so shuffling the input dict never changes the
    output sequence. Duplicate IDs are collapsed.

    ``min_similarity`` drops edges below the cutoff WITHOUT materializing the
    full O(n²) tuple list first (a 3.5k-record corpus is 6.3M pairs ≈ 450 MB
    of tuples when unfiltered) — use it when only threshold-crossing edges
    matter. Uses a batched matrix multiply when numpy is importable (same
    output, including the zero-vector → 0.0 semantics of
    :func:`cosine_similarity`); falls back to the pure-python loop otherwise.
    """
    parsed = {kid: v for kid, v in ((k, _parse_vector(x)) for k, x in vectors.items()) if v}
    ids = sorted(parsed.keys())
    if not ids:
        return []
    if _np is not None:
        try:
            matrix = _np.asarray([parsed[kid] for kid in ids], dtype=_np.float64)
        except (TypeError, ValueError):
            matrix = None
        if matrix is not None and matrix.ndim == 2 and matrix.shape[1] > 0:
            norms = _np.linalg.norm(matrix, axis=1)
            sim = _np.zeros((len(ids), len(ids)), dtype=_np.float64)
            nz = norms > 0.0
            if bool(nz.any()):
                unit = matrix[nz] / norms[nz][:, None]
                sim[_np.ix_(nz, nz)] = unit @ unit.T
            iu, ju = _np.triu_indices(len(ids), k=1)
            vals = sim[iu, ju]
            if min_similarity is not None:
                keep = vals >= float(min_similarity)
                iu, ju, vals = iu[keep], ju[keep], vals[keep]
            return [(ids[i], ids[j], float(s)) for i, j, s in zip(iu, ju, vals)]
    edges: List[Edge] = []
    for i, a in enumerate(ids):
        va = parsed[a]
        for b in ids[i + 1:]:
            sim = cosine_similarity(va, parsed[b])
            if min_similarity is None or sim >= min_similarity:
                edges.append((a, b, sim))
    return edges


def min_mean_max(sims: Sequence[float]) -> Tuple[float, float, float]:
    """Return (min, mean, max) of a similarity sequence. Empty → (0, 0, 0)."""
    if not sims:
        return 0.0, 0.0, 0.0
    mn = min(sims)
    mx = max(sims)
    mean = sum(sims) / len(sims)
    return mn, mean, mx


def centroid(vectors: Dict[str, Vector]) -> List[float]:
    """L2-normalized component-wise mean of the given vectors.

    The mean is normalized so member-to-centroid similarities are directly
    comparable to pairwise similarities. Empty input → empty list. Vectors of
    differing lengths are padded with zeros to the max length so the centroid
    is well-defined even when a legacy record slips in.
    """
    if not vectors:
        return []
    vecs = [v for v in (_parse_vector(x) for x in vectors.values()) if v]
    if not vecs:
        return []
    dim = max(len(v) for v in vecs)
    acc = [0.0] * dim
    for v in vecs:
        for i, x in enumerate(v):
            acc[i] += float(x)
    n = len(vecs)
    mean = [x / n for x in acc]
    return l2_normalize(mean)


def member_to_centroid(vectors: Dict[str, Vector], centroid_vec: Vector) -> Dict[str, float]:
    """Cosine similarity of each member to the centroid, keyed by ID."""
    cent = _parse_vector(centroid_vec) or []
    out: Dict[str, float] = {}
    for kid, vec in vectors.items():
        parsed = _parse_vector(vec)
        if parsed is not None:
            out[kid] = cosine_similarity(parsed, cent)
    return out


# ─── graph edges, weak links, components ─────────────────────────────────────

def edges_at_threshold(pair_sims: Iterable[Edge], threshold: float) -> List[Edge]:
    """Edges whose similarity is at or above the candidate threshold.

    Deterministically ordered (inherits the sorted order of ``pair_sims``).
    """
    return [(a, b, s) for a, b, s in pair_sims if s >= threshold]


def weak_links(member_centroid_sims: Dict[str, float], threshold: float) -> List[str]:
    """Member IDs whose centroid similarity falls below the weak-link threshold."""
    return sorted(kid for kid, sim in member_centroid_sims.items() if sim < threshold)


def connected_components(ids: Iterable[str], edges: Iterable[Edge]) -> List[frozenset]:
    """Deterministic connected components via union-find.

    Returns a list of frozensets sorted by their smallest member ID. Singletons
    (IDs with no edges) are included. Determinism: the sort key is
    ``min(component)`` so output order never depends on dict iteration order.
    """
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        # path compression
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    id_set = set(ids)
    for kid in id_set:
        parent.setdefault(kid, kid)
    for a, b, _ in edges:
        if a in id_set and b in id_set:
            union(a, b)

    groups: Dict[str, set] = {}
    for kid in id_set:
        root = find(kid)
        groups.setdefault(root, set()).add(kid)
    components = [frozenset(g) for g in groups.values()]
    components.sort(key=lambda c: min(c))
    return components


# ─── cohesion + cluster metric bundle ────────────────────────────────────────

def cohesion(pair_sims: Sequence[float]) -> float:
    """Average all-pairs similarity within a candidate cluster (0..1 typical)."""
    if not pair_sims:
        return 0.0
    return sum(pair_sims) / len(pair_sims)


def cluster_metrics(vectors: Dict[str, Vector]) -> Dict[str, float]:
    """Full metric bundle for a single candidate cluster.

    Returns ``pairwise_min``, ``pairwise_mean`` (cohesion), ``pairwise_max``,
    ``centroid`` (the unit vector), ``member_to_centroid`` map, and
    ``weak_links`` placeholder list (caller fills with the configured threshold).
    """
    pair = pairwise_similarities(vectors)
    sims = [s for _, _, s in pair]
    mn, mean, mx = min_mean_max(sims)
    cent = centroid(vectors)
    m2c = member_to_centroid(vectors, cent) if cent else {k: 0.0 for k in vectors}
    return {
        "pairwise_min": mn,
        "pairwise_mean": mean,
        "pairwise_max": mx,
        "cohesion": mean,
        "centroid": cent,
        "member_to_centroid": m2c,
    }


def component_pair_sims(
    member_ids: Iterable[str], pair_sims: Sequence[Edge]
) -> List[float]:
    """All pairwise similarities whose both endpoints are in ``member_ids``."""
    members = set(member_ids)
    return [s for a, b, s in pair_sims if a in members and b in members]
