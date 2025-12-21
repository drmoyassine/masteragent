# Project Debug Rules (Non-Obvious Only)

- Database connection errors: SQLite file location is `backend/prompt_manager.db` - check file permissions
- JWT token validation errors: Check `JWT_SECRET_KEY` environment variable in `backend/.env`
- GitHub API errors (HTTP 401): Verify GitHub token has proper repository permissions
- CORS errors: Check `CORS_ORIGINS` environment variable (defaults to `*`)
- Frontend build failures: Clear `frontend/node_modules` and run `yarn install` again
- API connection failures: Check `REACT_APP_BACKEND_URL=http://localhost:8001` in `frontend/.env`
- Authentication loop: Clear localStorage and verify token validation logic
- Webpack dev server issues: Health check plugin logs to specific endpoints when `ENABLE_HEALTH_CHECK=true`
- Database context manager failures: All DB operations must use `get_db_context()` not `get_db()`
- GitHub OAuth callback errors: Check `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and `GITHUB_REDIRECT_URI` env vars