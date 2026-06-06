<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

# Kubernetes Platform Engineer MCP Server - Copilot Instructions

## Project Overview
This is a comprehensive Model Context Protocol (MCP) server designed for Kubernetes platform engineering, cluster troubleshooting, monitoring, and advanced system administration. The server features **continuous learning capabilities** that automatically monitor 17+ major Kubernetes repositories and grow the knowledge base every hour.

## Key Technologies
- **MCP (Model Context Protocol)** - For AI assistant integration with VS Code Copilot
- **Python 3.11+** - Core server implementation with AsyncIO
- **Kubernetes Client Library** - For live cluster operations and diagnostics
- **Docker** - Fully containerized deployment with comprehensive tooling
- **SQLite + AsyncIO** - Local database for GitHub issues and knowledge base
- **GitHub API Integration** - Continuous monitoring and learning system
- **Prometheus & Grafana** - Monitoring and observability (optional)

## Architecture Components

### Core Managers
- **KubernetesManager** (`src/k8s_manager.py`) - Cluster operations and management
- **DiagnosticsManager** (`src/diagnostics_manager.py`) - Troubleshooting and health checks
- **MonitoringManager** (`src/monitoring_manager.py`) - Performance analysis and observability
- **SecurityManager** (`src/security_manager.py`) - Security scanning and compliance
- **DocumentationManager** (`src/documentation_manager.py`) - Live Kubernetes docs integration
- **GitHubIssuesManager** (`src/github_issues_manager.py`) - **NEW: Continuous learning engine**

### Configuration & Setup
- **ServerConfig** (`src/config.py`) - Centralized configuration management
- **Automated Setup** (`start.sh`) - One-command installation with VS Code integration
- **Management Scripts** - Complete operational toolkit (start, stop, status, logs, update)
- **Environment Variables** - Runtime configuration via `.env` files

## Development Guidelines

### Code Style
- Follow **PEP 8** Python style guidelines
- Use **type hints** for all function parameters and return values
- Implement **comprehensive error handling** with try/catch blocks
- Use **async/await** for all I/O operations
- Include **docstrings** for all classes and methods

### Continuous Learning System
- **Background Updates** - GitHub issues manager runs hourly update loops
- **Database Management** - Automatic cleanup of outdated issues (>1 year)
- **Rate Limiting** - Graceful handling of GitHub API limits
- **Pattern Recognition** - AI-powered categorization of issues by severity and component
- **Performance Optimization** - Indexed database with semantic search capabilities

### Setup & Installation
- **One-Command Setup** - Use `./start.sh` for complete automated installation
- **VS Code Integration** - Automatic detection and configuration of MCP settings
- **Cross-Platform Support** - Works on macOS, Linux, and Windows
- **Management Scripts** - Generated operational tools for all common tasks
- **Health Monitoring** - Docker-based health checks and status reporting

### Kubernetes Integration
- Always check for **kubeconfig** availability before operations
- Implement **proper RBAC** checks for cluster operations
- Use **namespaced operations** when possible for security
- Handle **API server timeouts** and connection errors gracefully
- **Live Cluster Access** - Dynamic kubeconfig mounting and context switching

### MCP Protocol Implementation
- Follow **MCP specification** for tool definitions
- Provide **comprehensive input schemas** for all tools
- Return **structured JSON responses** with proper error handling
- Include **meaningful descriptions** for all tools and parameters

### Security Considerations
- **Never expose sensitive data** in logs or responses
- **Validate all inputs** before processing
- **Use least privilege** principle for cluster access
- **Audit all operations** for security compliance

### Testing Strategy
- Write **unit tests** for all manager classes
- Include **integration tests** for MCP tool operations
- Test **error scenarios** and edge cases
- Validate **Kubernetes API interactions** with mocks

### Performance Optimization
- Use **async operations** for concurrent API calls
- Implement **connection pooling** for Kubernetes clients
- **Cache frequently accessed data** with appropriate TTL
- **Limit resource usage** for large cluster operations

## Troubleshooting Common Issues

