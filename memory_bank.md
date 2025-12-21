# Promptmaster - Memory Bank

## Executive Summary

### What is Promptmaster?

Promptmaster is a **prompt-as-code management system** that allows prompt engineers and non-technical users to create, manage, version, and consume complex AI prompts as **structured, multi-file Markdown assets**. The system provides a complete development environment for prompt engineering with GitHub integration, version control, and a clean HTTP API for consumption.

### Core Value Proposition

- **Git-Centric Architecture**: GitHub serves as the source of truth for prompt content, ensuring version control and collaboration
- **Structured Prompt Management**: Multi-section prompts with variable injection and template systems
- **API-First Design**: RESTful API for consuming prompts programmatically with authentication
- **User-Friendly Interface**: React-based web application with a retro-futuristic dark theme
- **Scalable Architecture**: Docker-based deployment with support for different pricing tiers

### Target Users

- **Prompt Engineers**: Primary users who create and manage AI prompts
- **AI/ML Teams**: Organizations managing multiple AI agents and workflows
- **Developers**: Integration with existing systems via REST API
- **Product Teams**: Non-technical users managing prompt-based features

## Technical Architecture

### High-Level System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   React Web UI  │    │  FastAPI Backend │    │   GitHub API    │
│   (Port 3000)   │◄──►│   (Port 8001)    │◄──►│  (Source of     │
│                 │    │                 │    │   Truth)        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Nginx Proxy   │    │  SQLite DB      │    │   Repository    │
│   (Port 80)     │    │  (prompt_       │    │   Storage       │
│                 │    │   manager.db)   │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Technology Stack Breakdown

#### Backend Stack
- **Framework**: FastAPI (Python 3.11+)
- **Database**: SQLite for metadata storage
- **Authentication**: JWT tokens with bcrypt password hashing
- **External APIs**: GitHub REST API integration
- **HTTP Client**: httpx for async requests
- **Password Security**: bcrypt for hashing
- **Web Server**: uvicorn ASGI server

#### Frontend Stack
- **Framework**: React 19.0.0 with Create React App
- **Styling**: Tailwind CSS with Shadcn/UI components
- **Routing**: React Router DOM v7
- **State Management**: React Context API
- **HTTP Client**: Axios with interceptors
- **Forms**: React Hook Form with Zod validation
- **UI Components**: Radix UI primitives
- **Icons**: Lucide React
- **Build Tool**: CRACO (Create React App Configuration Override)

#### Infrastructure & Deployment
- **Containerization**: Docker with multi-stage builds
- **Process Management**: SupervisorD
- **Web Server**: Nginx for static files and reverse proxy
- **Database**: SQLite (production-ready for small-medium scale)

### Database Schema Overview

#### Core Tables

