# Project Architecture Rules (Non-Obvious Only)

- Database layer: SQLite with custom `get_db_context()` context manager for transaction safety
- API structure: FastAPI with single `backend/server.py` file containing all endpoints (1258 lines)
- Frontend architecture: React with CRACO (not standard CRA), conditional plugin loading system
- Authentication: JWT tokens with 30-day expiry, bcrypt password hashing, GitHub OAuth integration
- GitHub integration: Per-user repository settings stored in `settings` table, custom `github_api_request()` wrapper
- Prompt management: Templates stored in GitHub as markdown files with version control via branches
- Variable injection: Mustache-style `{{variable}}` replacement in compiled prompts
- Business logic: Free plan strictly limited to 1 prompt, API keys use `pm_` prefix pattern
- Environment separation: Backend env vars in `backend/.env`, frontend requires `REACT_APP_BACKEND_URL` in `frontend/.env`
- Security considerations: CORS allows all origins, GitHub tokens stored plaintext, JWT secret configurable
- Build system: Docker service named `promptsrc` with volume mounting to backend directory