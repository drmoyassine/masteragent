# Benchmark Deployment — LongMemEval Dedicated Stack (Future Milestone)

Status: **planned**. A stack was built and verified on 2026-10-26, then torn down
2026-10-27 to free resources; this document is the resurrection recipe plus the
protocol, so round two is an afternoon, not a discovery project.

Related: `benchmarks/longmemeval/` (harness, PRs #62/#63),
`docs/plans/knowledge-learning-loop.md` §10 (the eval this serves).

## Why a dedicated deployment (not prod, not local)

- **Contamination is bidirectional** through the global knowledge tier: benchmark
  haystacks would pollute prod knowledge, and prod knowledge would answer
  benchmark questions. Neither direction is acceptable.
- **Footprint curves need a fresh DB** — "accuracy vs memory footprint growth" is
  only measurable when the denominator starts at zero.
- **Reproducibility**: pinned commit, separate LLM budget, no interference with
  nightly prod jobs.

## Blockers (do these first)

1. ~~**Migration 009 — fresh-install prompt-console gap.**~~ **RESOLVED** —
   `backend/migrations/009_prompt_console.sql` shipped (2026-10-27): creates
   the eight prompt-console tables idempotently on fresh installs and seeds
   the four default templates; regression-tested by the hermetic suite
   (`test_fresh_install_prompt_console.py`).
2. **LLM provider config** — the bench needs its own embedding + pipeline
   providers configured in-DB (`memory_llm_configs` + provider credentials
   via admin UI) before ingest produces anything beyond tier 1.

## Deployment recipe (verified on EasyPanel, 2026-10-26)

Panel notes: prod MasterAgent lives on the 4ky7uo panel; the other panel
(fir7vq) caps at 3 projects — the 2026-26 stack went under the `studygram`
project as `masteragent-bench*` services. Cleanest round two: a **compose
service** mirroring prod (`tenants/masteragent`) on either panel.

Three pieces:

| Piece | Config |
|---|---|
| Postgres | image `pgvector/pgvector:pg16` (panel "database" type is vanilla postgres — NO pgvector), volume at `/var/lib/postgresql/data` |
| Redis | panel-managed redis:7, password-authenticated URL |
| App | GitHub `drmoyassine/masteragent` @ pinned commit; container port **80** (supervisord: nginx + uvicorn); internal DNS = service names |

Env vars (all fresh, none shared with prod): `JWT_SECRET_KEY`,
`DATA_ENCRYPTION_KEY` (Fernet), `STRICT_STARTUP_VALIDATION=true`,
`ALLOW_PUBLIC_SIGNUP=false`, `ENFORCE_AGENT_SCOPE=false`, `ADMIN_EMAIL` /
`ADMIN_PASSWORD` / `ADMIN_USERNAME`, `POSTGRES_PASSWORD`, `MCP_SERVICE_KEY`,
`CORS_ORIGINS=<bench domain>`, `DATABASE_URL` +
`MEMORY_POSTGRES_URL=postgresql://postgres:<pw>@<pg>:5432/memory`,
`REDIS_URL=redis://:<pw>@<redis>:6379/0`, `TZ=UTC`, `PGTZ=UTC`.

Post-boot: health check `/api/health`, then create the harness agent —
`POST /api/memory/config/agents` with admin JWT (returns `mem_...` key).
**Not** `POST /api/keys` (that mints a prompt-manager `pm_` key that memory
endpoints reject).

Smoke: `python adapter.py --base-url <bench> --email … --password …
--agent-key mem_… --dataset bench_smoke.jsonl --skip-judge` (committed
3-question fixture; no HF download needed).

## Protocol

1. **Smoke** — `--skip-judge` on `bench_smoke.jsonl`; verify ingest counts,
   footprint, get-context shape.
2. **Dataset** — `download_dataset.py --split LongMemEval_s` → JSONL.
3. **Pilot (~50 questions)** — pick reader/judge: different model families
   (candidates: GLM reader + GPT-4o-mini judge, or the reverse). `READER_*` /
   `JUDGE_*` env vars point at any OpenAI-compatible endpoints.
4. **Full `loop_closed` run** (weight 0.0, default).
5. **Multi-day protocol** — the paper's real experiment: daily ingest+answer
   on the long-lived stack while the nightly `knowledge_outcome_attribution`
   accumulates events; same-day loop-open/closed deltas are ~0 by construction
   (recurrence needs ≥7-day windows, echo needs post-distill lessons).
   Compare accuracy-vs-footprint curves across ablations.
6. **Analysis** — per-type accuracy + mean footprint per run (printed by the
   adapter); curves plotted for the paper, not in the harness.

## Suggested timing

After migration 009 ships (it unblocks the fresh DB) and after the ~2026-11-09
prod blend flip review — the pilot then doubles as validation that the loop
dials behave as designed before the multi-day commitment.
