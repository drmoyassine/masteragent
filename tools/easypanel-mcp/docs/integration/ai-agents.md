---
title: AI Agents Integration - EasyPanel MCP
description: Integrate EasyPanel MCP with Claude Desktop, ChatGPT, Cursor, Cline, and other AI agents for infrastructure management.
keywords: EasyPanel MCP, Claude Desktop, ChatGPT, Cursor IDE, Cline, AI agents, MCP integration
---

# 🤖 AI Agents Integration

EasyPanel MCP works with **any AI agent that supports the Model Context Protocol (MCP)**. This guide covers integration with popular AI agents and IDEs.

---

## 📋 Supported AI Agents

| Agent | Type | Setup Complexity | Best For |
|-------|------|------------------|----------|
| **Claude Desktop** | Desktop App | ⭐ Easy | General purpose, natural language |
| **Cursor IDE** | Code Editor | ⭐ Easy | Development workflows |
| **Cline** | VS Code Extension | ⭐ Easy | Coding assistance |
| **ChatGPT Desktop** | Desktop App | ⭐⭐ Medium | GPT-4 infrastructure management |
| **n8n** | Automation Platform | ⭐⭐ Medium | Workflow automation |
| **Custom Agents** | Any MCP Client | ⭐⭐⭐ Advanced | Custom integrations |

---

## 🎯 Claude Desktop Integration

### What is Claude Desktop?

Claude Desktop is Anthropic's desktop application that supports MCP servers, allowing Claude to interact with external tools and services.

### Installation

1. **Download Claude Desktop**
   - macOS: [Download from Anthropic](https://claude.ai/download)
   - Windows: Coming soon
   - Linux: Use Claude via web or third-party clients

2. **Install on macOS**
   ```bash
   # Install to Applications
   mv ~/Downloads/Claude.app /Applications/
   ```

### Configuration

1. **Open Claude Desktop config file:**

   ```bash
   # macOS
   open ~/Library/Application\ Support/Claude/claude_desktop_config.json

   # Windows (when available)
   %APPDATA%\Claude\claude_desktop_config.json
   ```

2. **Add EasyPanel MCP configuration:**

   ```json
   {
     "mcpServers": {
       "easypanel": {
         "command": "python",
         "args": ["/path/to/easypanel-mcp/src/server.py"],
         "cwd": "/path/to/easypanel-mcp",
         "env": {
           "EASYPANEL_URL": "https://your-easypanel.com",
           "EASYPANEL_API_KEY": "ep_live_xxxxxxxxxxxxx"
         }
       }
     }
   }
   ```

3. **Restart Claude Desktop**

### Usage Examples

Once configured, you can ask Claude to:

```
User: "Show me all my projects in EasyPanel"
Claude: 📊 I can see you have 3 projects:
        - dashboard (Active)
        - test (Active)
        - wikileyes (Active)

User: "Deploy a PostgreSQL database in my test project"
Claude: 🚀 Creating PostgreSQL service...
        ✅ Service 'postgres-db' deployed successfully
        📦 Image: postgres:15
        🔗 Connected to project 'test'
```

---

## 💻 Cursor IDE Integration

### What is Cursor?

Cursor is an AI-powered code editor with built-in MCP support.

### Installation

1. **Download Cursor**
   - Visit: https://cursor.sh
   - Download for your platform (Windows, macOS, Linux)

2. **Install and open Cursor**

### Configuration

1. **Open Cursor Settings**
   - `Cmd/Ctrl + Shift + P` → "Cursor Settings"
   - Or: File → Settings → AI → MCP Servers

2. **Add EasyPanel MCP:**

   ```json
   {
     "mcpServers": {
       "easypanel": {
         "command": "python",
         "args": ["/absolute/path/to/easypanel-mcp/src/server.py"],
         "cwd": "/absolute/path/to/easypanel-mcp",
         "env": {
           "EASYPANEL_URL": "https://your-easypanel.com",
           "EASYPANEL_API_KEY": "ep_live_xxxxxxxxxxxxx"
         }
       }
     }
   }
   ```

3. **Reload Cursor**

### Usage in Cursor

- Use `Cmd/Ctrl + K` to open AI chat
- Ask about your EasyPanel infrastructure
- Deploy services directly from code comments

```
// @easypanel Deploy this API to production
async function deploy() {
  // Cursor will use EasyPanel MCP to deploy
}
```

---

## 🔧 Cline (VS Code Extension)

### What is Cline?

Cline is a VS Code extension that brings AI coding assistance with MCP support.

### Installation

1. **Install Cline in VS Code**
   - Open VS Code
   - Extensions: `Ctrl+Shift+X`
   - Search for "Cline"
   - Install

2. **Configure Cline**

   Open Cline settings (`Ctrl+,`) and add MCP configuration:

   ```json
   {
     "cline.mcpServers": {
       "easypanel": {
         "command": "python",
         "args": ["/path/to/easypanel-mcp/src/server.py"],
         "cwd": "/path/to/easypanel-mcp",
         "env": {
           "EASYPANEL_URL": "https://your-easypanel.com",
           "EASYPANEL_API_KEY": "ep_live_xxxxxxxxxxxxx"
         }
       }
     }
   }
   ```

### Usage

- Open Cline chat in VS Code
- Ask Cline to manage your EasyPanel infrastructure
- Deploy services while coding

---

## 🤖 ChatGPT Desktop Integration

### What is ChatGPT Desktop?

Third-party desktop clients for ChatGPT that support MCP.

### Supported Clients

1. **ChatGPT Desktop (macOS/Windows)**
   - GitHub: https://github.com/lencx/ChatGPT
   - Supports MCP via plugins

2. **OpenAI Desktop**
   - Check for MCP support in settings

### Configuration

Configuration varies by client. Look for MCP or plugin settings and add EasyPanel MCP server details.

---

## ⚡ n8n Automation Integration

### What is n8n?

n8n is a workflow automation platform that can integrate with MCP servers.

### Installation

1. **Self-host n8n:**
   ```bash
   docker run -d \
     -p 5678:5678 \
     -v n8n_data:/home/node/.n8n \
     n8nio/n8n
   ```

2. **Or use n8n Cloud:**
   - Visit: https://n8n.io/cloud

### Configuration

1. **Install MCP Node for n8n**
   - Open n8n
   - Settings → Community Nodes → Install
   - Search for "MCP"

2. **Add EasyPanel MCP Node:**
   - Create new workflow
   - Add MCP node
   - Configure:
     ```
     Server URL: http://localhost:8080
     Transport: HTTP
     ```

3. **Run EasyPanel MCP in HTTP mode:**
   ```bash
   python src/server.py http
   ```

### Example Workflow

```
Trigger (Webhook)
    ↓
MCP Node: list_projects
    ↓
IF: Project exists?
    ↓ YES → MCP Node: deploy_service
    ↓ NO  → MCP Node: create_project → deploy_service
    ↓
Response (Success message)
```

---

## 🔌 Custom MCP Clients

### HTTP Mode Configuration

For custom clients, run EasyPanel MCP in HTTP mode:

```bash
python src/server.py http
```

Default endpoint: `http://127.0.0.1:8080`

### MCP Protocol Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mcp` | POST | Main MCP endpoint |
| `/` | POST | Alternative endpoint |

### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "my-custom-client",
      "version": "1.0.0"
    }
  }
}
```

### Example Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {
        "list": true
      }
    },
    "serverInfo": {
      "name": "easypanel-mcp",
      "version": "1.0.0"
    }
  }
}
```

