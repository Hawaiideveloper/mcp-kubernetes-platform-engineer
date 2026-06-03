# Section 19 — RBAC Split: Read-Only Diagnosis vs. Namespaced Write

## Context

The system currently runs under a single ClusterRole with read-only access. As remediation
capabilities are implemented across sprints, RBAC must expand in a controlled and auditable way.
This section defines the four identities the system requires, the precise Kubernetes resources
each identity uses, and the full YAML for every ClusterRole, Role, ServiceAccount, and binding.

The central constraint: write authority is never cluster-wide. Applier identities are
namespace-scoped Role bindings, limited to namespaces in the safety allowlist (§6). Trading
namespaces have no applier identity at all — the RBAC itself enforces what the SafetyGate (§6)
enforces in code.

---

## Identity Summary

| Identity | Kind | Scope | Write | Used by |
|---|---|---|---|---|
| `auto-remediate-reader` | ClusterRole | Cluster-wide | No | Analyzer, watcher, classifier |
| `auto-remediate-applier-<ns>` | Role | Per non-trading namespace | Yes (limited) | Remediation executor |
| `auto-remediate-sandbox` | Role | `sandbox-*` namespaces | Full | vcluster controller |
| `auto-remediate-pr-bot` | None (no k8s RBAC) | N/A | No | PR generation |

Trading namespaces (`ibkr-live-trader`, `daxxon-trading`, `brightflow-live`) have no applier
Role bound. If the executor attempts to act in those namespaces, the Kubernetes API will reject
the request with 403 Forbidden before the SafetyGate (§6) even runs. Both defenses are required
and independent.

---

## Identity #1 — `auto-remediate-reader`

A ClusterRole granting read access to every resource the analyzer, watcher, and classifier need.
No write verbs. No escalate, bind, or impersonate. Bound to the `auto-remediate-reader`
ServiceAccount in the `auto-remediate` namespace.

```yaml
# k8s/rbac/reader-cluster-role.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: auto-remediate-reader
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
rules:
  - apiGroups: [""]
    resources:
      - pods
      - pods/log
      - pods/status
      - services
      - endpoints
      - configmaps
      - persistentvolumeclaims
      - persistentvolumes
      - events
      - nodes
      - namespaces
      - resourcequotas
      - limitranges
      - serviceaccounts
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources:
      - deployments
      - replicasets
      - statefulsets
      - daemonsets
    verbs: ["get", "list", "watch"]
  - apiGroups: ["batch"]
    resources:
      - jobs
      - cronjobs
    verbs: ["get", "list", "watch"]
  - apiGroups: ["networking.k8s.io"]
    resources:
      - ingresses
      - networkpolicies
    verbs: ["get", "list", "watch"]
  - apiGroups: ["policy"]
    resources:
      - poddisruptionbudgets
    verbs: ["get", "list", "watch"]
  - apiGroups: ["autoscaling"]
    resources:
      - horizontalpodautoscalers
    verbs: ["get", "list", "watch"]
  - apiGroups: ["rbac.authorization.k8s.io"]
    resources:
      - roles
      - rolebindings
      - clusterroles
      - clusterrolebindings
    verbs: ["get", "list", "watch"]
  - apiGroups: ["storage.k8s.io"]
    resources:
      - storageclasses
      - volumeattachments
    verbs: ["get", "list", "watch"]
  - apiGroups: ["metrics.k8s.io"]
    resources:
      - pods
      - nodes
    verbs: ["get", "list"]
```

```yaml
# k8s/rbac/reader-service-account.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: auto-remediate-reader
  namespace: auto-remediate
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
```

```yaml
# k8s/rbac/reader-cluster-role-binding.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: auto-remediate-reader
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: auto-remediate-reader
subjects:
  - kind: ServiceAccount
    name: auto-remediate-reader
    namespace: auto-remediate
```

---

## Identity #2 — `auto-remediate-applier-<ns>`

A namespace-scoped Role (not ClusterRole) created for each namespace in the safety allowlist.
Write verbs are constrained to the resources the remediation executor can mutate. Secrets,
Nodes, and ServiceAccounts are explicitly excluded. The Role and RoleBinding are generated
from a template; each namespace in `config/safety.yaml` that is not trading-tier and not
system-tier gets its own instance.

