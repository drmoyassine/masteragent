# AI Agent Guide - Promptmaster Project

This guide provides practical guidance for AI agents working with the Promptmaster codebase. It covers essential files, common workflows, development patterns, and troubleshooting approaches.

## Agent Quick Start

### Essential Files to Know

**Core Backend Files:**
- [`backend/server.py`](backend/server.py:1) - Main FastAPI application with all API endpoints
- [`backend/requirements.txt`](backend/requirements.txt:1) - Python dependencies
- [`backend/prompt_manager.db`](backend/prompt_manager.db:1) - SQLite database file

**Core Frontend Files:**
- [`frontend/src/App.js`](frontend/src/App.js:1) - Main React application with routing
- [`frontend/src/lib/api.js`](frontend/src/lib/api.js:1) - Axios API client configuration
- [`frontend/package.json`](frontend/package.json:1) - Node.js dependencies and scripts

**Configuration Files:**
- [`Dockerfile`](Dockerfile:1) - Container build configuration
- [`docker-compose.yml`](docker-compose.yml:1) - Multi-container deployment
- [`design_guidelines.json`](design_guidelines.json:1) - UI/UX design specifications
- [`requirements.md`](requirements.md:1) - Project requirements and architecture

**Documentation:**
- [`memory_bank.md`](memory_bank.md:1) - Comprehensive project knowledge base
- [`README.md`](README.md:1) - Basic project information

### Key Directories and Their Purposes

```
promptmaster/
├── backend/                 # FastAPI Python backend
│   ├── server.py           # Main application (1258 lines)
│   ├── requirements.txt    # Python dependencies
│   └── prompt_manager.db   # SQLite database
├── frontend/               # React frontend application
│   ├── src/
│   │   ├── App.js         # Main app with routing
│   │   ├── components/    # Reusable UI components
│   │   ├── pages/         # Route components
│   │   ├── lib/           # Utilities (api.js, utils.js)
│   │   └── context/       # React Context providers
│   ├── public/            # Static assets
│   └── package.json       # Dependencies
├── test_reports/          # Test execution results
└── tests/                 # Test files
```

### Common Workflows and Tasks

**Most Common Tasks:**
1. **UI Development**: Modify React components in `frontend/src/components/`
2. **API Development**: Add endpoints to `backend/server.py`
3. **Database Changes**: Update schema in `init_db()` function
4. **Authentication**: Modify JWT handling in `backend/server.py`
5. **GitHub Integration**: Update GitHub API calls in `github_api_request()`

## Codebase Navigation Guide

### Important Files and Their Purposes

#### Backend Architecture (`backend/server.py`)

**Database Setup (Lines 44-200):**
- `get_db()` - Database connection with row factory
- `get_db_context()` - Context manager for transactions
- `init_db()` - Creates all SQLite tables and seeds data

**Authentication System (Lines 26-287):**
- JWT token creation and verification
- Password hashing with bcrypt
- GitHub OAuth integration
- User session management

**API Endpoints by Category:**
- **Auth Endpoints (Lines 414-596)**: `/api/auth/*`
- **Settings Endpoints (Lines 651-711)**: `/api/settings`
- **Prompt Endpoints (Lines 739-905)**: `/api/prompts/*`
- **Section Endpoints (Lines 906-1096)**: `/api/prompts/{id}/sections/*`
- **Template Endpoints (Lines 713-737)**: `/api/templates/*`
- **API Key Endpoints (Lines 1195-1230)**: `/api/keys/*`

**Key Helper Functions:**
- `github_api_request()` (Lines 598-630) - GitHub API wrapper
- `inject_variables()` (Lines 638-644) - Variable substitution
- `extract_variables()` (Lines 646-649) - Parse variables from content
- `slugify()` (Lines 632-636) - Create URL-safe strings

#### Frontend Architecture

**App Structure (`frontend/src/App.js`):**
- Route configuration with React Router
- Protected route wrapper
- GitHub configuration check
- Authentication provider setup

**API Client (`frontend/src/lib/api.js`):**
- Axios instance configuration
- Request/response interceptors
- Automatic token handling
- 401 response handling

**Component Organization:**
```
frontend/src/components/
├── layout/
│   └── MainLayout.jsx     # App shell with sidebar
└── ui/                    # Shadcn/UI components
    ├── button.jsx
    ├── card.jsx
    ├── dialog.jsx
    └── [30+ other UI components]
```

