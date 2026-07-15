---
title: Projects Tools - EasyPanel MCP
description: Guide to EasyPanel MCP projects tools for organizing services, deployments, and resources into logical groups.
keywords: EasyPanel projects, resource organization, project management, MCP tools
---

# 📁 Projects Tools

Organize your EasyPanel resources into logical projects.

---

## Overview

Projects tools allow you to:

- **List** all projects
- **Create** new projects
- **Get** project details
- **Delete** projects

---

## 🔧 Available Tools

### 1. `list_projects`

List all projects.

**MCP Call:**
```json
{
  "name": "list_projects",
  "arguments": {}
}
```

---

### 2. `get_project`

Get project details.

**MCP Call:**
```json
{
  "name": "get_project",
  "arguments": {
    "project_id": "proj_abc123"
  }
}
```

---

### 3. `create_project`

Create a new project.

**MCP Call:**
```json
{
  "name": "create_project",
  "arguments": {
    "name": "production-app",
    "description": "Production environment"
  }
}
```

---

### 4. `delete_project`

Delete a project.

⚠️ **Warning:** This deletes all resources in the project!

**MCP Call:**
```json
{
  "name": "delete_project",
  "arguments": {
    "project_id": "proj_abc123"
  }
}
```

---

## 📚 Related Documentation

- **[Services Tools](services.md)** - Service management
- **[Examples](../examples/basic.md)** - Usage examples
