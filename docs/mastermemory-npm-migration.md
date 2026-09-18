# MasterMemory — npm Framework Migration Plan

> **Status**: Planned — blocked on [knowledge-tier-productionization.md](knowledge-tier-productionization.md)
> **Goal**: Extract the 4-tier experiential-learning memory architecture into an installable TypeScript framework. Users `npm create mastermemory`, pick a database (Supabase/Postgres, libSQL, SQLite), get the schema rolled into their own project (e.g. a `mastermemory` schema in their own Supabase instance, pgvector optional), and run the pipeline on their own infrastructure — including Supabase Edge Functions.
>
> **Merged 2026-07-27** with the method playbook reconstructed from the
> `Frontbase-` → `frontbase-framework` migration (FastAPI → Hono/TS) — the same
> shape of problem, solved once already. §1–§6 are *what to build*; §7–§11 are
> *how to prove it's correct*. Both of those repos are local siblings of this one
> and share an owner, so vendoring, relicensing, and publishing across them are
> all available.

---

## 0. Three programs, one order

This document covers what turned out to be three distinct pieces of work. They
are sequenced deliberately; the ordering rationale is in §2.4.

| | Program | Depends on | Status |
|---|---|---|---|
| **A** | **Integration (bridge)** — the framework's agents consume MasterAgent's memory and prompt systems over its existing MCP servers. A small port, not config: the framework's MCP client has four defects (§2.3) | nothing | **unblocked, 3–5 days** |
| **B** | **Edge migration pipeline** — the framework houses reusable tooling for porting Python services to Hono, landing in `@frontbase/compiler` (§2.2) | nothing | **next**, built while doing §5 Phase 0.5 |
| **C** | **npm port** — MasterMemory becomes `@mastermemory/*`, then replaces the MCP bridge with an in-process dependency inside the framework worker | Tier 3 in prod + B | **blocked** (§1) |

**A before B before C.** A is unblocked and answers a question C's 4–6 weeks
presuppose: *are these systems actually useful to the framework's agents?* B is
what makes C provable rather than hand-ported. C is gated on Tier 3, which has
produced zero rows.

---

## 1. Honest Framing

**This is a rewrite, not a wrap.** The FastAPI backend cannot be "abstracted" into an npm package — Supabase Edge Functions run Deno/TypeScript, and none of the Python survives. What transfers is the valuable part:

- The four-tier schemas and their semantics (interactions → memories → intelligence → knowledge)
- Trigger/threshold logic (daily generation, threshold-based memory, compaction, knowledge accumulation)
- Prior-context injection strategy ("established facts, do NOT repeat" at every tier)
- Dedup, quality-scoring, merge/decay math
- The prompt templates, once battle-tested in prod

The Python system becomes the **reference implementation**. We port the *contract*, verified by golden fixtures captured from production (see productionization plan §6).

**The one correction the Frontbase migration forces on this framing:** "port the contract" has to mean a *machine-checkable artifact*, not an understanding. That migration worked because the Python app was made to **emit an OpenAPI spec**, and the spec became the new system's acceptance test — final score 285 implemented / 1 stubbed / **0 missing / 0 divergent** against a 286-op contract. No code was shared between the repos. See §7.

### Why not port now

1. Tier 3 has never run in production — every pipeline behavior fixed during productionization is a spec decision the port inherits for free. Porting now means porting the bugs.
2. The schema/naming migration (`lessons`→`knowledge`, `insights`→`intelligence`) is still in flight.

This gate is **reinforced** by the Frontbase experience: engine extraction was deliberately blocked until a spike had banked 17 numbered findings against the *real production renderer*. Every one of them would otherwise have surfaced mid-build. Tier 3 has produced **zero rows ever** — there is no contract yet for the tier that motivates the whole library.

### Design break: code-first config

The DB-backed config system (`memory_llm_configs`, pipeline stages, admin-UI-managed prompts) **does not port**. It is the single biggest source of silent failure in the current system (missing config row → empty LLM response → swallowed parse error) and the wrong idiom for a library. The framework uses a typed config object:

```ts
// mastermemory.config.ts
export default defineMemory({
  db: supabaseAdapter({ schema: "mastermemory", vectors: "pgvector" }),
  llm: openAICompatible({ baseURL: ..., apiKey: ..., model: "gpt-4o-mini" }),
  embedding: { model: "text-embedding-3-small", dims: 1536 },
  entityTypes: {
    contact: {
      intelligenceSignals: [...],
      knowledgeSignals: [...],
      thresholds: { intelligence: 10, knowledge: 5 },
      autoApprove: { intelligence: true },
    },
  },
  prompts: { /* overrides; sane defaults ship in core */ },
  hooks: { onAttachment, extractEntities, scrubPII },  // optional
});
```

Sane defaults everywhere; a missing optional feature is *off*, never silently broken.

---

## 2. What `frontbase-framework` actually provides

Assessed against the checkout, not the README. Two objections that once looked decisive are now moot — **same owner** — so "packages are unpublished / `private` / `workspace:*`" and "Apache-2.0 vs MIT" are both solvable by decision. Two are architectural and stand:

