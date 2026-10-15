import os
import json
import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional, TypedDict, Any, Callable
from bullmq import Queue, Worker, Job
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Enterprise Type Safety for BullMQ
class IngestInteractionPayload(TypedDict):
    interaction_id: str

class GenerateMemoryPayload(TypedDict):
    entity_type: str
    entity_id: str
    interaction_date: str

class BasicEntityPayload(TypedDict):
    entity_type: str
    entity_id: str

class PromoteKnowledgePayload(TypedDict):
    insight_id: str

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


def _positive_int_env(name: str, default: int) -> int:
    """Read a bounded queue setting without allowing malformed deployment envs."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; using %s", name, default)
        return default
    return max(0, value)


# BullMQ stores completed/failed job payloads unless retention is explicitly
# bounded.  Counts are deliberately configurable because production operators
# may need a larger audit window, but must never be unbounded by default.
BULL_REMOVE_ON_COMPLETE = _positive_int_env("BULL_REMOVE_ON_COMPLETE_COUNT", 1000)
BULL_REMOVE_ON_FAIL = _positive_int_env("BULL_REMOVE_ON_FAIL_COUNT", 1000)
BULL_DEFAULT_JOB_OPTIONS = {
    "removeOnComplete": BULL_REMOVE_ON_COMPLETE,
    "removeOnFail": BULL_REMOVE_ON_FAIL,
}

# TASK-257 §6: these started as memory_settings knobs whose columns never
# existed, so every settings.get() silently returned its default. Concurrency
# binds at Worker start, so a live knob would need a worker restart to take
# effect anyway. Per-job attempts/backoff moved into the JobSpec registry (§5b).
QUEUE_CONCURRENCY = {"interactions_ops": 5, "memory_ops": 1, "knowledge_ops": 1}

interactions_queue = Queue("interactions_ops", opts={"connection": REDIS_URL, "defaultJobOptions": BULL_DEFAULT_JOB_OPTIONS})
memory_queue = Queue("memory_ops", opts={"connection": REDIS_URL, "defaultJobOptions": BULL_DEFAULT_JOB_OPTIONS})
knowledge_queue = Queue("knowledge_ops", opts={"connection": REDIS_URL, "defaultJobOptions": BULL_DEFAULT_JOB_OPTIONS})
memory_bulk_queue = interactions_queue

interactions_worker = None
memory_worker = None
knowledge_worker = None

# ── TASK-257 §5: declarative job registry ─────────────────────────────────────
# Every job the memory workers execute is declared once in JOBS: its handler,
# operator-control key, singleton lease, rate-limit policy, planning estimate,
# and completion side effects. BullMQ stays dumb transport and
# _process_bulk_job is a generic runner that reads a JobSpec.
#
# Per-job attempts/backoff live in the spec; enqueue sites read them through
# job_options(). Scheduled-run claims ride the job payload (job_claim) and the
# runner completes them after the work — completing at enqueue let a job lost
# between enqueue and pickup silently skip the day. Legacy job names
# (generate_knowledge, run_consolidation) stay first-class specs flagged
# replaced_by so in-flight producers keep working during the one-release
# mapping window — the runner logs a deprecation warning each time one is
# picked up.

Handler = Callable[[Any, Any], Any]


@dataclass(frozen=True)
class JobSpec:
    name: str
    handler: Handler
    ai_gate: bool = False                  # halt cleanly on a provider quota stop
    controls_key: Optional[str] = None     # services.job_controls pause/cancel checkpoint
    singleton: bool = False                # DB lease: one concurrent run at a time
    estimate_tokens: int = 1200            # planning estimate applied when max_records is set
    estimate_price_per_million: Optional[float] = None
    rpm: int = 60                          # fixed dispatch rate limit
    rpm_llm_config: Optional[str] = None   # LLM config whose rate_limit_rpm overrides rpm
    attempts: Optional[int] = None         # BullMQ retry count; None = single attempt (queue default)
    backoff_ms: int = 2000                 # exponential backoff delay between attempts
    refresh_metrics_on_complete: bool = False  # enqueue refresh_operation_metrics on completion
    dlq_interactions: bool = False         # stamp the interactions row failed on final attempt
    replaced_by: Optional[str] = None      # legacy name → current name to enqueue instead


# Handlers import their collaborators function-locally to avoid circular
# dependencies at boot — and so tests patching the worker-handler modules' attributes are
# resolved at dispatch time.

async def _run_ingest_interaction(job: Job, run_id) -> None:
    from memory_system.ingest.ingestion import process_interaction
    interaction_id = job.data.get("interaction_id")
    if interaction_id:
        await process_interaction(interaction_id)


async def _run_fire_outbound_webhook(job: Job, run_id) -> None:
    webhook_id = job.data.get("webhook_id")
    entity_id = job.data.get("entity_id")
    if webhook_id and entity_id:
        from services.outbound_webhooks import execute_outbound_webhook
        await execute_outbound_webhook(webhook_id, entity_id)


async def _run_generate_memory(job: Job, run_id) -> None:
    from memory_system.distill.generation import _generate_memory_for_entity
    e_type = job.data.get("entity_type")
    e_id = job.data.get("entity_id")
    date_str = job.data.get("interaction_date")
    if e_type and e_id and date_str:
        await _generate_memory_for_entity(e_type, e_id, date_str)


async def _run_generate_insight(job: Job, run_id) -> None:
    from memory_system.distill.compaction import compact_entity
    e_type = job.data.get("entity_type")
    e_id = job.data.get("entity_id")
    if e_type and e_id:
        await compact_entity(e_type, e_id)


async def _run_knowledge_check(job: Job, run_id):
    """Core knowledge-tier generation shared by the two job names below."""
    from memory_system.distill.knowledge import run_knowledge_check
    return await run_knowledge_check(
        drain=bool(job.data.get("drain")), min_count=job.data.get("min_count"),
        max_rounds=int(job.data.get("max_rounds", 50 if job.data.get("drain") else 1)),
        max_records=int(job.data.get("max_records", 100000)),
        progress_run_id=run_id,
    )


async def _run_all_knowledge_generation(job: Job, run_id):
    # One orchestrated run for every enabled producer: knowledge tiers plus
    # the playbook check and a telemetry pass (backfill on drain runs,
    # reflection otherwise). The legacy generate_knowledge name runs the
    # tiers only.
    operation_result = await _run_knowledge_check(job, run_id)
    from memory_system.distill.playbooks import run_playbook_check
    from memory_system.distill.telemetry import run_telemetry_reflection, backfill_telemetry
    await run_playbook_check()
    if job.data.get("drain"):
        await backfill_telemetry(max_days=int(job.data.get("max_days", 7)))
    else:
        await run_telemetry_reflection(job.data.get("reflection_date"))
    return operation_result


async def _run_promote_to_knowledge(job: Job, run_id) -> None:
    from memory_system.distill.knowledge import promote_to_knowledge
    i_id = job.data.get("insight_id")
    if i_id:
        await promote_to_knowledge(i_id)


async def _run_extract_playbooks(job: Job, run_id) -> None:
    from memory_system.distill.playbooks import run_playbook_check
    await run_playbook_check()


async def _run_consolidation(job: Job, run_id):
    # Legacy job name kept as a backward-compatible alias: it now starts
    # a hygiene run using the configured mode (no pairwise retirement),
    # plus the non-destructive decay/quality maintenance.
    from memory_system.maintain.consolidation import run_consolidation
    return await run_consolidation(
        max_records=int(job.data.get("max_records", 1000)),
        max_clusters=int(job.data.get("max_clusters", 100)),
        progress_run_id=run_id,
    )


async def _run_knowledge_hygiene(job: Job, run_id):
    # Knowledge hygiene: discover candidate clusters + generate proposals.
    # Auto-apply only in auto_* modes; manual_only/proposal_only never apply.
    from memory_system.maintain.consolidation_service import discover_and_propose
    from services.config_helpers import get_memory_settings
    _hsettings = get_memory_settings() or {}
    _mode = job.data.get("mode") or _hsettings.get("knowledge_hygiene_mode", "manual_only")
    _auto = (
        bool(job.data.get("allow_auto_apply", False))
        and _mode in ("auto_conservative", "auto_synthesis")
        and _hsettings.get("knowledge_hygiene_enabled", True)
    )
    return await discover_and_propose(
        run_id=job.data.get("run_id"),
        origin=job.data.get("origin") or "scheduled",
        mode=_mode,
        category_filter=job.data.get("category"),
        actor_id=None,
        auto_apply=bool(_auto),
        max_records=int(job.data.get("max_records", 5000)),
        max_clusters=int(job.data.get("max_clusters", 100)),
        progress_run_id=run_id,
    )


async def _run_embedding_backfill(job: Job, run_id):
    # Resumable, idempotent embedding backfill (never mutates content/status).
    from memory_system.maintain.embedding_backfill import run_embedding_backfill
    return await run_embedding_backfill(
        batch_size=int(job.data.get("batch_size", 25)),
        max_records=int(job.data.get("max_records", 1000)),
        progress_run_id=run_id,
    )


async def _run_creation_time_consolidation(job: Job, run_id) -> None:
    # Async creation-time consolidation: find candidates for a freshly
    # created record and propose (auto-apply only in auto_* modes).
    from memory_system.maintain.consolidation_service import creation_time_propose
    from services.config_helpers import get_memory_settings
    _cts = get_memory_settings() or {}
    _cmode = _cts.get("knowledge_hygiene_mode", "manual_only")
    await creation_time_propose(
        knowledge_id=job.data.get("knowledge_id"),
        auto_apply=_cmode in ("auto_conservative", "auto_synthesis"),
    )


async def _run_backfill_facets(job: Job, run_id):
    from memory_system.distill.facets import backfill_facets
    return await backfill_facets(
        batch_size=int(job.data.get("batch_size", 25)),
        max_records=int(job.data.get("max_records", 250)),
        progress_run_id=run_id,
    )


async def _run_backfill_telemetry(job: Job, run_id) -> None:
    from memory_system.distill.telemetry import backfill_telemetry
    await backfill_telemetry(max_days=int(job.data.get("max_days", 7)))


async def _run_interaction_retention(job: Job, run_id):
    from memory_system.maintain.interaction_retention import run_interaction_retention
    # Sync batched deletes must not block the shared event loop.
    return await asyncio.to_thread(
        run_interaction_retention,
        batch_size=int(job.data.get("batch_size", 500)),
        max_records=int(job.data.get("max_records", 5000)),
        progress_run_id=run_id,
    )


async def _run_refresh_operation_metrics(job: Job, run_id):
    from memory_system.maintain.operation_metrics import refresh_snapshots
    # Exact-eligibility aggregation is a synchronous table scan.
    return await asyncio.to_thread(refresh_snapshots)


async def _run_intelligence_sweep(job: Job, run_id) -> None:
    from memory_system.distill.compaction import run_compaction_check
    await run_compaction_check(min_count=job.data.get("min_count"))


async def _run_reflect_telemetry(job: Job, run_id) -> None:
    from memory_system.distill.telemetry import run_telemetry_reflection
    await run_telemetry_reflection(job.data.get("reflection_date"))


async def _run_extract_knowledge_attachment(job: Job, run_id):
    from memory_system.distill.knowledge_attachments import extract_attachment
    return await extract_attachment(
        str(job.data.get("attachment_id")),
        max_pages=int(job.data.get("max_pages", 200)),
    )


JOBS: dict = {
    # Interactions & webhooks
    "ingest_interaction": JobSpec("ingest_interaction", _run_ingest_interaction,
                                  ai_gate=True, rpm=600, dlq_interactions=True,
                                  attempts=3, backoff_ms=2000),
    # Manual single-shot below: no attempts policy (operators see the error directly).
    "reprocess": JobSpec("reprocess", _run_ingest_interaction,
                         ai_gate=True, rpm=600, dlq_interactions=True),
    "fire_outbound_webhook": JobSpec("fire_outbound_webhook", _run_fire_outbound_webhook,
                                     rpm=600),
    # Memory generation
    "generate_memory": JobSpec("generate_memory", _run_generate_memory,
                               ai_gate=True, rpm_llm_config="summarization",
                               attempts=3, backoff_ms=2000),
    "generate_insight": JobSpec("generate_insight", _run_generate_insight,
                                ai_gate=True, rpm_llm_config="intelligence_generation"),
    "run_intelligence_sweep": JobSpec("run_intelligence_sweep", _run_intelligence_sweep,
                                      ai_gate=True, attempts=3, backoff_ms=60000),
    "creation_time_consolidation": JobSpec("creation_time_consolidation", _run_creation_time_consolidation,
                                           ai_gate=True),
    # Knowledge generation — generate_knowledge is the legacy name (tiers only).
    "generate_knowledge": JobSpec("generate_knowledge", _run_knowledge_check,
                                  ai_gate=True, controls_key="run_all_knowledge_generation",
                                  rpm_llm_config="knowledge_generation",
                                  replaced_by="run_all_knowledge_generation"),
    "run_all_knowledge_generation": JobSpec("run_all_knowledge_generation", _run_all_knowledge_generation,
                                            ai_gate=True, controls_key="run_all_knowledge_generation",
                                            singleton=True, refresh_metrics_on_complete=True,
                                            attempts=3, backoff_ms=60000),
    "promote_to_knowledge": JobSpec("promote_to_knowledge", _run_promote_to_knowledge,
                                    ai_gate=True, rpm_llm_config="knowledge_generation"),
    "extract_playbooks": JobSpec("extract_playbooks", _run_extract_playbooks,
                                 ai_gate=True, singleton=True),
    "knowledge_hygiene_run": JobSpec("knowledge_hygiene_run", _run_knowledge_hygiene,
                                     ai_gate=True, controls_key="knowledge_hygiene_run",
                                     singleton=True, refresh_metrics_on_complete=True),
    "run_consolidation": JobSpec("run_consolidation", _run_consolidation,
                                 controls_key="knowledge_hygiene_run", singleton=True,
                                 replaced_by="knowledge_hygiene_run",
                                 attempts=3, backoff_ms=60000),
    "knowledge_embedding_backfill": JobSpec("knowledge_embedding_backfill", _run_embedding_backfill,
                                            ai_gate=True, controls_key="knowledge_embedding_backfill",
                                            singleton=True, estimate_tokens=500,
                                            estimate_price_per_million=0.02,
                                            refresh_metrics_on_complete=True),
    "extract_knowledge_attachment": JobSpec("extract_knowledge_attachment", _run_extract_knowledge_attachment,
                                            ai_gate=True),
    "backfill_facets": JobSpec("backfill_facets", _run_backfill_facets,
                               ai_gate=True, controls_key="backfill_facets",
                               singleton=True, refresh_metrics_on_complete=True),
    "backfill_telemetry": JobSpec("backfill_telemetry", _run_backfill_telemetry,
                                  ai_gate=True, singleton=True),
    "reflect_telemetry": JobSpec("reflect_telemetry", _run_reflect_telemetry,
                                 ai_gate=True, attempts=3, backoff_ms=60000),
    # Retention & metrics
    "interaction_retention": JobSpec("interaction_retention", _run_interaction_retention,
                                     controls_key="interaction_retention", singleton=True,
                                     attempts=3, backoff_ms=60000),
    "refresh_operation_metrics": JobSpec("refresh_operation_metrics", _run_refresh_operation_metrics,
                                         singleton=True),
}


def job_options(name: str, priority: Optional[int] = None) -> dict:
    """BullMQ enqueue options for a registered job: per-job attempts/backoff
    from its spec plus a site-chosen priority. Names without an attempts
    policy enqueue exactly as before."""
    options: dict = {}
    if priority is not None:
        options["priority"] = priority
    spec = JOBS.get(name)
    if spec is not None and spec.attempts:
        options["attempts"] = spec.attempts
        options["backoff"] = {"type": "exponential", "delay": spec.backoff_ms}
    return options


def _payload_claim(job: Job):
    """Scheduled-run claims ride the job payload (§5b): the scheduler stamps
    {'job_claim': {'name': <memory_job_log name>, 'date': 'YYYY-MM-DD'}} so the
    worker — not the enqueuer — completes the claim. Manual/admin triggers
    carry no claim and are unaffected. A malformed payload degrades to an
    unclaimed run."""
    raw = (job.data or {}).get("job_claim")
    if not (isinstance(raw, dict) and raw.get("name") and raw.get("date")):
        return None, None
    try:
        return str(raw["name"]), date.fromisoformat(str(raw["date"]))
    except ValueError:
        logger.warning("Ignoring malformed job_claim on job %s: %r", job.id, raw)
        return None, None


def _resolve_rpm(spec: JobSpec) -> int:
    """Dispatch rate limit: the spec default, overridden by its LLM config knob."""
    rpm = spec.rpm
    if spec.rpm_llm_config:
        from services.config_helpers import get_llm_config
        p_conf = get_llm_config(spec.rpm_llm_config)
        if p_conf and "rate_limit_rpm" in p_conf:
            rpm = p_conf.get("rate_limit_rpm", spec.rpm)
    return rpm


async def _process_bulk_job(job: Job, token: str):
    spec = JOBS.get(job.name)
    singleton_lock_name = None
    run_id = None
    claim_name, claim_date = _payload_claim(job)
    try:
        if spec is not None:
            # A duplicate re-fired by the 15-min stale reclaim while the
            # original still executes must not run the sweep twice: if the
            # claimed date already completed, this pickup is a no-op.
            if claim_name:
                from memory_system.distill.generation import get_job_claim_status
                if get_job_claim_status(claim_name, claim_date) == "completed":
                    logger.info("Skipping %s (%s): claim %s/%s already completed",
                                job.name, job.id, claim_name, claim_date)
                    return {"status": "skipped", "reason": "claim_completed"}

            if spec.replaced_by:
                logger.warning(
                    "Job name '%s' is deprecated; enqueue '%s' instead "
                    "(legacy names are retired after the mapping window)",
                    job.name, spec.replaced_by)

            # A credit/quota hard-stop must halt queued AI work cleanly. Completing
            # the skipped job (rather than retrying it) prevents a queue storm; an
            # operator can re-run it after resolving the provider alert.
            if spec.ai_gate:
                from services.job_safety import active_provider_stop
                provider_block = active_provider_stop()
                if provider_block:
                    if job.name == "extract_knowledge_attachment" and job.data.get("attachment_id"):
                        from core.storage import get_memory_db_context
                        with get_memory_db_context() as conn:
                            conn.cursor().execute(
                                "UPDATE knowledge_attachments SET status='blocked', extraction=%s::jsonb, updated_at=NOW() WHERE id=%s",
                                (json.dumps({"error": provider_block["message"], "reason": provider_block["code"]}), job.data.get("attachment_id")),
                            )
                    from memory_system.store.writes import log_pipeline_run
                    log_pipeline_run(job.name, "blocked", reason_code=provider_block["code"],
                                     detail={"message": provider_block["message"], "queue_job_id": str(job.id)},
                                     trigger="queue")
                    logger.warning("Skipping %s (%s): %s", job.name, job.id, provider_block["code"])
                    return {"status": "blocked", "reason": provider_block["code"]}

            if spec.controls_key:
                from services.job_controls import get_command
                command = get_command(spec.controls_key)
                if command in {"pause", "cancel"}:
                    logger.info("Skipping %s at operator checkpoint (%s)", job.name, command)
                    from memory_system.store.writes import log_pipeline_run
                    log_pipeline_run(job.name, "skipped", reason_code=f"operator_{command}",
                                     detail={"queue_job_id": str(job.id), "control": command}, trigger="queue")
                    return {"status": command, "reason": f"operator_{command}"}

            if spec.singleton:
                from services.job_safety import try_acquire_singleton_job
                if not try_acquire_singleton_job(job.name):
                    from memory_system.store.writes import log_pipeline_run
                    log_pipeline_run(job.name, "skipped", reason_code="already_running",
                                     detail={"queue_job_id": str(job.id)}, trigger="queue")
                    logger.warning("Skipping duplicate maintenance job %s (%s)", job.name, job.id)
                    return {"status": "skipped", "reason": "already_running"}
                singleton_lock_name = job.name
                from memory_system.store.writes import log_pipeline_run
                max_records = job.data.get("max_records")
                batch_size = job.data.get("batch_size")
                if max_records:
                    # Planning token estimate only: generation/facet/hygiene
                    # input sizes vary by record and provider, so do not
                    # pretend we can calculate a reliable bill without model
                    # pricing metadata.
                    estimated_tokens = int(max_records) * spec.estimate_tokens
                    estimated_cost = (
                        estimated_tokens * spec.estimate_price_per_million / 1_000_000
                        if spec.estimate_price_per_million else None
                    )
                else:
                    estimated_tokens = estimated_cost = None
                run_id = log_pipeline_run(
                    job.name, "started",
                    detail={"queue_job_id": str(job.id), "progress_total": int(max_records or 0),
                            "estimated_tokens": estimated_tokens, "estimated_cost_usd": estimated_cost,
                            "batch_size": batch_size,
                            "records_per_batch": job.data.get("records_per_batch") or batch_size,
                            "batches_per_run": job.data.get("batches_per_run"),
                            "run_all": bool(job.data.get("run_all", False))}, trigger="queue")

        logger.info(f"Worker picked up job {job.id}: {job.name}")

        if spec is None:
            logger.warning(f"Unknown job name: {job.name}")
        else:
            operation_result = await spec.handler(job, run_id)

        logger.info(f"Successfully processed bulk job {job.id} ({job.name})")

        # §5b: the claim completes here — after the work, not at enqueue — so
        # a job lost between enqueue and pickup can no longer silently skip
        # the day (the scheduler's 15-min stale reclaim re-fires it instead).
        if claim_name:
            from memory_system.distill.generation import complete_job_date
            complete_job_date(claim_name, claim_date)

        if singleton_lock_name:
            from memory_system.store.writes import log_pipeline_run
            from services.job_controls import get_command
            control = spec.controls_key and get_command(spec.controls_key)
            stopped = control in {"pause", "cancel"}
            detail = {"queue_job_id": str(job.id), "result": operation_result or {},
                      "control": control or "run"}
            if run_id:
                from memory_system.store.writes import update_pipeline_run
                if isinstance(operation_result, dict):
                    tier_results = operation_result.get("tiers") or {}
                    base_completed = operation_result.get("processed")
                    if base_completed is None:
                        base_completed = operation_result.get("clusters_found", operation_result.get("records_scanned", 0))
                        if operation_result.get("clusters_found") is not None:
                            base_completed = min(int(base_completed or 0), int(job.data.get("max_clusters", 100)))
                    completed = int(base_completed or 0) + sum(int(v.get("processed", 0) or 0) for v in tier_results.values() if isinstance(v, dict))
                    failed_total = int(operation_result.get("failed", 0) or 0) + sum(int(v.get("failed", 0) or 0) for v in tier_results.values() if isinstance(v, dict))
                else:
                    completed, failed_total = int(operation_result or 0), 0
                update_pipeline_run(run_id, status="cancelled" if control == "cancel" else ("paused" if control == "pause" else "completed"),
                                    outcome="stopped" if stopped else "completed", records_created=int(completed or 0),
                                    progress_completed=int(completed or 0), progress_failed=failed_total,
                                    detail=detail)
            else:
                log_pipeline_run(job.name, "completed", detail=detail, trigger="queue")

            # Eligibility changes when any Knowledge operation completes. Keep
            # the persisted UI snapshot current even when no browser is open;
            # the guard collapses simultaneous completion/UI refresh requests.
            if spec.refresh_metrics_on_complete:
                from memory_system.maintain.operation_metrics import mark_refresh_error, request_refresh
                if request_refresh():
                    try:
                        await knowledge_queue.add("refresh_operation_metrics", {}, {"priority": 4})
                    except Exception as refresh_exc:
                        mark_refresh_error(f"Could not queue post-operation eligibility refresh: {refresh_exc}")
                        logger.warning("Could not queue eligibility refresh: %s", refresh_exc)

        # Mathematical rate limiting sequential block
        rpm = _resolve_rpm(spec) if spec else 60
        sleep_interval = 60.0 / (rpm if rpm and rpm > 0 else 60)
        await asyncio.sleep(sleep_interval)

    except Exception as e:
        logger.error(f"Bulk job {job.id} failed: {e}")

        if run_id:
            from memory_system.store.writes import update_pipeline_run
            update_pipeline_run(run_id, status="failed", outcome="failed",
                                reason_code="job_failed",
                                detail={"message": str(e), "queue_job_id": str(job.id)})

        from services.job_safety import ProviderStopError
        if isinstance(e, ProviderStopError):
            from memory_system.store.writes import log_pipeline_run
            if run_id:
                from memory_system.store.writes import update_pipeline_run
                update_pipeline_run(run_id, status="blocked", outcome="blocked", reason_code=e.code,
                                    detail={"message": str(e), "queue_job_id": str(job.id)})
            else:
                log_pipeline_run(job.name, "blocked", reason_code=e.code,
                                 detail={"message": str(e), "queue_job_id": str(job.id)}, trigger="queue")
            # Do not re-raise: a provider stop is operational state, not a
            # per-record failure that BullMQ should repeatedly retry.
            return {"status": "blocked", "reason": e.code}

        # DLQ logic: If this is the final attempt, update database status
        attempts_made = job.attemptsMade + 1
        max_attempts = job.opts.get("attempts", 1)

        if attempts_made >= max_attempts:
            logger.error(f"Job {job.id} exhausted {max_attempts} retries. Moving to DLQ.")
            from core.storage import get_memory_db_context
            from memory_system.store.writes import log_pipeline_run
            try:
                # Every terminal failure leaves a pipeline-run row — the BullMQ
                # failed-set cap (BULL_REMOVE_ON_FAIL_COUNT) is not a durable
                # record, and Tier-2/3 jobs previously left none at all.
                log_pipeline_run(job.name, "failed", reason_code="job_failed",
                                 detail={"error": str(e)[:500], "queue_job_id": str(job.id),
                                         "attempts": attempts_made},
                                 trigger="queue")
                # Basic DLQ effort for interactions
                if spec is not None and spec.dlq_interactions:
                    i_id = job.data.get("interaction_id")
                    if i_id:
                        with get_memory_db_context() as conn:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE interactions SET status = 'failed', processing_errors = %s WHERE id = %s",
                                           (json.dumps({"fatal_error": str(e)}), i_id))
            except Exception as dlq_e:
                logger.error(f"DLQ update failed for job {job.id}: {dlq_e}")

            # §5b: the scheduled claim fails with the job on its FINAL attempt —
            # earlier attempts leave it 'running' (BullMQ retries well inside the
            # 15-min reclaim window). Provider-stop blocks and operator skips
            # also leave it 'running': the reclaim re-fires later the same day
            # once the stop lifts or the operator resumes.
            if claim_name:
                try:
                    from memory_system.distill.generation import fail_job_date
                    fail_job_date(claim_name, claim_date, e)
                except Exception as claim_exc:
                    logger.error("Failed to stamp claim failure for %s/%s: %s",
                                 claim_name, claim_date, claim_exc)

        raise e
    finally:
        if singleton_lock_name:
            from services.job_safety import release_singleton_job
            release_singleton_job(singleton_lock_name)

def _handle_completed(job, result):
    logger.info(f"Job {job.id} completed successfully")

def _handle_failed(job, error):
    logger.error(f"Job {job.id} failed with error: {error}")
    # Sticky alert on the FINAL attempt only — per-attempt noise stays in logs,
    # but a job that exhausted its retries is worth a banner until acknowledged.
    try:
        attempts_made = job.attemptsMade + 1
        max_attempts = job.opts.get("attempts", 1)
        if attempts_made < max_attempts:
            return
        from core.storage import get_memory_db_context
        code = f"queue_job_failed:{job.name}"
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_system_alerts
                    (code, severity, title, message, source, detail, active, first_seen_at, last_seen_at)
                VALUES (%s, 'error', %s, %s, 'queue', %s::jsonb, TRUE, NOW(), NOW())
                ON CONFLICT (code) DO UPDATE SET active=TRUE, message=EXCLUDED.message,
                    detail=EXCLUDED.detail, last_seen_at=NOW()
            """, (code, f"Queue job '{job.name}' exhausted its retries",
                  str(error)[:500],
                  json.dumps({"job_id": str(job.id), "attempts": attempts_made})))
    except Exception as exc:
        logger.warning("Could not stamp queue-failure alert for %s: %s",
                       getattr(job, "name", "?"), exc)

