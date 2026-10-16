"""TASK-260 — pure threshold/pricing math behind the LLM budget caps.

No database: these pin the classification and cost formulas that gate every
LLM call. The DB-backed enforcement path (check_budget / active_budget_block)
fails open on DB errors by design; the math here is what must not drift.
"""
from datetime import datetime, timezone

from services.budget import (
    WARN_RATIO,
    BudgetExceededError,
    _period_bounds,
    compute_cost,
    threshold_state,
)


def test_compute_cost_applies_per_million_prices():
    config = {"extra_config": {"price_prompt_usd_per_m": 3.0,
                               "price_completion_usd_per_m": 15.0}}
    cost, pt, ct = compute_cost(config, {"prompt_tokens": 1_000_000,
                                         "completion_tokens": 100_000})
    assert (pt, ct) == (1_000_000, 100_000)
    assert abs(cost - (3.0 + 1.5)) < 1e-9


def test_compute_cost_unpriced_model_records_tokens_at_zero():
    cost, pt, ct = compute_cost({}, {"prompt_tokens": 500, "completion_tokens": 100})
    assert (cost, pt, ct) == (0.0, 500, 100)


def test_compute_cost_tolerates_malformed_usage():
    cost, pt, ct = compute_cost({"extra_config": {"price_prompt_usd_per_m": "abc"}},
                                {"prompt_tokens": "x", "completion_tokens": None})
    assert (cost, pt, ct) == (0.0, 0, 0)


def test_threshold_state_uncapped_is_ok():
    assert threshold_state(9_999.0, 9_999.0, 0.0, 0.0) == ("ok", None, None)


def test_threshold_state_under_warn_ratio_is_ok():
    state, scope, ratio = threshold_state(0.79, 0.0, 1.0, 0.0)
    assert state == "ok" and scope is None and ratio is None


def test_threshold_state_warning_at_80_percent():
    state, scope, ratio = threshold_state(WARN_RATIO, 0.0, 1.0, 0.0)
    assert state == "warning" and scope == "daily"
    assert ratio is not None and abs(ratio - WARN_RATIO) < 1e-9


def test_threshold_state_blocked_at_cap():
    state, scope, _ = threshold_state(1.0, 0.0, 1.0, 0.0)
    assert state == "blocked" and scope == "daily"


def test_threshold_state_monthly_wins_over_daily():
    # Both breached: the wider period is the harder constraint.
    state, scope, _ = threshold_state(2.0, 20.0, 1.0, 10.0)
    assert state == "blocked" and scope == "monthly"


def test_threshold_state_monthly_warning_survives_daily_ok():
    state, scope, ratio = threshold_state(0.1, 9.0, 1.0, 10.0)
    assert state == "warning" and scope == "monthly"


def test_budget_error_carries_provider_stop_shape():
    err = BudgetExceededError("daily", 1.5, 1.0)
    assert err.code == "llm_budget_exceeded"
    assert err.scope == "daily"
    assert err.spent == 1.5 and err.cap == 1.0
    assert "daily" in str(err)


def test_period_bounds_are_utc_day_and_month_start():
    now = datetime(2026, 10, 16, 18, 45, 30, tzinfo=timezone.utc)
    day_start, month_start = _period_bounds(now)
    assert day_start == datetime(2026, 10, 16, 0, 0, tzinfo=timezone.utc)
    assert month_start == datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
