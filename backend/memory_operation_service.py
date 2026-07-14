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


def _provider_config(operation: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options = options or {}
    task = {
        "knowledge_embedding_backfill": "embedding",
        "run_all_knowledge_generation": "knowledge_generation",
        "knowledge_hygiene_run": "knowledge_consolidation",
        "backfill_facets": "knowledge_generation",
    }[operation]
    selected_id = options.get("provider_config_id")
    if selected_id:
        selected = get_llm_config_by_id(str(selected_id)) or {}
        if not selected or not selected.get("is_active"):
            raise ValueError("The selected provider configuration is unavailable or inactive")
        if selected.get("task_type") != task:
            raise ValueError(f"The selected provider configuration is not registered for {task}")
        config = dict(selected)
        if options.get("model_name"):
            config["model_name"] = str(options["model_name"]).strip()
        return config
    if operation == "run_all_knowledge_generation":
        node = next((n for n in get_pipeline_configs("knowledge") if n.get("task_type") == "knowledge_generation"), None)
        if node:
            config = get_llm_config_by_id(node["id"]) or {}
            if options.get("model_name"):
                config = dict(config); config["model_name"] = str(options["model_name"]).strip()
            return config
    config = get_llm_config(task) or {}
    if options.get("model_name"):
        config = dict(config)
        config["model_name"] = str(options["model_name"]).strip()
    return config


def _pricing(config: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Dict[str, Optional[float]]:
    """Resolve a run-frozen price snapshot without changing the shared model config."""
    extra = config.get("extra_config") or {}
    supplied = (options or {}).get("pricing") or {}
    result: Dict[str, Optional[float]] = {}
    for key in ("batch_input_cost_per_million", "batch_output_cost_per_million", "embedding_cost_per_million"):
        value = supplied.get(key, extra.get(key))
        try:
            result[key] = float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a non-negative number")
        if result[key] is not None and result[key] < 0:
            raise ValueError(f"{key} must be a non-negative number")
    return result


def _configured_batch_targets(operation: str) -> List[Dict[str, Any]]:
    """Return safe selectable accounts/models; credentials never leave the backend."""
    default = _provider_config(operation)
    candidates = []
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id,c.name,c.task_type,c.model_name,c.provider_id,c.extra_config_json,c.is_active,
                   p.provider,p.name AS provider_name,p.api_base_url,p.api_key_encrypted
            FROM memory_llm_configs c
            JOIN memory_llm_providers p ON p.id=c.provider_id
            WHERE c.is_active=TRUE
            ORDER BY p.name,c.name,c.model_name
        """)
        rows = [dict(row) for row in cur.fetchall()]
    seen = set()
    for row in rows:
        if default.get("task_type") and row.get("task_type") != default.get("task_type"):
            continue
        try:
            config = get_llm_config_by_id(str(row["id"])) or {}
            cap = provider_adapter(config).capabilities()
            if not cap.supported or row["id"] in seen:
                continue
        except Exception:
            continue
        seen.add(row["id"])
        candidates.append({
            "config_id": row["id"], "provider_id": row.get("provider_id"),
            "provider": cap.provider, "provider_name": row.get("provider_name") or cap.provider,
            "config_name": row.get("name") or row.get("model_name"), "model_name": row.get("model_name"),
            "is_default": str(row["id"]) == str(default.get("id")),
            "pricing": _pricing(config),
        })
    return candidates


def capabilities() -> Dict[str, Any]:
    globally_enabled = str(os.getenv("PROVIDER_BATCH_ENABLED", "true")).lower() in {"1", "true", "yes", "on"}
    result = {}
    for operation in sorted(OPERATION_KEYS):
        config = {}
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
            "default_config_id": config.get("id"),
            "default_model": config.get("model_name"),
            "targets": _configured_batch_targets(operation),
        }
    return result


def _bounded_total(options: Dict[str, Any]) -> int:
    records = max(1, int(options.get("records_per_batch") or 25))
    configured_max = max(1, int(options.get("max_records") or 1))
    if options.get("run_all"):
        return configured_max
    batches = max(1, int(options.get("batches_per_run") or 1))
    return min(records * batches, configured_max)


def _claimed_clause(parent_run_id: Optional[str], alias: str = "") -> tuple[str, list]:
    if not parent_run_id:
        return "", []
    prefix = f"{alias}." if alias else ""
    return """ AND NOT EXISTS (
        SELECT 1 FROM memory_provider_batch_request_sources s
        JOIN memory_provider_batch_requests q ON q.id=s.request_id
        JOIN memory_provider_batch_runs r ON r.id=q.batch_run_id
        WHERE r.parent_run_id=%s AND s.source_type=%s AND s.source_id=(""" + prefix + "id)::text)", [parent_run_id]


def _embedding_sources(limit: int, parent_run_id: Optional[str] = None,
                       snapshot_cutoff: Optional[str] = None) -> List[Dict[str, Any]]:
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
            claimed, params = _claimed_clause(parent_run_id, table)
            cutoff_clause = " AND created_at<=%s" if snapshot_cutoff else ""
            cur.execute(f"""
                SELECT id, {expr} AS text, {version_time} AS updated_at FROM {table}
                WHERE ({expr}) IS NOT NULL AND BTRIM(({expr})::text) <> ''
                  AND (embedding IS NULL OR embedding_model IS DISTINCT FROM %s
                       OR embedding_dimensions IS DISTINCT FROM vector_dims(embedding))
                  {claimed}
                  {cutoff_clause}
                ORDER BY {order}, id LIMIT %s
            """, tuple([model, *params, *([table] if parent_run_id else []), *([snapshot_cutoff] if snapshot_cutoff else []), limit - len(output)]))
            for row in cur.fetchall():
                output.append({"type": table, "id": str(row["id"]), "text": str(row["text"]),
                               "updated_at": row.get("updated_at")})
        if len(output) < limit:
            claimed, params = _claimed_clause(parent_run_id, "knowledge")
            cutoff_clause = " AND created_at<=%s" if snapshot_cutoff else ""
            cur.execute("""
                SELECT id,name,category,content,summary,signals,tags,metadata,updated_at
                FROM knowledge WHERE status='active' AND (
                    embedding IS NULL OR embedding_model IS DISTINCT FROM %s
                    OR embedding_dimensions IS DISTINCT FROM vector_dims(embedding))
                """ + claimed + cutoff_clause + """
                ORDER BY created_at,id LIMIT %s
            """, tuple([model, *params, *(["knowledge"] if parent_run_id else []), *([snapshot_cutoff] if snapshot_cutoff else []), limit - len(output)]))
            for row in cur.fetchall():
                item = dict(row)
                output.append({"type": "knowledge", "id": str(item["id"]),
                               "text": serialize_knowledge_for_embedding(item),
                               "updated_at": item.get("updated_at")})
    return output


def _facet_sources(limit: int, parent_run_id: Optional[str] = None,
                   snapshot_cutoff: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        claimed, params = _claimed_clause(parent_run_id, "knowledge")
        cutoff_clause = " AND created_at<=%s" if snapshot_cutoff else ""
        cur.execute("""
            SELECT id,name,summary,content,version,updated_at FROM knowledge
            WHERE status='active' AND COALESCE(metadata->'facets','{}'::jsonb)='{}'::jsonb
            """ + claimed + cutoff_clause + """
            ORDER BY created_at,id LIMIT %s
        """, tuple([*params, *(["knowledge"] if parent_run_id else []), *([snapshot_cutoff] if snapshot_cutoff else []), limit]))
        return [dict(row) for row in cur.fetchall()]


def _eligible_source_count(operation: str) -> int:
    """Count source records without materializing their content."""
    from memory_embedding import current_embedding_model
    model = current_embedding_model()
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        if operation == "knowledge_embedding_backfill":
            counts = []
            specs = [
                ("interactions", "content"), ("memories", "content_summary"),
                ("intelligence", "COALESCE(name,'') || '. ' || COALESCE(summary,'') || ' ' || COALESCE(content,'')"),
                ("knowledge", "COALESCE(name,'') || '. ' || COALESCE(summary,'') || ' ' || COALESCE(content,'')"),
            ]
            for table, expr in specs:
                status = " AND status='active'" if table == "knowledge" else ""
                cur.execute(f"""SELECT COUNT(*) count FROM {table} WHERE ({expr}) IS NOT NULL
                    AND BTRIM(({expr})::text)<>'' {status} AND (embedding IS NULL OR
                    embedding_model IS DISTINCT FROM %s OR embedding_dimensions IS DISTINCT FROM vector_dims(embedding))""", (model,))
                counts.append(int(cur.fetchone()["count"] or 0))
            return sum(counts)
        if operation == "backfill_facets":
            cur.execute("""SELECT COUNT(*) count FROM knowledge WHERE status='active'
                AND COALESCE(metadata->'facets','{}'::jsonb)='{}'::jsonb""")
            return int(cur.fetchone()["count"] or 0)
        if operation == "run_all_knowledge_generation":
            cur.execute("""SELECT COUNT(*) count FROM intelligence i WHERE status='confirmed'
                AND NOT EXISTS (SELECT 1 FROM knowledge k WHERE i.id=ANY(k.source_intelligence_ids))""")
            return int(cur.fetchone()["count"] or 0)
        cur.execute("SELECT COUNT(*) count FROM knowledge WHERE status='active'")
        return int(cur.fetchone()["count"] or 0)


def _generation_sources(limit: int, parent_run_id: Optional[str] = None,
                        snapshot_cutoff: Optional[str] = None) -> List[Dict[str, Any]]:
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
        claimed = """ AND NOT EXISTS (
            SELECT 1 FROM memory_provider_batch_request_sources s
            JOIN memory_provider_batch_requests q ON q.id=s.request_id
            JOIN memory_provider_batch_runs r ON r.id=q.batch_run_id
            WHERE r.parent_run_id=%s AND s.source_type='intelligence' AND s.source_id=i.id::text
        )""" if parent_run_id else ""
        cutoff_clause = " AND i.created_at<=%s" if snapshot_cutoff else ""
        cur.execute("""
            SELECT primary_entity_type, COUNT(*) AS count FROM intelligence i
            WHERE status='confirmed' AND NOT EXISTS (
                SELECT 1 FROM knowledge k WHERE i.id=ANY(k.source_intelligence_ids))
            """ + claimed + cutoff_clause + """
            GROUP BY primary_entity_type ORDER BY primary_entity_type
        """, tuple([*([parent_run_id] if parent_run_id else []), *([snapshot_cutoff] if snapshot_cutoff else [])]))
        for count_row in cur.fetchall():
            entity_type = count_row["primary_entity_type"]
            config = _get_entity_type_config(entity_type)
            policy = resolve_generation_policy("declarative_knowledge", settings=settings, entity_config=config)["values"]
            threshold = int(policy["evidence_threshold"])
            remaining = int(count_row["count"] or 0)
            while remaining >= threshold and sum(len(g["records"]) for g in groups) < limit:
                offset = sum(len(g["records"]) for g in groups if g["entity_type"] == entity_type)
                cur.execute("""
                    SELECT id,name,content,summary,signals,primary_entity_type,primary_entity_id,
                           version,updated_at FROM intelligence i
                    WHERE status='confirmed' AND primary_entity_type=%s AND NOT EXISTS (
                        SELECT 1 FROM knowledge k WHERE i.id=ANY(k.source_intelligence_ids))
                    """ + claimed + cutoff_clause + """
                    ORDER BY created_at,id OFFSET %s LIMIT %s
                """, tuple([entity_type, *([parent_run_id] if parent_run_id else []), *([snapshot_cutoff] if snapshot_cutoff else []), offset, threshold]))
                rows = [dict(r) for r in cur.fetchall()]
                if len(rows) < threshold:
                    break
                if groups and sum(len(g["records"]) for g in groups) + len(rows) > limit:
                    break
                groups.append({"pathway": "declarative_knowledge", "entity_type": entity_type,
                               "records": rows, "policy": policy})
                remaining -= threshold
    return groups


def _hygiene_sources(limit: int, parent_run_id: Optional[str] = None,
                     snapshot_cutoff: Optional[str] = None) -> List[Dict[str, Any]]:
    from memory_clustering import discover_candidate_groups
    from memory_consolidation_repository import load_active_records_for_categories
    from memory_embedding import CONSOLIDATABLE_KNOWLEDGE_CATEGORIES
    settings = get_memory_settings() or {}
    discovery_limit = max(limit * 5, limit)
    if parent_run_id:
        discovery_limit = min(1_000_000, discovery_limit + int(limit))
    records = load_active_records_for_categories(list(CONSOLIDATABLE_KNOWLEDGE_CATEGORIES), limit=discovery_limit)
    if snapshot_cutoff:
        cutoff = datetime.fromisoformat(str(snapshot_cutoff).replace("Z", "+00:00"))
        records = [r for r in records if not r.get("created_at") or r["created_at"] <= cutoff]
    if parent_run_id and records:
        with get_memory_db_context() as conn:
            cur = conn.cursor(); cur.execute("""SELECT DISTINCT s.source_id
                FROM memory_provider_batch_request_sources s
                JOIN memory_provider_batch_requests q ON q.id=s.request_id
                JOIN memory_provider_batch_runs r ON r.id=q.batch_run_id
                WHERE r.parent_run_id=%s AND s.source_type='knowledge'""", (parent_run_id,))
            claimed = {row["source_id"] for row in cur.fetchall()}
        records = [r for r in records if str(r["id"]) not in claimed]
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
    config = _provider_config(operation, options)
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


def _filter_claimed_manifest(parent_run_id: str, manifest: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Exclude any request containing a source already claimed by this coordinator."""
    pairs = {(s["source_type"], s["source_id"]) for item in manifest for s in _request_sources(item)}
    if not pairs:
        return manifest
    claimed = set()
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        for source_type, source_ids in _group_pairs(pairs).items():
            cur.execute("""SELECT s.source_type,s.source_id FROM memory_provider_batch_request_sources s
                JOIN memory_provider_batch_requests q ON q.id=s.request_id
                JOIN memory_provider_batch_runs r ON r.id=q.batch_run_id
                WHERE r.parent_run_id=%s AND s.source_type=%s AND s.source_id=ANY(%s)""",
                (parent_run_id, source_type, list(source_ids)))
            claimed.update((r["source_type"], r["source_id"]) for r in cur.fetchall())
    return [item for item in manifest if not any((s["source_type"], s["source_id"]) in claimed for s in _request_sources(item))]


def _group_pairs(pairs: Iterable[tuple[str, str]]) -> Dict[str, set[str]]:
    grouped: Dict[str, set[str]] = {}
    for source_type, source_id in pairs:
        grouped.setdefault(source_type, set()).add(source_id)
    return grouped


def preview(operation: str, execution_mode: str, options: Optional[Dict[str, Any]] = None,
            actor_id: Optional[str] = None) -> Dict[str, Any]:
    if operation not in OPERATION_KEYS:
        raise ValueError(f"Unsupported Knowledge operation: {operation}")
    options = dict(options or {})
    options.setdefault("snapshot_cutoff", datetime.now(timezone.utc).isoformat())
    if operation == "knowledge_hygiene_run" and execution_mode == "provider_batch" and options.get("mode") == "analysis_only":
        raise ValueError("Hygiene analysis_only has no LLM requests. Choose Asynchronous local analysis, or change hygiene mode to proposal_only/manual_only.")
    requested_total = _bounded_total(options)
    eligible_total = _eligible_source_count(operation)
    target_total = min(requested_total, eligible_total)
    # Preview only a representative bounded sample. The accepted workload is
    # prepared later in durable child batches and is never capped by this value.
    sample_limit = min(target_total, max(25, min(1000, int(os.getenv("PROVIDER_BATCH_PREVIEW_SAMPLE_RECORDS", "250")))))
    if operation == "knowledge_embedding_backfill":
        sources = _embedding_sources(sample_limit, snapshot_cutoff=options["snapshot_cutoff"])
    elif operation == "backfill_facets":
        sources = _facet_sources(sample_limit, snapshot_cutoff=options["snapshot_cutoff"])
    elif operation == "run_all_knowledge_generation":
        sources = _generation_sources(sample_limit, snapshot_cutoff=options["snapshot_cutoff"])
    else:
        sources = _hygiene_sources(sample_limit, snapshot_cutoff=options["snapshot_cutoff"])
    manifest = _build_manifest(operation, sources, options) if execution_mode == "provider_batch" else []
    config = _provider_config(operation, options)
    if operation == "knowledge_embedding_backfill":
        shared_model = (_provider_config(operation) or {}).get("model_name")
        if shared_model and config.get("model_name") != shared_model:
            raise ValueError(
                "Embedding backfill must use the shared semantic-index model. Change the shared embedding model first, then run its coordinated backfill."
            )
    pricing = _pricing(config, options)
    options.update({
        "provider_config_id": config.get("id"), "model_name": config.get("model_name"),
        "pricing": pricing, "target_source_count": target_total,
    })
    warnings = []
    sample_source_count = sum(len(_request_sources(item)) for item in manifest) if manifest else len(sources)
    if operation == "run_all_knowledge_generation":
        warnings.append("The first provider-batch generation stage contains currently eligible declarative evidence groups; dependent telemetry/playbook/skill stages continue as separate registered pathways.")
    advertised_capability = capabilities()[operation]
    if execution_mode == "provider_batch" and not advertised_capability["provider_batch"]:
        warnings.append(advertised_capability["reason"] or "Provider batch is unavailable.")
    sample_chars = sum(len(_json(r.get("body"))) for r in manifest)
    ratio = (target_total / sample_source_count) if sample_source_count else 0
    estimated_tokens = int((sample_chars // 4) * ratio)
    if operation == "knowledge_embedding_backfill":
        request_count = (target_total + max(1, int(options.get("records_per_batch") or 25)) - 1) // max(1, int(options.get("records_per_batch") or 25))
    else:
        request_count = max(0, int(round(len(manifest) * ratio)))
    provider_capability = provider_adapter(config).capabilities() if execution_mode == "provider_batch" else None
    requests_per_job = provider_capability.max_requests if provider_capability else 50_000
    if operation == "knowledge_embedding_backfill" and provider_capability:
        requests_per_job = min(requests_per_job, max(1, provider_capability.max_embedding_inputs // max(1, int(options.get("records_per_batch") or 25))))
    provider_job_count = (request_count + requests_per_job - 1) // requests_per_job if request_count else 0
    try:
        preparation_chunk = max(25, min(50_000, int(os.getenv("PROVIDER_BATCH_PREPARATION_CHUNK_RECORDS", "10000"))))
    except (TypeError, ValueError):
        preparation_chunk = 10_000
    if target_total:
        provider_job_count = max(provider_job_count, (target_total + preparation_chunk - 1) // preparation_chunk)
    input_price = pricing.get("embedding_cost_per_million") if operation == "knowledge_embedding_backfill" else pricing.get("batch_input_cost_per_million")
    estimated_output_tokens = 0 if operation == "knowledge_embedding_backfill" else int(request_count * int(options.get("estimated_output_tokens_per_request") or 600))
    estimated_cost = None
    if input_price is not None:
        estimated_cost = estimated_tokens * input_price / 1_000_000
        output_price = pricing.get("batch_output_cost_per_million")
        if estimated_output_tokens and output_price is not None:
            estimated_cost += estimated_output_tokens * output_price / 1_000_000
    estimates = {
        "requested_records": requested_total, "available_records": eligible_total,
        "eligible_records": target_total, "deferred_records": max(0, eligible_total - target_total),
        "sampled_records": sample_source_count, "request_count": request_count,
        "provider_job_count": provider_job_count,
        "input_characters": int(sample_chars * ratio),
        "estimated_input_tokens": estimated_tokens,
        "estimated_output_tokens": estimated_output_tokens,
        "estimated_cost_usd": estimated_cost,
        "completion_window": "24h" if execution_mode == "provider_batch" else None,
        "provider": config.get("provider"), "model": config.get("model_name"), "pricing": pricing,
    }
    snapshot = {"sample_hashes": [r.get("source_hash") for r in manifest], "eligible_at": datetime.now(timezone.utc).isoformat()}
    checksum = _hash({"operation": operation, "options": options, "estimates": estimates, "snapshot": snapshot})
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
              _json(snapshot), _json([]), _json(estimates), _json(warnings), checksum, expires))
    return {"id": preview_id, "operation_key": operation, "execution_mode": execution_mode,
            "options": options, "estimates": estimates, "warnings": warnings,
            "manifest_checksum": checksum, "expires_at": expires.isoformat(), "capability": advertised_capability}


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
    estimates = preview_row.get("estimates") or {}
    if not int(estimates.get("request_count") or 0):
        raise ValueError("No eligible provider requests were found")
    operation = preview_row["operation_key"]
    advertised = capabilities()[operation]
    if not advertised["provider_batch"]:
        raise ValueError(advertised.get("reason") or "Asynchronous provider batch is unavailable")
    options = preview_row.get("options") or {}
    config = _provider_config(operation, options)
    adapter = provider_adapter(config)
    cap = adapter.capabilities()
    if not cap.supported:
        raise ValueError(cap.reason or "Provider batch is unavailable")
    run_id = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT id FROM memory_provider_batch_runs WHERE parent_run_id IS NULL
            AND operation_key=%s AND local_status NOT IN ('completed','partially_completed','failed','expired','cancelled')
            LIMIT 1""", (operation,))
        conflict = cur.fetchone()
    if conflict:
        raise ValueError(f"An asynchronous {operation} operation is already active ({conflict['id']})")
    from memory_db_writes import log_pipeline_run
    pipeline_id = log_pipeline_run(operation, "started", trigger="provider_batch",
                                   detail={"execution_mode": "provider_batch", "preview_id": preview_id})
    endpoint = "/v1/embeddings" if operation == "knowledge_embedding_backfill" else "/v1/chat/completions"
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO memory_provider_batch_runs
              (id,pipeline_run_id,preview_id,operation_key,pathway,provider,endpoint,model,
               local_status,request_count,estimated_usage,manifest_checksum,is_coordinator,
               target_source_count,run_options,pricing_snapshot,next_poll_at)
            VALUES (%s,%s,%s,%s,'all',%s,%s,%s,'preparing',%s,%s::jsonb,%s,TRUE,%s,%s::jsonb,%s::jsonb,NOW())
        """, (run_id, pipeline_id, preview_id, operation, cap.provider, endpoint,
              config.get("model_name"), int(estimates.get("request_count") or 0),
              _json(estimates), preview_row["manifest_checksum"],
              int(options.get("target_source_count") or estimates.get("eligible_records") or 0),
              _json(options), _json(_pricing(config, options))))
        cur.execute("UPDATE memory_operation_previews SET state='submitted',submitted_at=NOW() WHERE id=%s", (preview_id,))
    return get_run(run_id)


def _provider_safe_manifest(manifest: List[Dict[str, Any]], cap: Any,
                            operation: str, records_per_batch: int) -> List[Dict[str, Any]]:
    selected, used_bytes, embedding_inputs = [], 0, 0
    for item in manifest:
        line_bytes = len(_json({"custom_id": item["custom_id"], "method": "POST", "url": item["url"], "body": item["body"]}).encode("utf-8")) + 1
        item_inputs = len(item.get("body", {}).get("input") or []) if operation == "knowledge_embedding_backfill" else 0
        if selected and (len(selected) >= cap.max_requests or used_bytes + line_bytes > int(cap.max_file_bytes * .95)
                         or embedding_inputs + item_inputs > cap.max_embedding_inputs):
            break
        selected.append(item); used_bytes += line_bytes; embedding_inputs += item_inputs
    return selected


def _limit_manifest_sources(manifest: List[Dict[str, Any]], source_limit: int) -> List[Dict[str, Any]]:
    selected, used = [], 0
    for item in manifest:
        count = len(_request_sources(item)) or 1
        if selected and used + count > source_limit:
            break
        selected.append(item); used += count
        if used >= source_limit:
            break
    return selected


async def _submit_child(parent: Dict[str, Any], manifest: List[Dict[str, Any]],
                        count_prepared_sources: bool = True) -> Dict[str, Any]:
    operation, options = parent["operation_key"], parent.get("run_options") or {}
    config = _provider_config(operation, options)
    adapter = provider_adapter(config); cap = adapter.capabilities()
    manifest = _provider_safe_manifest(manifest, cap, operation, int(options.get("records_per_batch") or 25))
    if not manifest:
        raise ValueError("A provider-safe child manifest could not be created")
    run_id = str(uuid.uuid4()); endpoint = manifest[0]["url"]
    source_count = sum(len(_request_sources(item)) for item in manifest)
    checksum = _hash({"parent": parent["id"], "child": parent.get("child_count", 0) + 1, "manifest": manifest})
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO memory_provider_batch_runs
            (id,preview_id,parent_run_id,operation_key,pathway,provider,endpoint,model,local_status,
             request_count,estimated_usage,manifest_checksum,run_options,pricing_snapshot)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'uploading',%s,%s::jsonb,%s,%s::jsonb,%s::jsonb)""",
            (run_id, parent.get("preview_id"), parent["id"], operation,
             "mixed" if len({m["pathway"] for m in manifest}) > 1 else manifest[0]["pathway"],
             cap.provider, endpoint, config.get("model_name"), len(manifest),
             _json({"source_count": source_count}), checksum, _json(options), _json(parent.get("pricing_snapshot") or {})))
        for ordinal, item in enumerate(manifest):
            cur.execute("""INSERT INTO memory_provider_batch_requests
                (batch_run_id,custom_id,operation_key,pathway,ordinal,request_hash,source_hash,request_body,apply_context,attempt)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id""",
                (run_id, item["custom_id"], operation, item["pathway"], ordinal, item["request_hash"],
                 item["source_hash"], _json(item["body"]), _json(item["context"]), int(item.get("attempt") or 1)))
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
        provider = await adapter.submit(file_id, endpoint, metadata={
            "masteragent_run_id": run_id, "parent_run_id": parent["id"], "operation": operation,
        })
        with get_memory_db_context() as conn:
            cur = conn.cursor()
            cur.execute("""UPDATE memory_provider_batch_runs SET provider_input_file_id=%s,provider_batch_id=%s,
                provider_status=%s,local_status=%s,submitted_at=NOW(),next_poll_at=NOW()+INTERVAL '30 seconds',updated_at=NOW()
                WHERE id=%s""", (file_id, provider["id"], provider.get("status"),
                _local_from_provider(provider.get("status")), run_id))
            cur.execute("""UPDATE memory_provider_batch_runs SET prepared_source_count=prepared_source_count+%s,
                child_count=child_count+1,updated_at=NOW(),next_poll_at=NOW()+INTERVAL '1 second' WHERE id=%s""",
                (source_count if count_prepared_sources else 0, parent["id"]))
    except Exception as exc:
        with get_memory_db_context() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE memory_provider_batch_runs SET local_status='failed',provider_error=%s::jsonb,finished_at=NOW(),updated_at=NOW() WHERE id=%s", (_json({"message": str(exc)}), run_id))
            cur.execute("UPDATE memory_provider_batch_runs SET pause_requested=TRUE,provider_error=%s::jsonb,updated_at=NOW() WHERE id=%s", (_json({"message": str(exc), "child_run_id": run_id}), parent["id"]))
        raise
    return get_run(run_id)


async def prepare_next_child(parent_id: str) -> Dict[str, Any]:
    parent = _load_run(parent_id)
    if not parent.get("is_coordinator") or parent.get("preparation_complete") or parent.get("pause_requested") or parent.get("cancel_requested"):
        return get_run(parent_id)
    remaining = max(0, int(parent.get("target_source_count") or 0) - int(parent.get("prepared_source_count") or 0))
    if not remaining:
        with get_memory_db_context() as conn:
            conn.cursor().execute("UPDATE memory_provider_batch_runs SET preparation_complete=TRUE,updated_at=NOW() WHERE id=%s", (parent_id,))
        return _aggregate_parent(parent_id)
    try:
        max_concurrent = max(1, min(50, int(os.getenv("PROVIDER_BATCH_MAX_CONCURRENT_JOBS", "5"))))
    except (TypeError, ValueError):
        max_concurrent = 5
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("""SELECT COUNT(*) count FROM memory_provider_batch_runs
            WHERE parent_run_id=%s AND local_status<>ALL(%s)""", (parent_id, list(LOCAL_TERMINAL)))
        if int(cur.fetchone()["count"] or 0) >= max_concurrent:
            return _aggregate_parent(parent_id)
    try:
        chunk = max(25, min(50_000, int(os.getenv("PROVIDER_BATCH_PREPARATION_CHUNK_RECORDS", "10000"))))
    except (TypeError, ValueError):
        chunk = 10_000
    limit = min(remaining, chunk); operation = parent["operation_key"]
    if operation == "knowledge_embedding_backfill":
        sources = _embedding_sources(limit, parent_id, (parent.get("run_options") or {}).get("snapshot_cutoff"))
    elif operation == "backfill_facets":
        sources = _facet_sources(limit, parent_id, (parent.get("run_options") or {}).get("snapshot_cutoff"))
    elif operation == "run_all_knowledge_generation":
        sources = _generation_sources(limit, parent_id, (parent.get("run_options") or {}).get("snapshot_cutoff"))
    else:
        sources = _hygiene_sources(limit, parent_id, (parent.get("run_options") or {}).get("snapshot_cutoff"))
    manifest = _filter_claimed_manifest(parent_id, _build_manifest(operation, sources, parent.get("run_options") or {}))
    manifest = _limit_manifest_sources(manifest, remaining)
    if not manifest:
        with get_memory_db_context() as conn:
            conn.cursor().execute("UPDATE memory_provider_batch_runs SET preparation_complete=TRUE,updated_at=NOW() WHERE id=%s", (parent_id,))
        return _aggregate_parent(parent_id)
    await _submit_child(parent, manifest)
    return _aggregate_parent(parent_id)


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
        model = row.get("run_model") or _provider_config(operation).get("model_name")
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
            model_provider=row.get("run_provider") or _provider_config(operation).get("provider"),
            model_name=row.get("run_model") or _provider_config(operation).get("model_name"),
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
    if run.get("is_coordinator"):
        with get_memory_db_context() as conn:
            cur = conn.cursor(); cur.execute("""SELECT id FROM memory_provider_batch_runs
                WHERE parent_run_id=%s AND local_status=ANY(%s) AND provider_batch_id IS NOT NULL
                ORDER BY created_at LIMIT 10""", (run_id, list(ACTIVE_LOCAL)))
            child_ids = [row["id"] for row in cur.fetchall()]
        for child_id in child_ids:
            try:
                await reconcile(child_id)
            except Exception as exc:
                logger.warning("Child reconciliation failed for %s: %s", child_id, exc)
        run = _load_run(run_id)
        if not run.get("preparation_complete") and not run.get("pause_requested") and not run.get("cancel_requested"):
            return await prepare_next_child(run_id)
        return _aggregate_parent(run_id)
    if run["local_status"] in LOCAL_TERMINAL:
        return get_run(run_id)
    adapter = provider_adapter(_provider_config(run["operation_key"], run.get("run_options") or {}))
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
    if run.get("parent_run_id"):
        _aggregate_parent(run["parent_run_id"])
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


def _aggregate_parent(parent_id: str) -> Dict[str, Any]:
    """Roll child progress into one user-facing durable operation."""
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT COUNT(*) child_count,
            COALESCE(SUM(request_count),0) requests,
            COALESCE(SUM(completed_count),0) completed,
            COALESCE(SUM(applied_count),0) applied,
            COALESCE(SUM(failed_count),0) failed,
            COUNT(*) FILTER (WHERE local_status<>ALL(%s)) active,
            COUNT(*) FILTER (WHERE local_status IN ('failed','expired','cancelled','partially_completed')) problem
            FROM memory_provider_batch_runs WHERE parent_run_id=%s""", (list(LOCAL_TERMINAL), parent_id))
        counts = cur.fetchone()
        cur.execute("SELECT actual_usage FROM memory_provider_batch_runs WHERE parent_run_id=%s", (parent_id,))
        usages = [row.get("actual_usage") or {} for row in cur.fetchall()]
        aggregate_usage = {
            "input_tokens": sum(int(u.get("input_tokens") or 0) for u in usages),
            "output_tokens": sum(int(u.get("output_tokens") or 0) for u in usages),
            "total_tokens": sum(int(u.get("total_tokens") or 0) for u in usages),
            "estimated_cost_usd_from_actual_tokens": sum(float(u.get("estimated_cost_usd_from_actual_tokens") or 0) for u in usages),
        }
        cur.execute("SELECT preparation_complete,cancel_requested,pause_requested,pipeline_run_id,target_source_count,prepared_source_count FROM memory_provider_batch_runs WHERE id=%s", (parent_id,))
        parent = cur.fetchone()
        finished = bool(parent["preparation_complete"] and not counts["active"])
        if parent["cancel_requested"] and not counts["active"]:
            status = "cancelled"
        elif finished and counts["problem"]:
            status = "partially_completed" if counts["applied"] else "failed"
        elif finished:
            status = "completed"
        elif parent["pause_requested"]:
            status = "paused"
        else:
            status = "provider_in_progress" if counts["child_count"] else "preparing"
        cur.execute("""UPDATE memory_provider_batch_runs SET local_status=%s,child_count=%s,
            request_count=%s,completed_count=%s,applied_count=%s,failed_count=%s,
            actual_usage=%s::jsonb,finished_at=CASE WHEN %s THEN COALESCE(finished_at,NOW()) ELSE NULL END,updated_at=NOW()
            WHERE id=%s""", (status, counts["child_count"], counts["requests"], counts["completed"],
                               counts["applied"], counts["failed"], _json(aggregate_usage), finished, parent_id))
    if parent.get("pipeline_run_id"):
        from memory_db_writes import update_pipeline_run
        update_pipeline_run(
            parent["pipeline_run_id"], status=("completed" if status in {"completed", "partially_completed"} else status),
            outcome=status if finished else None,
            records_created=int(counts["applied"] or 0),
            progress_total=int(parent.get("target_source_count") or 0),
            progress_completed=int(parent.get("prepared_source_count") or 0),
            progress_failed=int(counts["failed"] or 0),
            detail={"provider_batch_run_id": parent_id, "child_count": int(counts["child_count"] or 0),
                    "actual_usage": aggregate_usage},
        )
    return get_run(parent_id)


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
        cur = conn.cursor(); cur.execute("""SELECT q.*,r.provider AS run_provider,r.model AS run_model
            FROM memory_provider_batch_requests q JOIN memory_provider_batch_runs r ON r.id=q.batch_run_id
            WHERE q.batch_run_id=%s AND q.status='received' ORDER BY q.ordinal""", (run_id,)); rows = [dict(r) for r in cur.fetchall()]
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
        run_cur = conn.cursor(); run_cur.execute("SELECT operation_key,pricing_snapshot FROM memory_provider_batch_runs WHERE id=%s", (run_id,))
        run_meta = run_cur.fetchone() or {}
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
        pricing = run_meta.get("pricing_snapshot") or {}
        input_price = pricing.get("embedding_cost_per_million") if run_meta.get("operation_key") == "knowledge_embedding_backfill" else pricing.get("batch_input_cost_per_million")
        output_price = pricing.get("batch_output_cost_per_million")
        actual_usage["estimated_cost_usd_from_actual_tokens"] = (
            (actual_usage["input_tokens"] * float(input_price or 0) + actual_usage["output_tokens"] * float(output_price or 0)) / 1_000_000
            if input_price is not None else None
        )
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
        if run.get("is_coordinator"):
            cur.execute("""SELECT id,provider,model,local_status,provider_status,provider_batch_id,
                request_count,completed_count,applied_count,failed_count,submitted_at,finished_at,created_at
                FROM memory_provider_batch_runs WHERE parent_run_id=%s ORDER BY created_at""", (run_id,))
            run["children"] = [dict(row) for row in cur.fetchall()]
    return run


def list_runs(limit: int = 30) -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("SELECT * FROM memory_provider_batch_runs WHERE parent_run_id IS NULL ORDER BY created_at DESC LIMIT %s", (max(1, min(limit, 100)),)); return [dict(r) for r in cur.fetchall()]


def list_requests(run_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("SELECT is_coordinator FROM memory_provider_batch_runs WHERE id=%s", (run_id,))
        run = cur.fetchone()
        if run and run.get("is_coordinator"):
            cur.execute("""SELECT q.id,q.custom_id,q.pathway,q.ordinal,q.status,q.attempt,q.provider_request_id,
                q.usage,q.error,q.output_references,q.validated_at,q.applied_at,q.created_at,q.updated_at,
                q.batch_run_id FROM memory_provider_batch_requests q
                JOIN memory_provider_batch_runs r ON r.id=q.batch_run_id
                WHERE r.parent_run_id=%s ORDER BY r.created_at,q.ordinal LIMIT %s""",
                (run_id, max(1, min(limit, 1000))))
        else:
            cur.execute("""SELECT id,custom_id,pathway,ordinal,status,attempt,provider_request_id,
                usage,error,output_references,validated_at,applied_at,created_at,updated_at,batch_run_id
                FROM memory_provider_batch_requests WHERE batch_run_id=%s ORDER BY ordinal LIMIT %s""",
                (run_id, max(1, min(limit, 1000))))
        return [dict(r) for r in cur.fetchall()]


async def cancel(run_id: str) -> Dict[str, Any]:
    run = _load_run(run_id)
    if run["local_status"] in LOCAL_TERMINAL: return get_run(run_id)
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE memory_provider_batch_runs SET cancel_requested=TRUE,preparation_complete=CASE WHEN is_coordinator THEN TRUE ELSE preparation_complete END,local_status='cancelling',updated_at=NOW() WHERE id=%s", (run_id,))
        if run.get("is_coordinator"):
            cur.execute("SELECT id FROM memory_provider_batch_runs WHERE parent_run_id=%s AND local_status<>ALL(%s)", (run_id, list(LOCAL_TERMINAL)))
            child_ids = [row["id"] for row in cur.fetchall()]
        else:
            child_ids = []
    for child_id in child_ids:
        try:
            await cancel(child_id)
        except Exception as exc:
            logger.warning("Could not cancel child batch %s: %s", child_id, exc)
    if run.get("provider_batch_id"):
        await provider_adapter(_provider_config(run["operation_key"], run.get("run_options") or {})).cancel(run["provider_batch_id"])
    return get_run(run_id)


async def retry(run_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a fresh source snapshot and provider attempt for unresolved work.

    Discovery is intentionally rerun: stale or already-applied sources disappear
    through normal eligibility rules instead of reusing an expired JSONL file.
    """
    previous = _load_run(run_id)
    if previous["local_status"] not in {"failed", "expired", "cancelled", "partially_completed"}:
        raise ValueError("Only failed, expired, cancelled, or partially completed runs can be retried")
    if previous.get("is_coordinator"):
        with get_memory_db_context() as conn:
            cur = conn.cursor(); cur.execute("""SELECT id FROM memory_provider_batch_runs
                WHERE parent_run_id=%s AND local_status IN ('failed','expired','cancelled','partially_completed')
                ORDER BY created_at""", (run_id,))
            failed_children = [row["id"] for row in cur.fetchall()]
        retried = 0
        for child_id in failed_children:
            child_result = await retry(child_id, actor_id=actor_id)
            retried += int(bool(child_result))
        with get_memory_db_context() as conn:
            conn.cursor().execute("""UPDATE memory_provider_batch_runs SET cancel_requested=FALSE,
                pause_requested=FALSE,preparation_complete=CASE WHEN prepared_source_count<target_source_count THEN FALSE ELSE TRUE END,
                local_status='preparing',next_poll_at=NOW(),provider_error='{}'::jsonb,finished_at=NULL,updated_at=NOW()
                WHERE id=%s""", (run_id,))
        return _aggregate_parent(run_id)
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
    if not previous.get("parent_run_id"):
        raise ValueError("This legacy standalone batch cannot be retried automatically; review a fresh asynchronous operation")
    parent = _load_run(previous["parent_run_id"])
    retried = await _submit_child(parent, manifest, count_prepared_sources=False)
    _aggregate_parent(parent["id"])
    return retried


def pause(run_id: str) -> Dict[str, Any]:
    with get_memory_db_context() as conn:
        conn.cursor().execute("UPDATE memory_provider_batch_runs SET pause_requested=TRUE,local_status=CASE WHEN is_coordinator THEN 'paused' ELSE local_status END,updated_at=NOW() WHERE id=%s AND local_status NOT IN ('completed','failed','cancelled','expired')", (run_id,))
    return get_run(run_id)


def resume(run_id: str) -> Dict[str, Any]:
    with get_memory_db_context() as conn:
        conn.cursor().execute("UPDATE memory_provider_batch_runs SET pause_requested=FALSE,local_status=CASE WHEN is_coordinator THEN 'preparing' ELSE local_status END,next_poll_at=NOW(),updated_at=NOW() WHERE id=%s AND cancel_requested=FALSE", (run_id,))
    return get_run(run_id)


async def recover_nonterminal() -> int:
    """Reconcile submitted work after a deployment; safe to call repeatedly."""
    with get_memory_db_context() as conn:
        cur = conn.cursor(); cur.execute("""SELECT id FROM memory_provider_batch_runs
            WHERE ((is_coordinator=TRUE AND preparation_complete=FALSE AND pause_requested=FALSE AND cancel_requested=FALSE)
               OR (is_coordinator=FALSE AND local_status=ANY(%s) AND provider_batch_id IS NOT NULL))
              AND COALESCE(next_poll_at,NOW())<=NOW() ORDER BY is_coordinator DESC,created_at LIMIT 10""",
            (list(ACTIVE_LOCAL),)); ids = [r["id"] for r in cur.fetchall()]
    for run_id in ids:
        try: await reconcile(run_id)
        except Exception as exc: logger.warning("Provider batch recovery failed for %s: %s", run_id, exc)
    return len(ids)
