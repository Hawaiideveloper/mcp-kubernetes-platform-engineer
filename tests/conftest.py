"""
Test fixtures and utilities for Kubernetes Platform Engineer MCP Server tests.

This module provides shared fixtures, mock data, and utility functions
used across all test categories.
"""

import os
import time
from typing import Dict, List, Any
from unittest.mock import Mock

import pytest
import pytest_asyncio
from faker import Faker

# Import our modules
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import ServerConfig, KubernetesConfig, DiagnosticsConfig, MonitoringConfig, SecurityConfig
from k8s_manager import KubernetesManager
from diagnostics_manager import DiagnosticsManager
from monitoring_manager import MonitoringManager
from security_manager import SecurityManager
from documentation_manager import DocumentationManager
from github_issues_manager import GitHubIssuesManager
from mcp_server import KubernetesPlatformEngineerMCPServer

fake = Faker()

# ==========================================
# CONFIGURATION FIXTURES
# ==========================================

@pytest.fixture
def server_config():
    """Provide test server configuration."""
    return ServerConfig(
        name="test-kubernetes-platform-engineer",
        version="1.0.0-test",
        debug=True,
        log_level="DEBUG"
    )

@pytest.fixture
def k8s_config():
    """Provide test Kubernetes configuration."""
    return KubernetesConfig(
        kubeconfig_path="~/.kube/config",
        context_name="test-context",
        namespace="test"
    )

@pytest.fixture
def diagnostics_config():
    """Provide test diagnostics configuration."""
    return DiagnosticsConfig(
        timeout=30,
        max_retries=3,
        enable_network_tests=True
    )

@pytest.fixture
def monitoring_config():
    """Provide test monitoring configuration."""
    return MonitoringConfig(
        metrics_retention="1h",
        scrape_interval=10,
        enable_alerts=True
    )

@pytest.fixture
def security_config():
    """Provide test security configuration."""
    return SecurityConfig(
        enable_rbac_checks=True,
        scan_timeout=60,
        vulnerability_threshold="medium"
    )

# ==========================================
# MANAGER FIXTURES
# ==========================================

@pytest_asyncio.fixture
async def k8s_manager(k8s_config):
    """Provide a test Kubernetes manager."""
    manager = KubernetesManager(k8s_config)
    # Mock the initialization to avoid requiring real cluster
    manager.client = Mock()
    manager.v1 = Mock()
    manager.apps_v1 = Mock()
    manager.storage_v1 = Mock()
    return manager

@pytest_asyncio.fixture
async def diagnostics_manager(diagnostics_config):
    """Provide a test diagnostics manager."""
    manager = DiagnosticsManager(diagnostics_config)
    manager.k8s_client = Mock()
    return manager

@pytest_asyncio.fixture
async def monitoring_manager(monitoring_config):
    """Provide a test monitoring manager."""
    manager = MonitoringManager(monitoring_config)
    manager.prometheus_client = Mock()
    return manager

@pytest_asyncio.fixture
async def security_manager(security_config):
    """Provide a test security manager."""
    manager = SecurityManager(security_config)
    manager.k8s_client = Mock()
    return manager

@pytest_asyncio.fixture
async def documentation_manager(server_config):
    """Provide a test documentation manager."""
    manager = DocumentationManager(server_config)
    # Pre-load test documentation
    manager.documentation_db = generate_test_documentation()
    return manager

@pytest_asyncio.fixture
async def github_issues_manager(server_config):
    """Provide a test GitHub issues manager."""
    manager = GitHubIssuesManager(server_config)
    # Use in-memory database for testing
    manager.db_path = ":memory:"
    await manager.initialize_database()
    # Pre-populate with test issues
    await populate_test_issues(manager)
    return manager

@pytest_asyncio.fixture
async def mcp_server(server_config):
    """Provide a test MCP server with all managers."""
    server = KubernetesPlatformEngineerMCPServer(server_config)
    # Mock all managers
    server.k8s_manager = Mock()
    server.diagnostics_manager = Mock()
    server.monitoring_manager = Mock()
    server.security_manager = Mock()
    server.documentation_manager = Mock()
    server.github_issues_manager = Mock()
    return server

