---
title: Configuration - EasyPanel MCP
description: Complete configuration guide for EasyPanel MCP server including environment variables, security settings, and advanced options.
keywords: EasyPanel configuration, MCP settings, environment variables, API configuration, security settings, tRPC
---

# ⚙️ Configuration Guide

This guide covers all configuration options for EasyPanel MCP server.

---

## 📋 Configuration Overview

EasyPanel MCP uses environment variables for configuration. You can set these in a `.env` file or directly in your environment.

**Important:** EasyPanel MCP uses **tRPC protocol** to communicate with EasyPanel API. All operations are performed via tRPC procedures.

---

## 🔑 Required Configuration

### EasyPanel Connection

These settings are **required** to connect to your EasyPanel instance:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `EASYPANEL_URL` | Your EasyPanel URL | `http://localhost:3000` | ✅ Yes |
| `EASYPANEL_API_KEY` | Your API key OR email:password | - | ✅ Yes |

### Authentication Methods

EasyPanel MCP supports **two authentication methods**:

#### Method 1: API Key (Recommended)

Generate an API key from your EasyPanel dashboard:

```bash
EASYPANEL_API_KEY=ep_live_xxxxxxxxxxxxxxxxxxxx
```

**Pros:** More secure, can be rotated easily, no password stored

#### Method 2: Email + Password

Use your EasyPanel credentials:

```bash
EASYPANEL_API_KEY=your@email.com:your_password
```

**Format:** `email:password` (note the colon separator)

**Pros:** No need to generate keys, **Cons:** Password stored in config

### Example `.env` File

```bash
# Required: EasyPanel Configuration
EASYPANEL_URL=https://your-easypanel.com

# Method 1: API Key (recommended)
EASYPANEL_API_KEY=ep_live_abc123def456

# OR Method 2: Email + Password
# EASYPANEL_API_KEY=your@email.com:your_password
```

---

## 🔧 Optional Configuration

### EasyPanel Advanced Settings

| Variable | Description | Default | Type |
|----------|-------------|---------|------|
| `EASYPANEL_TIMEOUT` | Request timeout in seconds | `30` | Integer |
| `EASYPANEL_VERIFY_SSL` | Verify SSL certificates | `true` | Boolean |

### MCP Server Settings

| Variable | Description | Default | Type |
|----------|-------------|---------|------|
| `MCP_HOST` | Server bind address | `127.0.0.1` | String |
| `MCP_PORT` | Server port | `8080` | Integer |
| `MCP_LOG_LEVEL` | Logging level | `INFO` | String |
| `MCP_DEBUG` | Enable debug mode | `false` | Boolean |

---

## 📝 Complete Configuration Example

```bash
# ============================================
# EasyPanel Configuration
# ============================================

# Your EasyPanel instance URL
# Use http://localhost:3000 for local development
EASYPANEL_URL=https://panel.yourdomain.com

# API Key from EasyPanel (Settings → API Keys)
EASYPANEL_API_KEY=ep_live_abc123def456ghi789

# Request timeout (increase for slow networks)
EASYPANEL_TIMEOUT=60

# SSL verification (set to false for self-signed certs)
EASYPANEL_VERIFY_SSL=true

# ============================================
# MCP Server Configuration
# ============================================

# Network interface to bind to
# Use 0.0.0.0 to allow external connections
MCP_HOST=127.0.0.1

# Port for HTTP mode
MCP_PORT=8080

# Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
MCP_LOG_LEVEL=INFO

# Enable debug mode (verbose logging)
MCP_DEBUG=false
```

---

## 🔒 Security Best Practices

### 1. Protect Your API Key

!!! warning "Never expose your API key"
    - Never commit `.env` to version control
    - Use secrets management in production
    - Rotate keys periodically

### 2. Network Security

For production deployments:

```bash
# Bind to localhost only (recommended)
MCP_HOST=127.0.0.1

# Use a non-standard port
MCP_PORT=8787
```

### 3. SSL/TLS Configuration

For HTTPS connections to EasyPanel:

```bash
# Enable SSL verification (production)
EASYPANEL_VERIFY_SSL=true

# For self-signed certificates (development only)
EASYPANEL_VERIFY_SSL=false
```

### 4. Logging in Production

```bash
# Use WARNING or ERROR level in production
MCP_LOG_LEVEL=WARNING

# Disable debug mode
MCP_DEBUG=false
```

---

## 🌐 Network Configuration

### Local Development