### Key Functions and Endpoints

#### Core API Endpoints

**Authentication:**
- `POST /api/auth/signup` - Register new user
- `POST /api/auth/login` - Email/password login
- `GET /api/auth/github/login` - GitHub OAuth initiation
- `GET /api/auth/github/callback` - OAuth callback handler
- `GET /api/auth/status` - Check authentication status

**Prompt Management:**
- `GET /api/prompts` - List user prompts
- `POST /api/prompts` - Create new prompt
- `GET /api/prompts/{id}` - Get prompt details
- `PUT /api/prompts/{id}` - Update prompt metadata
- `DELETE /api/prompts/{id}` - Delete prompt

**Section Management:**
- `GET /api/prompts/{id}/sections` - List prompt sections
- `GET /api/prompts/{id}/sections/{filename}` - Get section content
- `POST /api/prompts/{id}/sections` - Create new section
- `PUT /api/prompts/{id}/sections/{filename}` - Update section
- `DELETE /api/prompts/{id}/sections/{filename}` - Delete section

**Rendering:**
- `POST /api/prompts/{id}/{version}/render` - Compile prompt with variables

### Database Schema Understanding

**Core Tables:**

**`users`** - User accounts and authentication
```sql
- id (TEXT PRIMARY KEY) - UUID
- github_id (INTEGER UNIQUE) - GitHub user ID
- username (TEXT) - Display name
- email (TEXT UNIQUE) - User email
- password_hash (TEXT) - bcrypt hash
- github_token (TEXT) - OAuth token
- plan (TEXT) - 'free' or 'pro'
```

**`settings`** - GitHub repository configuration
```sql
- id (INTEGER PRIMARY KEY)
- user_id (TEXT) - Foreign key to users
- github_token (TEXT) - User's GitHub token
- github_repo (TEXT) - Repository name
- github_owner (TEXT) - Repository owner
```

**`prompts`** - Prompt metadata
```sql
- id (TEXT PRIMARY KEY) - UUID
- user_id (TEXT) - Foreign key to users
- name (TEXT) - Prompt name
- description (TEXT) - Optional description
- folder_path (TEXT) - GitHub path (prompts/slug)
```

**`prompt_versions`** - Version control mapping
```sql
- id (TEXT PRIMARY KEY) - UUID
- prompt_id (TEXT) - Foreign key to prompts
- version_name (TEXT) - Human-readable version
- branch_name (TEXT) - GitHub branch name
- is_default (INTEGER) - Boolean flag
```

**`templates`** - Starter prompt templates
```sql
- id (TEXT PRIMARY KEY) - UUID
- name (TEXT) - Template name
- sections (TEXT) - JSON array of sections
```

**`api_keys`** - API key management
```sql
- id (TEXT PRIMARY KEY) - UUID
- name (TEXT) - Key identifier
- key_hash (TEXT) - Full API key
- key_preview (TEXT) - Display preview
```

### Frontend Component Structure

**Page Components (`frontend/src/pages/`):**
- `LandingPage.jsx` - Marketing site
- `AuthPage.jsx` - Login/signup forms
- `DashboardPage.jsx` - Prompt management
- `PromptEditorPage.jsx` - Markdown editor interface
- `TemplatesPage.jsx` - Template gallery
- `ApiKeysPage.jsx` - API key management
- `SettingsPage.jsx` - GitHub configuration

**Layout Components:**
- `MainLayout.jsx` - App shell with navigation sidebar
- Responsive design with mobile support

**Context Providers:**
- `AuthContext.jsx` - Authentication state management

## Development Workflows

### Local Development Setup

#### Backend Development
```bash
cd backend/
pip install -r requirements.txt
python -m uvicorn server:app --reload --host 0.0.0.0 --port 8001
```

**Required Environment Variables:**
```env
JWT_SECRET_KEY=your-super-secret-jwt-key
FRONTEND_URL=http://localhost:3000
GITHUB_CLIENT_ID=your-github-oauth-app-id
GITHUB_CLIENT_SECRET=your-github-oauth-secret
GITHUB_REDIRECT_URI=http://localhost/api/auth/github/callback
```

#### Frontend Development
```bash
cd frontend/
yarn install
yarn start
```

