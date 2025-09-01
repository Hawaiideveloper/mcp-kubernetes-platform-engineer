#!/bin/bash

# MCP Server Port Forward Management Script
# Manage port forwarding for Kubernetes MCP server

set -euo pipefail

NAMESPACE="mcp-kubernetes"
SERVICE="kubernetes-mcp-server-service"
LOCAL_PORT="3001"
REMOTE_PORT="3001"

show_help() {
    cat << EOF
🚀 MCP Server Port Forward Manager

Usage: $0 [COMMAND]

Commands:
    start     Start port forwarding to MCP server
    stop      Stop port forwarding
    status    Check port forwarding status
    restart   Restart port forwarding
    test      Test MCP server connectivity
    logs      Show MCP server logs
    help      Show this help message

Examples:
    $0 start           # Start port forwarding
    $0 test            # Test if MCP server is accessible
    $0 logs            # View MCP server logs

Port Forward Details:
    Local:  http://localhost:$LOCAL_PORT
    Remote: $SERVICE.$NAMESPACE.svc.cluster.local:$REMOTE_PORT
EOF
}

start_port_forward() {
    echo "🚀 Starting port forward to MCP server..."
    
    # Check if already running
    if pgrep -f "kubectl port-forward.*$SERVICE.*$LOCAL_PORT:$REMOTE_PORT" > /dev/null; then
        echo "⚠️  Port forward already running"
        return 0
    fi
    
    # Check if pod is running
    if ! kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=kubernetes-platform-engineer | grep -q Running; then
        echo "❌ MCP server pod is not running"
        echo "   Check pod status: kubectl get pods -n $NAMESPACE"
        return 1
    fi
    
    # Start port forward in background
    kubectl port-forward -n $NAMESPACE service/$SERVICE $LOCAL_PORT:$REMOTE_PORT &
    
    # Wait for port forward to be ready
    echo "⏳ Waiting for port forward to be ready..."
    sleep 3
    
    if test_connectivity; then
        echo "✅ Port forward started successfully"
        echo "   Access MCP server at: http://localhost:$LOCAL_PORT"
    else
        echo "❌ Port forward failed to start"
        return 1
    fi
}

stop_port_forward() {
    echo "🛑 Stopping port forward..."
    
    if pkill -f "kubectl port-forward.*$SERVICE.*$LOCAL_PORT:$REMOTE_PORT"; then
        echo "✅ Port forward stopped"
    else
        echo "⚠️  No port forward process found"
    fi
}

check_status() {
    echo "🔍 Checking port forward status..."
    
    if pgrep -f "kubectl port-forward.*$SERVICE.*$LOCAL_PORT:$REMOTE_PORT" > /dev/null; then
        PID=$(pgrep -f "kubectl port-forward.*$SERVICE.*$LOCAL_PORT:$REMOTE_PORT")
        echo "✅ Port forward is running (PID: $PID)"
        
        if test_connectivity; then
            echo "✅ MCP server is accessible"
        else
            echo "⚠️  Port forward running but MCP server not responding"
        fi
    else
        echo "❌ Port forward is not running"
        echo "   Start with: $0 start"
    fi
}

test_connectivity() {
    if curl -s http://localhost:$LOCAL_PORT/health > /dev/null 2>&1; then
        RESPONSE=$(curl -s http://localhost:$LOCAL_PORT/health)
        echo "✅ MCP server is healthy: $RESPONSE"
        return 0
    else
        echo "❌ MCP server is not accessible on localhost:$LOCAL_PORT"
        return 1
    fi
}

show_logs() {
    echo "📋 MCP server logs (last 20 lines):"
    echo "=================================="
    kubectl logs -n $NAMESPACE deployment/kubernetes-mcp-server --tail=20
}

restart_port_forward() {
    echo "🔄 Restarting port forward..."
    stop_port_forward
    sleep 2
    start_port_forward
}

case "${1:-help}" in
    start)
        start_port_forward
        ;;
    stop)
        stop_port_forward
        ;;
    status)
        check_status
        ;;
    restart)
        restart_port_forward
        ;;
    test)
        test_connectivity
        ;;
    logs)
        show_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo "   Use '$0 help' for usage information"
        exit 1
        ;;
esac
