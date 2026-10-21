-- 006: per-webhook shared secret for vision completion webhooks (TASK-274).
--
-- fire_vision_completion_webhooks sends it as the X-Webhook-Secret header on
-- every delivery; receivers (e.g. the WhatsApp voice-transcript n8n flow)
-- reject POSTs whose header mismatches. Nullable — webhooks without a secret
-- keep working headerless, so this is additive with zero backfill.
ALTER TABLE public.vision_completion_webhooks
    ADD COLUMN IF NOT EXISTS secret TEXT;
