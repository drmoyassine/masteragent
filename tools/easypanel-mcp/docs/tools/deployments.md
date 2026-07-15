---
title: Deployments Tools - EasyPanel MCP
description: Guide to EasyPanel MCP deployments tools for managing application versions, rolling updates, and deployment history.
keywords: EasyPanel deployments, version management, rolling updates, deployment history, MCP tools
---

# 🚀 Deployments Tools

Manage application deployments and versions with EasyPanel MCP.

---

## Overview

Deployments tools allow you to:

- **List** all deployments
- **Create** new deployments
- **Get** deployment details
- **View** deployment logs

---

## 🔧 Available Tools

### 1. `list_deployments`

List all deployments.

**MCP Call:**
```json
{
  "name": "list_deployments",
  "arguments": {
    "project_id": "proj_123"  // Optional
  }
}
```

---

### 2. `get_deployment`

Get deployment details.

**MCP Call:**
```json
{
  "name": "get_deployment",
  "arguments": {
    "deployment_id": "deploy_abc123"
  }
}
```

---

### 3. `create_deployment`

Create a new deployment.

**MCP Call:**
```json
{
  "name": "create_deployment",
  "arguments": {
    "project_id": "proj_123",
    "service_id": "svc_abc",
    "image": "myapp:v2.0.0",
    "config": {
      "strategy": "rolling",
      "rollback_on_failure": true
    }
  }
}
```

---

### 4. `get_deployment_logs`

Get deployment logs.

**MCP Call:**
```json
{
  "name": "get_deployment_logs",
  "arguments": {
    "deployment_id": "deploy_abc123"
  }
}
```

---

## 🎯 Deployment Strategies

### Rolling Deployment

```json
{
  "strategy": "rolling",
  "max_surge": 1,
  "max_unavailable": 0
}
```

### Blue-Green Deployment

```json
{
  "strategy": "blue-green",
  "switch_traffic": true
}
```

### Canary Deployment

```json
{
  "strategy": "canary",
  "canary_percentage": 10
}
```

---

## 📚 Related Documentation

- **[Services Tools](services.md)** - Service management
- **[Examples](../examples/basic.md)** - Usage examples
