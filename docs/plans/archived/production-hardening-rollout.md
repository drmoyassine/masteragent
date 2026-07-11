# Production Hardening Rollout (Completed and Archived)

This release is schema-additive and keeps legacy routes, prompt keys, webhook
signatures, and agent visibility behavior during the initial rollout.

## Before deployment

1. Back up PostgreSQL and the prompt storage volumes.
2. Set a stable `DATA_ENCRYPTION_KEY` and retain it in the secret manager. Do not
   rotate it without first re-encrypting stored credentials.
3. Set strong `JWT_SECRET_KEY`, `ADMIN_PASSWORD`, `MCP_SERVICE_KEY`, and
   `POSTGRES_PASSWORD` values.
4. Keep these compatibility controls for the first deployment:
   - `STRICT_STARTUP_VALIDATION=false`
   - `ENFORCE_AGENT_SCOPE=false`
   - `REQUIRE_WEBHOOK_TIMESTAMP=false`
   - `LEGACY_PROMPT_KEYS_GLOBAL=true`
5. Deploy one application replica first. Startup serializes schema changes with
   a PostgreSQL advisory lock and encrypts legacy credentials in place.

## Verification

- Log in with the configured administrator and confirm Memory Settings loads.
- Preview a prompt and render it with an existing prompt API key.
- Ingest one interaction and wait for its queue job to complete.
- Verify existing inbound webhooks. Legacy and standard HMAC signatures are accepted.
- Confirm health and both MCP endpoints.

## Tighten after verification

1. Set `STRICT_STARTUP_VALIDATION=true`.
2. Review `memory_agent_entities`, then set `ENFORCE_AGENT_SCOPE=true`.
3. Replace legacy unowned prompt keys, then set `LEGACY_PROMPT_KEYS_GLOBAL=false`.
4. Add a current epoch `X-Webhook-Timestamp` to webhook senders and sign
   `<timestamp>.<raw-body>`, then set `REQUIRE_WEBHOOK_TIMESTAMP=true`.
5. Set `ALLOW_PUBLIC_SIGNUP=false` unless public registration is intentional.
6. Keep `ALLOW_PRIVATE_DOCUMENT_URLS=false` unless network-level egress controls exist.

## Rollback

New columns and tables are ignored by older releases. Older releases cannot read
credentials encrypted by this release, so rollback requires the pre-deployment
database backup or retaining the new credential reader.
