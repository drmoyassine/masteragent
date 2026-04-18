# Frontbase Roadmap Analysis — Prioritization & Sequencing

> **Context**: Analyzing 5 planned work streams against the Cloud Alpha launch for maximum strategic impact.

---

## The 5 Work Streams Under Review

| # | Document | What It Is | Effort |
|---|----------|-----------|--------|
| A | **cloud-launch-plan.md** | Multi-tenant cloud SaaS: tenants, publish, subdomains | ~7.5 days |
| B | **browser-edge-runtime-plan.md** | Offline PWA: in-browser SQLite, P2P sync, service worker | ~3-4 weeks |
| C | **Edge-Agent — Replanned Roadmap.md** | Edge AI agent: MCP, Telegram/Slack channels, browsing, memory | ~3-5 weeks |
| D | **workspace_agent_phase2.md** | Builder AI agent: streaming, tool parity, dynamic prompts | ~1.5 weeks |
| E | **pydanticAI-ramfootprint.md** | Replace PydanticAI with raw httpx (RAM fix) | ~2-3 hours |

---

## The Big Picture: Frontbase Has 4 Competitive Moats

```
                    ┌─────────────────────────────────────────────┐
                    │         FRONTBASE COMPETITIVE MOATS          │
                    │                                             │
  Cloud Launch ────→│  1. MULTI-TENANT NO-CODE BUILDER (A)      │──→ User Acquisition
                    │     "Build and publish in 5 minutes"       │
                    │                                             │
  Browser Edge ───→│  2. INDESTRUCTIBLE OFFLINE MODE (B)        │──→ Enterprise Closer
  + Raspberry Pi   │     "Works even if every server dies"       │
                    │     "Raspberry Pi as local edge server"     │
                    │                                             │
  Edge Agent ─────→│  3. AI-NATIVE EDGE OPERATIONS (C+D)        │──→ Differentiation
                    │     "Your edge app thinks for itself"       │
                    │                                             │
  All combine ────→│  4. EDGE SELF-SUFFICIENCY (core invariant) │──→ Investor Story
                    │     "No callbacks. No dependencies."        │
                    └─────────────────────────────────────────────┘
```

---

## How the Browser Edge + Raspberry Pi Fits

This is your **most powerful enterprise story**. Let me map it to the existing case studies:

### The 5-Layer Resilience Stack

```
Layer 5 ─── Cloud Edge (CF Worker / Deno)
             Normal mode. Serves xyz.frontbase.dev globally.
             ↑ Dies? No problem ↓

Layer 4 ─── Local Edge Server (Raspberry Pi + WiFi adapter)
             On-premise hardware. Runs Node.js + Hono + SQLite.
             Serves pages to local browsers on the LAN.
             Syncs to cloud when network is available.
             ↑ Dies? No problem ↓

Layer 3 ─── Browser PWA (Service Worker + libsql-wasm)
             Each browser is a self-contained edge node.
             Full SQLite in-browser. Renders SSR pages locally.
             Offline-first. Queues data locally.
             ↑ Network resumes ↓

Layer 2 ─── Sync merge
             Browser → Local Edge → Cloud Edge
             LWW / user-defined conflict resolution
             Deduplication at each hop

Layer 1 ─── Central truth
             Cloud Turso becomes authoritative after merge
```

### The Airline Queue Scenario (Your Example)

```
Normal operation:
  Passenger kiosks → Airport WiFi → Cloud Edge → Airline systems

Airport internet dies (Hurricane/power outage):
  Passenger kiosks → Airport WiFi → Raspberry Pi (local edge)
    ✅ Check-in still works
    ✅ Boarding passes still print
    ✅ Data queues locally on Pi

Raspberry Pi also dies (total power loss):
  Passenger kiosks → Each running on battery
    ✅ Browser has full data in libsql-wasm
    ✅ Forms still submit (offline queue)
    ✅ Last-known passenger list rendered from local SQLite

Power restores:
  Browsers → discover Raspberry Pi on LAN
    → Sync offline queues (dedup by ID + timestamp)
    → Pi syncs to cloud edge
    → Cloud edge reconciles with central truth
    → All 300 passengers checked in, zero data loss
```

### Why This Destroys the Competition

No other platform offers this:

