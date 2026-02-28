# PromptSRC - Prompt Manager & Agent Memory System

<div align="center">

![PromptSRC](https://img.shields.io/badge/PromptSRC-AI%20Agent%20Infrastructure-22C55E?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=black)
![Qdrant](https://img.shields.io/badge/Qdrant-FF6B6B?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)

**The complete infrastructure for AI agents: version-controlled prompts + persistent memory system**

[Getting Started](#getting-started) • [Features](#features) • [API Reference](#api-reference) • [Deployment](#deployment)

</div>

---

## Overview

PromptSRC provides two essential modules for building production-ready AI agents:

1. **Prompt Manager** - Version-controlled prompts stored in GitHub, consumable via HTTP API
2. **Memory System** - Persistent memory for agents with semantic search, entity tracking, and lesson extraction

## Features

### Prompt Manager
- **Multi-file Markdown Structure** - Organize complex prompts as ordered sections
- **Git-backed Versioning** - Every version maps to a GitHub branch
- **Variable Injection** - Mustache-style placeholders with runtime injection
- **Render API** - Clean HTTP endpoints for consuming compiled prompts
- **Starter Templates** - Agent Persona, Task Executor, Knowledge Expert, and more
- **API Key Authentication** - Secure access for your agents

### Memory System
- **Structured Storage** - Store interactions with metadata, entities, and documents
- **Semantic Search** - Vector-powered search with Qdrant
- **Entity Timelines** - Track interaction history for contacts, organizations, projects
- **Curated Lessons** - Extract and organize knowledge from interactions
- **GLiNER2 NER** - Automatic entity extraction using state-of-the-art NER
- **PII Scrubbing** - Separate private and shared memories with configurable PII protection
- **Admin-configurable LLMs** - Configure separate APIs for summarization, embedding, vision, NER, PII
- **Rate Limiting** - Per-agent request throttling
- **OpenClaw Sync** - Export memories to Markdown for external tools

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python 3.11+) |
| Frontend | React 18, Tailwind CSS, Shadcn/UI |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Vector Store | Qdrant |
| NER Engine | GLiNER2 |
| Authentication | JWT (admin), API Keys (agents) |
| Containerization | Docker, Docker Compose |

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Node.js 18+ (for local development)
- Python 3.11+ (for local development)
- GitHub account (for Prompt Manager)

### Quick Start with Docker

```bash
# Clone the repository
git clone https://github.com/your-org/promptsrc.git
cd promptsrc

# Copy environment template
cp .env.example .env

# Start all services
docker-compose up -d

# Access the application
open http://localhost
```

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8001

# Frontend
cd frontend
yarn install
yarn start

# GLiNER Service (optional)
cd gliner
docker build -t gliner .
docker run -p 8002:8002 gliner
```

### Environment Variables

```bash
# Backend (.env)
JWT_SECRET_KEY=your_secret_key
MONGO_URL=mongodb://localhost:27017
DB_NAME=promptsrc

# GitHub Integration
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
GITHUB_REDIRECT_URI=http://localhost/api/auth/github/callback

# Vector Database
QDRANT_URL=http://localhost:6333

# GLiNER NER Service
GLINER_URL=http://localhost:8002

# Frontend (.env)
REACT_APP_BACKEND_URL=http://localhost
```

## Project Structure

```
promptsrc/
├── backend/
│   ├── core/                  # Shared DB and Auth logic
│   ├── routes/                # Prompt Manager endpoints
│   ├── memory/                # Memory System endpoints
│   ├── server.py              # Main FastAPI application
│   ├── memory_db.py           # Memory system database schema
│   ├── memory_models.py       # Pydantic models
│   ├── memory_services.py     # LLM and vector services
│   ├── memory_tasks.py        # Background tasks
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── LandingPage.jsx
│   │   │   ├── AuthPage.jsx
│   │   │   ├── DashboardPage.jsx
│   │   │   ├── MemorySettingsPage.jsx
│   │   │   ├── MemoryExplorerPage.jsx
│   │   │   └── MemoryMonitorPage.jsx
│   │   ├── components/
│   │   │   ├── ui/             # Shadcn components
│   │   │   └── layout/
│   │   └── lib/
│   │       └── api.js          # API client
│   └── package.json
├── gliner/
│   ├── app.py                  # GLiNER2 NER service
│   └── Dockerfile
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## API Reference

### Authentication

All admin endpoints require JWT authentication:
```bash
curl -X POST /api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "password"}'
```

Agent endpoints require API key authentication:
```bash
curl -X POST /api/memory/interactions \
  -H "X-API-Key: mem_xxxx" \
  -F "text=Meeting notes..."
```

### Prompt Manager Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prompts` | List all prompts |
| POST | `/api/prompts` | Create prompt |
| GET | `/api/prompts/{id}` | Get prompt |
| PUT | `/api/prompts/{id}` | Update prompt |
| DELETE | `/api/prompts/{id}` | Delete prompt |
| GET | `/api/prompts/{id}/sections` | List sections |
| POST | `/api/prompts/{id}/sections` | Create section |
| POST | `/api/prompts/{id}/{version}/render` | Render prompt |
| GET | `/api/templates` | List templates |

### Memory System Endpoints

#### Configuration (JWT Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memory/config/entity-types` | List entity types |
| POST | `/api/memory/config/entity-types` | Create entity type |
| GET | `/api/memory/config/llm-configs` | List LLM configs |
| PUT | `/api/memory/config/llm-configs/{id}` | Update LLM config |
| GET | `/api/memory/config/agents` | List agents |
| POST | `/api/memory/config/agents` | Create agent (returns API key) |
| GET | `/api/memory/config/settings` | Get settings |
| PUT | `/api/memory/config/settings` | Update settings |

#### Agent APIs (API Key Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/memory/interactions` | Ingest interaction |
| POST | `/api/memory/search` | Semantic search |
| GET | `/api/memory/timeline/{type}/{id}` | Entity timeline |
| GET | `/api/memory/lessons` | List lessons |

#### Admin APIs (JWT Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memory/daily/{date}` | Daily memory log |
| GET | `/api/memory/memories/{id}` | Memory detail |
| GET | `/api/memory/admin/stats` | System statistics |
| POST | `/api/memory/admin/sync/openclaw` | Trigger OpenClaw sync |
| POST | `/api/memory/admin/tasks/mine-lessons` | Trigger lesson mining |

### Example: Ingest an Interaction

```python
import requests

response = requests.post(
    "https://your-domain.com/api/memory/interactions",
    headers={"X-API-Key": "mem_YhZtU7wjp8-gFQKAjyT7ZwKzTC3L7R7I6cqHM3oJbYA"},
    data={
        "text": "Had a meeting with John Smith from Acme Corp about the partnership deal.",
        "channel": "meeting",
        "entities": '[{"type": "Contact", "name": "John Smith", "role": "primary"}, {"type": "Organization", "name": "Acme Corp", "role": "mentioned"}]',
        "metadata": '{"duration": "45min", "location": "zoom"}'
    }
)

print(response.json())
# {
#   "id": "abc123",
#   "timestamp": "2026-02-25T10:30:00Z",
#   "summary_text": "Partnership meeting with Acme Corp",
#   "entities": [...],
#   ...
# }
```

### Example: Search Memories

```python
response = requests.post(
    "https://your-domain.com/api/memory/search",
    headers={"Authorization": "Bearer <jwt_token>"},
    json={
        "query": "partnership discussions with Acme",
        "filters": {"channel": "meeting"},
        "limit": 10
    }
)

print(response.json())
# {"results": [...], "total": 5}
```

## Deployment

### Docker Compose (Recommended)

```yaml
version: '3.8'

services:
  promptsrc:
    build: .
    ports:
      - "80:80"
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - DATABASE_TYPE=postgresql
      - POSTGRES_URL=${POSTGRES_URL}
      - QDRANT_URL=http://qdrant:6333
      - GLINER_URL=http://gliner:8002
    depends_on:
      - qdrant
      - gliner

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  gliner:
    build: ./gliner
    ports:
      - "8002:8002"

volumes:
  qdrant_data:
```

### Production Checklist

- [ ] Set strong `JWT_SECRET_KEY`
- [ ] Configure PostgreSQL instead of SQLite
- [ ] Set up Qdrant with persistence
- [ ] Configure LLM API keys in admin UI
- [ ] Enable HTTPS
- [ ] Set up monitoring and logging
- [ ] Configure rate limiting
- [ ] Back up database regularly

## Default Credentials

For initial setup:
- **Email**: `admin@promptsrc.com`
- **Password**: `admin123`

⚠️ **Change these immediately in production!**

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- **Architecture Details**: Review [ARCHITECTURE.md](ARCHITECTURE.md)
- **Documentation**: [docs.promptsrc.com](https://docs.promptsrc.com)
- **Issues**: [GitHub Issues](https://github.com/your-org/promptsrc/issues)
- **Email**: support@promptsrc.com

---

<div align="center">
Built with ❤️ for AI Agent Developers
</div>
