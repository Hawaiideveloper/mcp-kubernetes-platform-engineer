#!/bin/bash

# Kubernetes Platform Engineer MCP - Deployment Script
# This script deploys the MCP server to your Kubernetes cluster

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

echo -e "${BLUE}🚀 Kubernetes Platform Engineer MCP - Cluster Deployment${NC}"
echo -e "${BLUE}============================================================${NC}"

# Check prerequisites
echo -e "\n${BLUE}Checking Prerequisites...${NC}"

# Check kubectl
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl is not installed. Please install kubectl first."
    exit 1
fi

# Check cluster connection
if ! kubectl cluster-info &> /dev/null; then
    print_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
    exit 1
fi

print_status "kubectl is installed and cluster is accessible"

# Check Docker image
if ! docker images | grep -q k8s-platform-engineer-mcp; then
    print_warning "Docker image not found locally. Building..."
    docker build -t k8s-platform-engineer-mcp:latest .
    print_status "Docker image built successfully"
else
    print_status "Docker image found locally"
fi

# Get cluster info
CLUSTER_NAME=$(kubectl config current-context)
CLUSTER_SERVER=$(kubectl cluster-info | grep "control plane" | awk '{print $6}')

print_info "Current context: $CLUSTER_NAME"
print_info "Cluster server: $CLUSTER_SERVER"

# Check if we need to load the image into the cluster (for kind, minikube, etc.)
if [[ "$CLUSTER_NAME" == *"kind"* ]]; then
    print_info "Detected kind cluster. Loading Docker image..."
    kind load docker-image k8s-platform-engineer-mcp:latest
    print_status "Image loaded into kind cluster"
elif [[ "$CLUSTER_NAME" == *"minikube"* ]]; then
    print_info "Detected minikube cluster. Setting Docker environment..."
    eval $(minikube docker-env)
    docker build -t k8s-platform-engineer-mcp:latest .
    print_status "Image built in minikube environment"
fi

# Deploy to cluster
echo -e "\n${BLUE}Deploying to Kubernetes Cluster...${NC}"

# Apply manifests in order
print_info "Creating namespace..."
kubectl apply -f k8s/namespace.yaml

print_info "Creating RBAC..."
kubectl apply -f k8s/rbac.yaml

print_info "Creating ConfigMap..."
kubectl apply -f k8s/configmap.yaml

print_info "Creating Secret..."
kubectl apply -f k8s/secret.yaml

print_info "Creating PVC..."
kubectl apply -f k8s/pvc.yaml

print_info "Creating Deployment..."
kubectl apply -f k8s/deployment.yaml

print_info "Creating Service..."
kubectl apply -f k8s/service.yaml

# Optional: Deploy ingress
read -p "Deploy Ingress for external access? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Creating Ingress..."
    kubectl apply -f k8s/ingress.yaml
    print_status "Ingress created"
fi

print_status "All manifests applied successfully"

# Wait for deployment to be ready
echo -e "\n${BLUE}Waiting for deployment to be ready...${NC}"
kubectl wait --for=condition=available --timeout=300s deployment/mcp-server -n mcp-kubernetes

print_status "Deployment is ready!"

# Show status
echo -e "\n${BLUE}Deployment Status:${NC}"
kubectl get pods -n mcp-kubernetes -o wide
echo
kubectl get services -n mcp-kubernetes

# Get access information
echo -e "\n${BLUE}Access Information:${NC}"

# Cluster IP
CLUSTER_IP=$(kubectl get service mcp-server-service -n mcp-kubernetes -o jsonpath='{.spec.clusterIP}')
print_info "Cluster IP: http://$CLUSTER_IP:3001"

# NodePort
NODEPORT=$(kubectl get service mcp-server-nodeport -n mcp-kubernetes -o jsonpath='{.spec.ports[0].nodePort}')
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
print_info "NodePort: http://$NODE_IP:$NODEPORT"

# Port forward option
print_info "For local access, run: kubectl port-forward -n mcp-kubernetes service/mcp-server-service 3001:3001"

# Test endpoints
echo -e "\n${BLUE}Testing Endpoints...${NC}"
print_info "Setting up port forward for testing..."
kubectl port-forward -n mcp-kubernetes service/mcp-server-service 3001:3001 &
PORT_FORWARD_PID=$!
sleep 5

# Test health endpoint
if curl -s http://localhost:3001/health &> /dev/null; then
    print_status "Health endpoint is responding"
else
    print_warning "Health endpoint not ready yet (this is normal, may take a few minutes)"
fi

# Kill port forward
kill $PORT_FORWARD_PID 2>/dev/null || true

echo -e "\n${GREEN}🎉 Deployment Complete!${NC}"
echo -e "${GREEN}==============================${NC}"
echo -e "MCP Server deployed to namespace: ${BLUE}mcp-kubernetes${NC}"
echo -e "Service name: ${BLUE}mcp-server-service${NC}"
echo -e "NodePort: ${BLUE}http://$NODE_IP:$NODEPORT${NC}"
echo -e ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. ${BLUE}Access via NodePort:${NC} http://$NODE_IP:$NODEPORT"
echo -e "2. ${BLUE}Port forward for local access:${NC} kubectl port-forward -n mcp-kubernetes service/mcp-server-service 3001:3001"
echo -e "3. ${BLUE}Check logs:${NC} kubectl logs -n mcp-kubernetes deployment/mcp-server -f"
echo -e "4. ${BLUE}Monitor status:${NC} kubectl get pods -n mcp-kubernetes -w"
echo -e ""
echo -e "${YELLOW}Useful Commands:${NC}"
echo -e "• View pods: ${BLUE}kubectl get pods -n mcp-kubernetes${NC}"
echo -e "• View logs: ${BLUE}kubectl logs -n mcp-kubernetes deployment/mcp-server${NC}"
echo -e "• Delete deployment: ${BLUE}kubectl delete -f k8s/${NC}"
echo -e "• Scale deployment: ${BLUE}kubectl scale deployment mcp-server -n mcp-kubernetes --replicas=2${NC}"

echo -e "\n${GREEN}Your Kubernetes Platform Engineer MCP is now running in the cluster! 🚀${NC}"
