---
title: FAQ - EasyPanel MCP
description: Frequently asked questions about EasyPanel MCP, installation, configuration, security, and usage.
keywords: EasyPanel FAQ, MCP questions, troubleshooting, common issues, AI deployment
---

# ❓ Frequently Asked Questions

Common questions about EasyPanel MCP.

---

## 📖 General Questions

### What is EasyPanel MCP?

EasyPanel MCP is a **Model Context Protocol (MCP) server** that allows AI agents (Claude, GPT, etc.) to interact with EasyPanel for infrastructure management using natural language.

### Is EasyPanel MCP free?

Yes! EasyPanel MCP is **100% free** and open-source under the MIT License.

### What AI agents are supported?

EasyPanel MCP works with:
- **Claude Desktop** (via MCP protocol)
- **n8n** (via HTTP)
- **GitHub Actions** (via HTTP)
- **Any MCP-compatible client**
- **Custom HTTP clients**

### Do I need EasyPanel cloud or can I self-host?

Both work! EasyPanel MCP supports:
- **EasyPanel Cloud** (panel.easypanel.io)
- **Self-hosted EasyPanel** (your own VPS)

---

## 🔧 Installation

### What Python version is required?

Python **3.10 or higher** is required.

### Does it work on Windows?

Yes! EasyPanel MCP is **cross-platform**:
- ✅ Windows
- ✅ macOS
- ✅ Linux

### Can I run it in Docker?

Docker support is coming soon. Currently, run directly with Python.

---

## 🔒 Security

### Is my API key secure?

Yes! Best practices:
- Never commit `.env` to Git
- Use secrets management in production
- Rotate API keys periodically
- Use HTTPS for EasyPanel connections

### Can I use self-signed certificates?

Yes, set in `.env`:
```bash
EASYPANEL_VERIFY_SSL=false
```

⚠️ Only for development, not production!

### What permissions does the API key need?

The API key needs full EasyPanel access for:
- Service management
- Deployment creation
- Network configuration
- Project management

---

## 💬 Usage

### How do I connect Claude Desktop?

Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "easypanel": {
      "command": "python",
      "args": ["/path/to/server.py"],
      "env": {
        "EASYPANEL_URL": "https://your-panel.com",
        "EASYPANEL_API_KEY": "your_key"
      }
    }
  }
}
```

See [Claude Desktop Guide](integration/claude-desktop.md).

### Can I use natural language?

Yes! Examples:
```
"Deploy my Flask API with PostgreSQL"
"Scale the worker service to 5 replicas"
"Show me the logs from the API"
"Create an isolated network for my database"
```

### What if I make a mistake?

You can:
- **Update** services with `update_service`
- **Restart** with `restart_service`
- **Delete** with `delete_service`
- **Rollback** deployments

---

## 🌐 Networking

### What are internal networks?

Internal networks are **isolated** Docker networks with no internet access. Perfect for:
- Databases
- Cache services
- Internal APIs

### How do I isolate my database?

```
"Create an internal network for my database"
```

The AI will create a network with `internal: true`.

---

## 🆘 Troubleshooting

### Server won't start

Check:
1. Python 3.10+ installed
2. Dependencies installed: `pip install -r requirements.txt`
3. `.env` file configured correctly
4. Port 8080 not in use

### Claude can't connect

Check:
1. Absolute path in config
2. Python path is correct
3. Server starts manually
4. Restart Claude Desktop

### EasyPanel connection fails

Check:
1. URL is correct (include https://)
2. API key is valid
3. EasyPanel is running
4. Network connectivity

---

## 📊 Performance

### How fast are deployments?

Typical deployment times:
- **Simple service**: 10-30 seconds
- **Multi-service stack**: 30-60 seconds
- **With database**: 1-2 minutes

### Can I scale to many services?

Yes! EasyPanel MCP handles:
- Hundreds of services
- Multiple projects
- Concurrent operations

---

## 🔗 Integration

### Can I use it with n8n?

Yes! Start in HTTP mode:
```bash
python src/server.py http
```

See [n8n Guide](integration/n8n.md).

### Does it work with GitHub Actions?

Yes! Use curl in workflows:
```yaml
curl -X POST http://mcp-server/mcp -d '{...}'
```

See [GitHub Actions Guide](integration/github-actions.md).

---

## 💙 Support

### How can I contribute?

Contributions welcome!
- Fork the repository
- Create feature branch
- Submit pull request
- Report issues

### How can I support the project?

- ⭐ Star on GitHub
- 💙 [Donate via PayPal](https://www.paypal.me/Creativegt)
- 📢 Share with others
- 🐛 Report bugs

### Who created EasyPanel MCP?

**Danny Maaz** - [LinkedIn](https://linkedin.com/in/dannymaaz) | [GitHub](https://github.com/dannymaaz)

---

## 📚 More Resources

- **[Installation Guide](getting-started/installation.md)**
- **[Tools Reference](tools/overview.md)**
- **[Examples](examples/basic.md)**
- **[Troubleshooting](troubleshooting.md)**

---

<p align="center" markdown>
**Still have questions?** Open an issue on [GitHub](https://github.com/dannymaaz/easypanel-mcp/issues)
</p>
