#!/bin/bash

set -e

echo "🚀 Pushing Docker image to GitHub Container Registry..."

# Tag the image for GitHub Container Registry
docker tag k8s-platform-engineer-mcp:latest ghcr.io/hawaiideveloper/mcp-kubernetes-platform-engineer:latest

# Push to GitHub Container Registry
docker push ghcr.io/hawaiideveloper/mcp-kubernetes-platform-engineer:latest

echo "✅ Image pushed successfully!"

# Update the Kubernetes deployment
echo "🔄 Updating Kubernetes deployment..."
kubectl apply -f k8s/deployment.yaml

# Wait for deployment to be ready
echo "⏳ Waiting for deployment to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/kubernetes-mcp-server -n mcp-kubernetes

echo "🎉 Deployment complete!"

# Show status
kubectl get pods -n mcp-kubernetes
kubectl get services -n mcp-kubernetes
