# VS Code MCP Configuration Guide

## Automatic Configuration (Recommended)

Run the setup script which automatically configures VS Code:
```bash
./start.sh
```

The script will:
1. ✅ Backup your existing VS Code settings
2. ✅ Add MCP server configuration
3. ✅ Preserve your existing settings
4. ✅ Create management scripts

## Manual Configuration

If you prefer to configure VS Code manually, add this to your VS Code `settings.json`:

### Location of settings.json:
- **macOS**: `~/Library/Application Support/Code/User/settings.json`
- **Linux**: `~/.config/Code/User/settings.json`  
- **Windows**: `%APPDATA%/Code/User/settings.json`

### Configuration to Add:

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
        "exec",
        "-i", 
        "k8s-mcp-server",
        "python",
        "src/main.py",
        "--stdio"
      ],
      "env": {
        "MCP_SERVER_NAME": "kubernetes-platform-engineer",
        "MCP_SERVER_VERSION": "1.0.0"
      }
    }
  }
}
```

## Verification Steps

After configuration:

1. **Restart VS Code** completely
2. **Open any file** in VS Code
3. **Test the integration** by typing:
   ```
   // How do I troubleshoot a CrashLoopBackOff pod in Kubernetes?
   ```
4. **Press Tab** to see Copilot suggestions powered by the MCP server

## Expected Behavior

When working correctly, you should see:
- 🤖 Enhanced Copilot responses with specific Kubernetes troubleshooting steps
- 📋 References to actual GitHub issues and solutions
- 🔧 Step-by-step debugging commands
- 💡 Best practices from the community
- 🛡️ Security recommendations

## Troubleshooting

### VS Code Not Recognizing MCP

1. **Check server status**:
   ```bash
   ./status.sh
   ```

2. **Verify container is running**:
   ```bash
   docker ps | grep k8s-mcp-server
   ```

3. **Check VS Code Developer Console**:
   - Help → Toggle Developer Tools
   - Look for MCP connection messages

### MCP Server Not Responding

1. **Check logs**:
   ```bash
   ./logs.sh
   ```

2. **Restart the server**:
   ```bash
   ./stop.sh && ./start.sh
   ```

3. **Check port availability**:
   ```bash
   lsof -i :3001
   ```

### Copilot Not Using MCP

1. **Verify settings.json** is valid JSON
2. **Check that MCP extensions** are installed in VS Code
3. **Restart VS Code** after configuration changes
4. **Clear VS Code cache**:
   - Command Palette → "Developer: Reload Window"

## Advanced Configuration

### Custom Port
```bash
MCP_PORT=3002 ./start.sh
```
Then update the `testOverrideProxyUrl` in settings.json to match.

### GitHub Token (Recommended)
```bash
export GITHUB_TOKEN="your_github_token_here"
./start.sh
```

### Multiple Clusters
```bash
export KUBECONFIG=~/.kube/config:~/.kube/staging:~/.kube/prod
./start.sh
```

## Integration Examples

### Ask Copilot These Questions:

1. **Troubleshooting**:
   - "Why is my pod stuck in Pending state?"
   - "How do I debug ImagePullBackOff errors?"
   - "What causes OOMKilled containers?"

2. **Configuration**:
   - "Create a deployment YAML for nginx with health checks"
   - "Show me a service mesh configuration"
   - "Generate RBAC for a service account"

3. **Monitoring**:
   - "How do I monitor pod resource usage?"
   - "Set up alerts for node failures"
   - "Configure log aggregation for my cluster"

4. **Security**:
   - "Scan my cluster for security vulnerabilities"
   - "Implement network policies for namespace isolation"
   - "Configure pod security standards"

The MCP server will provide responses based on real GitHub issues and community solutions! 🚀
