---
title: Services Tools - EasyPanel MCP
description: Complete guide to EasyPanel MCP services tools for managing Docker containers, viewing logs, and service lifecycle.
keywords: EasyPanel services, Docker service management, container lifecycle, service logs, MCP tools
---

# 📦 Services Tools

Complete guide to managing Docker services with EasyPanel MCP.

---

## Overview

Services tools allow you to manage the complete lifecycle of Docker containers in EasyPanel:

- **Create** new services from Docker images
- **Update** service configuration
- **Delete** services
- **Restart** running services
- **View logs** for debugging
- **List** all services

---

## 🔧 Available Tools

### 1. `list_services`

List all services in EasyPanel.

**Natural Language Examples:**
```
"Show me all my services"
"List services in the production project"
"What services are currently running?"
```

**MCP Call:**
```json
{
  "name": "list_services",
  "arguments": {
    "project_id": "proj_123"  // Optional filter
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "svc_abc",
      "name": "api-service",
      "image": "nginx:latest",
      "status": "running",
      "projectId": "proj_123"
    }
  ],
  "message": "Found 1 services"
}
```

---

### 2. `get_service`

Get detailed information about a specific service.

**Natural Language Examples:**
```
"Show me details for api-service"
"What's the status of postgres-db?"
"Inspect service svc_abc"
```

**MCP Call:**
```json
{
  "name": "get_service",
  "arguments": {
    "service_id": "svc_abc"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "svc_abc",
    "name": "api-service",
    "image": "nginx:latest",
    "status": "running",
    "state": "started",
    "resources": {
      "cpu": 2,
      "memory": 4096
    },
    "ports": [
      {"public": 80, "private": 8080}
    ]
  },
  "message": "Service svc_abc retrieved"
}
```

---

### 3. `create_service`

Create a new service from a Docker image.

**Natural Language Examples:**
```
"Deploy nginx in my project"
"Create a PostgreSQL database service"
"Set up a Redis cache"
```

**MCP Call:**
```json
{
  "name": "create_service",
  "arguments": {
    "name": "my-api",
    "project_id": "proj_123",
    "image": "node:18-alpine",
    "config": {
      "ports": ["3000:3000"],
      "env": {"NODE_ENV": "production"}
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {...},
  "message": "Service 'my-api' created successfully"
}
```

---

### 4. `update_service`

Update service configuration (env vars, resources, ports, etc.).

**Natural Language Examples:**
```
"Update the environment variables for api-service"
"Increase memory for worker to 8GB"
"Change the Docker image to v2.0.0"
```

**MCP Call:**
```json
{
  "name": "update_service",
  "arguments": {
    "service_id": "svc_abc",
    "config": {
      "env": {"NEW_VAR": "value"},
      "resources": {"memory": 8192}
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {...},
  "message": "Service svc_abc updated successfully"
}
```

---

### 5. `delete_service`

Delete a service.

**Natural Language Examples:**
```
"Delete the old-api service"
"Remove svc_abc"
```

**MCP Call:**
```json
{
  "name": "delete_service",
  "arguments": {
    "service_id": "svc_abc"
  }
}
```

---

### 6. `restart_service`

Restart a running service.

**Natural Language Examples:**
```
"Restart api-service"
"Apply new configuration to worker"
```

**MCP Call:**
```json
{
  "name": "restart_service",
  "arguments": {
    "service_id": "svc_abc"
  }
}
```

---

### 7. `start_service`

Start a stopped service.

**Natural Language Examples:**
```
"Start the database service"
"Bring postgres-db back online"
```

**MCP Call:**
```json
{
  "name": "start_service",
  "arguments": {
    "service_id": "svc_abc"
  }
}
```

---

### 8. `stop_service`

Stop a running service.

**Natural Language Examples:**
```
"Stop api-service for maintenance"
"Shutdown the worker temporarily"
```

**MCP Call:**
```json
{
  "name": "stop_service",
  "arguments": {
    "service_id": "svc_abc"
  }
}
```

---

### 9. `deploy_service`

Deploy or redeploy a service (apply changes).

**Natural Language Examples:**
```
"Deploy the new version of api-service"
"Redeploy with updated configuration"
```

**MCP Call:**
```json
{
  "name": "deploy_service",
  "arguments": {
    "service_id": "svc_abc"
  }
}
```

---

### 10. `get_service_logs`

Get intelligent service logs (inferred from service state).

**Natural Language Examples:**
```
"Show me logs for api-service"
"Why is worker failing?"
"Debug the database service"
```

