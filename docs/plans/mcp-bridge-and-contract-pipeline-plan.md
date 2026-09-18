# Execution plan — Program A (MCP bridge) + Program B (contract pipeline)

> **For**: an implementing agent working task-by-task. **Parent doc**:
> [../mastermemory-npm-migration.md](../mastermemory-npm-migration.md) — read §0, §2.2, §2.3 first.
> **Created**: 2026-07-27
>
> **Scope**: Programs A and B only. **Program C (the npm port) is out of scope**
> — it is gated on Tier 3 running in production (zero rows ever) *and* on A's
> value assessment. Do not start C. Do not "prepare" for C.

---

## 0. Ground truth — read this before touching anything

The parent doc said the MCP bridge was "configuration, not construction." **That
was wrong.** Verification against the checkouts found four defects in the
framework's MCP client. Program A is a small *port*, not a config change — and
that is good news, because two working reference implementations exist.

**The framework's `mcpCallExecutor`** (`frontbase-framework/packages/edge-infra/src/executors/ai.ts:36-54`):

| # | Defect | Evidence |
|---|---|---|
| 1 | **Deps declared nowhere.** `@modelcontextprotocol/sdk`, `ai`, `@ai-sdk/*` appear in no `package.json` in the monorepo, but are `await import(...)`-ed at lines 26, 42–43, 101–103. Every call throws `MODULE_NOT_FOUND`. | `grep -rn "modelcontextprotocol\|\"ai\":" packages/*/package.json package.json` → no matches |
| 2 | **Wrong transport.** Uses `SSEClientTransport`. MasterAgent serves **Streamable HTTP** (`mount_http()`, fastapi-mcp 0.4.0). They will not connect. | `backend/server.py:202,210` |
| 3 | **No auth.** Sends no headers. MasterAgent requires `X-API-Key` **or** `Authorization: Bearer` equal to `MCP_SERVICE_KEY`. | `backend/server.py:167-168` |
| 4 | **Zero test coverage.** No MCP reference in any `edge-infra/test/*.mjs`. | `ls edge-infra/test/` |

This is the same pattern as the CF-22 finding in the parent doc §8: the executor
is *registered*, not *working*. Treat every "it exists" claim in this plan as
something you verify before relying on it.

**Two working references to port from — do not design from scratch:**

- **`Frontbase-/fastapi-backend/app/services/mcp_client.py`** — the better one. Selects `sse` vs `streamable_http` by a `transport` value (lines 51–79), builds auth headers from a decrypted config blob (`_auth_headers`), lazy-imports the SDK and degrades gracefully.
- **`Frontbase-/services/edge/src/engine/agent/tools/user-tools.ts:137`** — `buildMcpClientTools`, the TypeScript shape, showing auth via `requestInit.headers` (line 146). SSE-only, so port the *header pattern* from here and the *transport selection* from the Python.

**What already works and must not be rebuilt:**

- `mcp_servers` CRUD in `frontbase-framework/packages/backend/src/compat/routes/agent-compat.ts` is real, backed by a table that already has `url`, `transport`, and `config` columns.
- MasterAgent's two MCP servers are live: `/api/prompts/mcp` (tag `📝 Prompts`) and `/api/memory/mcp` (tag `🧠 Memory`).

**What does NOT work and is OUT OF SCOPE:** the framework's agent chat loop is a
stub — `/api/agent/chat` returns `{success:false, detail:'No LLM provider configured'}`,
`tools/list` returns `{tools:[]}`, `tools/call` returns 204 (`agent-compat.ts:8-22`).
**Do not build the agent loop.** Task A7 is to report that gap, not close it.

---

## 1. Guardrails

Violating any of these is worse than delivering nothing.

1. **Branch, never commit to `main`.** One branch per program: `feat/mcp-bridge`, `feat/contract-pipeline`. Do not push or open a PR unless explicitly asked.
2. **Never invent credentials.** `MCP_SERVICE_KEY`, database URLs, and API keys come from the owner. If a task needs one you do not have, **stop and ask** — do not stub a fake key and mark the task done.
3. **Secrets never reach argv, logs, error messages, or test fixtures.** Feed them via env or stdin. This is a repo convention (`compiler/src/cli/deploy.ts` documents why: argv leaks to the process list).
4. **Do not widen scope.** If you find a bug outside your task, write it in the findings log (§4) and move on. The `ai` / `@ai-sdk/*` undeclared-dependency gap is a *known example* — record it, do not fix it.
5. **Do not run deploys.** No `wrangler deploy`, no `deploy:cf-full`, no `deploy.sh`. Dry-runs only.
6. **Do not edit** `frontbase-framework/docs/DECISIONS.md`. It is an append-only ledger for decisions the owner has made. Propose; don't record.
7. **In `Frontbase-`, `/docs/` and `test_*.py` are gitignored repo-wide.** New tests/docs there are local-only. Do not fight this; note it if it blocks you.
8. **Report failures honestly.** If a suite is red, say so with the output. Never describe a task as done because the code "looks right."