async def start_bullmq_workers():
    global interactions_worker, memory_worker, knowledge_worker

    from services.job_safety import reconcile_stale_maintenance_runs
    reconcile_stale_maintenance_runs()

    logger.info(
        "Starting BullMQ Workers (Int: %s, Mem: %s, Know: %s)...",
        QUEUE_CONCURRENCY["interactions_ops"],
        QUEUE_CONCURRENCY["memory_ops"],
        QUEUE_CONCURRENCY["knowledge_ops"],
    )

    interactions_worker = Worker("interactions_ops", _process_bulk_job, opts={"connection": REDIS_URL, "concurrency": QUEUE_CONCURRENCY["interactions_ops"]})
    interactions_worker.on("completed", _handle_completed)
    interactions_worker.on("failed", _handle_failed)

    memory_worker = Worker("memory_ops", _process_bulk_job, opts={"connection": REDIS_URL, "concurrency": QUEUE_CONCURRENCY["memory_ops"]})
    memory_worker.on("completed", _handle_completed)
    memory_worker.on("failed", _handle_failed)

    knowledge_worker = Worker("knowledge_ops", _process_bulk_job, opts={"connection": REDIS_URL, "concurrency": QUEUE_CONCURRENCY["knowledge_ops"]})
    knowledge_worker.on("completed", _handle_completed)
    knowledge_worker.on("failed", _handle_failed)

async def stop_bullmq_workers():
    global interactions_worker, memory_worker, knowledge_worker
    logger.info("Stopping BullMQ Workers gracefully...")
    tasks = []
    if interactions_worker: tasks.append(interactions_worker.close())
    if memory_worker: tasks.append(memory_worker.close())
    if knowledge_worker: tasks.append(knowledge_worker.close())
    
    if tasks:
        await asyncio.gather(*tasks)
    logger.info("BullMQ Workers stopped.")



