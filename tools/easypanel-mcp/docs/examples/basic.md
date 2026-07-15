---
title: Basic Examples - EasyPanel MCP
description: Basic examples for EasyPanel MCP showing common usage patterns for services, deployments, and networks.
keywords: EasyPanel examples, MCP usage, service deployment, Docker examples, AI deployment
---

# 💡 Basic Examples

Common usage examples for EasyPanel MCP.

---

## 📦 Deploy a Single Service

### NGINX Web Server

**Natural Language:**
```
"Deploy an NGINX web server on port 80"
```

**MCP Call:**
```json
{
  "name": "create_service",
  "arguments": {
    "name": "web-server",
    "project_id": "proj_123",
    "image": "nginx:latest",
    "config": {
      "ports": ["80:80"]
    }
  }
}
```

---

### PostgreSQL Database

**Natural Language:**
```
"Create a PostgreSQL database with password authentication"
```

**MCP Call:**
```json
{
  "name": "create_service",
  "arguments": {
    "name": "postgres-db",
    "project_id": "proj_123",
    "image": "postgres:15",
    "config": {
      "env": {
        "POSTGRES_USER": "admin",
        "POSTGRES_PASSWORD": "secure_password",
        "POSTGRES_DB": "myapp"
      },
      "volumes": ["postgres-data:/var/lib/postgresql/data"]
    }
  }
}
```

---

### Redis Cache

**Natural Language:**
```
"Set up a Redis cache service"
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
      "ports": ["6379:6379"]
    }
  }
}
```

---

## 🌐 Create Networks

### Internal Database Network

**Natural Language:**
```
"Create an isolated network for my database services"
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

---

### Public Application Network

**Natural Language:**
```
"Create a public network for my web services"
```

**MCP Call:**
```json
{
  "name": "create_network",
  "arguments": {
    "name": "public-net",
    "internal": false
  }
}
```

---

## 📁 Manage Projects

### Create New Project

**Natural Language:**
```
"Create a new project for my production environment"
```

**MCP Call:**
```json
{
  "name": "create_project",
  "arguments": {
    "name": "production",
    "description": "Production environment for all services"
  }
}
```

---

### List All Projects

**Natural Language:**
```
"Show me all my projects"
```

**MCP Call:**
```json
{
  "name": "list_projects",
  "arguments": {}
}
```

---

## 🔍 Service Management

### List Services

**Natural Language:**
```
"List all services in the production project"
```

**MCP Call:**
```json
{
  "name": "list_services",
  "arguments": {
    "project_id": "proj_production"
  }
}
```

---

### Get Service Details

**Natural Language:**
```
"Show me the configuration of the API service"
```

**MCP Call:**
```json
{
  "name": "get_service",
  "arguments": {
    "service_id": "svc_api_123"
  }
}
```

---

### View Logs

**Natural Language:**
```
"Show me the last 100 logs from the worker service"
```

**MCP Call:**
```json
{
  "name": "get_service_logs",
  "arguments": {
    "service_id": "svc_worker",
    "lines": 100
  }
}
```

---

### Restart Service

**Natural Language:**
```
"Restart the API service"
```

**MCP Call:**
```json
{
  "name": "restart_service",
  "arguments": {
    "service_id": "svc_api"
  }
}
```

---

### Scale Service

**Natural Language:**
```
"Scale the worker service to 5 replicas"
```

**MCP Call:**
```json
{
  "name": "update_service",
  "arguments": {
    "service_id": "svc_worker",
    "config": {
      "replicas": 5
    }
  }
}
```

---

### Delete Service

**Natural Language:**
```
"Delete the old test service"
```

**MCP Call:**
```json
{
  "name": "delete_service",
  "arguments": {
    "service_id": "svc_test_old"
  }
}
```

---

## 🚀 Deployments

### Create Deployment

**Natural Language:**
```
"Deploy version 2.0 of my application"
```

**MCP Call:**
```json
{
  "name": "create_deployment",
  "arguments": {
    "project_id": "proj_123",
    "service_id": "svc_app",
    "image": "myapp:v2.0.0"
  }
}
```

---

### List Deployments

**Natural Language:**
```
"Show me the deployment history"
```

**MCP Call:**
```json
{
  "name": "list_deployments",
  "arguments": {
    "project_id": "proj_123"
  }
}
```

---

## 🎯 Complete Workflows

### Full Stack Application

**Natural Language:**
```
"Deploy my full stack app with React frontend, Node.js backend, 
PostgreSQL database, and Redis cache. Use isolated networking for 
the database and cache."
```

**What AI will do:**
```json
// 1. Create project
{
  "name": "create_project",
  "arguments": {
    "name": "fullstack-app",
    "description": "Full stack application"
  }
}

// 2. Create internal network
{
  "name": "create_network",
  "arguments": {
    "name": "app-internal",
    "internal": true
  }
}

// 3. Deploy PostgreSQL
{
  "name": "create_service",
  "arguments": {
    "name": "postgres-db",
    "project_id": "proj_new",
    "image": "postgres:15",
    "config": {
      "networks": ["app-internal"],
      "env": {
        "POSTGRES_PASSWORD": "secret"
      }
    }
  }
}

// 4. Deploy Redis
{
  "name": "create_service",
  "arguments": {
    "name": "redis-cache",
    "project_id": "proj_new",
    "image": "redis:7-alpine",
    "config": {
      "networks": ["app-internal"]
    }
  }
}

// 5. Deploy Node.js Backend
{
  "name": "create_service",
  "arguments": {
    "name": "nodejs-backend",
    "project_id": "proj_new",
    "image": "myapp/backend:latest",
    "config": {
      "networks": ["app-internal", "public-net"],
      "ports": ["3000:3000"],
      "env": {
        "DATABASE_URL": "postgres://postgres:secret@postgres-db:5432/app",
        "REDIS_URL": "redis://redis-cache:6379"
      }
    }
  }
}

// 6. Deploy React Frontend
{
  "name": "create_service",
  "arguments": {
    "name": "react-frontend",
    "project_id": "proj_new",
    "image": "myapp/frontend:latest",
    "config": {
      "networks": ["public-net"],
      "ports": ["80:80"]
    }
  }
}
```

---

### Microservices Architecture

**Natural Language:**
```
"Set up a microservices architecture with API gateway, 
user service, and order service"
```

**What AI will do:**
```json
// 1. Create API Gateway
{
  "name": "create_service",
  "arguments": {
    "name": "api-gateway",
    "project_id": "proj_micro",
    "image": "kong:latest",
    "config": {
      "ports": ["8000:8000"],
      "networks": ["public-net", "internal-net"]
    }
  }
}

// 2. Create User Service
{
  "name": "create_service",
  "arguments": {
    "name": "user-service",
    "project_id": "proj_micro",
    "image": "myapp/user-service:latest",
    "config": {
      "networks": ["internal-net"],
      "env": {
        "DATABASE_URL": "postgres://users-db:5432/users"
      }
    }
  }
}

// 3. Create Order Service
{
  "name": "create_service",
  "arguments": {
    "name": "order-service",
    "project_id": "proj_micro",
    "image": "myapp/order-service:latest",
    "config": {
      "networks": ["internal-net"],
      "env": {
        "DATABASE_URL": "postgres://orders-db:5432/orders"
      }
    }
  }
}
```

---

## 📚 Related Documentation

- **[Tools Reference](../tools/overview.md)** - All available tools
- **[Advanced Examples](advanced.md)** - Complex workflows
- **[Real-World Cases](real-world.md)** - Production examples

---

<p align="center" markdown>
**💡 Ready for more?** Check out [Advanced Examples](advanced.md)
</p>