**Stop and ask** when: a task needs a credential you lack · a change would touch more than the files its task names · a reference implementation contradicts this plan · an acceptance criterion cannot be met as written.

---

## 2. PROGRAM A — the MCP bridge

**Goal:** the framework can call MasterAgent's memory and prompt tools over MCP,
proven by a test suite and one live smoke run.
**Repo:** `frontbase-framework` (all tasks except A6 verification).
**Estimated:** 3–5 days.

### A0 — Baseline

Establish that everything is green *before* you change it, so you can attribute any breakage.

```bash
cd frontbase-framework && pnpm install && pnpm build && pnpm test
```

- [ ] Record the pass/fail count of every suite in the findings log.
- [ ] **Acceptance:** you can state the baseline numerically. If anything is already red, log it and continue — do not fix it.

### A1 — Declare the missing dependency

**File:** `packages/edge-infra/package.json`

- [ ] Add `@modelcontextprotocol/sdk` to `dependencies`. Match the version used by `Frontbase-/services/edge` (check its `package.json`) so both repos speak the same protocol version.
- [ ] Add **only** that one. The `ai` and `@ai-sdk/*` gaps belong to `aiChatExecutor` — log them (§4), leave them.
- [ ] **Acceptance:** `pnpm --filter @frontbase/edge-infra build` is green, and this prints the module's exports without throwing:
  ```bash
  node -e "import('@modelcontextprotocol/sdk/client/index.js').then(m=>console.log(Object.keys(m)))"
  ```

### A2 — Transport selection (SSE + Streamable HTTP)

**File:** `packages/edge-infra/src/executors/ai.ts`, `mcpCallExecutor` only.
**Reference:** `mcp_client.py:51-79`.

- [ ] Read a `transport` node input: `'http'` (Streamable HTTP) or `'sse'`. **Default `'http'`** — that is what MasterAgent serves.
- [ ] For `'http'`, use `StreamableHTTPClientTransport` from `@modelcontextprotocol/sdk/client/streamableHttp.js`. Confirm the exact export path against the installed SDK version rather than trusting this line.
- [ ] Keep `SSEClientTransport` working for `'sse'`. This is additive; do not remove it.
- [ ] Preserve the existing `try/finally { await client.close() }`.
- [ ] **Acceptance:** both branches construct their transport under unit test (A4); `tsc` clean.

### A3 — Authentication headers

**File:** same executor. **Reference:** `_auth_headers` in `mcp_client.py`; header shape in `user-tools.ts:146`.

- [ ] Accept an `auth` input resolved to headers. Support `X-API-Key` **and** `Authorization: Bearer` — MasterAgent accepts either (`server.py:167-168`).
- [ ] Pass them via the transport's `requestInit.headers` for both transports.
- [ ] **The secret is resolved by the host from the vault/env and passed in — never a literal in a workflow node, never logged.** `edge-infra/src/vault` is the existing mechanism.
- [ ] Missing auth must fail with a clear, **secret-free** error.
- [ ] **Acceptance:** a test asserts the header is attached; a second test asserts the key value appears in **no** thrown error or log line.

### A4 — Test suite

**New file:** `packages/edge-infra/test/mcp.mjs`. Follow the house style exactly — read `test/runners.mjs` first: plain `node` script, imports from `../dist/`, a `check(label, cond)` helper, non-zero exit on failure.

- [ ] Cover: http transport selected by default · sse selected explicitly · auth headers attached · secret absent from error output · `client.close()` called on the failure path.
- [ ] Use a mock/in-process MCP server. **No network in this suite.**
- [ ] Register it in `packages/edge-infra/package.json` → `scripts.test`, in the existing chain.
- [ ] Add a mutation entry to `test/mutation.mjs`: break the transport selection, assert the suite catches it. (Parent doc §7 M6 — *a gate nobody has watched fail is not a gate*.)
- [ ] **Acceptance:** `pnpm --filter @frontbase/edge-infra test` green; `test:mutation` green; deliberately reverting A2 turns the suite red.