# ==========================================
# MOCK DATA GENERATORS
# ==========================================

def generate_test_pod_data(count: int = 10) -> List[Dict[str, Any]]:
    """Generate test pod data."""
    pods = []
    statuses = ["Running", "Pending", "Failed", "CrashLoopBackOff", "ImagePullBackOff"]
    
    for i in range(count):
        pod = {
            "metadata": {
                "name": f"test-pod-{i}",
                "namespace": fake.random_element(["default", "production", "staging"]),
                "labels": {"app": f"test-app-{i % 3}"},
                "creationTimestamp": fake.date_time_this_month().isoformat() + "Z"
            },
            "spec": {
                "containers": [{
                    "name": "main",
                    "image": f"nginx:{fake.random_element(['1.20', '1.21', 'latest'])}",
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                        "limits": {"cpu": "200m", "memory": "256Mi"}
                    }
                }],
                "nodeName": f"worker-node-{i % 3 + 1}"
            },
            "status": {
                "phase": fake.random_element(statuses),
                "containerStatuses": [{
                    "name": "main",
                    "ready": fake.boolean(chance_of_getting_true=80),
                    "restartCount": fake.random_int(0, 5),
                    "state": {"running": {"startedAt": fake.date_time_this_hour().isoformat() + "Z"}}
                }]
            }
        }
        pods.append(pod)
    
    return pods

def generate_test_node_data(count: int = 5) -> List[Dict[str, Any]]:
    """Generate test node data."""
    nodes = []
    
    for i in range(count):
        node = {
            "metadata": {
                "name": f"worker-node-{i + 1}",
                "labels": {
                    "kubernetes.io/arch": "amd64",
                    "kubernetes.io/os": "linux",
                    "node-role.kubernetes.io/worker": "",
                    "topology.kubernetes.io/zone": f"us-west-1{chr(97 + i % 3)}"  # a, b, c
                }
            },
            "spec": {
                "podCIDR": f"10.244.{i}.0/24"
            },
            "status": {
                "conditions": [
                    {
                        "type": "Ready",
                        "status": "True" if fake.boolean(chance_of_getting_true=90) else "False",
                        "lastHeartbeatTime": fake.date_time_this_hour().isoformat() + "Z",
                        "reason": "KubeletReady"
                    }
                ],
                "capacity": {
                    "cpu": f"{fake.random_int(2, 16)}",
                    "memory": f"{fake.random_int(4, 32)}Gi",
                    "pods": "110"
                },
                "allocatable": {
                    "cpu": f"{fake.random_int(1, 15)}",
                    "memory": f"{fake.random_int(3, 30)}Gi",
                    "pods": "110"
                },
                "nodeInfo": {
                    "kubeletVersion": "v1.28.2",
                    "osImage": "Ubuntu 22.04.3 LTS",
                    "containerRuntimeVersion": "containerd://1.7.2"
                }
            }
        }
        nodes.append(node)
    
    return nodes

def generate_test_events(count: int = 20) -> List[Dict[str, Any]]:
    """Generate test Kubernetes events."""
    events = []
    event_types = ["Normal", "Warning"]
    reasons = [
        "Created", "Started", "Pulled", "Killing",
        "FailedScheduling", "FailedMount", "Unhealthy",
        "BackOff", "FailedCreatePodSandBox"
    ]
    
    for i in range(count):
        event = {
            "metadata": {
                "name": f"test-event-{i}",
                "namespace": fake.random_element(["default", "production", "staging"])
            },
            "type": fake.random_element(event_types),
            "reason": fake.random_element(reasons),
            "message": fake.sentence(),
            "firstTimestamp": fake.date_time_this_hour().isoformat() + "Z",
            "lastTimestamp": fake.date_time_this_hour().isoformat() + "Z",
            "count": fake.random_int(1, 10),
            "involvedObject": {
                "kind": "Pod",
                "name": f"test-pod-{i % 10}",
                "namespace": fake.random_element(["default", "production", "staging"])
            }
        }
        events.append(event)
    
    return events

