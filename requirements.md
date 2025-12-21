# Prompt Manager Microservice - Requirements & Architecture

## Original Problem Statement
Build a **prompt-as-code management system** that allows prompt engineers and non-technical users to create, manage, version, and consume complex AI prompts as **structured, multi-file Markdown assets**, fully versioned in GitHub and consumable via a clean HTTP API.

## User Requirements Implemented
1. **GitHub Integration**: User connects their GitHub from the UI during initial setup/configuration
2. **Authentication**: GitHub OAuth sign-in/sign-up + Simple API key-based auth for render endpoint
3. **Database**: SQLite for metadata storage
4. **Starter Templates**: Pre-compiled sections that auto-generate all section MD files when selected
5. **Landing Page**: Marketing page with features and pricing
6. **Pricing Plans**: Free (1 prompt) and Pro ($9.99/month, unlimited)

## Architecture

### Tech Stack
- **Backend**: FastAPI (Python) with SQLite + JWT auth
- **Frontend**: React with Tailwind CSS + Shadcn/UI
- **Source of Truth**: GitHub Repository (for prompt content)
- **Authentication**: GitHub OAuth + JWT tokens

### Database Schema (SQLite)
- `users` - User accounts (github_id, username, email, plan, github_token)
- `settings` - GitHub repo configuration per user
- `prompts` - Prompt metadata (id, user_id, name, description, folder_path)
- `prompt_versions` - Version mappings (branch names)
- `templates` - Starter templates with pre-defined sections
- `api_keys` - API key authentication for render endpoint

### Core API Endpoints
- `GET /api/auth/github/login` - Initiate GitHub OAuth
- `GET /api/auth/github/callback` - GitHub OAuth callback
- `GET /api/auth/status` - Check auth status
- `GET/POST /api/settings` - GitHub repo configuration (protected)
- `GET/POST/PUT/DELETE /api/prompts` - Prompt CRUD (protected)
- `GET/POST/PUT/DELETE /api/prompts/{id}/sections` - Section management
- `POST /api/prompts/{id}/sections/reorder` - Drag-drop reordering
- `GET/POST /api/prompts/{id}/versions` - Version management
- `POST /api/prompts/{id}/{version}/render` - Render compiled prompt
- `GET/POST/DELETE /api/keys` - API key management
- `GET /api/templates` - Starter templates

### Default Templates Included
1. **Agent Persona** - Complete AI agent with identity, context, role, skills, guidelines (5 sections)
2. **Task Executor** - Focused task execution agent (3 sections)
3. **Knowledge Expert** - Domain-specific knowledge base (3 sections)
4. **Minimal Prompt** - Simple single-section prompt (1 section)

### Pricing Plans
- **Free**: 1 prompt, unlimited sections, GitHub versioning, Render API access
- **Pro ($9.99/month)**: Unlimited prompts, priority support, team collaboration (soon)

## Tasks Completed (v1)
- [x] Landing page with hero, features, pricing sections
- [x] GitHub OAuth sign-in/sign-up flow
- [x] JWT-based session management
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
- [x] Dark theme "retro-futurist" design

## Configuration Required
To enable GitHub OAuth, add to `/app/backend/.env`:
```
GITHUB_CLIENT_ID=your_github_oauth_app_client_id
GITHUB_CLIENT_SECRET=your_github_oauth_app_client_secret
```

Create a GitHub OAuth App at: https://github.com/settings/developers
- Authorization callback URL: `{FRONTEND_URL}/api/auth/github/callback`

## Next Tasks (v1.1)
- [ ] Stripe integration for Pro plan payments
- [ ] Drag-and-drop section reordering UI
- [ ] Real-time variable highlighting in editor
- [ ] Version diff comparison
- [ ] Template customization (create custom templates)
- [ ] Team collaboration features

## v2 Planned Features
- Structured role outputs (system/developer/user)
- Marketplace-ready templates
- Multi-tenant support
- Analytics dashboard
- Frontbase native integration
