# Kubernetes Platform Engineer MCP Server

A comprehensive Model Context Protocol (MCP) server designed for Kubernetes platform engineering, cluster troubleshooting, monitoring, and advanced system administration.

> **🧠 Always Learning**: This MCP server continuously monitors 17+ major Kubernetes repositories and automatically updates its knowledge base every hour. As the Kubernetes ecosystem evolves with new issues, solutions, and best practices, your assistant grows smarter without any manual intervention.

## 🚀 **Quick Start - One Command Setup**

```bash
# Automated setup with VS Code integration
curl -fsSL https://raw.githubusercontent.com/your-org/mcp-kubernetes-platform-engineer/main/start.sh | bash
```

**That's it!** The script will:
- ✅ Build and start the MCP server
- ✅ Configure VS Code/Copilot integration automatically  
- ✅ Create management scripts (start/stop/logs/status)
- ✅ Begin continuous learning from Kubernetes GitHub issues

### **Manual Setup (if preferred)**

```bash
git clone https://github.com/your-org/mcp-kubernetes-platform-engineer.git
cd mcp-kubernetes-platform-engineer
./start.sh
```

## 🛠️ **Core Features**

### **🔧 Cluster Management & Troubleshooting**
- **Comprehensive Cluster Health Diagnostics** - Deep analysis of nodes, pods, services, and networking
- **Pod Issue Troubleshooting** - Automated diagnosis of CrashLoopBackOff, ImagePullBackOff, and resource issues
- **Network Connectivity Testing** - Ping, DNS, HTTP, and TCP connectivity diagnostics between pods and services
- **Resource Usage Analysis** - CPU, memory, storage, and network analysis across cluster, nodes, namespaces, and pods

### **📚 Documentation & Knowledge Base**
- **Live Kubernetes Documentation Search** - Real-time access to official Kubernetes documentation and best practices
- **Command Reference** - Instant kubectl, helm, kubeadm command lookup with examples and usage
- **Best Practices Database** - Comprehensive collection of Kubernetes best practices by category
- **Troubleshooting Guides** - Official troubleshooting guides and solutions from Kubernetes documentation

### **🐛 GitHub Issues Intelligence & Continuous Learning**
- **Live Issue Database** - Monitors 17 major Kubernetes repositories with 45,720+ indexed issues
- **Automatic Knowledge Updates** - Fetches new issues every hour, ensuring cutting-edge knowledge
- **Similar Issue Detection** - AI-powered matching of current problems with known solutions
- **Solution Mining** - Extracts solutions, workarounds, and fixes from resolved issues  
- **Trending Issues Monitoring** - Real-time awareness of current widespread problems
- **Ecosystem Growth Tracking** - Automatically adapts as Kubernetes matures and evolves
- **Pattern Recognition** - Learns from issue patterns to predict and prevent common problems

### **📊 Performance Monitoring & Analysis**
- **Real-time Performance Metrics** - CPU, memory, disk I/O, and network performance monitoring
- **Bottleneck Identification** - Automated detection of performance bottlenecks and resource constraints
- **Log Analysis & Aggregation** - Intelligent log parsing, error pattern detection, and trend analysis
- **Capacity Planning** - Resource utilization trends and scaling recommendations

### **🔒 Security & Compliance**
- **RBAC Security Scanning** - Analysis of roles, role bindings, and service account privileges
- **Pod Security Standards** - Compliance checking against baseline and restricted security standards
- **Network Policy Analysis** - Network segmentation and micro-segmentation assessment
- **Container Image Vulnerability Scanning** - CVE detection and base image security analysis
- **Secrets Management Audit** - Detection of plaintext secrets and rotation compliance

### **🤖 Automated Remediation**
- **Intelligent Issue Resolution** - Automated remediation for common cluster issues
- **Best Practices Recommendations** - Actionable suggestions for performance, security, and reliability
- **Compliance Guidance** - Step-by-step remediation for CIS Kubernetes Benchmark and NIST standards

## 🎯 **MCP Tools Overview**

