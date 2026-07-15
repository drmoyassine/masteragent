---
title: n8n Integration - EasyPanel MCP
description: Integrate EasyPanel MCP with n8n workflows for automated infrastructure management and deployment pipelines.
keywords: n8n EasyPanel, workflow automation, deployment automation, CI/CD, infrastructure orchestration
---

# ⚡ n8n Integration

Automate infrastructure management with n8n workflows and EasyPanel MCP.

---

## Overview

Integrate EasyPanel MCP with n8n to create automated workflows for:
- Auto-deployment on Git push
- Scheduled scaling
- Monitoring and alerting
- Multi-step deployment pipelines

---

## 📋 Prerequisites

- **n8n** instance (self-hosted or cloud)
- **EasyPanel MCP** running in HTTP mode
- **EasyPanel API Key**

---

## 🔧 Setup Steps

### Step 1: Start MCP in HTTP Mode

```bash
python src/server.py http
```

Server will start on `http://127.0.0.1:8080`

---

### Step 2: Create n8n HTTP Request Node

Add an **HTTP Request** node to your workflow:

**Basic Configuration:**
```json
{
  "method": "POST",
  "url": "http://localhost:8080/mcp",
  "sendBody": true,
  "bodyParameters": {
    "parameters": [
      {
        "name": "method",
        "value": "tools/call"
      },
      {
        "name": "params.name",
        "value": "list_services"
      }
    ]
  }
}
```

---

## 🎯 Example Workflows

### Workflow 1: Auto-Deploy on Git Push

Trigger deployment when code is pushed to GitHub.

**Workflow JSON:**
```json
{
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "webhook/deploy",
        "responseMode": "lastNode"
      },
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://localhost:8080/mcp",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "{\n  \"method\": \"tools/call\",\n  \"params\": {\n    \"name\": \"create_deployment\",\n    \"arguments\": {\n      \"project_id\": \"{{ $json.body.project_id }}\",\n      \"service_id\": \"{{ $json.body.service_id }}\",\n      \"image\": \"{{ $json.body.image }}\"\n    }\n  }\n}"
      },
      "name": "EasyPanel Deploy",
      "type": "n8n-nodes-base.httpRequest"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "={{ $json.body.webhook_url }}",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "{\n  \"text\": \"✅ Deployment completed: {{ $json.result.content[0].text }}\"\n}"
      },
      "name": "Notify Slack",
      "type": "n8n-nodes-base.httpRequest"
    }
  ],
  "connections": {
    "Webhook": {
      "main": [
        [
          {
            "node": "EasyPanel Deploy",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "EasyPanel Deploy": {
      "main": [
        [
          {
            "node": "Notify Slack",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  }
}
```

---

### Workflow 2: Scheduled Scaling

Scale services based on schedule.

**Workflow:**
```json
{
  "nodes": [
    {
      "parameters": {
        "rule": {
          "interval": [
            {
              "field": "hours",
              "hoursInterval": 1
            }
          ]
        }
      },
      "name": "Schedule Trigger",
      "type": "n8n-nodes-base.scheduleTrigger"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://localhost:8080/mcp",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "{\n  \"method\": \"tools/call\",\n  \"params\": {\n    \"name\": \"list_services\"\n  }\n}"
      },
      "name": "Get Services",
      "type": "n8n-nodes-base.httpRequest"
    },
    {
      "parameters": {
        "conditions": {
          "string": [
            {
              "value1": "{{ $json.name }}",
              "value2": "worker",
              "operation": "equals"
            }
          ]
        }
      },
      "name": "Filter Worker",
      "type": "n8n-nodes-base.if"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://localhost:8080/mcp",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "{\n  \"method\": \"tools/call\",\n  \"params\": {\n    \"name\": \"update_service\",\n    \"arguments\": {\n      \"service_id\": \"{{ $json.id }}\",\n      \"config\": {\n        \"replicas\": 5\n      }\n    }\n  }\n}"
      },
      "name": "Scale Up",
      "type": "n8n-nodes-base.httpRequest"
    }
  ]
}
```

---

### Workflow 3: Health Check & Auto-Recovery

