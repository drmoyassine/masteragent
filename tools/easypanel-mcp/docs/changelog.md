---
title: Changelog - EasyPanel MCP
description: Changelog and release history for EasyPanel MCP.
keywords: EasyPanel changelog, release notes, version history, updates
---

# 📋 Changelog

All notable changes to EasyPanel MCP.

---

## [1.0.0] - 2026-03-14

### 🎉 Initial Release

#### ✨ Features

- **Core MCP Server**
  - Full MCP protocol implementation
  - stdio and HTTP transport modes
  - Async architecture for high performance

- **Services Tools** (7 tools)
  - `list_services` - List all services
  - `get_service` - Get service details
  - `create_service` - Create new services
  - `update_service` - Update configuration
  - `delete_service` - Remove services
  - `restart_service` - Restart running services
  - `get_service_logs` - View service logs

- **Deployments Tools** (4 tools)
  - `list_deployments` - List all deployments
  - `get_deployment` - Get deployment details
  - `create_deployment` - Create new deployment
  - `get_deployment_logs` - View deployment logs

- **Networks Tools** (3 tools)
  - `list_networks` - List all networks
  - `create_network` - Create networks (public or internal)
  - `delete_network` - Delete networks

- **Projects Tools** (4 tools)
  - `list_projects` - List all projects
  - `get_project` - Get project details
  - `create_project` - Create new project
  - `delete_project` - Delete project

#### 🔧 Configuration

- Environment-based configuration
- Support for custom timeouts
- SSL verification options
- Debug mode for troubleshooting

#### 📚 Documentation

- Complete MkDocs documentation
- Minimalist blue-themed design
- SEO optimized
- Integration guides:
  - Claude Desktop
  - n8n workflows
  - GitHub Actions

#### 🧪 Testing

- Comprehensive test suite
- Unit tests for all tools
- Integration test examples
- pytest configuration

#### 🌐 Cross-Platform

- Windows support
- macOS support
- Linux support
- Python 3.10+

---

## 🔮 Planned Features

### Next Releases

- [ ] **v1.1.0** - Enhanced Monitoring
  - Service metrics endpoint
  - Performance monitoring
  - Alert integrations

- [ ] **v1.2.0** - Advanced Deployments
  - Rolling updates
  - Blue-green deployments
  - Canary releases
  - Auto-rollback

- [ ] **v1.3.0** - Extended Tools
  - Volume management
  - Secret management
  - Stack management
  - Backup/restore

- [ ] **v2.0.0** - Enterprise Features
  - Multi-tenant support
  - RBAC (Role-Based Access Control)
  - Audit logging
  - Advanced networking

---

## 📊 Version Compatibility

| EasyPanel MCP | Python | EasyPanel | MCP Protocol |
|---------------|--------|-----------|--------------|
| 1.0.0         | 3.10+  | Any       | 2024-11-05   |

---

## 🐛 Known Issues

None at this time.

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

---

## 📜 License

MIT License - See [LICENSE](https://github.com/dannymaaz/easypanel-mcp/blob/main/LICENSE)

---

<p align="center" markdown>
**Built with ❤️ by Danny Maaz**
</p>
