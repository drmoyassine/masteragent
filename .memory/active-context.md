# Active Context

> **Last Updated**: 2026-03-01
> **Purpose**: Tracks current session context, recent changes, and immediate next steps.

---

## Current State

**Status**: ✅ Core Architecture Modularized & Hardened
**Testing**: 42/42 Tests Passing (`pytest`)
**Docker**: Running on localhost (port 80), VPS deployment configured

### Commits This Session
| Commit | Description |
|--------|-------------|
| *pending* | 15-Item Backend Refactor: Componentizing `core/`, `routes/`, `memory/` |
| *pending* | Centralize `ARCHITECTURE.md` API-First Module Definitions |
| `ad5fc50` | Add .env.example and fix .gitignore |
| `264bc9f` | Remove localhost defaults for VPS deployment |

---

## Completed Today (2026-03-01)

### 1. Backend Monolith Decomposition ✅
- **`server.py` & `memory_routes.py`**: Totally dismantled. Route logic extracted into standalone `routes/*` and `memory/*` files matching their domain entities.
- **`core/` Framework**: Standalone `db.py` and `auth.py` handlers created to universalize and DRY up validation chains.
- **Legacy Purge**: Obsoleted and safely deleted duplicate models (`old_memory_routes.py`, duplicate functions).

### 2. Security Hardening ✅
- **API Key Hashes**: Replaced plaintext conditional API Key verifications with cryptographically sound `hashlib.sha256` hashing routines.
- **Admin Warning Guard**: Injected explicit terminal boot warnings when `db_init.py` relies on `admin123` defaults without an explicit `.env` toggle.

### 3. Frontend Standardization ✅
- **Delete Handlers**: Unified `MemorySettingsPage.jsx` logic by ripping out raw `.then()` calls and installing robust `async () => { try/catch }` blocks bound to `toast` UI alerts.
- **Variable Alignment**: Adjusted API default routing versions from the disjointed `main` syntax back to `v1`.

---

## Key Files Modified

| File | Changes |
|------|---------|
| `backend/core/*` | New shared utility foundation (auth, db hooks) |
| `backend/routes/*` | New prompt manager controllers |
| `backend/memory/*` | New memory system controllers |
| `backend/server.py` | Strip down to barebone mount logic |
| `frontend/src/pages/MemorySettingsPage.jsx` | Standardized `toast` UX on inline deletes |
| `frontend/src/context/ConfigContext.jsx` | Clearer variables (removed ambiguous `hasStorage`) |

---

## VPS Deployment Guide

### Required Environment Variables
```env
PORT=8080
FRONTEND_URL=https://your-domain.com
GITHUB_REDIRECT_URI=https://your-domain.com/api/auth/github/callback
JWT_SECRET_KEY=your-secure-secret
```

### Optional Variables
```env
GITHUB_CLIENT_ID=your-github-oauth-id
GITHUB_CLIENT_SECRET=your-github-oauth-secret
GITHUB_TOKEN=your-github-pat-for-storage
GITHUB_REPO=owner/repo
```

---

## Next Steps

1. **Configure LLM APIs** - Via `/app/memory` → LLM APIs tab
2. **Start GLiNER** (optional): `docker-compose --profile gliner up -d`
3. **Test login** on VPS with `admin@promptsrc.com` / `admin123`

---

## Architecture Notes

### Dual Database System
- **Main DB**: `backend/prompt_manager.db` - Users, prompts, settings
- **Memory DB**: `backend/data/memory.db` - Entities, interactions, lessons

### Dual Authentication
- **JWT (Bearer)**: Admin endpoints via `require_admin_auth()`
- **API Key (X-API-Key)**: Agent endpoints via `verify_agent_key()`

### Service Ports (Docker)
- Frontend/Backend: 80 (nginx proxy)
- Qdrant REST: 6333
- Qdrant gRPC: 6334
- GLiNER: 8002 (optional)
