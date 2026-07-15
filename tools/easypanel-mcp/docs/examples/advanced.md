---
title: Advanced Examples - EasyPanel MCP
description: Advanced examples for EasyPanel MCP showing complex workflows, multi-service deployments, and automation patterns.
keywords: EasyPanel advanced examples, complex workflows, multi-service deployment, automation patterns
---

# 🚀 Advanced Examples

Complex workflows and advanced usage patterns.

---

## 🏗️ Multi-Tier Architecture

### 3-Tier Web Application

Deploy a complete 3-tier architecture with load balancer, application servers, and database.

**Natural Language:**
```
"Deploy a 3-tier web application with HAProxy load balancer, 
3 Node.js application servers, and a PostgreSQL database cluster. 
Use isolated networks for each tier."
```

**Implementation:**
```json
// Tier 1: Database Network (Most Isolated)
{
  "name": "create_network",
  "arguments": {
    "name": "db-tier",
    "internal": true,
    "driver": "overlay"
  }
}

// Tier 2: Application Network
{
  "name": "create_network",
  "arguments": {
    "name": "app-tier",
    "internal": true
  }
}

// Tier 3: Public Network
{
  "name": "create_network",
  "arguments": {
    "name": "public-tier",
    "internal": false
  }
}

// Database Service (DB Tier)
{
  "name": "create_service",
  "arguments": {
    "name": "postgres-primary",
    "project_id": "proj_3tier",
    "image": "postgres:15",
    "config": {
      "networks": ["db-tier"],
      "env": {
        "POSTGRES_PASSWORD": "secure_password",
        "POSTGRES_REPLICATION_MODE": "master"
      },
      "volumes": ["postgres-primary-data:/var/lib/postgresql/data"]
    }
  }
}

// Application Servers (App Tier) - 3 Replicas
{
  "name": "create_service",
  "arguments": {
    "name": "nodejs-app",
    "project_id": "proj_3tier",
    "image": "myapp/nodejs:latest",
    "config": {
      "networks": ["app-tier", "db-tier"],
      "replicas": 3,
      "env": {
        "DATABASE_URL": "postgres://postgres:password@postgres-primary:5432/app",
        "NODE_ENV": "production"
      },
      "resources": {
        "cpu": "0.5",
        "memory": "512M"
      }
    }
  }
}

// Load Balancer (Public Tier)
{
  "name": "create_service",
  "arguments": {
    "name": "haproxy-lb",
    "project_id": "proj_3tier",
    "image": "haproxy:latest",
    "config": {
      "networks": ["public-tier", "app-tier"],
      "ports": ["80:80", "443:443"],
      "volumes": ["./haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro"]
    }
  }
}
```

---

## 🔄 Blue-Green Deployment

Deploy a new version with zero downtime.

**Natural Language:**
```
"Deploy version 2.0 using blue-green strategy. Keep version 1.0 
running until 2.0 is healthy, then switch traffic."
```

**Implementation:**
```json
// 1. Deploy Green Environment (v2.0)
{
  "name": "create_service",
  "arguments": {
    "name": "app-green",
    "project_id": "proj_bg",
    "image": "myapp:v2.0.0",
    "config": {
      "ports": ["8081:8080"],
      "env": {
        "VERSION": "2.0.0",
        "DATABASE_URL": "postgres://db:5432/app"
      }
    }
  }
}

// 2. Health Check Green
{
  "name": "get_service",
  "arguments": {
    "service_id": "svc_green"
  }
}

// 3. Switch Load Balancer to Green
{
  "name": "update_service",
  "arguments": {
    "service_id": "svc_loadbalancer",
    "config": {
      "env": {
        "BACKEND_SERVICE": "app-green",
        "BACKEND_PORT": "8081"
      }
    }
  }
}

// 4. Verify Green is Receiving Traffic
// (Monitor logs and metrics)

// 5. Delete Blue Environment (v1.0)
{
  "name": "delete_service",
  "arguments": {
    "service_id": "svc_app_blue"
  }
}
```

---

## 📊 Monitoring Stack

Deploy complete monitoring with Prometheus, Grafana, and Alertmanager.

**Natural Language:**
```
"Set up a complete monitoring stack with Prometheus for metrics, 
Grafana for dashboards, and Alertmanager for alerts."
```

**Implementation:**
```json
// Prometheus
{
  "name": "create_service",
  "arguments": {
    "name": "prometheus",
    "project_id": "proj_monitoring",
    "image": "prom/prometheus:latest",
    "config": {
      "ports": ["9090:9090"],
      "volumes": [
        "prometheus-data:/prometheus",
        "./prometheus.yml:/etc/prometheus/prometheus.yml:ro"
      ]
    }
  }
}

// Grafana
{
  "name": "create_service",
  "arguments": {
    "name": "grafana",
    "project_id": "proj_monitoring",
    "image": "grafana/grafana:latest",
    "config": {
      "ports": ["3000:3000"],
      "volumes": ["grafana-data:/var/lib/grafana"],
      "env": {
        "GF_SECURITY_ADMIN_PASSWORD": "admin_password",
        "GF_INSTALL_PLUGINS": "grafana-clock-panel,grafana-simple-json-datasource"
      }
    }
  }
}

// Alertmanager
{
  "name": "create_service",
  "arguments": {
    "name": "alertmanager",
    "project_id": "proj_monitoring",
    "image": "prom/alertmanager:latest",
    "config": {
      "ports": ["9093:9093"],
      "volumes": [
        "alertmanager-data:/alertmanager",
        "./alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro"
      ]
    }
  }
}

// Node Exporter (for host metrics)
{
  "name": "create_service",
  "arguments": {
    "name": "node-exporter",
    "project_id": "proj_monitoring",
    "image": "prom/node-exporter:latest",
    "config": {
      "ports": ["9100:9100"],
      "pid": "host"
    }
  }
}
```