**Environment Configuration:**
Create `frontend/.env`:
```env
REACT_APP_BACKEND_URL=http://localhost:8001
```

#### Docker Development
```bash
docker-compose up -d
```

### Testing Procedures

#### Backend Testing
```bash
cd backend/
python -m pytest tests/ -v
```

#### Frontend Testing
```bash
cd frontend/
yarn test
```

#### End-to-End Testing
```bash
cd frontend/
yarn cypress:open
```

### Code Contribution Guidelines

#### Backend Changes
1. **Database Schema Changes**: Update `init_db()` function in `backend/server.py`
2. **New Endpoints**: Add to appropriate router section
3. **Authentication**: Follow existing JWT pattern
4. **Error Handling**: Use HTTPException with appropriate status codes

#### Frontend Changes
1. **New Pages**: Add to `frontend/src/pages/` with default export
2. **Components**: Use Shadcn/UI components from `frontend/src/components/ui/`
3. **Styling**: Follow `design_guidelines.json` specifications
4. **API Calls**: Use functions from `frontend/src/lib/api.js`

### Git Workflow
```bash
git checkout -b feature/new-feature
git add .
git commit -m "feat: add new feature"
git push origin feature/new-feature
```

## Common Tasks & Patterns

### Adding New Features

#### Adding a New API Endpoint

1. **Define Pydantic Model** (Lines 289-386 in `backend/server.py`):
```python
class NewFeatureRequest(BaseModel):
    field1: str
    field2: Optional[int] = None

class NewFeatureResponse(BaseModel):
    id: str
    result: str
```

2. **Add Endpoint**:
```python
@api_router.post("/new-feature", response_model=NewFeatureResponse)
async def create_new_feature(
    data: NewFeatureRequest, 
    user: dict = Depends(require_auth)
):
    # Implementation here
    pass
```

3. **Add Frontend API Function** (`frontend/src/lib/api.js`):
```javascript
export const createNewFeature = (data) => api.post('/new-feature', data);
```

#### Adding a New UI Component

1. **Create Component**:
```jsx
// frontend/src/components/ui/new-component.jsx
import React from 'react';

export const NewComponent = ({ children, ...props }) => {
  return (
    <div className="bg-card border border-border rounded-sm p-4" {...props}>
      {children}
    </div>
  );
};
```

2. **Use in Page**:
```jsx
// frontend/src/pages/example-page.jsx
import { NewComponent } from '@/components/ui/new-component';

export default function ExamplePage() {
  return (
    <NewComponent>
      <h2 className="text-xl font-bold">Example</h2>
    </NewComponent>
  );
}
```

### Modifying UI Components

#### Following Design Guidelines

**Typography** (from `design_guidelines.json`):
- Headings: `JetBrains Mono, monospace`
- Body: `IBM Plex Sans, sans-serif`
- Colors: Primary `#22C55E`, Background `#09090B`

**Component Classes:**
```jsx
// Button example
<button className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-sm font-mono text-sm uppercase tracking-wider px-6 py-2">
  Action
</button>

// Card example
<div className="bg-card border border-border rounded-sm p-6 relative overflow-hidden group hover:border-primary/50 transition-colors">
  Content
</div>
```

#### Dark Theme Implementation

**Color Palette:**
```css
/* Primary colors */
--background: #09090B;
--foreground: #FAFAFA;
--primary: #22C55E;
--secondary: #27272A;
--border: #27272A;
```

### Working with the Database

#### Adding New Tables

1. **Update `init_db()` function** (Lines 60-199):
```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS new_table (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
""")
```

2. **Add Model**:
```python
class NewTableCreate(BaseModel):
    name: str

class NewTableResponse(BaseModel):
    id: str
    name: str
    created_at: str
```

3. **Add CRUD Endpoints**:
```python
@api_router.post("/new-table", response_model=NewTableResponse)
async def create_new_table(data: NewTableCreate, user: dict = Depends(require_auth)):
    # Implementation
    pass
```

#### Database Operations Pattern

```python
# Use context manager for transactions
with get_db_context() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM table WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    
    if result:
        return dict(result)
    raise HTTPException(status_code=404, detail="Not found")
```

### API Endpoint Modifications

#### Request/Response Patterns

