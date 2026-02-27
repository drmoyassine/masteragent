from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import sqlite3
import json
import re
import secrets
import httpx
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from jose import jwt, JWTError
import bcrypt

# Import Memory System modules
from memory_routes import memory_router
from memory_db import init_memory_db

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# JWT Configuration
SECRET_KEY = os.environ.get('JWT_SECRET_KEY', secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

# GitHub OAuth Configuration
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID', '')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET', '')
GITHUB_REDIRECT_URI = os.environ.get('GITHUB_REDIRECT_URI', '')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

# Password hashing
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# SQLite Database Setup - use /app/backend/db/ for persistence
import os
DB_DIR = ROOT_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "prompt_manager.db"

def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db_context():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db_context() as conn:
        cursor = conn.cursor()
        
        # Users table for authentication
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                github_id INTEGER UNIQUE,
                username TEXT NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT,
                avatar_url TEXT,
                github_url TEXT,
                github_token TEXT,
                plan TEXT DEFAULT 'free',
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # Settings table for GitHub config (per user)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                user_id TEXT,
                github_token TEXT,
                github_repo TEXT,
                github_owner TEXT,
                storage_mode TEXT DEFAULT 'github',
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Migration: Add storage_mode column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE settings ADD COLUMN storage_mode TEXT DEFAULT 'github'")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Prompts metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                name TEXT NOT NULL,
                description TEXT,
                folder_path TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Prompt versions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id TEXT PRIMARY KEY,
                prompt_id TEXT NOT NULL,
                version_name TEXT NOT NULL,
                branch_name TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (prompt_id) REFERENCES prompts(id)
            )
        """)
        
        # Templates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                sections TEXT NOT NULL,
                created_at TEXT
            )
        """)
        
        # API Keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                key_preview TEXT NOT NULL,
                created_at TEXT,
                last_used TEXT
            )
        """)
        
        # Account-level variables (accessible across all prompts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_variables (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                value TEXT,
                description TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, name)
            )
        """)
        
        # Prompt-level variables (specific to a prompt version)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompt_variables (
                id TEXT PRIMARY KEY,
                prompt_id TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT 'v1',
                name TEXT NOT NULL,
                value TEXT,
                description TEXT,
                required INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (prompt_id) REFERENCES prompts(id),
                UNIQUE(prompt_id, version, name)
            )
        """)
        
        # Insert default templates
        cursor.execute("SELECT COUNT(*) FROM templates")
        if cursor.fetchone()[0] == 0:
            default_templates = [
                {
                    "id": str(uuid.uuid4()),
                    "name": "Agent Persona",
                    "description": "Complete AI agent persona with identity, context, and capabilities",
                    "sections": json.dumps([
                        {"order": 1, "name": "identity", "title": "Identity", "content": "# Identity\n\nYou are {{agent_name}}, a {{agent_role}}.\n\n## Core Traits\n- Professional and helpful\n- Clear and concise communication\n- Empathetic and understanding"},
                        {"order": 2, "name": "context", "title": "Context", "content": "# Context\n\n## Company: {{company_name}}\n\n{{company_description}}\n\n## Your Role\nYou serve as the primary point of contact for {{use_case}}."},
                        {"order": 3, "name": "role", "title": "Role & Responsibilities", "content": "# Role & Responsibilities\n\n## Primary Responsibilities\n1. Assist users with their inquiries\n2. Provide accurate information\n3. Escalate complex issues when necessary\n\n## Boundaries\n- Never share confidential information\n- Stay within your area of expertise"},
                        {"order": 4, "name": "skills", "title": "Skills & Capabilities", "content": "# Skills & Capabilities\n\n## Core Skills\n- Natural language understanding\n- Context retention\n- Multi-turn conversation\n\n## Tools Available\n{{#tools}}\n- {{name}}: {{description}}\n{{/tools}}"},
                        {"order": 5, "name": "guidelines", "title": "Operating Guidelines", "content": "# Operating Guidelines\n\n## Communication Style\n- Tone: {{tone}}\n- Language: {{language}}\n\n## Response Format\n- Keep responses concise but complete\n- Use formatting for clarity\n- Ask clarifying questions when needed"}
                    ]),
                    "created_at": datetime.now(timezone.utc).isoformat()
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "Task Executor",
                    "description": "Focused task execution agent with clear instructions",
                    "sections": json.dumps([
                        {"order": 1, "name": "objective", "title": "Objective", "content": "# Objective\n\nYour primary objective is to {{task_objective}}.\n\n## Success Criteria\n{{success_criteria}}"},
                        {"order": 2, "name": "instructions", "title": "Instructions", "content": "# Instructions\n\n## Step-by-Step Process\n1. Analyze the input\n2. Plan your approach\n3. Execute the task\n4. Validate results\n\n## Constraints\n{{constraints}}"},
                        {"order": 3, "name": "output", "title": "Output Format", "content": "# Output Format\n\n## Expected Output\n{{output_format}}\n\n## Examples\n{{#examples}}\n### Example {{index}}\nInput: {{input}}\nOutput: {{output}}\n{{/examples}}"}
                    ]),
                    "created_at": datetime.now(timezone.utc).isoformat()
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "Knowledge Expert",
                    "description": "Domain-specific knowledge base agent",
                    "sections": json.dumps([
                        {"order": 1, "name": "domain", "title": "Domain Expertise", "content": "# Domain Expertise\n\nYou are an expert in {{domain}}.\n\n## Knowledge Areas\n{{#knowledge_areas}}\n- {{name}}\n{{/knowledge_areas}}"},
                        {"order": 2, "name": "wisdom", "title": "Trade Knowledge", "content": "# Trade Knowledge & Wisdom\n\n## Best Practices\n{{best_practices}}\n\n## Common Pitfalls\n{{common_pitfalls}}\n\n## Lessons Learned\n{{lessons_learned}}"},
                        {"order": 3, "name": "responses", "title": "Response Guidelines", "content": "# Response Guidelines\n\n## When answering questions:\n1. Draw from your expertise\n2. Provide practical examples\n3. Cite sources when applicable\n\n## Handling uncertainty:\n- Acknowledge limitations\n- Suggest alternatives\n- Recommend expert consultation when needed"}
                    ]),
                    "created_at": datetime.now(timezone.utc).isoformat()
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "Minimal Prompt",
                    "description": "Simple single-section prompt for quick tasks",
                    "sections": json.dumps([
                        {"order": 1, "name": "prompt", "title": "Main Prompt", "content": "# {{title}}\n\n{{instructions}}\n\n## Input\n{{input}}\n\n## Output\nProvide your response below:"}
                    ]),
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            ]
            for template in default_templates:
                cursor.execute(
                    "INSERT INTO templates (id, name, description, sections, created_at) VALUES (?, ?, ?, ?, ?)",
                    (template["id"], template["name"], template["description"], template["sections"], template["created_at"])
                )

init_db()

# Initialize Memory System DB
init_memory_db()

# Seed admin user for testing
def seed_admin_user():
    admin_email = "admin@promptsrc.com"
    admin_password = "admin123"
    admin_username = "admin"
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
        if not cursor.fetchone():
            now = datetime.now(timezone.utc).isoformat()
            admin_id = str(uuid.uuid4())
            password_hash = hash_password(admin_password)
            cursor.execute("""
                INSERT INTO users (id, username, email, password_hash, plan, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pro', ?, ?)
            """, (admin_id, admin_username, admin_email, password_hash, now, now))
            logging.info(f"Admin user created: {admin_email}")

seed_admin_user()

# Create the main app
app = FastAPI(title="Prompt Manager & Memory System API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# API Key Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# JWT Token Utilities
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_jwt_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return user_id
    except JWTError:
        return None

def get_current_user(authorization: str = Header(None)):
    if not authorization:
        return None
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
        user_id = verify_jwt_token(token)
        if not user_id:
            return None
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if user:
                return dict(user)
    except Exception:
        pass
    return None

def require_auth(authorization: str = Header(None)):
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

async def verify_api_key(api_key: str = Security(api_key_header)):
    if not api_key:
        return None
    with get_db_context() as conn:
        cursor = conn.cursor()
        # Check all keys (we store hashed, but for simplicity we'll use preview matching)
        cursor.execute("SELECT * FROM api_keys WHERE key_hash = ?", (api_key,))
        key_row = cursor.fetchone()
        if key_row:
            cursor.execute("UPDATE api_keys SET last_used = ? WHERE id = ?", 
                          (datetime.now(timezone.utc).isoformat(), key_row["id"]))
            return dict(key_row)
    return None

# Pydantic Models
# Auth Models
class UserCreate(BaseModel):
    email: str
    password: str
    username: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    github_id: Optional[int] = None
    username: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    github_url: Optional[str] = None
    plan: str = "free"
    created_at: str
    updated_at: str

class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: Optional[UserResponse] = None

class AuthResponse(BaseModel):
    token: str
    user: UserResponse

class SettingsCreate(BaseModel):
    github_token: str
    github_repo: str
    github_owner: str
    create_repo: bool = False  # If true, create the repo

class SettingsResponse(BaseModel):
    id: int
    github_repo: Optional[str] = None
    github_owner: Optional[str] = None
    is_configured: bool = False
    storage_mode: str = "github"  # 'github' or 'local'

class PromptCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    template_id: Optional[str] = None

class PromptUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class PromptResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    folder_path: str
    created_at: str
    updated_at: str
    versions: List[Dict[str, Any]] = []

class SectionCreate(BaseModel):
    name: str
    title: str
    content: str
    order: Optional[int] = None
    parent_path: Optional[str] = None

class SectionUpdate(BaseModel):
    content: str

class SectionReorder(BaseModel):
    sections: List[Dict[str, Any]]

class VersionCreate(BaseModel):
    version_name: str
    source_version: Optional[str] = None

class RenderRequest(BaseModel):
    variables: Optional[Dict[str, Any]] = {}

class RenderResponse(BaseModel):
    prompt_id: str
    version: str
    compiled_prompt: str
    sections_used: List[str]

class APIKeyCreate(BaseModel):
    name: str

class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_preview: str
    created_at: str
    last_used: Optional[str] = None

class APIKeyCreateResponse(APIKeyResponse):
    key: str  # Full key only shown on creation

# Variable Models
class VariableBase(BaseModel):
    name: str
    value: Optional[str] = None
    description: Optional[str] = None

class VariableCreate(VariableBase):
    pass

class VariableUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None

class VariableResponse(VariableBase):
    id: str
    created_at: str
    updated_at: str

class PromptVariableResponse(VariableResponse):
    prompt_id: str
    version: str
    required: bool

class AccountVariableResponse(VariableResponse):
    user_id: str

class AvailableVariableResponse(BaseModel):
    name: str
    value: Optional[str] = None
    description: Optional[str] = None
    source: str  # 'account', 'prompt', or 'runtime'
    required: bool = False

# Helper Functions
def get_github_settings(user_id: str = None):
    with get_db_context() as conn:
        cursor = conn.cursor()
        if user_id:
            cursor.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,))
        else:
            cursor.execute("SELECT * FROM settings WHERE id = 1")
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None

def user_to_response(user: dict) -> UserResponse:
    return UserResponse(
        id=user["id"],
        github_id=user.get("github_id"),
        username=user["username"],
        email=user.get("email"),
        avatar_url=user.get("avatar_url"),
        github_url=user.get("github_url"),
        plan=user.get("plan", "free"),
        created_at=user["created_at"],
        updated_at=user["updated_at"]
    )

# Email/Password Auth Endpoints
@api_router.post("/auth/signup", response_model=AuthResponse)
async def signup(user_data: UserCreate):
    """Register a new user with email/password"""
    now = datetime.now(timezone.utc).isoformat()
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        
        # Check if email already exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (user_data.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Check if username already exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (user_data.username,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Username already taken")
        
        user_id = str(uuid.uuid4())
        password_hash = hash_password(user_data.password)
        
        cursor.execute("""
            INSERT INTO users (id, username, email, password_hash, plan, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'free', ?, ?)
        """, (user_id, user_data.username, user_data.email, password_hash, now, now))
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = dict(cursor.fetchone())
    
    token = create_access_token(data={"sub": user_id})
    return AuthResponse(token=token, user=user_to_response(user))

@api_router.post("/auth/login", response_model=AuthResponse)
async def login(credentials: UserLogin):
    """Login with email/password"""
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (credentials.email,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        user = dict(user)
        
        if not user.get("password_hash"):
            raise HTTPException(status_code=401, detail="This account uses GitHub login. Please sign in with GitHub.")
        
        if not verify_password(credentials.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Update last login
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("UPDATE users SET updated_at = ? WHERE id = ?", (now, user["id"]))
    
    token = create_access_token(data={"sub": user["id"]})
    return AuthResponse(token=token, user=user_to_response(user))

# GitHub OAuth Endpoints
@api_router.get("/auth/github/login")
async def github_login():
    """Redirect to GitHub OAuth"""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=503, 
            detail="GitHub OAuth not configured. Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET environment variables."
        )
    
    state = secrets.token_urlsafe(16)
    github_auth_url = (
        f"https://github.com/login/oauth/authorize?"
        f"client_id={GITHUB_CLIENT_ID}&"
        f"redirect_uri={GITHUB_REDIRECT_URI}&"
        f"scope=user:email,repo&"
        f"state={state}"
    )
    return {"auth_url": github_auth_url}

@api_router.get("/auth/github/callback")
async def github_callback(code: str, state: str = None):
    """Handle GitHub OAuth callback"""
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")
    
    try:
        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                },
                headers={"Accept": "application/json"}
            )
            token_data = token_response.json()
        
        github_token = token_data.get("access_token")
        if not github_token:
            error = token_data.get("error_description", "Failed to get access token")
            return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?error={error}")
        
        # Get user info from GitHub
        async with httpx.AsyncClient() as client:
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/json"
                }
            )
            github_user = user_response.json()
            
            # Get user emails
            emails_response = await client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/json"
                }
            )
            emails = emails_response.json()
        
        # Find primary email
        primary_email = None
        for email in emails:
            if email.get("primary"):
                primary_email = email.get("email")
                break
        if not primary_email and emails:
            primary_email = emails[0].get("email")
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Check if user exists
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE github_id = ?", (github_user["id"],))
            existing_user = cursor.fetchone()
            
            if existing_user:
                user_id = existing_user["id"]
                # Update user info and token
                cursor.execute("""
                    UPDATE users SET 
                        username = ?, email = ?, avatar_url = ?, github_token = ?, updated_at = ?
                    WHERE id = ?
                """, (github_user["login"], primary_email, github_user.get("avatar_url"), 
                      github_token, now, user_id))
            else:
                user_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO users (id, github_id, username, email, avatar_url, github_url, github_token, plan, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'free', ?, ?)
                """, (user_id, github_user["id"], github_user["login"], primary_email,
                      github_user.get("avatar_url"), github_user.get("html_url"), github_token, now, now))
        
        # Create JWT token
        jwt_token = create_access_token(data={"sub": user_id})
        
        # Redirect to frontend with token
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?token={jwt_token}")
    
    except Exception as e:
        logging.error(f"GitHub OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?error=Authentication failed")