- **`@frontbase/edge-core` is unusable here.** It's a page-rendering engine: eSSR JSX→HTML, layout-tree recursion, LiquidJS filters, a ~10 KB client behaviors runtime, service-worker lifecycle — all under a CI-gated <70 KB budget that exists to serve HTML fast. MasterMemory renders no pages.
- **There is no vector layer to inherit.** `edge-infra/src/` is `cache · executors · providers · provisioning · proxy · queue · storage · types · vault`. No pgvector, no Vectorize, no embeddings, no cosine anywhere. Retrieval is net-new work either way.

### 2.1 `@frontbase/compiler` — the genuinely reusable package

2,904 lines across 28 files. **24 of the 28 import nothing from `@frontbase/*`** — the substrate is already import-clean of the rendering engine. Only four files couple to it: `cli/deploy.ts`, `cli/simulate.ts`, `manifest/build.ts` (type-only), and `cli/scaffold.ts` (inside template *strings* only).

| Reusable as-is / near-as-is | Lines | What it is |
|---|---|---|
| `extractor/schema.ts` | 208 | `export const Schema = z.object({…})` → manifest, via the TS compiler API. Two hardcoded assumptions to generalize: the symbol name `Schema`, and the `.tsx`-only file walk. |
| `extractor/typegen.ts` | 30 | manifest → `.d.ts` equal to `z.infer<typeof Schema>` |
| `extractor/types.ts` | 39 | `PropertyField` / `ZodKind` / diagnostics |
| `cli/agent.ts` | 80 | **AgentFormatter** — stable-key-order, timestamp-free JSON diagnostics; every command supports `--json`. Fully domain-agnostic; high value. |
| `cli/quickfix.ts` | 99 | `TextEdit` model (unique-`oldString` search/replace) + `applyEdit`; separates `fixable` from semantic-only fixes |
| `cli/types.ts` | 37 | `CommandResult` / `Issue` |
| `cli/checker.ts` | 123 | project walker + extract + typecheck → `CommandResult` |
| `cli/linter.ts` | 166 | AST rule harness with `--json`. The *harness* ports; the rules (FB001–003) are Frontbase's. |
| `cli/eslintPlugin.ts` | 42 | thin ESLint wrapper over the rules |
| `manifest/sha256.ts` | 77 | content-hash determinism kit |
| `vite/index.ts` | 76 | Vite plugin driving extraction (likely unneeded for a headless library) |
| **Total** | **~980** | |

**Patterns worth stealing even where the code doesn't port:**

- **`cli/simulate.ts` (105)** — boots the engine against N provider implementations and asserts **byte-identical** output across all of them. This answers a question §3 leaves open: it is exactly how you prove `VectorDriver` is a real abstraction across pgvector / libSQL native vectors / sqlite-vec / JS-cosine. An abstraction with one implementation isn't one.
- **`deploy/compose.ts` (63)** — asserts a composition boundary (server code must not appear in the browser bundle) against the **real composed artifact**, not in unit tests. Generalizes precisely to this plan's core rule — *"`fetch`-based I/O only, no Node-only deps in core."* Make that a bundle gate, not a code-review convention.
- **`cli/scaffold.ts` (261)** — templates inlined as strings, no FS template dir, so the package stays self-contained; variants (`--pure` / `--with-infra` / `--full`) map to install patterns. Structure ports to `npm create mastermemory`; content doesn't.
- **`cli/deploy.ts` (308)** — secret values fed on **stdin, never as an argv element** (argv leaks to the process list). Copy the discipline.
- **`queries/{defineQueries,registrar}.ts` (121)** — a named-query allowlist with Zod params, scope, TTL, and `execute` *stripped* from the untrusted projection. MasterMemory has no untrusted browser tier, so this doesn't port — but if the library ever exposes an agent-facing tool surface, this is the shape.

Not reusable: `manifest/build.ts`, `manifest/migrate.ts`, `emit/swBundle.ts`, `cli/{provision-d1,app-identity,parity,devRouter}.ts` — pages, service workers, Cloudflare/D1/wrangler.

### 2.2 Program B — the edge migration pipeline lives in `@frontbase/compiler`

Today the reuse path is copy-and-diverge: cheapest at n=1, wrong at n≥2. The framework should house the tooling for porting Python services to Hono. **It belongs in `@frontbase/compiler`, not a new package** — an earlier draft of this doc proposed a separate `@frontbase/forge` and that was wrong on both name and placement:

- `compiler` is *already* "build tooling — Zod schema extraction, manifest/type generation, query registrar, Vite plugin, CLI." A migration pipeline is dev tooling with the same audience, the same devDependency install position, and the same lifecycle. Nothing distinguishes it.
- It honors the standing rule instead of fighting it — *"new capabilities extend existing packages rather than adding new ones"* (A-3 / A-14, fixed six-package surface). No Decision A-20 needed, no seventh version line, changelog, or peer tree.
- The ~980 lines of §2.1 are **already inside `compiler`**. A separate package means a move; this means generalizing in place.
- The `frontbase` CLI binary already exists (`init · check · lint · simulate · emit-sw · deploy`). Adding subcommands is a surface users and agents already know.

