-- 005_embedding_dimension.sql — fresh-install parity with prod's reconciled
-- state (TASK-261 residual closure, 2026-10-17).
--
-- Prod's memories.embedding is vector(1536) WITH the HNSW index
-- (idx_memories_embedding) — a MANUAL cutover-day step that no migration
-- performs: the frozen 001 baseline is dimensionless, and 002's guard only
-- creates the index when the column is ALREADY dimensioned (002's "reproduce
-- prod exactly / no HNSW on prod" comment was stale the day it shipped —
-- prod was dimensioned by hand after the baseline was frozen). Fresh installs
-- therefore stayed dimensionless and unindexed: functional, but semantic
-- search runs a sequential scan over memories forever.
--
-- This file is the follow-on — 002 is already executed on prod and is never
-- edited. On prod this migration is a guarded no-op (stamp only): the column
-- already carries typmod 1536 and the index already exists. On fresh installs
-- it dimensions the column and builds the index, matching prod exactly.
--
-- The ALTER is intentionally UNGUARDED against stored vectors: a dimensioned
-- ALTER over non-1536 vectors raises and aborts boot loudly — the correct
-- posture, never silently scan forever.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
        WHERE c.relname = 'memories'
          AND a.attname = 'embedding'
          AND a.atttypmod <= 0
    ) THEN
        ALTER TABLE memories ALTER COLUMN embedding TYPE vector(1536);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);