**MCP Call:**
```json
{
  "name": "get_service_logs",
  "arguments": {
    "service_id": "svc_abc",
    "lines": 100  // Optional, default 100
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": [
    "📊 Service: api-service",
    "📦 Status: running",
    "🔄 State: started",
    "📅 Created: 2026-03-14T10:00:00Z",
    "🕐 Updated: 2026-03-14T12:30:00Z",
    "🚀 Deployment: success",
    "💻 CPU: 2 cores",
    "🧠 Memory: 4096 MB"
  ],
  "message": "Retrieved 8 log lines for service svc_abc"
}
```

**Note:** Logs are intelligently inferred from service inspection since EasyPanel doesn't expose raw logs via tRPC.
{
  "success": true,
  "data": [
    {
      "id": "svc_abc123",
      "name": "api-service",
      "image": "nginx:latest",
      "status": "running",
      "projectId": "proj_123",
      "createdAt": "2026-03-14T10:00:00Z",
      "updatedAt": "2026-03-14T10:30:00Z"
    },
    {
      "id": "svc_def456",
      "name": "postgres-db",
      "image": "postgres:15",
      "status": "running",
      "projectId": "proj_123",
      "createdAt": "2026-03-14T09:00:00Z"
    }
  ],
  "message": "Found 2 services"
}
```

---

### 2. `get_service`

Get detailed information about a specific service.

**Natural Language Examples:**
```
"Show me details for the API service"
"What's the configuration of postgres-db?"
"Get service svc_abc123"
```

**MCP Call:**
```json
{
  "name": "get_service",
  "arguments": {
    "service_id": "svc_abc123"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "svc_abc123",
    "name": "api-service",
    "image": "nginx:latest",
    "status": "running",
    "projectId": "proj_123",
    "config": {
      "ports": ["80:80", "443:443"],
      "env": {
        "NODE_ENV": "production"
      },
      "replicas": 3,
      "networks": ["public-net", "internal-net"]
    },
    "resources": {
      "cpu": "0.5",
      "memory": "512M"
    },
    "health": {
      "status": "healthy",
      "checks": 10,
      "failures": 0
    }
  },
  "message": "Service svc_abc123 retrieved"
}
```

---

### 3. `create_service`

Create a new service.

**Natural Language Examples:**
```
"Create a new Redis service"
"Deploy nginx as a reverse proxy"
"Create a PostgreSQL database service"
"Set up a Node.js API service"
```

**MCP Call:**
```json
{
  "name": "create_service",
  "arguments": {
    "name": "redis-cache",
    "project_id": "proj_123",
    "image": "redis:7-alpine",
    "config": {
      "ports": ["6379:6379"],
      "env": {
        "REDIS_PASSWORD": "secure_password"
      },
      "volumes": ["redis-data:/data"],
      "networks": ["internal-net"],
      "resources": {
        "cpu": "0.25",
        "memory": "256M"
      }
    }
  }
}
```

**Common Configuration Options:**

```json
{
  "ports": ["host:container"],
  "env": {"KEY": "value"},
  "volumes": ["volume-name:/path"],
  "networks": ["network-name"],
  "replicas": 3,
  "resources": {
    "cpu": "0.5",
    "memory": "512M"
  },
  "healthcheck": {
    "test": "curl -f http://localhost/health",
    "interval": "30s",
    "timeout": "10s",
    "retries": 3
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "svc_new123",
    "name": "redis-cache",
    "image": "redis:7-alpine",
    "status": "creating",
    "projectId": "proj_123"
  },
  "message": "Service 'redis-cache' created successfully"
}
```

---

### 4. `update_service`

Update service configuration.

**Natural Language Examples:**
```
"Scale the API service to 5 replicas"
"Update the environment variables"
"Change the resource limits"
```

**MCP Call:**
```json
{
  "name": "update_service",
  "arguments": {
    "service_id": "svc_abc123",
    "config": {
      "replicas": 5,
      "env": {
        "NEW_VAR": "new_value"
      },
      "resources": {
        "cpu": "1.0",
        "memory": "1024M"
      }
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "svc_abc123",
    "name": "api-service",
    "status": "updating"
  },
  "message": "Service svc_abc123 updated successfully"
}
```

---

### 5. `delete_service`

Delete a service.

⚠️ **Warning:** This action is irreversible!

**Natural Language Examples:**
```
"Delete the test service"
"Remove the old API service"
"Clean up svc_abc123"
```

**MCP Call:**
```json
{
  "name": "delete_service",
  "arguments": {
    "service_id": "svc_abc123"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "svc_abc123",
    "deleted": true
  },
  "message": "Service svc_abc123 deleted successfully"
}
```

---

### 6. `restart_service`

Restart a running service.

**Natural Language Examples:**
```
"Restart the API service"
"Reboot the database service"
"Restart svc_abc123"
```

**MCP Call:**
```json
{
  "name": "restart_service",
  "arguments": {
    "service_id": "svc_abc123"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "svc_abc123",
    "status": "restarting"
  },
  "message": "Service svc_abc123 restarted successfully"
}
```

---

### 7. `get_service_logs`

Get logs from a service.

**Natural Language Examples:**
```
"Show me the logs from the API service"
"What errors are in the worker logs?"
"Get the last 200 lines from postgres"
```

**MCP Call:**
```json
{
  "name": "get_service_logs",
  "arguments": {
    "service_id": "svc_abc123",
    "lines": 100  // Optional, default: 100
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": [
    "2026-03-14T10:30:00Z INFO Starting application...",
    "2026-03-14T10:30:01Z INFO Connected to database",
    "2026-03-14T10:30:02Z INFO Server listening on port 8080",
    "2026-03-14T10:30:05Z ERROR Connection timeout to external API",
    "2026-03-14T10:30:06Z WARN Retrying connection (1/3)"
  ],
  "message": "Retrieved 5 log lines for service svc_abc123"
}
```

---

## 🎯 Common Workflows

### Workflow 1: Deploy a Complete Service

```json
// 1. Create service
{
  "name": "create_service",
  "arguments": {
    "name": "my-api",
    "project_id": "proj_123",
    "image": "myapp/api:v1.0.0",
    "config": {
      "ports": ["8080:8080"],
      "env": {
        "DATABASE_URL": "postgres://user:pass@db:5432/app",
        "NODE_ENV": "production"
      },
      "replicas": 3
    }
  }
}

// 2. Verify creation
{
  "name": "get_service",
  "arguments": {
    "service_id": "svc_new123"
  }
}

// 3. Check logs
{
  "name": "get_service_logs",
  "arguments": {
    "service_id": "svc_new123",
    "lines": 50
  }
}
```

### Workflow 2: Debug a Service

```json
// 1. Get service details
{
  "name": "get_service",
  "arguments": {
    "service_id": "svc_problem"
  }
}

// 2. Check logs for errors
{
  "name": "get_service_logs",
  "arguments": {
    "service_id": "svc_problem",
    "lines": 200
  }
}

// 3. Restart if needed
{
  "name": "restart_service",
  "arguments": {
    "service_id": "svc_problem"
  }
}

// 4. Verify it's running
{
  "name": "get_service",
  "arguments": {
    "service_id": "svc_problem"
  }
}
```

### Workflow 3: Scale a Service

```json
// 1. Check current state
{
  "name": "get_service",
  "arguments": {
    "service_id": "svc_api"
  }
}

// 2. Update replicas
{
  "name": "update_service",
  "arguments": {
    "service_id": "svc_api",
    "config": {
      "replicas": 10
    }
  }
}

// 3. Verify scaling
{
  "name": "get_service",
  "arguments": {
    "service_id": "svc_api"
  }
}
```

---

## 📊 Service Configuration Reference

### Ports

```json
"ports": [
  "80:80",      // HTTP
  "443:443",    // HTTPS
  "8080:8080"   // Custom
]
```

### Environment Variables

```json
"env": {
  "NODE_ENV": "production",
  "DATABASE_URL": "postgres://user:pass@host:5432/db",
  "REDIS_HOST": "redis",
  "API_KEY": "secret_key"
}
```

### Volumes

```json
"volumes": [
  "data-volume:/app/data",
  "logs-volume:/app/logs",
  "./config:/app/config:ro"  // Read-only
]
```

### Networks

```json
"networks": [
  "public-net",     // Internet accessible
  "internal-net"    // Isolated internal network
]
```

### Resources

```json
"resources": {
  "cpu": "0.5",        // CPU cores
  "memory": "512M"     // Memory limit
}
```

### Health Check

```json
"healthcheck": {
  "test": "curl -f http://localhost/health || exit 1",
  "interval": "30s",
  "timeout": "10s",
  "retries": 3,
  "start_period": "40s"
}
```

---

## 🆘 Troubleshooting

### Service Won't Start

!!! error "Service stuck in 'creating' state"

    **Solutions:**
    1. Check logs: `get_service_logs`
    2. Verify image exists
    3. Check resource availability
    4. Validate configuration

### Service Crashes Repeatedly

!!! error "Service keeps restarting"

    **Solutions:**
    1. Get logs to identify error
    2. Check environment variables
    3. Verify network connectivity
    4. Check resource limits

### Can't Access Service

!!! error "Service not reachable"

    **Solutions:**
    1. Verify ports are mapped correctly
    2. Check network configuration
    3. Ensure service is running
    4. Check firewall rules

---

## 📚 Related Documentation

- **[Deployments Tools](deployments.md)** - Manage deployments
- **[Networks Tools](networks.md)** - Configure networking
- **[Examples](../examples/basic.md)** - Usage examples

---

<p align="center" markdown>
**📦 Master services!** Continue to [Deployments Tools](deployments.md)
</p>
