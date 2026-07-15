---
title: Troubleshooting - EasyPanel MCP
description: Troubleshooting guide for EasyPanel MCP covering common issues, errors, and solutions.
keywords: EasyPanel troubleshooting, MCP errors, debug guide, common issues, connection problems
---

# 🔧 Troubleshooting Guide

Solve common EasyPanel MCP issues.

---

## 🔍 Diagnostic Steps

### 1. Check Server Status

```bash
# Test configuration
python -c "from config import config; print(config.easypanel.base_url)"

# Test EasyPanel connection
python -c "
import asyncio
from src.client import EasyPanelClient
from config import config

async def test():
    client = EasyPanelClient(config.easypanel)
    await client.connect()
    healthy = await client.health_check()
    print(f'EasyPanel healthy: {healthy}')
    await client.disconnect()

asyncio.run(test())
"
```

### 2. Check Logs

Run server with debug logging:
```bash
MCP_LOG_LEVEL=DEBUG python src/server.py
```

---

## ❌ Common Errors

### Connection Refused

!!! error "ConnectionRefusedError: [Errno 111] Connection refused"

**Cause:** EasyPanel not reachable

**Solutions:**
1. Verify EasyPanel is running
2. Check URL includes protocol: `https://`
3. Test connectivity: `curl https://your-easypanel.com`
4. Check firewall rules

---

### Unauthorized

!!! error "HTTP 401 Unauthorized"

**Cause:** Invalid API key

**Solutions:**
1. Regenerate API key in EasyPanel
2. Update `.env` with new key
3. Check for typos in key
4. Ensure no extra spaces

---

### Timeout

!!! error "TimeoutError" or "ReadTimeout"

**Cause:** Request taking too long

**Solutions:**
1. Increase timeout in `.env`:
   ```bash
   EASYPANEL_TIMEOUT=120
   ```
2. Check network latency
3. Verify EasyPanel performance
4. Reduce request complexity

---

### Port in Use

!!! error "OSError: [Errno 48] Address already in use"

**Cause:** Port 8080 already bound

**Solutions:**
1. Change port in `.env`:
   ```bash
   MCP_PORT=8081
   ```
2. Find process using port:
   ```bash
   # Windows
   netstat -ano | findstr :8080
   
   # macOS/Linux
   lsof -i :8080
   ```
3. Kill conflicting process

---

### Module Not Found

!!! error "ModuleNotFoundError: No module named 'httpx'"

**Cause:** Dependencies not installed

**Solutions:**
1. Activate virtual environment
2. Reinstall dependencies:
   ```bash
   pip install -r requirements.txt --force-reinstall
   ```
3. Verify installation:
   ```bash
   python -c "import httpx; print(httpx.__version__)"
   ```

---

### Python Version Error

!!! error "SyntaxError" or "TypeError"

**Cause:** Python version < 3.10

**Solutions:**
1. Check version: `python --version`
2. Upgrade Python to 3.10+
3. Use version manager (pyenv, nvm)

---

## 🤖 AI Agent Issues

### Claude Can't Connect

!!! error "MCP server not available"

**Solutions:**
1. Verify absolute path in config
2. Test server manually first
3. Check Python path in config
4. Restart Claude Desktop
5. Check Claude logs

**Config example:**
```json
{
  "mcpServers": {
    "easypanel": {
      "command": "/usr/bin/python3",
      "args": ["/absolute/path/to/server.py"],
      "env": {
        "EASYPANEL_URL": "https://panel.com",
        "EASYPANEL_API_KEY": "key"
      }
    }
  }
}
```

---

### n8n Connection Fails

!!! error "ECONNREFUSED"

**Solutions:**
1. Start MCP in HTTP mode: `python src/server.py http`
2. Check n8n can reach MCP server
3. Use correct URL in HTTP Request node
4. Check firewall between n8n and MCP

---

### GitHub Actions Fails

!!! error "HTTP request failed"

**Solutions:**
1. Ensure MCP server is publicly accessible
2. Verify secrets are set correctly
3. Test curl command locally
4. Check GitHub Actions logs

---

## 🌐 Network Issues

### Services Can't Communicate

!!! error "Connection timeout between services"

**Solutions:**
1. Verify services on same network
2. Check service names used as hostnames
3. Test network connectivity:
   ```bash
   docker network ls
   docker network inspect network-name
   ```
4. Ensure internal networks are truly isolated

---

### Can't Access Service

!!! error "Service not reachable from internet"

**Solutions:**
1. Check ports are mapped: `"ports": ["8080:8080"]`
2. Verify service is running
3. Check firewall rules
4. Test locally: `curl http://localhost:8080`

---

## 🐛 Debug Mode

### Enable Verbose Logging

```bash
# In .env
MCP_DEBUG=true
MCP_LOG_LEVEL=DEBUG
```

### View Server Logs

```bash
# Run and save logs
python src/server.py 2>&1 | tee mcp.log
```

### Debug EasyPanel API

```python
# Test API directly
import httpx
import asyncio

async def debug():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://your-easypanel.com/api/health",
            headers={"Authorization": "Bearer YOUR_KEY"}
        )
        print(f"Status: {response.status_code}")
        print(f"Body: {response.json()}")

asyncio.run(debug())
```

---

## 📊 Performance Issues

### Slow Deployments

**Causes:**
- Network latency
- EasyPanel overloaded
- Large Docker images

**Solutions:**
1. Increase timeout
2. Optimize Docker images (smaller)
3. Check EasyPanel resources
4. Use local Docker registry

---

### High Memory Usage

**Solutions:**
1. Set resource limits:
   ```json
   "resources": {
     "memory": "512M"
   }
   ```
2. Monitor with `get_service`
3. Scale down unused services

---

## 🆘 Getting Help

### 1. Check Documentation

- [FAQ](faq.md)
- [Installation Guide](getting-started/installation.md)
- [Tools Reference](tools/overview.md)

### 2. Enable Debug Mode

```bash
MCP_DEBUG=true python src/server.py
```

### 3. Gather Information

Collect:
- Error messages (full text)
- Server logs
- Configuration (without secrets)
- Steps to reproduce

### 4. Open GitHub Issue

Visit: [github.com/dannymaaz/easypanel-mcp/issues](https://github.com/dannymaaz/easypanel-mcp/issues)

Include:
- Description of issue
- Error messages
- Configuration
- Expected behavior
- Actual behavior

---

## ✅ Health Check Checklist

Run through this checklist when debugging:

- [ ] Python 3.10+ installed
- [ ] Virtual environment activated
- [ ] Dependencies installed
- [ ] `.env` file exists and configured
- [ ] EasyPanel URL accessible
- [ ] API key valid
- [ ] Server starts without errors
- [ ] AI agent can connect
- [ ] Can list services
- [ ] Can create test service

---

<p align="center" markdown>
**Still stuck?** Open an issue on [GitHub](https://github.com/dannymaaz/easypanel-mcp/issues)
</p>
