#!/bin/bash
echo "🛑 Stopping Kubernetes Platform Engineer MCP..."
docker stop k8s-mcp-server 2>/dev/null || true
docker rm k8s-mcp-server 2>/dev/null || true
echo "✓ MCP server stopped"
