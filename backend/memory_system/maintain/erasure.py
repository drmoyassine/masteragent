"""TASK-262 Part 2 — entity-level erasure with lineage traversal.

Removes every trace of one entity from the memory system, INCLUDING the
lineage references other entities' artifacts hold to it:

  owned rows (deleted)
    - interactions      where primary_entity = (entity)
    - memories          where primary_entity = (entity)
    - intelligence      where primary_entity = (entity)
    - knowledge         citing ONLY erased sources (direct arrays + one
                        merged_from hop — merge artifacts of erased rows)
    - knowledge_source_links pointing at erased rows or erased sources
    - entity_profiles   the profile row itself
    - memory_agent_entities  every agent's access grants on the entity

  citing rows (STRIPPED, never deleted — they belong to other entities)
    - other-entity memories:        interaction_ids loses erased interactions
    - other-entity intelligence:    source_memory_ids loses erased memories
    - surviving knowledge rows:     source arrays lose erased ids

All id sets are collected BEFORE any delete (the lineage traversal reads
arrays that the deletes would otherwise invalidate), then the destructive
phase runs in ONE transaction. Knowledge deletion is conservative: a row is
deleted only when NO source survives anywhere — arrays empty after stripping
AND no source link pointing outside the erased set.

dry_run (the default) collects and reports the footprint without touching a
row. The destructive path is admin-API only (require_admin_auth — the
mcp-service identity is refused there by design, TASK-259), and every call —
including dry runs — is audit-logged to memory_audit_log.
"""
import logging

from core.storage import get_memory_db_context, flush_interaction_cache

logger = logging.getLogger(__name__)


def _ids(cursor, sql: str, params: tuple) -> list:
    cursor.execute(sql, params)
    return [r["id"] for r in cursor.fetchall()]


def collect_entity_footprint(cursor, entity_type: str, entity_id: str) -> dict:
    """Read-only traversal. Returns id sets, counts, and capped samples.

    Collection order follows the citation direction: interactions (nothing
    upstream cites them) → memories → intelligence → knowledge.
    """
    interaction_ids = _ids(
        cursor,
        "SELECT id FROM interactions WHERE primary_entity_type=%s AND primary_entity_id=%s",
        (entity_type, entity_id),
    )
    memory_ids = _ids(
        cursor,
        "SELECT id FROM memories WHERE primary_entity_type=%s AND primary_entity_id=%s",
        (entity_type, entity_id),
    )
    citing_memory_ids = _ids(
        cursor,
        """
        SELECT id FROM memories
        WHERE NOT (primary_entity_type=%s AND primary_entity_id=%s)
          AND interaction_ids && %s
        """,
        (entity_type, entity_id, interaction_ids),
    ) if interaction_ids else []
    intelligence_ids = _ids(
        cursor,
        "SELECT id FROM intelligence WHERE primary_entity_type=%s AND primary_entity_id=%s",
        (entity_type, entity_id),
    )
    citing_intelligence_ids = _ids(
        cursor,
        """
        SELECT id FROM intelligence
        WHERE NOT (primary_entity_type=%s AND primary_entity_id=%s)
          AND source_memory_ids && %s
        """,
        (entity_type, entity_id, memory_ids),
    ) if memory_ids else []

    # Knowledge citing erased intelligence or interactions (direct arrays).
    knowledge_ids = _ids(
        cursor,
        """
        SELECT id FROM knowledge
        WHERE source_intelligence_ids && %s OR source_ai_interaction_ids && %s
        """,
        (intelligence_ids, interaction_ids),
    ) if (intelligence_ids or interaction_ids) else []
    # One merged_from hop: merge artifacts of already-erased rows. Their own
    # surviving-source test still decides delete vs strip.
    merged_rows = _ids(
        cursor,
        "SELECT id FROM knowledge WHERE merged_from && %s AND NOT (id = ANY(%s))",
        (knowledge_ids, knowledge_ids),
    ) if knowledge_ids else []
    knowledge_ids = knowledge_ids + merged_rows

    # Source links pointing at any erased row (evaluated BEFORE any deletion).
    erased_sources = interaction_ids + memory_ids + intelligence_ids
    linked_rows = 0
    if erased_sources:
        cursor.execute(
            "SELECT COUNT(*) AS n FROM knowledge_source_links WHERE source_id = ANY(%s)",
            (erased_sources,),
        )
        linked_rows = cursor.fetchone()["n"]

    counts = {
        "interactions": len(interaction_ids),
        "memories": len(memory_ids),
        "citing_memories_stripped": len(citing_memory_ids),
        "intelligence": len(intelligence_ids),
        "citing_intelligence_stripped": len(citing_intelligence_ids),
        "knowledge_candidates": len(knowledge_ids),
        "source_links": linked_rows,
    }
    samples = {
        "interactions": interaction_ids[:10],
        "memories": memory_ids[:10],
        "intelligence": intelligence_ids[:10],
        "knowledge_candidates": knowledge_ids[:10],
    }
    return {
        "interaction_ids": interaction_ids,
        "memory_ids": memory_ids,
        "citing_memory_ids": citing_memory_ids,
        "intelligence_ids": intelligence_ids,
        "citing_intelligence_ids": citing_intelligence_ids,
        "knowledge_ids": knowledge_ids,
        "erased_sources": erased_sources,
        "counts": counts,
        "samples": samples,
    }