**"Forge" was a bad name for a second reason:** it implied a new product where there are really only three additions. Decomposed honestly, most of the pipeline already ships:

| Piece | Status in `compiler` today |
|---|---|
| Zod extract · typegen · diagnostics · lint harness · sha256 determinism | **exists** (§2.1) — needs config knobs: symbol name, file glob, rule codes |
| Bundle-boundary gate | **exists** as the RULE-1 assert in `deploy/compose.ts` — generalize to "bundle X must contain no symbols from dep set Y" |
| Multi-driver parity harness | **exists** as `cli/simulate.ts` — generalize from providers to arbitrary driver sets |
| **Contract pipeline** (emit · hygiene-ratchet · vendor+pin · `x-implemented` diff · mutation) | **genuinely new** — §9, ~600 lines |

So the new surface is one subpath and a handful of commands:

```
@frontbase/compiler/contract     # new subpath export (alongside . · ./manifest · ./vite · ./cli)
frontbase contract emit          # spec from a source service
frontbase contract check         # hygiene + untyped-response ratchet
frontbase contract pin           # vendor + SHA pin
frontbase contract diff          # THE gate (--mutate for the harness)
frontbase parity <driverSet>     # generalized simulate
```

**Name note:** `contract`, not `migrate` — `manifest/migrate.ts` already owns "migrate" in this package for layout-version upgrades, and a second meaning would be a genuine collision.

**The one real objection, and its fix.** `compiler` declares `peerDependencies: { "@frontbase/edge-core": "workspace:*" }`, and four of its files import the engine. A consumer like `@mastermemory/*` installing compiler as a devDependency would drag a page-rendering engine into its install tree. Fix it structurally:

1. Mark the peer **optional** (`peerDependenciesMeta`) — the contract subpath doesn't need it.
2. Keep `./contract` on a module graph that **provably never reaches `edge-core`**, and enforce that with the boundary gate the toolkit itself ships.

That second point is why this placement is better than a separate package rather than merely cheaper: **the tool proves its own central claim on itself.** A separate package would assert the boundary by directory convention; this asserts it with the gate.

**Cost:** ~3–5 days, mostly the contract kit. Lower than the separate-package estimate because nothing moves.

### 2.3 Program A — framework agents consume memory + prompts

The framework's Workspace Agent and Edge Agent should treat MasterAgent's memory and prompt systems as first-class infrastructure. There are two ways to wire that, and they are sequential, not alternatives.

**Path 1 — MCP bridge (3–5 days).** Both ends exist, but one is a stub:

- MasterAgent mounts **two MCP servers over streamable HTTP** — `/api/prompts/mcp` (prompt CRUD + render + variables) and `/api/memory/mcp` (ingest, search, CRUD), authenticated by a single `MCP_SERVICE_KEY` (`backend/server.py:162-210`). **Working.**
- The framework has an **MCP client executor** — `mcpCallExecutor` in `edge-infra/src/executors/ai.ts` (node types `mcp.call` / `mcp_tool`). **Not working.** Verification found four defects: `@modelcontextprotocol/sdk` is declared in no `package.json` in the monorepo (every call throws `MODULE_NOT_FOUND`); it uses `SSEClientTransport` against a streamable-HTTP server; it sends no auth headers; and it has zero test coverage.
- The `mcp_servers` registry CRUD in `backend/src/compat/routes/agent-compat.ts` **is** real, with `url` / `transport` / `config` columns already in place.

> **Correction.** An earlier revision of this section called the bridge
> "configuration plus credential plumbing, not construction." That was wrong —
> it read the executor's existence as evidence it worked, which is the exact
> error §8 is about. It is a small **port**, not a config change, and two working
> reference implementations exist to port from: `Frontbase-/fastapi-backend/app/services/mcp_client.py`
> (selects sse vs streamable_http, builds auth headers) and
> `Frontbase-/services/edge/src/engine/agent/tools/user-tools.ts:137`
> (`buildMcpClientTools`, the TS shape).

**One scope limit to know up front:** the framework's *community* agent surface is stubbed — `/api/agent/chat` returns `{success:false, detail:'No LLM provider configured'}`, `tools/list` returns `{tools:[]}`. So a working MCP client in the framework has **no agent turn consuming it** until that loop exists. The product's Workspace Agent (`agent_executor.py` + `mcp_client.py`) does have a working loop, so the cheapest real value test may be wiring the bridge there first. Execution detail: [plans/mcp-bridge-and-contract-pipeline-plan.md](plans/mcp-bridge-and-contract-pipeline-plan.md).

**Path 2 — in-process dependency (blocked on Program C).** The framework's defining constraint is that everything composes into **one deployable worker** (Principle #1). An integration that requires a permanently-running Python service with Postgres + pgvector + Redis alongside it violates that outright — self-hosters would need two stacks. That is the real argument for the npm port: not packaging elegance, but that **`@mastermemory/core` imported into the worker is the only shape that preserves single-worker deployment.** Once C lands, the MCP bridge becomes a fallback for people who prefer a separate memory service.

