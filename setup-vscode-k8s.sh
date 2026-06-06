#!/bin/bash

# VS Code MCP Server Configuration for Kubernetes Deployment
# This script configures VS Code to use the MCP server running in Kubernetes

set -euo pipefail

VSCODE_SETTINGS_DIR="$HOME/Library/Application Support/Code/User"
SETTINGS_FILE="$VSCODE_SETTINGS_DIR/settings.json"
BACKUP_FILE="$SETTINGS_FILE.backup.$(date +%Y%m%d_%H%M%S)"

echo "🚀 Configuring VS Code for Kubernetes MCP Server Integration"
echo "============================================================"

# Backup existing settings
if [[ -f "$SETTINGS_FILE" ]]; then
    echo "📄 Backing up existing VS Code settings to: $BACKUP_FILE"
    cp "$SETTINGS_FILE" "$BACKUP_FILE"
else
    echo "📄 No existing VS Code settings found, creating new configuration"
    mkdir -p "$VSCODE_SETTINGS_DIR"
    echo "{}" > "$SETTINGS_FILE"
fi

# Check if port forward is active
echo "🔍 Checking MCP server connectivity..."
if curl -s http://localhost:3001/health >/dev/null 2>&1; then
    echo "✅ MCP server is accessible via port forward"
else
    echo "⚠️  MCP server not accessible on localhost:3001"
    echo "   Please ensure port forwarding is active:"
    echo "   kubectl port-forward -n mcp-kubernetes service/kubernetes-mcp-server-service 3001:3001"
    read -p "   Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborting configuration"
        exit 1
    fi
fi

# Create MCP configuration
echo "🔧 Configuring MCP server integration..."

cat > /tmp/mcp_config.json << 'EOF'
{
    "github.copilot.chat.experimental.modelContextProtocol": {
        "enabled": true,
        "servers": {
            "kubernetes-platform-engineer": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-fetch",
                    "http://localhost:3001"
                ],
                "description": "Kubernetes Platform Engineer MCP Server (Kubernetes Deployment)",
                "environment": {
                    "MCP_SERVER_URL": "http://localhost:3001",
                    "K8S_NAMESPACE": "mcp-kubernetes",
                    "K8S_SERVICE": "kubernetes-mcp-server-service"
                }
            }
        }
    },
    "github.copilot.advanced": {
        "debug.overrideEngine": "claude-3.5-sonnet"
    }
}
EOF

# Merge configurations using Python
[[ -f "$SETTINGS_FILE" ]] || { echo "VS Code settings not found at $SETTINGS_FILE"; exit 1; }

SETTINGS_FILE="$SETTINGS_FILE" python3 - <<'PYEOF'
import json
import os

settings_file = os.environ["SETTINGS_FILE"]

# Read existing settings
with open(settings_file, 'r') as f:
    existing_settings = json.load(f)

# Read new MCP configuration
with open("/tmp/mcp_config.json", 'r') as f:
    mcp_config = json.load(f)

# Merge configurations
for key, value in mcp_config.items():
    existing_settings[key] = value

# Write back to settings file
with open(settings_file, 'w') as f:
    json.dump(existing_settings, f, indent=2)

print("VS Code settings updated successfully")
PYEOF

echo "🎯 Configuration Complete!"
echo "========================="
echo
echo "📋 Setup Summary:"
echo "   • MCP Server: kubernetes-platform-engineer"
echo "   • Connection: localhost:3001 (via port forward)"
echo "   • Namespace: mcp-kubernetes"
echo "   • Service: kubernetes-mcp-server-service"
echo
echo "🚀 Next Steps:"
echo "   1. Ensure port forwarding is active:"
echo "      kubectl port-forward -n mcp-kubernetes service/kubernetes-mcp-server-service 3001:3001"
echo
echo "   2. Restart VS Code completely"
echo
echo "   3. Test the integration:"
echo "      • Open VS Code"
echo "      • Use GitHub Copilot Chat"
echo "      • Try: '@kubernetes-platform-engineer diagnose my cluster health'"
echo
echo "💡 Port Forward Management:"
echo "   • Start: kubectl port-forward -n mcp-kubernetes service/kubernetes-mcp-server-service 3001:3001 &"
echo "   • Stop:  pkill -f 'kubectl port-forward.*3001:3001'"
echo "   • Check: curl http://localhost:3001/health"
echo
echo "🔧 Troubleshooting:"
echo "   • If MCP server doesn't respond, check Kubernetes pod status:"
echo "     kubectl get pods -n mcp-kubernetes"
echo "   • View logs: kubectl logs -n mcp-kubernetes deployment/kubernetes-mcp-server"
echo "   • Restore settings: cp $BACKUP_FILE '$SETTINGS_FILE'"
echo
echo "✅ Ready to use Kubernetes MCP Server in VS Code!"