---

## 🔐 Secure Microservices

Deploy microservices with mutual TLS and service mesh patterns.

**Natural Language:**
```
"Deploy secure microservices with an API gateway, service mesh, 
and mutual TLS authentication between services."
```

**Implementation:**
```json
// API Gateway with Rate Limiting
{
  "name": "create_service",
  "arguments": {
    "name": "api-gateway",
    "project_id": "proj_secure",
    "image": "kong:latest",
    "config": {
      "ports": ["8443:8443"],
      "env": {
        "KONG_DATABASE": "off",
        "KONG_DECLARATIVE_CONFIG": "/kong/declarative/kong.yml",
        "KONG_PROXY_ACCESS_LOG": "/dev/stdout",
        "KONG_ADMIN_ACCESS_LOG": "/dev/stdout"
      },
      "volumes": ["./kong-config:/kong/declarative:ro"]
    }
  }
}

// User Service (Internal Only)
{
  "name": "create_service",
  "arguments": {
    "name": "user-service",
    "project_id": "proj_secure",
    "image": "myapp/user-service:latest",
    "config": {
      "networks": ["internal-mesh"],
      "env": {
        "SERVICE_PORT": "8080",
        "MTLS_ENABLED": "true",
        "CA_CERT_PATH": "/certs/ca.crt"
      },
      "volumes": ["./certs:/certs:ro"]
    }
  }
}

// Auth Service with JWT Validation
{
  "name": "create_service",
  "arguments": {
    "name": "auth-service",
    "project_id": "proj_secure",
    "image": "myapp/auth-service:latest",
    "config": {
      "networks": ["internal-mesh"],
      "env": {
        "JWT_SECRET": "${JWT_SECRET}",
        "TOKEN_EXPIRY": "3600"
      }
    }
  }
}
```

---

## 🗄️ Database Cluster

Deploy PostgreSQL with high availability.

**Natural Language:**
```
"Deploy a PostgreSQL cluster with one primary, two replicas, 
and PgBouncer for connection pooling."
```

**Implementation:**
```json
// Primary Database
{
  "name": "create_service",
  "arguments": {
    "name": "postgres-primary",
    "project_id": "proj_db",
    "image": "postgres:15",
    "config": {
      "networks": ["db-network"],
      "env": {
        "POSTGRES_PASSWORD": "secure_password",
        "POSTGRES_REPLICATION_MODE": "master",
        "POSTGRES_USER": "replicator"
      },
      "volumes": [
        "postgres-primary-data:/var/lib/postgresql/data",
        "./init-primary.sql:/docker-entrypoint-initdb.d/init.sql:ro"
      ]
    }
  }
}

// Replica 1
{
  "name": "create_service",
  "arguments": {
    "name": "postgres-replica-1",
    "project_id": "proj_db",
    "image": "postgres:15",
    "config": {
      "networks": ["db-network"],
      "env": {
        "POSTGRES_PASSWORD": "secure_password",
        "POSTGRES_REPLICATION_MODE": "slave",
        "POSTGRES_MASTER_HOST": "postgres-primary"
      },
      "volumes": ["postgres-replica-1-data:/var/lib/postgresql/data"]
    }
  }
}

// PgBouncer (Connection Pooling)
{
  "name": "create_service",
  "arguments": {
    "name": "pgbouncer",
    "project_id": "proj_db",
    "image": "bitnami/pgbouncer:latest",
    "config": {
      "networks": ["db-network", "app-network"],
      "ports": ["6432:6432"],
      "env": {
        "POSTGRESQL_HOST": "postgres-primary",
        "POSTGRESQL_PORT": "5432",
        "POSTGRESQL_USERNAME": "postgres",
        "POSTGRESQL_PASSWORD": "secure_password",
        "PGBOUNCER_DATABASE": "*",
        "PGBOUNCER_POOL_MODE": "transaction"
      }
    }
  }
}
```

---

## ⚡ Auto-Scaling Pattern

Implement auto-scaling based on metrics.

**Natural Language:**
```
"Set up auto-scaling for the worker service. Scale from 2 to 10 
replicas based on CPU usage above 70%."
```

**Implementation:**
```json
// Initial Deployment
{
  "name": "create_service",
  "arguments": {
    "name": "worker-service",
    "project_id": "proj_autoscale",
    "image": "myapp/worker:latest",
    "config": {
      "replicas": 2,
      "resources": {
        "cpu": "0.5",
        "memory": "512M"
      }
    }
  }
}

// Scaling Logic (via n8n or custom script)
// Check CPU every minute
{
  "name": "get_service",
  "arguments": {
    "service_id": "svc_worker"
  }
}

// If CPU > 70% and replicas < 10, scale up
{
  "name": "update_service",
  "arguments": {
    "service_id": "svc_worker",
    "config": {
      "replicas": 5
    }
  }
}

// If CPU < 30% and replicas > 2, scale down
{
  "name": "update_service",
  "arguments": {
    "service_id": "svc_worker",
    "config": {
      "replicas": 3
    }
  }
}
```

---

## 📚 Related Documentation

- **[Basic Examples](basic.md)** - Simple examples
- **[Real-World Cases](real-world.md)** - Production scenarios
- **[Tools Reference](../tools/overview.md)** - All available tools

---

<p align="center" markdown>
**🚀 Advanced mastery complete!** Check out [Real-World Cases](real-world.md)
</p>
