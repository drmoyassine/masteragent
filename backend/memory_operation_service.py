"""Shared preview, submission, reconciliation, and apply service for Knowledge operations.

The provider is only a transport. Result application is local, version guarded,
and idempotent. Existing synchronous endpoints remain available unchanged.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from core.storage import get_memory_db_context
from services.config_helpers import get_llm_config, get_llm_config_by_id, get_memory_settings, get_system_prompt_by_config_id, get_pipeline_configs
from services.provider_batch import TERMINAL_PROVIDER_STATES, parse_jsonl, provider_adapter

logger = logging.getLogger(__name__)

OPERATION_KEYS = {
    "knowledge_embedding_backfill", "run_all_knowledge_generation",
    "knowledge_hygiene_run", "backfill_facets",
}
LOCAL_TERMINAL = {"completed", "partially_completed", "failed", "expired", "cancelled"}
ACTIVE_LOCAL = {"preparing", "uploading", "submitted", "provider_validating",
                "provider_in_progress", "provider_finalizing", "importing", "applying", "cancelling"}


def _json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _provider_config(operation: str) -> Dict[str, Any]:
    if operation == "run_all_knowledge_generation":
        node = next((n for n in get_pipeline_configs("knowledge") if n.get("task_type") == "knowledge_generation"), None)
        if node:
            return get_llm_config_by_id(node["id"]) or {}
    task = {
        "knowledge_embedding_backfill": "embedding",
        "run_all_knowledge_generation": "knowledge_generation",
        "knowledge_hygiene_run": "knowledge_consolidation",
        "backfill_facets": "knowledge_generation",
    }[operation]
    return get_llm_config(task) or {}


def capabilities() -> Dict[str, Any]:
    globally_enabled = str(os.getenv("PROVIDER_BATCH_ENABLED", "true")).lower() in {"1", "true", "yes", "on"}
    result = {}
    for operation in sorted(OPERATION_KEYS):
        try:
            config = _provider_config(operation)
            cap = provider_adapter(config).capabilities()
            thinking_enabled = bool((config.get("extra_config") or {}).get("thinking_enabled"))
            supported = cap.supported and globally_enabled and not thinking_enabled
            reason = (
                "This operation uses iterative thinking/tool calls, which cannot be flattened into one provider Batch request without changing behavior."
                if thinking_enabled else cap.reason if globally_enabled else
                "Asynchronous provider batches are disabled by PROVIDER_BATCH_ENABLED."
            )
        except Exception as exc:
            cap, supported, reason = None, False, str(exc)
        result[operation] = {
            "provider_batch": supported,
            "local_async": operation == "knowledge_hygiene_run",
            "reason": reason,
            "provider": cap.provider if cap else (_provider_config(operation).get("provider") or "unknown"),
            "completion_window": "24h" if supported else None,
        }
    return result


def _bounded_total(options: Dict[str, Any]) -> int:
    records = max(1, int(options.get("records_per_batch") or 25))
    if options.get("run_all"):
        return min(1_000_000, int(options.get("max_records") or 1_000_000))
    batches = max(1, int(options.get("batches_per_run") or 1))
    return min(1_000_000, records * batches, int(options.get("max_records") or 1_000_000))


def _embedding_sources(limit: int) -> List[Dict[str, Any]]:
    from memory_embedding import current_embedding_model, serialize_knowledge_for_embedding
    model = current_embedding_model()
    specs = [
        ("interactions", "content", "timestamp", "created_at"),
        ("memories", "content_summary", "created_at", "created_at"),
        ("intelligence", "COALESCE(name,'') || '. ' || COALESCE(summary,'') || ' ' || COALESCE(content,'')", "created_at", "updated_at"),
    ]
    output: List[Dict[str, Any]] = []
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        for table, expr, order, version_time in specs:
            if len(output) >= limit:
                break
            cur.execute(f"""
                SELECT id, {expr} AS text, {version_time} AS updated_at FROM {table}
                WHERE ({expr}) IS NOT NULL AND BTRIM(({expr})::text) <> ''
                  AND (embedding IS NULL OR embedding_model IS DISTINCT FROM %s
                       OR embedding_dimensions IS DISTINCT FROM vector_dims(embedding))
                ORDER BY {order}, id LIMIT %s
            """, (model, limit - len(output)))
            for row in cur.fetchall():
                output.append({"type": table, "id": str(row["id"]), "text": str(row["text"]),
                               "updated_at": row.get("updated_at")})
        if len(output) < limit:
            cur.execute("""
                SELECT id,name,category,content,summary,signals,tags,metadata,updated_at
                FROM knowledge WHERE status='active' AND (
                    embedding IS NULL OR embedding_model IS DISTINCT FROM %s
                    OR embedding_dimensions IS DISTINCT FROM vector_dims(embedding))
                ORDER BY created_at,id LIMIT %s
            """, (model, limit - len(output)))
            for row in cur.fetchall():
                item = dict(row)
                output.append({"type": "knowledge", "id": str(item["id"]),
                               "text": serialize_knowledge_for_embedding(item),
                               "updated_at": item.get("updated_at")})
    return output


def _facet_sources(limit: int) -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id,name,summary,content,version,updated_at FROM knowledge
            WHERE status='active' AND COALESCE(metadata->'facets','{}'::jsonb)='{}'::jsonb
            ORDER BY created_at,id LIMIT %s
        """, (limit,))
        return [dict(row) for row in cur.fetchall()]


