"""
routes/auth.py — Authentication endpoints

Handles: signup, login, GitHub OAuth flow, auth status, logout.
"""
import os
import secrets
import hashlib
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.auth import (
    hash_password, verify_password,
    create_access_token, get_current_user, SECRET_KEY, ALGORITHM,
)
from core.secrets import encrypt_secret
from core.db import get_db_context
from core.storage import get_redis_client
from jose import jwt, JWTError

logger = logging.getLogger(__name__)
router = APIRouter()

# GitHub OAuth config
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.environ.get("GITHUB_REDIRECT_URI", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

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
    is_admin: bool = False
    created_at: str
    updated_at: str


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: Optional[UserResponse] = None


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def user_to_response(user: dict) -> UserResponse:
    return UserResponse(
        id=user["id"],
        github_id=user.get("github_id"),
        username=user["username"],
        email=user.get("email"),
        avatar_url=user.get("avatar_url"),
        github_url=user.get("github_url"),
        plan=user.get("plan", "free"),
        is_admin=bool(user.get("is_admin", False)),
        created_at=user["created_at"],
        updated_at=user["updated_at"],
    )


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post("/auth/signup", response_model=AuthResponse)
async def signup(user_data: UserCreate):
    """Register a new user with email/password."""
    if os.environ.get("ALLOW_PUBLIC_SIGNUP", "true").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=403, detail="Public signup is disabled")
    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (user_data.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")
        cursor.execute("SELECT id FROM users WHERE username = %s", (user_data.username,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Username already taken")
        user_id = str(uuid.uuid4())
        password_hash = hash_password(user_data.password)
        cursor.execute(
            """INSERT INTO users (id, username, email, password_hash, plan, created_at, updated_at)
               VALUES (%s, %s, %s, %s, 'free', %s, %s)""",
            (user_id, user_data.username, user_data.email, password_hash, now, now),
        )
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = dict(cursor.fetchone())
    token = create_access_token(data={"sub": user_id})
    return AuthResponse(token=token, user=user_to_response(user))


@router.post("/auth/login", response_model=AuthResponse)
async def login(credentials: UserLogin, request: Request):
    """Login with email/password."""
    client_ip = request.client.host if request.client else "unknown"
    login_bucket = hashlib.sha256(f"{client_ip}:{credentials.email.lower()}".encode()).hexdigest()
    rate_key = f"login_attempt:{login_bucket}"
    try:
        redis = get_redis_client()
        attempts = redis.incr(rate_key)
        if attempts == 1:
            redis.expire(rate_key, 900)
        if attempts > int(os.environ.get("LOGIN_MAX_ATTEMPTS", "10")):
            raise HTTPException(status_code=429, detail="Too many login attempts; try again later")
    except HTTPException:
        raise
    except Exception:
        redis = None
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (credentials.email,))
        user = cursor.fetchone()
        if not user:
            logger.warning(f"Login failed: user not found for email {credentials.email}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
        user = dict(user)
        if not user.get("password_hash"):
            raise HTTPException(status_code=401, detail="This account uses GitHub login. Please sign in with GitHub.")
        if not verify_password(credentials.password, user["password_hash"]):
            logger.warning(f"Login failed: password mismatch for email {credentials.email}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("UPDATE users SET updated_at = %s WHERE id = %s", (now, user["id"]))
    logger.info(f"Successful login for user: {credentials.email}")
    if redis is not None:
        try:
            redis.delete(rate_key)
        except Exception:
            pass
    token = create_access_token(data={"sub": user["id"]})
    return AuthResponse(token=token, user=user_to_response(user))


@router.get("/auth/github/login")
async def github_login():
    """Redirect to GitHub OAuth."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth not configured. Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.",
        )
    state = jwt.encode(
        {
            "purpose": "github_oauth",
            "nonce": secrets.token_urlsafe(16),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    auth_url = (
        f"https://github.com/login/oauth/authorize?"
        f"client_id={GITHUB_CLIENT_ID}&"
        f"redirect_uri={GITHUB_REDIRECT_URI}&"
        f"scope=user:email,repo&"
        f"state={state}"
    )
    return {"auth_url": auth_url}


@router.get("/auth/github/callback")
async def github_callback(code: str, state: str = None):
    """Handle GitHub OAuth callback."""
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state")
    try:
        state_payload = jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
        if state_payload.get("purpose") != "github_oauth":
            raise JWTError("wrong OAuth state purpose")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                data={"client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET, "code": code},
                headers={"Accept": "application/json"},
            )
            token_data = token_resp.json()
        github_token = token_data.get("access_token")
        if not github_token:
            error = token_data.get("error_description", "Failed to get access token")
            return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?{urlencode({'error': error})}")

        async with httpx.AsyncClient() as client:
            gh_headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/json"}
            user_resp = await client.get("https://api.github.com/user", headers=gh_headers)
            github_user = user_resp.json()
            emails_resp = await client.get("https://api.github.com/user/emails", headers=gh_headers)
            emails = emails_resp.json()

        primary_email = next((e.get("email") for e in emails if e.get("primary")), None)
        if not primary_email and emails:
            primary_email = emails[0].get("email")

        now = datetime.now(timezone.utc).isoformat()
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE github_id = %s", (github_user["id"],))
            existing = cursor.fetchone()
            if existing:
                user_id = existing["id"]
                cursor.execute(
                    "UPDATE users SET username=%s, email=%s, avatar_url=%s, github_token=%s, updated_at=%s WHERE id=%s",
                    (github_user["login"], primary_email, github_user.get("avatar_url"), encrypt_secret(github_token), now, user_id),
                )
            else:
                user_id = str(uuid.uuid4())
                cursor.execute(
                    """INSERT INTO users (id, github_id, username, email, avatar_url, github_url, github_token, plan, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, 'free', %s, %s)""",
                    (user_id, github_user["id"], github_user["login"], primary_email,
                     github_user.get("avatar_url"), github_user.get("html_url"), encrypt_secret(github_token), now, now),
                )
        jwt_token = create_access_token(data={"sub": user_id})
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?{urlencode({'token': jwt_token})}")
    except Exception as e:
        logger.error(f"GitHub OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?{urlencode({'error': 'Authentication failed'})}")


@router.get("/auth/status", response_model=AuthStatusResponse)
async def auth_status(user: dict = Depends(get_current_user)):
    """Check authentication status."""
    if not user:
        return AuthStatusResponse(authenticated=False)
    return AuthStatusResponse(authenticated=True, user=user_to_response(user))


@router.post("/auth/logout")
async def logout():
    """Logout user (client removes token)."""
    return {"message": "Logged out successfully"}