def _strip_arrays(cursor, table: str, array_col: str, row_ids: list, dead: list) -> int:
    """Remove dead ids from array_col on the given rows; returns rows changed."""
    if not row_ids or not dead:
        return 0
    dead_set = set(dead)
    changed = 0
    for rid in row_ids:
        cursor.execute(f"SELECT {array_col} AS arr FROM {table} WHERE id=%s", (rid,))
        row = cursor.fetchone()
        if not row:
            continue
        kept = [x for x in (row["arr"] or []) if x not in dead_set]
        if len(kept) != len(row["arr"] or []):
            cursor.execute(
                f"UPDATE {table} SET {array_col}=%s WHERE id=%s", (kept, rid),
            )
            changed += 1
    return changed


def erase_entity(entity_type: str, entity_id: str, *, actor: str, dry_run: bool = True) -> dict:
    """Collect the footprint; unless dry_run, erase it in one transaction.

    dry_run runs are audit-logged as entity_erase_dry_run, executed ones as
    entity_erase. The destructive path is reached only through the admin API
    (require_admin_auth) — never from agent or service identities.
    """
    entity_type = (entity_type or "").strip()
    entity_id = (entity_id or "").strip()
    if not entity_type or not entity_id:
        raise ValueError("entity_type and entity_id are required")

    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        fp = collect_entity_footprint(cursor, entity_type, entity_id)
        result = {
            "entity": f"{entity_type}/{entity_id}",
            "dry_run": dry_run,
            "footprint": fp["counts"],
            "samples": fp["samples"],
        }
        if dry_run:
            _audit(actor, "entity_erase_dry_run", entity_type, entity_id, result)
            return result

        intelligence_set = set(fp["intelligence_ids"])
        interaction_set = set(fp["interaction_ids"])
        knowledge_set = set(fp["knowledge_ids"])
        erased_sources = fp["erased_sources"]

        # 1. Knowledge: strip or delete, per row (conservative deletion).
        knowledge_deleted, knowledge_stripped = [], 0
        for kid in fp["knowledge_ids"]:
            cursor.execute(
                """
                SELECT source_intelligence_ids AS si, source_ai_interaction_ids AS sa,
                       merged_from AS mf
                FROM knowledge WHERE id=%s
                """,
                (kid,),
            )
            row = cursor.fetchone()
            if not row:
                continue
            si = [x for x in (row["si"] or []) if x not in intelligence_set]
            sa = [x for x in (row["sa"] or []) if x not in interaction_set]
            mf = [x for x in (row["mf"] or []) if x not in knowledge_set]
            if si or sa or mf:
                cursor.execute(
                    """
                    UPDATE knowledge SET source_intelligence_ids=%s,
                        source_ai_interaction_ids=%s, merged_from=%s, updated_at=now()
                    WHERE id=%s
                    """,
                    (si, sa, mf, kid),
                )
                knowledge_stripped += 1
                continue
            # Arrays fully erased — delete only if no source link survives
            # pointing OUTSIDE the erased set (link-only evidence keeps the row).
            cursor.execute(
                """
                SELECT 1 FROM knowledge_source_links
                WHERE knowledge_id=%s AND NOT (source_id = ANY(%s)) LIMIT 1
                """,
                (kid, erased_sources),
            )
            if cursor.fetchone():
                knowledge_stripped += 1
            else:
                cursor.execute("DELETE FROM knowledge WHERE id=%s", (kid,))
                knowledge_deleted.append(kid)
        result["knowledge_deleted"] = len(knowledge_deleted)
        result["knowledge_stripped"] = knowledge_stripped

        # 2. Source links: erased sources, and links of deleted knowledge rows.
        cursor.execute(
            """
            DELETE FROM knowledge_source_links
            WHERE source_id = ANY(%s) OR knowledge_id = ANY(%s)
            """,
            (erased_sources, knowledge_deleted),
        )
        result["source_links_deleted"] = cursor.rowcount

        # 3. Citing rows from OTHER entities: strip lineage, never delete.
        result["citing_memories_stripped"] = _strip_arrays(
            cursor, "memories", "interaction_ids", fp["citing_memory_ids"], fp["interaction_ids"],
        )
        result["citing_intelligence_stripped"] = _strip_arrays(
            cursor, "intelligence", "source_memory_ids",
            fp["citing_intelligence_ids"], fp["memory_ids"],
        )

        # 4. Owned rows: children before parents.
        if fp["intelligence_ids"]:
            cursor.execute("DELETE FROM intelligence WHERE id = ANY(%s)", (fp["intelligence_ids"],))
            result["intelligence_deleted"] = cursor.rowcount
        if fp["memory_ids"]:
            cursor.execute("DELETE FROM memories WHERE id = ANY(%s)", (fp["memory_ids"],))
            result["memories_deleted"] = cursor.rowcount
        if fp["interaction_ids"]:
            cursor.execute("DELETE FROM interactions WHERE id = ANY(%s)", (fp["interaction_ids"],))
            result["interactions_deleted"] = cursor.rowcount

        # 5. Profile row + every agent's grants on the entity.
        cursor.execute(
            "DELETE FROM entity_profiles WHERE entity_type=%s AND entity_id=%s",
            (entity_type, entity_id),
        )
        result["entity_profile_deleted"] = cursor.rowcount
        cursor.execute(
            "DELETE FROM memory_agent_entities WHERE entity_type=%s AND entity_id=%s",
            (entity_type, entity_id),
        )
        result["agent_grants_deleted"] = cursor.rowcount

    # 6. Redis: cached interactions for the erased ids (best-effort, logged).
    for iid in fp["interaction_ids"]:
        flush_interaction_cache(iid)

    result["dry_run"] = False
    _audit(actor, "entity_erase", entity_type, entity_id, result)
    logger.warning(
        "Entity erased: %s/%s by %s (interactions=%s memories=%s intelligence=%s knowledge_deleted=%s)",
        entity_type, entity_id, actor, fp["counts"]["interactions"],
        fp["counts"]["memories"], fp["counts"]["intelligence"],
        result.get("knowledge_deleted", 0),
    )
    return result


def _audit(actor: str, action: str, entity_type: str, entity_id: str, result: dict) -> None:
    from memory.auth import log_audit
    log_audit(actor, action, entity_type, entity_id, {"footprint": result.get("footprint"), **{
        k: v for k, v in result.items() if k not in {"samples", "footprint"}
    }})