### Setup Issues
```bash
# Setup script permission errors
chmod +x start.sh

# VS Code configuration issues
# Check settings backup and restart VS Code completely
ls -la "$HOME/Library/Application Support/Code/User/settings.json.backup.*"

# Container health issues
./status.sh
./logs.sh | tail -20
```

### Continuous Learning Issues
```bash
# GitHub API rate limiting
export GITHUB_TOKEN="your_github_token"
./start.sh

# Knowledge base not updating
./logs.sh | grep -i "github\|background\|update"
docker exec k8s-mcp-server ps aux | grep python
```

### Container Issues
```bash
# Volume mount problems (use absolute paths)
KUBE_MOUNT="-v $HOME/.kube/config:/root/.kube/config:ro"

# Health check failures (use Docker status, not HTTP)
docker ps | grep k8s-mcp-server
docker inspect k8s-mcp-server | grep '"Status"'
```

### Kubernetes Connectivity
```python
# Always check cluster connectivity first
try:
    await k8s_client.list_node()
except Exception as e:
    logger.error(f"Cluster connectivity failed: {e}")
```

### MCP Tool Responses
```python
# Structure responses consistently
return {
    "status": "success|error",
    "data": {...},
    "timestamp": datetime.utcnow().isoformat(),
    "metadata": {...}
}
```

### Error Handling
```python
# Comprehensive error handling pattern
try:
    result = await perform_operation()
    return {"status": "success", "data": result}
except KubernetesAPIError as e:
    logger.error(f"K8s API error: {e}")
    return {"status": "error", "error": "cluster_api_error", "message": str(e)}
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    return {"status": "error", "error": "internal_error", "message": "Internal server error"}
```

## Best Practices

### For AI Assistant Integration
- Provide **clear, actionable responses** that can be easily understood by users
- Include **step-by-step remediation instructions** where applicable
- **Prioritize issues** by severity and impact
- **Suggest follow-up actions** based on findings

### For Kubernetes Operations
- **Batch API calls** when possible to reduce latency
- **Use field selectors** to limit data retrieval
- **Implement proper pagination** for large result sets
- **Monitor API rate limits** and implement backoff strategies

### For Container Deployment
- **Use multi-stage builds** to minimize image size
- **Run as non-root user** for security
- **Include health checks** for container orchestration
- **Mount kubeconfig securely** with read-only access

## Useful Resources
- MCP Documentation: https://modelcontextprotocol.io/llms-full.txt
- Kubernetes Python Client: https://github.com/kubernetes-client/python
- Kubernetes API Reference: https://kubernetes.io/docs/reference/kubernetes-api/

## Quick Development Commands
```bash
# Setup and Management
./start.sh              # Complete automated setup with VS Code integration
./stop.sh               # Stop the MCP server
./status.sh             # Check server status and health
./logs.sh               # View real-time logs
./update.sh             # Update and restart server

# Development
pytest tests/ -v        # Run tests
black src/              # Format code
mypy src/               # Type checking

# Docker Operations
docker build -t k8s-platform-engineer-mcp .  # Build image
docker logs k8s-mcp-server -f                # Follow logs
docker exec -it k8s-mcp-server /bin/bash     # Enter container

# Container Status
docker ps | grep k8s-mcp-server              # Check if running
docker inspect k8s-mcp-server | grep Health # Check health status
```

## Continuous Learning Features

### Monitored Repositories (17+)
- `kubernetes/kubernetes` - Core platform issues
- `kubernetes/kubectl` - CLI tooling problems  
- `helm/helm` - Package management issues
- `istio/istio` - Service mesh challenges
- `prometheus/prometheus` - Monitoring problems
- `cilium/cilium` + `projectcalico/calico` - Networking solutions
- And 10+ more major Kubernetes ecosystem projects

### Learning Metrics
```bash
# Check knowledge base growth
# /stats endpoint does not exist. Server is stdio-only; no HTTP port is opened.

# Monitor background learning
./logs.sh | grep -i "background\|github\|fetching"

# Database status
docker exec k8s-mcp-server ls -la /app/data/
```
