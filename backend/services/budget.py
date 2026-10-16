"""TASK-260 — LLM budget caps enforced at the LLM call boundary.

Daily/monthly USD caps live on memory_settings (llm_daily_budget_usd /
llm_monthly_budget_usd; 0 = no cap). Spend is SUM(llm_spend_ledger.cost_usd)
— one row per real LLM call, written by services/llm.py from the provider
response's usage block. Per-model prices live in the LLM config's
extra_config as ``price_prompt_usd_per_m`` / ``price_completion_usd_per_m``;
models without a price record tokens but cost 0, so caps bind only where
prices are configured — these are estimates, not bills.

Crossing thresholds upserts memory_system_alerts rows (80% warning, 100%
block) that the services/alert_delivery.py poller forwards to the owner
channel. Recovery (period rollover, budget raise, price configured) flips
them inactive and lifts the block: the block is computed from spend, never
persisted as state, so it self-heals on the next check.

DB failures fail OPEN (no cap): a broken settings read must not halt all AI
work — provider hard-stops (credits exhausted) cover that case already.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

WARN_RATIO = 0.8

BUDGET_WARNING_CODE = "llm_budget_warning"
BUDGET_BLOCK_CODE = "llm_budget_exceeded"

# Alert upserts only write on a FALSE→TRUE transition (WHERE ... active=FALSE),
# so a steadily-active alert does not bump last_seen_at — bumping it would make
# the delivery poller re-send every window instead of once per incident.
_WARNING_UPSERT = """
    INSERT INTO memory_system_alerts
        (code, severity, title, message, source, detail, active, first_seen_at, last_seen_at)
    VALUES ('llm_budget_warning', 'warning',
            'LLM spend at 80% of budget', %s, 'budget', %s::jsonb, TRUE, NOW(), NOW())
    ON CONFLICT (code) DO UPDATE SET
        active=TRUE, message=EXCLUDED.message, detail=EXCLUDED.detail, last_seen_at=NOW()
    WHERE memory_system_alerts.active = FALSE
"""

_BLOCK_UPSERT = """
    INSERT INTO memory_system_alerts
        (code, severity, title, message, source, detail, active, first_seen_at, last_seen_at)
    VALUES ('llm_budget_exceeded', 'error',
            'LLM budget exceeded — AI work blocked', %s, 'budget', %s::jsonb, TRUE, NOW(), NOW())
    ON CONFLICT (code) DO UPDATE SET
        active=TRUE, message=EXCLUDED.message, detail=EXCLUDED.detail, last_seen_at=NOW()
    WHERE memory_system_alerts.active = FALSE
"""

_DEACTIVATE = """
    UPDATE memory_system_alerts SET active=FALSE
    WHERE code=%s AND active=TRUE
