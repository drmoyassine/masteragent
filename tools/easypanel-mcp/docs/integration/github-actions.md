---
title: GitHub Actions Integration - EasyPanel MCP
description: Automate deployments with GitHub Actions and EasyPanel MCP. CI/CD pipelines for Docker services.
keywords: GitHub Actions EasyPanel, CI/CD pipeline, automated deployment, Docker deployment, continuous integration
---

# 🔄 GitHub Actions Integration

Automate deployments with GitHub Actions and EasyPanel MCP.

---

## Overview

Integrate EasyPanel MCP with GitHub Actions to:
- Auto-deploy on push to main branch
- Deploy pull request previews
- Rollback on failure
- Multi-environment deployments

---

## 📋 Prerequisites

- **GitHub Repository**
- **EasyPanel MCP** running and accessible
- **EasyPanel API Key**

---

## 🔧 Setup Steps

### Step 1: Store Secrets in GitHub

Go to your repository → Settings → Secrets and variables → Actions

Add these secrets:

| Secret | Description | Example |
|--------|-------------|---------|
| `EASYPANEL_URL` | EasyPanel URL | `https://panel.example.com` |
| `EASYPANEL_API_KEY` | API Key | `ep_live_xxx` |
| `EASYPANEL_PROJECT_ID` | Project ID | `proj_123` |
| `EASYPANEL_SERVICE_ID` | Service ID | `svc_456` |

---

### Step 2: Create Deployment Workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to EasyPanel

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Deploy to EasyPanel via MCP
        run: |
          curl -X POST https://your-mcp-server.com/mcp \
            -H "Content-Type: application/json" \
            -d '{
              "method": "tools/call",
              "params": {
                "name": "create_deployment",
                "arguments": {
                  "project_id": "${{ secrets.EASYPANEL_PROJECT_ID }}",
                  "service_id": "${{ secrets.EASYPANEL_SERVICE_ID }}",
                  "image": "myapp:${{ github.sha }}"
                }
              }
            }'
```

---

## 🎯 Example Workflows

### Workflow 1: Simple Deploy on Push

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Build and Push Docker Image
        run: |
          docker build -t myapp:${{ github.sha }} .
          docker tag myapp:${{ github.sha }} registry.example.com/myapp:${{ github.sha }}
          docker push registry.example.com/myapp:${{ github.sha }}
      
      - name: Deploy via EasyPanel MCP
        run: |
          curl -X POST ${{ secrets.EASYPANEL_MCP_URL }}/mcp \
            -H "Content-Type: application/json" \
            -d '{
              "method": "tools/call",
              "params": {
                "name": "create_deployment",
                "arguments": {
                  "project_id": "${{ secrets.EASYPANEL_PROJECT_ID }}",
                  "service_id": "${{ secrets.EASYPANEL_SERVICE_ID }}",
                  "image": "registry.example.com/myapp:${{ github.sha }}"
                }
              }
            }'
```

---

### Workflow 2: Multi-Environment Deployment

```yaml
name: Multi-Environment Deploy

on:
  push:
    branches:
      - main
      - develop
  pull_request:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        environment: [staging, production]
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Determine Image Tag
        id: image
        run: |
          if [ "${{ github.event_name }}" == "pull_request" ]; then
            echo "tag=pr-${{ github.event.pull_request.number }}" >> $GITHUB_OUTPUT
          else
            echo "tag=${{ github.sha }}" >> $GITHUB_OUTPUT
          fi
      
      - name: Deploy to ${{ matrix.environment }}
        run: |
          curl -X POST ${{ secrets.EASYPANEL_MCP_URL }}/mcp \
            -H "Content-Type: application/json" \
            -d '{
              "method": "tools/call",
              "params": {
                "name": "create_deployment",
                "arguments": {
                  "project_id": "${{ secrets[format(\"EASYPANEL_{0}_PROJECT_ID\", matrix.environment)] }}",
                  "service_id": "${{ secrets[format(\"EASYPANEL_{0}_SERVICE_ID\", matrix.environment)] }}",
                  "image": "myapp:${{ steps.image.outputs.tag }}"
                }
              }
            }'
```

---

### Workflow 3: Deploy with Rollback

