"""memory_system — MasterAgent memory pipeline package.

Subpackages:
  ingest/    interaction ingestion + per-agent rate limiting
  distill/   the knowledge distillation tiers (memories → intelligence →
             knowledge → skills/telemetry, evidence routing, facets)
  maintain/  consolidation, clustering/similarity, quality, skill-md rendering,
             embedding machinery + backfill, operation metrics, retention
  store/     DB writes, pydantic models, shared entity-type helpers
  scheduler  the 60-second background tier scheduler (companion to the
             memory.queue worker)

Deliberately import-free: internal modules import subpackages directly and
external callers (server.py, core.startup) name the submodule they need —
keeps package init free of import cycles.
"""
