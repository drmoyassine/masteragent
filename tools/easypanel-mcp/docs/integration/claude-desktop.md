---
title: Claude Desktop Integration - EasyPanel MCP
description: Step-by-step guide to integrate EasyPanel MCP with Claude Desktop for AI-powered infrastructure management.
keywords: Claude Desktop MCP, AI infrastructure, Claude integration, EasyPanel AI, natural language deployment
---

# 🤖 Claude Desktop Integration

Connect EasyPanel MCP with Claude Desktop to manage infrastructure using natural language.

---

## Overview

Claude Desktop supports MCP (Model Context Protocol) servers, allowing Claude to interact with external tools. EasyPanel MCP exposes all EasyPanel functionality to Claude.

---

## 📋 Prerequisites

- **Claude Desktop** installed
- **EasyPanel MCP** installed and configured
- **EasyPanel API Key**

---

## 🔧 Configuration Steps

### Step 1: Locate Claude Desktop Config

Find or create the configuration file:

<div class="tabs" markdown>

<div class="tab" markdown>
**Windows**
```
%APPDATA%\Claude\claude_desktop_config.json
```
Typically: `C:\Users\YourName\AppData\Roaming\Claude\claude_desktop_config.json`
</div>

<div class="tab" markdown>
**macOS**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```
</div>

<div class="tab" markdown>
**Linux**
```
~/.config/Claude/claude_desktop_config.json
```
</div>

</div>

---

### Step 2: Add EasyPanel MCP Configuration

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "easypanel": {
      "command": "python",
      "args": ["/absolute/path/to/easypanel-mcp/src/server.py"],
      "env": {
        "EASYPANEL_URL": "https://your-easypanel.com",
        "EASYPANEL_API_KEY": "ep_live_your_api_key_here"
      }
    }
  }
}
```

⚠️ **Important:** Use **absolute paths** for the server script.

---

### Step 3: Find Python Path (Optional)

If Claude can't find Python, specify the full path:

<div class="tabs" markdown>

<div class="tab" markdown>
**Windows**
```powershell
# In PowerShell
(Get-Command python).Source
# Output: C:\Python310\python.exe
```
</div>

<div class="tab" markdown>
**macOS/Linux**
```bash
which python3
# Output: /usr/bin/python3 or /home/user/.venv/bin/python
```
</div>

</div>

Update config with full path:

```json
{
  "mcpServers": {
    "easypanel": {
      "command": "/usr/bin/python3",
      "args": ["/home/user/projects/easypanel-mcp/src/server.py"],
      "env": {
        "EASYPANEL_URL": "https://your-easypanel.com",
        "EASYPANEL_API_KEY": "ep_live_your_key"
      }
    }
  }
}
```

---

### Step 4: Restart Claude Desktop

1. Close Claude Desktop completely
2. Reopen Claude Desktop
3. Check for MCP server connection

---

## ✅ Verify Connection

### Test in Claude

Ask Claude:

```
"Can you list my EasyPanel services?"
```

Claude should respond with your services list.

---

## 💬 Example Conversations

### Deploy a Service

**You:** *"Deploy a PostgreSQL database for my new project"*

**Claude:**
```
I'll help you deploy a PostgreSQL database. Let me:
1. Check your existing projects
2. Create or select a project
3. Deploy PostgreSQL service

[Uses list_projects tool]
[Uses create_service tool with postgres:15 image]
[Configures environment variables]

✅ PostgreSQL database deployed successfully!
Service: postgres-db-1
Connection: postgres://postgres:password@postgres-db:5432/postgres
```

### Debug a Service

**You:** *"Why is my API service not responding?"*

**Claude:**
```
Let me investigate the issue:

[Uses get_service tool to check status]
[Uses get_service_logs tool to view logs]

I found the issue:
- Service status: crashed
- Error: Connection timeout to database
- Last log: "Attempting to connect to postgres:5432..."

The service can't connect to the database. Would you like me to:
1. Check if the database service is running
2. Verify network configuration
3. Restart both services
```

### Scale Services

**You:** *"Scale my API to 5 replicas, we're getting more traffic"*

**Claude:**
```
I'll scale your API service to 5 replicas.

[Uses list_services to find your API service]
[Uses update_service to set replicas: 5]

✅ API service scaled successfully!
Previous replicas: 2
New replicas: 5
Status: Updating...
```

---

## 🔧 Advanced Configuration

### Multiple EasyPanel Instances

```json
{
  "mcpServers": {
    "easypanel-prod": {
      "command": "python",
      "args": ["/path/to/easypanel-mcp/src/server.py"],
      "env": {
        "EASYPANEL_URL": "https://prod.easypanel.com",
        "EASYPANEL_API_KEY": "ep_prod_xxx"
      }
    },
    "easypanel-dev": {
      "command": "python",
      "args": ["/path/to/easypanel-mcp/src/server.py"],
      "env": {
        "EASYPANEL_URL": "https://dev.easypanel.com",
        "EASYPANEL_API_KEY": "ep_dev_yyy"
      }
    }
  }
}
```

### Custom Logging

```json
{
  "mcpServers": {
    "easypanel": {
      "command": "python",
      "args": ["/path/to/easypanel-mcp/src/server.py"],
      "env": {
        "EASYPANEL_URL": "https://your-easypanel.com",
        "EASYPANEL_API_KEY": "ep_live_xxx",
        "MCP_LOG_LEVEL": "DEBUG",
        "MCP_DEBUG": "true"
      }
    }
  }
}
```

---

## 🆘 Troubleshooting

### Claude Can't Connect

!!! error "MCP server not available"

    **Solutions:**
    1. Verify Python path is correct
    2. Check script path is absolute
    3. Ensure virtual environment is activated (if used)
    4. Test server manually: `python /path/to/server.py`

### Configuration Not Loading

!!! error "Environment variables not set"

    **Solutions:**
    1. Check JSON syntax is valid
    2. Verify environment variable names
    3. Restart Claude Desktop
    4. Check file permissions

### Server Crashes

!!! error "MCP server exited unexpectedly"

    **Solutions:**
    1. Check logs in server output
    2. Verify EasyPanel credentials
    3. Test connection manually
    4. Increase timeout if needed

---

## 📚 Related Documentation

- **[n8n Integration](n8n.md)** - Workflow automation
- **[GitHub Actions](github-actions.md)** - CI/CD integration
- **[Tools Reference](../tools/overview.md)** - All available tools

---

<p align="center" markdown>
**🤖 Claude connected!** Try asking Claude to deploy a service.
</p>
