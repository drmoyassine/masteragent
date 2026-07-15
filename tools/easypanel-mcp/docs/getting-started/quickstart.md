---
title: Quick Start - EasyPanel MCP
description: Get started with EasyPanel MCP in 5 minutes. Deploy your first service using AI agents.
keywords: EasyPanel quick start, MCP tutorial, deploy with AI, Docker service deployment
---

# 🚀 Quick Start Guide

Get up and running with EasyPanel MCP in 5 minutes and deploy your first service using AI!

---

## ⏱️ 5-Minute Setup

### Step 1: Install (1 minute)

```bash
# Clone repository
git clone https://github.com/dannymaaz/easypanel-mcp
cd easypanel-mcp

# Create virtual environment and activate
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure (1 minute)

```bash
# Copy environment file
cp .env.example .env

# Edit .env with your settings
# Use your favorite editor: nano, vim, notepad, etc.
```

Edit these two lines in `.env`:

```bash
EASYPANEL_URL=https://your-easypanel.com
EASYPANEL_API_KEY=your_api_key_here
```

!!! tip "Getting Your API Key"
    1. Open your EasyPanel dashboard
    2. Go to **Settings** → **API Keys**
    3. Click **Generate New Key**
    4. Copy the key and paste it in `.env`

### Step 3: Test Connection (1 minute)

```bash
# Quick connection test
python -c "
import asyncio
from src.client import EasyPanelClient
from config import config

async def test():
    client = EasyPanelClient(config.easypanel)
    await client.connect()
    healthy = await client.health_check()
    print(f'✅ EasyPanel connection: {\"OK\" if healthy else \"FAILED\"}')
    await client.disconnect()

asyncio.run(test())
"
```

Expected output:
```
✅ EasyPanel connection: OK
```

### Step 4: Start Server (30 seconds)

```bash
# Start MCP server
python src/server.py
```

The server is now running and waiting for AI agent commands!

### Step 5: Connect AI Agent (2 minutes)

Choose your AI agent:

<div class="tabs" markdown>

<div class="tab" markdown>
**Claude Desktop**

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "easypanel": {
      "command": "python",
      "args": ["/path/to/easypanel-mcp/src/server.py"],
      "env": {
        "EASYPANEL_URL": "https://your-easypanel.com",
        "EASYPANEL_API_KEY": "your_key"
      }
    }
  }
}
```

Then restart Claude Desktop.
</div>

<div class="tab" markdown>
**HTTP Mode (n8n, custom)**

```bash
# Start in HTTP mode
python src/server.py http
```

Then send requests to `http://localhost:8080/mcp`
</div>

</div>

---

## 💬 Your First AI Deployment

Now you can talk to your AI agent naturally!

### Example Conversation

<div class="admonition example" markdown>
<p class="admonition-title">Deploy a Flask API with PostgreSQL</p>

**You:** *"Deploy my Flask API with PostgreSQL database"*

**AI Agent:** 
```
I'll help you deploy a Flask API with PostgreSQL. Let me:

1. Create a new project called 'flask-api'
2. Deploy PostgreSQL database
3. Deploy Flask application
4. Configure networking

Starting deployment...

✅ Project 'flask-api' created
✅ Service 'postgres-db' deployed (postgres:15)
✅ Service 'flask-app' deployed (your-flask:latest)
✅ Internal network 'flask-net' created
✅ Services connected securely

🎉 Deployment complete!
📊 Dashboard: https://flask-api.easypanel.com
🔗 API: https://api.flask-api.easypanel.com
```
</div>

---

## 🎯 Common Commands

Here are some natural language commands you can use:

### Service Management

```
"List all my services"
"Show me the logs for the worker service"
"Restart the API service"
"Create a new Redis cache service"
```

### Project Management

```
"Create a new project for my staging environment"
"Show me all projects"
"Delete the test project"
```

### Network Configuration

```
"Create an internal network for my database"
"List all networks"
"Set up isolated networking for my services"
```

### Deployments

```
"Deploy version 2.0 of my application"
"Show me the deployment history"
"Rollback to the previous version"
```

---

## 📋 Complete Example: Full Stack App

Let's deploy a complete full-stack application:

### Request

```
"Deploy my full-stack app with React frontend, Node.js backend, 
PostgreSQL database, and Redis cache. Use an internal network 
for the database and cache."
```

### What the AI Will Do

```
1. ✅ Create project 'fullstack-app'
2. ✅ Create internal network 'app-internal'
3. ✅ Deploy PostgreSQL service (postgres:15)
   - Connected to app-internal network
   - Environment variables configured
4. ✅ Deploy Redis service (redis:7-alpine)
   - Connected to app-internal network
5. ✅ Deploy Node.js backend
   - Connected to app-internal and public networks
   - Database connection configured
6. ✅ Deploy React frontend
   - Public access enabled
   - Backend URL configured

🎉 Full stack deployed successfully!
```

---

## 🔍 Verify Your Deployment

### Check Services

```
"Show me all running services"
```

AI Response:
```json
{
  "success": true,
  "data": [
    {"name": "postgres-db", "status": "running", "image": "postgres:15"},
    {"name": "redis-cache", "status": "running", "image": "redis:7-alpine"},
    {"name": "nodejs-backend", "status": "running", "image": "myapp/backend:latest"},
    {"name": "react-frontend", "status": "running", "image": "myapp/frontend:latest"}
  ],
  "message": "Found 4 services"
}
```

### Check Logs

```
"Show me the last 50 logs from the backend"
```

### Health Check

```
"Is everything running healthy?"
```

---

## 🛠️ Next Steps

Now that you have the basics:

### Learn More

- **[Tools Reference](../tools/overview.md)** - All available tools
- **[Integration Guides](../integration/claude-desktop.md)** - Connect your AI
- **[Advanced Examples](../examples/advanced.md)** - Complex workflows

### Best Practices

- **[Security](../faq.md#security)** - Secure your setup
- **[Networking](../tools/networks.md)** - Isolate services
- **[Monitoring](../examples/real-world.md)** - Monitor deployments

---

## 🆘 Troubleshooting

### Server Won't Start

!!! error "Connection refused to EasyPanel"

    **Solution:**
    1. Verify `EASYPANEL_URL` is correct
    2. Check API key is valid
    3. Ensure EasyPanel is running

### AI Agent Can't Connect

!!! error "MCP server not responding"

    **Solution:**
    1. Check server is running: `python src/server.py`
    2. Verify path in AI agent config
    3. Check for port conflicts

### Deployment Fails

!!! error "Service creation failed"

    **Solution:**
    1. Check EasyPanel permissions
    2. Verify project exists
    3. Review service configuration

---

## 📚 Quick Reference

### Environment Variables

```bash
EASYPANEL_URL=https://your-easypanel.com
EASYPANEL_API_KEY=your_key
MCP_PORT=8080
```

### Start Commands

```bash
# Standard mode (stdio)
python src/server.py

# HTTP mode
python src/server.py http
```

### Test Connection

```bash
python src/server.py  # Then send MCP requests
```

---

## ✅ Success Checklist

- [ ] Server starts without errors
- [ ] AI agent connects successfully
- [ ] Can list services via AI
- [ ] Can create a test service
- [ ] Can view service logs
- [ ] Can restart services

---

<p align="center" markdown>
**🎉 Congratulations!** You're now deploying with AI.  
Explore **[Tools Reference](../tools/overview.md)** for all capabilities.
</p>