**Why A genuinely belongs before C, not just "is cheaper."** The bridge answers a question the port presupposes: whether framework agents get real value from four-tier memory. If the answer is partial — say Tiers 0–2 plus prompt rendering carry the value and knowledge-tier retrieval does not — then C's scope shrinks materially. Tiers 0–2 work in production today, so the bridge can test that *now*, without waiting on Tier 3. Spending 4–6 weeks porting before asking is the same class of error as §8.

**Resolved collision: Prompt Manager & Agent Settings Unification (2026-07-27 decision):**

1. **Unified Prompt Engine (Zero-Git):** Prompt Manager and Agent Settings are unified into a single headless engine in the port. Git versioning / GitHub storage synchronization is **explicitly excluded from the npm/TypeScript port**.
2. **Three Core Pillars:** The ported Prompt Engine focuses exclusively on:
   - **Markdown Editor Support:** Raw Markdown string parsing & formatting with optional YAML frontmatter.
   - **Prompt Sectioning (`## Heading`):** Modularity and dynamic section-level overrides (`## Section Name`).
   - **Variable Injection (`{{ variable }}`):** Pure TypeScript regex variable extraction and interpolation.
3. **Pipeline vs Prompt Rule:** Pipeline configuration is code-first and typed; prompt templates and section overrides are runtime data managed via Markdown string/section structures.

**Where this gets recorded:** Path 2 changes the framework's package graph, so when work starts it needs an entry in `frontbase-framework/docs/DECISIONS.md` (append-only, explicit supersession). This document is the proposal; that ledger is where the decision lives.

### 2.4 Ordering rationale (§0 table)

**A → B → C**, because:

- **A is unblocked and de-risks C's scope.** Both ends of the MCP bridge exist; it costs days and can shrink a 4–6 week program.
- **B before C** because C without the contract pipeline is a hand-port — precisely the failure §8 documents. But build B *while* doing Phase 0.5 on MasterAgent (§5), not speculatively: tooling with no consumer is guesswork, and MasterAgent's ~155 routes are the first real consumer. The framework already learned this — `compiler`'s extractor was seeded from a spike that had a real payload, not from a design doc.
- **C last** and still gated on Tier 3 (§1). Nothing in A or B relaxes that gate; A is what makes waiting cheap.

---

## 3. Package Architecture

Monorepo, TypeScript, targeting Node + Deno + edge runtimes (core rule: `fetch`-based I/O only, no Node-only deps in core — **enforced by a bundle-boundary gate**, §2.1):

```
mastermemory/
├── packages/
│   ├── core/                 # @mastermemory/core — runtime-agnostic pipeline engine
│   │   ├── tiers/            #   ingest, generateMemories, extractIntelligence, buildKnowledge
│   │   ├── scoring/          #   quality score, dedup, decay, consolidation
│   │   ├── prompts/          #   default templates + {{ variable }} injection
│   │   └── drivers/          #   interfaces only: Storage, Vector, Queue, Lock, Clock
│   ├── adapter-postgres/     # node-postgres; pgvector optional (flag)
│   ├── adapter-supabase/     # supabase-js; schema-scoped tables (mastermemory.*)
│   ├── adapter-libsql/       # libSQL/Turso; native vector type
│   ├── adapter-sqlite/       # better-sqlite3 + sqlite-vec, or JS cosine fallback
│   ├── server/               # @mastermemory/server — Hono HTTP surface (Deno/Node/Bun/edge)
│   └── create-mastermemory/  # npm create scaffolder
└── (devDependency: @frontbase/compiler — extraction, diagnostics, contract gates,
                    parity harness; via the ./contract subpath, §2.2)
```

**Consumed by the framework** (§2.3): `@mastermemory/core` becomes an in-worker dependency of the framework's Workspace + Edge agents, replacing the Program-A MCP bridge. That is the shape that keeps single-worker deployment intact.

**Fixed-surface rule, adopted from A-3/A-14:** seven packages. New capabilities extend an existing package; adding one is a decision entry, not a directory. Writing that rule down is the only reason the framework's 35-package proposal never happened.

### Driver decisions (mapped from the Python system)

| Concern | Today (Python/VPS) | Framework |
|---|---|---|
| Queue | BullMQ + Redis | `QueueDriver`: Postgres jobs table with `FOR UPDATE SKIP LOCKED` (Supabase: pgmq/Queues); inline synchronous driver for SQLite/small deployments; BullMQ optional on Node |
| Scheduler | 60s asyncio loop in-process | Single idempotent `tick()` entry point. Supabase: pg_cron → edge function. Node: node-cron. Or manual invocation. The existing "has today's job run" job-log logic fits this shape directly |
| Entity lock | Redis `SET NX` + TTL | Postgres advisory locks / job-row transaction; SQLite is single-writer anyway. **Redis dependency dropped entirely** |
| Vector search | pgvector raw SQL | `VectorDriver`: pgvector · libSQL native vectors · sqlite-vec · brute-force JS cosine fallback (fine < ~50k rows). On/off flag per install. **Two implementations must pass one fixture set** (§2.1 parity harness) or the abstraction isn't real |
| LLM calls | httpx → OpenAI-compatible | Same via `fetch` — ports almost line-for-line. Add fence-stripping + `response_format` hardening from day one |
| Vision/OCR | PyMuPDF in-process | **Not portable.** Optional `onAttachment` hook → any HTTP service (including the existing Python container) |
| NER | GLiNER container / LLM fallback | Optional `extractEntities` hook; LLM-based default in core |
| PII scrubbing | zendata / LLM | Optional `scrubPII` hook; LLM-based default in core |
| Admin UI | React SPA | Out of scope for v1; the HTTP surface exposes the same admin endpoints so the existing UI (or a future one) can attach |

