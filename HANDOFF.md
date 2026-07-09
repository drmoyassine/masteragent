# MasterAgent Handoff

## Current state

MasterAgent contains a Prompt Manager and a four-tier Memory System:
Interactions → Memories → Intelligence → Knowledge. PostgreSQL/pgvector is the
source of truth, Redis/BullMQ handles processing, and the React SPA provides the UI.

## Production compatibility controls

- `ENFORCE_AGENT_SCOPE=false` preserves historical cross-agent entity access.
- `REQUIRE_WEBHOOK_TIMESTAMP=false` preserves webhook senders without replay headers.
- `ALLOW_PUBLIC_SIGNUP=true` preserves signup; registered users are not administrators.
- `STRICT_STARTUP_VALIDATION=false` warns rather than aborting on legacy secrets.

See `docs/production-hardening-rollout.md` before deployment.

## Validation baseline

- Python source compilation passes.
- Frontend production build passes under CI warning enforcement.
- Docker Compose configuration validates.
- Live integration tests require PostgreSQL, Redis, and the running API.

## Next engineering priorities

1. Run the live suite against a disposable Compose environment.
2. Migrate remaining Insights/Lessons tests to Intelligence/Knowledge.
3. Move blocking PostgreSQL queries off the FastAPI event loop in a benchmarked change.
4. Fix an embedding dimension before adding HNSW indexes.