| Layer | Retool | Appsmith | Budibase | **Frontbase** |
|-------|:---:|:---:|:---:|:---:|
| Cloud hosted | ✅ | ✅ | ✅ | ✅ |
| Self-hosted server | ✅ | ✅ | ✅ | ✅ |
| Local edge hardware (Pi) | ❌ | ❌ | ❌ | ✅ ← **unique** |
| Browser-native offline | ❌ | ❌ | ❌ | ✅ ← **unique** |
| P2P browser sync | ❌ | ❌ | ❌ | ✅ ← **unique** |
| Survives total cloud death | ❌ | ❌ | ❌ | ✅ ← **unique** |

### Enterprise Verticals This Unlocks

| Vertical | Use Case | Why They'd Pay $50K-500K/year |
|----------|----------|-------------------------------|
| **Airlines** | Check-in kiosks, gate displays, boarding | AT&T outage (2024): 125M devices disconnected. Kiosks need to work without internet. |
| **Retail/QSR** | POS fallback, menu displays, inventory | Internet dies at a Starbucks? Ordering still works on the Raspberry Pi. |
| **Logistics** | Warehouse tablets, driver manifests | Amazon warehouse WiFi drops? Workers still scan and queue. |
| **Military** | Tactical terminals, field ops | DDIL environments — everything must work disconnected. Raspberry Pi in a ruggedized case. |
| **Healthcare** | Nurse stations, patient check-in | Hospital WiFi outage shouldn't stop patient intake. |
| **Oil & Gas** | Rig-side dashboards, safety checklists | No internet on a deepwater rig. Pi + browser = full ops dashboard. |

---

## Recommended Sequencing

### The Strategic Logic

```
Phase 1: PROVE IT WORKS (Cloud Launch)
  → Get users in. Show the builder is real.
  → Every feature here doubles as enterprise demo.
  
Phase 2: PROVE IT'S SMART (AI Agent Polish)  
  → "Your apps think for themselves"
  → Demos at enterprise meetings are 10x more impressive

Phase 3: PROVE IT'S INDESTRUCTIBLE (Browser Edge + Pi)
  → This is the MOAT. The thing no one else can do.
  → But it requires cloud working first (what do you sync TO?)
  → And it requires published pages working (what do you render offline?)
  → This is the feature that closes $100K+ enterprise deals.
```

### Concrete Timeline

```
WEEK 1-2     ┌──────────────────────────────────────────────┐
             │  A. Cloud Alpha Launch (7.5 days)            │
             │  + E. PydanticAI → httpx (2 hours)           │
             │                                              │
             │  Ships: app.frontbase.dev, xyz.frontbase.dev │
             │  Result: First real users                    │
             └──────────────────────────────────────────────┘
                              │
WEEK 3       ┌──────────────────────────────────────────────┐
             │  D. Workspace Agent Phase 2 - Wave 1-2       │
             │     Streaming + tool parity                  │
             │                                              │
             │  Ships: Polished AI chat in builder          │
             │  Result: "Watch me build a page by talking"  │
             └──────────────────────────────────────────────┘
                              │
WEEK 4-5     ┌──────────────────────────────────────────────┐
             │  C. Edge Agent - Wave A (MCP resources)      │
             │  C. Edge Agent - Wave B (Telegram/Slack)     │
             │                                              │
             │  Ships: "Connect Telegram, your edge app     │
             │          responds to customer questions"      │
             │  Result: Enterprise demo capability          │
             └──────────────────────────────────────────────┘
                              │
WEEK 6-9     ┌──────────────────────────────────────────────┐
             │  B. Browser Edge Runtime (Phases 1-3)        │
             │     BrowserSqliteProvider + Sync + PWA       │
             │     + Raspberry Pi hardware adapter          │
             │                                              │
             │  Ships: "Open your browser. Go offline.      │
             │          Everything still works. Come back    │
             │          online. Everything syncs."           │
             │  Result: The enterprise MOAT is live          │
             └──────────────────────────────────────────────┘
                              │
WEEK 10+     ┌──────────────────────────────────────────────┐
             │  B. Browser Edge Phase 4 (P2P WebRTC)        │
             │  C. Edge Agent Waves C+D (browsing, memory)  │
             │                                              │
             │  Ships: Advanced features                    │
             │  Result: Platform maturity                    │
             └──────────────────────────────────────────────┘
```

---

## Why Browser Edge MUST Come After Cloud Launch (Not Before)

| Reason | Explanation |
|--------|------------|
| **Sync needs a target** | BrowserSqliteProvider syncs WITH the cloud edge. If cloud doesn't exist yet, there's nothing to sync to. |
| **Publish pipeline feeds it** | Browser offline mode caches **published pages**. The publish pipeline + Turso state DB must be working first. |
| **Schema depends on tenants** | The sync protocol needs `tenant_id` — which doesn't exist until cloud launch adds it. |
| **You can't demo offline without online** | Enterprise buyers first need to see it working online, THEN you blow their minds by turning off the WiFi. |
| **User feedback shapes priorities** | Real users on the cloud alpha will tell you WHICH offline scenarios matter most. |

