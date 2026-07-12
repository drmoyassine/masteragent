"""Knowledge facets + the always-on Knowledge Management skill (Sprint 2.5).

Facets are governed, structured filter dimensions stored at `metadata.facets`.
Unlike freeform `tags`, facet keys come from a configurable schema and values
are normalized at extraction — so they are safe for agents to filter on.

This module is deliberately additive: it never alters generated `content` or
`summary`, and every function degrades to a no-op ({}) on any failure so
knowledge creation can never regress.
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── Default global facet schema (study-abroad domain) ────────────────────────
DEFAULT_FACETS_SCHEMA = [
    {"key": "country", "label": "Country", "description": "Country the information pertains to", "examples": ["Malaysia", "United Kingdom", "Australia"]},
    {"key": "university", "label": "University", "description": "Specific institution name, if applicable"},
    {"key": "program", "label": "Program / Major", "description": "Field of study or program name"},
    {"key": "field_of_study", "label": "Field", "description": "Broad discipline (e.g. Engineering, Business)"},
    {"key": "level", "label": "Level", "description": "Study level: undergraduate | postgraduate | foundation | phd | diploma"},
    {"key": "requirement_type", "label": "Requirement type", "description": "entry | english | visa | financial | document | deadline"},
    {"key": "intake", "label": "Intake", "description": "Intake term/year if specific (e.g. Fall 2026)"},
]

# facet_key → entity_profiles.properties key. Admin configures to match CRM.
DEFAULT_PROFILE_FACET_MAP = {
    "country": "country",
    "program": "program",
    "university": "university",
    "level": "level",
}

# Stable id so seeding is idempotent across restarts.
MANAGEMENT_SKILL_ID = "00000000-0000-0000-0000-knowledge-mgmt"
MANAGEMENT_SKILL_NAME = "Knowledge Management Protocol"


def _management_skill_body() -> str:
    """The protocol body taught to every agent. Concise + imperative."""
    return (
        "## What the injected knowledge is\n"
        "The knowledge items provided alongside this skill are **experiential knowledge** "
        "this organization has accumulated from past interactions — best practices, lessons "
        "learned, trade knowledge, playbooks, and skills. This is a **subset** of what you "
        "can do, not the whole of it.\n\n"
        "## How it was selected\n"
        "The list was filtered to the current conversation's context using governed facets "
        "(such as country, program, level). Items may arrive as a **lean index** "
        "(`id, name, category, signals, summary, facets` — no full content) or as full "
        "records, depending on configuration. When an item has no `content` field, treat "
        "it as an index entry and pull the full record before acting on it.\n\n"
        "## Critical rule: absence does not mean absence\n"
        "**An empty or sparse knowledge list does NOT mean the knowledge or capability is "
        "absent.** It means only that we have not yet codified experiential knowledge matching "
        "these exact facets. Never conclude 'we don't know how to handle this' from a thin list.\n\n"
        "## How to use an index entry\n"
        "If an item looks relevant, **retrieve its full record** via the knowledge sub-agent "
        "node (`GET /knowledge/{id}`) before acting on it. The summary is a teaser, not the "
        "full procedure.\n\n"
        "## Fallback ladder when the index is thin\n"
        "1. **Broaden** — re-query `/search/semantic` with `strict=false` (facets dropped) to "
        "find near-matches outside the current facet filter.\n"
        "2. **Use your assigned tools** per the system prompt to source the information.\n"
        "3. **Delegate** to the specialized counselor sub-agent to find or produce it.\n\n"
        "## Facet discipline\n"
        "Filter only on governed facet keys. **Do not invent facet values** — use values you "
        "have seen in the index, in the contact's CRM profile, or from `GET /knowledge/facets`. "
        "If unsure whether a value is valid, broaden the search semantically instead of guessing.\n\n"
        "## Contributing back\n"
        "Knowledge is generated **automatically** from interactions — your job is to use and "
        "delegate, not to write knowledge manually. If a record helped or failed, submit "
        "feedback via `POST /knowledge/{id}/feedback` so its quality score improves."
    )


# ── Schema / config accessors ────────────────────────────────────────────────

def get_facets_schema() -> list:
    """Global facets schema from memory_settings (empty list = none configured)."""
    from memory_services import get_memory_settings
    try:
        settings = get_memory_settings() or {}
        schema = settings.get("knowledge_facets_schema")
        if isinstance(schema, str):
            schema = json.loads(schema)
        return schema or []
    except Exception as e:
        logger.warning(f"get_facets_schema failed: {e}")
        return []


def get_profile_facet_map() -> dict:
    from memory_services import get_memory_settings
    try:
        settings = get_memory_settings() or {}
        m = settings.get("profile_facet_map")
        if isinstance(m, str):
            m = json.loads(m)
        return m or {}
    except Exception:
        return {}


def facet_prompt_instructions() -> str:
    """Compact governed schema instructions for primary generation prompts."""
    schema = get_facets_schema()
    if not schema:
        return 'Return "facets": {}.'
    keys = "\n".join(
        f"- {item.get('key')}: {item.get('description', '')}"
        for item in schema if item.get("key")
    )
    return (
        "Return a `facets` object using ONLY the governed keys below. Include a scalar value "
        "only when explicitly supported by the source; never infer or guess.\n" + keys
    )


def validate_generated_facets(facets: object, explicit: Optional[dict] = None) -> tuple[dict, dict]:
    """Validate generated facets and preserve authoritative explicit values."""
    schema = get_facets_schema()
    allowed = {item.get("key"): item for item in schema if item.get("key")}
    output = dict(explicit or {})
    rejected = []
    if isinstance(facets, dict):
        for key, value in facets.items():
            if key not in allowed or key in output or value in (None, "", [], {}):
                if key not in allowed: rejected.append(key)
                continue
            if isinstance(value, (dict, list)):
                rejected.append(key)
                continue
            output[key] = str(value).strip()
    return output, {"status": "explicit" if explicit else "succeeded", "rejected_keys": rejected}


# ── Facet extraction (creation-side, WS-4) ───────────────────────────────────

async def extract_facets(name: str, content: str, summary: str) -> dict:
    """Extract governed facets for a knowledge record via one LLM call.

    Returns {} when disabled, unconfigured, or on any failure — never blocks
    or alters knowledge creation (zero-regression)."""
    from memory_services import get_memory_settings, call_llm
    from services.llm import parse_llm_json

    try:
        settings = get_memory_settings() or {}
        if not settings.get("facet_extraction_enabled", True):
            return {}
        schema = get_facets_schema()
        if not schema:
            return {}

        keys_block = "\n".join(
            f"- {s.get('key')}: {s.get('description', '')}" for s in schema if s.get("key")
        )
        valid_keys = {s.get("key") for s in schema if s.get("key")}
        system_prompt = (
            "You extract structured facets from a knowledge record for use as hard filter "
            "dimensions. For each facet key below, extract a value ONLY if it is clearly and "
            "explicitly present in the text; omit keys that are not present. Normalize values "
            "to canonical form (proper casing, full names — e.g. 'Malaysia' not 'malaysia'/'MY'). "
            "Do not infer or guess.\n\n"
            f"Valid facet keys:\n{keys_block}\n\n"
            'Return ONLY a JSON object: {"key": "value", ...}'
        )
        user_msg = f"Name: {name}\nSummary: {summary or ''}\nContent:\n{(content or '')[:4000]}"
        result_text = await call_llm(
            user_msg,
            system_prompt=system_prompt,
            max_tokens=400,
            task_type="knowledge_generation",
        )
        facets = parse_llm_json(result_text, context="facet_extraction")
        if not isinstance(facets, dict):
            return {}
        # Coerce to trimmed scalar strings so JSONB @> containment matches reliably
        # (a list/number value would never match a scalar hard filter).
        out: dict = {}
        for k, v in facets.items():
            if k not in valid_keys or v in (None, "", [], {}):
                continue
            if isinstance(v, (list, dict)):
                continue
            sval = str(v).strip()
            if sval:
                out[k] = sval
        return out
    except Exception as e:
        from services.job_safety import ProviderStopError
        if isinstance(e, ProviderStopError):
            raise
        logger.warning(f"extract_facets failed (returning {{}}): {e}")
        return {}


def canonicalize_facets(cursor, facets: dict, drop_unmatched: bool = False) -> dict:
    """Map facet values to their canonical form as actually stored in the DB,
    case-insensitively. Prevents silent false-negatives when a value's casing
    differs from what was extracted (e.g. CRM 'malaysia' vs stored 'Malaysia').

    - Matched values are replaced with the stored canonical spelling.
    - Unmatched values: dropped when drop_unmatched=True (profile-derived — never
      filter on a value that exists nowhere, which would zero out results), or
      kept as-is when False (explicit caller intent).
    """
    if not facets:
        return {}
    result: dict = {}
    for key, val in facets.items():
        if val in (None, ""):
            continue
        sval = str(val).strip()
        try:
            cursor.execute("""
                SELECT DISTINCT metadata->'facets'->>%s AS v
                FROM knowledge
                WHERE status = 'active'
                  AND (visibility = 'shared' OR visibility IS NULL)
                  AND metadata->'facets' ? %s
            """, (key, key))
            stored = [row["v"] for row in cursor.fetchall() if row["v"]]
        except Exception:
            stored = []
        match = next((s for s in stored if s.lower() == sval.lower()), None)
        if match:
            result[key] = match
        elif not drop_unmatched:
            result[key] = sval
    return result


async def enrich_metadata_with_facets(
    metadata: Optional[dict], name: str, content: str, summary: str
) -> dict:
    """Return a copy of `metadata` with `facets` merged in. Callers pass the
    result to insert_knowledge. Keeps facets out of the rendered SKILL.md body
    (the renderer only reads operational keys)."""
    md = dict(metadata or {})
    explicit = md.get("facets") if isinstance(md.get("facets"), dict) else {}
    extracted = await extract_facets(name, content, summary)
    validated, _ = validate_generated_facets(extracted, explicit=explicit)
    md["facets"] = validated
    return md


# ── Backfill (WS-4) ──────────────────────────────────────────────────────────

async def backfill_facets(batch_size: int = 25, max_records: int = 1000,
                          progress_run_id: Optional[str] = None) -> dict:
    """Run extract_facets over active knowledge records missing metadata.facets.
    Best-effort; resolves facets from name+summary+content using the global schema."""
    from core.storage import get_memory_db_context
    processed, updated = 0, 0
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            # Reprocess records with no facets OR empty facets ({}), so records
            # created while extraction was disabled are not permanently skipped.
            cursor.execute("""
                SELECT id, name, summary, content FROM knowledge
                WHERE status = 'active'
                  AND COALESCE(metadata->'facets', '{}'::jsonb) = '{}'::jsonb
                ORDER BY created_at ASC LIMIT %s
            """, (max_records,))
            rows = [dict(r) for r in cursor.fetchall()]

        for r in rows:
            from services.job_controls import get_command
            if get_command("backfill_facets") in {"pause", "cancel"}:
                logger.info("Facet backfill stopped at checkpoint")
                break
            processed += 1
            facets = await extract_facets(r.get("name", ""), r.get("content", ""), r.get("summary", ""))
            if not facets:
                continue
            with get_memory_db_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE knowledge
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('facets', %s::jsonb),
                        updated_at = NOW()
                    WHERE id = %s AND COALESCE(metadata->'facets', '{}'::jsonb) = '{}'::jsonb
                """, (json.dumps(facets), r["id"]))
                if cursor.rowcount:
                    updated += 1
            if processed % batch_size == 0:
                logger.info(f"Facet backfill progress: {processed}/{len(rows)} ({updated} enriched)")
            if progress_run_id:
                from memory_db_writes import update_pipeline_run
                update_pipeline_run(progress_run_id, progress_completed=processed,
                                    progress_failed=max(0, processed - updated),
                                    detail={"enriched": updated, "source_rows": len(rows),
                                            "checkpoint": {"last_record_id": str(r["id"])}})
        logger.info(f"Facet backfill complete: processed={processed}, enriched={updated}")
    except Exception as e:
        from services.job_safety import ProviderStopError
        if isinstance(e, ProviderStopError):
            logger.warning("Facet backfill stopped by provider: %s", e)
            raise
        logger.error(f"backfill_facets failed: {e}")
    return {"processed": processed, "enriched": updated}


