"""
conftest.py — Test fixtures for the MasterAgent backend suite (TASK-261).

Two modes:

  Hermetic (default) — boots the REAL app in-process: throwaway Postgres
  (pgvector) + Redis containers via testcontainers, migrations applied, admin
  seeded, served on an ephemeral local port by uvicorn (background tasks and
  BullMQ workers patched off — no scheduler loops, no async job execution).
  Deterministic and self-contained; needs Docker on the test machine.

  Live stack (opt-in) — set MEMORY_TEST_BASE_URL (e.g. http://localhost:8080)
  to test against an already-running deployment instead. Credentials come
  from MEMORY_TEST_EMAIL / MEMORY_TEST_PASSWORD (skipping on login failure,
  as before).

Environment:
    MEMORY_TEST_BASE_URL   — live-mode switch + backend URL
    MEMORY_TEST_DATABASE_URL / MEMORY_TEST_REDIS_URL — hermetic fast-path:
        reuse running Postgres/Redis instead of spinning testcontainers
    MEMORY_TEST_EMAIL      — admin email     (default: admin@masteragent.test)
    MEMORY_TEST_PASSWORD   — admin password  (default: generated per session)
    MEMORY_TEST_AGENT_KEY  — pre-existing agent API key (live-mode convenience)
"""
import os
import secrets
import socket
import threading
import time

import pytest
import requests

# ── Test identity (fixed before any module import reads the env) ─────────────
TEST_EMAIL = os.environ.get("MEMORY_TEST_EMAIL", "admin@masteragent.test")
TEST_PASSWORD = os.environ.get("MEMORY_TEST_PASSWORD") or secrets.token_hex(16)
os.environ.setdefault("MEMORY_TEST_EMAIL", TEST_EMAIL)
os.environ.setdefault("MEMORY_TEST_PASSWORD", TEST_PASSWORD)

PRESET_AGENT_KEY = os.environ.get("MEMORY_TEST_AGENT_KEY", "")
HERMETIC = not os.environ.get("MEMORY_TEST_BASE_URL")

# testcontainers' ryuk reaper sidecar races Docker Desktop's port publish on
# Windows ("port 8080 is not available"). Teardown is handled explicitly in
# _stop_hermetic_stack, so the reaper adds nothing here.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# ── Hermetic stack ───────────────────────────────────────────────────────────
_herm = {"server": None, "thread": None, "containers": [], "started": False}


