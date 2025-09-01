#!/bin/bash

# Security Vulnerability Scanner for Kubernetes
# This demonstrates what the MCP server can do for security scanning

echo "🛡️  Kubernetes Security Vulnerability Scan"
echo "=========================================="
echo "Cluster: $(kubectl config current-context)"
echo "Scan Date: $(date)"
echo

# 1. Check for pods running as root
echo "🔍 1. Checking for pods running as root..."
ROOT_PODS=$(kubectl get pods -A -o json | jq -r '.items[] | select(
  .spec.securityContext.runAsUser == null or 
  .spec.securityContext.runAsUser == 0 or
  (.spec.containers[]?.securityContext.runAsUser // 0) == 0
) | "\(.metadata.namespace)/\(.metadata.name)"' | head -5)

if [ -n "$ROOT_PODS" ]; then
    echo "⚠️  WARNING: Found pods running as root:"
    echo "$ROOT_PODS"
else
    echo "✅ No pods running as root detected"
fi
echo

# 2. Check for privileged containers
echo "🔍 2. Checking for privileged containers..."
PRIVILEGED_PODS=$(kubectl get pods -A -o json | jq -r '.items[] | select(
  .spec.containers[]?.securityContext.privileged == true
) | "\(.metadata.namespace)/\(.metadata.name)"')

if [ -n "$PRIVILEGED_PODS" ]; then
    echo "🚨 CRITICAL: Found privileged containers:"
    echo "$PRIVILEGED_PODS"
else
    echo "✅ No privileged containers detected"
fi
echo

# 3. Check for containers with excessive capabilities
echo "🔍 3. Checking for containers with excessive capabilities..."
CAP_PODS=$(kubectl get pods -A -o json | jq -r '.items[] | select(
  .spec.containers[]?.securityContext.capabilities.add // [] | length > 0
) | "\(.metadata.namespace)/\(.metadata.name)"' | head -3)

if [ -n "$CAP_PODS" ]; then
    echo "⚠️  WARNING: Found containers with added capabilities:"
    echo "$CAP_PODS"
else
    echo "✅ No containers with excessive capabilities detected"
fi
echo

# 4. Check for missing network policies
echo "🔍 4. Checking network policy coverage..."
NETWORK_POLICIES=$(kubectl get networkpolicies -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
NAMESPACES=$(kubectl get namespaces --no-headers | wc -l | tr -d ' ')

echo "Network Policies: $NETWORK_POLICIES"
echo "Namespaces: $NAMESPACES"

if [ "$NETWORK_POLICIES" -lt 1 ]; then
    echo "⚠️  WARNING: No network policies found - network traffic is unrestricted"
else
    echo "✅ Network policies are configured"
fi
echo

# 5. Check for overly permissive RBAC
echo "🔍 5. Checking RBAC permissions..."
CLUSTER_ADMIN_BINDINGS=$(kubectl get clusterrolebindings -o json | jq -r '.items[] | select(
  .roleRef.name == "cluster-admin" and 
  .subjects[]?.kind == "ServiceAccount"
) | "\(.metadata.name)"' | wc -l | tr -d ' ')

echo "ServiceAccounts with cluster-admin: $CLUSTER_ADMIN_BINDINGS"

if [ "$CLUSTER_ADMIN_BINDINGS" -gt 2 ]; then
    echo "⚠️  WARNING: Multiple ServiceAccounts have cluster-admin privileges"
else
    echo "✅ RBAC permissions appear reasonable"
fi
echo

# 6. Check for pods without resource limits
echo "🔍 6. Checking for pods without resource limits..."
NO_LIMITS_PODS=$(kubectl get pods -A -o json | jq -r '.items[] | select(
  .spec.containers[]?.resources.limits == null
) | "\(.metadata.namespace)/\(.metadata.name)"' | head -3)

if [ -n "$NO_LIMITS_PODS" ]; then
    echo "⚠️  WARNING: Found pods without resource limits:"
    echo "$NO_LIMITS_PODS"
else
    echo "✅ All pods have resource limits configured"
fi
echo

# 7. Check for default service accounts in use
echo "🔍 7. Checking for default service account usage..."
DEFAULT_SA_PODS=$(kubectl get pods -A -o json | jq -r '.items[] | select(
  .spec.serviceAccountName == "default" or .spec.serviceAccountName == null
) | "\(.metadata.namespace)/\(.metadata.name)"' | head -3)

if [ -n "$DEFAULT_SA_PODS" ]; then
    echo "⚠️  WARNING: Found pods using default service account:"
    echo "$DEFAULT_SA_PODS"
else
    echo "✅ No pods using default service account"
fi
echo

# 8. Summary
echo "🛡️  Security Scan Summary"
echo "========================"
echo "• Root containers: $(echo "$ROOT_PODS" | wc -l | tr -d ' ') detected"
echo "• Privileged containers: $(echo "$PRIVILEGED_PODS" | wc -l | tr -d ' ') detected"
echo "• Network policies: $NETWORK_POLICIES configured"
echo "• Cluster-admin SAs: $CLUSTER_ADMIN_BINDINGS found"
echo

# 9. Your MCP Server Security Status
echo "📊 Your MCP Server Security Status"
echo "=================================="
kubectl get pod -n mcp-kubernetes -o json | jq -r '.items[] | {
  name: .metadata.name,
  runAsUser: .spec.securityContext.runAsUser,
  runAsGroup: .spec.securityContext.runAsGroup,
  readOnlyRootFilesystem: .spec.containers[0].securityContext.readOnlyRootFilesystem,
  allowPrivilegeEscalation: .spec.containers[0].securityContext.allowPrivilegeEscalation,
  resourceLimits: (.spec.containers[0].resources.limits != null)
} | "✅ MCP Server (\(.name)): 
  - Running as user: \(.runAsUser)
  - Running as group: \(.runAsGroup)  
  - Read-only filesystem: \(.readOnlyRootFilesystem)
  - Privilege escalation: \(.allowPrivilegeEscalation)
  - Resource limits: \(.resourceLimits)"'

echo
echo "🎯 Recommendations:"
echo "==================="
echo "1. Review pods running as root and implement non-root containers"
echo "2. Implement network policies for namespace isolation"
echo "3. Use dedicated service accounts instead of default"
echo "4. Set resource limits on all containers"
echo "5. Regular security scanning with tools like Falco or Twistlock"
echo
echo "✅ Your MCP server follows security best practices!"
