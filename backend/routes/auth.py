"""
routes/auth.py — Authentication endpoints

Handles: signup, login, GitHub OAuth flow, auth status, logout.
"""
import os
import secrets
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.auth import (
    hash_password, verify_password,
    create_access_token, get_current_user,
)
from core.db import get_db_context

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
        created_at=user["created_at"],
        updated_at=user["updated_at"],
    )


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post("/auth/signup", response_model=AuthResponse)
async def signup(user_data: UserCreate):
    """Register a new user with email/password."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (user_data.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")
        cursor.execute("SELECT id FROM users WHERE username = ?", (user_data.username,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Username already taken")
        user_id = str(uuid.uuid4())
        password_hash = hash_password(user_data.password)
        cursor.execute(
            """INSERT INTO users (id, username, email, password_hash, plan, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'free', ?, ?)""",
            (user_id, user_data.username, user_data.email, password_hash, now, now),
        )
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = dict(cursor.fetchone())
    token = create_access_token(data={"sub": user_id})
    return AuthResponse(token=token, user=user_to_response(user))


@router.post("/auth/login", response_model=AuthResponse)
async def login(credentials: UserLogin):
    """Login with email/password."""
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (credentials.email,))
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
        cursor.execute("UPDATE users SET updated_at = ? WHERE id = ?", (now, user["id"]))
    logger.info(f"Successful login for user: {credentials.email}")
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
    state = secrets.token_urlsafe(16)
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
            return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?error={error}")

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
            cursor.execute("SELECT * FROM users WHERE github_id = ?", (github_user["id"],))
            existing = cursor.fetchone()
            if existing:
                user_id = existing["id"]
                cursor.execute(
                    "UPDATE users SET username=?, email=?, avatar_url=?, github_token=?, updated_at=? WHERE id=?",
                    (github_user["login"], primary_email, github_user.get("avatar_url"), github_token, now, user_id),
                )
            else:
                user_id = str(uuid.uuid4())
                cursor.execute(
                    """INSERT INTO users (id, github_id, username, email, avatar_url, github_url, github_token, plan, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'free', ?, ?)""",
                    (user_id, github_user["id"], github_user["login"], primary_email,
                     github_user.get("avatar_url"), github_user.get("html_url"), github_token, now, now),
                )
        jwt_token = create_access_token(data={"sub": user_id})
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?token={jwt_token}")
    except Exception as e:
        logger.error(f"GitHub OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?error=Authentication failed")


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
