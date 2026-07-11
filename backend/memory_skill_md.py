"""SKILL.md rendering + parsing for the unified knowledge table.

Follows the Anthropic agent-skills standard: YAML frontmatter with `name`
(lowercase-hyphen slug, <=64 chars) and `description` (<=1024 chars stating
what the skill does AND when to use it), followed by a markdown instruction
body. For category='skill' and category='playbook' records the `content`
column stores this full document verbatim — there is no separate column.
`summary` keeps the description for compact context injection; `metadata`
keeps the structured steps/trigger_conditions for programmatic access.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

SKILL_MD_CATEGORIES = ("skill", "playbook")


def slugify(name: str, max_len: int = 64) -> str:
    """Spec-compliant skill name: lowercase letters, digits, hyphens; <=64 chars."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:max_len].rstrip("-") or "unnamed-skill"


def is_skill_md(text: Optional[str]) -> bool:
    """True when the text already is a SKILL.md document (frontmatter present)."""
    return bool(text) and text.lstrip().startswith("---")


def _yaml_escape(value: str) -> str:
    """Quote a scalar for safe inline YAML."""
    value = (value or "").replace("\n", " ").strip()
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_skill_md(
    *,
    name: str,
    category: str,
    description: str,
    body: str = "",
    metadata: Optional[dict] = None,
    signals: Optional[list] = None,
    tags: Optional[list] = None,
    version: int = 1,
) -> str:
    """Render a standard-compliant SKILL.md document from knowledge-record fields.

    Playbooks render their trigger conditions and ordered steps into the body;
    skills render their procedure. Both share the same SKILL.md format (the
    agent-skills standard has no separate playbook format).
    """
    metadata = metadata or {}
    description = (description or "").strip()[:1024] or f"Organizational {category} extracted from experience."

    lines = [
        "---",
        f"name: {slugify(name)}",
        f"description: {_yaml_escape(description)}",
    ]
    # These are optional Agent Skills frontmatter fields. They are emitted only
    # from explicitly governed metadata; merely mentioning a tool in a skill
    # body does not create an allowed-tools grant.
    compatibility = str(metadata.get("compatibility") or "").strip()
    if compatibility:
        lines.append(f"compatibility: {_yaml_escape(compatibility[:500])}")
    allowed_tools = [str(tool).strip() for tool in (metadata.get("allowed_tools") or []) if str(tool).strip()]
    if allowed_tools:
        lines.append(f"allowed-tools: {_yaml_escape(' '.join(allowed_tools))}")
    lines.extend([
        "metadata:",
        "  source: masteragent",
        f"  category: {category}",
        f"  version: {int(version or 1)}",
    ])
    # Agent Skills metadata is a string key/value map. Structured arrays stay
    # authoritative in the Knowledge database; export a portable string view.
    if signals:
        lines.append(f"  signals: {_yaml_escape(', '.join(str(s) for s in signals if s))}")
    if tags:
        lines.append(f"  tags: {_yaml_escape(', '.join(str(t) for t in tags if t))}")
    if category == "skill" and metadata.get("skill_type"):
        lines.append(f"  skill_type: {metadata['skill_type']}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {(name or 'Unnamed').strip()}")
    lines.append("")

    def _list_section(title: str, values) -> None:
        values = [str(v).strip() for v in (values or []) if str(v).strip()]
        if not values:
            return
        lines.extend([f"## {title}", ""])
        lines.extend(f"- {value}" for value in values)
        lines.append("")

    if category == "playbook":
        if metadata.get("purpose"):
            lines.extend(["## Purpose", "", str(metadata["purpose"]).strip(), ""])
        if metadata.get("expected_outcome"):
            lines.extend(["## Expected outcome", "", str(metadata["expected_outcome"]).strip(), ""])
        if body:
            lines.append(body.strip())
            lines.append("")
        triggers = metadata.get("trigger_conditions") or []
        if triggers:
            lines.append("## When to use")
            lines.append("")
            for t in triggers:
                lines.append(f"- {t}")
            lines.append("")
        _list_section("Prerequisites", metadata.get("prerequisites"))
        _list_section("Required inputs", metadata.get("required_inputs"))
        _list_section("Responsible roles", metadata.get("responsible_roles"))
        _list_section("Tools and integrations", metadata.get("tools"))
        steps = metadata.get("steps") or []
        if steps:
            lines.append("## Steps")
            lines.append("")
            for s in sorted(steps, key=lambda x: x.get("order", 0) if isinstance(x, dict) else 0):
                action = s.get("action", "") if isinstance(s, dict) else str(s)
                lines.append(f"{s.get('order', '')}. {action}" if isinstance(s, dict) and s.get("order") else f"- {action}")
            lines.append("")
        _list_section("Branches and decisions", metadata.get("branches"))
        _list_section("Escalation", metadata.get("escalation_rules"))
        _list_section("Failure conditions", metadata.get("failure_conditions"))
        _list_section("Rollback and recovery", metadata.get("rollback"))
        _list_section("Safety requirements", metadata.get("safety_requirements"))
        _list_section("Completion criteria", metadata.get("completion_criteria"))
        _list_section("Exit conditions", metadata.get("exit_conditions"))
    else:  # skill
        if metadata.get("purpose"):
            lines.extend(["## Purpose", "", str(metadata["purpose"]).strip(), ""])
        trigger_desc = metadata.get("trigger_desc") or ""
        if trigger_desc and trigger_desc.strip() != description:
            lines.append("## When to use")
            lines.append("")
            lines.append(trigger_desc.strip())
            lines.append("")
        procedure = metadata.get("procedure") or body
        if procedure:
            lines.append("## Procedure")
            lines.append("")
            lines.append(procedure.strip())
            lines.append("")
        _list_section("Inputs", metadata.get("inputs"))
        _list_section("Outputs", metadata.get("outputs"))
        _list_section("Prerequisites", metadata.get("prerequisites"))
        _list_section("Tools and integrations", metadata.get("tools"))
        _list_section("Permissions", metadata.get("permissions"))
        _list_section("Applicable environments", metadata.get("environments"))
        _list_section("Side effects", metadata.get("side_effects"))
        _list_section("Failure conditions", metadata.get("failure_conditions"))
        _list_section("Recovery", metadata.get("recovery"))
        _list_section("Safety requirements", metadata.get("safety_requirements"))
        _list_section("Examples", metadata.get("examples"))
        _list_section("Edge cases", metadata.get("edge_cases"))

    return "\n".join(lines).rstrip() + "\n"