def _generation_sources(limit: int) -> List[Dict[str, Any]]:
    """Freeze declarative evidence groups; other producers remain independently visible.

    A request represents one threshold-sized group and reuses the configured
    Knowledge-generation prompt. Telemetry/playbook/skill producers are exposed
    as pathways in the preview and continue through the existing local producer
    until their dependent multi-stage requests can be resolved.
    """
    from memory_helpers import _get_entity_type_config
    from memory_generation_policy import resolve_generation_policy
    settings = get_memory_settings() or {}
    groups = []
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT primary_entity_type, COUNT(*) AS count FROM intelligence i
            WHERE status='confirmed' AND NOT EXISTS (
                SELECT 1 FROM knowledge k WHERE i.id=ANY(k.source_intelligence_ids))
            GROUP BY primary_entity_type ORDER BY primary_entity_type
        """)
        for count_row in cur.fetchall():
            entity_type = count_row["primary_entity_type"]
            config = _get_entity_type_config(entity_type)
            policy = resolve_generation_policy("declarative_knowledge", settings=settings, entity_config=config)["values"]
            threshold = int(policy["evidence_threshold"])
            remaining = int(count_row["count"] or 0)
            while remaining >= threshold and len(groups) < limit:
                offset = sum(len(g["records"]) for g in groups if g["entity_type"] == entity_type)
                cur.execute("""
                    SELECT id,name,content,summary,signals,primary_entity_type,primary_entity_id,
                           version,updated_at FROM intelligence i
                    WHERE status='confirmed' AND primary_entity_type=%s AND NOT EXISTS (
                        SELECT 1 FROM knowledge k WHERE i.id=ANY(k.source_intelligence_ids))
                    ORDER BY created_at,id OFFSET %s LIMIT %s
                """, (entity_type, offset, threshold))
                rows = [dict(r) for r in cur.fetchall()]
                if len(rows) < threshold:
                    break
                groups.append({"pathway": "declarative_knowledge", "entity_type": entity_type,
                               "records": rows, "policy": policy})
                remaining -= threshold
    return groups


def _hygiene_sources(limit: int) -> List[Dict[str, Any]]:
    from memory_clustering import discover_candidate_groups
    from memory_consolidation_repository import load_active_records_for_categories
    from memory_embedding import CONSOLIDATABLE_KNOWLEDGE_CATEGORIES
    settings = get_memory_settings() or {}
    records = load_active_records_for_categories(list(CONSOLIDATABLE_KNOWLEDGE_CATEGORIES), limit=max(limit * 5, limit))
    groups = discover_candidate_groups(
        records,
        threshold=float(settings.get("knowledge_hygiene_similarity_threshold", .82)),
        min_size=int(settings.get("knowledge_hygiene_min_cluster_size", 2)),
        max_size=int(settings.get("knowledge_hygiene_max_cluster_size", 5)),
        min_cohesion=float(settings.get("knowledge_hygiene_min_cluster_cohesion", .72)),
        weak_link_threshold=float(settings.get("knowledge_hygiene_weak_link_threshold", .65)),
    )
    by_id = {str(r["id"]): r for r in records}
    return [{"group": g, "records": [by_id[str(i)] for i in g.get("member_ids", []) if str(i) in by_id]}
            for g in groups if g.get("status") in {"accepted", "manual_review"}][:limit]


def _chat_body(config: Dict[str, Any], system: str, user: str, max_tokens: int) -> Dict[str, Any]:
    return {"model": config.get("model_name"), "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": .3, "max_completion_tokens": max_tokens}


def _build_manifest(operation: str, sources: List[Dict[str, Any]], options: Dict[str, Any]) -> List[Dict[str, Any]]:
    config = _provider_config(operation)
    requests: List[Dict[str, Any]] = []
    if operation == "knowledge_embedding_backfill":
        size = max(1, min(25, int(options.get("records_per_batch") or 25)))
        for start in range(0, len(sources), size):
            chunk = sources[start:start + size]
            context = {"sources": [{k: v for k, v in row.items() if k != "text"} for row in chunk]}
            body = {"model": config.get("model_name"), "input": [row["text"][:12000] for row in chunk]}
            requests.append({"pathway": "shared_embedding", "url": "/v1/embeddings", "body": body, "context": context})
    elif operation == "backfill_facets":
        from memory_facets import get_facets_schema
        schema = get_facets_schema()
        system = ("Extract only explicitly supported governed facets. Never infer. Valid schema: " +
                  _json(schema) + '\nReturn only a JSON object of facet key/value pairs.')
        for row in sources:
            body = _chat_body(config, system,
                              f"Name: {row['name']}\nSummary: {row.get('summary') or ''}\nContent:\n{(row.get('content') or '')[:6000]}", 400)
            requests.append({"pathway": "facet_extraction", "url": "/v1/chat/completions", "body": body,
                             "context": {"source": {k: v for k, v in row.items() if k != "content"}, "facet_schema_hash": _hash(schema)}})
    elif operation == "run_all_knowledge_generation":
        from memory_facets import facet_prompt_instructions
        pipeline = get_pipeline_configs("knowledge")
        node = next((n for n in pipeline if n.get("task_type") == "knowledge_generation"), None)
        system = (get_system_prompt_by_config_id(node["id"]) if node else None) or (
            "Synthesize reusable Knowledge. Return only a JSON object with decision, name, category, "
            "summary, content, signals, tags, facets, confidence, qualifications, contradictions, source_support.")
        system += "\n" + facet_prompt_instructions()
        for group in sources:
            from memory_helpers import _get_entity_type_config, _format_signal_definitions
            from services.prompt_renderer import inject_variables
            entity_config = _get_entity_type_config(group["entity_type"])
            group_system = inject_variables(system, {
                "knowledge_signals": _format_signal_definitions(entity_config.get("knowledge_signals_prompt") or [])
            })
            user = "\n\n---\n\n".join(f"[{','.join(r.get('signals') or [])}] {r.get('name','')}\n{r.get('content','')}" for r in group["records"])
            body = _chat_body(config, group_system, user[:8000], int((group.get("policy") or {}).get("max_tokens") or 1200))
            requests.append({"pathway": group["pathway"], "url": "/v1/chat/completions", "body": body,
                             "context": {"entity_type": group["entity_type"], "records": [
                                 {k: v for k, v in r.items() if k != "content"} for r in group["records"]],
                                         "policy": group.get("policy") or {}}})
    elif operation == "knowledge_hygiene_run":
        from memory_consolidation_prompts import build_system_prompt, build_user_prompt, CONSOLIDATION_PROMPT_VERSION
        for item in sources:
            group, records = item["group"], item["records"]
            category = group["category"]
            body = _chat_body(config, build_system_prompt(category),
                              build_user_prompt(records, group.get("metrics") or {}, category),
                              int((get_memory_settings() or {}).get("knowledge_max_tokens") or 1600))
            requests.append({"pathway": category, "url": "/v1/chat/completions", "body": body,
                             "context": {"group": group, "records": [{k: v for k, v in r.items() if k != "embedding"} for r in records],
                                         "prompt_version": CONSOLIDATION_PROMPT_VERSION,
                                         "mode": options.get("mode") or (get_memory_settings() or {}).get("knowledge_hygiene_mode", "manual_only")}})
    for ordinal, request in enumerate(requests):
        source_hash = _hash(request["context"])
        request_hash = _hash(request["body"])
        request["ordinal"] = ordinal
        request["source_hash"] = source_hash
        request["request_hash"] = request_hash
        request["custom_id"] = f"ma-{operation[:12]}-{source_hash[:12]}-{request_hash[:12]}-{ordinal}"
    return requests


def _request_sources(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    context = item.get("context") or {}
    candidates = context.get("sources") or context.get("records") or []
    if context.get("source"):
        candidates = [context["source"]]
    output = []
    for source in candidates:
        output.append({
            "source_type": source.get("type") or ("knowledge" if item.get("pathway") in {"facet_extraction", "best_practices", "lessons_learned", "trade_knowledge", "skill", "playbook"} else "intelligence"),
            "source_id": str(source.get("id")),
            "source_version": source.get("version"),
            "source_updated_at": source.get("updated_at"),
        })
    return [source for source in output if source["source_id"] not in {"None", ""}]


def preview(operation: str, execution_mode: str, options: Optional[Dict[str, Any]] = None,
            actor_id: Optional[str] = None) -> Dict[str, Any]:
    if operation not in OPERATION_KEYS:
        raise ValueError(f"Unsupported Knowledge operation: {operation}")
    options = dict(options or {})
    if operation == "knowledge_hygiene_run" and execution_mode == "provider_batch" and options.get("mode") == "analysis_only":
        raise ValueError("Hygiene analysis_only has no LLM requests. Choose Asynchronous local analysis, or change hygiene mode to proposal_only/manual_only.")
    requested_total = _bounded_total(options)
    try:
        snapshot_cap = max(100, min(50_000, int(os.getenv("PROVIDER_BATCH_SNAPSHOT_MAX_RECORDS", "10000"))))
    except (TypeError, ValueError):
        snapshot_cap = 10_000
    total = min(requested_total, snapshot_cap) if execution_mode == "provider_batch" else requested_total
    if operation == "knowledge_embedding_backfill":
        sources = _embedding_sources(total)
    elif operation == "backfill_facets":
        sources = _facet_sources(total)
    elif operation == "run_all_knowledge_generation":
        sources = _generation_sources(total)
    else:
        sources = _hygiene_sources(total)
    manifest = _build_manifest(operation, sources, options) if execution_mode == "provider_batch" else []
    file_limit = 190 * 1024 * 1024
    if execution_mode == "provider_batch" and manifest:
        bounded_manifest, used_bytes = [], 0
        for item in manifest:
            line_bytes = len(_json({"custom_id": item["custom_id"], "method": "POST", "url": item["url"], "body": item["body"]}).encode("utf-8")) + 1
            if bounded_manifest and used_bytes + line_bytes > file_limit:
                break
            bounded_manifest.append(item); used_bytes += line_bytes
        manifest = bounded_manifest
    config = _provider_config(operation)
    warnings = []
    if requested_total > total:
        warnings.append(
            f"This submission is safely capped at {total:,} source records; "
            f"{requested_total - total:,} remain eligible for later submissions. "
            "The cap prevents large previews from exhausting application memory."
        )
    included_source_count = sum(len(_request_sources(item)) for item in manifest) if manifest else len(sources)
    if execution_mode == "provider_batch" and included_source_count < len(sources):
        warnings.append(
            f"Provider file-size safety retained {included_source_count:,} records in this submission; "
            f"{len(sources) - included_source_count:,} additional snapshot records remain eligible."
        )
    if operation == "run_all_knowledge_generation":
        warnings.append("The first provider-batch generation stage contains currently eligible declarative evidence groups; dependent telemetry/playbook/skill stages continue as separate registered pathways.")
    cap = capabilities()[operation]
    if execution_mode == "provider_batch" and not cap["provider_batch"]:
        warnings.append(cap["reason"] or "Provider batch is unavailable.")
    estimated_tokens = sum(len(_json(r.get("body"))) for r in manifest) // 4
    extra = config.get("extra_config") or {}
    batch_input_price = extra.get("batch_input_cost_per_million")
    try:
        estimated_cost = (estimated_tokens * float(batch_input_price) / 1_000_000) if batch_input_price is not None else None
    except (TypeError, ValueError):
        estimated_cost = None
    estimates = {
        "requested_records": requested_total, "eligible_records": included_source_count,
        "deferred_records": max(0, requested_total - included_source_count), "snapshot_cap": snapshot_cap,
        "provider_job_count": 1 if manifest else 0,
        "input_characters": sum(len(_json(r.get("body"))) for r in manifest),
        "estimated_input_tokens": estimated_tokens,
        "estimated_cost_usd": estimated_cost,
        "completion_window": "24h" if execution_mode == "provider_batch" else None,
    }
    snapshot = [{"source_hash": r.get("source_hash"), "pathway": r.get("pathway")} for r in manifest]
    checksum = _hash({"operation": operation, "options": options, "manifest": manifest})
    preview_id = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    with get_memory_db_context() as conn:
        conn.cursor().execute("""
            INSERT INTO memory_operation_previews
              (id,operation_key,execution_mode,actor_id,options,settings_snapshot,source_snapshot,
               request_manifest,estimates,warnings,manifest_checksum,expires_at)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s)
        """, (preview_id, operation, execution_mode, actor_id, _json(options),
              _json({"provider": config.get("provider"), "model": config.get("model_name")}),
              _json(snapshot), _json(manifest), _json(estimates), _json(warnings), checksum, expires))
    return {"id": preview_id, "operation_key": operation, "execution_mode": execution_mode,
            "options": options, "estimates": estimates, "warnings": warnings,
            "manifest_checksum": checksum, "expires_at": expires.isoformat(), "capability": cap}


def _load_preview(preview_id: str) -> Dict[str, Any]:
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("SELECT * FROM memory_operation_previews WHERE id=%s", (preview_id,)); row = cur.fetchone()
    if not row:
        raise KeyError("Operation preview not found")
    row = dict(row)
    if row["expires_at"] <= datetime.now(timezone.utc):
        raise RuntimeError("Operation preview expired; review the workload again")
    if row["state"] != "previewed":
        raise RuntimeError(f"Operation preview is {row['state']}")
    return row


async def submit(preview_id: str) -> Dict[str, Any]:
    preview_row = _load_preview(preview_id)
    if preview_row["execution_mode"] != "provider_batch":
        raise ValueError("This preview is not an asynchronous provider batch")
    manifest = preview_row.get("request_manifest") or []
    if not manifest:
        raise ValueError("No eligible provider requests were found")
    operation = preview_row["operation_key"]
    advertised = capabilities()[operation]
    if not advertised["provider_batch"]:
        raise ValueError(advertised.get("reason") or "Asynchronous provider batch is unavailable")
    config = _provider_config(operation)
    adapter = provider_adapter(config)
    cap = adapter.capabilities()
    if not cap.supported:
        raise ValueError(cap.reason or "Provider batch is unavailable")
    if len(manifest) > cap.max_requests:
        raise ValueError(f"This preview has {len(manifest)} requests; provider limit is {cap.max_requests}")
    source_hashes = [item["source_hash"] for item in manifest]
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT r.id FROM memory_provider_batch_requests q
            JOIN memory_provider_batch_runs r ON r.id=q.batch_run_id
            WHERE r.operation_key=%s AND r.local_status=ANY(%s)
              AND q.source_hash=ANY(%s) LIMIT 1
        """, (operation, list(ACTIVE_LOCAL), source_hashes))
        conflict = cur.fetchone()
    if conflict:
        raise ValueError(f"Another active run already owns part of this source snapshot ({conflict['id']})")
    run_id = str(uuid.uuid4())
    from memory_db_writes import log_pipeline_run
    pipeline_id = log_pipeline_run(operation, "started", trigger="provider_batch",
                                   detail={"execution_mode": "provider_batch", "preview_id": preview_id})
    endpoint = manifest[0]["url"]
    if any(item["url"] != endpoint for item in manifest):
        raise ValueError("A provider batch can contain only one endpoint")
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO memory_provider_batch_runs
              (id,pipeline_run_id,preview_id,operation_key,pathway,provider,endpoint,model,
               local_status,request_count,estimated_usage,manifest_checksum)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'uploading',%s,%s::jsonb,%s)
        """, (run_id, pipeline_id, preview_id, operation, "mixed" if len({m['pathway'] for m in manifest}) > 1 else manifest[0]["pathway"],
              cap.provider, endpoint, config.get("model_name"), len(manifest),
              _json(preview_row.get("estimates") or {}), preview_row["manifest_checksum"]))
        for item in manifest:
            cur.execute("""
                INSERT INTO memory_provider_batch_requests
                  (batch_run_id,custom_id,operation_key,pathway,ordinal,request_hash,source_hash,request_body,apply_context,attempt)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                RETURNING id
            """, (run_id, item["custom_id"], operation, item["pathway"], item["ordinal"],
                  item["request_hash"], item["source_hash"], _json(item["body"]), _json(item["context"]),
                  int(item.get("attempt") or 1)))
            request_id = cur.fetchone()["id"]
            for source in _request_sources(item):
                cur.execute("""INSERT INTO memory_provider_batch_request_sources
                    (request_id,source_type,source_id,source_version,source_updated_at)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (request_id, source["source_type"], source["source_id"],
                     str(source["source_version"]) if source["source_version"] is not None else None,
                     source["source_updated_at"]))
    try:
        file_id = await adapter.upload(manifest, f"masteragent-{run_id}.jsonl")
        with get_memory_db_context() as conn:
            conn.cursor().execute("UPDATE memory_provider_batch_runs SET provider_input_file_id=%s,local_status='submitted',updated_at=NOW() WHERE id=%s", (file_id, run_id))
        provider = await adapter.submit(file_id, endpoint, metadata={
            "masteragent_run_id": run_id, "operation": operation,
            "manifest": preview_row["manifest_checksum"][:32],
        })
        with get_memory_db_context() as conn:
            cur = conn.cursor()
            cur.execute("""UPDATE memory_provider_batch_runs SET provider_batch_id=%s,provider_status=%s,
                local_status=%s,submitted_at=NOW(),next_poll_at=NOW()+INTERVAL '30 seconds',updated_at=NOW() WHERE id=%s""",
                (provider["id"], provider.get("status"), _local_from_provider(provider.get("status")), run_id))
            cur.execute("UPDATE memory_operation_previews SET state='submitted',submitted_at=NOW() WHERE id=%s", (preview_id,))
    except Exception as exc:
        with get_memory_db_context() as conn:
            conn.cursor().execute("UPDATE memory_provider_batch_runs SET local_status='failed',provider_error=%s::jsonb,finished_at=NOW(),updated_at=NOW() WHERE id=%s", (_json({"message": str(exc)}), run_id))
        if pipeline_id:
            from memory_db_writes import update_pipeline_run
            update_pipeline_run(pipeline_id, status="failed", outcome="failed", reason_code="provider_batch_submit_failed",
                                detail={"provider_batch_run_id": run_id, "message": str(exc)})
        raise
    return get_run(run_id)


