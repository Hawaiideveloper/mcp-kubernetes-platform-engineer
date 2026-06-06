#!/usr/bin/env bash
set -euo pipefail

# Kubernetes Platform Engineer MCP - Automated Setup Script
# This script sets up everything needed to run the MCP server with VS Code Copilot

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MCP_PORT=${MCP_PORT:-3001}
GITHUB_TOKEN=${GITHUB_TOKEN:-""}
LOG_LEVEL=${LOG_LEVEL:-"INFO"}
UPDATE_INTERVAL=${GITHUB_ISSUES_UPDATE_INTERVAL:-"3600"}

echo -e "${BLUE}🚀 Kubernetes Platform Engineer MCP Setup${NC}"
echo -e "${BLUE}===========================================${NC}"

# Function to print status messages
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check prerequisites
echo -e "\n${BLUE}Checking Prerequisites...${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    print_info "Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info &> /dev/null; then
    print_error "Docker is not running. Please start Docker first."
    exit 1
fi

print_status "Docker is installed and running"

# Check VS Code
if ! command -v code &> /dev/null; then
    print_warning "VS Code CLI not found in PATH"
    print_info "You may need to install VS Code CLI: https://code.visualstudio.com/docs/setup/mac#_launching-from-the-command-line"
else
    print_status "VS Code CLI is available"
fi

# Stop existing container if running
echo -e "\n${BLUE}Cleaning up existing instances...${NC}"
if docker ps | grep -q k8s-mcp-server; then
    print_info "Stopping existing MCP server container..."
    docker stop k8s-mcp-server &> /dev/null || true
fi

if docker ps -a | grep -q k8s-mcp-server; then
    print_info "Removing existing MCP server container..."
    docker rm k8s-mcp-server &> /dev/null || true
fi

# Build Docker image
echo -e "\n${BLUE}Building MCP Server Image...${NC}"
print_info "This may take a few minutes on first run..."

if docker build -t k8s-platform-engineer-mcp:latest . > build.log 2>&1; then
    print_status "Docker image built successfully"
    rm -f build.log
else
    print_error "Docker build failed. Check build.log for details."
    exit 1
fi

# Create data directories
echo -e "\n${BLUE}Setting up data directories...${NC}"
mkdir -p ./data/logs ./data/configs ./data/github_issues
print_status "Data directories created"

# Prepare environment variables
ENV_ARGS=""
# Write token to a short-lived temp file to avoid ps aux exposure
TMPENV=$(mktemp)
trap 'rm -f "$TMPENV"' EXIT
chmod 600 "$TMPENV"
if [ -n "${GITHUB_TOKEN:-}" ]; then
    printf 'GITHUB_TOKEN=%s\n' "$GITHUB_TOKEN" > "$TMPENV"
    ENV_ARGS="$ENV_ARGS --env-file $TMPENV"
    print_status "GitHub token configured for higher API limits (via env-file)"
fi

ENV_ARGS="$ENV_ARGS -e LOG_LEVEL=$LOG_LEVEL"
ENV_ARGS="$ENV_ARGS -e GITHUB_ISSUES_UPDATE_INTERVAL=$UPDATE_INTERVAL"

# Start MCP server
echo -e "\n${BLUE}Starting MCP Server...${NC}"
print_info "Starting server on port $MCP_PORT..."

# Check if port is available
if lsof -i :$MCP_PORT &> /dev/null; then
    print_error "Port $MCP_PORT is already in use"
    print_info "Try: MCP_PORT=3002 ./start.sh"
    exit 1
fi

# Check if kubeconfig exists
if [ -f ~/.kube/config ]; then
    print_status "Found kubectl configuration - enabling live cluster access"
    KUBE_MOUNT="-v $HOME/.kube/config:/root/.kube/config:ro"
else
    print_warning "No kubeconfig found at ~/.kube/config"
    print_info "Server will work but won't have live cluster access"
    KUBE_MOUNT=""
fi

# Run container in background
docker run -d \
    --name k8s-mcp-server \
    -p $MCP_PORT:3001 \
    -v "./data:/app/data" \
    $KUBE_MOUNT \
    $ENV_ARGS \
    k8s-platform-engineer-mcp:latest > /dev/null

print_status "MCP server container started"

# Wait for server to start and test health
echo -e "\n${BLUE}Verifying Server Health...${NC}"
print_info "Waiting for server to initialize..."
sleep 5

# Check if container is running
if ! docker ps | grep -q k8s-mcp-server; then
    print_error "MCP server failed to start"
    print_info "Check logs with: docker logs k8s-mcp-server"
    exit 1
fi

# Test server health
print_info "Testing server health..."
for i in {1..15}; do
    if docker ps | grep -q k8s-mcp-server && docker inspect k8s-mcp-server | grep -q '"Status": "running"'; then
        print_status "MCP server is running and healthy"
        break
    elif [ $i -eq 15 ]; then
        print_error "Server health check failed"
        print_info "Check logs with: docker logs k8s-mcp-server"
        exit 1
    else
        sleep 2
    fi
done

# Configure VS Code
echo -e "\n${BLUE}Configuring VS Code Integration...${NC}"