```yaml
name: Deploy with Auto-Rollback

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Get Current Deployment
        id: current
        run: |
          RESPONSE=$(curl -s -X POST ${{ secrets.EASYPANEL_MCP_URL }}/mcp \
            -H "Content-Type: application/json" \
            -d '{
              "method": "tools/call",
              "params": {
                "name": "list_deployments",
                "arguments": {
                  "project_id": "${{ secrets.EASYPANEL_PROJECT_ID }}"
                }
              }
            }')
          echo "previous=$(echo $RESPONSE | jq -r '.data[0].id')" >> $GITHUB_OUTPUT
      
      - name: Deploy New Version
        id: deploy
        run: |
          curl -X POST ${{ secrets.EASYPANEL_MCP_URL }}/mcp \
            -H "Content-Type: application/json" \
            -d '{
              "method": "tools/call",
              "params": {
                "name": "create_deployment",
                "arguments": {
                  "project_id": "${{ secrets.EASYPANEL_PROJECT_ID }}",
                  "service_id": "${{ secrets.EASYPANEL_SERVICE_ID }}",
                  "image": "myapp:${{ github.sha }}"
                }
              }
            }'
      
      - name: Health Check
        run: |
          sleep 30
          curl -f https://myapp.example.com/health || exit 1
      
      - name: Rollback on Failure
        if: failure()
        run: |
          curl -X POST ${{ secrets.EASYPANEL_MCP_URL }}/mcp \
            -H "Content-Type: application/json" \
            -d '{
              "method": "tools/call",
              "params": {
                "name": "create_deployment",
                "arguments": {
                  "project_id": "${{ secrets.EASYPANEL_PROJECT_ID }}",
                  "service_id": "${{ secrets.EASYPANEL_SERVICE_ID }}",
                  "image": "myapp:${{ steps.previous.outputs.deployment_id }}"
                }
              }
            }'
```

---

### Workflow 4: Pull Request Preview

```yaml
name: PR Preview Deployments

on:
  pull_request:
    branches: [main]

jobs:
  preview:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Deploy Preview
        run: |
          curl -X POST ${{ secrets.EASYPANEL_MCP_URL }}/mcp \
            -H "Content-Type: application/json" \
            -d '{
              "method": "tools/call",
              "params": {
                "name": "create_service",
                "arguments": {
                  "name": "app-pr-${{ github.event.pull_request.number }}",
                  "project_id": "${{ secrets.EASYPANEL_PROJECT_ID }}",
                  "image": "myapp:pr-${{ github.event.pull_request.number }}",
                  "config": {
                    "env": {
                      "PR_NUMBER": "${{ github.event.pull_request.number }}",
                      "PR_URL": "${{ github.event.pull_request.html_url }}"
                    }
                  }
                }
              }
            }'
      
      - name: Comment PR
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `🚀 Preview deployed for PR #${{ github.event.pull_request.number }}`
            })
```

---

## 🔧 MCP Server Setup for GitHub Actions

### Option 1: Self-Hosted MCP Server

Run MCP on a server accessible from internet:

```bash
# Start MCP in HTTP mode
python src/server.py http

# Ensure server is accessible from internet
# Configure firewall and reverse proxy if needed
```

### Option 2: GitHub Actions Runner with MCP

Install MCP on your self-hosted runner:

```yaml
# In your runner setup
- name: Install EasyPanel MCP
  run: |
    git clone https://github.com/dannymaaz/easypanel-mcp
    cd easypanel-mcp
    pip install -r requirements.txt

- name: Start MCP
  run: |
    python src/server.py http &
```

---

## 📊 Complete CI/CD Pipeline

```yaml
name: Complete CI/CD

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Tests
        run: npm test
  
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker Image
        run: docker build -t myapp:${{ github.sha }} .
      - name: Push to Registry
        run: docker push registry.example.com/myapp:${{ github.sha }}
  
  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Deploy to Staging
        run: |
          curl -X POST ${{ secrets.EASYPANEL_MCP_URL }}/mcp \
            -H "Content-Type: application/json" \
            -d '{
              "method": "tools/call",
              "params": {
                "name": "create_deployment",
                "arguments": {
                  "project_id": "${{ secrets.EASYPANEL_STAGING_PROJECT_ID }}",
                  "image": "registry.example.com/myapp:${{ github.sha }}"
                }
              }
            }'
  
  integration-tests:
    needs: deploy-staging
    runs-on: ubuntu-latest
    steps:
      - name: Run Integration Tests
        run: npm run test:integration
  
  deploy-production:
    needs: integration-tests
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy to Production
        run: |
          curl -X POST ${{ secrets.EASYPANEL_MCP_URL }}/mcp \
            -H "Content-Type: application/json" \
            -d '{
              "method": "tools/call",
              "params": {
                "name": "create_deployment",
                "arguments": {
                  "project_id": "${{ secrets.EASYPANEL_PROD_PROJECT_ID }}",
                  "image": "registry.example.com/myapp:${{ github.sha }}"
                }
              }
            }'
```

---

## 🆘 Troubleshooting

### Connection Issues

!!! error "Connection refused"

    **Solutions:**
    1. Ensure MCP server is accessible from internet
    2. Check firewall rules
    3. Verify URL is correct

### Authentication Failed

!!! error "Unauthorized"

    **Solutions:**
    1. Verify API key is correct
    2. Check API key hasn't expired
    3. Regenerate API key if needed

### Deployment Fails

!!! error "Deployment failed"

    **Solutions:**
    1. Check Docker image exists in registry
    2. Verify project and service IDs
    3. Review EasyPanel logs

---

## 📚 Related Documentation

- **[Claude Desktop](claude-desktop.md)** - AI assistant integration
- **[n8n](n8n.md)** - Workflow automation
- **[Tools Reference](../tools/overview.md)** - All available tools

---

<p align="center" markdown>
**🔄 GitHub Actions connected!** Automate your deployments.
</p>
