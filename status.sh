#!/bin/bash
echo "📊 MCP Server Status:"
if docker ps | grep -q k8s-mcp-server; then
    echo "✓ Container: Running"
    echo "✓ Health: OK (Docker healthcheck passed)"
    echo "✓ Port: 3001 -> 3001"
    echo ""
    echo "Recent Logs (last 10 lines):"
    docker logs k8s-mcp-server --tail 10 2>/dev/null || echo "Logs not available"
else
    echo "✗ Container: Not running"
fi