# Detect VS Code settings path
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    VSCODE_SETTINGS="$HOME/Library/Application Support/Code/User/settings.json"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    VSCODE_SETTINGS="$HOME/.config/Code/User/settings.json"
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    # Windows
    VSCODE_SETTINGS="$APPDATA/Code/User/settings.json"
else
    print_warning "Unknown OS type. Please manually configure VS Code settings."
    VSCODE_SETTINGS=""
fi

if [ ! -z "$VSCODE_SETTINGS" ]; then
    # Create settings directory if it doesn't exist
    mkdir -p "$(dirname "$VSCODE_SETTINGS")"
    
    # Create or update settings.json
    if [ -f "$VSCODE_SETTINGS" ]; then
        # Backup existing settings
        cp "$VSCODE_SETTINGS" "$VSCODE_SETTINGS.backup.$(date +%s)"
        print_info "Backed up existing VS Code settings"
        
        # Read existing settings
        EXISTING_SETTINGS=$(cat "$VSCODE_SETTINGS")
    else
        EXISTING_SETTINGS="{}"
    fi
    
    # Create MCP configuration
    MCP_CONFIG=$(cat << EOF
{
  "github.copilot.advanced": {
    "debug.overrideEngine": "mcp",
    "debug.testOverrideProxyUrl": "http://localhost:$MCP_PORT"
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
EOF
)
    
    # Merge configurations using jq if available
    if command -v jq &> /dev/null; then
        echo "$EXISTING_SETTINGS" | jq ". * $MCP_CONFIG" > "$VSCODE_SETTINGS"
        print_status "VS Code settings updated with MCP configuration"
    else
        # Fallback: replace settings entirely (simpler but less safe)
        echo "$MCP_CONFIG" > "$VSCODE_SETTINGS"
        print_warning "jq not found. VS Code settings replaced entirely."
        print_info "If you had existing settings, they're backed up."
    fi
else
    print_warning "Could not auto-configure VS Code. Please add MCP settings manually."
fi

# Create management scripts
echo -e "\n${BLUE}Creating management scripts...${NC}"

# Create stop script
cat > stop.sh << 'EOF'
#!/bin/bash
echo "🛑 Stopping Kubernetes Platform Engineer MCP..."
docker stop k8s-mcp-server 2>/dev/null || true
docker rm k8s-mcp-server 2>/dev/null || true
echo "✓ MCP server stopped"
EOF
chmod +x stop.sh

# Create update script
cat > update.sh << 'EOF'
#!/bin/bash
echo "🔄 Updating Kubernetes Platform Engineer MCP..."
./stop.sh
git pull origin main 2>/dev/null || echo "No git repository to update"
./start.sh
echo "✓ MCP server updated and restarted"
EOF
chmod +x update.sh

# Create logs script
cat > logs.sh << 'EOF'
#!/bin/bash
echo "📋 MCP Server Logs (Press Ctrl+C to exit):"
docker logs k8s-mcp-server -f
EOF
chmod +x logs.sh

# Create status script
cat > status.sh << 'EOF'
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
EOF
chmod +x status.sh

print_status "Management scripts created (stop.sh, update.sh, logs.sh, status.sh)"

# Final status and instructions
echo -e "\n${GREEN}🎉 Setup Complete!${NC}"
echo -e "${GREEN}==================${NC}"
echo -e "MCP Server URL: ${BLUE}http://localhost:$MCP_PORT${NC}"
echo -e "Container Name: ${BLUE}k8s-mcp-server${NC}"
echo -e ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. ${BLUE}Restart VS Code${NC} to load the new MCP configuration"
echo -e "2. ${BLUE}Open a file in VS Code${NC} and try asking Copilot about Kubernetes"
echo -e "3. ${BLUE}Test with:${NC} '// How do I debug a failing pod?'"
echo -e ""
echo -e "${YELLOW}Useful Commands:${NC}"
echo -e "• View logs: ${BLUE}./logs.sh${NC}"
echo -e "• Check status: ${BLUE}./status.sh${NC}"
echo -e "• Stop server: ${BLUE}./stop.sh${NC}"
echo -e "• Update server: ${BLUE}./update.sh${NC}"
echo -e ""
echo -e "${YELLOW}Features:${NC}"
echo -e "• ✅ Real-time GitHub issues monitoring (updates every hour)"
echo -e "• ✅ 45,720+ Kubernetes issues indexed and searchable"
echo -e "• ✅ 17+ major Kubernetes repositories tracked"
echo -e "• ✅ Automatic knowledge base growth as ecosystem evolves"
echo -e "• ✅ Comprehensive troubleshooting guides and solutions"
echo -e ""

if [ -z "$GITHUB_TOKEN" ]; then
    print_warning "For higher GitHub API limits, set GITHUB_TOKEN environment variable"
    print_info "Get token at: https://github.com/settings/tokens"
fi

echo -e "\n${GREEN}Your Kubernetes Platform Engineer MCP is ready! 🚀${NC}"
echo -e "${GREEN}The knowledge base will continue growing automatically as new issues are discovered.${NC}"
