# Project Coding Rules (Non-Obvious Only)

- Always use `get_db_context()` context manager for database operations in `backend/server.py` - never call `get_db()` directly
- Frontend components MUST use named exports, pages MUST use default exports
- Database file is `backend/prompt_manager.db` - initialize with `init_db()` function
- Free plan limits exactly 1 prompt (enforced in `create_prompt()` endpoint)
- API keys must use `pm_` prefix and are stored plaintext with preview
- Variable injection uses `{{variable}}` syntax with Mustache-style replacement in templates
- GitHub operations require the custom `github_api_request()` wrapper function
- Frontend uses CRACO configuration with conditional plugin loading
- Path alias `@` maps to `frontend/src/` directory
- JWT tokens expire in 30 days (hardcoded in `backend/server.py`)
- GitHub tokens are stored in plaintext in the database `settings` table