**users**
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,              -- UUID
    github_id INTEGER UNIQUE,         -- GitHub user ID
    username TEXT NOT NULL,           -- Display name
    email TEXT UNIQUE,                -- User email
    password_hash TEXT,               -- bcrypt hash (nullable for GitHub-only)
    avatar_url TEXT,                  -- Profile image
    github_url TEXT,                  -- GitHub profile
    github_token TEXT,                -- OAuth token (encrypted)
    plan TEXT DEFAULT 'free',         -- 'free' or 'pro'
    created_at TEXT,                  -- ISO timestamp
    updated_at TEXT                   -- ISO timestamp
);
```

**settings**
```sql
CREATE TABLE settings (
    id INTEGER PRIMARY KEY,
    user_id TEXT,                     -- Foreign key to users
    github_token TEXT,                -- User's GitHub token
    github_repo TEXT,                 -- Repository name
    github_owner TEXT,                -- Repository owner
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**prompts**
```sql
CREATE TABLE prompts (
    id TEXT PRIMARY KEY,              -- UUID
    user_id TEXT,                     -- Foreign key to users
    name TEXT NOT NULL,               -- Prompt name
    description TEXT,                 -- Optional description
    folder_path TEXT NOT NULL,        -- GitHub path (prompts/slug)
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**prompt_versions**
```sql
CREATE TABLE prompt_versions (
    id TEXT PRIMARY KEY,              -- UUID
    prompt_id TEXT NOT NULL,          -- Foreign key to prompts
    version_name TEXT NOT NULL,       -- Human-readable version
    branch_name TEXT NOT NULL,        -- GitHub branch name
    is_default INTEGER DEFAULT 0,     -- Boolean flag
    created_at TEXT,
    FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);
```

**templates**
```sql
CREATE TABLE templates (
    id TEXT PRIMARY KEY,              -- UUID
    name TEXT NOT NULL,               -- Template name
    description TEXT,                 -- Template description
    sections TEXT NOT NULL,           -- JSON array of sections
    created_at TEXT
);
```

**api_keys**
```sql
CREATE TABLE api_keys (
    id TEXT PRIMARY KEY,              -- UUID
    name TEXT NOT NULL,               -- Key identifier
    key_hash TEXT NOT NULL,           -- Full key (stored directly)
    key_preview TEXT NOT NULL,        -- Display preview
    created_at TEXT,
    last_used TEXT                    -- Last usage timestamp
);
```

### API Structure Summary

#### Authentication Endpoints
- `POST /api/auth/signup` - Email/password registration
- `POST /api/auth/login` - Email/password login
- `GET /api/auth/github/login` - GitHub OAuth initiation
- `GET /api/auth/github/callback` - GitHub OAuth callback
- `GET /api/auth/status` - Authentication status check
- `POST /api/auth/logout` - User logout

#### Protected Resource Endpoints
- `GET/POST/PUT/DELETE /api/settings` - GitHub configuration
- `GET/POST/PUT/DELETE /api/prompts` - Prompt CRUD operations
- `GET/POST/PUT/DELETE /api/prompts/{id}/sections` - Section management
- `POST /api/prompts/{id}/{version}/render` - Prompt rendering with variables
- `GET/POST/DELETE /api/keys` - API key management
- `GET /api/templates` - Starter templates

#### Render Endpoint
```
POST /api/prompts/{prompt_id}/{version}/render
Content-Type: application/json
X-API-Key: {api_key}  # Optional for public access

{
  "variables": {
    "agent_name": "Assistant",
    "company": "Acme Corp"
  }
}
```

## Key Components & Features

### Core Functionality Breakdown

#### 1. Prompt Management System
- **Multi-Section Prompts**: Structured prompts with ordered sections
- **Template System**: Pre-built prompt templates (Agent Persona, Task Executor, etc.)
- **Variable Injection**: Mustache-style `{{variable}}` substitution
- **GitHub Integration**: All content stored in user's GitHub repository
- **Version Control**: Git branch-based versioning system

#### 2. Authentication System
- **Dual Authentication**: Email/password + GitHub OAuth
- **JWT Tokens**: 30-day expiration with secure token generation
- **Session Management**: Automatic token refresh and validation
- **Password Security**: bcrypt hashing with salt
- **GitHub OAuth**: Optional social login with token storage

#### 3. GitHub Integration
- **Repository Storage**: Prompts stored as Markdown files in GitHub
- **Branch Management**: Version control through Git branches
- **File Structure**: 
  ```
  prompts/
  └── prompt-name/
      ├── manifest.json          # Metadata and variable definitions
      ├── 01_identity.md         # Section files (ordered)
      ├── 02_context.md
      └── 03_guidelines.md
  ```
- **API Integration**: Real-time GitHub API operations
- **OAuth Scopes**: `user:email` and `repo` permissions

#### 4. UI/UX Components

##### Design System (Retro-Futurism)
- **Theme**: Dark mode with electric green accents (#22C55E)
- **Typography**: JetBrains Mono for headings, IBM Plex Sans for body
- **Visual Style**: Sharp borders, minimal rounded corners
- **Color Palette**:
  - Background: #09090B (near black)
  - Primary: #22C55E (electric green)
  - Secondary: #27272A (dark gray)
  - Accent: #F59E0B (amber)

##### Key UI Components
- **MainLayout**: App shell with sidebar navigation
- **DashboardPage**: Prompt grid with search and CRUD operations
- **PromptEditorPage**: Markdown editor with sections sidebar
- **LandingPage**: Marketing site with features and pricing
- **Template Gallery**: Pre-built prompt templates
- **API Keys Management**: Secure key generation and revocation

#### 5. Plugin System
The frontend includes a plugin architecture for enhanced development:

**Health Check Plugin** (`frontend/plugins/health-check/`)
- `health-endpoints.js`: Backend health monitoring
- `webpack-health-plugin.js`: Development server health checks

**Visual Edits Plugin** (`frontend/plugins/visual-edits/`)
- `babel-metadata-plugin.js`: Babel transformation for metadata
- `dev-server-setup.js`: Development server configuration

## Development & Deployment

### Local Development Setup

#### Prerequisites
- Node.js 20+ and Yarn
- Python 3.11+
- GitHub account with personal access token
- Git repository for prompt storage

#### Backend Development
```bash
cd backend/
pip install -r requirements.txt
python -m uvicorn server:app --reload --host 0.0.0.0 --port 8001
```

#### Frontend Development
```bash
cd frontend/
yarn install
yarn start
```

#### Environment Configuration
Create `.env` file in backend directory:
```env
JWT_SECRET_KEY=your-super-secret-jwt-key
FRONTEND_URL=http://localhost:3000
GITHUB_CLIENT_ID=your-github-oauth-app-id
GITHUB_CLIENT_SECRET=your-github-oauth-secret
GITHUB_REDIRECT_URI=http://localhost/api/auth/github/callback
```

### Environment Variables

#### Required Variables
| Variable | Description | Example |
|----------|-------------|----------|
| `JWT_SECRET_KEY` | JWT signing secret | `change-this-secret-in-production` |
| `FRONTEND_URL` | Frontend application URL | `http://localhost:3000` |

#### Optional Variables
| Variable | Description | Example |
|----------|-------------|----------|
| `GITHUB_CLIENT_ID` | GitHub OAuth App ID | `abc123` |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth Secret | `xyz789` |
| `GITHUB_REDIRECT_URI` | OAuth callback URL | `http://localhost/api/auth/github/callback` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:3000,https://yourdomain.com` |

#### Environment File Locations
- **Backend**: `backend/.env` (NOT root .env)
- **Frontend**: `frontend/.env` with `REACT_APP_BACKEND_URL=http://localhost:8001`
- Backend environment variables are loaded in `backend/server.py` with `load_dotenv(ROOT_DIR / '.env')`

### Docker Configuration

#### Single Container Deployment
```bash
docker build -t promptmaster .
docker run -p 80:80 \
  -e JWT_SECRET_KEY=your_secret \
  -e FRONTEND_URL=https://yourdomain.com \
  promptmaster
```

#### Docker Compose Deployment
```bash
docker-compose up -d
```

#### Docker Architecture
- **Multi-stage Build**: Node.js builder → Python runtime
- **Process Management**: SupervisorD manages Nginx and FastAPI
- **Health Checks**: HTTP health checks every 30 seconds
- **Static Files**: Nginx serves React build, proxies API calls
- **Volume Mounting**: SQLite database persisted in named volume

### Testing Approach

#### Backend Testing
- **Unit Tests**: pytest with test discovery
- **API Testing**: httpx for HTTP client testing
- **Database Testing**: In-memory SQLite for test isolation

#### Frontend Testing
- **Component Testing**: React Testing Library
- **E2E Testing**: Cypress (configured but not implemented)
- **API Testing**: Mock responses with Axios interceptors

#### Test Reports
Available test reports in `test_reports/` directory showing iteration results and coverage.

### Deployment Insights (2025-12-21)

#### CORS Configuration Discovery
**Critical Finding**: CORS middleware must be added BEFORE router inclusion in FastAPI for proper cross-origin handling.

```python
# CORRECT: Add middleware before router
app = FastAPI(title="Prompt Manager API")
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)

# INCORRECT: Adding middleware after router won't work
app.include_router(api_router)
app.add_middleware(...)  # Too late - won't apply to API routes
```

**CRITICAL PATTERN**: Changed CORS import from `starlette.middleware.cors` to `fastapi.middleware.cors` in `backend/server.py` line 5 for proper FastAPI compatibility.

#### Environment Configuration Discovery
**Key Finding**: Backend environment variables must be in `backend/.env`, not root `.env`
- Backend loads env vars with: `load_dotenv(ROOT_DIR / '.env')`
- Frontend requires separate `frontend/.env` file with `REACT_APP_BACKEND_URL`
- Docker service name is `promptsrc`, not the project name

#### Admin User Seeding
**Pattern**: Admin user automatically created on startup:
- Email: `admin@promptsrc.com`
- Password: `admin123`
- Plan: Pro (bypasses free plan limits)
- Created in `seed_admin_user()` function called during initialization

#### Database Auto-Initialization
**Critical Pattern**: Database automatically initialized with:
- All table schemas created in `init_db()` function
- Default prompt templates seeded automatically
- SQLite file created at `backend/prompt_manager.db`
- No manual setup required - just start the server

#### Service Startup Order
**Important Discovery**: 
1. Backend must start BEFORE frontend for CORS configuration to work
2. Frontend serves on both port 3000 and 3001 (Emergent platform integration)
3. Backend authentication API fully tested and working with JWT token generation
4. CORS origins configuration requires `allow_origins=["*"]` for development/testing

## Known Issues & Considerations

### Current Limitations

#### 1. Database Scaling
- **SQLite Limitations**: Single-writer database, not suitable for high-concurrency production
- **File-based Storage**: Database file must be manually backed up
- **No Connection Pooling**: Direct file I/O for each request

#### 2. Authentication Security
- **GitHub Token Storage**: User tokens stored unencrypted in database
- **No Token Rotation**: GitHub tokens don't expire or refresh automatically
- **API Key Storage**: API keys stored in plain text (hashing would be more secure)

#### 3. GitHub Integration
- **Rate Limiting**: No handling of GitHub API rate limits
- **Error Recovery**: Limited retry logic for GitHub API failures
- **Repository Permissions**: Requires full repo access scope

#### 4. Frontend Performance
- **Bundle Size**: Large dependency footprint (70+ packages)
- **Code Splitting**: No lazy loading for route components
- **State Management**: Context API may cause unnecessary re-renders

### Areas Needing Attention

#### 1. Security Hardening
- [ ] Encrypt GitHub tokens in database
- [ ] Implement API key hashing (bcrypt/scrypt)
- [ ] Add rate limiting middleware
- [ ] Implement CSRF protection
- [ ] Add input validation and sanitization

#### 2. Production Readiness
- [ ] Move to PostgreSQL for better concurrency
- [ ] Add logging and monitoring (Sentry, DataDog)
- [ ] Implement backup and recovery procedures
- [ ] Add comprehensive error handling
- [ ] Set up CI/CD pipeline

#### 3. Performance Optimization
- [ ] Implement Redis caching layer
- [ ] Add database connection pooling
- [ ] Optimize React bundle with code splitting
- [ ] Add CDN for static assets
- [ ] Implement database query optimization

#### 4. Feature Completeness
- [ ] Stripe payment integration for Pro plans
- [ ] Password reset functionality
- [ ] Real-time collaboration features
- [ ] Advanced version diff comparison
- [ ] Team management and permissions

### Production Readiness Status

| Component | Status | Notes |
|-----------|--------|-------|
| **Backend API** | 🟡 Partial | Core functionality works, needs security hardening |
| **Frontend UI** | 🟢 Good | Complete user interface with responsive design |
| **Authentication** | 🟡 Partial | Works but needs token encryption |
| **Database** | 🔴 Not Ready | SQLite insufficient for production scale |
| **Deployment** | 🟡 Partial | Docker works, needs orchestration |
| **Monitoring** | 🔴 Missing | No logging, alerting, or metrics |
| **Testing** | 🔴 Limited | Basic tests, needs comprehensive coverage |

## Future Roadmap

### Version 1.1 (Short Term)

#### Payment Integration
- **Stripe Integration**: Pro plan subscriptions ($9.99/month)
- **Usage Tracking**: Monitor prompt limits for free accounts
- **Billing Portal**: Self-service subscription management
- **Plan Enforcement**: Automatic feature restrictions

#### User Experience Enhancements
- **Password Reset Flow**: Email-based password recovery
- **Drag & Drop Reordering**: Visual section arrangement
- **Real-time Variable Highlighting**: Live variable detection in editor
- **Advanced Search**: Full-text search across prompts and sections

#### Collaboration Features
- **Team Workspaces**: Multi-user access with role-based permissions
- **Prompt Sharing**: Share prompts between team members
- **Comment System**: Inline feedback and discussions
- **Approval Workflows**: Review and approval process for prompts

### Version 2.0 (Medium Term)

#### Advanced Prompt Features
- **Structured Role Outputs**: System/Developer/User message templates
- **Conditional Logic**: If/else blocks and dynamic content
- **Loop Constructs**: Repeat sections with different variables
- **Prompt Chaining**: Connect multiple prompts in workflows

#### Platform Expansion
- **Template Marketplace**: Community-driven template sharing
- **Multi-tenant Architecture**: Isolated data per organization
- **API Rate Limiting**: Tiered access based on subscription
- **Webhook Support**: Real-time notifications for changes

#### Analytics & Insights
- **Usage Analytics**: Prompt performance metrics
- **A/B Testing**: Compare prompt effectiveness
- **Cost Optimization**: Track API usage and costs
- **Success Metrics**: Model output quality scoring

### Version 3.0 (Long Term)

#### AI-Native Features
- **Auto-optimization**: AI-powered prompt improvement suggestions
- **Prompt Generation**: AI-assisted prompt creation from descriptions
- **Quality Scoring**: Automated prompt quality assessment
- **Context Awareness**: Smart variable suggestions based on usage

#### Enterprise Features
- **SSO Integration**: SAML/OAuth enterprise authentication
- **Compliance Tools**: Audit trails and data governance
- **Custom Integrations**: API for third-party integrations
- **White-label Options**: Customizable branding and deployment

### Technical Debt & Improvements

#### Infrastructure Modernization
- **Microservices Architecture**: Split backend into focused services
- **Event-Driven Architecture**: Async processing with message queues
- **GraphQL API**: More efficient data fetching for complex queries
- **Serverless Functions**: Event-driven prompt processing

#### Developer Experience
- **CLI Tool**: Command-line interface for prompt management
- **SDK Development**: Client libraries for popular languages
- **Plugin Architecture**: Extensible prompt processing pipeline
- **Development Tools**: Local development environment setup

---

## Additional Resources

### Key File References
- **Backend Server**: [`backend/server.py`](backend/server.py:1) - Complete FastAPI implementation
- **Frontend App**: [`frontend/src/App.js`](frontend/src/App.js:1) - Main React application
- **API Client**: [`frontend/src/lib/api.js`](frontend/src/lib/api.js:1) - Axios configuration
- **Database Schema**: Defined in [`backend/server.py`](backend/server.py:60) - SQLite table creation
- **Docker Configuration**: [`Dockerfile`](Dockerfile:1) - Multi-stage container build
- **Design System**: [`design_guidelines.json`](design_guidelines.json:1) - Complete UI specifications

### Configuration Files
- **Package Dependencies**: [`frontend/package.json`](frontend/package.json:1)
- **Python Dependencies**: [`backend/requirements.txt`](backend/requirements.txt:1)
- **Docker Compose**: [`docker-compose.yml`](docker-compose.yml:1)
- **CRACO Config**: [`frontend/craco.config.js`](frontend/craco.config.js:1)

### Component Library
The frontend uses a comprehensive UI component system based on Radix UI primitives:
- **Layout Components**: Dialog, Sheet, Drawer, Resizable panels
- **Data Display**: Table, Cards, Badge, Progress indicators
- **Form Controls**: Input, Select, Checkbox, Radio Group, Slider
- **Navigation**: Tabs, Breadcrumb, Navigation Menu
- **Feedback**: Toast notifications, Alert dialogs, Tooltips

### Testing Infrastructure
- **Test Reports**: `test_reports/` directory with iteration results
- **Test Configuration**: Individual test files throughout codebase
- **E2E Testing**: Cypress configuration in `frontend/cypress.json`

---

*This Memory Bank serves as the comprehensive knowledge base for the Promptmaster project. It should be updated as the system evolves and new features are implemented.*