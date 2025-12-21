# Prompt Manager Microservice - Requirements & Architecture

## Original Problem Statement
Build a **prompt-as-code management system** that allows prompt engineers and non-technical users to create, manage, version, and consume complex AI prompts as **structured, multi-file Markdown assets**, fully versioned in GitHub and consumable via a clean HTTP API.

## User Requirements Implemented
1. **GitHub Integration**: User connects their GitHub from the UI during initial setup/configuration
2. **Authentication**: Simple API key-based authentication
3. **Database**: SQLite for metadata storage
4. **Starter Templates**: Pre-compiled sections that auto-generate all section MD files when selected

## Architecture

### Tech Stack
- **Backend**: FastAPI (Python) with SQLite
- **Frontend**: React with Tailwind CSS + Shadcn/UI
- **Source of Truth**: GitHub Repository (for prompt content)

### Database Schema (SQLite)
- `settings` - GitHub configuration (token, owner, repo)
- `prompts` - Prompt metadata (id, name, description, folder_path)
- `prompt_versions` - Version mappings (branch names)
- `templates` - Starter templates with pre-defined sections
- `api_keys` - API key authentication

### Core API Endpoints
- `GET/POST /api/settings` - GitHub configuration
- `GET/POST/PUT/DELETE /api/prompts` - Prompt CRUD
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

### Variable System
- Mustache-style placeholders: `{{variable_name}}`
- Variables extracted automatically from content
- Required variables validated during render
- JSON payload injection at render time

## Tasks Completed (v1 MVP)
- [x] Setup page with GitHub connection
- [x] Dashboard with prompts list
- [x] Prompt editor with sections sidebar
- [x] Markdown editor for section content
- [x] Version selector (GitHub branches)
- [x] Render endpoint with variable injection
- [x] API Keys management page
- [x] Templates page with preview
- [x] Settings page with disconnect option
- [x] Dark theme "retro-futurist" design
- [x] SQLite database initialization
- [x] Default templates seeding

## Next Tasks (v1.1)
- [ ] Drag-and-drop section reordering UI
- [ ] Real-time variable highlighting in editor
- [ ] Manifest.json auto-update on section changes
- [ ] Version diff comparison
- [ ] Template customization (create custom templates)
- [ ] Prompt search and filtering
- [ ] Bulk operations (delete multiple prompts)
- [ ] Export/Import functionality

## v2 Planned Features
- Structured role outputs (system/developer/user)
- Marketplace-ready templates
- Multi-tenant support
- Frontbase native integration
