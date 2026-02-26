# Debug Mode Rules - MasterAgent (PromptSRC)

## Service Health Endpoints
```bash
# Backend health
curl http://localhost:8001/api/health

# Memory system health
curl http://localhost:8001/api/memory/health

# GLiNER NER service
curl http://localhost:8002/health

# Qdrant vector store
curl http://localhost:6333/collections
```

## Common Error Patterns

### Authentication Errors
```
401 "Authentication required" → Missing JWT token in Authorization header
401 "Invalid API key" → Missing or invalid X-API-Key header
401 "Invalid or expired token" → JWT expired or malformed
```

### Database Errors
```
sqlite3.OperationalError: no such table → Run init_db() or init_memory_db()
FOREIGN KEY constraint failed → Check parent record exists
UNIQUE constraint failed → Duplicate key (entity_type.name, etc.)
```

### Service Connection Errors
```
Connection refused localhost:8002 → GLiNER service not running
Connection refused localhost:6333 → Qdrant not running
httpx.ConnectError → External LLM API unreachable
```

## Debugging Commands
```bash
# Check backend logs (Docker)
docker-compose logs promptsrc -f

# Check specific service
docker-compose logs gliner -f
docker-compose logs qdrant -f

# Run tests with verbose output
cd backend && pytest tests/test_memory_auth.py -v -s

# Test specific endpoint
curl -X GET http://localhost:8001/api/memory/config/entity-types \
  -H "Authorization: Bearer <token>"
```

## Test Credentials
- Email: `admin@promptsrc.com`
- Password: `admin123`
- Agent API Key: `mem_YhZtU7wjp8-gFQKAjyT7ZwKzTC3L7R7I6cqHM3oJbYA`

## Database Inspection
```bash
# Main DB
sqlite3 backend/prompt_manager.db ".tables"
sqlite3 backend/prompt_manager.db "SELECT * FROM users;"

# Memory DB
sqlite3 backend/data/memory.db ".tables"
sqlite3 backend/data/memory.db "SELECT * FROM memory_agents;"
```

## Common Issues
1. **Port conflicts**: Backend uses 8001 (Docker) vs 8000 (local)
2. **Missing env vars**: Check `REACT_APP_BACKEND_URL` for frontend
3. **Qdrant collections**: Run `init_qdrant_collections()` if missing
4. **API key format**: Agent keys start with `mem_`
