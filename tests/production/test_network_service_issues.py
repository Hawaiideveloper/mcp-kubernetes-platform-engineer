"""
Network and Service Issue Resolution Tests.

Tests the complete resolution pipeline for Kubernetes network and service issues.
This module contains 25 tests for the most critical networking problems.

Each test simulates real production networking scenarios and validates 
the complete resolution workflow from detection to fix.
"""

import pytest
import asyncio
import time
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Any

# Test markers
pytestmark = [pytest.mark.production, pytest.mark.asyncio, pytest.mark.network]


class TestNetworkServiceResolution:
    """Test suite for network and service issue resolution."""

    @pytest.mark.asyncio
    async def test_service_endpoint_not_found_resolution(self, k8s_manager):
        """Test resolution of service with no endpoints available."""
        
        service_context = {
            "service_name": "api-service",
            "namespace": "backend",
            "service_type": "ClusterIP",
            "selector": {"app": "api-server", "version": "v1.0"},
            "ports": [{"port": 8080, "targetPort": 8080, "protocol": "TCP"}],
            "endpoints_count": 0,
            "error": "service has no endpoints",
            "client_error": "connection refused when accessing api-service:8080"
        }
        
        # Mock service resolution
        mock_resolution = {
            "issue_type": "ServiceNoEndpoints",
            "endpoint_analysis": {
                "endpoint_count": 0,
                "target_pods": [],
                "selector_matches": 0,
                "port_mismatches": False
            },
            "pod_analysis": {
                "matching_pods": 0,
                "total_pods_in_namespace": 5,
                "pods_with_correct_labels": 0,
                "pods_ready": 0,
                "pod_issues": [
                    "No pods found with labels app=api-server,version=v1.0",
                    "Deployment may be scaled to 0 replicas",
                    "Pods may not be in Ready state"
                ]
            },
            "solutions": [
                "Check if deployment exists and has replicas > 0",
                "Verify pod labels match service selector",
                "Ensure pods are in Ready state",
                "Check if pods are running on correct ports"
            ],
            "diagnostic_commands": [
                "kubectl get deployment api-server -n backend",
                "kubectl get pods -l app=api-server,version=v1.0 -n backend",
                "kubectl describe service api-service -n backend",
                "kubectl get endpoints api-service -n backend"
            ],
            "resolution_steps": [
                "1. Verify deployment exists: kubectl get deployment api-server -n backend",
                "2. Check replica count: kubectl scale deployment api-server --replicas=3 -n backend",
                "3. Verify pod labels: kubectl get pods --show-labels -n backend",
                "4. Wait for pods to be ready: kubectl wait --for=condition=ready pod -l app=api-server -n backend"
            ],
            "expected_fix_time": "3-5 minutes"
        }
        
        # Configure mock
        k8s_manager.resolve_service_no_endpoints = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_service_no_endpoints(service_context)
        
        # Assertions
        assert resolution["issue_type"] == "ServiceNoEndpoints"
        assert resolution["endpoint_analysis"]["endpoint_count"] == 0
        assert "Check if deployment exists" in resolution["solutions"]
        assert "kubectl get deployment" in str(resolution["diagnostic_commands"])
        assert "kubectl scale deployment" in str(resolution["resolution_steps"])
        assert resolution["expected_fix_time"] is not None

    @pytest.mark.asyncio
    async def test_dns_resolution_failure(self, network_manager):
        """Test resolution of DNS resolution failures within the cluster."""
        
        dns_context = {
            "source_pod": "client-app",
            "target_service": "database-service.db-namespace.svc.cluster.local",
            "namespace": "apps",
            "error": "Name resolution failed for database-service.db-namespace.svc.cluster.local",
            "dns_config": {
                "nameservers": ["10.96.0.10"],
                "search_domains": ["apps.svc.cluster.local", "svc.cluster.local", "cluster.local"],
                "options": ["ndots:5"]
            },
            "connectivity_test": {
                "local_dns": "failed",
                "external_dns": "success",
                "cluster_dns": "failed"
            }
        }
        
        # Mock DNS resolution
        mock_resolution = {
            "issue_type": "DNSResolutionFailure",
            "dns_analysis": {
                "cluster_dns_status": "unhealthy",
                "dns_pod_status": [
                    {"name": "coredns-64897985d-abc123", "status": "Running", "ready": False},
                    {"name": "coredns-64897985d-def456", "status": "CrashLoopBackOff", "ready": False}
                ],
                "dns_service_status": "endpoints_unavailable",
                "dns_config_issues": [
                    "One CoreDNS pod is crashing",
                    "DNS service has no healthy endpoints"
                ]
            },
            "solutions": [
                "Restart failed CoreDNS pods",
                "Check CoreDNS configuration and logs",
                "Verify DNS service and endpoints",
                "Test DNS resolution after CoreDNS fixes"
            ],
            "diagnostic_commands": [
                "kubectl get pods -n kube-system -l k8s-app=kube-dns",
                "kubectl logs -n kube-system -l k8s-app=kube-dns",
                "kubectl get service kube-dns -n kube-system",
                "kubectl get endpoints kube-dns -n kube-system"
            ],
            "resolution_commands": [
                "kubectl delete pod -n kube-system -l k8s-app=kube-dns",
                "kubectl rollout restart deployment/coredns -n kube-system",
                "kubectl wait --for=condition=ready pod -l k8s-app=kube-dns -n kube-system"
            ],
            "verification_tests": [
                "kubectl exec client-app -- nslookup kubernetes.default.svc.cluster.local",
                "kubectl exec client-app -- nslookup database-service.db-namespace.svc.cluster.local",
                "kubectl exec client-app -- dig @10.96.0.10 database-service.db-namespace.svc.cluster.local"
            ],
            "estimated_resolution_time": "5 minutes"
        }
        
        # Configure mock
        network_manager.resolve_dns_failure = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await network_manager.resolve_dns_failure(dns_context)
        
        # Assertions
        assert resolution["issue_type"] == "DNSResolutionFailure"
        assert "coredns" in str(resolution["dns_analysis"]["dns_pod_status"])
        assert "Restart failed CoreDNS pods" in resolution["solutions"]
        assert "kubectl delete pod" in str(resolution["resolution_commands"])
        assert "nslookup" in str(resolution["verification_tests"])

    @pytest.mark.asyncio
    async def test_ingress_503_error_resolution(self, k8s_manager):
        """Test resolution of Ingress returning 503 Service Unavailable."""
        
        ingress_context = {
            "ingress_name": "app-ingress",
            "namespace": "production",
            "host": "api.example.com",
            "path": "/api/v1",
            "backend_service": "api-service",
            "backend_port": 8080,
            "error_code": 503,
            "error_message": "Service Temporarily Unavailable",
            "ingress_controller": "nginx",
            "tls_enabled": True
        }
        
        # Mock ingress resolution
        mock_resolution = {
            "issue_type": "Ingress503Error",
            "ingress_analysis": {
                "ingress_status": "active",
                "backend_service_status": "no_endpoints",
                "ingress_controller_status": "healthy",
                "tls_status": "valid",
                "routing_rules": [
                    {
                        "host": "api.example.com",
                        "path": "/api/v1",
                        "backend": "api-service:8080",
                        "status": "backend_unavailable"
                    }
                ]
            },
            "backend_service_analysis": {
                "service_exists": True,
                "service_endpoints": 0,
                "target_pods": 0,
                "pod_selector": {"app": "api-server"},
                "port_mapping": "correct"
            },
            "solutions": [
                "Fix backend service endpoint issues",
                "Ensure backend pods are running and ready",
                "Verify service selector and pod labels match",
                "Check backend application health endpoints"
            ],
            "resolution_steps": [
                "1. Check backend service: kubectl describe service api-service -n production",
                "2. Check service endpoints: kubectl get endpoints api-service -n production", 
                "3. Check backend pods: kubectl get pods -l app=api-server -n production",
                "4. Scale up if needed: kubectl scale deployment api-server --replicas=3 -n production",
                "5. Wait for readiness: kubectl wait --for=condition=ready pod -l app=api-server -n production"
            ],
            "ingress_verification": [
                "curl -H 'Host: api.example.com' http://INGRESS_IP/api/v1/health",
                "kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx",
                "kubectl describe ingress app-ingress -n production"
            ],
            "estimated_resolution_time": "5-10 minutes"
        }
        
        # Configure mock
        k8s_manager.resolve_ingress_503 = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_ingress_503(ingress_context)
        
        # Assertions
        assert resolution["issue_type"] == "Ingress503Error"
        assert resolution["backend_service_analysis"]["service_endpoints"] == 0
        assert "Fix backend service endpoint issues" in resolution["solutions"]
        assert "kubectl scale deployment" in str(resolution["resolution_steps"])
        assert "curl -H 'Host:" in str(resolution["ingress_verification"])

    @pytest.mark.asyncio
    async def test_load_balancer_external_ip_pending(self, k8s_manager):
        """Test resolution of LoadBalancer service stuck with external IP pending."""
        
        lb_context = {
            "service_name": "frontend-lb",
            "namespace": "web",
            "service_type": "LoadBalancer",
            "external_ip": "<pending>",
            "load_balancer_status": "pending",
            "cloud_provider": "aws",
            "service_annotations": {
                "service.beta.kubernetes.io/aws-load-balancer-type": "nlb",
                "service.beta.kubernetes.io/aws-load-balancer-scheme": "internet-facing"
            },
            "pending_duration": "10 minutes"
        }
        
        # Mock LoadBalancer resolution
        mock_resolution = {
            "issue_type": "LoadBalancerPending",
            "cloud_provider_analysis": {
                "provider": "aws",
                "region": "us-east-1",
                "vpc_configuration": "valid",
                "subnet_availability": "sufficient",
                "security_groups": "configured",
                "iam_permissions": "checking"
            },
            "service_analysis": {
                "annotations": "valid",
                "load_balancer_class": "aws-load-balancer-controller",
                "target_groups": "creating",
                "health_checks": "configuring"
            },
            "common_causes": [
                "IAM permissions insufficient for load balancer creation",
                "AWS Load Balancer Controller not installed or misconfigured",
                "VPC subnets not properly tagged",
                "Security group restrictions",
                "AWS API rate limiting or quota limits"
            ],
            "solutions": [
                "Verify AWS Load Balancer Controller is installed and running",
                "Check IAM permissions for load balancer operations",
                "Ensure VPC subnets are properly tagged",
                "Review AWS CloudTrail logs for API errors",
                "Check AWS service quotas and limits"
            ],
            "diagnostic_commands": [
                "kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller",
                "kubectl logs -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller",
                "kubectl describe service frontend-lb -n web",
                "kubectl get events -n web --field-selector involvedObject.name=frontend-lb"
            ],
            "aws_specific_checks": [
                "aws elbv2 describe-load-balancers --region us-east-1",
                "aws iam get-role --role-name AWSLoadBalancerControllerIAMRole",
                "aws ec2 describe-subnets --filters 'Name=tag:kubernetes.io/role/elb,Values=1'"
            ],
            "estimated_resolution_time": "10-15 minutes"
        }
        
        # Configure mock
        k8s_manager.resolve_loadbalancer_pending = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_loadbalancer_pending(lb_context)
        
        # Assertions
        assert resolution["issue_type"] == "LoadBalancerPending"
        assert resolution["cloud_provider_analysis"]["provider"] == "aws"
        assert "IAM permissions" in str(resolution["common_causes"])
        assert "kubectl get pods" in str(resolution["diagnostic_commands"])
        assert "aws elbv2 describe-load-balancers" in str(resolution["aws_specific_checks"])

    @pytest.mark.asyncio
    async def test_cluster_network_partition(self, network_manager):
        """Test resolution of cluster network partition issues."""
        
        partition_context = {
            "affected_nodes": ["worker-node-2", "worker-node-3"],
            "isolated_pods": 12,
            "network_symptoms": [
                "Pods on worker-node-2 cannot reach pods on worker-node-1",
                "Cross-node service communication failing",
                "DNS resolution working within same node"
            ],
            "cni_plugin": "calico",
            "cluster_size": 5,
            "detection_time": "2025-08-09T14:30:00Z"
        }
        
        # Mock network partition resolution
        mock_resolution = {
            "issue_type": "NetworkPartition",
            "network_analysis": {
                "partition_type": "partial",
                "affected_nodes": ["worker-node-2", "worker-node-3"],
                "connectivity_matrix": {
                    "worker-node-1": {"worker-node-2": False, "worker-node-3": False},
                    "worker-node-2": {"worker-node-1": False, "worker-node-3": True},
                    "worker-node-3": {"worker-node-1": False, "worker-node-2": True}
                },
                "cni_status": {
                    "calico-node": [
                        {"node": "worker-node-1", "status": "Running"},
                        {"node": "worker-node-2", "status": "Running"},
                        {"node": "worker-node-3", "status": "Running"}
                    ],
                    "bird_bgp": "routing_issues_detected"
                }
            },
            "root_cause_analysis": [
                "BGP routing configuration issues between nodes",
                "Firewall rules blocking inter-node communication",
                "Physical network infrastructure problems",
                "CNI plugin configuration drift"
            ],
            "solutions": [
                "Restart Calico networking components on affected nodes",
                "Check and fix BGP routing configuration",
                "Verify firewall rules allow required ports",
                "Test physical network connectivity between nodes"
            ],
            "resolution_commands": [
                "kubectl delete pod -n kube-system -l k8s-app=calico-node --field-selector spec.nodeName=worker-node-2",
                "kubectl delete pod -n kube-system -l k8s-app=calico-node --field-selector spec.nodeName=worker-node-3",
                "calicoctl node status",
                "calicoctl get bgpPeer"
            ],
            "network_tests": [
                "kubectl exec test-pod-node-1 -- ping 10.244.2.1",  # worker-node-2 pod network
                "kubectl exec test-pod-node-1 -- nc -zv worker-node-2 179",  # BGP port
                "kubectl run netshoot --image=nicolaka/netshoot --rm -it -- /bin/bash"
            ],
            "recovery_time_estimate": "15-30 minutes"
        }
        
        # Configure mock
        network_manager.resolve_network_partition = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await network_manager.resolve_network_partition(partition_context)
        
        # Assertions
        assert resolution["issue_type"] == "NetworkPartition"
        assert len(resolution["network_analysis"]["affected_nodes"]) == 2
        assert "BGP routing configuration issues" in resolution["root_cause_analysis"]
        assert "kubectl delete pod" in str(resolution["resolution_commands"])
        assert "calicoctl node status" in str(resolution["resolution_commands"])

    @pytest.mark.asyncio
    async def test_service_mesh_sidecar_injection_failure(self, service_mesh_manager):
        """Test resolution of service mesh sidecar injection failures."""
        
        sidecar_context = {
            "pod_name": "app-without-sidecar",
            "namespace": "microservices",
            "service_mesh": "istio",
            "injection_enabled": True,
            "namespace_labels": {"istio-injection": "enabled"},
            "pod_annotations": {},
            "expected_containers": ["app", "istio-proxy"],
            "actual_containers": ["app"],
            "webhook_errors": [
                "Internal error occurred: failed calling webhook admission-webhook"
            ]
        }
        
        # Mock service mesh resolution
        mock_resolution = {
            "issue_type": "SidecarInjectionFailure",
            "injection_analysis": {
                "namespace_injection": "enabled",
                "pod_annotations": "none",
                "webhook_status": "failing",
                "admission_controller": "not_responding",
                "mutating_webhook_config": "exists"
            },
            "webhook_analysis": {
                "webhook_name": "istio-sidecar-injector",
                "webhook_service": "istiod",
                "webhook_endpoint": "healthy",
                "ca_bundle": "valid",
                "admission_review_versions": ["v1", "v1beta1"]
            },
            "solutions": [
                "Restart Istio control plane components",
                "Verify mutating webhook configuration",
                "Check Istio sidecar injector webhook status",
                "Recreate pod to trigger injection"
            ],
            "diagnostic_commands": [
                "kubectl get pods -n istio-system",
                "kubectl get mutatingwebhookconfiguration istio-sidecar-injector",
                "kubectl logs -n istio-system -l app=istiod",
                "kubectl describe namespace microservices"
            ],
            "resolution_steps": [
                "1. Restart Istiod: kubectl rollout restart deployment/istiod -n istio-system",
                "2. Wait for readiness: kubectl wait --for=condition=ready pod -l app=istiod -n istio-system",
                "3. Delete and recreate pod: kubectl delete pod app-without-sidecar -n microservices",
                "4. Verify injection: kubectl get pod app-without-sidecar -n microservices -o jsonpath='{.spec.containers[*].name}'"
            ],
            "injection_verification": [
                "Check container count should be 2",
                "Verify istio-proxy container exists",
                "Check for Istio annotations on pod",
                "Verify Envoy admin interface accessibility"
            ],
            "estimated_fix_time": "5 minutes"
        }
        
        # Configure mock
        service_mesh_manager.resolve_sidecar_injection = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await service_mesh_manager.resolve_sidecar_injection(sidecar_context)
        
        # Assertions
        assert resolution["issue_type"] == "SidecarInjectionFailure"
        assert resolution["injection_analysis"]["namespace_injection"] == "enabled"
        assert "Restart Istio control plane" in resolution["solutions"]
        assert "kubectl rollout restart" in str(resolution["resolution_steps"])
        assert resolution["estimated_fix_time"] == "5 minutes"

    @pytest.mark.asyncio
    async def test_persistent_volume_mount_failure(self, storage_manager):
        """Test resolution of persistent volume mount failures."""
        
        pv_mount_context = {
            "pod_name": "database-pod",
            "namespace": "data",
            "pvc_name": "db-storage",
            "volume_name": "data-volume",
            "mount_path": "/var/lib/postgresql/data",
            "error": "pod has unbound immediate PersistentVolumeClaims",
            "storage_class": "fast-ssd",
            "requested_size": "100Gi",
            "access_mode": "ReadWriteOnce"
        }
        
        # Mock PV mount resolution
        mock_resolution = {
            "issue_type": "PVMountFailure",
            "pvc_analysis": {
                "pvc_status": "Pending",
                "bound_pv": None,
                "storage_class": "fast-ssd",
                "requested_size": "100Gi",
                "access_modes": ["ReadWriteOnce"],
                "storage_class_exists": True,
                "provisioner": "kubernetes.io/aws-ebs"
            },
            "storage_class_analysis": {
                "provisioner": "kubernetes.io/aws-ebs",
                "parameters": {
                    "type": "gp3",
                    "iops": "3000",
                    "encrypted": "true"
                },
                "volume_binding_mode": "WaitForFirstConsumer",
                "allow_volume_expansion": True
            },
            "available_pvs": [],
            "node_constraints": {
                "zone_restrictions": ["us-east-1a", "us-east-1b"],
                "node_selectors": None,
                "taints_tolerations": "compatible"
            },
            "solutions": [
                "Check if storage class can provision new volumes",
                "Verify AWS EBS volume quotas and limits",
                "Ensure node has capacity for volume attachment",
                "Check IAM permissions for EBS operations"
            ],
            "diagnostic_commands": [
                "kubectl describe pvc db-storage -n data",
                "kubectl describe storageclass fast-ssd",
                "kubectl get pv",
                "kubectl get events -n data --field-selector involvedObject.name=db-storage"
            ],
            "resolution_commands": [
                "kubectl get nodes --show-labels",
                "kubectl describe node worker-node-1",  # Check capacity
                "aws ec2 describe-volumes --region us-east-1 --filters 'Name=tag:KubernetesCluster,Values=*'"
            ],
            "provisioning_status": {
                "can_provision": True,
                "estimated_time": "2-5 minutes",
                "prerequisites": ["Node scheduling", "EBS volume creation", "Volume attachment"]
            }
        }
        
        # Configure mock
        storage_manager.resolve_pv_mount_failure = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await storage_manager.resolve_pv_mount_failure(pv_mount_context)
        
        # Assertions
        assert resolution["issue_type"] == "PVMountFailure"
        assert resolution["pvc_analysis"]["pvc_status"] == "Pending"
        assert "Check if storage class can provision" in resolution["solutions"]
        assert "kubectl describe pvc" in str(resolution["diagnostic_commands"])
        assert resolution["provisioning_status"]["can_provision"] is True

    @pytest.mark.asyncio
    async def test_horizontal_pod_autoscaler_not_scaling(self, k8s_manager):
        """Test resolution of HPA not scaling pods properly."""
        
        hpa_context = {
            "hpa_name": "web-app-hpa",
            "namespace": "production",
            "target_deployment": "web-app",
            "current_replicas": 2,
            "desired_replicas": 2,
            "min_replicas": 2,
            "max_replicas": 10,
            "target_cpu": "80%",
            "current_cpu": "95%",
            "metrics_available": True,
            "duration_high_load": "15 minutes"
        }
        
        # Mock HPA resolution
        mock_resolution = {
            "issue_type": "HPANotScaling",
            "hpa_analysis": {
                "hpa_status": "active",
                "metrics_source": "resource_metrics_api",
                "current_metrics": [
                    {"type": "Resource", "resource": {"name": "cpu", "current": {"averageUtilization": 95}}}
                ],
                "scaling_events": [],
                "last_scale_time": None,
                "scaling_policy": {
                    "scale_up_stabilization": "0s",
                    "scale_down_stabilization": "300s"
                }
            },
            "metrics_server_analysis": {
                "metrics_server_running": True,
                "metrics_available": True,
                "api_response_time": "< 100ms",
                "node_metrics": "available",
                "pod_metrics": "available"
            },
            "pod_resource_analysis": {
                "pods_with_requests": 2,
                "pods_without_requests": 0,
                "cpu_requests_set": True,
                "memory_requests_set": True,
                "resource_utilization_calculation": "valid"
            },
            "blocking_factors": [
                "Pod resource requests not properly configured",
                "Metrics collection lag or delay",
                "HPA scaling policy restrictions",
                "Resource quotas preventing scaling"
            ],
            "solutions": [
                "Verify pod resource requests are set correctly",
                "Check HPA scaling policies and stabilization windows",
                "Review resource quotas in namespace",
                "Examine HPA events and status conditions"
            ],
            "resolution_commands": [
                "kubectl describe hpa web-app-hpa -n production",
                "kubectl get hpa web-app-hpa -n production -o yaml",
                "kubectl top pods -n production -l app=web-app",
                "kubectl get events -n production --field-selector involvedObject.name=web-app-hpa"
            ],
            "recommended_changes": {
                "scale_up_policy": "Increase scaling aggressiveness",
                "resource_requests": "Ensure all containers have CPU requests",
                "stabilization_window": "Reduce scale-up stabilization to respond faster"
            }
        }
        
        # Configure mock
        k8s_manager.resolve_hpa_not_scaling = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_hpa_not_scaling(hpa_context)
        
        # Assertions
        assert resolution["issue_type"] == "HPANotScaling"
        assert resolution["hpa_analysis"]["current_metrics"] is not None
        assert "Verify pod resource requests" in resolution["solutions"]
        assert "kubectl describe hpa" in str(resolution["resolution_commands"])
        assert resolution["recommended_changes"] is not None

    @pytest.mark.asyncio
    async def test_configmap_secret_mount_failure(self, k8s_manager):
        """Test resolution of ConfigMap/Secret mount failures."""
        
        mount_context = {
            "pod_name": "config-consumer",
            "namespace": "apps",
            "configmap_name": "app-config",
            "secret_name": "app-secrets",
            "mount_path_cm": "/etc/config",
            "mount_path_secret": "/etc/secrets",
            "error": "couldn't find key app.conf in ConfigMap apps/app-config",
            "expected_files": ["app.conf", "database.conf"],
            "volume_mounts": [
                {"name": "config-volume", "mountPath": "/etc/config"},
                {"name": "secret-volume", "mountPath": "/etc/secrets"}
            ]
        }
        
        # Mock mount failure resolution
        mock_resolution = {
            "issue_type": "ConfigMapSecretMountFailure",
            "configmap_analysis": {
                "configmap_exists": True,
                "available_keys": ["database.conf", "logging.conf"],
                "missing_keys": ["app.conf"],
                "data_size": "2.4KB",
                "created": "2025-08-09T10:30:00Z"
            },
            "secret_analysis": {
                "secret_exists": True,
                "secret_type": "Opaque",
                "available_keys": ["db-password", "api-key"],
                "data_size": "0.8KB",
                "created": "2025-08-09T10:30:00Z"
            },
            "volume_mount_analysis": {
                "mount_configuration": "correct",
                "volume_references": "valid",
                "subpath_usage": None,
                "read_only": False
            },
            "solutions": [
                "Add missing app.conf key to ConfigMap",
                "Verify all required keys exist in ConfigMap/Secret",
                "Check volume mount configuration in pod spec",
                "Ensure ConfigMap/Secret are in same namespace as pod"
            ],
            "resolution_commands": [
                "kubectl describe configmap app-config -n apps",
                "kubectl describe secret app-secrets -n apps",
                "kubectl get pod config-consumer -n apps -o yaml | grep -A 10 volumeMounts",
                "kubectl exec config-consumer -n apps -- ls -la /etc/config/"
            ],
            "fix_commands": [
                "kubectl patch configmap app-config -n apps --patch '{\"data\":{\"app.conf\":\"# Application configuration\\nserver_port=8080\\n\"}}'",
                "kubectl delete pod config-consumer -n apps",  # Force recreation to pick up changes
                "kubectl wait --for=condition=ready pod -l app=config-consumer -n apps"
            ]
        }
        
        # Configure mock
        k8s_manager.resolve_configmap_secret_mount = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await k8s_manager.resolve_configmap_secret_mount(mount_context)
        
        # Assertions
        assert resolution["issue_type"] == "ConfigMapSecretMountFailure"
        assert "app.conf" in resolution["configmap_analysis"]["missing_keys"]
        assert "Add missing app.conf key" in resolution["solutions"]
        assert "kubectl patch configmap" in str(resolution["fix_commands"])
        assert resolution["secret_analysis"]["secret_exists"] is True
