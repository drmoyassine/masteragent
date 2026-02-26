# Ask Mode Rules - MasterAgent (PromptSRC)

## Project Structure Overview

```
masteragent/
├── backend/                 # FastAPI Python backend
│   ├── server.py           # Main app, auth, prompts, settings
│   ├── memory_routes.py    # Memory system API endpoints
│   ├── memory_db.py        # Memory database schema
│   ├── memory_services.py  # LLM, Qdrant, GLiNER integration
│   ├── memory_models.py    # Pydantic models for memory
│   ├── prompt_manager.db   # Main SQLite database
│   └── data/memory.db      # Memory system database
├── frontend/               # React 19 frontend
│   ├── src/
│   │   ├── lib/api.js     # All API client functions
│   │   ├── context/       # AuthContext for authentication
│   │   ├── pages/         # Route components
│   │   └── components/ui/ # Shadcn/UI components
│   └── craco.config.js    # Webpack config with @ alias
├── gliner/                 # GLiNER2 NER service
│   └── app.py             # FastAPI entity extraction
└── docker-compose.yml      # Multi-service deployment
```

## Key Technologies
- **Backend**: FastAPI 0.110.1, SQLite, PyJWT, bcrypt
- **Frontend**: React 19, Tailwind CSS, Shadcn/UI, react-router-dom 7
- **ML**: GLiNER2 for NER, OpenAI-compatible APIs for LLM
- **Vector Store**: Qdrant (separate collections for interactions/lessons)
- **Build**: craco (not standard CRA), yarn

## Authentication Flow
1. **Admin Users**: Login → JWT token → `Authorization: Bearer <token>`
2. **Agents**: API key → `X-API-Key: <key>` header
3. Frontend stores token in `localStorage.getItem('auth_token')`

## Memory System Components
- **Entity Types**: Contact, Organization, Project, etc.
- **Entity Subtypes**: Lead, Partner, Internal, etc.
- **Lesson Types**: Process, Risk, Sales, etc.
- **Channel Types**: email, call, meeting, etc.
- **Agents**: Registered AI agents with API keys

## LLM Task Types
- `summarization` - Text summarization
- `embedding` - Vector embeddings
- `vision` - Image/document parsing
- `entity_extraction` - NER via GLiNER
- `pii_scrubbing` - PII detection/removal

## API Prefixes
- `/api/auth/*` - Authentication endpoints
- `/api/prompts/*` - Prompt management
- `/api/memory/*` - Memory system endpoints
- `/api/settings` - User settings
- `/api/keys` - API key management
