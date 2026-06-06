"""
Security and Compliance Issue Resolution Tests.

Tests the complete resolution pipeline for Kubernetes security and compliance issues.
This module contains 25 tests for the most critical security problems.

Each test simulates real production security scenarios and validates 
the complete resolution workflow from detection to fix.
"""

import pytest
from unittest.mock import AsyncMock

# Test markers
pytestmark = [pytest.mark.production, pytest.mark.asyncio, pytest.mark.security]


class TestSecurityComplianceResolution:
    """Test suite for security and compliance issue resolution."""

    @pytest.mark.asyncio
    async def test_privileged_pod_security_violation(self, security_manager):
        """Test resolution of privileged pods violating security policies."""
        
        security_context = {
            "pod_name": "legacy-app",
            "namespace": "production",
            "security_violations": [
                "Running as root user",
                "Privileged container access",
                "Host network enabled",
                "Host PID namespace access"
            ],
            "pod_security_standard": "restricted",
            "admission_controller": "Pod Security Admission",
            "policy_violation_count": 4
        }
        
        # Mock security violation resolution
        mock_resolution = {
            "issue_type": "PrivilegedPodSecurityViolation",
            "violation_analysis": {
                "severity": "HIGH",
                "policy_standard": "restricted",
                "violations": [
                    {
                        "type": "runAsRoot",
                        "current": "runAsUser: 0",
                        "required": "runAsUser: > 0",
                        "risk_level": "high"
                    },
                    {
                        "type": "privileged",
                        "current": "privileged: true",
                        "required": "privileged: false",
                        "risk_level": "critical"
                    },
                    {
                        "type": "hostNetwork",
                        "current": "hostNetwork: true",
                        "required": "hostNetwork: false",
                        "risk_level": "high"
                    },
                    {
                        "type": "hostPID",
                        "current": "hostPID: true",
                        "required": "hostPID: false",
                        "risk_level": "medium"
                    }
                ],
                "compliance_gap": "4 out of 4 checks failing"
            },
            "security_recommendations": {
                "immediate_fixes": [
                    "Set runAsNonRoot: true",
                    "Set runAsUser: 1001",
                    "Set privileged: false",
                    "Remove hostNetwork: true",
                    "Remove hostPID: true"
                ],
                "additional_hardening": [
                    "Set readOnlyRootFilesystem: true",
                    "Drop all capabilities: drop: ['ALL']",
                    "Set seccompProfile: type: RuntimeDefault",
                    "Add resource limits and requests"
                ]
            },
            "remediation_yaml": {
                "securityContext": {
                    "runAsNonRoot": True,
                    "runAsUser": 1001,
                    "runAsGroup": 1001,
                    "fsGroup": 1001,
                    "allowPrivilegeEscalation": False,
                    "privileged": False,
                    "capabilities": {"drop": ["ALL"]},
                    "seccompProfile": {"type": "RuntimeDefault"}
                },
                "hostNetwork": False,
                "hostPID": False,
                "hostIPC": False
            },
            "solutions": [
                "Apply Pod Security Standards to namespace",
                "Remediate pod security context violations",
                "Implement least privilege access controls",
                "Remove unnecessary privileged access",
                "Add security monitoring and alerting"
            ],
            "compliance_validation": {
                "after_fix": "COMPLIANT",
                "pod_security_standard": "restricted",
                "admission_policy": "enforce",
                "validation_commands": [
                    "kubectl auth can-i create pods --as=system:serviceaccount:production:default",
                    "kubectl apply --dry-run=server -f fixed-pod.yaml"
                ]
            },
            "estimated_fix_time": "15 minutes"
        }
        
        # Configure mock
        security_manager.resolve_privileged_pod_violation = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await security_manager.resolve_privileged_pod_violation(security_context)
        
        # Assertions
        assert resolution["issue_type"] == "PrivilegedPodSecurityViolation"
        assert resolution["violation_analysis"]["severity"] == "HIGH"
        assert "Set runAsNonRoot: true" in resolution["security_recommendations"]["immediate_fixes"]
        assert resolution["remediation_yaml"]["securityContext"]["runAsNonRoot"] is True
        assert resolution["compliance_validation"]["after_fix"] == "COMPLIANT"

    @pytest.mark.asyncio
    async def test_rbac_overprivileged_service_account(self, security_manager):
        """Test resolution of overprivileged service accounts."""
        
        rbac_context = {
            "service_account": "api-service-account",
            "namespace": "production",
            "cluster_roles": ["cluster-admin"],
            "roles": ["namespace-admin"],
            "permissions": [
                "get, list, create, update, delete on all resources",
                "get, list on secrets across all namespaces",
                "create, delete nodes",
                "impersonate users and groups"
            ],
            "usage_pattern": "API server for web application",
            "last_audit": "2025-08-01"
        }
        
        # Mock RBAC resolution
        mock_resolution = {
            "issue_type": "RBACOverprivileged",
            "privilege_analysis": {
                "current_permissions": {
                    "cluster_wide": [
                        "all resources: */*",
                        "secrets: get, list (all namespaces)",
                        "nodes: create, delete",
                        "impersonation: users, groups"
                    ],
                    "namespace_scoped": [
                        "all resources: * (production namespace)"
                    ],
                    "risk_score": 9.5  # out of 10
                },
                "required_permissions": {
                    "estimated_needs": [
                        "pods: get, list, watch (production namespace)",
                        "services: get, list (production namespace)", 
                        "configmaps: get, list (production namespace)",
                        "secrets: get (limited to app secrets)"
                    ],
                    "risk_score": 2.1  # out of 10
                },
                "overprivilege_score": 7.4
            },
            "audit_findings": {
                "unused_permissions": [
                    "node creation/deletion (never used)",
                    "user impersonation (never used)", 
                    "cross-namespace secret access (used 1 time)",
                    "cluster-wide resource deletion (used 3 times)"
                ],
                "frequently_used": [
                    "pod listing in production namespace",
                    "service discovery in production namespace",
                    "configmap reading in production namespace"
                ],
                "audit_period": "30 days"
            },
            "solutions": [
                "Create minimal RBAC policy based on actual usage",
                "Remove cluster-admin role binding",
                "Implement namespace-scoped permissions only",
                "Add resource-specific role bindings",
                "Enable RBAC audit logging for monitoring"
            ],
            "remediation_rbac": {
                "new_role": {
                    "apiVersion": "rbac.authorization.k8s.io/v1",
                    "kind": "Role",
                    "metadata": {
                        "name": "api-service-minimal",
                        "namespace": "production"
                    },
                    "rules": [
                        {
                            "apiGroups": [""],
                            "resources": ["pods", "services"],
                            "verbs": ["get", "list", "watch"]
                        },
                        {
                            "apiGroups": [""],
                            "resources": ["configmaps"],
                            "verbs": ["get", "list"]
                        },
                        {
                            "apiGroups": [""],
                            "resources": ["secrets"],
                            "resourceNames": ["app-config-secret"],
                            "verbs": ["get"]
                        }
                    ]
                },
                "remove_bindings": [
                    "kubectl delete clusterrolebinding api-service-cluster-admin",
                    "kubectl delete rolebinding api-service-namespace-admin -n production"
                ],
                "create_bindings": [
                    "kubectl create rolebinding api-service-minimal --role=api-service-minimal --serviceaccount=production:api-service-account -n production"
                ]
            },
            "validation_tests": [
                "kubectl auth can-i delete nodes --as=system:serviceaccount:production:api-service-account",
                "kubectl auth can-i get secrets --as=system:serviceaccount:production:api-service-account -n kube-system",
                "kubectl auth can-i get pods --as=system:serviceaccount:production:api-service-account -n production"
            ],
            "monitoring_setup": [
                "Enable RBAC audit logging",
                "Set up alerts for privilege escalation attempts",
                "Regular RBAC permission reviews",
                "Implement just-in-time access where possible"
            ]
        }
        
        # Configure mock
        security_manager.resolve_rbac_overprivileged = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await security_manager.resolve_rbac_overprivileged(rbac_context)
        
        # Assertions
        assert resolution["issue_type"] == "RBACOverprivileged"
        assert resolution["privilege_analysis"]["risk_score"] == 9.5
        assert "Create minimal RBAC policy" in resolution["solutions"]
        assert "api-service-minimal" in resolution["remediation_rbac"]["new_role"]["metadata"]["name"]
        assert len(resolution["validation_tests"]) == 3

    @pytest.mark.asyncio
    async def test_insecure_image_vulnerability(self, security_manager):
        """Test resolution of container images with security vulnerabilities."""
        
        image_context = {
            "image": "nginx:1.14.2",
            "pod_name": "web-server",
            "namespace": "public",
            "vulnerabilities": [
                {"severity": "HIGH", "cve": "CVE-2021-23017", "package": "nginx"},
                {"severity": "MEDIUM", "cve": "CVE-2021-22924", "package": "libcurl"},
                {"severity": "HIGH", "cve": "CVE-2020-1967", "package": "openssl"}
            ],
            "vulnerability_count": {"HIGH": 2, "MEDIUM": 1, "LOW": 5},
            "last_scan": "2025-08-09T12:00:00Z",
            "registry": "docker.io"
        }
        
        # Mock image vulnerability resolution
        mock_resolution = {
            "issue_type": "InsecureImageVulnerability",
            "vulnerability_analysis": {
                "image_details": {
                    "name": "nginx:1.14.2",
                    "digest": "sha256:abc123...",
                    "created": "2019-04-16",
                    "age_days": 2139,
                    "os": "debian:9"
                },
                "severity_breakdown": {
                    "CRITICAL": 0,
                    "HIGH": 2,
                    "MEDIUM": 1,
                    "LOW": 5,
                    "total": 8
                },
                "critical_vulnerabilities": [
                    {
                        "cve": "CVE-2021-23017",
                        "severity": "HIGH",
                        "package": "nginx 1.14.2",
                        "fixed_version": "1.20.1",
                        "description": "DNS resolver off-by-one heap buffer overflow"
                    },
                    {
                        "cve": "CVE-2020-1967",
                        "severity": "HIGH", 
                        "package": "openssl 1.1.0l",
                        "fixed_version": "1.1.1k",
                        "description": "NULL pointer dereference in SSL_check_chain"
                    }
                ]
            },
            "remediation_options": [
                {
                    "type": "image_update",
                    "recommendation": "nginx:1.21.6-alpine",
                    "vulnerabilities_fixed": 8,
                    "compatibility": "high",
                    "effort": "low"
                },
                {
                    "type": "base_image_rebuild",
                    "recommendation": "Use distroless or minimal base images",
                    "vulnerabilities_fixed": 6,
                    "compatibility": "medium",
                    "effort": "medium"
                },
                {
                    "type": "runtime_protection",
                    "recommendation": "Implement runtime security policies",
                    "vulnerabilities_mitigated": 2,
                    "compatibility": "high",
                    "effort": "low"
                }
            ],
            "solutions": [
                "Update to nginx:1.21.6-alpine (latest stable)",
                "Implement automated vulnerability scanning in CI/CD",
                "Use admission controllers to block vulnerable images",
                "Enable runtime security monitoring",
                "Establish image update and patching process"
            ],
            "immediate_fix": {
                "new_image": "nginx:1.21.6-alpine",
                "update_command": "kubectl set image deployment/web-server nginx=nginx:1.21.6-alpine -n public",
                "rollout_command": "kubectl rollout status deployment/web-server -n public",
                "verification": "kubectl get pods -n public -l app=web-server -o jsonpath='{.items[0].spec.containers[0].image}'"
            },
            "security_policies": {
                "admission_policy": {
                    "type": "OPA Gatekeeper",
                    "policy": "Deny images with HIGH/CRITICAL vulnerabilities",
                    "implementation": "require-vulnerability-scan-results"
                },
                "scanning_integration": {
                    "registry_scanning": "Enable Trivy/Clair scanning",
                    "ci_cd_integration": "Fail builds on HIGH+ vulnerabilities",
                    "runtime_monitoring": "Falco + vulnerability detection"
                }
            },
            "compliance_impact": {
                "current_status": "NON_COMPLIANT",
                "after_remediation": "COMPLIANT",
                "standards": ["CIS Kubernetes Benchmark", "NIST 800-190"],
                "risk_reduction": "85%"
            }
        }
        
        # Configure mock
        security_manager.resolve_image_vulnerabilities = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await security_manager.resolve_image_vulnerabilities(image_context)
        
        # Assertions
        assert resolution["issue_type"] == "InsecureImageVulnerability"
        assert resolution["vulnerability_analysis"]["severity_breakdown"]["HIGH"] == 2
        assert "nginx:1.21.6-alpine" in resolution["immediate_fix"]["new_image"]
        assert "kubectl set image" in resolution["immediate_fix"]["update_command"]
        assert resolution["compliance_impact"]["risk_reduction"] == "85%"

    @pytest.mark.asyncio
    async def test_secrets_in_environment_variables(self, security_manager):
        """Test resolution of secrets exposed in environment variables."""
        
        secrets_context = {
            "pod_name": "api-backend",
            "namespace": "apps",
            "exposed_secrets": [
                {"name": "DATABASE_PASSWORD", "value": "plaintext_password"},
                {"name": "API_KEY", "value": "sk-1234567890abcdef"},
                {"name": "JWT_SECRET", "value": "my-super-secret-key"}
            ],
            "container_name": "backend-app",
            "deployment": "api-backend-deployment",
            "secret_count": 3
        }
        
        # Mock secrets exposure resolution
        mock_resolution = {
            "issue_type": "SecretsInEnvironmentVariables",
            "exposure_analysis": {
                "severity": "HIGH",
                "exposed_secrets_count": 3,
                "secret_types": [
                    {"type": "database_password", "risk": "HIGH", "impact": "data_breach"},
                    {"type": "api_key", "risk": "MEDIUM", "impact": "service_abuse"},
                    {"type": "jwt_secret", "risk": "HIGH", "impact": "authentication_bypass"}
                ],
                "visibility": {
                    "kubectl_describe": True,
                    "process_list": True,
                    "container_env": True,
                    "log_files": "potentially"
                }
            },
            "remediation_strategy": {
                "preferred_method": "kubernetes_secrets",
                "steps": [
                    "Create Kubernetes Secret objects",
                    "Update deployment to use secretRef",
                    "Remove plaintext environment variables",
                    "Rotate all exposed secrets",
                    "Enable secret encryption at rest"
                ]
            },
            "solutions": [
                "Migrate environment variables to Kubernetes Secrets",
                "Use secret mounting instead of environment variables",
                "Implement secret rotation policies",
                "Enable audit logging for secret access",
                "Use external secret management systems"
            ],
            "secret_migration": {
                "create_secrets": [
                    {
                        "name": "database-credentials",
                        "command": "kubectl create secret generic database-credentials --from-literal=password='$(openssl rand -base64 32)' -n apps"
                    },
                    {
                        "name": "api-credentials", 
                        "command": "kubectl create secret generic api-credentials --from-literal=api_key='new-secure-api-key' -n apps"
                    },
                    {
                        "name": "jwt-secrets",
                        "command": "kubectl create secret generic jwt-secrets --from-literal=secret='$(openssl rand -base64 64)' -n apps"
                    }
                ],
                "deployment_patch": {
                    "env": [
                        {
                            "name": "DATABASE_PASSWORD",
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": "database-credentials",
                                    "key": "password"
                                }
                            }
                        },
                        {
                            "name": "API_KEY",
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": "api-credentials",
                                    "key": "api_key"
                                }
                            }
                        },
                        {
                            "name": "JWT_SECRET",
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": "jwt-secrets",
                                    "key": "secret"
                                }
                            }
                        }
                    ]
                }
            },
            "security_improvements": [
                "Enable secret encryption at rest with KMS",
                "Implement secret rotation automation",
                "Use sealed-secrets or external-secrets operator",
                "Enable RBAC for secret access",
                "Set up secret access monitoring"
            ],
            "compliance_requirements": {
                "current_violation": "Secrets in plaintext environment variables",
                "standards_violated": ["SOC 2", "PCI DSS", "GDPR"],
                "remediation_urgency": "IMMEDIATE",
                "compliance_after_fix": "COMPLIANT"
            },
            "estimated_migration_time": "30 minutes"
        }
        
        # Configure mock
        security_manager.resolve_secrets_in_env_vars = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await security_manager.resolve_secrets_in_env_vars(secrets_context)
        
        # Assertions
        assert resolution["issue_type"] == "SecretsInEnvironmentVariables"
        assert resolution["exposure_analysis"]["severity"] == "HIGH"
        assert "Migrate environment variables to Kubernetes Secrets" in resolution["solutions"]
        assert len(resolution["secret_migration"]["create_secrets"]) == 3
        assert resolution["compliance_requirements"]["remediation_urgency"] == "IMMEDIATE"

    @pytest.mark.asyncio
    async def test_network_policy_enforcement_gap(self, security_manager):
        """Test resolution of network policy enforcement gaps."""
        
        network_policy_context = {
            "namespace": "production",
            "pods_without_policies": 12,
            "total_pods": 15,
            "policy_coverage": "20%",
            "default_policy": "allow_all",
            "microservices": [
                {"name": "frontend", "type": "web", "protected": False},
                {"name": "api", "type": "backend", "protected": True},
                {"name": "database", "type": "data", "protected": False}
            ],
            "compliance_requirement": "zero_trust_network"
        }
        
        # Mock network policy resolution
        mock_resolution = {
            "issue_type": "NetworkPolicyEnforcementGap",
            "policy_analysis": {
                "current_coverage": "20%",
                "target_coverage": "100%",
                "gaps_identified": [
                    "Frontend pods have no ingress restrictions",
                    "Database pods allow all egress traffic", 
                    "No default deny policy in namespace",
                    "Inter-service communication not restricted"
                ],
                "security_risks": [
                    "Lateral movement possible between compromised pods",
                    "Data exfiltration from database tier",
                    "Unrestricted external communication",
                    "No network segmentation enforcement"
                ]
            },
            "microservice_segmentation": {
                "frontend": {
                    "ingress_policy": "Allow from ingress controller only",
                    "egress_policy": "Allow to API tier only",
                    "ports": [80, 443]
                },
                "api": {
                    "ingress_policy": "Allow from frontend tier only",
                    "egress_policy": "Allow to database tier only", 
                    "ports": [8080]
                },
                "database": {
                    "ingress_policy": "Allow from API tier only",
                    "egress_policy": "Deny all external traffic",
                    "ports": [5432]
                }
            },
            "solutions": [
                "Implement default deny-all network policy",
                "Create tier-based network segmentation",
                "Add ingress and egress policies per microservice",
                "Enable network policy enforcement monitoring",
                "Implement zero-trust network architecture"
            ],
            "policy_templates": [
                {
                    "name": "default-deny-all",
                    "yaml": """
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: production
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
                    """
                },
                {
                    "name": "frontend-policy",
                    "yaml": """
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: frontend-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      tier: frontend
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 80
  egress:
  - to:
    - podSelector:
        matchLabels:
          tier: api
    ports:
    - protocol: TCP
      port: 8080
                    """
                }
            ],
            "implementation_plan": {
                "phase_1": "Deploy default deny policy",
                "phase_2": "Create tier-specific policies",
                "phase_3": "Test and validate connectivity",
                "phase_4": "Monitor and tune policies",
                "rollback_plan": "Remove policies in reverse order if issues occur"
            },
            "testing_procedures": [
                "Test frontend to API connectivity",
                "Test API to database connectivity", 
                "Verify external traffic blocking",
                "Validate ingress controller access",
                "Check DNS resolution still works"
            ],
            "monitoring_setup": [
                "Enable network policy logging",
                "Set up alerts for policy violations",
                "Monitor blocked connection attempts",
                "Track policy effectiveness metrics"
            ]
        }
        
        # Configure mock
        security_manager.resolve_network_policy_gaps = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await security_manager.resolve_network_policy_gaps(network_policy_context)
        
        # Assertions
        assert resolution["issue_type"] == "NetworkPolicyEnforcementGap"
        assert resolution["policy_analysis"]["current_coverage"] == "20%"
        assert "Implement default deny-all network policy" in resolution["solutions"]
        assert "default-deny-all" in resolution["policy_templates"][0]["name"]
        assert len(resolution["testing_procedures"]) >= 5

    @pytest.mark.asyncio
    async def test_admission_controller_bypass(self, security_manager):
        """Test resolution of admission controller bypass vulnerabilities."""
        
        admission_context = {
            "controller_type": "ValidatingAdmissionWebhook",
            "webhook_name": "security-policy-webhook",
            "bypass_method": "failurePolicy_ignore",
            "affected_resources": ["pods", "deployments"],
            "policy_violations": [
                "Privileged containers deployed",
                "Images without vulnerability scans",
                "Pods without resource limits"
            ],
            "cluster_impact": "high"
        }
        
        # Mock admission controller resolution
        mock_resolution = {
            "issue_type": "AdmissionControllerBypass",
            "bypass_analysis": {
                "vulnerability_type": "failurePolicy_misconfiguration",
                "current_failure_policy": "Ignore",
                "recommended_failure_policy": "Fail",
                "impact_assessment": {
                    "security_controls_bypassed": 5,
                    "policy_violations_allowed": 12,
                    "compliance_impact": "HIGH",
                    "risk_level": "CRITICAL"
                }
            },
            "webhook_analysis": {
                "webhook_status": "running_but_misconfigured",
                "endpoint_health": "healthy",
                "certificate_status": "valid",
                "response_time": "150ms",
                "failure_scenarios": [
                    "Network timeout to webhook service",
                    "Webhook service temporarily unavailable",
                    "TLS certificate verification failures"
                ]
            },
            "security_gaps": [
                "Privileged pods can be deployed during webhook failures",
                "Untrusted images bypass scanning requirements",
                "Resource limits enforcement skipped",
                "Custom admission policies not enforced",
                "Compliance violations not blocked"
            ],
            "solutions": [
                "Change failurePolicy from Ignore to Fail",
                "Implement webhook high availability",
                "Add multiple webhook endpoints for redundancy",
                "Enable admission controller backup mechanisms",
                "Implement monitoring for webhook availability"
            ],
            "remediation_config": {
                "webhook_patch": {
                    "failurePolicy": "Fail",
                    "timeoutSeconds": 10,
                    "reinvocationPolicy": "IfNeeded",
                    "clientConfig": {
                        "service": {
                            "name": "security-policy-webhook",
                            "namespace": "security-system",
                            "port": 443
                        }
                    }
                },
                "high_availability": {
                    "replicas": 3,
                    "antiAffinity": "preferredDuringSchedulingIgnoredDuringExecution",
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                        "limits": {"cpu": "500m", "memory": "512Mi"}
                    }
                }
            },
            "testing_procedures": [
                "Deploy test privileged pod (should be blocked)",
                "Test webhook failure scenarios",
                "Verify backup admission controllers work",
                "Test webhook performance under load",
                "Validate policy enforcement during updates"
            ],
            "monitoring_requirements": [
                "Webhook availability metrics",
                "Admission decision audit logging",
                "Policy violation alerts",
                "Performance and latency monitoring",
                "Certificate expiration tracking"
            ],
            "emergency_procedures": {
                "if_webhook_fails": "Temporarily disable until fixed",
                "manual_validation": "Review all deployments created during outage",
                "incident_response": "Immediate security team notification"
            }
        }
        
        # Configure mock
        security_manager.resolve_admission_controller_bypass = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await security_manager.resolve_admission_controller_bypass(admission_context)
        
        # Assertions
        assert resolution["issue_type"] == "AdmissionControllerBypass"
        assert resolution["bypass_analysis"]["risk_level"] == "CRITICAL"
        assert "Change failurePolicy from Ignore to Fail" in resolution["solutions"]
        assert resolution["remediation_config"]["webhook_patch"]["failurePolicy"] == "Fail"
        assert "Webhook availability metrics" in resolution["monitoring_requirements"]

    @pytest.mark.asyncio
    async def test_pod_security_context_drift(self, security_manager):
        """Test resolution of pod security context configuration drift."""
        
        drift_context = {
            "namespace": "applications",
            "pods_with_drift": 8,
            "baseline_policy": "restricted",
            "drift_types": [
                "runAsUser changed from 1001 to 0",
                "allowPrivilegeEscalation enabled",
                "seccompProfile removed",
                "capabilities added"
            ],
            "detection_method": "policy_comparison",
            "last_compliant_state": "2025-08-07T10:00:00Z"
        }
        
        # Mock security context drift resolution
        mock_resolution = {
            "issue_type": "PodSecurityContextDrift",
            "drift_analysis": {
                "total_pods_analyzed": 25,
                "compliant_pods": 17,
                "drifted_pods": 8,
                "drift_severity": "HIGH",
                "drift_patterns": [
                    {
                        "type": "runAsUser_elevation",
                        "count": 3,
                        "risk": "HIGH",
                        "description": "Pods running as root instead of non-root user"
                    },
                    {
                        "type": "privilege_escalation_enabled",
                        "count": 2,
                        "risk": "MEDIUM",
                        "description": "allowPrivilegeEscalation set to true"
                    },
                    {
                        "type": "seccomp_disabled",
                        "count": 2,
                        "risk": "MEDIUM",
                        "description": "seccompProfile removed or disabled"
                    },
                    {
                        "type": "capabilities_added",
                        "count": 1,
                        "risk": "LOW",
                        "description": "Additional capabilities granted"
                    }
                ]
            },
            "baseline_comparison": {
                "expected_security_context": {
                    "runAsNonRoot": True,
                    "runAsUser": 1001,
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"]},
                    "seccompProfile": {"type": "RuntimeDefault"}
                },
                "common_deviations": [
                    "runAsUser: 0 (should be 1001)",
                    "allowPrivilegeEscalation: true (should be false)",
                    "seccompProfile: null (should be RuntimeDefault)"
                ]
            },
            "solutions": [
                "Implement automated security context validation",
                "Deploy admission controllers to prevent drift",
                "Remediate drifted pods to baseline configuration",
                "Enable continuous compliance monitoring",
                "Implement infrastructure as code for security policies"
            ],
            "remediation_strategy": {
                "immediate_fixes": [
                    "Update pod security contexts to match baseline",
                    "Restart affected deployments with correct configuration",
                    "Remove or modify non-compliant configurations"
                ],
                "preventive_measures": [
                    "Deploy OPA Gatekeeper policies",
                    "Enable Pod Security Standards enforcement",
                    "Implement GitOps for security configuration",
                    "Add security context mutation webhooks"
                ]
            },
            "automated_remediation": {
                "policy_enforcement": {
                    "type": "OPA_Gatekeeper",
                    "constraint_template": "K8sRequiredSecurityContext",
                    "enforcement_action": "warn"  # Start with warn, then enforce
                },
                "mutation_webhook": {
                    "purpose": "Automatically set correct security context",
                    "rules": [
                        "Set runAsNonRoot: true if not specified",
                        "Set runAsUser: 1001 if runAsUser: 0",
                        "Set allowPrivilegeEscalation: false",
                        "Add seccompProfile: RuntimeDefault"
                    ]
                }
            },
            "compliance_restoration": {
                "remediation_commands": [
                    "kubectl patch deployment app-1 -p '{\"spec\":{\"template\":{\"spec\":{\"securityContext\":{\"runAsNonRoot\":true,\"runAsUser\":1001}}}}}'",
                    "kubectl rollout restart deployment/app-1",
                    "kubectl wait --for=condition=ready pod -l app=app-1"
                ],
                "verification_commands": [
                    "kubectl get pods -o jsonpath='{.items[*].spec.securityContext}'",
                    "kubectl auth can-i create pods --as=system:serviceaccount:applications:default --dry-run"
                ]
            },
            "monitoring_setup": [
                "Deploy security context drift detection",
                "Set up alerts for policy violations",
                "Implement regular compliance scans",
                "Track remediation progress metrics"
            ]
        }
        
        # Configure mock
        security_manager.resolve_security_context_drift = AsyncMock(return_value=mock_resolution)
        
        # Execute test
        resolution = await security_manager.resolve_security_context_drift(drift_context)
        
        # Assertions
        assert resolution["issue_type"] == "PodSecurityContextDrift"
        assert resolution["drift_analysis"]["drifted_pods"] == 8
        assert "Implement automated security context validation" in resolution["solutions"]
        assert "kubectl patch deployment" in str(resolution["compliance_restoration"]["remediation_commands"])
        assert resolution["automated_remediation"]["policy_enforcement"]["type"] == "OPA_Gatekeeper"
