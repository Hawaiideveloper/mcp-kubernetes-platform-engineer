# 🚀 Getting Started with Kubernetes Platform Engineer MCP

## Quick Start (2 Minutes)

### 1. One-Command Setup
```bash
curl -fsSL https://raw.githubusercontent.com/your-org/mcp-kubernetes-platform-engineer/main/start.sh | bash
```

### 2. Manual Setup (if you prefer)

#### Prerequisites
- Docker installed and running
- VS Code with GitHub Copilot extension
- Internet connection

#### Step 1: Clone and Start
```bash
git clone https://github.com/your-org/mcp-kubernetes-platform-engineer.git
cd mcp-kubernetes-platform-engineer
./start.sh
```

#### Step 2: VS Code Integration
The `start.sh` script will automatically configure VS Code for you, but if you need to do it manually:

1. Open VS Code
2. Go to Settings (Cmd/Ctrl + ,)
3. Search for "copilot"
4. Click "Edit in settings.json"
5. Add this configuration:

```json
{
  "github.copilot.advanced": {
    "debug.overrideEngine": "mcp",
    "debug.testOverrideProxyUrl": "http://localhost:3001"
  },
  "mcp.servers": {
    "kubernetes-platform-engineer": {
      "command": "docker",
      "args": [
        "run", 
        "--rm", 
        "-i", 
        "--name", "k8s-mcp-server",
        "-p", "3001:3000",
        "k8s-platform-engineer-mcp:latest"
      ],
      "env": {
        "MCP_SERVER_NAME": "kubernetes-platform-engineer",
        "MCP_SERVER_VERSION": "1.0.0"
      }
    }
  }
}
```

## ✅ Verification

After setup, verify everything works:

1. **Check Docker Container**:
   ```bash
   docker ps | grep k8s-mcp
   ```

2. **Check MCP Server**:
   ```bash
   curl http://localhost:3001/health
   ```

3. **Test in VS Code**:
   - Open a new file
   - Type: `// How do I troubleshoot a failing pod in Kubernetes?`
   - Press Tab to see Copilot suggestions powered by the MCP server

## 🔧 Configuration Options

### Environment Variables
Set these in your shell or Docker environment:

```bash
# GitHub token for higher API rate limits (optional but recommended)
export GITHUB_TOKEN="your_github_token_here"

# Update interval for GitHub issues (in seconds, default: 3600)
export GITHUB_ISSUES_UPDATE_INTERVAL="1800"

# Log level (DEBUG, INFO, WARNING, ERROR)
export LOG_LEVEL="INFO"

# Custom port (default: 3001)
export MCP_PORT="3001"
```

### Kubernetes Configuration
If you have kubectl configured:

```bash
# Mount your kubeconfig for live cluster access
docker run --rm -it \
  -v ~/.kube/config:/root/.kube/config:ro \
  -p 3001:3000 \
  k8s-platform-engineer-mcp:latest
```

## 🔄 Daily Usage

### Starting the Server
```bash
./start.sh
```

### Stopping the Server
```bash
./stop.sh
```

### Updating to Latest Version
```bash
./update.sh
```

### Viewing Logs
```bash
docker logs k8s-mcp-server -f
```

## 💡 Using with Copilot

Once configured, you can ask Copilot questions like:

- "How do I debug a CrashLoopBackOff pod?"
- "Show me recent Kubernetes security issues"
- "What are common kubectl troubleshooting commands?"
- "Help me write a deployment YAML for nginx"
- "Explain this Kubernetes error: [paste error]"

The MCP server will provide responses based on:
- 45,720+ indexed Kubernetes GitHub issues
- Real-time cluster analysis (if kubectl configured)
- Best practices and security recommendations
- Step-by-step troubleshooting guides

## 🔍 Advanced Features

### Live Issue Monitoring
The server automatically updates its knowledge base every hour by:
- Fetching new GitHub issues from 17+ Kubernetes repositories
- Analyzing issue patterns and solutions
- Building searchable knowledge database
- Tracking trending problems and fixes

### Multi-Cluster Support
```bash
# Add multiple kubeconfig contexts
export KUBECONFIG=~/.kube/config:~/.kube/staging:~/.kube/prod
```

### Custom Repositories
Add your own repositories to monitor:
```bash
export CUSTOM_REPOS="your-org/k8s-configs,your-org/helm-charts"
```

## 🐛 Troubleshooting

### Common Issues

#### 1. Port Already in Use
```bash
# Change port in start.sh or use:
MCP_PORT=3002 ./start.sh
```

#### 2. Docker Permission Denied
```bash
# Add your user to docker group
sudo usermod -aG docker $USER
# Then logout and login again
```

#### 3. VS Code Not Recognizing MCP
```bash
# Restart VS Code after configuration
# Check VS Code Developer Tools (Help > Toggle Developer Tools)
# Look for MCP connection messages
```

#### 4. GitHub Rate Limiting
```bash
# Set GitHub token for higher limits
export GITHUB_TOKEN="your_token"
./start.sh
```

### Getting Help

1. **Check Logs**: `docker logs k8s-mcp-server`
2. **Check Health**: `curl http://localhost:3001/health`
3. **Issue Tracker**: Create an issue on GitHub
4. **Discord**: Join our community discord server

## 🔄 Staying Updated

The MCP server automatically:
- ✅ Updates GitHub issues every hour
- ✅ Cleans up old data to stay performant  
- ✅ Adapts to new Kubernetes versions and patterns
- ✅ Learns from community solutions

Your knowledge base grows automatically as the Kubernetes ecosystem evolves!

## 📊 Monitoring & Analytics

View your MCP server stats:
```bash
curl http://localhost:3001/stats | jq
```

This shows:
- Total issues indexed
- Recent issue trends
- Most common problem categories
- Knowledge base health metrics

---

**🎉 You're Ready!** Your Kubernetes Platform Engineer MCP is now running and continuously learning from the community.