The pattern below uses `brightflow-dashboard` as a concrete example. The same template applies
to every allowlisted non-trading namespace.

```yaml
# k8s/rbac/applier-role-template.yaml
# One instance per namespace in the safety allowlist (non-trading, non-system).
# Replace <NAMESPACE> with the target namespace name.
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: auto-remediate-applier
  namespace: <NAMESPACE>
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: applier
rules:
  - apiGroups: ["apps"]
    resources:
      - deployments
    verbs: ["get", "patch", "update"]
  - apiGroups: [""]
    resources:
      - services
    verbs: ["get", "patch", "update"]
  - apiGroups: [""]
    resources:
      - configmaps
    verbs: ["get", "patch", "update", "delete"]
  - apiGroups: [""]
    resources:
      - persistentvolumeclaims
    verbs: ["get", "patch", "update", "delete"]
  # Pods: delete only (to trigger restart). No create, no exec.
  - apiGroups: [""]
    resources:
      - pods
    verbs: ["get", "delete"]
  # Explicitly omitted: secrets, nodes, serviceaccounts, clusterroles,
  # clusterrolebindings, roles, rolebindings.
```

```yaml
# k8s/rbac/applier-service-account.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: auto-remediate-applier
  namespace: auto-remediate
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: applier
```

```yaml
# k8s/rbac/applier-role-binding-template.yaml
# One instance per namespace in the safety allowlist (non-trading, non-system).
# Replace <NAMESPACE> with the target namespace name.
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: auto-remediate-applier
  namespace: <NAMESPACE>
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: applier
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: auto-remediate-applier
subjects:
  - kind: ServiceAccount
    name: auto-remediate-applier
    namespace: auto-remediate
```

Concrete instances for the stateless-web and batch namespaces currently in `config/safety.yaml`:

```yaml
# k8s/rbac/applier-role-brightflow-dashboard.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: auto-remediate-applier
  namespace: brightflow-dashboard
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: applier
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "patch", "update"]
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "patch", "update"]
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "patch", "update", "delete"]
  - apiGroups: [""]
    resources: ["persistentvolumeclaims"]
    verbs: ["get", "patch", "update", "delete"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "delete"]
```

```yaml
# k8s/rbac/applier-role-binding-brightflow-dashboard.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: auto-remediate-applier
  namespace: brightflow-dashboard
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: applier
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: auto-remediate-applier
subjects:
  - kind: ServiceAccount
    name: auto-remediate-applier
    namespace: auto-remediate
```

```yaml
# k8s/rbac/applier-role-triton-inference.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: auto-remediate-applier
  namespace: triton-inference
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: applier
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "patch", "update"]
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "patch", "update"]
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "patch", "update", "delete"]
  - apiGroups: [""]
    resources: ["persistentvolumeclaims"]
    verbs: ["get", "patch", "update", "delete"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "delete"]
```

```yaml
# k8s/rbac/applier-role-binding-triton-inference.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: auto-remediate-applier
  namespace: triton-inference
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: applier
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: auto-remediate-applier
subjects:
  - kind: ServiceAccount
    name: auto-remediate-applier
    namespace: auto-remediate
```

---

## Identity #3 — `auto-remediate-sandbox`

Used exclusively by the vcluster controller. Scoped to `sandbox-*` namespaces. Full write inside
those namespaces — the sandbox is an isolated environment used for pre-production verification,
and the vcluster controller must be able to create, modify, and destroy any resource there.

This identity is never bound outside `sandbox-*` namespaces. The label selector on the
RoleBinding is `namespace: sandbox-*`; a separate Role and RoleBinding must be created for each
active sandbox namespace. The sandbox controller creates and destroys these bindings as it
creates and destroys sandbox environments.

```yaml
# k8s/rbac/sandbox-role-template.yaml
# Replace <SANDBOX_NAMESPACE> with the actual sandbox namespace, e.g. sandbox-pr-42.
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: auto-remediate-sandbox
  namespace: <SANDBOX_NAMESPACE>
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: sandbox
rules:
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["*"]
```

```yaml
# k8s/rbac/sandbox-service-account.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: auto-remediate-sandbox
  namespace: auto-remediate
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: sandbox
```

