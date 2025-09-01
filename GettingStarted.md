# Getting Started with Kubernetes Platform Engineer MCP Server

Welcome! This guide will help you get the MCP Server running in under 5 minutes.

---

## 🚀 Quick 5-Minute Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Hawaiideveloper/mcp-kubernetes-platform-engineer.git
cd mcp-kubernetes-platform-engineer
```

### 2. Start with Docker (Recommended for Fastest Start)
```bash
curl -fsSL https://raw.githubusercontent.com/Hawaiideveloper/mcp-kubernetes-platform-engineer/main/start.sh | bash
```
- This command builds and starts the MCP server in Docker.
- It also configures VS Code integration automatically.

### 3. Verify the Server is Running
```bash
docker ps | grep k8s-mcp-server
./logs.sh | tail -20
```
- You should see the container running and logs showing server activity.

### 4. Access the MCP Server
- **Local (Docker):**
  - Health check:  
    ```bash
    curl http://localhost:3001/health
    ```
- **Kubernetes (Optional):**
  - Deploy to your cluster:
    ```bash
    kubectl apply -f k8s/
    kubectl get pods -n mcp-kubernetes
    kubectl port-forward -n mcp-kubernetes service/kubernetes-mcp-server-service 3001:3001
    curl http://localhost:3001/health
    ```

### 5. Use in VS Code with Copilot
- Open VS Code. The setup script configures Copilot integration automatically.
- Try a query in Copilot Chat:
  - `@k8s-platform-engineer diagnose why my pods are crashing`
  - `@k8s-platform-engineer analyze resource usage in production namespace`

---

## 🛠️ Troubleshooting
- **Container not running?**
  - Run: `./logs.sh | tail -20` and check for errors.
- **Kubernetes issues?**
  - Ensure your kubeconfig is mounted and cluster is accessible.
- **VS Code integration not working?**
  - Restart VS Code and check settings.

---

## 📚 More Info
- See the [README.md](./README.md) for advanced configuration, Kubernetes deployment, and feature details.
- For help, open an issue on GitHub or check the `logs/` directory for diagnostics.

---

Enjoy your production-ready Kubernetes platform engineering assistant!
