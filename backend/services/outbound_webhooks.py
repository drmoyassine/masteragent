import json
import logging
import asyncio
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
            # Refresh the Debian timer in Redis natively
            now_ts = datetime.now(timezone.utc).timestamp()
            redis.set(f"outbound_debounce:{webhook_id}:{interaction['primary_entity_id']}", str(now_ts), ex=debounce_ms * 2 // 1000)
            
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
        
    last_ts = float(last_run_str)
    now_ts = datetime.now(timezone.utc).timestamp()
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, url, debounce_ms, conditions, payload_mode, include_latest_memory
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

        # Step 2: Fetch ALL pending interactions for this entity (full conversation context)
        cursor.execute("""
            SELECT id, interaction_type, content, metadata, timestamp, source
            FROM interactions
            WHERE primary_entity_type = %s AND primary_entity_id = %s
              AND status = 'pending'
            ORDER BY timestamp ASC
        """, (entity_type, entity_id))

        interaction_payload = []
        for i in cursor.fetchall():
            interaction_payload.append({
                "id": i["id"],
                "interaction_type": i["interaction_type"],
                "content": i["content"],
                "metadata": i["metadata"],
                "timestamp": str(i["timestamp"]),
                "source": i["source"]
            })

        # ── Entity context: the "uncondensed frontier" ──────────────────
        intelligence_payload = []
        uncompacted_memories = []

        if wh["include_latest_memory"]:
            # All confirmed intelligence for this entity (condensed from older memories)
            cursor.execute("""
                SELECT id, knowledge_type, name, content, summary, created_at
                FROM intelligence
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                  AND status = 'confirmed'
                ORDER BY created_at ASC
            """, (entity_type, entity_id))
            for row in cursor.fetchall():
                intelligence_payload.append({
                    "id": row["id"],
                    "knowledge_type": row["knowledge_type"],
                    "name": row["name"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "created_at": str(row["created_at"])
                })

            # Uncompacted memories (not yet condensed into intelligence)
            cursor.execute("""
                SELECT id, date, content_summary, related_entities, intents
                FROM memories
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                  AND compacted = FALSE
                ORDER BY date ASC
            """, (entity_type, entity_id))
            for row in cursor.fetchall():
                uncompacted_memories.append({
                    "id": row["id"],
                    "date": str(row["date"]),
                    "content_summary": row["content_summary"],
                    "related_entities": row["related_entities"],
                    "intents": row["intents"]
                })

        # Flag only the triggering interactions as fired (not the context ones)
        cursor.execute("""
            UPDATE interactions 
            SET outbound_webhooks_fired = array_append(outbound_webhooks_fired, %s)
            WHERE id = ANY(%s)
        """, (webhook_id, trigger_ids))
        conn.commit()

    # Fire Webhook Payload
    final_payload = {
        "webhook_id": webhook_id,
        "webhook_name": wh["name"],
        "entity_type": entity_type,
        "entity_id": entity_id,
        "interactions": interaction_payload,
        "intelligence": intelligence_payload,
        "uncompacted_memories": uncompacted_memories,
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(wh["url"], json=final_payload, timeout=10.0)
            if resp.status_code >= 400:
                logger.warning(f"Outbound webhook returned status: {resp.status_code} ({resp.text})")
            else:
                logger.info(f"Successfully posted {len(interaction_payload)} interactions + {len(intelligence_payload)} intelligence + {len(uncompacted_memories)} memories to {wh['url']}")
    except Exception as e:
        logger.error(f"Failed to post to outbound webhook {wh['name']}: {e}")
