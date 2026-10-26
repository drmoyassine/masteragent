"""
test_learning_loop.py — Knowledge learning loop (docs/plans/knowledge-learning-loop.md)

Covers:
  - settings: the nine learning-loop keys exposed with spec defaults
  - usage capture: fulltext search + get-context write events (capped, ranked,
    usage_count bumped); capture flag off = no events
  - attribution: lessons_learned echo → failure, confirmed recurrence →
    success, else no_signal; idempotent via the attributed_at cursor;
    counter deltas compose + quality recompute runs
  - retrieval blend: w=0 pins existing ordering exactly (the phase-0 pin);
    w>0 reorders near-equivalent records (search helpers, unit-level — the
    endpoint needs a live embedding provider, the helper does not)
  - retirement candidates: old + never-served + low-quality active rows only
  - admin routes: trigger enqueues; retirement-candidates endpoint responds

Seeding goes through core.storage directly (the hermetic suite runs the real
app in-process against throwaway Postgres; these tests share that DB).
Attribution runs via run_outcome_attribution directly — the BullMQ worker
does not drain queued jobs inside the hermetic harness, and the job body is
pure SQL anyway.
"""
import asyncio
import uuid

import pytest

from core.storage import get_memory_db_context
from memory_system.maintain.consolidation_service import find_retirement_candidates
from memory_system.maintain.learning import run_outcome_attribution
from services.search import search_knowledge_by_vector

ENTITY_TYPE, ENTITY_ID = "student", "lltest-entity"
EMB_DIM = 8


# ── Seed helpers ──────────────────────────────────────────────────────────────

def _seed_knowledge(*, name, category="best_practices", status="active", signals=(),
                    quality=None, embedding=None, age_days=0, usage_count=0,
                    source_intelligence_ids=()):
    kid = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO knowledge (id, seq_id, name, content, summary, category, status,
                                   visibility, signals, quality_score, embedding,
                                   source_intelligence_ids, metadata, usage_count,
                                   created_at, updated_at)
            VALUES (%s, (SELECT COALESCE(MAX(seq_id), 0) + 1 FROM knowledge), %s, %s, %s,
                    %s, %s, 'shared', %s, %s, %s, %s, '{}', %s,
                    NOW() - make_interval(days => %s), NOW())
            """,
            (kid, name, f"{name} — test content for lltest queries",
             f"{name} summary", category, status, list(signals), quality,
             embedding, list(source_intelligence_ids), usage_count, age_days),
        )
    return kid


def _seed_event(kid, *, entity_id=ENTITY_ID, age_hours=24, outcome=None):
    eid = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO knowledge_usage_events (id, knowledge_id, entity_type, entity_id,
                                                pathway, created_at)
            VALUES (%s, %s, %s, %s, 'get_context', NOW() - make_interval(hours => %s))
            """,
            (eid, kid, ENTITY_TYPE, entity_id, age_hours),
        )
        if outcome is not None:
            cur.execute(
                "UPDATE knowledge_usage_events SET outcome = %s, attributed_at = NOW() WHERE id = %s",
                (outcome, eid),
            )
    return eid


def _seed_intelligence(*, entity_id=ENTITY_ID, age_hours=23):
    iid = str(uuid.uuid4())
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO intelligence (id, seq_id, primary_entity_type, primary_entity_id,
                                      name, content, status, created_at)
            VALUES (%s, (SELECT COALESCE(MAX(seq_id), 0) + 1 FROM intelligence), %s, %s,
                    %s, %s, 'confirmed', NOW() - make_interval(hours => %s))
            """,
            (iid, ENTITY_TYPE, entity_id, "LLTEST-echo-intelligence", "echo evidence", age_hours),
        )
    return iid


def _events():
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT knowledge_id, pathway, entity_id, rank, outcome, attributed_at, created_at
            FROM knowledge_usage_events ORDER BY created_at DESC, rank
        """)
        return [dict(r) for r in cur.fetchall()]