**Standard CRUD Pattern:**
```python
# Create
@api_router.post("/resource", response_model=ResourceResponse)
async def create_resource(data: ResourceCreate, user: dict = Depends(require_auth)):
    # Validate user permissions
    # Create in database
    # Return created resource

# Read
@api_router.get("/resource/{id}", response_model=ResourceResponse)
async def get_resource(id: str, user: dict = Depends(require_auth)):
    # Check ownership
    # Fetch from database
    # Return resource

# Update
@api_router.put("/resource/{id}", response_model=ResourceResponse)
async def update_resource(id: str, data: ResourceUpdate, user: dict = Depends(require_auth)):
    # Check ownership
    # Update in database
    # Return updated resource

# Delete
@api_router.delete("/resource/{id}")
async def delete_resource(id: str, user: dict = Depends(require_auth)):
    # Check ownership
    # Delete from database
    # Return success message
```

#### Error Handling Patterns

```python
# Standard error responses
raise HTTPException(status_code=400, detail="Invalid input")
raise HTTPException(status_code=401, detail="Not authenticated")
raise HTTPException(status_code=403, detail="Insufficient permissions")
raise HTTPException(status_code=404, detail="Resource not found")
raise HTTPException(status_code=409, detail="Conflict")
raise HTTPException(status_code=500, detail="Internal server error")
```

### GitHub Integration Updates

#### GitHub API Calls

**Standard Pattern** (Lines 598-630):
```python
async def github_api_request(method: str, endpoint: str, data: dict = None, user_id: str = None):
    settings = get_github_settings(user_id)
    if not settings or not settings.get("github_token"):
        raise HTTPException(status_code=400, detail="GitHub not configured")
    
    headers = {
        "Authorization": f"token {settings['github_token']}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    base_url = f"https://api.github.com/repos/{settings['github_owner']}/{settings['github_repo']}"
    url = f"{base_url}{endpoint}"
    
    async with httpx.AsyncClient() as client:
        # Make request based on method
        # Handle errors
        # Return response
```

**File Operations:**
```python
# Create file
await github_api_request("PUT", f"/contents/{path}", {
    "message": "Create file",
    "content": base64_content
})

# Update file
await github_api_request("PUT", f"/contents/{path}", {
    "message": "Update file", 
    "content": base64_content,
    "sha": current_sha
})

# Delete file
await github_api_request("DELETE", f"/contents/{path}", {
    "message": "Delete file",
    "sha": current_sha
})
```

## Best Practices & Conventions

### Code Style Guidelines

#### Backend (Python)
- **Line Length**: 88 characters (Black formatting)
- **Import Order**: Standard library, third-party, local
- **Function Naming**: `snake_case` for functions and variables
- **Class Naming**: `PascalCase` for classes
- **Async/Await**: Use for all I/O operations
- **Type Hints**: Include for all function parameters and returns

#### Frontend (JavaScript/React)
- **Component Naming**: `PascalCase` for components
- **File Naming**: `kebab-case` for files
- **Hook Naming**: Start with `use` (useState, useEffect, custom hooks)
- **Prop Types**: Use PropTypes or TypeScript
- **CSS Classes**: Follow Tailwind conventions

### Security Considerations

#### Authentication & Authorization
- **JWT Tokens**: 30-day expiration (Line 28)
- **Password Hashing**: bcrypt with salt (Lines 37-41)
- **API Key Validation**: Check on protected endpoints (Lines 275-287)
- **User Authorization**: Always verify ownership for user data

#### Input Validation
```python
# Use Pydantic models for validation
class UserInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
```

#### CORS Configuration
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Performance Optimization

#### Backend
- **Database Connections**: Use context managers
- **Async Operations**: All I/O should be async
- **Error Handling**: Fast failure for invalid requests
- **Pagination**: Implement for large datasets

#### Frontend
- **Code Splitting**: Use React.lazy() for route components
- **State Management**: Minimize unnecessary re-renders
- **API Calls**: Use React Query or SWR for caching
- **Bundle Size**: Monitor and optimize dependencies

### Error Handling Patterns

