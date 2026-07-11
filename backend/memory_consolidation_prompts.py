"""memory_consolidation_prompts.py — Category-aware consolidation prompts + validation.

Shared base prompt + per-category preservation rules, the strict Pydantic
proposal model (§5.2), and validation hooks. The LLM proposes content only;
deterministic code in the consolidation service preserves system fields and
decides whether to apply.

Prompt version is pinned and stored on every preview/event so an audit can
reconstruct exactly what instructions produced a given proposal.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

CONSOLIDATION_PROMPT_VERSION = "v1"

RECOMMENDATIONS = (
    "merge",
    "merge_with_warnings",
    "keep_separate",
    "split_cluster",
    "manual_review",
)


# ─── system prompt ───────────────────────────────────────────────────────────

CONSOLIDATION_BASE_PROMPT = (
    "You are a knowledge-consolidation analyst. You are given several existing "
    "knowledge records that a similarity graph grouped together, plus non-"
    "authoritative grouping metrics. Your job is preservation-first: decide "
    "whether these records can coherently become ONE stronger canonical record, "
    "and if so produce it without losing information.\n\n"
    "ABSOLUTE RULES:\n"
    "- Never invent claims, qualifications, or evidence that are not in the sources.\n"
    "- Never silently discard a qualification, condition, exception, or context.\n"
    "- Never turn distinct separate incidents into one fabricated event.\n"
    "- Preserve every distinct fact; only remove true redundancy (the same fact stated twice).\n"
    "- Similarity metrics are RETRIEVAL/GROUPING EVIDENCE ONLY. They never justify a merge by themselves. Read the actual content.\n"
    "- The canonical record must subsume every source's unique information or the recommendation must be keep_separate / split_cluster / manual_review.\n\n"
    "RECOMMENDATION VALUES (choose exactly one):\n"
    "- merge: the records cleanly become one canonical record with no conflicts.\n"
    "- merge_with_warnings: they can become one, but surfaced warnings/qualifications must be respected.\n"
    "- keep_separate: they are genuinely different records and should NOT merge.\n"
    "- split_cluster: the group is incoherent and should be split into smaller consolidations (provide split_recommendations).\n"
    "- manual_review: too ambiguous or conflicting to decide automatically.\n\n"
    "Return ONLY a JSON object matching the schema. No prose outside the JSON."
)


CATEGORY_INSTRUCTIONS: Dict[str, str] = {
    "best_practices": (
        "CATEGORY: best_practices. Preserve every recommendation, the conditions "
        "under which it applies, its exceptions, and its scope. Keep the distinction "
        "between guidance that applies universally versus only conditionally. Do not "
        "collapse a conditional rule into a universal one."
    ),
    "lessons_learned": (
        "CATEGORY: lessons_learned. Preserve causal context, evidence, and outcomes. "
        "Keep separate incidents DISTINCT — never fabricate a single incident from "
        "separate events. Preserve every qualification and the 'why' behind each lesson."
    ),
    "trade_knowledge": (
        "CATEGORY: trade_knowledge. Preserve jurisdiction, product, material, "
        "environment, and domain distinctions. If two records apply to incompatible "
        "contexts (e.g. different jurisdictions/products), surface that as a warning "
        "or contradiction and prefer keep_separate/manual_review over a forced merge."
    ),
    "skill": (
        "CATEGORY: skill. Preserve purpose, inputs, outputs, tools, prerequisites, "
        "permissions, side effects, execution behavior, failure conditions, safety "
        "requirements, and which agents/environments it applies to. Complementary "
        "skills may merge only into one coherent operational contract; overlapping "
        "but conflicting skills should stay separate. The canonical 'content' must "
        "be a single SKILL.md body (the system will wrap it in frontmatter)."
    ),
    "playbook": (
        "CATEGORY: playbook. Preserve triggers, prerequisites, the ORDERED steps, "
        "branches, decisions, escalations, rollback, roles, tools/integrations, "
        "completion criteria, and exit conditions. The result must remain executable: "
        "do not drop or reorder steps without cause. The canonical 'content' must be "
        "a single playbook body (the system will wrap it in frontmatter)."
    ),
}


def build_system_prompt(category: str) -> str:
    """Base prompt + the category-specific preservation rules."""
    cat = category if category in CATEGORY_INSTRUCTIONS else "trade_knowledge"
    return f"{CONSOLIDATION_BASE_PROMPT}\n\n{CATEGORY_INSTRUCTIONS[cat]}"


# ─── user prompt ─────────────────────────────────────────────────────────────

def _format_source(idx: int, src: Dict[str, Any]) -> str:
    """Render one source record for the LLM (no embedding ever sent)."""
    parts = [f"--- SOURCE {idx} (id={src.get('id')}) ---"]
    cat = src.get("category")
    if cat:
        parts.append(f"category: {cat}")
    parts.append(f"name: {src.get('name', '')}")
    if src.get("summary"):
        parts.append(f"summary: {src.get('summary')}")
    signals = src.get("signals") or []
    if signals:
        parts.append("signals: " + ", ".join(str(s) for s in signals))
    tags = src.get("tags") or []
    if tags:
        parts.append("tags: " + ", ".join(str(t) for t in tags))
    metadata = src.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    facets = metadata.get("facets") if isinstance(metadata, dict) else None
    if isinstance(facets, dict) and facets:
        parts.append("context: " + json.dumps(facets, ensure_ascii=False))
    for key in (
        "status", "quality_score", "evidence_breadth", "source_pathway",
        "created_at", "updated_at", "merge_count", "version",
        "source_intelligence_ids", "source_ai_interaction_ids",
    ):
        val = src.get(key)
        if val not in (None, "", [], {}):
            parts.append(f"{key}: {json.dumps(val, ensure_ascii=False, default=str)}")
    if isinstance(metadata, dict) and metadata:
        parts.append("metadata: " + json.dumps(metadata, ensure_ascii=False, default=str))
    # Operational fields for skills/playbooks
    for key in ("trigger_conditions", "triggers", "steps", "procedure", "prerequisites",
                "permissions", "tools", "side_effects", "failure_conditions", "safety",
                "completion_criteria", "exit_conditions", "rollback", "applies_to"):
        val = metadata.get(key) if isinstance(metadata, dict) else None
        if val:
            parts.append(f"{key}: {json.dumps(val, ensure_ascii=False)}")
    parts.append("content:")
    parts.append(src.get("content", "") or "")
    return "\n".join(parts)


def build_user_prompt(
    sources: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    category: str,
) -> str:
    """Render the full user message: grouping metrics (labeled non-authoritative) + sources."""
    lines = [f"CATEGORY UNDER REVIEW: {category}"]
    lines.append(
        "GROUPING METRICS (retrieval evidence only — NOT a merge decision): "
        f"pairwise_min={metrics.get('pairwise_min')}, "
        f"pairwise_mean(cohesion)={metrics.get('cohesion')}, "
        f"pairwise_max={metrics.get('pairwise_max')}, "
        f"weak_links={metrics.get('weak_links')}."
    )
    lines.append("")
    for i, src in enumerate(sources, start=1):
        lines.append(_format_source(i, src))
        lines.append("")
    lines.append(
        "Produce the canonical record that preserves every source's unique information, "
        "or recommend keeping them separate. Return the JSON object only."
    )
    return "\n".join(lines)


# ─── structured proposal model ───────────────────────────────────────────────

class CanonicalProposal(BaseModel):
    name: str
    summary: str = ""
    content: str
    signals: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SourceTraceability(BaseModel):
    source_id: str
    retained_items: List[str] = Field(default_factory=list)
    omitted_as_repetition: List[str] = Field(default_factory=list)


class ConsolidationProposal(BaseModel):
    """Strict schema for the LLM consolidation proposal (§5.2)."""
    recommendation: str
    confidence: float = 0.0
    rationale: str = ""
    canonical: Optional[CanonicalProposal] = None
    preserved_information: List[str] = Field(default_factory=list)
    removed_repetition: List[str] = Field(default_factory=list)
    unreconciled_information: List[str] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    source_traceability: List[SourceTraceability] = Field(default_factory=list)
    split_recommendations: List[Any] = Field(default_factory=list)


def validate_proposal(payload: Any, category: str) -> Tuple[Optional[ConsolidationProposal], List[str]]:
    """Validate a parsed LLM payload into a :class:`ConsolidationProposal`.

    Returns ``(proposal, errors)``. On success ``errors`` is empty. The
    ``recommendation`` value is validated against the allowed enum; for
    ``merge``/``merge_with_warnings`` a canonical block is required.
    """
    if not isinstance(payload, dict):
        return None, ["LLM output is not a JSON object"]
    errors: List[str] = []
    try:
        proposal = ConsolidationProposal(**payload)
    except ValidationError as exc:
        return None, [f"schema: {err}" for err in exc.errors()]
    rec = (proposal.recommendation or "").strip()
    if rec not in RECOMMENDATIONS:
        errors.append(f"recommendation must be one of {list(RECOMMENDATIONS)}, got {rec!r}")
    if rec in ("merge", "merge_with_warnings"):
        if proposal.canonical is None:
            errors.append("recommendation requires a canonical block")
        elif not (proposal.canonical.name or "").strip() or not (proposal.canonical.content or "").strip():
            errors.append("canonical.name and canonical.content are required for a merge")
        # Skills/playbooks: the canonical content must round-trip as a valid
        # SKILL.md body (the apply step wraps it in frontmatter; a body that
        # cannot be parsed back is invalid and un-applicable).
        if category in ("skill", "playbook") and proposal.canonical and not errors:
            try:
                from memory_skill_md import parse_skill_md, render_skill_md
                candidate = render_skill_md(
                    name=proposal.canonical.name, category=category,
                    description=proposal.canonical.summary or proposal.canonical.content,
                    body=proposal.canonical.content, metadata=proposal.canonical.metadata,
                    signals=proposal.canonical.signals, tags=proposal.canonical.tags,
                )
                parse_skill_md(candidate)
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(f"skill/playbook validation failed: {exc}")
    if proposal.confidence is not None and not (0.0 <= float(proposal.confidence) <= 1.0):
        # clamp instead of reject — confidence is advisory
        proposal.confidence = max(0.0, min(1.0, float(proposal.confidence)))
    return (proposal if not errors else None), errors


def proposal_to_dict(proposal: ConsolidationProposal) -> Dict[str, Any]:
    """Serialize a validated proposal for JSONB storage."""
    return json.loads(proposal.model_dump_json())


def repair_prompt(errors: List[str], category: str) -> str:
    """Instruction appended on the single allowed repair retry."""
    return (
        f"Your previous response was invalid: {'; '.join(errors)}. "
        f"Return ONLY a valid JSON object for category={category} matching the schema, "
        "with recommendation one of: merge, merge_with_warnings, keep_separate, "
        "split_cluster, manual_review."
    )