---

## 🛠️ Available Tools

Once connected, AI agents can use these tools:

### Projects
- `list_projects` - List all projects
- `get_project` - Get project details
- `create_project` - Create new project
- `delete_project` - Delete project

### Services
- `list_services` - List all services
- `get_service` - Get service details
- `create_service` - Create new service
- `update_service` - Update service config
- `delete_service` - Delete service
- `restart_service` - Restart service
- `deploy_service` - Deploy/redeploy service

### Deployments
- `list_deployments` - List all deployments
- `get_deployment` - Get deployment details
- `create_deployment` - Create new deployment
- `get_deployment_logs` - Get deployment logs

### Networks
- `list_networks` - List all networks
- `create_network` - Create new network
- `delete_network` - Delete network

---

## 🔒 Security Considerations

### 1. Protect API Keys

- **Never** commit `.env` files to version control
- Use environment variables or secrets managers
- Rotate API keys periodically

### 2. Network Security

```json
{
  "mcpServers": {
    "easypanel": {
      "env": {
        "MCP_HOST": "127.0.0.1",  // Only localhost access
        "MCP_PORT": "8080"
      }
    }
  }
}
```

### 3. Access Control

- Only trusted AI agents should have MCP access
- Use separate API keys for different agents
- Monitor logs for unusual activity

---

## 🧪 Testing Your Integration

### Test Connection

```bash
# Test MCP server
python test_connection.py
```

Expected output:
```
✅ Connected successfully!
✅ Found 3 project(s)
✅ ALL TESTS PASSED
```

### Test with AI Agent

Ask your AI agent:
```
"List my EasyPanel projects"
```

If configured correctly, you should see your projects listed.

---

## 🆘 Troubleshooting

### Agent Doesn't See MCP Tools

**Solution:**
1. Restart the AI agent application
2. Verify MCP config file syntax (JSON)
3. Check that EasyPanel MCP is running

### Connection Refused

**Solution:**
1. Ensure EasyPanel MCP is running
2. Check `EASYPANEL_URL` is correct
3. Verify API key is valid
4. Test with `python test_connection.py`

### Tools Not Available

**Solution:**
1. Check MCP server logs for errors
2. Verify tRPC connection to EasyPanel
3. Ensure EasyPanel is accessible

---

## 📚 Additional Resources

- **[Installation Guide](../getting-started/installation.md)** - Setup EasyPanel MCP
- **[Configuration Guide](../getting-started/configuration.md)** - Configuration options
- **[Tools Reference](../tools/overview.md)** - Available tools
- **[MCP Specification](https://modelcontextprotocol.io/)** - Official MCP docs

---

<p align="center" markdown>
**🤖 Ready to deploy with AI?** Choose your agent and start managing infrastructure with natural language!
</p>