"""


class BudgetExceededError(RuntimeError):
    """Typed budget block — same contract shape as ProviderStopError so queue
    gates and pipeline logging treat it uniformly."""

    def __init__(self, scope: str, spent: float, cap: float):
        self.code = BUDGET_BLOCK_CODE
        self.scope = scope  # 'daily' | 'monthly'
        self.spent = spent
        self.cap = cap
        super().__init__(
            f"LLM {scope} budget exceeded: ${spent:.4f} spent of ${cap:.2f} cap"
        )


def _price(config: dict, key: str) -> float:
    extra = (config or {}).get("extra_config") or {}
    try:
        return float(extra.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def compute_cost(config: dict, usage: Optional[dict]) -> Tuple[float, int, int]:
    """(cost_usd, prompt_tokens, completion_tokens) from a response usage block.

    Unpriced models cost 0.0 but still record their tokens, so a retroactive
    price backfill works off the ledger."""
    usage = usage or {}
    try:
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        pt = ct = 0
    pp = _price(config, "price_prompt_usd_per_m")
    cp = _price(config, "price_completion_usd_per_m")
    cost = (pt * pp + ct * cp) / 1_000_000.0
    return cost, pt, ct


def _cap(settings: dict, key: str) -> float:
    try:
        return max(0.0, float(settings.get(key) or 0))
    except (TypeError, ValueError):
        return 0.0


def threshold_state(
    daily_spent: float,
    monthly_spent: float,
    daily_cap: float,
    monthly_cap: float,
) -> Tuple[str, Optional[str], Optional[float]]:
    """(state, worst_scope, worst_ratio) — pure threshold math.

    state is 'blocked' | 'warning' | 'ok'. monthly wins over daily when both
    are breached (the wider period is the harder constraint)."""
    worst_ratio = 0.0
    worst_scope = None
    state = "ok"
    for scope, spent, cap in (("monthly", monthly_spent, monthly_cap),
                              ("daily", daily_spent, daily_cap)):
        if cap <= 0:
            continue
        ratio = spent / cap
        if ratio >= 1.0:
            return "blocked", scope, ratio
        if ratio >= WARN_RATIO:
            state = "warning"
            if ratio > worst_ratio:
                worst_ratio, worst_scope = ratio, scope
    return state, worst_scope, worst_ratio if state == "warning" else None


def _period_bounds(now: datetime) -> Tuple[datetime, datetime]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    return day_start, month_start


def _spend_and_sync() -> Tuple[dict, float, float]:
    """Read caps + spend in one connection and sync the budget alert rows.

    Returns ({settings}, daily_spent, monthly_spent). DB failure raises —
    callers decide fail-open vs fail-closed."""
    from core.storage import get_memory_db_context

    now = datetime.now(timezone.utc)
    day_start, month_start = _period_bounds(now)
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_settings WHERE id = 1")
        row = cursor.fetchone()
        settings = dict(row) if row else {}
        daily_cap = _cap(settings, "llm_daily_budget_usd")
        monthly_cap = _cap(settings, "llm_monthly_budget_usd")

        if daily_cap <= 0 and monthly_cap <= 0:
            # No caps configured: nothing to enforce, and any stale budget
            # alerts from before a cap was cleared must not stay active.
            cursor.execute(_DEACTIVATE, (BUDGET_WARNING_CODE,))
            cursor.execute(_DEACTIVATE, (BUDGET_BLOCK_CODE,))
            return settings, 0.0, 0.0

        cursor.execute(
            """
            SELECT COALESCE(SUM(cost_usd) FILTER (WHERE called_at >= %s), 0) AS daily,
                   COALESCE(SUM(cost_usd), 0) AS monthly
            FROM llm_spend_ledger
            WHERE called_at >= %s
            """,
            (day_start, month_start),
        )
        sums = cursor.fetchone()
        daily_spent = float(sums["daily"] or 0)
        monthly_spent = float(sums["monthly"] or 0)

        state, scope, ratio = threshold_state(daily_spent, monthly_spent, daily_cap, monthly_cap)
        if state == "blocked":
            cap = daily_cap if scope == "daily" else monthly_cap
            spent = daily_spent if scope == "daily" else monthly_spent
            message = f"LLM {scope} budget exceeded: ${spent:.4f} of ${cap:.2f} cap — AI work blocked until the period resets or the cap is raised"
            detail = f'{{"scope": "{scope}", "spent_usd": {spent:.6f}, "cap_usd": {cap:.2f}}}'
            cursor.execute(_BLOCK_UPSERT, (message, detail))
        else:
            cursor.execute(_DEACTIVATE, (BUDGET_BLOCK_CODE,))
        if state == "warning":
            cap = daily_cap if scope == "daily" else monthly_cap
            spent = daily_spent if scope == "daily" else monthly_spent
            message = f"LLM {scope} spend at {ratio:.0%} of ${cap:.2f} budget (${spent:.4f})"
            detail = f'{{"scope": "{scope}", "spent_usd": {spent:.6f}, "cap_usd": {cap:.2f}, "ratio": {ratio:.4f}}}'
            cursor.execute(_WARNING_UPSERT, (message, detail))
        else:
            cursor.execute(_DEACTIVATE, (BUDGET_WARNING_CODE,))
        return settings, daily_spent, monthly_spent


def check_budget(task_type: str) -> None:
    """Raise BudgetExceededError when a cap is breached; sync alert rows.

    Raises nothing but BudgetExceededError — DB failures fail open (logged)."""
    try:
        settings, daily_spent, monthly_spent = _spend_and_sync()
    except Exception as exc:
        logger.warning("Budget check unavailable for %s (failing open): %s", task_type, exc)
        return
    state, scope, _ = threshold_state(
        daily_spent, monthly_spent,
        _cap(settings, "llm_daily_budget_usd"), _cap(settings, "llm_monthly_budget_usd"),
    )
    if state == "blocked":
        scope = scope or "daily"
        cap = _cap(settings, "llm_daily_budget_usd") if scope == "daily" else _cap(settings, "llm_monthly_budget_usd")
        spent = daily_spent if scope == "daily" else monthly_spent
        raise BudgetExceededError(scope, spent, cap)


def active_budget_block() -> Optional[dict]:
    """Queue-gate mirror of job_safety.active_provider_stop(): the current
    budget block, or None. Syncs the block alert row when it fires."""
    try:
        settings, daily_spent, monthly_spent = _spend_and_sync()
    except Exception as exc:
        logger.warning("Budget block check unavailable (failing open): %s", exc)
        return None
    state, scope, _ = threshold_state(
        daily_spent, monthly_spent,
        _cap(settings, "llm_daily_budget_usd"), _cap(settings, "llm_monthly_budget_usd"),
    )
    if state != "blocked":
        return None
    scope = scope or "daily"
    cap = _cap(settings, "llm_daily_budget_usd") if scope == "daily" else _cap(settings, "llm_monthly_budget_usd")
    spent = daily_spent if scope == "daily" else monthly_spent
    return {
        "code": BUDGET_BLOCK_CODE,
        "scope": scope,
        "message": f"LLM {scope} budget exceeded: ${spent:.4f} of ${cap:.2f} cap",
    }


def record_llm_usage(task_type: str, model: str, config: dict, usage: Optional[dict]) -> None:
    """Write one ledger row from a real provider usage block. Best-effort —
    accounting must never break the call it accounts for. Threshold alerts
    are synced by the next check_budget/active_budget_block call."""
    cost, pt, ct = compute_cost(config, usage)
    try:
        from core.storage import get_memory_db_context

        with get_memory_db_context() as conn:
            conn.cursor().execute(
                """
                INSERT INTO llm_spend_ledger
                    (called_at, task_type, model, prompt_tokens, completion_tokens, cost_usd)
                VALUES (NOW(), %s, %s, %s, %s, %s)
                """,
                (task_type, model, pt, ct, cost),
            )
    except Exception as exc:
        logger.warning("Could not record LLM usage (%s/%s): %s", task_type, model, exc)


def budget_status() -> dict:
    """Admin surface: current spend vs caps (GET /config/llm-budget)."""
    try:
        settings, daily_spent, monthly_spent = _spend_and_sync()
    except Exception as exc:
        logger.warning("Budget status unavailable: %s", exc)
        return {"available": False, "error": "budget state unavailable"}
    daily_cap = _cap(settings, "llm_daily_budget_usd")
    monthly_cap = _cap(settings, "llm_monthly_budget_usd")

    ledger = {"calls_today": 0, "unpriced_calls_today": 0}
    try:
        from core.storage import get_memory_db_context

        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) AS calls,
                       COUNT(*) FILTER (WHERE cost_usd = 0) AS unpriced
                FROM llm_spend_ledger
                WHERE called_at >= %s
                """,
                (_period_bounds(datetime.now(timezone.utc))[0],),
            )
            row = cursor.fetchone()
            ledger = {"calls_today": int(row["calls"] or 0),
                      "unpriced_calls_today": int(row["unpriced"] or 0)}
    except Exception as exc:
        logger.warning("Ledger counts unavailable: %s", exc)

    def _leg(spent: float, cap: float) -> dict:
        return {
            "cap_usd": cap,
            "spent_usd": round(spent, 6),
            "ratio": round(spent / cap, 4) if cap > 0 else None,
            "state": threshold_state(spent, 0, cap, 0)[0] if cap > 0 else "uncapped",
        }

    return {
        "available": True,
        "daily": _leg(daily_spent, daily_cap),
        "monthly": _leg(monthly_spent, monthly_cap),
        "ledger": ledger,
        "pricing_note": (
            "cost_usd is estimated from each LLM config's extra_config: "
            "price_prompt_usd_per_m / price_completion_usd_per_m (USD per "
            "1M tokens). Models without a price record tokens at cost 0 — "
            "configure prices for the caps to bind."
        ),
    }