@api_router.get("/auth/status", response_model=AuthStatusResponse)
async def auth_status(user: dict = Depends(get_current_user)):
    """Check authentication status"""
    if not user:
        return AuthStatusResponse(authenticated=False)
    
    return AuthStatusResponse(
        authenticated=True,
        user=user_to_response(user)
    )

@api_router.post("/auth/logout")
async def logout():
    """Logout user"""
    return {"message": "Logged out successfully"}

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
        if method == "GET":
            response = await client.get(url, headers=headers)
        elif method == "PUT":
            response = await client.put(url, headers=headers, json=data)
        elif method == "POST":
            response = await client.post(url, headers=headers, json=data)
        elif method == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        
        if response.status_code == 204:
            return {}
        return response.json()

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text)
    return text

def inject_variables(content: str, variables: dict, prompt_id: str = None, user_id: str = None, version: str = "v1") -> str:
    """Inject variables with resolution order: runtime → prompt → account → default"""
    resolved = {}
    
    # 3. Account-level variables (lowest priority)
    if user_id:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, value FROM account_variables WHERE user_id = ?", (user_id,))
            for row in cursor.fetchall():
                resolved[row["name"]] = row["value"]
    
    # 2. Prompt-level variables (medium priority)
    if prompt_id:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, value FROM prompt_variables WHERE prompt_id = ? AND version = ?", (prompt_id, version))
            for row in cursor.fetchall():
                resolved[row["name"]] = row["value"]
    
    # 1. Runtime values (highest priority)
    resolved.update(variables)
    
    # Apply substitution
    result = content
    for key, value in resolved.items():
        if value is not None:
            result = re.sub(r'\{\{\s*' + re.escape(key) + r'\s*\}\}', str(value), result)
    return result

