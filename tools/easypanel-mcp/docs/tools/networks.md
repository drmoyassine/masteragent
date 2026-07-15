---
title: Networks Tools - EasyPanel MCP
description: Guide to EasyPanel MCP networks tools for creating internal isolated networks and managing Docker networking.
keywords: EasyPanel networks, Docker networking, internal networks, isolated networks, overlay networks, MCP tools
---

# 🌐 Networks Tools

Manage Docker networks including internal isolated networks for secure service communication.

---

## Overview

Networks tools allow you to:

- **List** all networks
- **Create** new networks (public or internal)
- **Delete** networks

---

## 🔒 Internal vs Public Networks

### Internal Networks (Isolated)

Internal networks have **no internet access** and are only accessible by services within the same network.

**Use Cases:**
- Database services
- Cache services (Redis, Memcached)
- Internal APIs
- Message queues

### Public Networks

Public networks have internet access and can be exposed externally.

**Use Cases:**
- Web applications
- API gateways
- Reverse proxies

---

## 🔧 Available Tools

### 1. `list_networks`

List all networks.

**Natural Language Examples:**
```
"Show me all networks"
"List available networks"
"What networks exist?"
```

**MCP Call:**
```json
{
  "name": "list_networks",
  "arguments": {}
}
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "net_abc123",
      "name": "public-net",
      "driver": "overlay",
      "internal": false,
      "scope": "swarm",
      "createdAt": "2026-03-14T10:00:00Z"
    },
    {
      "id": "net_def456",
      "name": "database-net",
      "driver": "overlay",
      "internal": true,
      "scope": "swarm",
      "createdAt": "2026-03-14T10:05:00Z"
    }
  ],
  "message": "Found 2 networks"
}
```

---

### 2. `create_network`

Create a new network.

**Natural Language Examples:**
```
"Create an internal network for my database"
"Create a public network for my web services"
"Set up an isolated network for backend services"
```

**MCP Call:**
```json
{
  "name": "create_network",
  "arguments": {
    "name": "database-net",
    "internal": true,
    "driver": "overlay"
  }
}
```

**Parameters:**
- `name` (required): Network name
- `internal` (optional): Isolated network (default: false)
- `driver` (optional): Network driver (default: "overlay")

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "net_new789",
    "name": "database-net",
    "driver": "overlay",
    "internal": true,
    "scope": "swarm",
    "createdAt": "2026-03-14T11:00:00Z"
  },
  "message": "Network 'database-net' created as internal (isolated) network"
}
```

---

### 3. `delete_network`

Delete a network.

⚠️ **Warning:** Ensure no services are using the network!

**Natural Language Examples:**
```
"Delete the old test network"
"Remove the unused network"
"Clean up net_abc123"
```

**MCP Call:**
```json
{
  "name": "delete_network",
  "arguments": {
    "network_id": "net_abc123"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "net_abc123",
    "deleted": true
  },
  "message": "Network net_abc123 deleted successfully"
}
```

---

## 🎯 Common Workflows

### Workflow 1: Create Isolated Database Network

```json
// 1. Create internal network
{
  "name": "create_network",
  "arguments": {
    "name": "db-internal",
    "internal": true,
    "driver": "overlay"
  }
}

// 2. Create database service on internal network
{
  "name": "create_service",
  "arguments": {
    "name": "postgres-db",
    "project_id": "proj_123",
    "image": "postgres:15",
    "config": {
      "networks": ["db-internal"],
      "env": {
        "POSTGRES_PASSWORD": "secure_password"
      }
    }
  }
}

// 3. Create API service with access to internal network
{
  "name": "create_service",
  "arguments": {
    "name": "api-service",
    "project_id": "proj_123",
    "image": "myapp/api:latest",
    "config": {
      "networks": ["db-internal", "public-net"],
      "ports": ["8080:8080"]
    }
  }
}
```

### Workflow 2: Multi-Tier Architecture

```json
// Public tier (internet accessible)
{
  "name": "create_network",
  "arguments": {
    "name": "public-tier",
    "internal": false
  }
}

// Internal tier (application services)
{
  "name": "create_network",
  "arguments": {
    "name": "app-internal",
    "internal": true
  }
}

// Database tier (completely isolated)
{
  "name": "create_network",
  "arguments": {
    "name": "db-tier",
    "internal": true
  }
}
```

---

## 🔒 Security Best Practices

### 1. Isolate Databases

```json
{
  "name": "create_network",
  "arguments": {
    "name": "database-network",
    "internal": true  // ← No internet access
  }
}
```

### 2. Separate Frontend and Backend

```json
// Frontend network (public)
{
  "name": "frontend-net",
  "internal": false
}

// Backend network (internal)
{
  "name": "backend-net",
  "internal": true
}
```

### 3. Microservices Isolation

```json
// Each microservice group has its own internal network
{
  "name": "users-service-net",
  "internal": true
}

{
  "name": "orders-service-net",
  "internal": true
}

{
  "name": "payments-service-net",
  "internal": true
}
```

---

## 📊 Network Architecture Example

```
┌─────────────────────────────────────────┐
│           Internet                      │
└─────────────────┬───────────────────────┘
                  │
         ┌────────▼────────┐
         │  public-net     │
         │  (Frontend)     │
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │  app-internal   │
         │  (Backend API)  │
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │  db-internal    │
         │  (Database)     │
         └─────────────────┘
```

---

## 🆘 Troubleshooting

### Services Can't Communicate

!!! error "Connection refused between services"

    **Solutions:**
    1. Verify services are on the same network
    2. Check network is not internal if internet needed
    3. Ensure service names are used as hostnames

### Network Deletion Fails

!!! error "Network has active endpoints"

    **Solutions:**
    1. List services on the network
    2. Disconnect or remove services
    3. Then delete network

---

## 📚 Related Documentation

- **[Services Tools](services.md)** - Service management
- **[Security Guide](../integration/security.md)** - Security best practices
- **[Examples](../examples/advanced.md)** - Advanced workflows

---

<p align="center" markdown>
**🌐 Master networks!** Continue to [Projects Tools](projects.md)
</p>