def generate_test_documentation() -> Dict[str, Any]:
    """Generate test documentation database."""
    docs = {}
    
    # Pod troubleshooting docs
    docs["pod_troubleshooting"] = {
        "title": "Troubleshooting Pods",
        "url": "https://kubernetes.io/docs/tasks/debug/debug-pod-replication-controller/",
        "sections": [
            {
                "title": "CrashLoopBackOff",
                "content": [
                    "Check container logs with kubectl logs",
                    "Verify container configuration",
                    "Check resource limits and requests"
                ]
            },
            {
                "title": "ImagePullBackOff", 
                "content": [
                    "Verify image name and tag",
                    "Check registry authentication",
                    "Ensure image exists in registry"
                ]
            }
        ],
        "tags": ["pods", "troubleshooting", "debugging"],
        "commands": [
            {"command": "kubectl logs <pod-name>", "type": "kubectl", "description": "View pod logs"},
            {"command": "kubectl describe pod <pod-name>", "type": "kubectl", "description": "Get pod details"},
            {"command": "kubectl get events", "type": "kubectl", "description": "View cluster events"}
        ]
    }
    
    # Network troubleshooting docs
    docs["network_troubleshooting"] = {
        "title": "Troubleshooting Network Issues",
        "url": "https://kubernetes.io/docs/tasks/debug/debug-cluster/",
        "sections": [
            {
                "title": "Service Connectivity",
                "content": [
                    "Check service endpoints",
                    "Verify network policies",
                    "Test DNS resolution"
                ]
            }
        ],
        "tags": ["networking", "services", "dns"],
        "commands": [
            {"command": "kubectl get endpoints", "type": "kubectl", "description": "List service endpoints"},
            {"command": "kubectl exec -it <pod> -- nslookup <service>", "type": "kubectl", "description": "Test DNS resolution"}
        ]
    }
    
    # Storage troubleshooting docs
    docs["storage_troubleshooting"] = {
        "title": "Troubleshooting Storage Issues",
        "url": "https://kubernetes.io/docs/concepts/storage/",
        "sections": [
            {
                "title": "PVC Pending",
                "content": [
                    "Check StorageClass availability",
                    "Verify CSI driver status",
                    "Check node storage capacity"
                ]
            }
        ],
        "tags": ["storage", "pvc", "volumes"],
        "commands": [
            {"command": "kubectl describe pvc <pvc-name>", "type": "kubectl", "description": "Get PVC details"},
            {"command": "kubectl get storageclass", "type": "kubectl", "description": "List storage classes"}
        ]
    }
    
    return docs

async def populate_test_issues(manager: GitHubIssuesManager, count: int = 100):
    """Populate GitHub issues manager with test issues."""
    issue_types = [
        "CrashLoopBackOff", "ImagePullBackOff", "NodeNotReady", 
        "DNSFailure", "PVCPending", "RBACDenied", "ResourceExhaustion",
        "SchedulingFailure", "APIServerTimeout", "CertificateExpired"
    ]
    
    components = [
        "pod", "node", "networking", "storage", "security", 
        "scheduler", "control-plane", "kubelet"
    ]
    
    states = ["open", "closed"]
    
    for i in range(count):
        issue_type = fake.random_element(issue_types)
        component = fake.random_element(components)
        
        issue = {
            "id": i + 1,
            "number": i + 1000,
            "title": f"{issue_type}: {fake.sentence()}",
            "body": fake.paragraph(),
            "state": fake.random_element(states),
            "labels": [
                {"name": "kind/bug"},
                {"name": f"sig/{component}"},
                {"name": f"priority/{fake.random_element(['low', 'medium', 'high'])}"}
            ],
            "created_at": fake.date_time_this_year().isoformat() + "Z",
            "closed_at": fake.date_time_this_month().isoformat() + "Z" if fake.boolean() else None,
            "user": {"login": fake.user_name()},
            "assignees": [{"login": fake.user_name()}] if fake.boolean() else [],
            "comments": fake.random_int(0, 20)
        }
        
        await manager.store_issue("kubernetes/kubernetes", issue)

