#!/bin/bash
echo "🔄 Updating Kubernetes Platform Engineer MCP..."
./stop.sh
git pull origin main 2>/dev/null || echo "No git repository to update"
./start.sh
echo "✓ MCP server updated and restarted"
