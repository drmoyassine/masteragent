"""TASK-260 — alert delivery wiring.

Regression: the scheduler awaits poll_alert_delivery inline, so it must be
awaitable — a plain sync call there raised `await None` → TypeError, which
killed the background loop on its first tick (health flipped to
"scheduler: stale" ~2 min after every boot). It must also never block the
event loop while the webhook POSTs run.
"""
import asyncio
import inspect

import services.alert_delivery as ad


def test_poll_alert_delivery_is_coroutine_and_completes(monkeypatch):
    # The scheduler does `await poll_alert_delivery()` — a sync function here
    # is an immediate TypeError on the first tick.
    assert inspect.iscoroutinefunction(ad.poll_alert_delivery)

    monkeypatch.setattr(ad, "scan_pipeline_failures", lambda: None)
    monkeypatch.setattr(ad, "deliver_pending_alerts", lambda: 0)
    # No ALERT_WEBHOOK_URL, no DB — must complete without raising or hanging.
    asyncio.run(ad.poll_alert_delivery())


def test_delivery_noops_without_webhook_url(monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert ad._webhook_url() == ""
    # With no URL configured the delivery pass is a cheap no-op.
    assert ad.deliver_pending_alerts() == 0


def test_window_seconds_floor_and_default(monkeypatch):
    monkeypatch.delenv("ALERT_DELIVERY_WINDOW_SECONDS", raising=False)
    assert ad._window_seconds() == 900  # default
    monkeypatch.setenv("ALERT_DELIVERY_WINDOW_SECONDS", "10")
    assert ad._window_seconds() == 60  # floored — no sub-minute re-page storms
    monkeypatch.setenv("ALERT_DELIVERY_WINDOW_SECONDS", "not-a-number")
    assert ad._window_seconds() == 900  # garbage falls back to the default
