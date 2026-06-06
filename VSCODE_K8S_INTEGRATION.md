# VS Code Integration with Kubernetes MCP Server

This guide explains how to integrate your Kubernetes-deployed MCP server with VS Code for seamless development experience.

## 🚀 **Two Integration Methods**

### Method 1: NodePort Access (Recommended for Production)
- **Advantages**: No port forwarding needed, always available, better for production
- **Setup**: `./setup-vscode-nodeport.sh`
- **URL**: Direct cluster access via NodePort

### Method 2: Port Forward Access (Recommended for Development)
- **Advantages**: Standard localhost access, easy debugging, secure tunnel
- **Setup**: `./setup-vscode-k8s.sh`
- **URL**: localhost:3001 via kubectl port-forward (HTTP mode only; stdio mode has no port)

## 📋 **Quick Setup Guide**

### Option A: NodePort Method (Easiest)
```bash
# Run the NodePort configuration script
./setup-vscode-nodeport.sh

# Restart VS Code
# Test with: @kubernetes-platform-engineer diagnose my cluster
```

### Option B: Port Forward Method
```bash
# 1. Start port forwarding
./mcp-port-forward.sh start

# 2. Configure VS Code
./setup-vscode-k8s.sh

# 3. Restart VS Code
# 4. Test with: @kubernetes-platform-engineer diagnose my cluster
```

## 🔧 **Management Commands**

### Port Forward Management
```bash
./mcp-port-forward.sh start     # Start port forwarding
./mcp-port-forward.sh stop      # Stop port forwarding
./mcp-port-forward.sh status    # Check status
./mcp-port-forward.sh test      # Test connectivity
./mcp-port-forward.sh logs      # View MCP server logs
./mcp-port-forward.sh restart   # Restart port forwarding
```

### Direct Cluster Access
```bash
# Test NodePort connectivity
curl http://${NODE_IP}:${NODE_PORT}/health

# Check MCP server status
kubectl get pods -n mcp-kubernetes
kubectl logs -n mcp-kubernetes deployment/kubernetes-mcp-server

# Check services
kubectl get svc -n mcp-kubernetes
```

## 🎯 **VS Code Configuration Details**

The setup scripts configure VS Code with the following MCP server settings:

```json
{
  "github.copilot.chat.experimental.modelContextProtocol": {
    "enabled": true,
    "servers": {
      "kubernetes-platform-engineer": {
        "command": "npx",
        "args": [
          "-y",
          "@modelcontextprotocol/server-fetch",
          "http://[SERVER_URL]"
        ],
        "description": "Kubernetes Platform Engineer MCP Server",
        "environment": {
          "MCP_SERVER_URL": "http://[SERVER_URL]",
          "K8S_NAMESPACE": "mcp-kubernetes",
          "K8S_SERVICE": "kubernetes-mcp-server-service"
        }
      }
    }
  }
}
```

## 🧪 **Testing Your Integration**

After setup, test the integration in VS Code:

1. **Open VS Code** and restart completely
2. **Open GitHub Copilot Chat**
3. **Try these commands**:
   ```
   @kubernetes-platform-engineer diagnose my cluster health
   @kubernetes-platform-engineer get cluster info
   @kubernetes-platform-engineer analyze pod performance in mcp-kubernetes namespace
   @kubernetes-platform-engineer troubleshoot any failing pods
   @kubernetes-platform-engineer search documentation for pod security
   ```

## 🔍 **Troubleshooting**

### Common Issues and Solutions

#### 1. MCP Server Not Responding
```bash
# Check pod status
kubectl get pods -n mcp-kubernetes

# Check logs
kubectl logs -n mcp-kubernetes deployment/kubernetes-mcp-server

# Test direct connectivity
curl http://${NODE_IP}:${NODE_PORT}/health
```

#### 2. Port Forward Issues
```bash
# Check if port forward is running
./mcp-port-forward.sh status

# Restart port forward
./mcp-port-forward.sh restart

# Check for port conflicts
lsof -i :3001
```