#### Backend Error Handling
```python
# Try-catch for external API calls
try:
    response = await github_api_request("GET", endpoint)
except httpx.HTTPStatusError as e:
    logging.error(f"GitHub API error: {e}")
    raise HTTPException(status_code=502, detail="External service error")

# Database transaction handling
try:
    # Database operations
    conn.commit()
except sqlite3.Error as e:
    conn.rollback()
    logging.error(f"Database error: {e}")
    raise HTTPException(status_code=500, detail="Database operation failed")
```

#### Frontend Error Handling
```javascript
// API call with error handling
const fetchData = async () => {
  try {
    const response = await api.get('/data');
    return response.data;
  } catch (error) {
    if (error.response?.status === 401) {
      // Handle authentication error
      localStorage.removeItem('auth_token');
      window.location.href = '/';
    }
    // Show user-friendly error
    toast.error('Failed to load data');
  }
};
```

## Troubleshooting Guide

### Common Issues and Solutions

#### Backend Issues

**Database Connection Errors:**
```
sqlite3.ProgrammingError: no such table
```
**Solution**: Run `init_db()` or check database file permissions

**JWT Token Issues:**
```
jwt.exceptions.InvalidTokenError: Invalid token
```
**Solution**: Check `SECRET_KEY` environment variable

**GitHub API Errors:**
```
HTTP 401: Bad credentials
```
**Solution**: Verify GitHub token and repository permissions

**CORS Errors:**
```
Access to fetch blocked by CORS policy
```
**Solution**: Check `CORS_ORIGINS` environment variable

#### Frontend Issues

**Build Failures:**
```bash
# Clear cache and reinstall
cd frontend/
rm -rf node_modules package-lock.json
yarn install
yarn start
```

**API Connection Issues:**
```
Network Error
```
**Solution**: Check `REACT_APP_BACKEND_URL` environment variable

**Authentication Loop:**
```
Infinite redirects to login
```
**Solution**: Clear localStorage and check token validation

**UI Rendering Issues:**
```
Components not displaying correctly
```
**Solution**: Check Tailwind classes and design guidelines

### Debugging Techniques

#### Backend Debugging

**Enable Debug Logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Use throughout the application
logger = logging.getLogger(__name__)
logger.debug(f"Processing request: {data}")
```

**Database Query Debugging:**
```python
# Add SQL logging
conn.set_trace_callback(print)
```

**API Testing with curl:**
```bash
# Test authentication
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password"}'

# Test protected endpoint
curl -X GET http://localhost:8001/api/prompts \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

#### Frontend Debugging

**React Developer Tools:**
- Install browser extension
- Inspect component state and props
- Monitor re-renders

**Network Tab:**
- Monitor API requests/responses
- Check request headers and payloads
- Identify failed requests

**Console Debugging:**
```javascript
// Add debug logging
const debugLog = (message, data) => {
  if (process.env.NODE_ENV === 'development') {
    console.log(`[DEBUG] ${message}`, data);
  }
};
```

### Log Analysis

#### Backend Logs
```python
# Standard log format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

**Common Log Patterns:**
- `INFO - User login: user_id`
- `ERROR - GitHub API error: 404`
- `DEBUG - Database query: SELECT * FROM prompts`

#### Frontend Logs
```javascript
// Structured logging
const logEvent = (event, data) => {
  console.log(JSON.stringify({
    timestamp: new Date().toISOString(),
    event,
    data
  }));
};
```

### Test Failure Resolution

#### Backend Test Failures

**Database Tests:**
```python
# Use in-memory database for tests
@pytest.fixture
def test_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db_test(conn)
    yield conn
    conn.close()
```

**API Tests:**
```python
# Mock external dependencies
@pytest.fixture
def mock_github_api(monkeypatch):
    async def mock_request(*args, **kwargs):
        return {"status": "success"}
    monkeypatch.setattr("github_api_request", mock_request)
```

#### Frontend Test Failures

**Component Tests:**
```javascript
// Test with proper mocking
import { render, screen } from '@testing-library/react';
import { AuthProvider } from '@/context/AuthContext';

