#!/bin/bash
echo "📋 MCP Server Logs (Press Ctrl+C to exit):"
docker logs k8s-mcp-server -f
