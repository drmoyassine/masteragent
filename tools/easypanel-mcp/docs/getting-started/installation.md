---
title: Installation - EasyPanel MCP
description: Step-by-step installation guide for EasyPanel MCP server on Windows, macOS, and Linux.
keywords: EasyPanel MCP installation, MCP server setup, Python MCP, Docker AI integration
---

# 📦 Installation Guide

This guide covers installing EasyPanel MCP on all supported platforms.

---

## ✅ Prerequisites

Before you begin, ensure you have:

- **Python 3.10 or higher** ([Download Python](https://www.python.org/downloads/))
- **EasyPanel instance** (self-hosted or cloud)
- **EasyPanel API Key** (generate from your panel settings)
- **Git** (optional, for cloning the repository)

---

## 🔧 Installation Steps

### Step 1: Clone the Repository

<div class="tabs" markdown>

<div class="tab" markdown>
**Windows**
```bash
git clone https://github.com/dannymaaz/easypanel-mcp
cd easypanel-mcp
```
</div>

<div class="tab" markdown>
**macOS/Linux**
```bash
git clone https://github.com/dannymaaz/easypanel-mcp
cd easypanel-mcp
```
</div>

</div>

!!! tip "Alternative: Download ZIP"
    If you don't have Git installed, you can [download the ZIP file](https://github.com/dannymaaz/easypanel-mcp/archive/refs/heads/main.zip) and extract it.

---

### Step 2: Create Virtual Environment

Creating a virtual environment is **highly recommended** to avoid dependency conflicts.

<div class="tabs" markdown>

<div class="tab" markdown>
**Windows (PowerShell)**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```
</div>

<div class="tab" markdown>
**Windows (CMD)**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```
</div>

<div class="tab" markdown>
**macOS/Linux**
```bash
python3 -m venv venv
source venv/bin/activate
```
</div>

</div>

!!! success "Verification"
    You should see `(venv)` in your terminal prompt, indicating the virtual environment is active.

---

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `httpx` - Async HTTP client for EasyPanel API
- `python-dotenv` - Environment variable management
- `aiohttp` - Async web server for HTTP mode
- `typing-extensions` - Type hints support

---

### Step 4: Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env
```

Now edit the `.env` file with your settings:

```bash
# EasyPanel Configuration
EASYPANEL_URL=https://your-easypanel.com
EASYPANEL_API_KEY=your_api_key_here
EASYPANEL_TIMEOUT=30
EASYPANEL_VERIFY_SSL=true

# MCP Server Configuration
MCP_HOST=127.0.0.1
MCP_PORT=8080
MCP_LOG_LEVEL=INFO
MCP_DEBUG=false
```

!!! warning "Important"
    - **Never commit your `.env` file** to version control
    - Keep your API key secure and rotate it periodically
    - Use `EASYPANEL_VERIFY_SSL=false` only for local development with self-signed certificates

---

### Step 5: Verify Installation

Test that everything is working:

```bash
python -c "from config import config; print('Configuration loaded successfully!')"
```

If you see no errors, you're ready to go! 🎉

---

## 🚀 Running the Server

### Standard Mode (stdio)

For Claude Desktop and other stdio-based clients:

```bash
python src/server.py
```

### HTTP Mode

For n8n, webhooks, and HTTP-based clients:

```bash
python src/server.py http
```

The server will start on `http://127.0.0.1:8080` by default.

---

## 🔍 Troubleshooting

### Python Version Error

!!! error "Error: Python 3.10+ required"

    **Solution:** Upgrade your Python installation:
    
    - Download from [python.org](https://www.python.org/downloads/)
    - Or use version manager: `pyenv install 3.10`

### Module Not Found

!!! error "ModuleNotFoundError: No module named 'httpx'"

    **Solution:** Reinstall dependencies:
    
    ```bash
    pip install -r requirements.txt --force-reinstall
    ```

### Port Already in Use

!!! error "OSError: [Errno 48] Address already in use"

    **Solution:** Change the port in `.env`:
    
    ```bash
    MCP_PORT=8081  # Use any available port
    ```

### EasyPanel Connection Failed

!!! error "Connection refused"

    **Solution:** 
    1. Verify `EASYPANEL_URL` is correct
    2. Check your API key is valid
    3. Ensure EasyPanel is running and accessible
    4. For local development, use `http://localhost:3000`

---

## 📦 Alternative Installation Methods

### Using pip (Development Mode)

```bash
pip install -e .
```

This installs the package in editable mode, allowing you to modify the source code.

### Using Docker (Coming Soon)

```bash
docker run -d \
  -p 8080:8080 \
  -e EASYPANEL_URL=https://your-easypanel.com \
  -e EASYPANEL_API_KEY=your_key \
  dannymaaz/easypanel-mcp:latest
```

---

## ✅ Next Steps

Now that you have EasyPanel MCP installed:

1. **[Configuration Guide](configuration.md)** - Learn about all configuration options
2. **[Quick Start](quickstart.md)** - Deploy your first service with AI
3. **[Tools Reference](../tools/overview.md)** - Explore all available tools

---

## 🆘 Need Help?

- Check the [FAQ](../faq.md)
- Read [Troubleshooting](../troubleshooting.md)
- Open an issue on [GitHub](https://github.com/dannymaaz/easypanel-mcp/issues)

---

<p align="center" markdown>
**🚀 Ready to deploy with AI?** Continue to [Configuration Guide](configuration.md)
</p>