### HTTP surface (`@mastermemory/server`)

Hono app mirroring today's agent-facing API so existing n8n workflows can migrate by swapping the base URL:

- `POST /interactions` (ingest, attachments via hook)
- `GET /get-context` (pending interactions + memories + intelligence + knowledge)
- `POST /search/semantic`, `POST /search/fulltext`
- CRUD on memories / intelligence / knowledge
- `POST /tick` (scheduler entry point)
- Admin triggers (generate-memories, intelligence-check, knowledge-check)

Auth: API-key header (same `X-API-Key` model), pluggable verifier.

### Scaffolder (`npm create mastermemory`)

Prompts: which DB · pgvector on/off · schema name (default `mastermemory`) · tiers to enable. Emits:

1. Migration SQL files into the user's project (Supabase users apply via their own migration flow, in their own project)
2. Typed `mastermemory.config.ts`
3. For Supabase: an edge-function template + pg_cron setup snippet for `tick()`

---

## 4. Scope

### v1 (the proven core loop only)

- Interactions → memories → intelligence → knowledge pipeline
- Threshold + scheduled triggers, prior-context injection, signal validation
- Semantic + fulltext search, get-context
- `tick()` scheduler, Postgres/Supabase adapters, scaffolder
- Pipeline run log (observability learned from productionization)

### v2+ (plugins — deliberately deferred; least proven in our own prod)

- Playbooks & skills extraction (union-find clustering + AI telemetry)
- Hermes (admin natural-language instruction → knowledge records)
- Consolidation / decay / quality recompute
- Outbound + inbound webhooks
- libSQL/SQLite adapters (pure adapter work once driver interfaces are proven)
- Admin UI package

### The `library` / `console` contract split

Frontbase split its contract `full` (cloud) vs `community` (self-host) and ported only `community`. MasterMemory needs the analogous cut, and the v1/v2 lists above are most of it:

- **`library` surface** — ingest, generate, extract, build, search, `get-context`, `tick`. This is what the drift gate (§7 M5) measures.
- **`console` surface** — the ~79 admin/config endpoints (`memory/admin.py` 44 + `memory/config.py` 35) backing the React SPA. §1 already declares the DB-backed config system a design break that does not port. So mark these `x-surface: console`, **exclude them from the gate**, and record why — otherwise the gate reports ~50% "missing" forever and everyone learns to ignore it.

Derive the classification from a tag or router (§7 M1). Never hand-list it.

---

## 5. Phased Roadmap

| Phase | What | Effort | Gate |
|---|---|---|---|
| **A** | **MCP bridge** (§2.3 Path 1) — fix `mcpCallExecutor`'s four defects, then consume `/api/prompts/mcp` + `/api/memory/mcp` | **3–5 d** | `edge-infra` MCP suite + mutation green; live `tools/list` from both servers; agent-loop gap written up. See [the execution plan](plans/mcp-bridge-and-contract-pipeline-plan.md) |
| 0 | Productionize knowledge tier in Python system | days | see productionization plan |
| **0.5** | **Emit the contract from Python** (§9) + **land `@frontbase/compiler/contract`** (§2.2) — the tooling and its first consumer are the same work | **~1–2 wks** | committed `contracts/openapi.json`; CI rejects a router change that doesn't regenerate it; every new gate has a `--mutate` harness |
| 1 | Stabilize the contract: freeze schema, finish naming migration, capture golden **pipeline** fixtures from prod (§8) | 1–2 wks (overlaps 0) | knowledge generating in prod; fixtures committed + runner fails on drift |
| **1.5** | **Spike + written Proceed/Adjust/Abort memo** (§10) | ≤2 wks | numbered findings list banked as Phase 2 requirements |
| 2 | Build monorepo: core + postgres/supabase adapters + server + scaffolder | 4–6 wks focused | Phase 1 fixtures pass as conformance tests; drift gate green; every gate has a mutation harness |
| 3 | Dogfood: run the counselor workload on `@mastermemory/*` in our own Supabase project; FastAPI admin UI stays as optional console over the same schema | 2+ wks | Phase 2 shipped |
| **3.5** | **Swap the bridge for the dependency** (§2.3 Path 2) — `@mastermemory/core` in-worker; MCP bridge demoted to a fallback | 1–2 wks | single-worker deploy green with memory in-process; framework `DECISIONS.md` entry recorded |
| 4 | v2 plugins + remaining adapters, public release | ongoing | Phase 3 stable |

Phase A leads because it is unblocked and can shrink Phase 2 (§2.4). Phases 0.5 and 1.5 are the insertions the Frontbase migration argues for; **0.5 is the highest-leverage week here** — MasterAgent has ~155 route decorators across 13 modules and **no contract artifact at all today**. Without it, the port's acceptance criterion is "an agent read 26,500 lines of Python and believed it understood them." With it, the criterion is a diff. Phase 3.5 is where the integration and the port finally converge.