#### 3. VS Code Integration Issues
```bash
# Check VS Code settings
cat "$HOME/Library/Application Support/Code/User/settings.json" | grep -A 10 modelContextProtocol

# Restore backup settings
ls -la "$HOME/Library/Application Support/Code/User/settings.json.backup."*

# Test MCP fetch command directly
npx -y @modelcontextprotocol/server-fetch http://localhost:3001  # HTTP mode only (src/main.py); not the default stdio mode
```

#### 4. Network Connectivity Issues
```bash
# Check cluster connectivity
kubectl cluster-info

# Check service endpoints
kubectl get endpoints -n mcp-kubernetes

# Check NodePort service
kubectl get svc -n mcp-kubernetes kubernetes-mcp-server-nodeport
```

## 📊 **Health Monitoring**

Monitor your MCP server health:

```bash
# Quick health check
curl -s http://${NODE_IP}:${NODE_PORT}/health | jq '.'

# Pod resource usage
kubectl top pods -n mcp-kubernetes

# Service status
kubectl get svc -n mcp-kubernetes

# Recent events
kubectl get events -n mcp-kubernetes --sort-by='.lastTimestamp' | tail -5
```

## 🔄 **Switching Between Methods**

### From Port Forward to NodePort
```bash
# Stop port forwarding
./mcp-port-forward.sh stop

# Configure for NodePort
./setup-vscode-nodeport.sh

# Restart VS Code
```

### From NodePort to Port Forward
```bash
# Start port forwarding
./mcp-port-forward.sh start

# Configure for port forward
./setup-vscode-k8s.sh

# Restart VS Code
```

## 📝 **Configuration Files**

- **VS Code Settings**: `~/Library/Application Support/Code/User/settings.json`
- **Backup Files**: `settings.json.backup.*`
- **MCP Server Config**: Embedded in VS Code settings
- **Port Forward Script**: `./mcp-port-forward.sh`
- **Setup Scripts**: `./setup-vscode-*.sh`

## 🎯 **Best Practices**

1. **Use NodePort for Production**: More reliable, no port forwarding needed
2. **Use Port Forward for Development**: Better security, easier debugging
3. **Always Backup Settings**: Scripts automatically create backups
4. **Monitor Server Health**: Regular health checks and log monitoring
5. **Restart VS Code**: Always restart after configuration changes

## 🚀 **Advanced Usage**

### Custom Environment Variables
The MCP server supports additional environment variables:

```bash
export K8S_NAMESPACE="your-namespace"
export K8S_CONTEXT="your-context"
export DEBUG_MODE="true"
```

### Multiple Cluster Support
For multiple clusters, use different NodePorts or port forward on different ports:

```bash
# Cluster 1: Default port 3001
./setup-vscode-nodeport.sh

# Cluster 2: Custom port 3002
kubectl port-forward -n mcp-kubernetes service/kubernetes-mcp-server-service 3002:3001 &
```

## ✅ **Success Indicators**

You'll know the integration is working when:

1. ✅ Health endpoint responds: `{"status":"healthy",...}`
2. ✅ VS Code shows MCP server in Copilot chat
3. ✅ Commands like `@kubernetes-platform-engineer` work
4. ✅ Server provides cluster insights and recommendations
5. ✅ Documentation search and GitHub issues work

## 🆘 **Getting Help**

If you encounter issues:

1. **Check the logs**: `kubectl logs -n mcp-kubernetes deployment/kubernetes-mcp-server`
2. **Verify connectivity**: `curl http://${NODE_IP}:${NODE_PORT}/health`
3. **Test port forward**: `./mcp-port-forward.sh test`
4. **Restore settings**: Use backup files if needed
5. **Restart everything**: Stop services, restart VS Code, reconfigure

---

**Your Kubernetes MCP Server is ready for VS Code integration!** 🎉
