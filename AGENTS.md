# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Build/Lint/Test Commands

**Backend:**
- `cd backend && python -m uvicorn server:app --reload --host 0.0.0.0 --port 8001` - Start development server
- `cd backend && python -m pytest tests/ -v` - Run tests
- `black .` - Format code (88 char line limit)
- `isort .` - Sort imports

**Frontend:**
- `cd frontend && yarn start` - Start development server
- `cd frontend && yarn test` - Run tests  
- `cd frontend && yarn build` - Production build

**Docker:**
- `docker-compose up -d` - Start all services (service name: `promptsrc`)

## Critical Non-Obvious Patterns

**Database Operations (backend/server.py):**
- ALL database operations MUST use `get_db_context()` context manager - never use `get_db()` directly
- Database file location: `backend/prompt_manager.db` 
- Custom `init_db()` function creates all tables and seeds data

**Frontend Configuration:**
- Uses CRACO, not standard Create React App
- Custom webpack plugins in `frontend/plugins/` load conditionally during development only
- Path alias: `@` maps to `frontend/src/`
- Components require named exports, pages require default exports

**GitHub Integration:**
- Use custom `github_api_request()` wrapper for all GitHub operations
- Repository settings stored per-user in `settings` table
- GitHub OAuth has custom redirect handling to `/auth/callback`

**Business Rules:**
- Free plan limited to exactly 1 prompt (enforced in `create_prompt()`)
- API keys use `pm_` prefix and store plaintext with preview functionality
- JWT tokens expire in 30 days
- Variable injection uses `{{variable}}` syntax with Mustache-style replacement

**Environment Setup:**
- Backend env vars loaded from `backend/.env` (not root .env)
- Frontend requires `REACT_APP_BACKEND_URL=http://localhost:8001` in `frontend/.env`
- Docker service named `promptsrc` with volume mount to `backend/`

**Security:**
- Passwords hashed with bcrypt
- GitHub tokens stored in plaintext in database
- CORS allows all origins by default (`CORS_ORIGINS=*`)

**Deployment Patterns:**
- Backend must be started before frontend for proper CORS configuration
- Environment files: `backend/.env` (not root .env) and `frontend/.env`
- Admin user seeded automatically: `admin@promptsrc.com` / `admin123`
- Database auto-initializes on startup with default templates
- CRACO middleware loads conditionally (development vs production)
- CORS middleware must be added BEFORE router inclusion to work properly
- Service name in docker-compose.yml is `promptsrc`, not the project name
- Frontend serves on both port 3000 and 3001 (Emergent platform)
- Backend authentication API tested and working with JWT token generation
- CORS import path changed from `starlette.middleware.cors` to `fastapi.middleware.cors`