### A5 — Live smoke against MasterAgent

**Requires a running MasterAgent and `MCP_SERVICE_KEY`. You do not have these — ask.**

- [ ] Confirm with the owner: base URL, and the key delivered via env (never in a file, never in chat).
- [ ] Call `tools/list` against `/api/memory/mcp` and `/api/prompts/mcp`.
- [ ] Call one **read-only** tool per server (a memory search; a prompt render). **Do not call ingest, CRUD, or any mutating tool against a production instance.**
- [ ] Keep this out of the default `test` script — credential-gated, like the existing `d1RunnerFromRest` / `supabaseRunner` patterns in `test/runners.mjs`.
- [ ] **Acceptance:** non-empty tool lists from both servers, and one successful read-only call, with output pasted into the findings log (redact the key).

### A6 — Register MasterAgent as an MCP server

- [ ] Via the existing `POST /api/mcp-servers` (`agent-compat.ts`) — do not write SQL directly. Set `transport` to match A2's naming.
- [ ] Two rows: memory and prompts.
- [ ] Document the setup (env vars, URLs, how the key is supplied) in `frontbase-framework/docs/guides/` following the style of the existing guides there.
- [ ] **Acceptance:** `GET /api/mcp-servers` returns both rows; a fresh reader can follow the guide without asking questions.

### A7 — Report the agent-loop gap. Do not close it.

- [ ] Write a findings section stating plainly: the MCP *client* now works, but the framework's community agent surface is a stub, so **no agent turn consumes it yet**. Name the file and lines.
- [ ] State what closing it would require, and that the product's Workspace Agent (`Frontbase-/fastapi-backend/app/services/agent_executor.py` + `mcp_client.py`) already has a working loop — so the cheapest real value test may be wiring the bridge *there* first.
- [ ] **Acceptance:** the owner can decide the next step from your write-up without re-deriving any of it.

> **Note on the parent doc's Phase-A acceptance criterion** ("one Edge/Workspace agent
> turn reading memory + rendering a managed prompt"): that is **not achievable in
> the framework** as written, because the loop is a stub. It *is* achievable against
> the product's Workspace Agent. Flag this to the owner at A7 rather than silently
> redefining the criterion.

---

## 3. PROGRAM B — the contract pipeline

**Goal:** MasterAgent emits a machine-checkable contract; `@frontbase/compiler`
gains the reusable tooling that consumes it.
**Repos:** `masteragent` (B1–B4), `frontbase-framework` (B5–B8).
**Estimated:** 1–2 weeks. **Start only after A4 is green** (A5–A7 may still be open).

**Sequencing rule:** build each tool *against MasterAgent as its first consumer*.
Never write a generic gate before the concrete case works. Tooling with no
consumer is guesswork.

### B1 — Export the OpenAPI contract from MasterAgent

**New file:** `masteragent/backend/scripts/export_openapi.py`.
**Reference:** `Frontbase-/fastapi-backend/scripts/export_openapi.py` — port near-verbatim.

- [ ] Collapse the `MODES` dict to a single mode (MasterAgent has no `DEPLOYMENT_MODE` split).
- [ ] **Keep `PYTHONHASHSEED=0` and the subprocess isolation.** Non-negotiable — without it FastAPI resolves duplicate pydantic model names in set-iteration order and the output is non-deterministic. The reference file explains this in its docstring.
- [ ] Emit `masteragent/contracts/openapi.json`; add a `--check` mode that fails on drift.
- [ ] **Acceptance:** two consecutive runs are byte-identical; `--check` passes on a clean tree and fails after any router edit. Record the op count (expect ~155).

### B2 — Hygiene ratchet

**New file:** `masteragent/backend/scripts/openapi_check.py`.
**Reference:** `Frontbase-/fastapi-backend/scripts/openapi_check.py`.

- [ ] Hard-fail on: missing or duplicate `operationId` · missing tags · module-prefixed schema names (the tell-tale of duplicate class names).
- [ ] Ratchet untyped success responses into `masteragent/contracts/openapi_gaps.json`. **The baseline will be large. That is expected and correct** — it may only ever shrink.
- [ ] Drop the `x-edition` assertion (Frontbase-specific).
- [ ] **Acceptance:** the baseline is committed; adding a new untyped route fails the check.

### B3 — `library` / `console` classification