def extract_variables(content: str) -> List[str]:
    """Extract variable names from content"""
    pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
    return list(set(re.findall(pattern, content)))

# Settings Endpoints (protected)
@api_router.get("/settings", response_model=SettingsResponse)
async def get_settings(user: dict = Depends(require_auth)):
    settings = get_github_settings(user["id"])
    if settings:
        storage_mode = settings.get("storage_mode", "github")
        # For github mode, check if token exists; for local mode, always configured
        if storage_mode == "local":
            is_configured = True
        else:
            is_configured = bool(settings.get("github_token"))
        
        return SettingsResponse(
            id=settings["id"],
            github_repo=settings.get("github_repo"),
            github_owner=settings.get("github_owner"),
            is_configured=is_configured,
            storage_mode=storage_mode
        )
    return SettingsResponse(id=0, is_configured=False, storage_mode="github")

@api_router.post("/settings", response_model=SettingsResponse)
async def save_settings(settings_data: SettingsCreate, user: dict = Depends(require_auth)):
    now = datetime.now(timezone.utc).isoformat()
    
    headers = {
        "Authorization": f"token {settings_data.github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    async with httpx.AsyncClient() as client:
        if settings_data.create_repo:
            # Create new repository
            create_response = await client.post(
                "https://api.github.com/user/repos",
                headers=headers,
                json={
                    "name": settings_data.github_repo,
                    "description": "Prompt Manager - AI prompt versioning repository",
                    "private": False,
                    "auto_init": True  # Initialize with README
                }
            )
            if create_response.status_code == 201:
                repo_data = create_response.json()
                # Update owner from response (in case user belongs to org)
                settings_data.github_owner = repo_data["owner"]["login"]
            elif create_response.status_code == 422:
                # Repo already exists, try to use it
                pass
            else:
                raise HTTPException(status_code=400, detail=f"Failed to create repository: {create_response.text}")
        
        # Validate GitHub connection
        response = await client.get(
            f"https://api.github.com/repos/{settings_data.github_owner}/{settings_data.github_repo}",
            headers=headers
        )
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid GitHub credentials or repository not found")
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM settings WHERE user_id = ?", (user["id"],))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE settings SET github_token = ?, github_repo = ?, github_owner = ?, updated_at = ?
                WHERE user_id = ?
            """, (settings_data.github_token, settings_data.github_repo, settings_data.github_owner, now, user["id"]))
            settings_id = existing["id"]
        else:
            cursor.execute("""
                INSERT INTO settings (user_id, github_token, github_repo, github_owner, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user["id"], settings_data.github_token, settings_data.github_repo, settings_data.github_owner, now, now))
            settings_id = cursor.lastrowid
    
    return SettingsResponse(
        id=settings_id,
        github_repo=settings_data.github_repo,
        github_owner=settings_data.github_owner,
        is_configured=True
    )