---

## 6. Open Questions (decide before Phase 2)

- **Package naming/registry**: `mastermemory` vs `@mastermemory/*` scope availability on npm
- **Prompt Manager vs. `agent_settings.py`** (§2.3 collision 1): does Prompt Manager absorb the framework's 3-layer agent-prompt stack, or sit beside it? Absorbing is the coherent story but is a migration with an existing UI attached. Blocks Phase 3.5, not Phase A.
- **Which tiers the framework's agents actually need** (§2.3): answered empirically by Phase A. If Tiers 0–2 plus prompt rendering carry the value, Phase 2's scope shrinks.
- **Embedding dimensions**: fixed at config time vs flexible per-table (current Python allows flexible `vector` columns at the cost of no HNSW index — decide indexing strategy per adapter)
- **Multi-tenancy**: single-tenant per schema (current model) vs tenant column — single-tenant per schema recommended for v1 (matches "roll your own schema" story)
- **Prompt Manager relationship**: the Prompt Manager module stays a separate product; the framework's prompt config accepts plain strings/templates, with an optional integration to fetch from a Prompt Manager instance later
- **License** (current repo is MIT) and whether the reference Python implementation stays public. Note `frontbase-framework` chose Apache-2.0 deliberately (Decision A-15: explicit patent grant, enterprise-legal friendliness under a commercial layer; AGPL rejected as suppressing adoption of an embeddable framework). The same reasoning may or may not apply here — but MasterMemory will depend on `@frontbase/compiler` (dev) and the framework will depend on `@mastermemory/core` (runtime, §2.3), so the licenses must be compatible **in both directions**.
- **The four production escape hatches**: `HANDOFF.md` lists `ENFORCE_AGENT_SCOPE=false`, `REQUIRE_WEBHOOK_TIMESTAMP=false`, `ALLOW_PUBLIC_SIGNUP=true`, `STRICT_STARTUP_VALIDATION=false` — each a deliberate legacy-compat default. Decide each one's value in the library *explicitly*; a default that carries over by accident is precisely the failure mode §8 describes.
- ~~Agent-skills interchange~~ **DECIDED (2026-07-05)**: the Anthropic agent-skills SKILL.md standard is adopted in the reference implementation — skill/playbook `content` stores the full SKILL.md document (renderer/parser in `backend/memory_skill_md.py`, import/export endpoints live). The npm framework inherits this: skills are marketplace-interoperable by construction
- **Drop the `knowledge.tags` column** in the clean-slate schema; fold freeform labels into `metadata.tags` (sibling of `metadata.facets`). Decided 2026-07-06 — deferred to the rewrite because dropping it now costs a data migration + code sweep + a generation-prompt output change, for zero functional gain (see [knowledge-precontext-retrieval-plan.md](plans/archived/knowledge-precontext-retrieval-plan.md) §8). Until then `tags` is a human/admin-only field, off the agent query surface; agents filter only on the governed `metadata.facets`.

---

## 7. The method: contract-first port (from `Frontbase-` → `frontbase-framework`)

Not a rewrite-and-hope, and not a wrapper. A **three-repo pipeline with a generated contract in the middle**:

```
   Frontbase-  (Python/FastAPI)                frontbase-framework (Hono/TS)
   ────────────────────────────                ─────────────────────────────
   routers + pydantic models
        │
        │  export_openapi.py  (deterministic, CI-gated for staleness)
        ▼
   contracts/openapi.community.json  ──vendor──▶  packages/backend/contracts/
   contracts/openapi.full.json          (pinned      openapi.community.json
        │                                to a           + PRODUCT_COMMIT
        │  openapi-ts                  product sha)         │
        ▼                                                    │ emit-openapi.mjs
   src/client/*.ts  (typed frontend client) ──vendor──▶  contracts/framework.openapi.json
                                                             │   (each op stamped
                                                             │    x-implemented)
                                                             ▼
                                                    contract-diff.mjs  ← THE GATE
                                                    MISSING   → fail
                                                    DIVERGENT → fail
                                                    stubbed   → burn-down counter
```

Repo shape (Decision A-15): fresh dedicated monorepo; the product repo stayed **untouched** through the entire first phase and became the framework's *first consumer*, not a casualty. **No cross-repo code imports, ever** — parity is proven through committed fixtures plus a vendored contract, so each repo builds hermetically offline. The sync script states the rationale outright: *"the framework must build and test hermetically, and contract bumps must be explicit, reviewable commits — so the contract is vendored (not fetched live)."* Repo starts private, flips public when presentable. Docs that had lived gitignored in the product repo migrated in and became version-controlled.

### The seven mechanisms

Each is load-bearing. Reproduce all seven.

**M1. Derive the contract, never hand-maintain it.** `export_openapi.py` imports the app once per deployment mode **in a subprocess** and dumps `app.openapi()`. An operation is `community` iff it exists in the self-host surface — derived, never annotated. Determinism is engineered: `PYTHONHASHSEED=0` is pinned because FastAPI resolves duplicate pydantic model names in set-iteration order. *Any hand-maintained old↔new mapping drifts within weeks.*

