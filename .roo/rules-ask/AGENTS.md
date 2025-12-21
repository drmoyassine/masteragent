# Project Documentation Rules (Non-Obvious Only)

- Backend configuration: `backend/.env` file (not root .env) contains all environment variables
- Frontend configuration: `frontend/.env` file must contain `REACT_APP_BACKEND_URL=http://localhost:8001`
- Database initialization: `init_db()` function in `backend/server.py` creates all tables and seeds default templates
- Design specifications: `design_guidelines.json` contains complete UI/UX guidelines including typography, colors, and component styles
- API documentation: FastAPI auto-generates docs at `/docs` endpoint in backend
- GitHub integration: Repository settings stored per-user in `settings` table, not environment variables
- Frontend routing: Uses React Router with protected routes and authentication context
- Build configuration: `docker-compose.yml` service name is `promptsrc` (not the project name)
- Variable templates: Mustache-style `{{variable}}` syntax used throughout prompt templates
- Authentication flow: GitHub OAuth redirects to `/auth/callback` with JWT token in URL