def _knowledge_row(kid):
    with get_memory_db_context() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT usage_count, success_count, failure_count, quality_score
            FROM knowledge WHERE id = %s
        """, (kid,))
        return dict(cur.fetchone())


def _set(admin, base_url, **kv):
    r = admin.put(f"{base_url}/api/memory/config/settings", json=kv)
    assert r.status_code == 200, r.text


# ── Environment fixture ───────────────────────────────────────────────────────

@pytest.fixture()
def loop_env(admin, base_url):
    """Clean learning-loop tables around each test; restore touched settings."""
    def _clean():
        with get_memory_db_context() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM knowledge_usage_events")
            cur.execute("DELETE FROM knowledge WHERE name LIKE 'LLTEST-%'")
            cur.execute("DELETE FROM intelligence WHERE name LIKE 'LLTEST-%'")
    _clean()
    yield base_url
    _set(admin, base_url,
         knowledge_learning_usage_capture=True,
         knowledge_learning_max_events_per_call=50,
         knowledge_retrieval_quality_weight=0.0)
    _clean()


# ── Settings ──────────────────────────────────────────────────────────────────

def test_settings_defaults_exposed(admin, base_url):
    r = admin.get(f"{base_url}/api/memory/config/settings")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["knowledge_learning_usage_capture"] is True
    assert s["knowledge_learning_max_events_per_call"] == 50
    assert s["knowledge_learning_attribution_enabled"] is True
    assert s["knowledge_learning_negative_window_days"] == 7
    assert s["knowledge_learning_negative_similarity"] == 0.80
    assert s["knowledge_learning_min_signal_age_hours"] == 6
    assert s["knowledge_learning_retire_after_days"] == 90
    assert s["knowledge_learning_refine_min_failures"] == 2
    assert s["knowledge_retrieval_quality_weight"] == 0.0


# ── Usage capture ─────────────────────────────────────────────────────────────

def test_fulltext_capture_capped_and_ranked(agent, admin, loop_env):
    for suffix in ("alpha", "beta", "gamma"):
        _seed_knowledge(name=f"LLTEST-{suffix}")
    _set(admin, loop_env, knowledge_learning_max_events_per_call=2)

    r = agent.post(f"{loop_env}/api/memory/search/fulltext",
                   json={"query": "lltest", "layers": ["knowledge"]})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 3

    events = _events()
    assert len(events) == 2, "cap must bound events even when more rows served"
    assert {e["rank"] for e in events} == {1, 2}
    assert all(e["pathway"] == "fulltext_search" for e in events)
    counts = sum(_knowledge_row(e["knowledge_id"])["usage_count"] for e in events)
    assert counts == 2


def test_get_context_capture(loop_env, agent):
    kid = _seed_knowledge(name="LLTEST-context")

    r = agent.get(f"{loop_env}/api/memory/get-context",
                  params={"entity_type": ENTITY_TYPE, "entity_id": ENTITY_ID})
    assert r.status_code == 200, r.text

    # The knowledge tier may carry bootstrap rows too — capture mirrors exactly
    # what was served, so assert on OUR row's event, not on a total count.
    mine = [e for e in _events() if e["knowledge_id"] == kid]
    assert len(mine) == 1
    assert mine[0]["pathway"] == "get_context"
    assert mine[0]["entity_id"] == ENTITY_ID
    assert _knowledge_row(kid)["usage_count"] == 1


def test_capture_flag_off_disables(agent, admin, loop_env):
    _seed_knowledge(name="LLTEST-muted")
    _set(admin, loop_env, knowledge_learning_usage_capture=False)

    r = agent.post(f"{loop_env}/api/memory/search/fulltext",
                   json={"query": "lltest", "layers": ["knowledge"]})
    assert r.status_code == 200
    assert _events() == []


# ── Outcome attribution ───────────────────────────────────────────────────────

def test_attribution_no_signal_and_idempotent(loop_env):
    kid = _seed_knowledge(name="LLTEST-quiet")
    _seed_event(kid, age_hours=24)

    out = run_outcome_attribution(trigger="test")
    assert out["events_seen"] == 1
    assert out["outcomes"] == {"no_signal": 1}

    ev = _events()[0]
    assert ev["outcome"] == "no_signal"
    assert ev["attributed_at"] is not None
    row = _knowledge_row(kid)
    assert row["success_count"] == 0 and row["failure_count"] == 0

    # Idempotent: the attributed_at cursor means a re-run resumes at zero.
    again = run_outcome_attribution(trigger="test")
    assert again["events_seen"] == 0


def test_attribution_lessons_learned_echo_failure(loop_env):
    kid = _seed_knowledge(name="LLTEST-guide", signals=["visa"])
    # Event first: the echo lesson must become active strictly AFTER the
    # retrieval it contradicts (created_at ordering is the signal).
    _seed_event(kid, age_hours=24)
    iid = _seed_intelligence(age_hours=23)
    _seed_knowledge(name="LLTEST-echo-lesson", category="lessons_learned",
                    signals=["visa"], source_intelligence_ids=[iid], age_days=0)

    out = run_outcome_attribution(trigger="test")
    assert out["outcomes"].get("failure") == 1

    ev = _events()[0]
    assert ev["outcome"] == "failure"
    row = _knowledge_row(kid)
    assert row["failure_count"] == 1 and row["success_count"] == 0
    assert row["quality_score"] is not None, "quality recompute must run on touched records"


def test_attribution_recurrence_success(loop_env):
    kid = _seed_knowledge(name="LLTEST-recurring")
    _seed_event(kid, age_hours=240)   # 10 days ago
    _seed_event(kid, age_hours=24)    # re-retrieved 9 days later

    out = run_outcome_attribution(trigger="test")
    assert out["outcomes"].get("success") == 1
    assert out["outcomes"].get("no_signal") == 1

    outcomes = {e["outcome"] for e in _events()}
    assert outcomes == {"success", "no_signal"}
    row = _knowledge_row(kid)
    assert row["success_count"] == 1 and row["failure_count"] == 0


def test_attribution_disabled_flag(loop_env, admin):
    _set(admin, loop_env, knowledge_learning_attribution_enabled=False)
    kid = _seed_knowledge(name="LLTEST-disabled")
    _seed_event(kid, age_hours=24)

    out = run_outcome_attribution(trigger="test")
    assert out["status"] == "disabled"
    assert _events()[0]["outcome"] is None, "disabled run must not touch events"


# ── Retrieval quality blend ───────────────────────────────────────────────────

# q ≈ [1,0,...]; k1 at cosine 0.80 (no quality), k2 at cosine 0.75 (quality 1.0).
# w=0 → k1 first. w=0.2 → k1 0.90 vs k2 0.95 → k2 first (near-equivalent flip).
_K1 = [0.8, 0.6] + [0.0] * (EMB_DIM - 2)
_K2 = [0.75, 0.6614378277661484] + [0.0] * (EMB_DIM - 2)
_Q = [1.0] + [0.0] * (EMB_DIM - 1)


def test_blend_zero_pins_existing_order(loop_env):
    _seed_knowledge(name="LLTEST-sim-top", embedding=_K1, quality=None)
    _seed_knowledge(name="LLTEST-quality-but-farther", embedding=_K2, quality=1.0)

    hits = asyncio.run(search_knowledge_by_vector(_Q, limit=10))
    names = [h["name"] for h in hits if h["name"].startswith("LLTEST-")]
    assert names == ["LLTEST-sim-top", "LLTEST-quality-but-farther"], \
        "w=0 must preserve pure similarity order byte-for-byte"


def test_blend_positive_reorders_near_equivalent(loop_env, admin):
    _seed_knowledge(name="LLTEST-sim-top", embedding=_K1, quality=None)
    _seed_knowledge(name="LLTEST-quality-but-farther", embedding=_K2, quality=1.0)
    _set(admin, loop_env, knowledge_retrieval_quality_weight=0.2)


    hits = asyncio.run(search_knowledge_by_vector(_Q, limit=10))
    names = [h["name"] for h in hits if h["name"].startswith("LLTEST-")]
    assert names == ["LLTEST-quality-but-farther", "LLTEST-sim-top"]


# ── Retirement candidates ─────────────────────────────────────────────────────

def test_retirement_candidates_filter(loop_env):
    old_bad = _seed_knowledge(name="LLTEST-old-bad", age_days=120, quality=0.2)
    _seed_knowledge(name="LLTEST-fresh-bad", age_days=1, quality=0.2)
    _seed_knowledge(name="LLTEST-old-used", age_days=120, quality=0.2, usage_count=3)
    _seed_knowledge(name="LLTEST-old-good", age_days=120, quality=0.9)

    candidates = find_retirement_candidates()
    names = [c["name"] for c in candidates]
    assert names == ["LLTEST-old-bad"]
    assert candidates[0]["id"] == old_bad
    assert candidates[0]["usage_count"] == 0


# ── Admin routes ──────────────────────────────────────────────────────────────

def test_admin_trigger_and_retirement_endpoint(admin, loop_env):
    _seed_knowledge(name="LLTEST-old-bad", age_days=120, quality=0.2)

    r = admin.post(f"{loop_env}/api/memory/trigger/knowledge-outcome-attribution")
    assert r.status_code == 200, r.text
    assert "queued" in r.json()["message"].lower()

    r = admin.get(f"{loop_env}/api/memory/admin/retirement-candidates")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["candidates"], list)
    assert any(c["name"] == "LLTEST-old-bad" for c in body["candidates"])