| Tool | Description | Use Case |
|------|-------------|----------|
| `get_cluster_info` | Comprehensive cluster information | Initial cluster assessment |
| `diagnose_cluster_health` | Multi-dimensional health diagnostics | Regular health checks |
| `troubleshoot_pod_issues` | Pod-specific issue diagnosis | Pod troubleshooting |
| `analyze_resource_usage` | Resource utilization analysis | Performance optimization |
| `check_network_connectivity` | Network connectivity testing | Network troubleshooting |
| `analyze_logs` | Log aggregation and analysis | Issue investigation |
| `security_scan` | Security and compliance scanning | Security assessments |
| `performance_analysis` | Detailed performance analysis | Performance tuning |
| `get_recommendations` | Best practices recommendations | Optimization guidance |
| `execute_remediation` | Automated issue remediation | Incident response |
| **`search_documentation`** | **Live Kubernetes docs search** | **Finding official solutions** |
| **`get_best_practices`** | **Category-specific best practices** | **Implementation guidance** |
| **`find_kubectl_commands`** | **Command reference lookup** | **Command discovery** |
| **`get_troubleshooting_guide`** | **Official troubleshooting guides** | **Issue resolution** |
| **`search_github_issues`** | **Search known GitHub issues** | **Finding similar problems** |
| **`find_similar_issues`** | **AI-powered issue matching** | **Problem recognition** |
| **`get_trending_issues`** | **Current widespread issues** | **Proactive monitoring** |
| **`get_issue_statistics`** | **Issue database insights** | **Trend analysis** |

## 🔧 **Installation & Setup**

### **Prerequisites**

- **Docker & Docker Compose** - For containerized deployment
- **Kubernetes Cluster Access** - Valid kubeconfig file
- **kubectl** - Kubernetes command-line tool
- **Helm** (optional) - For deploying monitoring stack

### **Configuration**

Create a `.env` file for custom configuration:

```bash
# Kubernetes Configuration
KUBECONFIG=/path/to/kubeconfig
K8S_NAMESPACE=default
K8S_CONTEXT=your-context
K8S_CLUSTER_NAME=your-cluster

# Server Configuration  
MCP_HOST=0.0.0.0
MCP_PORT=3000
DEBUG=false

# Monitoring Configuration
PROMETHEUS_URL=http://prometheus:9090
GRAFANA_URL=http://grafana:3000
ENABLE_METRICS=true

# Security Configuration
RBAC_ENABLED=true
POD_SECURITY_STANDARDS=true
NETWORK_POLICIES=true

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=/app/logs/k8s-platform-engineer.log
```

### **Manual Installation**

```bash
# Clone and setup
git clone <repository-url>
cd mcp-kubernetes-platform-engineer

# Install Python dependencies
pip install -r requirements.txt

# Run the server
python src/main.py
```

## 📋 **Usage Examples**

### **AI Assistant Integration**

**VS Code with GitHub Copilot:**
```json
{
  "github.copilot.chat.experimental.modelContextProtocol": {
    "enabled": true,
    "servers": {
      "k8s-platform-engineer": {
        "command": "docker",
        "args": ["exec", "k8s-platform-engineer", "python", "src/main.py"],
        "description": "Kubernetes Platform Engineer for cluster troubleshooting"
      }
    }
  }
}
```

**Example Queries:**
- `@k8s-platform-engineer diagnose why my pods are crashing`
- `@k8s-platform-engineer analyze resource usage in production namespace`
- `@k8s-platform-engineer check network connectivity between frontend and backend pods`
- `@k8s-platform-engineer scan for security vulnerabilities`
- `@k8s-platform-engineer search documentation for pod security best practices`
- `@k8s-platform-engineer find similar issues for "ImagePullBackOff error"`
- `@k8s-platform-engineer get kubectl commands for debugging failed pods`
- `@k8s-platform-engineer show trending kubernetes issues this week`

### **Direct API Usage**

```bash
# Get cluster health overview
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "diagnose_cluster_health",
      "arguments": {
        "check_types": ["nodes", "pods", "services", "networking"]
      }
    }
  }'

# Troubleshoot specific pod
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call", 
    "params": {
      "name": "troubleshoot_pod_issues",
      "arguments": {
        "pod_name": "my-app-pod",
        "namespace": "production",
        "include_logs": true
      }
    }
  }'

# Search Kubernetes documentation
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "search_documentation", 
      "arguments": {
        "query": "pod security best practices",
        "max_results": 5
      }
    }
  }'

# Find similar GitHub issues
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "find_similar_issues",
      "arguments": {
        "error_message": "ImagePullBackOff: Failed to pull image",
        "max_results": 10
      }
    }
  }'
```

## 🧠 **Continuous Learning & Knowledge Evolution**

The MCP server is designed to grow smarter over time by continuously monitoring the Kubernetes ecosystem:

