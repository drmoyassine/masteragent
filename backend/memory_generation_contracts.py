"""Versioned structured contracts for Knowledge generation pathways.

The LLM may propose content, but these models define the minimal data that may
enter the Knowledge store.  They deliberately tolerate legacy prompt output at
the boundary while recording a clear upgrade path for seeded prompts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

DECLARATIVE_CATEGORIES = {"best_practices", "lessons_learned", "trade_knowledge"}


class EvidenceFields(BaseModel):
    schema_version: str = "knowledge-generation-v2"
    signals: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    facets: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    qualifications: List[str] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)
    source_support: List[str] = Field(default_factory=list)


class DeclarativeCandidate(EvidenceFields):
    decision: Literal["create", "no_candidate"] = "create"
    name: Optional[str] = None
    category: Optional[str] = None
    summary: str = ""
    content: str = ""

    @model_validator(mode="after")
    def validate_create(self):
        if self.decision == "create":
            if not (self.name or "").strip() or not self.content.strip():
                raise ValueError("A declarative create candidate requires name and content")
            if self.category not in DECLARATIVE_CATEGORIES:
                raise ValueError("Unsupported declarative Knowledge category")
        return self


class SkillCandidate(EvidenceFields):
    target: Literal["skill"] = "skill"
    name: str
    summary: str
    purpose: str = ""
    trigger_desc: str
    procedure: str
    skill_type: Literal["soft", "hard"] = "hard"
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    environments: List[str] = Field(default_factory=list)
    agent_types: List[str] = Field(default_factory=list)
    side_effects: List[str] = Field(default_factory=list)
    failure_conditions: List[str] = Field(default_factory=list)
    recovery: List[str] = Field(default_factory=list)
    safety_requirements: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    edge_cases: List[str] = Field(default_factory=list)


class PlaybookCandidate(EvidenceFields):
    target: Literal["playbook"] = "playbook"
    name: str
    description: str
    purpose: str = ""
    expected_outcome: str = ""
    signal_type: Optional[str] = None
    trigger_conditions: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    required_inputs: List[str] = Field(default_factory=list)
    responsible_roles: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    branches: List[str] = Field(default_factory=list)
    escalation_rules: List[str] = Field(default_factory=list)
    failure_conditions: List[str] = Field(default_factory=list)
    rollback: List[str] = Field(default_factory=list)
    safety_requirements: List[str] = Field(default_factory=list)
    completion_criteria: List[str] = Field(default_factory=list)
    exit_conditions: List[str] = Field(default_factory=list)


def _raise_contract(context: str, exc: Exception) -> None:
    raise ValueError(f"Invalid {context} generation contract: {exc}") from exc


def validate_declarative(payload: Dict[str, Any]) -> DeclarativeCandidate:
    try:
        # Legacy seeded prompts did not return an explicit decision/confidence.
        # Keep existing customized prompts operational while new seed v2 provides
        # the complete contract.
        normalized = {**payload}
        normalized.setdefault("decision", "create")
        normalized.setdefault("confidence", 0.5)
        normalized.setdefault("signals", payload.get("knowledge_type", []))
        normalized.setdefault("facets", (payload.get("metadata") or {}).get("facets", {}))
        return DeclarativeCandidate.model_validate(normalized)
    except ValidationError as exc:
        _raise_contract("declarative", exc)


def validate_telemetry_candidate(payload: Dict[str, Any]) -> EvidenceFields:
    try:
        target = payload.get("target")
        if target == "skill":
            normalized = {**payload, "trigger_desc": payload.get("trigger_desc") or payload.get("summary") or "", "procedure": payload.get("procedure") or payload.get("content") or "", "summary": payload.get("summary") or ""}
            return SkillCandidate.model_validate(normalized)
        if target == "playbook":
            normalized = {**payload, "description": payload.get("description") or payload.get("summary") or payload.get("content") or ""}
            return PlaybookCandidate.model_validate(normalized)
        normalized = {**payload, "decision": "create", "category": target}
        return validate_declarative(normalized)
    except ValidationError as exc:
        _raise_contract("telemetry", exc)


def validate_playbook(payload: Dict[str, Any]) -> PlaybookCandidate:
    try:
        return PlaybookCandidate.model_validate({
            **payload, "target": "playbook", "confidence": payload.get("confidence", 0.5),
            "description": payload.get("description") or payload.get("summary") or "",
        })
    except ValidationError as exc:
        _raise_contract("playbook", exc)


def validate_skill(payload: Dict[str, Any]) -> SkillCandidate:
    try:
        return SkillCandidate.model_validate({
            **payload, "target": "skill", "confidence": payload.get("confidence", 0.5),
            "summary": payload.get("summary") or payload.get("trigger_desc") or "",
            "trigger_desc": payload.get("trigger_desc") or payload.get("summary") or "",
            "procedure": payload.get("procedure") or payload.get("content") or "",
        })
    except ValidationError as exc:
        _raise_contract("skill", exc)