@api_router.get("/github/user")
async def get_github_user(token: str):
    """Get GitHub user info from token"""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.github.com/user", headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid GitHub token")
        return response.json()

@api_router.delete("/settings")
async def delete_settings(user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM settings WHERE user_id = ?", (user["id"],))
    return {"message": "Settings deleted"}

class StorageModeUpdate(BaseModel):
    storage_mode: str  # 'github' or 'local'

@api_router.post("/settings/storage-mode", response_model=SettingsResponse)
async def set_storage_mode(mode_data: StorageModeUpdate, user: dict = Depends(require_auth)):
    """Set the storage mode for the user (github or local)."""
    if mode_data.storage_mode not in ["github", "local"]:
        raise HTTPException(status_code=400, detail="Invalid storage mode. Must be 'github' or 'local'")
    
    now = datetime.now(timezone.utc).isoformat()
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE user_id = ?", (user["id"],))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE settings SET storage_mode = ?, updated_at = ?
                WHERE user_id = ?
            """, (mode_data.storage_mode, now, user["id"]))
            settings_id = existing["id"]
            storage_mode = mode_data.storage_mode
            github_repo = existing.get("github_repo")
            github_owner = existing.get("github_owner")
            # For github mode, check if token exists; for local mode, always configured
            if mode_data.storage_mode == "local":
                is_configured = True
            else:
                is_configured = bool(existing.get("github_token"))
        else:
            # Create new settings entry with local mode
            cursor.execute("""
                INSERT INTO settings (user_id, storage_mode, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """, (user["id"], mode_data.storage_mode, now, now))
            settings_id = cursor.lastrowid
            storage_mode = mode_data.storage_mode
            github_repo = None
            github_owner = None
            is_configured = (mode_data.storage_mode == "local")
    
    return SettingsResponse(
        id=settings_id,
        github_repo=github_repo,
        github_owner=github_owner,
        is_configured=is_configured,
        storage_mode=storage_mode
    )

# Templates Endpoints
@api_router.get("/templates")
async def get_templates():
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM templates ORDER BY created_at")
        rows = cursor.fetchall()
        templates = []
        for row in rows:
            template = dict(row)
            template["sections"] = json.loads(template["sections"])
            templates.append(template)
        return templates

@api_router.get("/templates/{template_id}")
async def get_template(template_id: str):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Template not found")
        template = dict(row)
        template["sections"] = json.loads(template["sections"])
        return template

# Prompts Endpoints (protected)
@api_router.get("/prompts")
async def get_prompts(user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE user_id = ? ORDER BY updated_at DESC", (user["id"],))
        prompts = [dict(row) for row in cursor.fetchall()]
        
        for prompt in prompts:
            cursor.execute("SELECT * FROM prompt_versions WHERE prompt_id = ? ORDER BY created_at", (prompt["id"],))
            prompt["versions"] = [dict(v) for v in cursor.fetchall()]
        
        return prompts

@api_router.post("/prompts", response_model=PromptResponse)
async def create_prompt(prompt_data: PromptCreate, user: dict = Depends(require_auth)):
    # Import storage service
    from storage_service import get_storage_service, get_storage_mode
    
    # Check plan limits
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM prompts WHERE user_id = ?", (user["id"],))
        count = cursor.fetchone()["count"]
        if user.get("plan") == "free" and count >= 1:
            raise HTTPException(status_code=403, detail="Free plan limited to 1 prompt. Upgrade to Pro for unlimited prompts.")
    
    prompt_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    prompt_slug = slugify(prompt_data.name)
    # Folder structure: prompts/{prompt_name}/v1/
    folder_path = f"prompts/{prompt_slug}"
    
    # Check storage mode - fallback to local if GitHub not configured
    storage_mode = get_storage_mode(user["id"])
    if storage_mode == "github":
        settings = get_github_settings(user["id"])
        if not settings or not settings.get("github_token"):
            # Auto-fallback to local storage
            storage_mode = "local"
    
    # Get template sections if template_id provided
    sections_to_create = []
    if prompt_data.template_id:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sections FROM templates WHERE id = ?", (prompt_data.template_id,))
            template_row = cursor.fetchone()
            if template_row:
                sections_to_create = json.loads(template_row["sections"])
    
    # Prepare sections for storage service
    sections = []
    for section in sections_to_create:
        section_filename = f"{str(section['order']).zfill(2)}_{section['name']}.md"
        sections.append({
            "filename": section_filename,
            "content": section.get("content", ""),
            "order": section.get("order", 1),
            "name": section.get("name", "section")
        })
    
    # Extract variables from sections
    variables = {}
    for section in sections_to_create:
        vars_in_section = extract_variables(section.get("content", ""))
        for var in vars_in_section:
            if var not in variables:
                variables[var] = {"required": True}
    
    # Create prompt in DB first
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prompts (id, user_id, name, description, folder_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (prompt_id, user["id"], prompt_data.name, prompt_data.description or "", folder_path, now, now))
        
        # Create default version (v1)
        version_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO prompt_versions (id, prompt_id, version_name, branch_name, is_default, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (version_id, prompt_id, "v1", "v1", now))
    
    # Use storage service to create prompt files
    try:
        storage_service = get_storage_service(user["id"])
        await storage_service.create_prompt(
            folder_path=folder_path,
            name=prompt_data.name,
            description=prompt_data.description or "",
            sections=sections,
            variables=variables
        )
    except Exception as e:
        # If storage fails, clean up DB entry
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM prompt_versions WHERE prompt_id = ?", (prompt_id,))
            cursor.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        raise HTTPException(status_code=500, detail=f"Failed to create prompt: {str(e)}")
    
    return PromptResponse(
        id=prompt_id,
        name=prompt_data.name,
        description=prompt_data.description,
        folder_path=folder_path,
        created_at=now,
        updated_at=now,
        versions=[{"id": version_id, "version_name": "v1", "branch_name": "v1", "is_default": True}]
    )

@api_router.get("/prompts/{prompt_id}")
async def get_prompt(prompt_id: str, user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        prompt = dict(row)
        cursor.execute("SELECT * FROM prompt_versions WHERE prompt_id = ?", (prompt_id,))
        prompt["versions"] = [dict(v) for v in cursor.fetchall()]
        
        return prompt

@api_router.put("/prompts/{prompt_id}")
async def update_prompt(prompt_id: str, prompt_data: PromptUpdate, user: dict = Depends(require_auth)):
    now = datetime.now(timezone.utc).isoformat()
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        updates = []
        params = []
        if prompt_data.name:
            updates.append("name = ?")
            params.append(prompt_data.name)
        if prompt_data.description is not None:
            updates.append("description = ?")
            params.append(prompt_data.description)
        updates.append("updated_at = ?")
        params.append(now)
        params.append(prompt_id)
        
        cursor.execute(f"UPDATE prompts SET {', '.join(updates)} WHERE id = ?", params)
    
    return await get_prompt(prompt_id, user)

@api_router.delete("/prompts/{prompt_id}")
async def delete_prompt(prompt_id: str, user: dict = Depends(require_auth)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        # Delete from DB
        cursor.execute("DELETE FROM prompt_versions WHERE prompt_id = ?", (prompt_id,))
        cursor.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
    
    # Note: GitHub files should be deleted separately or kept for history
    return {"message": "Prompt deleted"}

# Sections Endpoints (folder-based versioning)
@api_router.get("/prompts/{prompt_id}/sections")
async def get_prompt_sections(prompt_id: str, version: str = "v1", user: dict = Depends(require_auth)):
    from storage_service import get_storage_service
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]
    
    try:
        storage_service = get_storage_service(user["id"])
        content = await storage_service.get_prompt_content(folder_path, version)
        
        if not content:
            return []
        
        sections = []
        for section in content.get("sections", []):
            filename = section.get("filename", "")
            # Parse order from filename
            match = re.match(r'^(\d+)_(.+)\.md$', filename)
            if match:
                order = int(match.group(1))
                name = match.group(2)
            else:
                order = 99
                name = filename.replace(".md", "")
            
            sections.append({
                "filename": filename,
                "name": name,
                "order": order,
                "path": f"{folder_path}/{version}/{filename}",
                "type": "file"
            })
        
        sections.sort(key=lambda x: x["order"])
        return sections
    except Exception as e:
        logging.error(f"Error fetching sections: {e}")
        return []

@api_router.get("/prompts/{prompt_id}/sections/{filename}")
async def get_section_content(prompt_id: str, filename: str, version: str = "v1", user: dict = Depends(require_auth)):
    from storage_service import get_storage_service
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]
    
    try:
        storage_service = get_storage_service(user["id"])
        section_data = await storage_service.get_section(folder_path, filename, version)
        
        if not section_data:
            raise HTTPException(status_code=404, detail="Section not found")
        
        content = section_data.get("content", "")
        return {
            "filename": filename,
            "content": content,
            "variables": extract_variables(content)
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching section: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch section: {str(e)}")

@api_router.post("/prompts/{prompt_id}/sections")
async def create_section(prompt_id: str, section_data: SectionCreate, version: str = "v1", user: dict = Depends(require_auth)):
    from storage_service import get_storage_service
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]
    
    # Get existing sections to determine order
    sections = await get_prompt_sections(prompt_id, version, user)
    order = section_data.order if section_data.order else (max([s["order"] for s in sections], default=0) + 1)
    
    filename = f"{str(order).zfill(2)}_{slugify(section_data.name)}.md"
    
    try:
        storage_service = get_storage_service(user["id"])
        success = await storage_service.create_section(folder_path, filename, section_data.content, version)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create section")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error creating section: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create section: {str(e)}")
    
    # Update timestamp
    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE prompts SET updated_at = ? WHERE id = ?", (now, prompt_id))
    
    return {"filename": filename, "message": "Section created"}

@api_router.put("/prompts/{prompt_id}/sections/{filename}")
async def update_section(prompt_id: str, filename: str, section_data: SectionUpdate, version: str = "v1", user: dict = Depends(require_auth)):
    from storage_service import get_storage_service
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]
    
    try:
        storage_service = get_storage_service(user["id"])
        success = await storage_service.update_section(folder_path, filename, section_data.content, version)
        if not success:
            raise HTTPException(status_code=404, detail="Section not found")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating section: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update section: {str(e)}")
    
    # Update timestamp
    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE prompts SET updated_at = ? WHERE id = ?", (now, prompt_id))
    
    return {"filename": filename, "message": "Section updated"}

@api_router.delete("/prompts/{prompt_id}/sections/{filename}")
async def delete_section(prompt_id: str, filename: str, version: str = "v1", user: dict = Depends(require_auth)):
    from storage_service import get_storage_service
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]
    
    try:
        storage_service = get_storage_service(user["id"])
        success = await storage_service.delete_section(folder_path, filename, version)
        if not success:
            raise HTTPException(status_code=404, detail="Section not found")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting section: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete section: {str(e)}")
    
    return {"message": "Section deleted"}

@api_router.post("/prompts/{prompt_id}/sections/reorder")
async def reorder_sections(prompt_id: str, reorder_data: SectionReorder, version: str = "v1", user: dict = Depends(require_auth)):
    from storage_service import get_storage_service
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT folder_path FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = row["folder_path"]
    
    try:
        storage_service = get_storage_service(user["id"])
        
        for i, section in enumerate(reorder_data.sections):
            old_filename = section["filename"]
            name = section.get("name", old_filename.split("_", 1)[1].replace(".md", ""))
            new_filename = f"{str(i + 1).zfill(2)}_{name}.md"
            
            if old_filename != new_filename:
                # Get current content
                section_data = await storage_service.get_section(folder_path, old_filename, version)
                if section_data:
                    # Create new file with new name
                    await storage_service.create_section(folder_path, new_filename, section_data["content"], version)
                    # Delete old file
                    await storage_service.delete_section(folder_path, old_filename, version)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error reordering sections: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reorder sections: {str(e)}")
    
    return {"message": "Sections reordered"}

# Versions Endpoints
@api_router.get("/prompts/{prompt_id}/versions")
async def get_prompt_versions(prompt_id: str):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompt_versions WHERE prompt_id = ? ORDER BY created_at DESC", (prompt_id,))
        return [dict(row) for row in cursor.fetchall()]

@api_router.post("/prompts/{prompt_id}/versions")
async def create_version(prompt_id: str, version_data: VersionCreate):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        prompt = cursor.fetchone()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
    
    branch_name = slugify(version_data.version_name)
    source_branch = version_data.source_version or "main"
    
    # Get source branch SHA
    ref_data = await github_api_request("GET", f"/git/refs/heads/{source_branch}")
    if not ref_data:
        raise HTTPException(status_code=400, detail=f"Source branch '{source_branch}' not found")
    
    # Create new branch
    await github_api_request("POST", "/git/refs", {
        "ref": f"refs/heads/{branch_name}",
        "sha": ref_data["object"]["sha"]
    })
    
    # Save version to DB
    version_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prompt_versions (id, prompt_id, version_name, branch_name, is_default, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
        """, (version_id, prompt_id, version_data.version_name, branch_name, now))
    
    return {"id": version_id, "version_name": version_data.version_name, "branch_name": branch_name}

# Render Endpoint
@api_router.post("/prompts/{prompt_id}/{version}/render", response_model=RenderResponse)
async def render_prompt(prompt_id: str, version: str, render_data: RenderRequest, api_key: dict = Depends(verify_api_key)):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        prompt = cursor.fetchone()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        folder_path = prompt["folder_path"]
        user_id = prompt["user_id"]  # Get user_id for variable resolution
    
    # Get sections
    sections = await get_prompt_sections(prompt_id, version)
    if not sections:
        raise HTTPException(status_code=404, detail="No sections found")
    
    import base64
    compiled_parts = []
    sections_used = []
    all_variables = set()
    
    for section in sections:
        file_data = await github_api_request("GET", f"/contents/{folder_path}/{section['filename']}?ref={version}")
        if file_data:
            content = base64.b64decode(file_data["content"]).decode("utf-8")
            all_variables.update(extract_variables(content))
            
            # Inject variables with full resolution order: runtime → prompt → account
            content = inject_variables(
                content,
                render_data.variables or {},
                prompt_id=prompt_id,
                user_id=user_id,
                version=version
            )
            
            compiled_parts.append(content)
            sections_used.append(section["filename"])
    
    # Check for missing required variables (still have {{var}} in output)
    compiled_prompt = "\n\n---\n\n".join(compiled_parts)
    remaining_vars = extract_variables(compiled_prompt)
    if remaining_vars:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Missing required variables",
                "missing": remaining_vars
            }
        )
    
    return RenderResponse(
        prompt_id=prompt_id,
        version=version,
        compiled_prompt=compiled_prompt,
        sections_used=sections_used
    )