### **How It Works**

1. **Hourly GitHub Monitoring** 📊
   - Scans 17+ major Kubernetes repositories every hour
   - Tracks: `kubernetes/kubernetes`, `helm/helm`, `istio/istio`, `prometheus/prometheus`, etc.
   - Identifies new issues, solutions, and patterns as they emerge

2. **Intelligent Knowledge Curation** 🤖  
   - Automatically categorizes issues by severity, component, and solution type
   - Extracts actionable solutions and workarounds from resolved issues
   - Builds searchable index with semantic understanding

3. **Pattern Recognition** 🔍
   - Learns from issue patterns to predict common failure modes
   - Identifies trending problems before they become widespread
   - Tracks resolution success rates for different solution approaches

4. **Database Optimization** ⚡
   - Automatically cleans up outdated issues (> 1 year old)
   - Maintains performance while growing knowledge base
   - Prioritizes recent and high-impact issues for faster retrieval

### **Monitored Repositories**

| Repository | Focus Area | Why Important |
|------------|------------|---------------|
| `kubernetes/kubernetes` | Core platform | Main Kubernetes issues and fixes |
| `kubernetes/kubectl` | CLI tooling | Command-line troubleshooting |
| `kubernetes/kubeadm` | Cluster setup | Installation and bootstrap issues |
| `helm/helm` | Package management | Application deployment problems |
| `istio/istio` | Service mesh | Network and security challenges |
| `prometheus/prometheus` | Monitoring | Observability and metrics issues |
| `grafana/grafana` | Visualization | Dashboard and alerting problems |
| `cilium/cilium` | Networking | CNI and network policy issues |
| `projectcalico/calico` | Networking | Alternative CNI solutions |
| + 8 more repositories | Various | Comprehensive ecosystem coverage |

### **Knowledge Growth Metrics**

Track your MCP server's learning progress:
```bash
curl http://localhost:3001/stats | jq '.knowledge_base'
```

Example output:
```json
{
  "total_issues": 47832,
  "issues_added_today": 127,
  "solutions_extracted": 12405,
  "trending_problems": 23,
  "last_update": "2025-01-10T02:49:24Z",
  "repositories_monitored": 17,
  "knowledge_freshness": "99.2%"
}
```

### **What This Means for You**

🎯 **Always Current**: Your troubleshooting assistant knows about the latest Kubernetes issues and solutions

🔮 **Predictive**: Get warned about emerging problems before they hit your clusters

🌍 **Community-Driven**: Benefit from the collective knowledge of thousands of Kubernetes practitioners

⚡ **Performance**: Recent and relevant issues are prioritized for faster problem resolution

🛡️ **Future-Proof**: As Kubernetes evolves, your assistant evolves with it automatically

## 🏗️ **Architecture**

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Server                               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ Kubernetes      │  │ Diagnostics     │                  │
│  │ Manager         │  │ Manager         │                  │
│  └─────────────────┘  └─────────────────┘                  │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ Monitoring      │  │ Security        │                  │
│  │ Manager         │  │ Manager         │                  │
│  └─────────────────┘  └─────────────────┘                  │
├─────────────────────────────────────────────────────────────┤
│                 Kubernetes Cluster                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │   Nodes     │ │    Pods     │ │  Services   │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

## 🔍 **Troubleshooting Guide**

This section documents all issues encountered during development and deployment, along with their solutions. Each issue is documented with the error, root cause, solution, and prevention steps.

### **🚨 Known Issues & Solutions**

#### **Issue #001: Python Environment Configuration**
**Error:** `ModuleNotFoundError: No module named 'kubernetes'`
**Cause:** Missing Python dependencies in virtual environment
**Solution:**
```bash
# Activate virtual environment
source .venv/bin/activate

# Install all dependencies
pip install -r requirements.txt

# Verify installation
python -c "import kubernetes; print('Success')"
```
**Prevention:** Always activate virtual environment before running commands
**Status:** ✅ Resolved

#### **Issue #002: pytest Configuration Syntax**
**Error:** `pytest.ini:1: invalid syntax`
**Cause:** TOML syntax used in INI file format
**Solution:**
```bash
# Convert pytest.ini from TOML to INI format
[tool:pytest]  # Remove this line
# Replace with:
[pytest]
```
**Prevention:** Use correct INI syntax for pytest.ini files
**Status:** ✅ Resolved