def _reserve_port() -> socket.socket:
    """Bind an ephemeral port now so the URL is known at collection time;
    ownership passes to uvicorn (it closes the socket on shutdown)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    return sock


if HERMETIC:
    _herm["sock"] = _reserve_port()
    BASE_URL = f"http://127.0.0.1:{_herm['sock'].getsockname()[1]}"
else:
    BASE_URL = os.environ.get("MEMORY_TEST_BASE_URL", "http://localhost:8080").rstrip("/")


def _provision_datastores() -> None:
    """Throwaway Postgres (pgvector) + Redis, or the fast-path URLs."""
    fast_pg = os.environ.get("MEMORY_TEST_DATABASE_URL")
    fast_redis = os.environ.get("MEMORY_TEST_REDIS_URL")
    if fast_pg and fast_redis:
        os.environ.setdefault("POSTGRES_PASSWORD", "hermetic-fastpath")
        os.environ["DATABASE_URL"] = fast_pg
        os.environ["MEMORY_POSTGRES_URL"] = fast_pg
        os.environ["REDIS_URL"] = fast_redis
        return
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    pg = PostgresContainer("pgvector/pgvector:pg16").start()
    redis = RedisContainer("redis:7-alpine").start()
    _herm["containers"] = [pg, redis]
    pg_url = pg.get_connection_url().replace("+psycopg2", "")

    # 001_baseline.sql is a pg_dump with `ALTER TABLE ... OWNER TO postgres`
    # throughout; the container's superuser is `test`. Bootstrap the role so
    # the migrations run unmodified (migrations are forward-only and shared
    # with prod — never edited for tests).
    import psycopg2
    conn = psycopg2.connect(pg_url)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'postgres') THEN "
                "CREATE ROLE postgres LOGIN SUPERUSER; "
                "END IF; END $$;"
            )
    finally:
        conn.close()

    redis_url = f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(redis.port)}"
    # DATABASE_URL and MEMORY_POSTGRES_URL resolve to the same instance
    # (core.db resolution order; TASK-257 §4 single-namespace posture).
    os.environ["POSTGRES_PASSWORD"] = pg.password
    os.environ["DATABASE_URL"] = pg_url
    os.environ["MEMORY_POSTGRES_URL"] = pg_url
    os.environ["REDIS_URL"] = redis_url


def _start_hermetic_stack() -> None:
    """Boot the full app on the ephemeral port: lifespan runs the REAL
    initialize_application() (validate → schema init → migrations → seed admin
    → credential-envelope gate); only the background loops are patched off."""
    if _herm["started"]:
        return

    # Datastores were provisioned at conftest import (see below): core.db
    # resolves DATABASE_URL once at import, and test modules import memory.*
    # at collection — before any fixture runs. Fixture-time provisioning
    # would leave that resolution frozen on the compose default.

    # Every boot-relevant knob is set EXPLICITLY before importing server:
    # load_dotenv does not override existing vars, but anything we leave unset
    # would leak in from a developer .env (JWT_SECRET_KEY, REDIS_URL, ...).
    os.environ["JWT_SECRET_KEY"] = secrets.token_hex(32)
    os.environ["ADMIN_EMAIL"] = TEST_EMAIL
    os.environ["ADMIN_PASSWORD"] = TEST_PASSWORD
    os.environ["DATA_ENCRYPTION_KEY"] = secrets.token_hex(32)
    os.environ.pop("DATA_ENCRYPTION_KEY_NEXT", None)
    os.environ.setdefault("ENFORCE_AGENT_SCOPE", "false")

    import server as server_module

    async def _no_background_tasks() -> None:
        pass

    server_module.start_background_tasks = _no_background_tasks
    server_module.start_bullmq_workers = _no_background_tasks
    server_module.stop_background_tasks = _no_background_tasks
    server_module.stop_bullmq_workers = _no_background_tasks

    import traceback

    import uvicorn
    config = uvicorn.Config(server_module.app, host="127.0.0.1",
                            log_level="warning", access_log=False)
    srv = uvicorn.Server(config)
    # uvicorn's lifespan failures propagate out of run() inside the thread —
    # capture them so the wait loop can surface the real cause, not just
    # "thread died".
    captured: list[str] = []

    def _run() -> None:
        try:
            srv.run(sockets=[_herm["sock"]])
        except BaseException:
            captured.append(traceback.format_exc())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    deadline = time.time() + 180
    while not srv.started and time.time() < deadline:
        if not thread.is_alive():
            detail = captured[0] if captured else "no exception captured (see stderr)"
            raise RuntimeError(f"Hermetic server thread died during startup:\n{detail}")
        time.sleep(0.1)
    if not srv.started:
        srv.should_exit = True
        raise RuntimeError("Hermetic server did not start within 180s")
    _herm.update(server=srv, thread=thread, started=True)


def _stop_hermetic_stack() -> None:
    srv = _herm.get("server")
    if srv is not None:
        srv.should_exit = True
        thread = _herm.get("thread")
        if thread is not None:
            thread.join(timeout=30)
        _herm["server"] = _herm["thread"] = None
    containers, _herm["containers"] = _herm.get("containers", []), []
    for container in reversed(containers):
        try:
            container.stop()
        except Exception:
            pass


if HERMETIC:
    # Datastores come up at CONFTEST IMPORT time, not fixture time: core.db
    # resolves DATABASE_URL once at import, and test modules import memory.*
    # at collection — before any fixture runs. Fixture-time provisioning
    # would leave that resolution frozen on the compose default.
    _provision_datastores()
    import atexit
    atexit.register(_stop_hermetic_stack)  # safety net if no fixture finalizer runs


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def base_url():
    if HERMETIC:
        _start_hermetic_stack()
        try:
            yield BASE_URL
        finally:
            _stop_hermetic_stack()
    else:
        yield BASE_URL


@pytest.fixture(scope="session")
def api_client(base_url):
    """Shared requests session without auth (tests strip headers freely).
    Depends on base_url so the hermetic stack boots for ANY HTTP test —
    this fixture is the root of the auth_token → admin/agent chain."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def auth_token(api_client):
    resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL, "password": TEST_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed ({resp.status_code}): {resp.text}")
    token = resp.json().get("token")
    if not token:
        pytest.skip("No token returned from login")
    return token


@pytest.fixture()
def authenticated_client(auth_token):
    """FRESH session with the admin JWT per test — header-popping tests on the
    shared anonymous session must not strip auth from later tests."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    })
    return s


@pytest.fixture(scope="session")
def admin(auth_token):
    """Session-scoped session with admin JWT (header pops never touch it)."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    })
    return s


@pytest.fixture(scope="session")
def agent_api_key(admin):
    """
    Returns a test agent API key.
    Creates a temporary agent and deletes it at teardown.
    """
    if PRESET_AGENT_KEY:
        yield PRESET_AGENT_KEY
        return

    resp = admin.post(f"{BASE_URL}/api/memory/config/agents", json={
        "name": "TEST_Suite_Agent",
        "description": "Temporary agent for automated tests",
        "access_level": "private",
    })
    assert resp.status_code == 200, f"Could not create test agent: {resp.text}"
    data = resp.json()
    agent_id = data["id"]
    key = data["api_key"]
    yield key
    admin.delete(f"{BASE_URL}/api/memory/config/agents/{agent_id}")


@pytest.fixture(scope="session")
def agent(agent_api_key):
    """Session-scoped session with agent X-API-Key."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-API-Key": agent_api_key,
    })
    return s