# ==========================================
# MOCK KUBERNETES CLIENT
# ==========================================

class MockKubernetesClient:
    """Mock Kubernetes client for testing."""
    
    def __init__(self):
        self.pods = generate_test_pod_data()
        self.nodes = generate_test_node_data()
        self.events = generate_test_events()
        self.namespaces = ["default", "kube-system", "production", "staging"]
    
    def list_pod_for_all_namespaces(self, **kwargs):
        """Mock list all pods."""
        result = Mock()
        result.items = [Mock(**pod) for pod in self.pods]
        return result
    
    def list_node(self, **kwargs):
        """Mock list nodes.""" 
        result = Mock()
        result.items = [Mock(**node) for node in self.nodes]
        return result
    
    def list_event_for_all_namespaces(self, **kwargs):
        """Mock list events."""
        result = Mock()
        result.items = [Mock(**event) for event in self.events]
        return result
    
    def read_pod(self, name, namespace, **kwargs):
        """Mock read specific pod."""
        for pod in self.pods:
            if pod["metadata"]["name"] == name and pod["metadata"]["namespace"] == namespace:
                return Mock(**pod)
        raise Exception(f"Pod {name} not found in namespace {namespace}")

# ==========================================
# PERFORMANCE TEST UTILITIES
# ==========================================

@pytest.fixture
def performance_monitor():
    """Monitor for performance tests."""
    import psutil
    
    class PerformanceMonitor:
        def __init__(self):
            self.process = psutil.Process()
            self.start_time = None
            self.start_memory = None
            self.start_cpu = None
        
        def start(self):
            self.start_time = time.time()
            self.start_memory = self.process.memory_info().rss
            self.start_cpu = self.process.cpu_percent()
        
        def stop(self):
            end_time = time.time()
            end_memory = self.process.memory_info().rss
            end_cpu = self.process.cpu_percent()
            
            return {
                "duration": end_time - self.start_time,
                "memory_delta": end_memory - self.start_memory,
                "cpu_usage": end_cpu
            }
    
    return PerformanceMonitor()

# ==========================================
# CLEANUP UTILITIES
# ==========================================

@pytest.fixture(scope="function", autouse=True)
def cleanup_test_environment():
    """Clean up test environment after each test."""
    yield
    # Cleanup code here if needed
    pass

# ==========================================
# ASYNC TEST UTILITIES
# ==========================================

@pytest_asyncio.fixture
async def async_test_timeout():
    """Provide timeout for async tests."""
    return 30  # 30 seconds

def async_test(timeout: int = 30):
    """Decorator for async tests with timeout."""
    def decorator(func):
        @pytest.mark.asyncio
        @pytest.mark.timeout(timeout)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# ==========================================
# TEST DATA CONSTANTS
# ==========================================

SAMPLE_CLUSTER_INFO = {
    "cluster_name": "test-cluster",
    "version": "v1.28.2",
    "nodes": {"total": 5, "ready": 5},
    "pods": {"total": 50, "running": 45, "pending": 3, "failed": 2},
    "namespaces": ["default", "kube-system", "production", "staging"]
}

SAMPLE_ISSUE_PATTERNS = [
    "Pod app-web-123 is in CrashLoopBackOff state",
    "Failed to pull image nginx:latest",
    "Node worker-1 status shows NotReady", 
    "Pod cannot resolve service names",
    "PersistentVolumeClaim remains in Pending state",
    "User cannot perform action due to RBAC",
    "Node running out of memory",
    "Pod stuck in Pending state - no suitable node",
    "kubectl timeout connecting to API server",
    "TLS certificate expired"
]

EXPECTED_SOLUTIONS = {
    "CrashLoopBackOff": [
        "Check container logs with kubectl logs",
        "Verify container configuration",
        "Check resource limits"
    ],
    "ImagePullBackOff": [
        "Check image name and registry access",
        "Verify registry authentication",
        "Check imagePullSecrets"
    ],
    "NodeNotReady": [
        "Check kubelet service status",
        "Verify node resources",
        "Check network connectivity"
    ]
}