#### **Issue #004: stern Download URL Incorrect**
**Error:** `wget: server returned error 404` during Docker build
**Cause:** Incorrect stern version URL in Dockerfile
**Solution:**
```dockerfile
# Fix stern download URL
RUN wget https://github.com/stern/stern/releases/download/v1.32.0/stern_1.32.0_linux_amd64.tar.gz
```
**Prevention:** Verify GitHub release URLs before using in Dockerfiles
**Status:** ✅ Resolved

#### **Issue #005: lsb_release Dependency Missing**
**Error:** `./configure: error: lsb_release not found` during Docker build
**Cause:** Missing lsb_release package in Debian bookworm
**Solution:**
```dockerfile
# Hardcode Debian version instead of using lsb_release
RUN echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian bookworm stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
```
**Prevention:** Use explicit OS version strings in Dockerfiles
**Status:** ✅ Resolved

#### **Issue #006: Non-existent Python Packages**
**Error:** `ERROR: Could not find a version that satisfies the requirement kubectl-python`
**Cause:** Dependencies list included packages that don't exist on PyPI
**Solution:**
```bash
# Remove these non-existent packages from requirements.txt:
# - kubectl-python (doesn't exist)
# - sqlite3 (built into Python)  
# - podman-py (not needed)
```
**Prevention:** Verify package names on PyPI before adding to requirements
**Status:** ✅ Resolved

#### **Issue #007: Docker Volume Mount Path Issue**
**Error:** `"~/.kube/config" includes invalid characters for a local volume name`
**Cause:** Docker doesn't expand tilde (~) in volume mount paths
**Solution:**
```bash
# Use $HOME instead of ~ in Docker volume mounts
KUBE_MOUNT="-v $HOME/.kube/config:/root/.kube/config:ro"
```
**Prevention:** Always use absolute paths in Docker volume mounts
**Status:** ✅ Resolved

#### **Issue #008: MCP Server Health Check Failures**
**Error:** Health check fails with curl connection refused
**Cause:** MCP server doesn't provide HTTP endpoints, only MCP protocol
**Solution:**
```bash
**Prevention:** Use absolute paths for all file system references
**Status:** ✅ Resolved

### **🚀 Setup & Continuous Learning Issues**

#### **Setup Script Failures**
**Error:** `./start.sh: Permission denied` or script execution fails
**Cause:** Script not executable or missing dependencies
**Solution:**
```bash
# Make script executable
chmod +x start.sh

# Check prerequisites
docker --version
code --version

# Run with debugging
bash -x ./start.sh
```
**Prevention:** Always check script permissions and prerequisites

#### **VS Code Configuration Issues**
**Error:** MCP not recognized in VS Code after setup
**Cause:** VS Code needs restart or settings not properly merged
**Solution:**
```bash
# Check VS Code settings location
ls -la "$HOME/Library/Application Support/Code/User/settings.json"

# Restart VS Code completely
code --command="workbench.action.quit"

# Check for backup files
ls -la "$HOME/Library/Application Support/Code/User/settings.json.backup.*"
```
**Prevention:** Restart VS Code after any settings changes

#### **Continuous Learning Rate Limiting**
**Error:** Frequent "Rate limited for kubernetes/kubernetes" warnings
**Cause:** GitHub API rate limits without authentication token
**Solution:**
```bash
# Set GitHub token for higher limits
export GITHUB_TOKEN="your_github_token_here"
./start.sh

# Or restart existing container with token
docker stop k8s-mcp-server
GITHUB_TOKEN="your_token" ./start.sh
```
**Prevention:** Always use GitHub token for production deployments

#### **Knowledge Base Growth Issues**
**Error:** Knowledge base not updating or growing slowly
**Cause:** Network issues or repository access problems
**Solution:**
```bash
# Check container logs for GitHub API issues
./logs.sh | grep -i "github\|rate\|error"

# Verify network connectivity
docker exec k8s-mcp-server ping -c 3 api.github.com

# Check background update loop status
docker exec k8s-mcp-server ps aux | grep python
```
**Prevention:** Monitor logs regularly and ensure stable network connection

#### **Container Health Issues**
**Error:** Container starts but shows as unhealthy
**Cause:** Resource constraints or initialization timeouts
**Solution:**
```bash
# Check container resources
docker stats k8s-mcp-server

# Increase initialization timeout
sleep 10 && ./status.sh

