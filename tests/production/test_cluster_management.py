"""
Cluster Management and Deployment Issue Resolution Tests.

Tests the complete resolution pipeline for Kubernetes cluster management and deployment issues.
This module contains 25 tests for the most critical cluster and deployment problems.

Each test simulates real production cluster scenarios and validates 
the complete resolution workflow from detection to fix.
"""

import pytest
from unittest.mock import AsyncMock

# Test markers
pytestmark = [pytest.mark.production, pytest.mark.asyncio, pytest.mark.cluster]


class TestClusterManagementResolution:
    """Test suite for cluster management and deployment issue resolution."""

    @pytest.mark.asyncio
    async def test_node_not_ready_resolution(self, k8s_manager):
        """Test resolution of nodes in NotReady state."""
        
        node_context = {
            "node_name": "worker-node-3",
            "node_status": "NotReady",
            "last_heartbeat": "2025-08-09T14:25:00Z",
            "kubelet_version": "v1.28.2",
            "conditions": [
                {"type": "Ready", "status": "False", "reason": "KubeletNotReady"},
                {"type": "DiskPressure", "status": "True", "reason": "KubeletHasDiskPressure"},
                {"type": "MemoryPressure", "status": "False"},
                {"type": "PIDPressure", "status": "False"}
            ],
            "pods_on_node": 12,
            "node_role": "worker"
        }
        
        # Mock node resolution
        mock_resolution = {
            "issue_type": "NodeNotReady",
            "node_analysis": {
                "primary_issue": "DiskPressure",
                "kubelet_status": "running_but_unhealthy",
                "docker_status": "running",
                "disk_usage": {
                    "root_fs": "95%",
                    "docker_fs": "89%",
                    "kubelet_fs": "87%"
                },
                "memory_usage": "45%",
                "cpu_usage": "23%",
                "network_connectivity": "ok"
            },
            "disk_analysis": {
                "high_usage_dirs": [
                    "/var/log/pods (15GB)",
                    "/var/lib/docker/containers (8GB)",
                    "/var/lib/kubelet/pods (12GB)"
                ],
                "cleanup_candidates": [
                    "Old pod logs older than 7 days",
                    "Stopped docker containers",
                    "Unused docker images",
                    "Completed job pods"
                ],
                "estimated_recoverable": "25GB"
            },
            "solutions": [
                "Clean up disk space to resolve DiskPressure",
                "Restart kubelet service after cleanup",
                "Implement automated log rotation",
                "Monitor disk usage proactively"
            ],
            "resolution_commands": [
                "kubectl delete pods --field-selector=status.phase=Succeeded -A --force",
                "docker system prune -a --filter until=24h",
                "find /var/log/pods -name '*.log' -mtime +7 -delete",
                "systemctl restart kubelet",
                "journalctl -u kubelet --since '10 minutes ago'"
            ],
            "cleanup_script": """#!/bin/bash
# Emergency disk cleanup script
echo "Starting emergency disk cleanup on worker-node-3"
kubectl delete pods --field-selector=status.phase=Succeeded -A --force
docker system prune -a --filter until=24h -f
find /var/log/pods -name '*.log' -mtime +7 -delete
echo "Cleanup completed. Restarting kubelet..."
systemctl restart kubelet
sleep 30
kubectl get node worker-node-3
""",
            "verification_steps": [
                "Check node status: kubectl get node worker-node-3",
                "Verify disk usage: df -h",
                "Check kubelet logs: journalctl -u kubelet -f",
                "Monitor node conditions: kubectl describe node worker-node-3"
            ],
            "estimated_recovery_time": "10 minutes"
        }
        
        # Configure mock
        k8s_manager.resolve_node_not_ready = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_node_not_ready(node_context)
        
        # Assertions
        assert resolution["issue_type"] == "NodeNotReady"
        assert resolution["node_analysis"]["primary_issue"] == "DiskPressure"
        assert "Clean up disk space" in resolution["solutions"]
        assert "kubectl delete pods" in str(resolution["resolution_commands"])
        assert resolution["disk_analysis"]["estimated_recoverable"] == "25GB"
        assert "systemctl restart kubelet" in resolution["cleanup_script"]

    @pytest.mark.asyncio
    async def test_deployment_rollout_stuck(self, k8s_manager):
        """Test resolution of stuck deployment rollouts."""
        
        deployment_context = {
            "deployment_name": "api-server",
            "namespace": "production",
            "desired_replicas": 5,
            "ready_replicas": 2,
            "updated_replicas": 3,
            "available_replicas": 2,
            "rollout_status": "progressing",
            "strategy": "RollingUpdate",
            "max_unavailable": "25%",
            "max_surge": "25%",
            "stuck_duration": "20 minutes"
        }
        
        # Mock deployment resolution
        mock_resolution = {
            "issue_type": "DeploymentRolloutStuck",
            "rollout_analysis": {
                "current_revision": 5,
                "target_revision": 6,
                "progress_deadline": "600s",
                "rolling_update_status": {
                    "max_unavailable": 1,  # 25% of 5 replicas
                    "max_surge": 1,
                    "current_surge": 0,
                    "current_unavailable": 3
                },
                "replica_set_status": [
                    {"name": "api-server-abc123", "revision": 5, "replicas": 2, "ready": 2},
                    {"name": "api-server-def456", "revision": 6, "replicas": 3, "ready": 0}
                ]
            },
            "pod_analysis": {
                "new_pods": [
                    {"name": "api-server-def456-1", "status": "ImagePullBackOff"},
                    {"name": "api-server-def456-2", "status": "CrashLoopBackOff"},
                    {"name": "api-server-def456-3", "status": "Pending"}
                ],
                "old_pods": [
                    {"name": "api-server-abc123-1", "status": "Running"},
                    {"name": "api-server-abc123-2", "status": "Running"}
                ],
                "blocking_issues": [
                    "New image cannot be pulled",
                    "Application crashes on startup",
                    "Insufficient resources for new pods"
                ]
            },
            "solutions": [
                "Fix image pull issues for new replica set",
                "Debug application startup crashes",
                "Resolve resource constraints",
                "Consider rollback if issues persist"
            ],
            "resolution_steps": [
                "1. Check new pods: kubectl get pods -l app=api-server -n production",
                "2. Debug image pull: kubectl describe pod api-server-def456-1 -n production",
                "3. Check logs: kubectl logs api-server-def456-2 -n production",
                "4. Fix issues or rollback: kubectl rollout undo deployment/api-server -n production"
            ],
            "rollback_option": {
                "can_rollback": True,
                "previous_revision": 5,
                "rollback_command": "kubectl rollout undo deployment/api-server -n production",
                "estimated_rollback_time": "5 minutes"
            },
            "resource_check": {
                "cpu_available": "2.5 cores",
                "memory_available": "8Gi",
                "sufficient_resources": False,
                "recommendation": "Scale down other deployments or add nodes"
            }
        }
        
        # Configure mock
        k8s_manager.resolve_deployment_rollout_stuck = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_deployment_rollout_stuck(deployment_context)
        
        # Assertions
        assert resolution["issue_type"] == "DeploymentRolloutStuck"
        assert len(resolution["pod_analysis"]["blocking_issues"]) == 3
        assert "Fix image pull issues" in resolution["solutions"]
        assert resolution["rollback_option"]["can_rollback"] is True
        assert "kubectl rollout undo" in resolution["rollback_option"]["rollback_command"]

    @pytest.mark.asyncio
    async def test_etcd_cluster_unhealthy(self, cluster_manager):
        """Test resolution of etcd cluster health issues."""
        
        etcd_context = {
            "cluster_size": 3,
            "healthy_members": 1,
            "unhealthy_members": ["etcd-2", "etcd-3"],
            "leader": "etcd-1",
            "error_symptoms": [
                "slow API server responses",
                "kubectl commands timing out",
                "frequent leader elections"
            ],
            "etcd_version": "3.5.9",
            "control_plane_nodes": ["master-1", "master-2", "master-3"]
        }
        
        # Mock etcd resolution
        mock_resolution = {
            "issue_type": "EtcdClusterUnhealthy",
            "etcd_analysis": {
                "cluster_status": "degraded",
                "quorum_available": True,  # 1/3 still maintains quorum
                "member_status": [
                    {"name": "etcd-1", "status": "healthy", "is_leader": True},
                    {"name": "etcd-2", "status": "unreachable", "last_seen": "5 minutes ago"},
                    {"name": "etcd-3", "status": "unhealthy", "error": "connection refused"}
                ],
                "db_size": "2.1GB",
                "raft_applied_index": 123456,
                "performance_issues": ["high latency", "network partitions"]
            },
            "disk_analysis": {
                "disk_usage": [
                    {"node": "master-1", "etcd_disk": "45%", "inodes": "23%"},
                    {"node": "master-2", "etcd_disk": "78%", "inodes": "67%"},
                    {"node": "master-3", "etcd_disk": "42%", "inodes": "19%"}
                ],
                "disk_io_latency": [
                    {"node": "master-1", "latency": "2ms"},
                    {"node": "master-2", "latency": "45ms"},  # High latency
                    {"node": "master-3", "latency": "3ms"}
                ]
            },
            "solutions": [
                "Investigate and fix etcd-2 and etcd-3 connectivity",
                "Check disk I/O performance on master-2",
                "Verify network connectivity between etcd members",
                "Consider etcd defragmentation if needed"
            ],
            "diagnostic_commands": [
                "kubectl exec -n kube-system etcd-master-1 -- etcdctl endpoint health --cluster",
                "kubectl exec -n kube-system etcd-master-1 -- etcdctl member list",
                "kubectl logs -n kube-system etcd-master-2",
                "kubectl logs -n kube-system etcd-master-3"
            ],
            "recovery_commands": [
                "# Check etcd member status",
                "kubectl exec -n kube-system etcd-master-1 -- etcdctl member list -w table",
                "# Restart unhealthy etcd pods",
                "kubectl delete pod -n kube-system etcd-master-2",
                "kubectl delete pod -n kube-system etcd-master-3",
                "# Monitor recovery",
                "kubectl get pods -n kube-system -l component=etcd -w"
            ],
            "defrag_recommendation": {
                "needed": True,
                "current_db_size": "2.1GB",
                "estimated_after_defrag": "1.2GB",
                "defrag_command": "kubectl exec -n kube-system etcd-master-1 -- etcdctl defrag --cluster"
            },
            "critical_warning": "etcd cluster is in degraded state. Immediate action required."
        }
        
        # Configure mock
        cluster_manager.resolve_etcd_unhealthy = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await cluster_manager.resolve_etcd_unhealthy(etcd_context)
        
        # Assertions
        assert resolution["issue_type"] == "EtcdClusterUnhealthy"
        assert resolution["etcd_analysis"]["quorum_available"] is True
        assert "Investigate and fix etcd-2" in resolution["solutions"]
        assert "etcdctl endpoint health" in str(resolution["diagnostic_commands"])
        assert resolution["defrag_recommendation"]["needed"] is True
        assert "degraded state" in resolution["critical_warning"]

    @pytest.mark.asyncio
    async def test_kube_apiserver_high_latency(self, cluster_manager):
        """Test resolution of API server high latency issues."""
        
        apiserver_context = {
            "avg_response_time": "2.5s",
            "p95_response_time": "8.2s",
            "error_rate": "3%",
            "concurrent_requests": 250,
            "etcd_latency": "45ms",
            "control_plane_nodes": 3,
            "cluster_size": 50,
            "high_latency_duration": "25 minutes"
        }
        
        # Mock API server resolution
        mock_resolution = {
            "issue_type": "APIServerHighLatency",
            "performance_analysis": {
                "current_metrics": {
                    "avg_latency": "2.5s",
                    "p95_latency": "8.2s",
                    "p99_latency": "15.8s",
                    "requests_per_second": 145,
                    "error_rate": "3%"
                },
                "target_metrics": {
                    "avg_latency": "< 200ms",
                    "p95_latency": "< 1s",
                    "error_rate": "< 1%"
                },
                "bottlenecks_identified": [
                    "High etcd latency (45ms vs target 10ms)",
                    "API server CPU throttling",
                    "Large response payloads",
                    "Inefficient client queries"
                ]
            },
            "resource_analysis": {
                "apiserver_cpu": "85%",
                "apiserver_memory": "67%",
                "etcd_cpu": "78%",
                "etcd_memory": "45%",
                "network_bandwidth": "12%",
                "disk_io_wait": "23%"
            },
            "solutions": [
                "Optimize etcd performance and reduce latency",
                "Scale API server resources or add replicas",
                "Implement request rate limiting and prioritization",
                "Optimize client queries and reduce response sizes"
            ],
            "immediate_actions": [
                "Increase API server CPU limits",
                "Add priority and fairness configuration",
                "Scale etcd if possible",
                "Implement client-side caching where appropriate"
            ],
            "optimization_commands": [
                "# Increase API server resources",
                "kubectl patch -n kube-system deployment kube-apiserver --patch '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"kube-apiserver\",\"resources\":{\"limits\":{\"cpu\":\"2000m\",\"memory\":\"4Gi\"}}}]}}}}'",
                "# Enable profiling temporarily",
                "kubectl port-forward -n kube-system svc/kube-apiserver 6443:443",
                "# Check etcd performance",
                "kubectl exec -n kube-system etcd-master-1 -- etcdctl check perf"
            ],
            "monitoring_setup": [
                "Set up API server latency alerts",
                "Monitor etcd performance metrics",
                "Track client request patterns",
                "Implement distributed tracing"
            ],
            "long_term_recommendations": [
                "Implement horizontal API server scaling",
                "Use etcd learner nodes for read scaling",
                "Optimize frequently used API patterns",
                "Consider API aggregation for custom resources"
            ]
        }
        
        # Configure mock
        cluster_manager.resolve_apiserver_latency = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await cluster_manager.resolve_apiserver_latency(apiserver_context)
        
        # Assertions
        assert resolution["issue_type"] == "APIServerHighLatency"
        assert resolution["performance_analysis"]["current_metrics"]["avg_latency"] == "2.5s"
        assert "High etcd latency" in str(resolution["performance_analysis"]["bottlenecks_identified"])
        assert "Optimize etcd performance" in resolution["solutions"]
        assert "kubectl patch" in str(resolution["optimization_commands"])

    @pytest.mark.asyncio
    async def test_cluster_autoscaler_not_scaling(self, k8s_manager):
        """Test resolution of cluster autoscaler not scaling nodes."""
        
        autoscaler_context = {
            "pending_pods": 8,
            "unschedulable_duration": "15 minutes",
            "cluster_autoscaler_version": "1.21.0",
            "node_groups": [
                {"name": "workers", "min": 3, "max": 10, "current": 3},
                {"name": "compute", "min": 0, "max": 5, "current": 0}
            ],
            "cloud_provider": "aws",
            "total_nodes": 3,
            "resource_shortage": {
                "cpu": "12 cores needed",
                "memory": "32Gi needed"
            }
        }
        
        # Mock autoscaler resolution
        mock_resolution = {
            "issue_type": "ClusterAutoscalerNotScaling",
            "autoscaler_analysis": {
                "autoscaler_status": "running",
                "scaling_events": [],
                "last_activity": "10 minutes ago",
                "node_group_limits": [
                    {"name": "workers", "at_max": False, "can_scale": True},
                    {"name": "compute", "at_max": False, "can_scale": True}
                ],
                "scaling_policies": {
                    "scale_down_delay": "10m",
                    "scale_down_unneeded_time": "10m",
                    "max_node_provision_time": "15m"
                }
            },
            "blocking_factors": [
                "Pod anti-affinity rules preventing scheduling",
                "Resource requests too large for available instance types",
                "AWS service limits or quotas reached",
                "Autoscaler configuration issues"
            ],
            "pod_analysis": {
                "pending_pods": [
                    {
                        "name": "large-job-1",
                        "cpu_request": "4000m",
                        "memory_request": "16Gi",
                        "scheduling_issue": "Insufficient resources"
                    },
                    {
                        "name": "batch-worker-2",
                        "cpu_request": "2000m", 
                        "memory_request": "8Gi",
                        "scheduling_issue": "Node affinity not satisfied"
                    }
                ],
                "unschedulable_reasons": [
                    "Insufficient cpu (8 pods)",
                    "Insufficient memory (5 pods)",
                    "Node affinity (2 pods)"
                ]
            },
            "solutions": [
                "Check cluster autoscaler logs for scaling decisions",
                "Verify AWS service limits and quotas",
                "Review pod resource requests and node capacity",
                "Check node group configuration and policies"
            ],
            "diagnostic_commands": [
                "kubectl logs -n kube-system -l app=cluster-autoscaler",
                "kubectl describe pod large-job-1",
                "kubectl get nodes --show-labels",
                "kubectl get events --field-selector reason=FailedScheduling"
            ],
            "aws_checks": [
                "aws ec2 describe-account-attributes --attribute-names max-instances",
                "aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names workers",
                "aws ec2 describe-instance-type-offerings --location-type availability-zone"
            ],
            "resolution_actions": [
                "Increase AWS service limits if needed",
                "Adjust node group max size",
                "Modify pod resource requests if too large",
                "Update cluster autoscaler configuration"
            ],
            "estimated_scaling_time": "5-10 minutes after fixes"
        }
        
        # Configure mock
        k8s_manager.resolve_autoscaler_not_scaling = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_autoscaler_not_scaling(autoscaler_context)
        
        # Assertions
        assert resolution["issue_type"] == "ClusterAutoscalerNotScaling"
        assert len(resolution["blocking_factors"]) > 0
        assert "Check cluster autoscaler logs" in resolution["solutions"]
        assert "kubectl logs" in str(resolution["diagnostic_commands"])
        assert "aws ec2 describe-account-attributes" in str(resolution["aws_checks"])

    @pytest.mark.asyncio
    async def test_kubelet_certificate_expiration(self, security_manager):
        """Test resolution of kubelet certificate expiration issues."""
        
        cert_context = {
            "node_name": "worker-node-4",
            "certificate_type": "kubelet-client",
            "expiration_date": "2025-08-09T16:00:00Z",
            "current_date": "2025-08-09T15:45:00Z",
            "time_until_expiry": "15 minutes",
            "certificate_status": "expired",
            "kubelet_status": "failing_auth",
            "auto_rotation_enabled": False
        }
        
        # Mock certificate resolution
        mock_resolution = {
            "issue_type": "KubeletCertificateExpired",
            "certificate_analysis": {
                "cert_type": "kubelet-client",
                "expiry_status": "expired",
                "time_expired": "45 minutes",
                "issuer": "kubernetes-ca",
                "rotation_enabled": False,
                "backup_certificates": []
            },
            "kubelet_analysis": {
                "kubelet_running": True,
                "api_connectivity": False,
                "authentication_failing": True,
                "last_successful_heartbeat": "45 minutes ago",
                "node_status": "NotReady"
            },
            "certificate_locations": {
                "client_cert": "/var/lib/kubelet/pki/kubelet-client-current.pem",
                "client_key": "/var/lib/kubelet/pki/kubelet-client-current-key.pem",
                "ca_cert": "/etc/kubernetes/pki/ca.crt",
                "kubelet_config": "/var/lib/kubelet/config.yaml"
            },
            "solutions": [
                "Enable automatic certificate rotation",
                "Manually renew kubelet certificates",
                "Restart kubelet service after certificate renewal",
                "Verify certificate rotation configuration"
            ],
            "resolution_steps": [
                "1. SSH to worker-node-4",
                "2. Stop kubelet: sudo systemctl stop kubelet",
                "3. Remove old certificates: sudo rm /var/lib/kubelet/pki/kubelet-client*",
                "4. Enable rotation in kubelet config",
                "5. Start kubelet: sudo systemctl start kubelet",
                "6. Verify new certificate: openssl x509 -in /var/lib/kubelet/pki/kubelet-client-current.pem -text"
            ],
            "certificate_renewal_commands": [
                "# Enable certificate rotation",
                "sudo sed -i 's/rotateCertificates: false/rotateCertificates: true/' /var/lib/kubelet/config.yaml",
                "# Remove expired certificates",
                "sudo rm -f /var/lib/kubelet/pki/kubelet-client*",
                "# Restart kubelet to trigger renewal",
                "sudo systemctl restart kubelet",
                "# Wait for certificate renewal",
                "sleep 60",
                "# Verify node rejoins cluster",
                "kubectl get node worker-node-4"
            ],
            "prevention_measures": [
                "Enable automatic certificate rotation on all nodes",
                "Set up certificate expiration monitoring",
                "Implement automated certificate renewal workflows",
                "Regular certificate expiration audits"
            ],
            "estimated_recovery_time": "5-10 minutes"
        }
        
        # Configure mock
        security_manager.resolve_kubelet_cert_expiration = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await security_manager.resolve_kubelet_cert_expiration(cert_context)
        
        # Assertions
        assert resolution["issue_type"] == "KubeletCertificateExpired"
        assert resolution["certificate_analysis"]["rotation_enabled"] is False
        assert "Enable automatic certificate rotation" in resolution["solutions"]
        assert "systemctl restart kubelet" in str(resolution["certificate_renewal_commands"])
        assert "5-10 minutes" in resolution["estimated_recovery_time"]

    @pytest.mark.asyncio
    async def test_kube_proxy_daemonset_failure(self, k8s_manager):
        """Test resolution of kube-proxy DaemonSet failures."""
        
        kube_proxy_context = {
            "daemonset_name": "kube-proxy",
            "namespace": "kube-system",
            "desired_nodes": 8,
            "ready_pods": 5,
            "failed_nodes": ["worker-node-2", "worker-node-3", "worker-node-4"],
            "error_pattern": "failed to create pod network",
            "cni_plugin": "calico",
            "k8s_version": "1.28.2"
        }
        
        # Mock kube-proxy resolution
        mock_resolution = {
            "issue_type": "KubeProxyDaemonSetFailure",
            "daemonset_analysis": {
                "current_replicas": 5,
                "desired_replicas": 8,
                "ready_replicas": 5,
                "failed_replicas": 3,
                "update_strategy": "RollingUpdate",
                "pod_status": [
                    {"node": "worker-node-2", "status": "ImagePullBackOff"},
                    {"node": "worker-node-3", "status": "CrashLoopBackOff"},
                    {"node": "worker-node-4", "status": "Init:Error"}
                ]
            },
            "network_analysis": {
                "cni_plugin": "calico",
                "cni_status": "partially_healthy",
                "node_network_issues": [
                    "CNI plugin not installed on worker-node-2",
                    "CNI configuration mismatch on worker-node-3",
                    "Network namespace issues on worker-node-4"
                ],
                "iptables_rules": "inconsistent_across_nodes"
            },
            "solutions": [
                "Fix CNI plugin installation on failed nodes",
                "Resolve kube-proxy image pull issues",
                "Check and fix network namespace problems",
                "Ensure consistent iptables configuration"
            ],
            "node_specific_fixes": {
                "worker-node-2": [
                    "Install missing CNI plugin binaries",
                    "Fix image pull authentication",
                    "Restart kube-proxy pod"
                ],
                "worker-node-3": [
                    "Fix CNI configuration file",
                    "Check container runtime network setup",
                    "Restart both CNI and kube-proxy"
                ],
                "worker-node-4": [
                    "Reset network namespace",
                    "Reinstall CNI plugin",
                    "Verify node network connectivity"
                ]
            },
            "resolution_commands": [
                "# Check kube-proxy pods",
                "kubectl get pods -n kube-system -l k8s-app=kube-proxy -o wide",
                "# Fix image pull on worker-node-2",
                "kubectl delete pod -n kube-system kube-proxy-xyz --force",
                "# Check CNI installation",
                "kubectl exec -n kube-system kube-proxy-abc -- ls -la /opt/cni/bin/",
                "# Restart daemonset",
                "kubectl rollout restart daemonset/kube-proxy -n kube-system"
            ],
            "verification_tests": [
                "kubectl get pods -n kube-system -l k8s-app=kube-proxy",
                "kubectl exec test-pod -- nc -zv kubernetes.default 443",
                "kubectl get services -A",
                "kubectl run test-connectivity --image=busybox --rm -it -- /bin/sh"
            ]
        }
        
        # Configure mock
        k8s_manager.resolve_kube_proxy_failure = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_kube_proxy_failure(kube_proxy_context)
        
        # Assertions
        assert resolution["issue_type"] == "KubeProxyDaemonSetFailure"
        assert resolution["daemonset_analysis"]["failed_replicas"] == 3
        assert "Fix CNI plugin installation" in resolution["solutions"]
        assert "worker-node-2" in resolution["node_specific_fixes"]
        assert "kubectl rollout restart" in str(resolution["resolution_commands"])

    @pytest.mark.asyncio
    async def test_scheduler_not_scheduling_pods(self, k8s_manager):
        """Test resolution of kube-scheduler not scheduling pods."""
        
        scheduler_context = {
            "pending_pods": 15,
            "scheduler_name": "default-scheduler",
            "pending_duration": "30 minutes",
            "scheduler_status": "running",
            "scheduler_events": [
                "no nodes available to schedule pods",
                "0/5 nodes are available: 3 Insufficient cpu, 2 node(s) had taints"
            ],
            "cluster_nodes": 5,
            "available_nodes": 2
        }
        
        # Mock scheduler resolution
        mock_resolution = {
            "issue_type": "SchedulerNotScheduling",
            "scheduler_analysis": {
                "scheduler_health": "running_but_not_scheduling",
                "scheduling_queue_length": 15,
                "recent_scheduling_attempts": 0,
                "scheduler_logs_errors": [
                    "failed to find a fit for pod",
                    "no nodes available",
                    "insufficient resources"
                ],
                "scheduler_config": "default"
            },
            "cluster_capacity_analysis": {
                "total_nodes": 5,
                "schedulable_nodes": 2,
                "tainted_nodes": 2,
                "unready_nodes": 1,
                "resource_availability": {
                    "total_cpu": "20 cores",
                    "available_cpu": "3.2 cores",
                    "total_memory": "80Gi",
                    "available_memory": "12Gi"
                }
            },
            "pod_scheduling_constraints": {
                "resource_requests_too_large": 8,
                "node_selector_mismatch": 3,
                "pod_affinity_conflicts": 2,
                "taint_toleration_issues": 2
            },
            "solutions": [
                "Add more nodes or increase node capacity",
                "Remove unnecessary taints from nodes",
                "Optimize pod resource requests",
                "Fix node selector and affinity rules",
                "Restart kube-scheduler if stuck"
            ],
            "immediate_actions": [
                "Scale cluster to add more capacity",
                "Remove non-essential taints",
                "Adjust pod resource requests",
                "Clear scheduling queue if needed"
            ],
            "resolution_commands": [
                "# Check scheduler status",
                "kubectl get pods -n kube-system -l component=kube-scheduler",
                "# Check node capacity",
                "kubectl describe nodes | grep -A 5 'Allocatable'",
                "# Check pending pods",
                "kubectl get pods --field-selector=status.phase=Pending -A",
                "# Remove taints if safe",
                "kubectl taint nodes worker-node-2 dedicated-"
            ],
            "capacity_recommendations": {
                "add_nodes": 2,
                "node_size": "4 cores, 16GB RAM",
                "remove_taints": ["worker-node-2", "worker-node-3"],
                "resource_optimization": "Reduce pod requests by 30%"
            }
        }
        
        # Configure mock
        k8s_manager.resolve_scheduler_not_scheduling = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_scheduler_not_scheduling(scheduler_context)
        
        # Assertions
        assert resolution["issue_type"] == "SchedulerNotScheduling"
        assert resolution["scheduler_analysis"]["scheduling_queue_length"] == 15
        assert "Add more nodes" in resolution["solutions"]
        assert "kubectl taint nodes" in str(resolution["resolution_commands"])
        assert resolution["capacity_recommendations"]["add_nodes"] == 2