**M2. Gate staleness in CI on both sides.** `--check` regenerates and fails if the committed spec differs from the routers; same for the generated client. The rule is three lines: add handler with a `response_model` → `contracts:export && client:generate` → commit spec + client + router **together**.

**M3. Add a hygiene ratchet, not just a diff.** `openapi_check.py` hard-fails on missing/duplicate `operationId`, missing tags, module-prefixed schema names (the tell-tale of duplicate class names), and **ratchets untyped responses** — `openapi_gaps.json` is a baseline that may only shrink. This is what makes the *old* system's contract trustworthy enough to port against. Skip it and you port a fog.

**M4. Vendor + pin, don't fetch live.** `sync-contract.mjs` copies the spec plus generated Zod into the new repo and writes the source SHA to `PRODUCT_COMMIT`. *Real failure this caught:* the console-bundle pin and the contract pin drifted to different product revisions — invisible without a written-down pin. **If you vendor two artifacts from one upstream, pin them to one SHA and assert equality in CI.**

**M5. Emit your own spec and diff it, with `x-implemented` stubs as the burn-down.** `emit-openapi.mjs` reads the vendored contract plus an `IMPLEMENTED` registry and stamps every op `x-implemented: true|false`. Then the gate: **MISSING** → fail · **DIVERGENT** → fail · **`x-implemented: false`** → *not* a failure, those are honest 501 stubs counted in a per-tag conformance table. Implementation notes worth copying: the comparator resolves `$ref`s and sorts keys so comparison is order-independent; output is byte-deterministic so `--check` works; and it is **dependency-free by choice** — the note in the file records that the npm `oasdiff` package is a `0.0.1` security placeholder.

**M6. A mutation harness on every gate.** `contract-diff.mjs --mutate` feeds the gate a deliberately tampered spec and **exits 0 only if the gate catches it**. Every framework package has `test:mutation`; there's a root `pnpm test:mutation`. *A gate nobody has watched fail is not a gate.* Cheapest high-value practice here.

**M7. Golden corpus for behavior the contract can't express.** Schemas prove shapes, not semantics — so HTML snapshots were generated **once** from the old system's production renderer (14 real pages incl. the real homepage) and committed to `golden-corpus/{layouts,pages}` with a `manifest.json`. The new engine had to reproduce them byte-identically. The MasterMemory analogue is §8.

---

## 8. The lesson that cost the most: coverage ≠ parity

From `frontbase-framework/docs/cf-22-admin-visual-parity-gap.md` — read it before starting.

- CF-18 was stamped **"FULL PARITY"** on the axis of *functional-area coverage*: 11/11 nav areas had *a* working UI over real endpoints. True, and shipped.
- The first real deploy showed the console "looks super poor" next to the product's. Measured after the fact: **~2,200 lines / 6 hand-rolled UI primitives** vs **~11,500 lines / 52 shadcn primitives / a 110-file builder studio**. Per nav area, 5×–22× thinner.
- The plan had *admitted this in writing* ("MVP pages are simpler than the product's — by design"). Once the milestone was stamped done, **no tracked item carried the admission forward.** The doc's own verdict: *"The gap was known at design time, then lost in the bookkeeping."*
- The reopened effort then found the second-order version of the same error: 285/286 route coverage with a **green drift gate**, but *"many handlers are empty-state/success-shaped placeholders,"* plus a critical security defect (plaintext API keys) and a no-op password reset. The gate proved endpoints were *registered*, not that handlers *behave*.

**Three rules:**

1. **Name the axis you measured, in the milestone title.** "Route coverage complete" ≠ "behavior verified" ≠ "parity."
2. **Every acknowledged gap becomes a tracked item before the milestone closes,** or it evaporates.
3. **A schema gate is necessary and insufficient.** Behavior needs golden fixtures; security needs its own checklist, run independently.

### Golden pipeline fixtures — the real gate here

The schema gate proves the HTTP surface. It cannot prove `generateMemories()` produces the same memories. Capture from production (`knowledge-tier-productionization.md` §6 already calls for this) and make this the **primary** conformance suite:

- interaction batch → expected memory rows (T1)
- memory set + prior-context → expected intelligence rows (T2)
- intelligence set → expected knowledge rows (T3), **including** the SKILL.md rendering path (`backend/memory_skill_md.py`)
- dedup/threshold boundary cases — pin the unified creation+consolidation threshold behavior
- semantic + fulltext ranking on a fixed corpus with a fixed embedding

LLM calls are nondeterministic: **record request/response pairs and replay them.** The determinism under test is the pipeline, not the model.

---

## 9. Files to read and adapt (~600 lines; both repos are local siblings)

