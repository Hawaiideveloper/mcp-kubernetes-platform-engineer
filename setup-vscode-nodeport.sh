#!/bin/bash

# Alternative VS Code MCP Configuration using NodePort
# This approach uses the external NodePort service for direct access

set -euo pipefail

VSCODE_SETTINGS_DIR="$HOME/Library/Application Support/Code/User"
SETTINGS_FILE="$VSCODE_SETTINGS_DIR/settings.json"
BACKUP_FILE="$SETTINGS_FILE.backup.nodeport.$(date +%Y%m%d_%H%M%S)"

# Get cluster IP and NodePort
CLUSTER_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
NODEPORT=$(kubectl get svc -n mcp-kubernetes kubernetes-mcp-server-nodeport -o jsonpath='{.spec.ports[0].nodePort}')

echo "🚀 Configuring VS Code for Direct NodePort MCP Server Access"
echo "============================================================"
echo "📍 Cluster IP: $CLUSTER_IP"
echo "🔌 NodePort: $NODEPORT"
echo "🌐 MCP Server URL: http://$CLUSTER_IP:$NODEPORT"

# Test connectivity
echo "🔍 Testing MCP server connectivity..."
if curl -s "http://$CLUSTER_IP:$NODEPORT/health" >/dev/null 2>&1; then
    echo "✅ MCP server is accessible via NodePort"
    HEALTH_RESPONSE=$(curl -s "http://$CLUSTER_IP:$NODEPORT/health")
    echo "   Response: $HEALTH_RESPONSE"
else
    echo "❌ MCP server not accessible via NodePort"
    echo "   URL: http://$CLUSTER_IP:$NODEPORT/health"
    echo "   Please check:"
    echo "   • kubectl get pods -n mcp-kubernetes"
    echo "   • kubectl get svc -n mcp-kubernetes"
    exit 1
fi

# Backup existing settings
if [[ -f "$SETTINGS_FILE" ]]; then
    echo "📄 Backing up existing VS Code settings to: $BACKUP_FILE"
    cp "$SETTINGS_FILE" "$BACKUP_FILE"
else
    echo "📄 No existing VS Code settings found, creating new configuration"
    mkdir -p "$VSCODE_SETTINGS_DIR"
    echo "{}" > "$SETTINGS_FILE"
fi

# Create MCP configuration for NodePort access
echo "🔧 Configuring MCP server integration..."

cat > /tmp/mcp_nodeport_config.json << EOF
{
    "github.copilot.chat.experimental.modelContextProtocol": {
        "enabled": true,
        "servers": {
            "kubernetes-platform-engineer": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-fetch",
                    "http://$CLUSTER_IP:$NODEPORT"
                ],
                "description": "Kubernetes Platform Engineer MCP Server (Direct NodePort Access)",
                "environment": {
                    "MCP_SERVER_URL": "http://$CLUSTER_IP:$NODEPORT",
                    "K8S_NAMESPACE": "mcp-kubernetes",
                    "K8S_SERVICE": "kubernetes-mcp-server-nodeport",
                    "CONNECTION_TYPE": "nodeport"
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
python3 << EOF
import json
import sys

settings_file = "$SETTINGS_FILE"

# Read existing settings
with open(settings_file, 'r') as f:
    existing_settings = json.load(f)

# Read new MCP configuration
with open("/tmp/mcp_nodeport_config.json", 'r') as f:
    mcp_config = json.load(f)

# Merge configurations
for key, value in mcp_config.items():
    existing_settings[key] = value

# Write back to settings file
with open(settings_file, 'w') as f:
    json.dump(existing_settings, f, indent=2)

print("✅ VS Code settings updated successfully")
EOF

echo "🎯 NodePort Configuration Complete!"
echo "==================================="
echo
echo "📋 Setup Summary:"
echo "   • MCP Server: kubernetes-platform-engineer"
echo "   • Connection: Direct NodePort access"
echo "   • URL: http://$CLUSTER_IP:$NODEPORT"
echo "   • Namespace: mcp-kubernetes"
echo "   • Service: kubernetes-mcp-server-nodeport"
echo
echo "✅ Advantages of NodePort Method:"
echo "   • No port forwarding required"
echo "   • Direct cluster access"
echo "   • Always available when cluster is running"
echo "   • Better for production use"
echo
echo "🚀 Next Steps:"
echo "   1. Restart VS Code completely"
echo "   2. Test the integration:"
echo "      • Open VS Code"
echo "      • Use GitHub Copilot Chat"
echo "      • Try: '@kubernetes-platform-engineer diagnose my cluster health'"
echo
echo "🔧 Troubleshooting:"
echo "   • Test connectivity: curl http://$CLUSTER_IP:$NODEPORT/health"
echo "   • Check pod status: kubectl get pods -n mcp-kubernetes"
echo "   • Check service: kubectl get svc -n mcp-kubernetes"
echo "   • Restore settings: cp $BACKUP_FILE '$SETTINGS_FILE'"
echo
echo "✅ Ready to use Kubernetes MCP Server in VS Code!"