# API Keys Endpoints
@api_router.get("/keys", response_model=List[APIKeyResponse])
async def get_api_keys():
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, key_preview, created_at, last_used FROM api_keys ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

@api_router.post("/keys", response_model=APIKeyCreateResponse)
async def create_api_key(key_data: APIKeyCreate):
    key_id = str(uuid.uuid4())
    full_key = f"pm_{secrets.token_urlsafe(32)}"
    key_preview = f"{full_key[:7]}...{full_key[-4:]}"
    now = datetime.now(timezone.utc).isoformat()
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO api_keys (id, name, key_hash, key_preview, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (key_id, key_data.name, full_key, key_preview, now))
    
    return APIKeyCreateResponse(
        id=key_id,
        name=key_data.name,
        key=full_key,
        key_preview=key_preview,
        created_at=now
    )

@api_router.delete("/keys/{key_id}")
async def delete_api_key(key_id: str):
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    return {"message": "API key deleted"}

# =====================
# Account Variables Endpoints
# =====================

@api_router.get("/account-variables", response_model=List[AccountVariableResponse])
async def list_account_variables(user: dict = Depends(require_auth)):
    """List all account-level variables for the current user"""
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM account_variables WHERE user_id = ? ORDER BY name",
            (user["id"],)
        )
        variables = cursor.fetchall()
        return [
            AccountVariableResponse(
                id=row["id"],
                user_id=row["user_id"],
                name=row["name"],
                value=row["value"],
                description=row["description"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
            for row in variables
        ]

@api_router.post("/account-variables", response_model=AccountVariableResponse)
async def create_account_variable(data: VariableCreate, user: dict = Depends(require_auth)):
    """Create a new account-level variable"""
    now = datetime.now(timezone.utc).isoformat()
    var_id = str(uuid.uuid4())
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        # Check if variable with this name already exists
        cursor.execute(
            "SELECT id FROM account_variables WHERE user_id = ? AND name = ?",
            (user["id"], data.name)
        )
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail=f"Variable '{data.name}' already exists")
        
        cursor.execute(
            """INSERT INTO account_variables (id, user_id, name, value, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (var_id, user["id"], data.name, data.value, data.description, now, now)
        )
    
    return AccountVariableResponse(
        id=var_id,
        user_id=user["id"],
        name=data.name,
        value=data.value,
        description=data.description,
        created_at=now,
        updated_at=now
    )

@api_router.put("/account-variables/{name}", response_model=AccountVariableResponse)
async def update_account_variable(name: str, data: VariableUpdate, user: dict = Depends(require_auth)):
    """Update an existing account-level variable"""
    now = datetime.now(timezone.utc).isoformat()
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM account_variables WHERE user_id = ? AND name = ?",
            (user["id"], name)
        )
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Variable '{name}' not found")
        
        # Update only provided fields
        new_value = data.value if data.value is not None else existing["value"]
        new_description = data.description if data.description is not None else existing["description"]
        
        cursor.execute(
            """UPDATE account_variables
               SET value = ?, description = ?, updated_at = ?
               WHERE user_id = ? AND name = ?""",
            (new_value, new_description, now, user["id"], name)
        )
    
    return AccountVariableResponse(
        id=existing["id"],
        user_id=user["id"],
        name=name,
        value=new_value,
        description=new_description,
        created_at=existing["created_at"],
        updated_at=now
    )

@api_router.delete("/account-variables/{name}")
async def delete_account_variable(name: str, user: dict = Depends(require_auth)):
    """Delete an account-level variable"""
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM account_variables WHERE user_id = ? AND name = ?",
            (user["id"], name)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Variable '{name}' not found")
        
        cursor.execute(
            "DELETE FROM account_variables WHERE user_id = ? AND name = ?",
            (user["id"], name)
        )
    
    return {"message": f"Variable '{name}' deleted"}

# =====================
# Prompt Variables Endpoints
# =====================

@api_router.get("/prompts/{prompt_id}/variables", response_model=List[PromptVariableResponse])
async def list_prompt_variables(prompt_id: str, version: str = "v1", user: dict = Depends(require_auth)):
    """List all variables for a specific prompt version"""
    # Verify prompt exists and belongs to user
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        prompt = cursor.fetchone()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        cursor.execute(
            """SELECT * FROM prompt_variables
               WHERE prompt_id = ? AND version = ?
               ORDER BY name""",
            (prompt_id, version)
        )
        variables = cursor.fetchall()
        
        return [
            PromptVariableResponse(
                id=row["id"],
                prompt_id=row["prompt_id"],
                version=row["version"],
                name=row["name"],
                value=row["value"],
                description=row["description"],
                required=bool(row["required"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
            for row in variables
        ]

@api_router.post("/prompts/{prompt_id}/variables", response_model=PromptVariableResponse)
async def create_prompt_variable(prompt_id: str, data: VariableCreate, version: str = "v1", user: dict = Depends(require_auth)):
    """Create a new prompt-level variable"""
    now = datetime.now(timezone.utc).isoformat()
    var_id = str(uuid.uuid4())
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        # Verify prompt exists
        cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        prompt = cursor.fetchone()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        # Check if variable with this name already exists for this version
        cursor.execute(
            "SELECT id FROM prompt_variables WHERE prompt_id = ? AND version = ? AND name = ?",
            (prompt_id, version, data.name)
        )
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail=f"Variable '{data.name}' already exists for this version")
        
        cursor.execute(
            """INSERT INTO prompt_variables (id, prompt_id, version, name, value, description, required, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (var_id, prompt_id, version, data.name, data.value, data.description, now, now)
        )
    
    return PromptVariableResponse(
        id=var_id,
        prompt_id=prompt_id,
        version=version,
        name=data.name,
        value=data.value,
        description=data.description,
        required=False,
        created_at=now,
        updated_at=now
    )

@api_router.put("/prompts/{prompt_id}/variables/{name}", response_model=PromptVariableResponse)
async def update_prompt_variable(prompt_id: str, name: str, data: VariableUpdate, version: str = "v1", user: dict = Depends(require_auth)):
    """Update an existing prompt-level variable"""
    now = datetime.now(timezone.utc).isoformat()
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM prompt_variables WHERE prompt_id = ? AND version = ? AND name = ?",
            (prompt_id, version, name)
        )
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Variable '{name}' not found")
        
        # Update only provided fields
        new_value = data.value if data.value is not None else existing["value"]
        new_description = data.description if data.description is not None else existing["description"]
        
        cursor.execute(
            """UPDATE prompt_variables
               SET value = ?, description = ?, updated_at = ?
               WHERE prompt_id = ? AND version = ? AND name = ?""",
            (new_value, new_description, now, prompt_id, version, name)
        )
    
    return PromptVariableResponse(
        id=existing["id"],
        prompt_id=prompt_id,
        version=version,
        name=name,
        value=new_value,
        description=new_description,
        required=bool(existing["required"]),
        created_at=existing["created_at"],
        updated_at=now
    )

@api_router.delete("/prompts/{prompt_id}/variables/{name}")
async def delete_prompt_variable(prompt_id: str, name: str, version: str = "v1", user: dict = Depends(require_auth)):
    """Delete a prompt-level variable"""
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM prompt_variables WHERE prompt_id = ? AND version = ? AND name = ?",
            (prompt_id, version, name)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Variable '{name}' not found")
        
        cursor.execute(
            "DELETE FROM prompt_variables WHERE prompt_id = ? AND version = ? AND name = ?",
            (prompt_id, version, name)
        )
    
    return {"message": f"Variable '{name}' deleted"}

# =====================
# Available Variables Endpoint (for autocomplete)
# =====================

@api_router.get("/prompts/{prompt_id}/available-variables", response_model=List[AvailableVariableResponse])
async def get_available_variables(prompt_id: str, version: str = "v1", user: dict = Depends(require_auth)):
    """Get all available variables for a prompt (prompt-level + account-level)"""
    variables = []
    seen_names = set()
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        
        # Verify prompt exists
        cursor.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        prompt = cursor.fetchone()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        
        # Get prompt-level variables (higher priority)
        cursor.execute(
            "SELECT * FROM prompt_variables WHERE prompt_id = ? AND version = ?",
            (prompt_id, version)
        )
        for row in cursor.fetchall():
            seen_names.add(row["name"])
            variables.append(AvailableVariableResponse(
                name=row["name"],
                value=row["value"],
                description=row["description"],
                source="prompt",
                required=bool(row["required"])
            ))
        
        # Get account-level variables (if not already defined at prompt level)
        cursor.execute(
            "SELECT * FROM account_variables WHERE user_id = ?",
            (user["id"],)
        )
        for row in cursor.fetchall():
            if row["name"] not in seen_names:
                seen_names.add(row["name"])
                variables.append(AvailableVariableResponse(
                    name=row["name"],
                    value=row["value"],
                    description=row["description"],
                    source="account",
                    required=False
                ))
    
    return variables

# Health check
@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# Root endpoint
@api_router.get("/")
async def root():
    return {"message": "Prompt Manager & Memory System API", "version": "1.0.0"}

# Include the router in the main app
app.include_router(api_router)

# Include Memory System Router
app.include_router(memory_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