| File | Lines | Role | Port effort |
|---|---|---|---|
| `../Frontbase-/fastapi-backend/scripts/export_openapi.py` | ~150 | M1 — deterministic spec export | **Near-verbatim.** No `DEPLOYMENT_MODE` split here; collapse `MODES` to one entry, keep `PYTHONHASHSEED=0` and the subprocess isolation. |
| `../Frontbase-/fastapi-backend/scripts/openapi_check.py` | ~100 | M3 — hygiene + untyped-response ratchet | **Near-verbatim.** Drop the `x-edition` assertion. Expect a large initial `openapi_gaps.json` — that's the point. |
| `../Frontbase-/fastapi-backend/contracts/README.md` | 40 | the "adding a route" contract for humans | Rewrite header, keep structure. |
| `../frontbase-framework/scripts/sync-contract.mjs` | ~80 | M4 — vendor + pin | Retarget paths; keep the pin file and the hermetic-build rationale. |
| `../frontbase-framework/packages/backend/scripts/emit-openapi.mjs` | ~50 | M5 — emit own spec with `x-implemented` | Near-verbatim. Heed its warning: **do not** use a JSON array-replacer for determinism — it filters keys at every nesting level and empties the doc. |
| `../frontbase-framework/scripts/contract-diff.mjs` | ~200 | M5+M6 — the gate + mutation mode | **Near-verbatim.** The `$ref`-resolving comparator is the valuable part. |

Plus §2.1's ~980 lines from `packages/compiler/src/`.

Read for method, no code to take:

- `../frontbase-framework/docs/PHASE0-DECISION-MEMO.md` — the model for §10: a spike ending in a written **Proceed/Adjust/Abort** verdict, a measured evidence table, and **17 numbered "Phase 1 inputs"** — every obstacle hit, banked as a requirement. Nothing was re-discovered later.
- `../frontbase-framework/docs/DECISIONS.md` — append-only decision log with explicit supersession (A-13 *"Supersedes A-11"*; A-11 had blessed a dual-backend architecture and was reversed). At 857 lines it's why nobody re-litigated settled questions across an 8-month effort.
- `../frontbase-framework/docs/{ARCHITECTURE-SPLIT,PACKAGE-STRUCTURE}.md` — the 35 → 11 → 6 consolidation and the fixed-surface rule adopted in §3.

---

## 10. Phase 1.5 — write the spike memo

Before Phase 2, a ≤2-week spike answering, with numbers:

- Does the pipeline core run on Deno/edge with `fetch`-only I/O? (cold start, memory — and does the bundle-boundary gate pass?)
- Does `VectorDriver` survive contact with pgvector **and** one non-pgvector backend passing the *same* fixtures?
- Do the §8 golden fixtures pass against a TS reimplementation of **one** tier?
- Verdict: **Proceed / Adjust / Abort.**

End it with a numbered findings list. Those findings *are* the Phase 2 requirements.

---

## 11. Checklist for the implementing agent

**Phase A — MCP bridge (do first; §2.3)** — full task breakdown in [plans/mcp-bridge-and-contract-pipeline-plan.md](plans/mcp-bridge-and-contract-pipeline-plan.md)
- [ ] Declare `@modelcontextprotocol/sdk`; add streamable-HTTP transport; add auth headers (`MCP_SERVICE_KEY` via the vault, never argv)
- [ ] `edge-infra/test/mcp.mjs` + mutation entry
- [ ] Live `tools/list` against both MasterAgent MCP servers
- [ ] Agent-loop gap reported, **not** closed; owner decides where the first real agent turn lands

**Phase 0.5 — contract + pipeline (§2.2, §9)**
- [ ] `@frontbase/compiler/contract` subpath; `edge-core` peer marked optional; boundary gate proves `./contract` never reaches the engine
- [ ] Adapt `export_openapi.py`; commit `contracts/openapi.json`
- [ ] Adapt `openapi_check.py`; commit `openapi_gaps.json` baseline
- [ ] Classify ops `library | console`, **derived** from router/tag (§4)
- [ ] CI staleness gate on the spec
- [ ] `contracts/README.md` with the three-step "adding a route" rule

**Phase 1 — fixtures**
- [ ] Golden pipeline fixtures per tier, captured from prod, committed
- [ ] Recorded LLM request/response pairs for replay
- [ ] Fixture runner that fails loudly on drift

**Phase 2 — the new repo**
- [ ] Fresh repo; MasterAgent untouched, becomes first consumer
- [ ] `sync-contract.mjs` + pin (one SHA for all vendored artifacts, asserted equal in CI)
- [ ] `emit-openapi.mjs` with `x-implemented` stamping
- [ ] `contract-diff.mjs` gate in CI
- [ ] `--mutate` mutation harness on **every** gate
- [ ] Bundle-boundary gate: no Node-only deps in core
- [ ] Multi-driver parity harness green on ≥2 vector backends
- [ ] `DECISIONS.md`, append-only, explicit supersession
- [ ] Fixed seven-package surface written down

**Phase 3.5 — converge (§2.3 Path 2)**
- [ ] `@mastermemory/core` in-worker; single-worker deploy green
- [ ] Prompt Manager / `agent_settings.py` collision resolved (§6)
- [ ] Framework `DECISIONS.md` entry recorded
- [ ] MCP bridge demoted to documented fallback, not deleted

**Every milestone**
- [ ] Title names the axis measured
- [ ] Acknowledged gaps become tracked items before close
- [ ] Security checklist run independently of the schema gate
