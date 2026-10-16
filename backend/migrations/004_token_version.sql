-- TASK-259 item 7: per-user JWT revocation counter.
-- create_access_token stamps users.token_version as the 'tver' claim;
-- get_current_user refuses any token whose tver is missing or stale.
-- A token WITHOUT the claim is invalid (clean-slate session revocation —
-- every JWT issued before this deploy stops working; re-login required).
-- Bump a user's token_version to invalidate all their outstanding tokens.
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;