test('renders component', () => {
  render(
    <AuthProvider>
      <ComponentUnderTest />
    </AuthProvider>
  );
  expect(screen.getByText('Expected Text')).toBeInTheDocument();
});
```

## Agent-Specific Considerations

### When to Use Different Modes

#### Documentation Writer Mode
- **Use for**: Creating/updating documentation, README files, API docs
- **Focus**: Clear, actionable guidance with examples
- **Files to edit**: `.md` files, documentation

#### Code Mode
- **Use for**: Implementing features, fixing bugs, adding tests
- **Focus**: Following existing patterns and conventions
- **Files to edit**: `.py`, `.js`, `.jsx` files

#### Architect Mode
- **Use for**: Planning features, system design, architecture decisions
- **Focus**: High-level design and planning
- **Files to edit**: Design documents, specifications

#### Debug Mode
- **Use for**: Investigating issues, adding logging, debugging failures
- **Focus**: Systematic problem-solving
- **Files to edit**: Log files, debug code

### File Modification Guidelines

#### Allowed File Types by Mode

**Documentation Writer Mode:**
- ✅ `.md` files
- ✅ README files
- ✅ API documentation
- ❌ Code files (.py, .js, .jsx)
- ❌ Configuration files

**Code Mode:**
- ✅ Source code (.py, .js, .jsx)
- ✅ Configuration files (.json, .yml)
- ✅ Test files
- ❌ Documentation files
- ❌ Binary files

#### Safe Modification Areas

**Backend (backend/server.py):**
- ✅ Adding new endpoints (follow existing patterns)
- ✅ Adding new database tables (update `init_db()`)
- ✅ Modifying existing functions (maintain signatures)
- ❌ Removing core functionality
- ❌ Changing authentication flow without understanding

**Frontend (frontend/src/):**
- ✅ Adding new components
- ✅ Modifying existing UI components
- ✅ Adding new pages
- ❌ Breaking existing routing
- ❌ Removing authentication flows

### Testing Requirements

#### Minimum Testing Requirements

**For Code Changes:**
1. **Backend**: Test new endpoints with pytest
2. **Frontend**: Test new components with React Testing Library
3. **Integration**: Verify API-frontend integration works

**For Documentation Changes:**
1. **Syntax**: Ensure markdown renders correctly
2. **Links**: Verify internal links work
3. **Examples**: Test code examples when possible

#### Testing Commands

```bash
# Backend tests
cd backend && python -m pytest tests/ -v

# Frontend tests  
cd frontend && yarn test

# End-to-end tests
cd frontend && yarn cypress:run

# Docker tests
docker-compose -f docker-compose.test.yml up --abort-on-container-exit
```

### Documentation Updates

#### When to Update Documentation

**Required Updates:**
- Adding new features
- Modifying existing functionality
- Breaking changes
- New API endpoints
- Configuration changes

**Documentation Sources:**
- [`memory_bank.md`](memory_bank.md:1) - Comprehensive project knowledge
- [`requirements.md`](requirements.md:1) - Requirements and architecture
- [`README.md`](README.md:1) - Basic project information
- [`agent.md`](agent.md:1) - This guide

#### Documentation Standards

**Markdown Formatting:**
```markdown
# Use clear headings
## Consistent section structure
### Include code examples
```python
# Code blocks with language specification
def example_function():
    pass
```

**File References:**
- Use relative paths: `backend/server.py`
- Include line numbers for specific sections: `backend/server.py:1258`
- Link to related files

**Code Examples:**
- Include complete, runnable examples
- Show expected inputs and outputs
- Include error cases

---

## Quick Reference

### Essential Commands

```bash
# Start development servers
cd backend && python -m uvicorn server:app --reload
cd frontend && yarn start

# Run tests
cd backend && python -m pytest
cd frontend && yarn test

# Build for production
docker-compose up -d

# Reset database
rm backend/prompt_manager.db
cd backend && python -c "from server import init_db; init_db()"
```

### Key Environment Variables

**Backend:**
- `JWT_SECRET_KEY` - JWT signing secret
- `FRONTEND_URL` - Frontend URL for redirects
- `GITHUB_CLIENT_ID` - GitHub OAuth App ID
- `GITHUB_CLIENT_SECRET` - GitHub OAuth Secret

**Frontend:**
- `REACT_APP_BACKEND_URL` - Backend API URL

### Common File Locations

- **Database**: `backend/prompt_manager.db`
- **Logs**: Check terminal output (no file logging configured)
- **Configuration**: Environment variables
- **Frontend Build**: `frontend/build/` (after `yarn build`)

---

*This guide should be updated as the codebase evolves. Refer to [`memory_bank.md`](memory_bank.md:1) for comprehensive project details.*