# ── Management skill seeding (WS-3) ──────────────────────────────────────────

def seed_management_skill() -> None:
    """Idempotently seed the always-on Knowledge Management skill. Called from
    the schema migration block on startup."""
    from core.storage import get_memory_db_context
    from memory_skill_md import render_skill_md
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM knowledge WHERE id = %s", (MANAGEMENT_SKILL_ID,))
            if cursor.fetchone():
                return
            metadata = {
                "always_inject": True,
                "skill_type": "soft",
                "trigger_desc": "Always active — governs how to read and use the injected knowledge index.",
                "entity_types": [],
                "playbook_ids": [],
            }
            body = _management_skill_body()
            description = (
                "Always-on protocol governing how to read the injected knowledge index, retrieve "
                "full records on demand, broaden searches, and extend knowledge. Teaches that an "
                "empty/sparse index does not mean the knowledge or capability is absent."
            )
            content = render_skill_md(
                name=MANAGEMENT_SKILL_NAME,
                category="skill",
                description=description,
                body=body,
                metadata=metadata,
                signals=[],
                tags=[],
                version=1,
            )
            cursor.execute("""
                INSERT INTO knowledge (
                    id, source_intelligence_ids, signals, name, content, summary,
                    visibility, tags, category, metadata, source_pathway,
                    extraction_confidence, quality_score, status, version, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
            """, (
                MANAGEMENT_SKILL_ID, [], [], MANAGEMENT_SKILL_NAME, content, description,
                "shared", [], "skill", json.dumps(metadata), "system",
                1.0, 1.0, "active", 1,
            ))
        logger.info("Seeded Knowledge Management skill")
    except Exception as e:
        logger.warning(f"seed_management_skill failed: {e}")


def seed_default_facets_schema() -> None:
    """Idempotently seed the global facets schema if unset.

    NOTE: profile_facet_map is intentionally NOT auto-seeded — a populated map
    would auto-activate facet hard-filtering on every get-context (deriving
    facets from CRM profiles), which would exclude un-facetted records and
    change injection behavior before backfill runs. The map is opt-in: the
    admin configures it (see DEFAULT_PROFILE_FACET_MAP) once facets are populated."""
    from core.storage import get_memory_db_context
    try:
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE memory_settings
                SET knowledge_facets_schema = %s
                WHERE (knowledge_facets_schema IS NULL OR knowledge_facets_schema = 'null')
            """, (json.dumps(DEFAULT_FACETS_SCHEMA),))
    except Exception as e:
        logger.warning(f"seed_default_facets_schema failed: {e}")