- [ ] Mark each op `x-surface: library | console`, **derived from its router or tag** — never a hand-maintained list (parent doc §7 M1).
- [ ] `console` = the admin/config surface (`memory/admin.py` ~44 ops, `memory/config.py` ~35). `library` = ingest, generate, extract, build, search, get-context, tick.
- [ ] Write the exclusion rationale into `masteragent/contracts/README.md` (port the structure from the Frontbase one): the console surface is the design break of parent §1 and is deliberately outside the gate.
- [ ] **Acceptance:** every op carries a surface; the split is reproducible from a clean checkout; the counts are recorded.

### B4 — CI staleness gate

- [ ] Add a workflow to MasterAgent's existing `.github/` running `export_openapi.py --check` and `openapi_check.py`.
- [ ] Document the three-step rule in `contracts/README.md`: add handler with a `response_model` → regenerate → commit router + spec **together**.
- [ ] **Acceptance:** a PR that edits a router without regenerating is rejected by CI.

### B5 — The `./contract` subpath in `@frontbase/compiler`

**Files:** `packages/compiler/package.json`, `packages/compiler/src/contract/`.

- [ ] Add a `./contract` entry to `exports`, alongside `.` / `./manifest` / `./vite` / `./cli`.
- [ ] Mark `@frontbase/edge-core` **optional** via `peerDependenciesMeta` — the contract subpath does not need the engine.
- [ ] **`src/contract/` must not import `@frontbase/edge-core`, directly or transitively.**
- [ ] **Acceptance:** `tsc` clean; the subpath resolves from a project with no `edge-core` installed.

### B6 — `frontbase contract` commands

**Reference:** `frontbase-framework/scripts/{sync-contract,contract-diff}.mjs` and `packages/backend/scripts/emit-openapi.mjs` — all three port near-verbatim.

- [ ] `contract pin` — vendor a spec + write the source SHA. **One SHA for all vendored artifacts, asserted equal in CI** (parent §7 M4: mismatched pins were a real, invisible failure).
- [ ] `contract emit` — stamp each op `x-implemented: true|false` from a registry.
- [ ] `contract diff` — filter spec ops to `x-surface: library` before comparing (print excluded `console` count in summary). MISSING → fail · DIVERGENT → fail · `x-implemented:false` → burn-down counter, not a failure. Keep the `$ref`-resolving, key-sorting comparator; keep it **dependency-free** (the npm `oasdiff` is a `0.0.1` security placeholder — the reference file says so).
- [ ] Wire into `src/cli/index.ts` following the existing `commander` pattern; every command supports `--json` via `AgentFormatter`.
- [ ] **Name check:** `contract`, never `migrate` — `manifest/migrate.ts` already owns that word for layout-version upgrades.
- [ ] **Acceptance:** run against B1's real contract; two consecutive runs byte-deterministic across runs; `--json` shape stable.

### B7 — Mutation harness

- [ ] `contract diff --mutate`: feed a spec with an op deliberately removed; **exit 0 only if the gate catches it.**
- [ ] Register in `packages/compiler/test/mutation.mjs`.
- [ ] **Acceptance:** `pnpm --filter @frontbase/compiler test:mutation` green, and it fails if you neuter the comparator.

### B8 — Boundary gate

**Reference:** the RULE-1 assert in `packages/compiler/src/deploy/compose.ts`.

- [ ] Generalize to: *"bundle built from entry X contains no symbols from dep set Y."*
- [ ] **Apply it to `./contract` vs `@frontbase/edge-core`** — the toolkit proving its own claim on itself (parent §2.2).
- [ ] **Acceptance:** the gate passes for `./contract`; adding a deliberate `edge-core` import to `src/contract/` turns it red.

---

## 4. Deliverables

One findings log per program, written as you go — not reconstructed at the end.

- `masteragent/docs/plans/mcp-bridge-findings.md`
- `masteragent/docs/plans/contract-pipeline-findings.md`

Each must contain: baseline numbers (A0) · per-task status with the **command output** that proves it · every out-of-scope bug found (guardrail 4) · every place this plan was wrong, quoted · what you did **not** do and why.

**Definition of done, Program A:** A1–A4 merged to a branch, `edge-infra` test + mutation green, live smoke recorded (A5) or explicitly blocked on credentials, the agent-loop gap written up (A7).

**Definition of done, Program B:** MasterAgent emits a deterministic, CI-gated contract with a committed gaps baseline and a derived surface split; `@frontbase/compiler/contract` ships `pin`/`emit`/`diff` with a mutation harness and a passing self-boundary gate.

**Neither program is done because the code looks right.** Each acceptance
criterion names a command. Run it, paste the output.