```yaml
# k8s/rbac/sandbox-role-binding-template.yaml
# Replace <SANDBOX_NAMESPACE> with the actual sandbox namespace.
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: auto-remediate-sandbox
  namespace: <SANDBOX_NAMESPACE>
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: sandbox
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: auto-remediate-sandbox
subjects:
  - kind: ServiceAccount
    name: auto-remediate-sandbox
    namespace: auto-remediate
```

---

## Identity #4 — `auto-remediate-pr-bot`

No Kubernetes RBAC at all. The PR bot interacts exclusively with the GitHub API using a token
mounted as a Secret. It has no ServiceAccount token mounted and no Role or ClusterRole bound
to it. The pod spec for the PR bot must set `automountServiceAccountToken: false`.

```yaml
# k8s/rbac/pr-bot-service-account.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: auto-remediate-pr-bot
  namespace: auto-remediate
  labels:
    app.kubernetes.io/part-of: auto-remediate
    app.kubernetes.io/component: rbac
    auto-remediate/identity: pr-bot
automountServiceAccountToken: false
```

The GitHub token is injected via a Secret reference in the pod spec:

```yaml
# Relevant excerpt from the PR bot Deployment (not the full manifest).
spec:
  serviceAccountName: auto-remediate-pr-bot
  automountServiceAccountToken: false
  containers:
    - name: pr-bot
      env:
        - name: GITHUB_TOKEN
          valueFrom:
            secretKeyRef:
              name: auto-remediate-github-token
              key: token
```

No RoleBinding or ClusterRoleBinding is created for `auto-remediate-pr-bot`.

---

## Trading Namespaces — No Applier Identity

The trading namespaces (`ibkr-live-trader`, `daxxon-trading`, `brightflow-live`) have no
`auto-remediate-applier` Role or RoleBinding. This is intentional and must not be changed
without an explicit security review and operator sign-off. The absence of a binding means that
even if the SafetyGate (§6) were bypassed in code, the Kubernetes API server would return
403 Forbidden for any write attempt against these namespaces. Both the software gate and the
RBAC gate are required; neither alone is sufficient.

Any attempt to create applier bindings in trading namespaces must be rejected in code review.
A CI check must verify at pull-request time that no Role or RoleBinding named
`auto-remediate-applier` exists in any file targeting a trading namespace.

---

## Audit Hook — Applier Action Logging

Every action taken by the applier ServiceAccount must be logged with the ServiceAccount name as
a structured field in the audit record. This requirement connects to the audit log schema defined
in §18.

The executor must retrieve the acting ServiceAccount name from the pod's mounted service account
token or from the configured identity and include it in every audit record it emits:

```python
# Required fields in every audit record emitted by an applier action (§18 schema)
{
    "event": "applier_action",
    "timestamp": "<ISO-8601>",
    "service_account": "auto-remediate-applier",   # never omitted, never null
    "namespace": "<target namespace>",
    "resource_kind": "<Deployment|Service|ConfigMap|PVC|Pod>",
    "resource_name": "<name>",
    "verb": "<patch|update|delete>",
    "dry_run": False,
    "session_id": "<remediation session UUID>",
    "result": "<success|error>",
    "error_detail": "<string or null>",
}
```

If the audit log write fails before the action is taken, the action must not proceed. If the
audit log write fails after the action is taken, the failure must be surfaced as a critical alert
and the session must be marked degraded. The service_account field is sourced from the
`APPLIER_SERVICE_ACCOUNT_NAME` environment variable, which the Deployment sets to
`auto-remediate-applier`. It is not derived at runtime from the token to avoid a parsing
dependency; the env var is authoritative.

---

## Rollout Order

1. Apply reader ClusterRole and ClusterRoleBinding first (Sprint 1, day 1). This is safe and
   unblocks analyzer implementation.
2. Apply pr-bot ServiceAccount (Sprint 1, day 1). No RBAC risk.
3. Apply sandbox Role template and ServiceAccount (Sprint 2, before vcluster integration).
   Bindings are created per-sandbox at runtime.
4. Apply applier Role and RoleBinding for each non-trading namespace (Sprint 2, after sandbox
   verification passes end-to-end). Gate behind a feature flag until at least one sandbox
   cycle has been observed to succeed.
5. Never apply applier bindings to trading namespaces. No future sprint changes this constraint
   without a written operator decision recorded in the audit log.
