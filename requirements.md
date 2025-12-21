# Prompt Manager Microservice - Requirements & Architecture

## Original Problem Statement
Build a **prompt-as-code management system** that allows prompt engineers and non-technical users to create, manage, version, and consume complex AI prompts as **structured, multi-file Markdown assets**, fully versioned in GitHub and consumable via a clean HTTP API.

## User Requirements Implemented
1. **GitHub Integration**: User connects their GitHub from the UI during initial setup/configuration
2. **Authentication**: Email/password as primary method + GitHub OAuth as optional
3. **Database**: SQLite for metadata storage
4. **Starter Templates**: Pre-compiled sections that auto-generate all section MD files when selected
5. **Landing Page**: Marketing page with features and pricing
6. **Pricing Plans**: Free (1 prompt) and Pro ($9.99/month, unlimited)
7. **Deployment**: Dockerfile and docker-compose.yml for containerized deployment

## Architecture

### Tech Stack
- **Backend**: FastAPI (Python) with SQLite + JWT auth + bcrypt password hashing
- **Frontend**: React with Tailwind CSS + Shadcn/UI
- **Source of Truth**: GitHub Repository (for prompt content)
- **Authentication**: Email/Password + GitHub OAuth (optional)

### Database Schema (SQLite)
- `users` - User accounts (email, password_hash, username, github_id, plan)
- `settings` - GitHub repo configuration per user
- `prompts` - Prompt metadata (id, user_id, name, description, folder_path)
- `prompt_versions` - Version mappings (branch names)
- `templates` - Starter templates with pre-defined sections
- `api_keys` - API key authentication for render endpoint

### Core API Endpoints
**Authentication:**
- `POST /api/auth/signup` - Register with email/password
- `POST /api/auth/login` - Login with email/password
- `GET /api/auth/github/login` - Initiate GitHub OAuth (optional)
- `GET /api/auth/github/callback` - GitHub OAuth callback
- `GET /api/auth/status` - Check auth status

**Protected Resources:**
- `GET/POST /api/settings` - GitHub repo configuration
- `GET/POST/PUT/DELETE /api/prompts` - Prompt CRUD
- `GET/POST/PUT/DELETE /api/prompts/{id}/sections` - Section management
- `POST /api/prompts/{id}/{version}/render` - Render compiled prompt
- `GET/POST/DELETE /api/keys` - API key management
- `GET /api/templates` - Starter templates

### Pricing Plans
- **Free**: 1 prompt, unlimited sections, GitHub versioning, Render API access
- **Pro ($9.99/month)**: Unlimited prompts, priority support, team collaboration (soon)

## Deployment

### Docker Deployment
```bash
# Build and run with docker-compose
docker-compose up -d

# Or build manually
docker build -t promptsrc .
docker run -p 80:80 \
  -e JWT_SECRET_KEY=your_secret \
  -e FRONTEND_URL=https://your-domain.com \
  promptsrc
```

### Environment Variables
| Variable | Description | Required |
|----------|-------------|----------|
| `JWT_SECRET_KEY` | Secret for JWT tokens | Yes |
| `FRONTEND_URL` | Frontend URL for redirects | Yes |
| `GITHUB_CLIENT_ID` | GitHub OAuth App ID | No (optional) |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App Secret | No (optional) |
| `GITHUB_REDIRECT_URI` | OAuth callback URL | No (optional) |

## Tasks Completed (v1)
- [x] Landing page with hero, features, pricing sections
- [x] Email/password sign-up and sign-in forms
- [x] GitHub OAuth as optional sign-in method
- [x] JWT-based session management with bcrypt password hashing
- [x] Protected app routes behind authentication
- [x] User profile in sidebar with plan badge
- [x] Setup page for GitHub repo connection (protected)
- [x] Dashboard with prompts list
- [x] Prompt editor with sections sidebar
- [x] Markdown editor for section content
- [x] Version selector (GitHub branches)
- [x] Render endpoint with variable injection
- [x] API Keys management page
- [x] Templates page with preview
- [x] Settings page with disconnect option
- [x] Free plan limit (1 prompt) enforcement
- [x] Dockerfile and docker-compose.yml for deployment
- [x] Dark theme "retro-futurist" design

## Next Tasks (v1.1)
- [ ] Stripe integration for Pro plan payments
- [ ] Password reset flow
- [ ] Drag-and-drop section reordering UI
- [ ] Real-time variable highlighting in editor
- [ ] Version diff comparison
- [ ] Team collaboration features

## v2 Planned Features
- Structured role outputs (system/developer/user)
- Marketplace-ready templates
- Multi-tenant support
- Analytics dashboard
