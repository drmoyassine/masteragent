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
        "metadata:",
        "  source: masteragent",
        f"  category: {category}",
        f"  version: {int(version or 1)}",
    ]
    if signals:
        lines.append(f"  signals: [{', '.join(_yaml_escape(s) for s in signals if s)}]")
    if tags:
        lines.append(f"  tags: [{', '.join(_yaml_escape(t) for t in tags if t)}]")
    if category == "skill" and metadata.get("skill_type"):
        lines.append(f"  skill_type: {metadata['skill_type']}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {(name or 'Unnamed').strip()}")
    lines.append("")

    if category == "playbook":
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
        steps = metadata.get("steps") or []
        if steps:
            lines.append("## Steps")
            lines.append("")
            for s in sorted(steps, key=lambda x: x.get("order", 0) if isinstance(x, dict) else 0):
                action = s.get("action", "") if isinstance(s, dict) else str(s)
                lines.append(f"{s.get('order', '')}. {action}" if isinstance(s, dict) and s.get("order") else f"- {action}")
            lines.append("")
    else:  # skill
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

    return {"name": name, "description": description, "body": body, "meta": fields}