```bash
# Local EasyPanel instance
EASYPANEL_URL=http://localhost:3000
EASYPANEL_VERIFY_SSL=false

# MCP on default port
MCP_HOST=127.0.0.1
MCP_PORT=8080
```

### Remote EasyPanel (Cloud)

```bash
# Cloud EasyPanel instance
EASYPANEL_URL=https://your-panel.easypanel.io
EASYPANEL_VERIFY_SSL=true

# Secure MCP configuration
MCP_HOST=127.0.0.1
MCP_PORT=8080
```

### Docker Network

```bash
# EasyPanel in Docker network
EASYPANEL_URL=http://easypanel:3000
EASYPANEL_VERIFY_SSL=false

# MCP accessible from other containers
MCP_HOST=0.0.0.0
MCP_PORT=8080
```

---

## 📊 Logging Configuration

### Log Levels Explained

| Level | Description | When to Use |
|-------|-------------|-------------|
| `DEBUG` | All debug information | Development, troubleshooting |
| `INFO` | General information | Default, development |
| `WARNING` | Warnings and errors | Staging |
| `ERROR` | Errors only | Production |
| `CRITICAL` | Critical errors only | Production (minimal logging) |

### Example Log Output

```
2026-03-14 10:30:15 - easypanel.client - INFO - Connected to EasyPanel at https://panel.example.com
2026-03-14 10:30:20 - easypanel.server - INFO - Starting MCP server with HTTP transport
2026-03-14 10:30:20 - easypanel.server - INFO - Server running on 127.0.0.1:8080
```

---

## 🔧 Advanced Configuration

### Timeout Tuning

For large deployments or slow networks:

```bash
# Increase timeout for slow operations
EASYPANEL_TIMEOUT=120
```

### Custom SSL Certificates

```bash
# Use custom CA bundle
# (Set via environment or code)
REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt
```

### Multiple Instances

Run multiple MCP servers on different ports:

```bash
# Instance 1 (.env)
MCP_PORT=8080

# Instance 2 (.env.prod)
MCP_PORT=8081
```

---

## 🧪 Testing Configuration

### Verify Configuration

```bash
# Test configuration loading
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

### Configuration Validation

The server validates configuration on startup:

```
✅ EASYPANEL_URL is set
✅ EASYPANEL_API_KEY is set
✅ EASYPANEL_TIMEOUT is valid integer
✅ MCP_PORT is available
```

---

## 🐳 Docker Environment Variables

When running in Docker:

```yaml
# docker-compose.yml
services:
  easypanel-mcp:
    image: dannymaaz/easypanel-mcp:latest
    environment:
      - EASYPANEL_URL=https://panel.example.com
      - EASYPANEL_API_KEY=ep_live_xxx
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8080
    ports:
      - "8080:8080"
```

---

## 🆘 Troubleshooting

### Configuration Not Loading

!!! error "Configuration values are default"

    **Solution:** Ensure `.env` file is in the correct directory:
    
    ```bash
    # Check current directory
    pwd
    
    # Verify .env exists
    ls -la .env
    ```

### Invalid Environment Variable

!!! error "ValueError: invalid literal for int()"

    **Solution:** Check that numeric values are integers:
    
    ```bash
    # Correct
    EASYPANEL_TIMEOUT=30
    
    # Incorrect (quotes)
    EASYPANEL_TIMEOUT="30"
    ```

### Port Conflicts

!!! error "Address already in use"

    **Solution:** Change the port:
    
    ```bash
    MCP_PORT=8081
    ```

---

## ✅ Configuration Checklist

Before running in production:

- [ ] `EASYPANEL_URL` points to correct instance
- [ ] `EASYPANEL_API_KEY` is valid and secure
- [ ] `EASYPANEL_VERIFY_SSL=true` for production
- [ ] `MCP_HOST=127.0.0.1` (unless external access needed)
- [ ] `MCP_LOG_LEVEL` set appropriately
- [ ] `MCP_DEBUG=false` in production
- [ ] `.env` file is in `.gitignore`
- [ ] Timeout values are appropriate for your use case

---

## 📚 Related Documentation

- **[Installation Guide](installation.md)** - Setup and installation
- **[Quick Start](quickstart.md)** - Get started quickly
- **[Security Guide](../integration/security.md)** - Security best practices

---

<p align="center" markdown>
**⚙️ Configuration complete!** Continue to [Quick Start](quickstart.md)
</p>
