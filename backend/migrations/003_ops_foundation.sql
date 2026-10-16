-- TASK-260 — ops foundations: LLM budget caps, outbound alert delivery, spend ledger.
-- Applied by memory_system/store/migrations.py; schema-qualified because the
-- baseline pins search_path='' for the migration session.

-- Budget caps (USD; 0 = no cap) enforced in services/budget.py, and the
-- alert-delivery kill-switch consumed by services/alert_delivery.py.
ALTER TABLE public.memory_settings ADD COLUMN IF NOT EXISTS llm_daily_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE public.memory_settings ADD COLUMN IF NOT EXISTS llm_monthly_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE public.memory_settings ADD COLUMN IF NOT EXISTS alerts_delivery_enabled BOOLEAN NOT NULL DEFAULT TRUE;

-- Delivery watermark on alerts: the poller marks a POST as sent here and only
-- re-delivers when the alert re-fires (last_seen_at moves past delivered_at).
ALTER TABLE public.memory_system_alerts ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ;

-- Real per-call usage from provider responses (services/llm.py); the queue's
-- estimate_* planning numbers stay on memory_pipeline_runs. Per-model prices
-- live in each LLM config's extra_config — cost_usd is an estimate.
CREATE TABLE IF NOT EXISTS public.llm_spend_ledger (
    id BIGSERIAL PRIMARY KEY,
    called_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    task_type TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_llm_spend_ledger_called_at
    ON public.llm_spend_ledger (called_at);

-- Scanning watermarks, one row per scanner (e.g. pipeline-run failure watcher).
CREATE TABLE IF NOT EXISTS public.alert_delivery_state (
    watermark TEXT PRIMARY KEY,
    last_seen_id TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