def _local_from_provider(status: Optional[str]) -> str:
    return {
        "validating": "provider_validating", "in_progress": "provider_in_progress",
        "finalizing": "provider_finalizing", "completed": "importing",
        "failed": "failed", "expired": "expired", "cancelling": "cancelling", "cancelled": "cancelled",
    }.get(status or "", "submitted")


def _extract_result(line: Dict[str, Any]) -> tuple[Optional[Any], Dict[str, Any], Optional[Dict[str, Any]]]:
    response = line.get("response") or {}
    error = line.get("error")
    body = response.get("body") or {}
    usage = body.get("usage") or {}
    if error or int(response.get("status_code") or 200) >= 400:
        return None, usage, error or body.get("error") or {"message": "Provider request failed"}
    if "data" in body:
        return body["data"], usage, None
    choices = body.get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices else None
    return content, usage, None


async def _apply_request(row: Dict[str, Any], result: Any) -> Dict[str, Any]:
    operation = row["operation_key"]
    context = row.get("apply_context") or {}
    if operation == "knowledge_embedding_backfill":
        vectors = sorted(result or [], key=lambda value: int(value.get("index", 0)))
        sources = context.get("sources") or []
        if len(vectors) != len(sources):
            raise ValueError(f"Expected {len(sources)} vectors, received {len(vectors)}")
        model = _provider_config(operation).get("model_name")
        applied = 0
        with get_memory_db_context() as conn:
            cur = conn.cursor()
            for src, vector_item in zip(sources, vectors):
                vector = vector_item.get("embedding") if isinstance(vector_item, dict) else None
                if not vector:
                    continue
                table = src["type"]
                if table == "knowledge":
                    cur.execute("""UPDATE knowledge SET embedding=%s::vector,embedding_model=%s,
                        embedding_version=2,embedding_dimensions=%s,embedded_at=NOW(),updated_at=NOW()
                        WHERE id=%s AND status='active' AND (embedding IS NULL OR embedding_model IS DISTINCT FROM %s
                        OR embedding_dimensions IS DISTINCT FROM vector_dims(embedding))
                        AND updated_at IS NOT DISTINCT FROM %s""",
                        (vector, model, len(vector), src["id"], model, src.get("updated_at")))
                else:
                    timestamp_column = "updated_at" if table == "intelligence" else "created_at"
                    cur.execute(f"""UPDATE {table} SET embedding=%s::vector,embedding_model=%s,
                        embedding_version=1,embedding_dimensions=%s,embedded_at=NOW()
                        WHERE id=%s AND (embedding IS NULL OR embedding_model IS DISTINCT FROM %s
                        OR embedding_dimensions IS DISTINCT FROM vector_dims(embedding))
                        AND {timestamp_column} IS NOT DISTINCT FROM %s""",
                        (vector, model, len(vector), src["id"], model, src.get("updated_at")))
                applied += cur.rowcount
        return {"updated": applied}
    from services.llm import parse_llm_json
    parsed = parse_llm_json(result, context=f"provider_batch:{operation}") if isinstance(result, str) else result
    if operation == "backfill_facets":
        from memory_facets import get_facets_schema, validate_generated_facets
        if context.get("facet_schema_hash") != _hash(get_facets_schema()):
            raise ValueError("Facet schema changed after submission; request must be regenerated")
        facets, state = validate_generated_facets(parsed)
        src = context["source"]
        if not facets:
            return {"updated": 0, "reason": "no_supported_facets"}
        with get_memory_db_context() as conn:
            cur = conn.cursor(); cur.execute("""UPDATE knowledge SET metadata=COALESCE(metadata,'{}'::jsonb)||
                jsonb_build_object('facets',%s::jsonb,'facet_extraction',%s::jsonb),updated_at=NOW()
                WHERE id=%s AND status='active' AND version IS NOT DISTINCT FROM %s
                  AND COALESCE(metadata->'facets','{}'::jsonb)='{}'::jsonb""",
                (_json(facets), _json(state), src["id"], src.get("version")))
            return {"updated": cur.rowcount, "knowledge_id": src["id"]}
    if operation == "run_all_knowledge_generation":
        from memory_generation_contracts import validate_declarative
        from memory_db_writes import insert_knowledge
        from memory_generation_policy import approval_status, resolve_generation_policy
        candidate = validate_declarative(parsed)
        if candidate.decision == "no_candidate":
            return {"created": 0, "reason": "no_candidate"}
        data = candidate.model_dump()
        policy = context.get("policy") or resolve_generation_policy("declarative_knowledge", settings=get_memory_settings() or {})["values"]
        if float(data.get("confidence") or 0) < float(policy["min_confidence"]):
            return {"created": 0, "reason": "below_confidence"}
        records = context.get("records") or []
        ids = [str(r["id"]) for r in records]
        with get_memory_db_context() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT id,status,version,updated_at,name,summary,content,primary_entity_id,
                embedding,embedding_model,embedding_version,embedding_dimensions,embedded_at
                FROM intelligence WHERE id=ANY(%s)""", (ids,))
            current = {str(item["id"]): item for item in cur.fetchall()}
            if len(current) != len(records) or any(
                current[str(source["id"])].get("status") != "confirmed"
                or str(current[str(source["id"])].get("version")) != str(source.get("version"))
                or str(current[str(source["id"])].get("updated_at")) != str(source.get("updated_at"))
                for source in records
            ):
                return {"created": 0, "reason": "stale_source"}
            cur.execute("SELECT 1 FROM knowledge WHERE source_intelligence_ids @> %s::text[] LIMIT 1", (ids,))
            if cur.fetchone():
                return {"created": 0, "reason": "already_applied"}
        settings = get_memory_settings() or {}
        if settings.get("knowledge_evidence_routing_enabled", True):
            from memory_evidence_service import analyze_evidence, apply_high_similarity_link
            evidence_sources = [{"source_type": "intelligence", "source_id": str(item["id"]),
                "entity_id": item.get("primary_entity_id"), "name": item.get("name") or "",
                "summary": item.get("summary") or "", "content": item.get("content") or "",
                "embedding": item.get("embedding"), "embedding_model": item.get("embedding_model"),
                "embedding_version": item.get("embedding_version"), "embedding_dimensions": item.get("embedding_dimensions"),
                "embedded_at": item.get("embedded_at")} for item in current.values()]
            route = analyze_evidence(pathway="declarative_knowledge", sources=evidence_sources,
                                     settings=settings, entity_type=context.get("entity_type"))
            linked = apply_high_similarity_link(route, evidence_sources, settings)
            if linked:
                return {"created": 0, "reason": "evidence_linked", "canonical_id": linked}
            if route.get("route") == "revision_assessment" and settings.get("knowledge_evidence_routing_mode") == "enforced":
                from memory_evidence_revision_service import assess_and_apply
                revision = await assess_and_apply(route=route, sources=evidence_sources, settings=settings)
                if revision.get("action") in {"no_change", "revised", "manual_review"}:
                    return {"created": 0, "reason": f"revision_{revision.get('action')}",
                            "canonical_id": route.get("canonical_knowledge_id")}
        from memory_facets import validate_generated_facets
        facets, facet_state = validate_generated_facets(data.get("facets") or {})
        metadata = data.get("metadata") or {}; metadata["facets"] = facets; metadata["facet_extraction"] = facet_state
        from memory_helpers import _get_entity_type_config
        defined = _get_entity_type_config(context.get("entity_type") or "").get("knowledge_signals_prompt") or []
        valid_signals = {(item.get("name") or "").strip().lower() for item in defined if (item.get("name") or "").strip()}
        signals = [str(value).strip().lower() for value in (data.get("signals") or [])
                   if str(value).strip() and (not valid_signals or str(value).strip().lower() in valid_signals)]
        from memory_embedding import embed_knowledge_fields
        embedding, _ = await embed_knowledge_fields(
            name=data["name"], category=data.get("category") or "trade_knowledge",
            content=data["content"], summary=data.get("summary") or "",
            signals=signals, tags=data.get("tags") or [], metadata=metadata,
        )
        if not embedding:
            raise ValueError("Generated Knowledge embedding was empty; source remains retryable")
        knowledge_id = str(uuid.uuid4())
        insert_knowledge(knowledge_id=knowledge_id, intelligence_ids=ids, signals=list(dict.fromkeys(signals)),
                         category=data.get("category") or "trade_knowledge", name=data["name"],
                         content=data["content"], summary=data.get("summary") or "", embedding=embedding,
                         tags=data.get("tags") or [], metadata=metadata,
                         extraction_confidence=float(data.get("confidence") or 0),
                         status=approval_status(policy["approval_policy"]), evidence_breadth=len(ids),
                         source_pathway="provider_batch_declarative")
        return {"created": 1, "knowledge_id": knowledge_id}
    if operation == "knowledge_hygiene_run":
        from memory_consolidation_prompts import validate_proposal, proposal_to_dict
        from memory_consolidation_repository import insert_preview
        proposal, errors = validate_proposal(parsed, row.get("pathway") or "trade_knowledge")
        records = context.get("records") or []
        snapshot = {str(r["id"]): {"version": r.get("version"), "updated_at": r.get("updated_at"),
                                   "status": r.get("status"), "record": r} for r in records}
        preview_id = insert_preview(origin="provider_batch", actor_type="system", actor_id=None,
            category=row.get("pathway") or "trade_knowledge", source_ids=list(snapshot), source_snapshot=snapshot,
            metrics=(context.get("group") or {}).get("metrics") or {}, options={}, settings_snapshot={},
            model_provider=_provider_config(operation).get("provider"), model_name=_provider_config(operation).get("model_name"),
            prompt_version=context.get("prompt_version") or "v1", raw_response=parsed,
            proposal=proposal_to_dict(proposal) if proposal else None, validation_errors=errors,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
        result_view = {"proposal_created": int(not errors), "preview_id": preview_id, "validation_errors": errors}
        mode = context.get("mode")
        proposal_dict = proposal_to_dict(proposal) if proposal else None
        if not errors and mode in {"auto_conservative", "auto_synthesis"}:
            from memory_consolidation_service import _canonical_from_proposal, _policy_allows_apply, apply
            settings = get_memory_settings() or {}
            if _policy_allows_apply(proposal_dict, row.get("pathway") or "trade_knowledge", settings):
                event = await apply(preview_id=preview_id, approved_canonical=_canonical_from_proposal(proposal_dict),
                                    canonical_strategy=settings.get("knowledge_hygiene_default_canonical_strategy", "update_existing"),
                                    canonical_target_id=str(records[0]["id"]), actor_type="system", origin="provider_batch")
                result_view["applied_event"] = (event.get("event") or {}).get("id")
        return result_view
    raise ValueError(f"Unsupported operation result: {operation}")


async def reconcile(run_id: str) -> Dict[str, Any]:
    run = _load_run(run_id)
    if run["local_status"] in LOCAL_TERMINAL:
        return get_run(run_id)
    adapter = provider_adapter(_provider_config(run["operation_key"]))
    provider = await adapter.status(run["provider_batch_id"])
    status = provider.get("status")
    try:
        poll_seconds = max(15, min(3600, int(os.getenv("PROVIDER_BATCH_POLL_SECONDS", "60"))))
    except (TypeError, ValueError):
        poll_seconds = 60
    with get_memory_db_context() as conn:
        conn.cursor().execute("""UPDATE memory_provider_batch_runs SET provider_status=%s,local_status=%s,
            provider_output_file_id=%s,provider_error_file_id=%s,last_polled_at=NOW(),
            next_poll_at=NOW()+(%s * INTERVAL '1 second'),provider_error=%s::jsonb,updated_at=NOW()
            WHERE id=%s""", (status, _local_from_provider(status), provider.get("output_file_id"),
                              provider.get("error_file_id"), poll_seconds,
                              _json(provider.get("errors") or {}), run_id))
    if status not in TERMINAL_PROVIDER_STATES:
        return get_run(run_id)
    if provider.get("output_file_id"):
        await _import_file(run_id, await adapter.file_content(provider["output_file_id"]))
    if provider.get("error_file_id"):
        await _import_file(run_id, await adapter.file_content(provider["error_file_id"]))
    await _apply_pending(run_id)
    _finish(run_id, provider_status=status)
    settings = get_memory_settings() or {}
    delete_files = settings.get("provider_batch_delete_files_after_import")
    if delete_files is None:
        delete_files = str(os.getenv("PROVIDER_BATCH_DELETE_FILES_AFTER_IMPORT", "true")).lower() in {"1", "true", "yes", "on"}
    if delete_files:
        for file_id in (run.get("provider_input_file_id"), provider.get("output_file_id"), provider.get("error_file_id")):
            if file_id:
                try: await adapter.delete_file(file_id)
                except Exception: logger.warning("Could not delete provider batch file %s", file_id)
    return get_run(run_id)


async def _import_file(run_id: str, content: bytes) -> None:
    async for line in parse_jsonl(content):
        custom_id = line.get("custom_id")
        result, usage, error = _extract_result(line)
        with get_memory_db_context() as conn:
            cur = conn.cursor(); cur.execute("""UPDATE memory_provider_batch_requests SET status=%s,
                provider_request_id=%s,response_body=%s::jsonb,usage=%s::jsonb,error=%s::jsonb,updated_at=NOW()
                WHERE batch_run_id=%s AND custom_id=%s AND status NOT IN ('applied','validated')""",
                ("failed" if error else "received", (line.get("response") or {}).get("request_id"),
                 _json(result) if result is not None else None, _json(usage), _json(error or {}), run_id, custom_id))


async def _apply_pending(run_id: str) -> None:
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("SELECT * FROM memory_provider_batch_requests WHERE batch_run_id=%s AND status='received' ORDER BY ordinal", (run_id,)); rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        try:
            refs = await _apply_request(row, row.get("response_body"))
            with get_memory_db_context() as conn:
                conn.cursor().execute("UPDATE memory_provider_batch_requests SET status='applied',output_references=%s::jsonb,validated_at=NOW(),applied_at=NOW(),updated_at=NOW() WHERE id=%s AND status='received'", (_json(refs), row["id"]))
        except Exception as exc:
            with get_memory_db_context() as conn:
                conn.cursor().execute("UPDATE memory_provider_batch_requests SET status='apply_failed',error=%s::jsonb,updated_at=NOW() WHERE id=%s", (_json({"message": str(exc)}), row["id"]))


def _finish(run_id: str, provider_status: str) -> None:
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("""SELECT COUNT(*) count,
            COUNT(*) FILTER(WHERE status='applied') applied,
            COUNT(*) FILTER(WHERE status IN ('failed','apply_failed')) failed
            FROM memory_provider_batch_requests WHERE batch_run_id=%s""", (run_id,)); counts = cur.fetchone()
        cur.execute("SELECT usage FROM memory_provider_batch_requests WHERE batch_run_id=%s", (run_id,))
        usage_rows = [r.get("usage") or {} for r in cur.fetchall()]
        actual_usage = {
            "input_tokens": sum(int(u.get("prompt_tokens") or u.get("input_tokens") or 0) for u in usage_rows),
            "output_tokens": sum(int(u.get("completion_tokens") or u.get("output_tokens") or 0) for u in usage_rows),
            "total_tokens": sum(int(u.get("total_tokens") or 0) for u in usage_rows),
        }
        local = (
            "completed" if counts["applied"] == counts["count"]
            else "partially_completed" if counts["applied"]
            else "cancelled" if provider_status == "cancelled"
            else "expired" if provider_status == "expired"
            else "failed"
        )
        cur.execute("""UPDATE memory_provider_batch_runs SET local_status=%s,completed_count=%s,
            applied_count=%s,failed_count=%s,actual_usage=%s::jsonb,finished_at=NOW(),updated_at=NOW() WHERE id=%s""",
            (local, counts["applied"], counts["applied"], counts["failed"], _json(actual_usage), run_id))
        cur.execute("SELECT pipeline_run_id FROM memory_provider_batch_runs WHERE id=%s", (run_id,))
        pipeline = cur.fetchone()
    if pipeline and pipeline.get("pipeline_run_id"):
        from memory_db_writes import update_pipeline_run
        update_pipeline_run(
            pipeline["pipeline_run_id"], status="completed" if local in {"completed", "partially_completed"} else local,
            outcome=local, records_created=int(counts["applied"] or 0),
            progress_total=int(counts["count"] or 0), progress_completed=int(counts["applied"] or 0),
            progress_failed=int(counts["failed"] or 0),
            detail={"provider_batch_run_id": run_id, "provider_status": provider_status},
        )


def _load_run(run_id: str) -> Dict[str, Any]:
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("SELECT * FROM memory_provider_batch_runs WHERE id=%s", (run_id,)); row = cur.fetchone()
    if not row: raise KeyError("Operation run not found")
    return dict(row)


def get_run(run_id: str) -> Dict[str, Any]:
    run = _load_run(run_id)
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("SELECT status,COUNT(*) count FROM memory_provider_batch_requests WHERE batch_run_id=%s GROUP BY status", (run_id,)); run["request_statuses"] = {r["status"]: r["count"] for r in cur.fetchall()}
    return run


def list_runs(limit: int = 30) -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("SELECT * FROM memory_provider_batch_runs ORDER BY created_at DESC LIMIT %s", (max(1, min(limit, 100)),)); return [dict(r) for r in cur.fetchall()]


def list_requests(run_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("""SELECT id,custom_id,pathway,ordinal,status,attempt,provider_request_id,
            usage,error,output_references,validated_at,applied_at,created_at,updated_at
            FROM memory_provider_batch_requests WHERE batch_run_id=%s ORDER BY ordinal LIMIT %s""", (run_id, max(1, min(limit, 1000)))); return [dict(r) for r in cur.fetchall()]


async def cancel(run_id: str) -> Dict[str, Any]:
    run = _load_run(run_id)
    if run["local_status"] in LOCAL_TERMINAL: return get_run(run_id)
    with get_memory_db_context() as conn:
        conn.cursor().execute("UPDATE memory_provider_batch_runs SET cancel_requested=TRUE,local_status='cancelling',updated_at=NOW() WHERE id=%s", (run_id,))
    if run.get("provider_batch_id"):
        await provider_adapter(_provider_config(run["operation_key"])).cancel(run["provider_batch_id"])
    return get_run(run_id)


async def retry(run_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a fresh source snapshot and provider attempt for unresolved work.

    Discovery is intentionally rerun: stale or already-applied sources disappear
    through normal eligibility rules instead of reusing an expired JSONL file.
    """
    previous = _load_run(run_id)
    if previous["local_status"] not in {"failed", "expired", "cancelled", "partially_completed"}:
        raise ValueError("Only failed, expired, cancelled, or partially completed runs can be retried")
    # A validated provider result that failed only during local application is
    # retried locally and must never be billed a second time.
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""UPDATE memory_provider_batch_requests SET status='received',updated_at=NOW()
            WHERE batch_run_id=%s AND status='apply_failed' AND response_body IS NOT NULL RETURNING id""", (run_id,))
        local_retry_count = len(cur.fetchall())
    if local_retry_count:
        await _apply_pending(run_id)
        _finish(run_id, provider_status=previous.get("provider_status") or "completed")
        previous = _load_run(run_id)
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("SELECT options,settings_snapshot FROM memory_operation_previews WHERE id=%s", (previous["preview_id"],))
        old_preview = cur.fetchone() or {}
        cur.execute("""SELECT * FROM memory_provider_batch_requests
            WHERE batch_run_id=%s AND status NOT IN ('applied','apply_failed') ORDER BY ordinal""", (run_id,))
        unresolved = [dict(row) for row in cur.fetchall()]
    if not unresolved:
        return get_run(run_id)
    attempt = max(int(row.get("attempt") or 1) for row in unresolved) + 1
    manifest = []
    for ordinal, row in enumerate(unresolved):
        manifest.append({
            "custom_id": f"{row['custom_id'].split('-r')[0]}-r{attempt}",
            "url": previous["endpoint"], "body": row["request_body"],
            "context": row.get("apply_context") or {}, "pathway": row.get("pathway"),
            "ordinal": ordinal, "request_hash": row["request_hash"],
            "source_hash": row["source_hash"], "attempt": attempt,
        })
    preview_id = str(uuid.uuid4())
    checksum = _hash({"parent_run": run_id, "attempt": attempt, "manifest": manifest})
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    estimates = {"eligible_records": sum(len(_request_sources(item)) for item in manifest),
                 "request_count": len(manifest), "provider_job_count": 1,
                 "completion_window": "24h", "retry_of": run_id, "attempt": attempt}
    with get_memory_db_context() as conn:
        conn.cursor().execute("""INSERT INTO memory_operation_previews
            (id,operation_key,execution_mode,actor_id,options,settings_snapshot,source_snapshot,
             request_manifest,estimates,warnings,manifest_checksum,expires_at)
            VALUES (%s,%s,'provider_batch',%s,%s::jsonb,%s::jsonb,'[]'::jsonb,%s::jsonb,%s::jsonb,'[]'::jsonb,%s,%s)""",
            (preview_id, previous["operation_key"], actor_id, _json(old_preview.get("options") or {}),
             _json(old_preview.get("settings_snapshot") or {}), _json(manifest), _json(estimates), checksum, expires))
    retried = await submit(preview_id)
    with get_memory_db_context() as conn:
        conn.cursor().execute("UPDATE memory_provider_batch_runs SET parent_run_id=%s WHERE id=%s", (run_id, retried["id"]))
    return get_run(retried["id"])


def pause(run_id: str) -> Dict[str, Any]:
    with get_memory_db_context() as conn:
        conn.cursor().execute("UPDATE memory_provider_batch_runs SET pause_requested=TRUE,updated_at=NOW() WHERE id=%s AND local_status NOT IN ('completed','failed','cancelled','expired')", (run_id,))
    return get_run(run_id)


def resume(run_id: str) -> Dict[str, Any]:
    with get_memory_db_context() as conn:
        conn.cursor().execute("UPDATE memory_provider_batch_runs SET pause_requested=FALSE,next_poll_at=NOW(),updated_at=NOW() WHERE id=%s AND cancel_requested=FALSE", (run_id,))
    return get_run(run_id)


async def recover_nonterminal() -> int:
    """Reconcile submitted work after a deployment; safe to call repeatedly."""
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("SELECT id FROM memory_provider_batch_runs WHERE local_status=ANY(%s) AND provider_batch_id IS NOT NULL AND COALESCE(next_poll_at,NOW())<=NOW() LIMIT 10", (list(ACTIVE_LOCAL),)); ids = [r["id"] for r in cur.fetchall()]
    for run_id in ids:
        try: await reconcile(run_id)
        except Exception as exc: logger.warning("Provider batch recovery failed for %s: %s", run_id, exc)
    return len(ids)
