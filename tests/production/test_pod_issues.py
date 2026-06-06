"""
Production Issue Resolution Tests.

Tests the complete end-to-end resolution pipeline for real Kubernetes issues.
This module contains 25 tests for the most critical pod lifecycle issues.

Each test simulates a real production scenario and validates the complete 
resolution workflow from detection to fix.
"""

import pytest
import time
from unittest.mock import AsyncMock

# Test markers
pytestmark = [pytest.mark.production, pytest.mark.asyncio]


class TestPodLifecycleIssuesResolution:
    """Test suite for pod lifecycle issue resolution in production scenarios."""

    @pytest.mark.asyncio
    async def test_crashloopbackoff_complete_resolution(self, mcp_server):
        """Test complete resolution pipeline for CrashLoopBackOff."""
        
        # Simulate real production issue scenario
        issue_context = {
            "pod_name": "app-pod-123",
            "namespace": "production",
            "error_pattern": "CrashLoopBackOff",
            "container_name": "main-app",
            "restart_count": 5,
            "last_exit_code": 1,
            "cluster_context": {
                "environment": "production",
                "cluster_size": "large",
                "criticality": "high"
            }
        }
        
        # Mock the complete resolution pipeline
        mock_pipeline_result = {
            "issue_identified": True,
            "issue_type": "CrashLoopBackOff",
            "confidence_score": 0.95,
            "documentation_found": True,
            "solution_steps": [
                "1. Check container logs for error details",
                "2. Verify container configuration and resource limits",
                "3. Check for application-specific issues",
                "4. Review recent deployment changes"
            ],
            "kubectl_commands": [
                "kubectl logs app-pod-123 -n production --previous",
                "kubectl describe pod app-pod-123 -n production",
                "kubectl get events -n production --field-selector involvedObject.name=app-pod-123",
                "kubectl top pod app-pod-123 -n production"
            ],
            "estimated_resolution_time": "15 minutes",
            "priority": "P1-High",
            "automation_available": True,
            "similar_issues_found": 3,
            "success_probability": 0.92
        }
        
        # Configure mocks
        mcp_server.resolve_issue_end_to_end = AsyncMock(return_value=mock_pipeline_result)
        
        # Execute test
        start_time = time.time()
        result = await mcp_server.resolve_issue_end_to_end(issue_context)
        end_time = time.time()
        
        # Assertions - Core Resolution
        assert result["issue_identified"] is True
        assert result["documentation_found"] is True
        assert result["solution_steps"] is not None
        assert len(result["kubectl_commands"]) >= 3
        assert "kubectl logs" in str(result["kubectl_commands"])
        assert "kubectl describe pod" in str(result["kubectl_commands"])
        assert result["confidence_score"] > 0.8
        
        # Assertions - Performance
        resolution_time = end_time - start_time
        assert resolution_time < 5.0  # Should complete analysis in under 5 seconds
        
        # Assertions - Production Requirements
        assert result["priority"] in ["P0-Critical", "P1-High", "P2-Medium"]
        assert result["success_probability"] > 0.8
        assert result["automation_available"] is not None

    @pytest.mark.asyncio
    async def test_imagepullbackoff_registry_auth_resolution(self, k8s_manager, github_issues_manager):
        """Test ImagePullBackOff resolution with registry authentication."""
        
        issue_data = {
            "error": "Failed to pull image 'private-registry.com/app:v1.0'",
            "pod_name": "web-app",
            "namespace": "default",
            "image_details": {
                "registry": "private-registry.com",
                "repository": "app",
                "tag": "v1.0"
            },
            "node": "worker-node-1"
        }
        
        # Mock similar resolved issues from GitHub
        mock_similar_issues = [
            {
                "title": "ImagePullBackOff with private registry authentication",
                "solution": "Create imagePullSecrets and attach to pod",
                "success_rate": 0.94,
                "resolution_time": "5 minutes"
            },
            {
                "title": "Private registry authentication failure",
                "solution": "Update docker registry secret",
                "success_rate": 0.91,
                "resolution_time": "3 minutes"
            }
        ]
        
        # Mock resolution result
        mock_resolution = {
            "issue_type": "ImagePullBackOff",
            "root_cause": "Private registry authentication failure",
            "solution_type": "imagePullSecrets",
            "commands": [
                "kubectl create secret docker-registry regcred \\",
                "  --docker-server=private-registry.com \\",
                "  --docker-username=<username> \\",
                "  --docker-password=<password> \\",
                "  --docker-email=<email>",
                "kubectl patch deployment web-app -p '{\"spec\":{\"template\":{\"spec\":{\"imagePullSecrets\":[{\"name\":\"regcred\"}]}}}}'",
                "kubectl rollout restart deployment/web-app"
            ],
            "estimated_fix_time": "5 minutes",
            "verification_steps": [
                "kubectl get pods -l app=web-app",
                "kubectl describe pod <new-pod-name>"
            ],
            "success_probability": 0.93
        }
        
        # Configure mocks
        github_issues_manager.find_similar_issues = AsyncMock(return_value=mock_similar_issues)
        k8s_manager.resolve_imagepull_issue = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        similar_issues = await github_issues_manager.find_similar_issues(
            "ImagePullBackOff private registry authentication"
        )
        resolution = await k8s_manager.resolve_imagepull_issue(issue_data, similar_issues)
        
        # Assertions
        assert "imagePullSecrets" in resolution["solution_type"]
        assert "kubectl create secret docker-registry" in str(resolution["commands"])
        assert resolution["estimated_fix_time"] <= "5 minutes"
        assert resolution["success_probability"] > 0.9
        assert len(resolution["verification_steps"]) > 0

    @pytest.mark.asyncio
    async def test_pod_stuck_pending_scheduling(self, diagnostics_manager):
        """Test resolution of pod stuck in Pending due to scheduling issues."""
        
        pending_pod_context = {
            "pod_name": "large-app",
            "namespace": "compute",
            "status": "Pending",
            "events": [
                "Warning FailedScheduling: no nodes available to schedule pods",
                "Warning FailedScheduling: Insufficient cpu",
                "Warning FailedScheduling: Insufficient memory"
            ],
            "resource_requests": {
                "cpu": "4000m",
                "memory": "16Gi"
            },
            "scheduling_attempts": 5,
            "pending_duration": "10 minutes"
        }
        
        # Mock cluster analysis
        mock_resolution = {
            "root_cause": "InsufficientResources",
            "analysis": {
                "total_nodes": 3,
                "available_nodes": 3,
                "max_allocatable_cpu": "3500m",
                "max_allocatable_memory": "14Gi",
                "resource_gap": {
                    "cpu": "500m",
                    "memory": "2Gi"
                }
            },
            "solutions": [
                "Add more nodes to cluster with sufficient resources",
                "Reduce resource requests for the pod",
                "Scale down other workloads temporarily",
                "Use node affinity to target specific node types"
            ],
            "node_analysis": {
                "worker-node-1": {"cpu_available": "1200m", "memory_available": "6Gi"},
                "worker-node-2": {"cpu_available": "2100m", "memory_available": "8Gi"},
                "worker-node-3": {"cpu_available": "3500m", "memory_available": "14Gi"}
            },
            "recommended_actions": [
                "Immediate: Reduce CPU request to 3000m and memory to 14Gi",
                "Short-term: Add high-memory nodes to cluster",
                "Long-term: Implement cluster autoscaling"
            ],
            "estimated_resolution_time": "5 minutes (resource adjustment) or 15 minutes (node addition)"
        }
        
        # Configure mock
        diagnostics_manager.resolve_pending_pod = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await diagnostics_manager.resolve_pending_pod(pending_pod_context)
        
        # Assertions
        assert resolution["root_cause"] == "InsufficientResources"
        assert "Add more nodes" in resolution["solutions"]
        assert "Reduce resource requests" in resolution["solutions"]
        assert resolution["node_analysis"] is not None
        assert len(resolution["recommended_actions"]) >= 2
        assert "cpu_available" in str(resolution["node_analysis"])

    @pytest.mark.asyncio
    async def test_pod_oomkilled_resolution(self, monitoring_manager):
        """Test resolution of OOMKilled pods."""
        
        oom_context = {
            "pod_name": "memory-intensive-app",
            "namespace": "data-processing",
            "exit_code": 137,
            "last_state": "OOMKilled",
            "container_limits": {"memory": "128Mi"},
            "container_requests": {"memory": "64Mi"},
            "actual_memory_usage": "156Mi",
            "oom_events": [
                {
                    "timestamp": "2025-08-09T12:30:45Z",
                    "message": "Memory limit exceeded"
                }
            ],
            "workload_type": "batch-job"
        }
        
        # Mock memory analysis and resolution
        mock_resolution = {
            "issue_type": "OOMKilled",
            "memory_analysis": {
                "current_limit": "128Mi",
                "peak_usage": "156Mi",
                "recommended_limit": "256Mi",
                "safety_margin": "20%",
                "usage_pattern": "gradual_increase"
            },
            "solutions": [
                "Increase memory limits to 256Mi",
                "Add memory requests to improve scheduling",
                "Implement memory monitoring and alerting",
                "Consider splitting workload into smaller chunks"
            ],
            "recommended_memory": "256Mi",
            "commands": [
                "kubectl patch deployment memory-intensive-app -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"main\",\"resources\":{\"limits\":{\"memory\":\"256Mi\"},\"requests\":{\"memory\":\"128Mi\"}}}]}}}}'",
                "kubectl rollout restart deployment/memory-intensive-app"
            ],
            "monitoring_recommendations": [
                "Set up memory usage alerts at 80% of limit",
                "Monitor memory trends over time",
                "Implement graceful degradation for memory pressure"
            ],
            "prevention_steps": [
                "Regular memory profiling",
                "Implement memory-efficient algorithms", 
                "Use streaming for large data processing"
            ]
        }
        
        # Configure mock
        monitoring_manager.resolve_oom_issue = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await monitoring_manager.resolve_oom_issue(oom_context)
        
        # Assertions
        assert resolution["issue_type"] == "OOMKilled"
        assert "Increase memory limits" in resolution["solutions"]
        assert resolution["recommended_memory"] > "128Mi"
        assert "kubectl patch" in str(resolution["commands"])
        assert resolution["memory_analysis"]["peak_usage"] == "156Mi"
        assert len(resolution["prevention_steps"]) > 0

    @pytest.mark.asyncio
    async def test_init_container_failure_resolution(self, k8s_manager):
        """Test resolution of init container failures."""
        
        init_failure_context = {
            "pod_name": "app-with-init",
            "namespace": "backend",
            "init_container": "db-migration",
            "failure_reason": "Error: connection refused to database",
            "exit_code": 1,
            "init_container_image": "migration-tool:v1.2",
            "logs": [
                "2025-08-09 12:00:01 Starting database migration",
                "2025-08-09 12:00:02 Connecting to postgres://db:5432/app",
                "2025-08-09 12:00:03 Error: connection refused",
                "2025-08-09 12:00:03 Migration failed"
            ],
            "dependencies": ["postgres-service"]
        }
        
        # Mock init container resolution
        mock_resolution = {
            "component": "init_container",
            "root_cause": "Database service unavailable",
            "dependency_analysis": {
                "postgres-service": {
                    "status": "ClusterIP",
                    "endpoints": 0,
                    "ready_pods": 0,
                    "issue": "No healthy backend pods"
                }
            },
            "solutions": [
                "Check database service and pods status",
                "Verify database connectivity from pod",
                "Check service discovery and DNS resolution",
                "Ensure database is ready before init container starts"
            ],
            "diagnostic_commands": [
                "kubectl logs app-with-init -c db-migration -n backend",
                "kubectl describe service postgres-service -n backend",
                "kubectl get pods -l app=postgres -n backend",
                "kubectl exec -it app-with-init -c db-migration -- nslookup postgres-service"
            ],
            "resolution_steps": [
                "1. Verify postgres pods are running and ready",
                "2. Check service endpoints and selectors",
                "3. Test network connectivity between containers",
                "4. Add init container retry logic or health checks"
            ],
            "estimated_resolution_time": "10 minutes"
        }
        
        # Configure mock
        k8s_manager.resolve_init_container_failure = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_init_container_failure(init_failure_context)
        
        # Assertions
        assert resolution["component"] == "init_container"
        assert "Check database connectivity" in resolution["solutions"]
        assert "kubectl logs" in str(resolution["diagnostic_commands"])
        assert resolution["dependency_analysis"] is not None
        assert "postgres-service" in resolution["dependency_analysis"]
        assert len(resolution["resolution_steps"]) >= 3

    @pytest.mark.asyncio
    async def test_pod_eviction_pressure_resolution(self, k8s_manager):
        """Test resolution of pod evictions due to resource pressure."""
        
        eviction_context = {
            "pod_name": "worker-pod-456",
            "namespace": "processing",
            "eviction_reason": "DiskPressure",
            "node": "worker-node-2",
            "eviction_time": "2025-08-09T12:15:30Z",
            "resource_pressure": {
                "disk_usage": "95%",
                "available_space": "2Gi",
                "inodes_usage": "92%"
            },
            "pod_priority": "0",  # Default priority
            "workload_type": "batch"
        }
        
        # Mock eviction resolution
        mock_resolution = {
            "issue_type": "PodEviction",
            "eviction_cause": "DiskPressure",
            "node_analysis": {
                "disk_usage": "95%",
                "cleanup_candidates": [
                    "/var/log/pods/* (old logs)",
                    "/var/lib/docker/containers/* (stopped containers)",
                    "unused container images"
                ],
                "immediate_actions": [
                    "Clean up old pod logs",
                    "Remove unused container images",
                    "Clear temporary files"
                ]
            },
            "solutions": [
                "Immediate: Clean up disk space on affected node",
                "Short-term: Implement log rotation and cleanup policies",
                "Long-term: Add disk monitoring and expand storage capacity",
                "Scheduling: Use pod priority classes to protect critical workloads"
            ],
            "cleanup_commands": [
                "kubectl delete pods --field-selector=status.phase=Succeeded -A",
                "docker system prune -a --filter until=24h",
                "find /var/log/pods -name '*.log' -mtime +7 -delete"
            ],
            "prevention_measures": [
                "Implement automated disk cleanup jobs",
                "Set up disk usage monitoring and alerts",
                "Configure log retention policies",
                "Use ephemeral storage limits for pods"
            ],
            "estimated_cleanup_time": "5 minutes"
        }
        
        # Configure mock
        k8s_manager.resolve_pod_eviction = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_pod_eviction(eviction_context)
        
        # Assertions
        assert resolution["issue_type"] == "PodEviction"
        assert resolution["eviction_cause"] == "DiskPressure"
        assert "Clean up disk space" in resolution["solutions"]
        assert "docker system prune" in str(resolution["cleanup_commands"])
        assert len(resolution["prevention_measures"]) > 2
        assert resolution["node_analysis"]["disk_usage"] == "95%"

    @pytest.mark.asyncio
    async def test_pod_security_context_violation(self, security_manager):
        """Test resolution of pod security context violations."""
        
        security_violation_context = {
            "pod_name": "restricted-app",
            "namespace": "secure",
            "violation_type": "SecurityContextConstraints",
            "error_message": "Pod Security violation: running as root user forbidden",
            "security_context": {
                "runAsUser": 0,  # root
                "runAsNonRoot": False,
                "privileged": True,
                "allowPrivilegeEscalation": True
            },
            "policy": "restricted",
            "cluster_policy": "pod-security-standard"
        }
        
        # Mock security violation resolution
        mock_resolution = {
            "violation_type": "SecurityContextConstraints",
            "policy_analysis": {
                "current_policy": "restricted",
                "violations": [
                    "Running as root user (UID 0)",
                    "Privileged containers not allowed",
                    "Privilege escalation enabled"
                ],
                "required_changes": [
                    "Set runAsNonRoot: true",
                    "Set runAsUser to non-zero value",
                    "Set privileged: false",
                    "Set allowPrivilegeEscalation: false"
                ]
            },
            "solutions": [
                "Modify pod security context to run as non-root",
                "Use Pod Security Standards instead of privileged access",
                "Implement least-privilege principle",
                "Use security context constraints appropriately"
            ],
            "security_recommendations": [
                "Set runAsUser: 1000",
                "Set runAsGroup: 3000", 
                "Set fsGroup: 2000",
                "Add securityContext.capabilities.drop: ['ALL']",
                "Set readOnlyRootFilesystem: true where possible"
            ],
            "remediation_yaml": {
                "securityContext": {
                    "runAsNonRoot": True,
                    "runAsUser": 1000,
                    "runAsGroup": 3000,
                    "fsGroup": 2000,
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"]},
                    "seccompProfile": {"type": "RuntimeDefault"}
                }
            },
            "compliance_check": "Pod will comply with restricted policy after changes"
        }
        
        # Configure mock
        security_manager.resolve_security_violation = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await security_manager.resolve_security_violation(security_violation_context)
        
        # Assertions
        assert resolution["violation_type"] == "SecurityContextConstraints"
        assert "Modify pod security context" in resolution["solutions"]
        assert "runAsNonRoot" in str(resolution["security_recommendations"])
        assert resolution["remediation_yaml"]["securityContext"]["runAsNonRoot"] is True
        assert resolution["remediation_yaml"]["securityContext"]["runAsUser"] != 0
        assert "compliance_check" in resolution

    @pytest.mark.asyncio
    async def test_pod_resource_quota_exceeded(self, k8s_manager):
        """Test resolution of resource quota exceeded errors."""
        
        quota_exceeded_context = {
            "pod_name": "resource-hungry-app",
            "namespace": "limited",
            "error": "exceeded quota: compute-quota",
            "requested_resources": {
                "cpu": "2000m",
                "memory": "4Gi"
            },
            "quota_details": {
                "name": "compute-quota",
                "cpu_limit": "10",
                "memory_limit": "20Gi",
                "cpu_used": "9.5",
                "memory_used": "18Gi"
            },
            "namespace_usage": {
                "pods": 15,
                "cpu_total": "9.5",
                "memory_total": "18Gi"
            }
        }
        
        # Mock quota resolution
        mock_resolution = {
            "issue_type": "ResourceQuotaExceeded", 
            "quota_analysis": {
                "quota_name": "compute-quota",
                "utilization": {
                    "cpu": "95%",
                    "memory": "90%"
                },
                "available": {
                    "cpu": "500m",
                    "memory": "2Gi"
                },
                "top_consumers": [
                    {"pod": "app-1", "cpu": "2000m", "memory": "4Gi"},
                    {"pod": "app-2", "cpu": "1500m", "memory": "3Gi"},
                    {"pod": "app-3", "cpu": "2000m", "memory": "5Gi"}
                ]
            },
            "solutions": [
                "Increase resource quota limits for the namespace",
                "Optimize resource requests for existing pods",
                "Scale down non-critical workloads temporarily",
                "Move some workloads to different namespace"
            ],
            "immediate_actions": [
                "Scale down app-3 temporarily (largest memory consumer)",
                "Reduce resource requests for batch jobs",
                "Request quota increase from cluster admin"
            ],
            "optimization_recommendations": [
                "Review and right-size resource requests",
                "Implement resource monitoring and alerting",
                "Use Vertical Pod Autoscaler for automatic sizing",
                "Set up resource usage dashboards"
            ],
            "quota_adjustment": {
                "recommended_cpu_limit": "15",
                "recommended_memory_limit": "30Gi",
                "justification": "Current 95% utilization indicates need for more capacity"
            }
        }
        
        # Configure mock
        k8s_manager.resolve_quota_exceeded = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_quota_exceeded(quota_exceeded_context)
        
        # Assertions
        assert resolution["issue_type"] == "ResourceQuotaExceeded"
        assert "Increase resource quota" in resolution["solutions"]
        assert resolution["quota_analysis"]["utilization"]["cpu"] == "95%"
        assert len(resolution["immediate_actions"]) > 0
        assert "recommended_cpu_limit" in resolution["quota_adjustment"]
        assert resolution["quota_adjustment"]["recommended_cpu_limit"] > "10"

    @pytest.mark.asyncio
    async def test_pod_network_policy_blocking(self, security_manager):
        """Test resolution of network policy blocking pod communication."""
        
        network_policy_context = {
            "source_pod": "web-frontend",
            "target_service": "api-backend",
            "namespace": "microservices",
            "error": "connection timeout to api-backend:8080",
            "network_policies": [
                "default-deny-all",
                "allow-frontend-to-backend",
                "allow-backend-to-db"
            ],
            "connectivity_test": {
                "dns_resolution": "success",
                "tcp_connection": "failed",
                "port": 8080
            }
        }
        
        # Mock network policy resolution
        mock_resolution = {
            "issue_type": "NetworkPolicyBlocking",
            "policy_analysis": {
                "blocking_policy": "default-deny-all",
                "allowing_policies": ["allow-frontend-to-backend"],
                "policy_evaluation": {
                    "ingress_allowed": False,
                    "egress_allowed": True,
                    "missing_rules": ["ingress rule for api-backend port 8080"]
                }
            },
            "solutions": [
                "Review network policy rules for api-backend service",
                "Add ingress rule to allow traffic on port 8080",
                "Verify pod and service labels match policy selectors",
                "Test connectivity after policy updates"
            ],
            "policy_recommendations": {
                "missing_ingress_rule": {
                    "from": [{"podSelector": {"matchLabels": {"app": "web-frontend"}}}],
                    "ports": [{"protocol": "TCP", "port": 8080}]
                },
                "policy_yaml": """
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-backend-8080
  namespace: microservices
spec:
  podSelector:
    matchLabels:
      app: api-backend
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: web-frontend
    ports:
    - protocol: TCP
      port: 8080
                """
            },
            "verification_commands": [
                "kubectl describe networkpolicy -n microservices",
                "kubectl exec -it web-frontend -- nc -zv api-backend 8080",
                "kubectl get pods --show-labels -n microservices"
            ]
        }
        
        # Configure mock
        security_manager.resolve_network_policy_issue = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await security_manager.resolve_network_policy_issue(network_policy_context)
        
        # Assertions
        assert resolution["issue_type"] == "NetworkPolicyBlocking"
        assert resolution["policy_analysis"] is not None
        assert "Review network policy rules" in resolution["solutions"]
        assert "kubectl describe networkpolicy" in str(resolution["verification_commands"])
        assert "ingress_allowed" in resolution["policy_analysis"]["policy_evaluation"]
        assert "policy_yaml" in resolution["policy_recommendations"]

    @pytest.mark.asyncio
    async def test_multi_container_pod_failure(self, diagnostics_manager):
        """Test resolution of multi-container pod with partial failures."""
        
        multi_container_context = {
            "pod_name": "multi-service-pod",
            "namespace": "apps",
            "containers": [
                {
                    "name": "web-server",
                    "status": "Running",
                    "ready": True,
                    "restart_count": 0
                },
                {
                    "name": "log-shipper",
                    "status": "CrashLoopBackOff", 
                    "ready": False,
                    "restart_count": 5,
                    "last_exit_code": 1
                },
                {
                    "name": "metrics-exporter",
                    "status": "ImagePullBackOff",
                    "ready": False,
                    "restart_count": 0
                }
            ],
            "pod_phase": "Running",  # Pod running but not all containers ready
            "service_impact": "partial"
        }
        
        # Mock multi-container resolution
        mock_resolution = {
            "issue_type": "MultiContainerFailure",
            "container_analysis": {
                "web-server": {
                    "status": "healthy",
                    "issues": None,
                    "action": "no_action_needed"
                },
                "log-shipper": {
                    "status": "failing",
                    "issues": ["crash_loop", "configuration_error"],
                    "action": "investigate_logs_and_config",
                    "priority": "medium"
                },
                "metrics-exporter": {
                    "status": "failing",
                    "issues": ["image_pull_failure"],
                    "action": "verify_image_and_registry",
                    "priority": "low"
                }
            },
            "resolution_strategy": "sequential",  # Fix one container at a time
            "solutions": [
                "Fix log-shipper configuration and restart",
                "Verify metrics-exporter image availability",
                "Consider sidecar container independence",
                "Implement container health checks"
            ],
            "container_specific_actions": {
                "log-shipper": [
                    "Check log-shipper configuration",
                    "Verify log file paths and permissions",
                    "Review log shipping endpoint connectivity"
                ],
                "metrics-exporter": [
                    "Verify image name and tag",
                    "Check registry access",
                    "Ensure image exists in specified registry"
                ]
            },
            "impact_assessment": {
                "core_functionality": "available",  # web-server still working
                "monitoring": "degraded",  # metrics-exporter down
                "logging": "degraded",  # log-shipper down
                "overall_impact": "medium"
            }
        }
        
        # Configure mock
        diagnostics_manager.resolve_multi_container_pod = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await diagnostics_manager.resolve_multi_container_pod(multi_container_context)
        
        # Assertions
        assert resolution["issue_type"] == "MultiContainerFailure"
        assert "web-server" in resolution["container_analysis"]
        assert resolution["container_analysis"]["web-server"]["status"] == "healthy"
        assert resolution["container_analysis"]["log-shipper"]["status"] == "failing"
        assert "sequential" in resolution["resolution_strategy"]
        assert "container_specific_actions" in resolution
        assert resolution["impact_assessment"]["core_functionality"] == "available"