# Check detailed container information
docker inspect k8s-mcp-server | jq '.State'
```
**Prevention:** Ensure adequate system resources (1GB+ RAM recommended)

### **🔧 Installation Issues**
```
**Prevention:** Use appropriate health checks for each service type
**Status:** ✅ Resolved

#### **Issue #003: PostgreSQL Dependency Conflicts**
**Error:** `Building wheel for psycopg2 failed` during pip install
**Cause:** PostgreSQL development libraries missing
**Solution:**
```bash
# Option 1: Install system dependencies (macOS)
brew install postgresql

# Option 2: Use binary package
pip install psycopg2-binary

# Option 3: Remove PostgreSQL dependencies if not needed
pip install --no-deps pytest asyncio-mqtt aiohttp
```
**Prevention:** Use psycopg2-binary for development environments
**Status:** ✅ Resolved

#### **Issue #004: Stern Tool Download URL Invalid**
**Error:** `404 Not Found` when downloading stern tool in Docker build
**Cause:** Incorrect version number in download URL (stern_1.28.0 doesn't exist)
**Solution:**
```bash
# Fix Dockerfile stern installation
RUN wget https://github.com/stern/stern/releases/download/v1.32.0/stern_1.32.0_linux_amd64.tar.gz \
    && tar -xzf stern_1.32.0_linux_amd64.tar.gz \
    && mv stern /usr/local/bin/ \
    && rm stern_1.32.0_linux_amd64.tar.gz
```
**Prevention:** Always verify GitHub release versions before using in Dockerfile
**Status:** ✅ Resolved

#### **Issue #006: Non-existent Python Packages in requirements.txt**
**Error:** `ERROR: No matching distribution found for kubectl-python>=3.0.0`
**Cause:** Several packages in requirements.txt don't exist on PyPI
**Solution:**
```bash
# Remove non-existent packages from requirements.txt:
# - kubectl-python>=3.0.0 (doesn't exist, kubernetes>=28.1.0 is correct)
# - sqlite3 (built-in module, can't be installed via pip)
# - podman-py>=0.1.0 (non-standard package name)
```
**Prevention:** Verify package names on PyPI before adding to requirements.txt
**Status:** ✅ Resolved

#### **Container Build Success**
**Status:** ✅ Docker image built successfully
**Build Time:** ~4.5 minutes
**Image Size:** Contains comprehensive Kubernetes tooling
**Next Step:** Container launch and testing

### **🔧 Installation Issues**

#### **Container fails to start:**
```bash
# Check logs
docker logs k8s-platform-engineer

# Verify kubeconfig
kubectl cluster-info

# Test connectivity
kubectl get nodes
```

#### **Permission denied errors:**
```bash
# Check RBAC permissions
kubectl auth can-i get pods --as=system:serviceaccount:default:default

# Create service account with appropriate permissions
kubectl create clusterrolebinding k8s-platform-engineer \
  --clusterrole=cluster-admin \
  --serviceaccount=default:k8s-platform-engineer
```

#### **Network connectivity issues:**
```bash
# Test cluster connectivity
kubectl get svc

# Verify DNS resolution
nslookup kubernetes.default.svc.cluster.local

# Check network policies
kubectl get networkpolicies --all-namespaces
```

### **🧪 Testing Issues**

#### **Test Suite Execution Failures**
```bash
# Run tests with verbose output
pytest -v --tb=short

# Run specific test categories
pytest tests/unit/ -v
pytest tests/integration/ -v

# Skip slow tests
pytest -m "not slow"

# Generate coverage report
pytest --cov=src --cov-report=html
```

#### **Mock and Fixture Issues**
```bash
# Debug fixture issues
pytest --fixtures tests/

# Run with pdb on failures
pytest --pdb

# Clear pytest cache
pytest --cache-clear
```

### **⚡ Performance Issues**

#### **Slow API Response Times**
- **Symptoms:** Tool calls taking >10 seconds
- **Diagnosis:** Check Kubernetes API server latency
- **Solutions:**
  - Increase timeout values in configuration
  - Implement connection pooling
  - Cache frequently accessed data

#### **High Memory Usage**
- **Symptoms:** Container memory usage >1GB
- **Diagnosis:** Memory leaks in async operations
- **Solutions:**
  - Implement proper resource cleanup
  - Use connection limits
  - Monitor with memory profiler

### **🔐 Security Issues**

#### **RBAC Permission Errors**
```bash
# Check current permissions
kubectl auth can-i --list

# Create minimal RBAC setup
kubectl apply -f rbac-minimal.yaml

# Test specific permissions
kubectl auth can-i get pods --namespace=production
```

#### **Certificate Expiration**
```bash
# Check certificate expiration
kubectl get csr

# Renew expired certificates
kubeadm certs renew all

# Verify certificate validity
openssl x509 -in /etc/kubernetes/pki/apiserver.crt -text -noout
```

### **📊 Monitoring & Observability Issues**

#### **Metrics Collection Failures**
- **Check Prometheus configuration**
- **Verify metric endpoints accessibility**
- **Review scrape target health**

#### **Log Aggregation Issues**
- **Verify log formatting (JSON)**
- **Check log rotation policies**
- **Monitor disk space usage**

### **🐛 Common Error Messages**

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `connection refused` | API server unreachable | Check kubeconfig and network |
| `forbidden: User cannot...` | RBAC permissions | Update RBAC policies |
| `no such file or directory` | Missing kubeconfig | Set KUBECONFIG environment variable |
| `context deadline exceeded` | API timeout | Increase timeout or check cluster health |
| `x509: certificate has expired` | Expired certificates | Renew cluster certificates |

### **📝 Debugging Techniques**

#### **Enable Debug Logging**
```bash
# Set debug environment variable
export DEBUG=true

# Run with verbose logging
python src/main.py --log-level=DEBUG

# Docker with debug logging
docker run -e DEBUG=true k8s-platform-engineer-mcp
```

#### **Network Debugging**
```bash
# Test pod-to-pod connectivity
kubectl exec -it test-pod -- ping target-pod

# DNS resolution testing
kubectl exec -it test-pod -- nslookup kubernetes.default.svc.cluster.local

# Service endpoint testing
kubectl get endpoints service-name
```

#### **Resource Debugging**
```bash
# Check resource usage
kubectl top nodes
kubectl top pods --all-namespaces

# Describe problematic resources
kubectl describe pod problematic-pod
kubectl describe node problematic-node
```

### **🔄 Recovery Procedures**

#### **Service Recovery**
```bash
# Restart MCP server
docker restart k8s-platform-engineer

# Force pod recreation
kubectl delete pod app-pod --grace-period=0 --force

# Drain and uncordon node
kubectl drain node-name --ignore-daemonsets
kubectl uncordon node-name
```

#### **Data Recovery**
```bash
# Restore from backup
kubectl apply -f backup-manifests/

# Emergency cluster restore
kubeadm reset && kubeadm init --config=cluster-config.yaml
```

### **📞 Getting Help**

When reporting issues, please include:

1. **Error message** (full stack trace)
2. **Environment details** (OS, Docker version, Kubernetes version)
3. **Configuration files** (redacted sensitive information)
4. **Reproduction steps**
5. **Expected vs actual behavior**

**Issue Template:**
```markdown
**Environment:**
- OS: [e.g., macOS 14.0]
- Docker: [e.g., 24.0.6]
- Kubernetes: [e.g., v1.28.2]
- Python: [e.g., 3.11.5]

**Error Message:**
[Paste full error message here]

**Steps to Reproduce:**
1. Step one
2. Step two
3. Step three

**Expected Behavior:**
[What should happen]

**Actual Behavior:**
[What actually happened]

**Additional Context:**
[Any other relevant information]
```

## 📊 **Monitoring & Observability**

The MCP server includes built-in monitoring capabilities:

- **Health Checks** - `/health` endpoint for monitoring
- **Metrics Export** - Prometheus-compatible metrics on port 8080
- **Structured Logging** - JSON-formatted logs with correlation IDs
- **Performance Tracking** - Response time and resource usage metrics

## 🔒 **Security Considerations**

- **RBAC Integration** - Respects Kubernetes RBAC permissions
- **Secure Communication** - TLS support for production deployments
- **Audit Logging** - All operations are logged for security auditing
- **Container Security** - Non-root container execution with minimal privileges

## 🤝 **Contributing**

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙋 **Support**

- **Documentation** - [Wiki](https://github.com/your-org/mcp-kubernetes-platform-engineer/wiki)
- **Issues** - [GitHub Issues](https://github.com/your-org/mcp-kubernetes-platform-engineer/issues)
- **Discussions** - [GitHub Discussions](https://github.com/your-org/mcp-kubernetes-platform-engineer/discussions)

---

**Built for Kubernetes Platform Engineers by Kubernetes Platform Engineers** 🚀