## Why Browser Edge MUST Come Before Enterprise Sales Ramp (Not After)

| Reason | Explanation |
|--------|------------|
| **It's the differentiation** | Every competitor has "cloud hosted no-code." Only Frontbase has "works on a Raspberry Pi with no internet." |
| **It closes the deal** | Show an airline exec a kiosk that keeps working when you unplug the ethernet. That's a $500K conversation. |
| **Your case studies demand it** | The aviation, telecom, oil & gas case studies all center on "what happens when connectivity dies." Browser edge IS the answer. |

---

## The Raspberry Pi Hardware Play

> [!IMPORTANT]
> The `browser-edge-runtime-plan.md` currently only covers the browser PWA side. Your new vision adds a **hardware layer**: a Raspberry Pi running the Hono edge engine as a local network appliance.

### What This Looks Like Architecturally

```
Raspberry Pi (ARM, 1-8 GB RAM, WiFi/Ethernet)
  └─ Node.js 20
      └─ Hono Edge Engine (same codebase as CF Worker)
          └─ SQLite (local state DB)
          └─ Redis (optional, via Upstash or local)
          └─ WiFi AP mode (optional: Pi IS the network)

Local devices connect to Pi's IP on the LAN:
  iPad/Laptop/Phone → http://192.168.1.50:3002/
  → Hono serves SSR pages
  → Forms submit to local SQLite
  → When WAN restores: Pi syncs to cloud Turso
```

### What Makes This Work Today

The edge engine **already runs on Docker/Node.js** (`services/edge/Dockerfile`). A Raspberry Pi 4/5 runs Node.js 20 natively. The entire edge engine including SSR and workflows would work on a $35 Raspberry Pi with zero code changes.

What's needed:
1. **ARM Docker image** (multi-platform build in existing Dockerfile)
2. **WiFi AP mode script** (optional: Pi creates its own hotspot for zero-infra environments)
3. **Auto-sync on WAN resume** (merge browser offline queues → Pi SQLite → cloud Turso)
4. **Pre-flash SD card images** ("Frontbase Edge Box": plug in, power on, done)

### Revenue Angle

| Product | Price | Margin |
|---------|-------|--------|
| Frontbase Edge Box (Pi 5 + case + SD card) | $149 | ~70% (Pi cost ~$45) |
| Frontbase Edge Box Pro (Pi 5 + PoE + industrial case) | $299 | ~65% |
| Annual Edge Support License | $999/year | ~95% (pure support) |
| Enterprise Fleet Management (100+ boxes) | Custom | High |

---

## Updated Enterprise Vision Alignment

The enterprise-vision.md should be updated to include the **5-layer resilience stack** as the centerpiece differentiator:

| Tier | Product | Revenue |
|------|---------|---------|
| Free | Cloud Builder + shared CF Worker | $0 (acquisition) |
| Pro | Dedicated edge + custom domain | $19-49/mo |
| Business | Team + white label + BYOE | $49-149/mo |
| **Enterprise** | **Self-hosted + Browser Edge + Raspberry Pi fleet** | **$10K-500K/year** |
| **Enterprise Managed** | **We manage your fleet of edge boxes** | **$50K-500K/year** |

---

## Summary: The Recommended Order

| Priority | Work Stream | When | Strategic Purpose |
|----------|------------|------|------------------|
| 🔴 **1** | Cloud Alpha Launch + PydanticAI fix | **Week 1-2** | Get users in, prove platform works |
| 🟡 **2** | Workspace Agent Phase 2 (Waves 1-2) | **Week 3** | Polish demos for enterprise buyers |
| 🟡 **3** | Edge Agent Waves A+B (MCP + Channels) | **Week 4-5** | "Your app responds on Telegram" |
| 🔴 **4** | Browser Edge Runtime (Phases 1-3) + Pi | **Week 6-9** | The MOAT. Closes enterprise deals. |
| 🟢 **5** | P2P WebRTC + Edge Agent C+D | **Week 10+** | Advanced capabilities, maturity |

> [!IMPORTANT]
> **The Browser Edge + Raspberry Pi is your single most defensible feature.**
> But it needs cloud launch as its foundation (sync target, publish pipeline, tenant model).
> Build cloud first → then make it indestructible.