def render_knowledge_md(
    *,
    name: str,
    category: str,
    description: str,
    content: str,
    signals: Optional[list] = None,
    tags: Optional[list] = None,
    quality_score: Optional[float] = None,
    version: int = 1,
) -> str:
    """Render a declarative knowledge record (best_practices / lessons_learned /
    trade_knowledge) as a memory-file-style markdown document.

    Export-only: unlike skills/playbooks the source `content` is NOT stored in
    this format (it feeds LLM prompts where frontmatter is noise). All fields are
    relational, so this rendering is lossless. Follows the same frontmatter
    discovery-header principle as the agent-skills standard: name + description
    let a consumer decide relevance before loading the body.
    """
    description = (description or "").strip()[:1024] or f"Organizational {category}."
    lines = [
        "---",
        f"name: {slugify(name)}",
        f"description: {_yaml_escape(description)}",
        "metadata:",
        "  source: masteragent",
        f"  category: {category}",
        f"  version: {int(version or 1)}",
    ]
    if quality_score is not None:
        lines.append(f"  quality_score: {round(float(quality_score), 3)}")
    if signals:
        lines.append(f"  signals: [{', '.join(_yaml_escape(s) for s in signals if s)}]")
    if tags:
        lines.append(f"  tags: [{', '.join(_yaml_escape(t) for t in tags if t)}]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {(name or 'Unnamed').strip()}")
    lines.append("")
    lines.append((content or "").strip())
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_any_knowledge_md(row: dict) -> str:
    """Render any knowledge row to markdown, dispatching by category.

    skill/playbook → SKILL.md (verbatim if already frontmatter'd, else rendered);
    declarative categories → memory-file markdown. `row` is a dict of the
    knowledge columns.
    """
    import json as _json
    category = row.get("category") or "trade_knowledge"
    content = row.get("content") or ""
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = _json.loads(metadata)
        except Exception:
            metadata = {}
    signals = row.get("signals") or []
    tags = row.get("tags") or []
    version = row.get("version") or 1

    if category in SKILL_MD_CATEGORIES:
        if is_skill_md(content):
            return content
        return render_skill_md(
            name=row.get("name", ""),
            category=category,
            description=row.get("summary") or content,
            body=content,
            metadata=metadata,
            signals=signals,
            tags=tags,
            version=version,
        )
    return render_knowledge_md(
        name=row.get("name", ""),
        category=category,
        description=row.get("summary") or content,
        content=content,
        signals=signals,
        tags=tags,
        quality_score=row.get("quality_score"),
        version=version,
    )


def parse_skill_md(text: str) -> dict:
    """Parse a SKILL.md document into {name, description, body, meta}.

    Minimal frontmatter parser: top-level `key: value` scalars only (the two
    required spec fields are scalars). Nested mappings are ignored for import
    purposes; the document itself is stored verbatim.
    """
    text = (text or "").lstrip("﻿").strip()
    if not text.startswith("---"):
        raise ValueError("Not a SKILL.md document: missing frontmatter delimiter '---'")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Not a SKILL.md document: unterminated frontmatter")

    frontmatter, body = parts[1], parts[2].strip()
    fields = {}
    for line in frontmatter.splitlines():
        if not line.strip() or line.startswith((" ", "\t")):
            continue  # skip blank + nested lines
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"').strip("'")
        fields[key.strip().lower()] = value

    name = fields.get("name", "")
    description = fields.get("description", "")
    if not name:
        raise ValueError("SKILL.md missing required frontmatter field: name")
    if not description:
        raise ValueError("SKILL.md missing required frontmatter field: description")
    if len(name) > 64 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError("SKILL.md name must use lowercase letters, numbers, and single hyphens (max 64 chars)")
    if len(description) > 1024:
        raise ValueError("SKILL.md description must be 1024 characters or fewer")

    return {"name": name, "description": description, "body": body, "meta": fields}


def validate_skill_md(text: str, package_name: Optional[str] = None) -> dict:
    """Validate the portable single-file Agent Skills subset we support.

    This is an equivalent in-process guard for generated/imported documents.
    A deployment may additionally run the external ``skills-ref validate`` tool,
    but generation and import must remain safe when that optional CLI is absent.
    """
    parsed = parse_skill_md(text)
    if package_name is not None and parsed["name"] != package_name:
        raise ValueError("SKILL.md name must match its package directory")
    return parsed