Monitor services and auto-recover failed ones.

**Workflow:**
```json
{
  "nodes": [
    {
      "parameters": {
        "method": "POST",
        "url": "http://localhost:8080/mcp",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "{\n  \"method\": \"tools/call\",\n  \"params\": {\n    \"name\": \"list_services\"\n  }\n}"
      },
      "name": "List Services",
      "type": "n8n-nodes-base.httpRequest"
    },
    {
      "parameters": {
        "conditions": {
          "string": [
            {
              "value1": "{{ $json.status }}",
              "value2": "crashed",
              "operation": "equals"
            }
          ]
        }
      },
      "name": "Check Status",
      "type": "n8n-nodes-base.if"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://localhost:8080/mcp",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "{\n  \"method\": \"tools/call\",\n  \"params\": {\n    \"name\": \"restart_service\",\n    \"arguments\": {\n      \"service_id\": \"{{ $json.id }}\"\n    }\n  }\n}"
      },
      "name": "Restart Service",
      "type": "n8n-nodes-base.httpRequest"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "{\n  \"text\": \"🚨 Service {{ $json.name }} crashed and was automatically restarted\"\n}"
      },
      "name": "Alert Slack",
      "type": "n8n-nodes-base.httpRequest"
    }
  ]
}
```

---

## 🔧 HTTP Request Node Template

Use this template for any EasyPanel MCP tool:

```json
{
  "method": "POST",
  "url": "http://localhost:8080/mcp",
  "sendBody": true,
  "specifyBody": "json",
  "jsonBody": "{\n  \"method\": \"tools/call\",\n  \"params\": {\n    \"name\": \"TOOL_NAME\",\n    \"arguments\": {\n      \"PARAM_NAME\": \"PARAM_VALUE\"\n    }\n  }\n}"
}
```

Replace:
- `TOOL_NAME` with the tool name (e.g., `create_service`)
- `PARAM_NAME` and `PARAM_VALUE` with actual parameters

---

## 📊 Common Tools in n8n

### List Services

```json
{
  "method": "tools/call",
  "params": {
    "name": "list_services",
    "arguments": {}
  }
}
```

### Create Service

```json
{
  "method": "tools/call",
  "params": {
    "name": "create_service",
    "arguments": {
      "name": "my-service",
      "project_id": "proj_123",
      "image": "nginx:latest"
    }
  }
}
```

### Get Logs

```json
{
  "method": "tools/call",
  "params": {
    "name": "get_service_logs",
    "arguments": {
      "service_id": "svc_abc",
      "lines": 100
    }
  }
}
```

---

## 🔗 Integration Examples

### GitHub + n8n + EasyPanel

```
GitHub Webhook
     ↓
n8n Workflow
     ↓
EasyPanel MCP
     ↓
Deploy Service
```

### Monitoring + n8n + EasyPanel

```
Prometheus Alert
     ↓
n8n Workflow
     ↓
EasyPanel MCP
     ↓
Scale Service
```

### Schedule + n8n + EasyPanel

```
Cron Schedule
     ↓
n8n Workflow
     ↓
EasyPanel MCP
     ↓
Backup Database
```

---

## 🆘 Troubleshooting

### Connection Refused

!!! error "ECONNREFUSED"

    **Solutions:**
    1. Ensure MCP is running in HTTP mode
    2. Check correct port (default: 8080)
    3. Verify firewall allows connection

### Timeout

!!! error "Request timeout"

    **Solutions:**
    1. Increase timeout in n8n HTTP node
    2. Check EasyPanel is responsive
    3. Increase `EASYPANEL_TIMEOUT` in MCP config

### Invalid Response

!!! error "Unexpected response format"

    **Solutions:**
    1. Verify JSON body format
    2. Check tool name is correct
    3. Ensure all required parameters provided

---

## 📚 Related Documentation

- **[Claude Desktop](claude-desktop.md)** - AI assistant integration
- **[GitHub Actions](github-actions.md)** - CI/CD pipelines
- **[Tools Reference](../tools/overview.md)** - All available tools

---

<p align="center" markdown>
**⚡ n8n connected!** Build your first automation workflow.
</p>
