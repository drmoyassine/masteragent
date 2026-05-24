import json
import logging
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import httpx

from core.storage import get_memory_db_context, get_redis_client

logger = logging.getLogger(__name__)

async def evaluate_outbound_webhooks(interaction_id: str):
    """
    Evaluates an interaction against all active outbound webhooks.
    If conditions match, it sets a Redis debounce timestamp and enqueues a delayed BullMQ job.
    """
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        # Fetch the completed interaction
        cursor.execute("""
            SELECT id, primary_entity_id, primary_entity_type, interaction_type, source
            FROM interactions WHERE id = %s
        """, (interaction_id,))
        interaction = cursor.fetchone()
        
        if not interaction:
            return

        # Fetch all active outbound webhooks
        cursor.execute("""
            SELECT id, name, debounce_ms, conditions 
            FROM memory_outbound_webhooks 
            WHERE is_active = TRUE
        """)
        webhooks = cursor.fetchall()

    if not webhooks:
        return

    redis = get_redis_client()

    for wh in webhooks:
        webhook_id = wh["id"]
        debounce_ms = wh["debounce_ms"] or 60000
        conditions = wh["conditions"] or {}
        if isinstance(conditions, str):
            try:
                conditions = json.loads(conditions)
            except:
                conditions = {}

        # Simple json filter evaluated natively
        # e.g., conditions: {"interaction_type": ["whatsapp_incoming"]}
        match = True
        for key, value in conditions.items():
            interaction_val = interaction.get(key)
            if isinstance(value, list):
                if interaction_val not in value:
                    match = False
                    break
            elif interaction_val != value:
                match = False
                break
        
        if match:
            # Refresh the sliding-window timer in Redis. TTL is debounce + 5 minutes
            # so the key survives reasonable BullMQ queue backpressure.
            now_ts = datetime.now(timezone.utc).timestamp()
            ttl_s = max(60, (debounce_ms + 5 * 60_000) // 1000)
            redis.set(f"outbound_debounce:{webhook_id}:{interaction['primary_entity_id']}", str(now_ts), ex=ttl_s)
            
            # Enqueue delayed job
            try:
                # Import locally to avoid circular dependencies
                from memory.queue import interactions_queue
                await interactions_queue.add(
                    "fire_outbound_webhook",
                    {
                        "webhook_id": webhook_id, 
                        "entity_id": interaction["primary_entity_id"]
                    },
                    {"delay": debounce_ms, "priority": 1}
                )
                logger.info(f"Triggered outbound webhook rule '{wh['name']}' for {interaction['primary_entity_id']} (in {debounce_ms}ms)")
            except Exception as e:
                logger.error(f"Failed to enqueue outbound webhook logic: {e}")

async def execute_outbound_webhook(webhook_id: str, entity_id: str):
    """
    Called by the worker when the debounce period settles.
    Queries the database and fires the compiled payload.
    """
    redis = get_redis_client()
    debounce_key = f"outbound_debounce:{webhook_id}:{entity_id}"

    # Check if timer has been pushed further back by newer interactions
    last_run_str = redis.get(debounce_key)
    if not last_run_str:
        return # Timer expired natively or doesn't exist, safely ignore.

    # Defer-and-retry pre-flight checks:
    #   (a) memory job holds the per-entity lock — wait for it to release, then
    #       the next firing reads fresh state (including the just-generated memory).
    #   (b) any pending interaction for this entity is still un-enriched (vision/
    #       embedding pipeline hasn't completed) — wait so the payload ships
    #       with parsed attachment text included.
    # We re-enqueue the same fire with a short delay. A Redis counter caps the
    # number of consecutive defers so a stuck interaction can't spin forever;
    # after the cap, we fire with whatever's enriched.
    WAIT_DELAY_MS = 10_000
    MAX_WAIT_RETRIES = 30  # ~5 minutes of cumulative waiting
    wait_counter_key = f"outbound_wait:{webhook_id}:{entity_id}"

    try:
        from services import memory_lock

        # Resolve entity_type from the most recent interaction (any status).
        # This ensures the memory lock check works even after memory generation
        # marks all interactions as 'done'.
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT primary_entity_type FROM interactions
                WHERE primary_entity_id = %s
                ORDER BY timestamp DESC LIMIT 1
            """, (entity_id,))
            row = cursor.fetchone()
            et = row["primary_entity_type"] if row else None

            # Count un-enriched pending interactions for this entity.
            cursor.execute("""
                SELECT COUNT(*) AS cnt FROM interactions
                WHERE primary_entity_id = %s AND status = 'pending' AND is_enriched = FALSE
            """, (entity_id,))
            row2 = cursor.fetchone()
            unenriched = (row2["cnt"] if row2 else 0) or 0

        memory_locked = bool(et and memory_lock.is_locked(et, entity_id))

        if memory_locked or unenriched > 0:
            # Check how many times we've already deferred this fire.
            try:
                current = int(redis.get(wait_counter_key) or 0)
            except Exception:
                current = 0

            if current < MAX_WAIT_RETRIES:
                # Increment counter with a generous TTL (well beyond the max wait).
                try:
                    redis.set(wait_counter_key, str(current + 1), ex=900)
                except Exception as e:
                    logger.warning(f"outbound_wait counter set failed: {e}")

                from memory.queue import interactions_queue
                await interactions_queue.add(
                    "fire_outbound_webhook",
                    {"webhook_id": webhook_id, "entity_id": entity_id},
                    {"delay": WAIT_DELAY_MS, "priority": 1},
                )
                reasons = []
                if memory_locked:
                    reasons.append("memory lock held")
                if unenriched > 0:
                    reasons.append(f"{unenriched} unenriched interaction(s)")
                logger.info(
                    f"Outbound webhook {webhook_id} for {et}/{entity_id} deferred "
                    f"({', '.join(reasons)}). Retry {current + 1}/{MAX_WAIT_RETRIES} "
                    f"in {WAIT_DELAY_MS}ms."
                )
                return

            # Cap reached — log and proceed with whatever is enriched.
            logger.warning(
                f"Outbound webhook {webhook_id} for {et}/{entity_id} reached "
                f"MAX_WAIT_RETRIES ({MAX_WAIT_RETRIES}); firing with current state."
            )
        # Clear counter on successful pass-through.
        try:
            redis.delete(wait_counter_key)
        except Exception:
            pass
    except Exception as e:
        # Pre-flight failure shouldn't block the webhook — log and proceed.
        logger.warning(f"outbound webhook pre-flight check failed: {e}")
        
    last_ts = float(last_run_str)
    now_ts = datetime.now(timezone.utc).timestamp()
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, url, debounce_ms, conditions, payload_mode, include_latest_memory,
                   payload_interaction_types
            FROM memory_outbound_webhooks WHERE id = %s
        """, (webhook_id,))
        wh = cursor.fetchone()
        
    if not wh:
        return
        
    debounce_s = (wh["debounce_ms"] or 60000) / 1000.0
    elapsed_s = now_ts - last_ts
    
    # If a newer message was routed, elapsed_s will be less than the delay 
    # (plus a minor buffer for timing issues). 
    # Let that newer job handle it later.
    if elapsed_s < (debounce_s - 2.0):
        logger.info(f"Outbound Webhook {wh['name']} dropped because a newer message arrived.")
        return

    # Delete the debounce key so a new block can start
    redis.delete(debounce_key)

    # Compile the final payload
    payload_mode = wh["payload_mode"] or "trigger_only"
    conditions = wh["conditions"] or {}
    if isinstance(conditions, str):
        try:
            conditions = json.loads(conditions)
        except:
            conditions = {}

    # Payload-level interaction-type allowlist applied to BOTH the interactions
    # array and the intelligence/memories blocks below. NULL/empty = no filter
    # (include all types — backward compatible).
    payload_type_filter = wh.get("payload_interaction_types")
    if isinstance(payload_type_filter, str):
        try:
            payload_type_filter = json.loads(payload_type_filter)
        except:
            payload_type_filter = None
    if not payload_type_filter:
        payload_type_filter = None
        
    with get_memory_db_context() as conn:
        cursor = conn.cursor()

        # Step 1: Check for NEW triggering interactions (matching conditions, not yet fired)
        trigger_query = """
            SELECT id, primary_entity_type
            FROM interactions
            WHERE primary_entity_id = %s
              AND status = 'pending'
              AND is_enriched = TRUE
              AND NOT (%s = ANY(outbound_webhooks_fired))
        """
        trigger_params = [entity_id, webhook_id]

        if conditions:
            for key, value in conditions.items():
                if isinstance(value, list):
                    trigger_query += f" AND {key} = ANY(%s)"
                    trigger_params.append(value)
                else:
                    trigger_query += f" AND {key} = %s"
                    trigger_params.append(value)

        cursor.execute(trigger_query, trigger_params)
        trigger_rows = cursor.fetchall()

        if not trigger_rows:
            logger.info("Outbound Webhook executed but no matching enriched interactions found.")
            return

        # Resolve entity_type and collect IDs to flag as fired
        entity_type = trigger_rows[0]["primary_entity_type"]
        trigger_ids = [str(r["id"]) for r in trigger_rows]

        # Step 2: Fetch the payload's interactions.
        #   - payload_mode == "all_window": all interactions for this entity that are
        #     either still pending OR were recently processed (within 2x debounce window).
        #     This catches interactions marked 'done' by memory generation during the
        #     debounce period while excluding stale historical data.
        #   - payload_mode == "trigger_only": only the interactions matching the
        #     webhook's trigger conditions.
        debounce_window_s = debounce_s * 2 + 60  # generous buffer
        step2_query = f"""
            SELECT id, interaction_type, content, metadata, timestamp, source, is_enriched
            FROM interactions
            WHERE primary_entity_type = %s AND primary_entity_id = %s
              AND (status = 'pending' OR timestamp > NOW() - INTERVAL '{int(debounce_window_s)} seconds')
        """
        step2_params: list = [entity_type, entity_id]

        if payload_mode == "trigger_only" and conditions:
            for key, value in conditions.items():
                if isinstance(value, list):
                    step2_query += f" AND {key} = ANY(%s)"
                    step2_params.append(value)
                else:
                    step2_query += f" AND {key} = %s"
                    step2_params.append(value)

        # Apply payload-level interaction-type filter (separate from trigger
        # conditions). When set, narrows the bundled interactions to the listed
        # types regardless of payload_mode. Mode flips between include/exclude.
        if payload_type_filter:
            mode = wh.get("payload_interaction_types_mode", "include")
            if mode == "exclude":
                step2_query += " AND interaction_type != ALL(%s)"
            else:
                step2_query += " AND interaction_type = ANY(%s)"
            step2_params.append(payload_type_filter)

        step2_query += " ORDER BY timestamp ASC"
        wh_mode = wh.get("payload_interaction_types_mode", "include")
        logger.info(f"[WEBHOOK_DEBUG] step2 query: {step2_query}")
        logger.info(f"[WEBHOOK_DEBUG] step2 params: entity_type={entity_type}, entity_id={entity_id}, payload_type_filter={payload_type_filter}, mode={wh_mode}")
        cursor.execute(step2_query, step2_params)

        interaction_payload = []
        for i in cursor.fetchall():
            interaction_payload.append({
                "id": i["id"],
                "interaction_type": i["interaction_type"],
                "content": i["content"],
                "metadata": i["metadata"],
                "timestamp": str(i["timestamp"]),
                "source": i["source"],
                "is_enriched": i["is_enriched"],
            })

        # ── Entity context: full memory tiers for the entity ──────────────────
        intelligence_payload = []
        memories_payload = []

        if wh["include_latest_memory"]:
            # All intelligence for this entity
            cursor.execute("""
                SELECT id, knowledge_type, name, content, summary, status, created_at
                FROM intelligence
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                ORDER BY created_at ASC
            """, (entity_type, entity_id))
            for row in cursor.fetchall():
                intelligence_payload.append({
                    "id": row["id"],
                    "knowledge_type": row["knowledge_type"],
                    "name": row["name"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "status": row["status"],
                    "created_at": str(row["created_at"])
                })

            # All memories for this entity (compacted flag included so consumers
            # can distinguish frontier from rolled-up daily summaries).
            cursor.execute("""
                SELECT id, date, content_summary, related_entities, intents, compacted
                FROM memories
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                ORDER BY date ASC
            """, (entity_type, entity_id))
            for row in cursor.fetchall():
                memories_payload.append({
                    "id": row["id"],
                    "date": str(row["date"]),
                    "content_summary": row["content_summary"],
                    "related_entities": row["related_entities"],
                    "intents": row["intents"],
                    "compacted": row["compacted"]
                })

    # NOTE: outbound_webhooks_fired is set only AFTER a successful POST, below.
    # This prevents silent data loss when the receiver (e.g., n8n) is down,
    # at the cost of possibly re-firing on the next legitimate trigger if a
    # POST completes but the response is lost (n8n side should be idempotent
    # or tolerant of this edge case).

    final_payload = {
        "webhook_id": webhook_id,
        "webhook_name": wh["name"],
        "entity_type": entity_type,
        "entity_id": entity_id,
        "interactions": interaction_payload,
        "intelligence": intelligence_payload,
        "memories": memories_payload,
    }

    # Duplicate-interaction watch: log a WARNING if the assembled payload
    # contains repeated ids, or near-simultaneous repeats of
    # (content, interaction_type, source). Set up to catch a previously-reported
    # duplicate-payload incident the next time it reproduces.
    _log_duplicate_interactions(wh["name"], entity_id, interaction_payload)

    post_succeeded = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(wh["url"], json=final_payload, timeout=300.0)
            if resp.status_code >= 400:
                logger.warning(f"Outbound webhook returned status: {resp.status_code} ({resp.text})")
            else:
                post_succeeded = True
                logger.info(f"Successfully posted {len(interaction_payload)} interactions + {len(intelligence_payload)} intelligence + {len(memories_payload)} memories to {wh['url']}")
    except Exception as e:
        logger.error(f"Failed to post to outbound webhook {wh['name']}: {e}")

    if not post_succeeded:
        # Leave outbound_webhooks_fired unchanged. The next triggering message
        # will re-bundle these interactions and try again. No retry storm here:
        # only a new triggering message restarts the debounce window.
        logger.warning(
            f"Outbound webhook {wh['name']} not marked as fired for "
            f"{len(trigger_ids)} interactions (will retry on next trigger)."
        )
        return

    # Mark only the triggering interactions as fired (not the context ones).
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE interactions
            SET outbound_webhooks_fired = array_append(outbound_webhooks_fired, %s)
            WHERE id = ANY(%s)
        """, (webhook_id, trigger_ids))
        conn.commit()


def _log_duplicate_interactions(webhook_name: str, entity_id: str, payload: list) -> None:
    """Detection-only: log duplicates so we can investigate a reported but
    unreproduced bug. Two checks:
      1. repeated `id` (shouldn't happen — would indicate a SQL/code bug)
      2. repeated `(content, interaction_type, source)` within a 5-second window
         (would indicate upstream double-ingest)
    """
    seen_ids: dict = {}
    dup_ids: list = []
    for i in payload:
        iid = i.get("id")
        if iid in seen_ids:
            dup_ids.append(iid)
        else:
            seen_ids[iid] = True
    if dup_ids:
        logger.warning(
            f"[OUTBOUND_DUP_WATCH] webhook={webhook_name} entity={entity_id} "
            f"repeated_ids={dup_ids}"
        )

    # Near-simultaneous content repeats: bucket by (content, interaction_type, source)
    # and report any pair whose timestamps are within 5 seconds.
    buckets: dict = defaultdict(list)
    for i in payload:
        key = (i.get("content"), i.get("interaction_type"), i.get("source"))
        buckets[key].append((i.get("id"), i.get("timestamp")))
    for key, occurrences in buckets.items():
        if len(occurrences) < 2:
            continue
        parsed: list = []
        for iid, ts in occurrences:
            try:
                parsed.append((iid, datetime.fromisoformat(str(ts).replace("Z", "+00:00").split("+")[0])))
            except Exception:
                parsed.append((iid, None))
        parsed.sort(key=lambda x: x[1] or datetime.min)
        for a, b in zip(parsed, parsed[1:]):
            if a[1] is None or b[1] is None:
                continue
            delta = abs((b[1] - a[1]).total_seconds())
            if delta <= 5.0:
                logger.warning(
                    f"[OUTBOUND_DUP_WATCH] webhook={webhook_name} entity={entity_id} "
                    f"near-duplicate content ids=({a[0]}, {b[0]}) "
                    f"delta_seconds={delta:.3f} type={key[1]} source={key[2]}"
                )
