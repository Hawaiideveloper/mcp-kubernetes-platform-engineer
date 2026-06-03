# Section 17 — Deterministic Remediation Table

## Overview

LLMs produce explanations. Deterministic functions produce commands. Every
remediation in this section is a pure function: given a `Finding` object and
the live Kubernetes state, it returns a `FixCandidate` that can be applied
without further human reasoning. The framework enforces this contract through
the `Remediation` protocol defined below.

---

## The Remediation Protocol

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Finding:
    uid: str                        # stable identifier from audit engine
    behavior: str                   # e.g. "image_tag_migration_remediation"
    namespace: str
    resource_kind: str              # Deployment, Job, Pod, PVC, …
    resource_name: str
    container_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

@dataclass
class FixCandidate:
    description: str
    patch_type: str                 # "strategic-merge" | "json-patch" | "kubectl-cmd"
    payload: str | list[dict]       # YAML string or JSON-patch list or shell command
    requires_review: bool = False   # True for changes that must go through PR
    references: list[str] = field(default_factory=list)

class Remediation(ABC):
    @abstractmethod
    def applies_to(self, finding: Finding) -> bool: ...

    @abstractmethod
    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate: ...
```

---

## Remediation Table

### 1. ImageTagMigration

**Applies to:** `ImagePullBackOff` where the registry returns `404 Not Found`
for the current image tag. Handles known yanked/renamed images.

```python
KNOWN_MIGRATIONS: dict[str, str] = {
    "bitnami/kubectl:1.30":             "registry.k8s.io/kubectl:v1.30.12",
    "bitnami/kubectl:1.29":             "registry.k8s.io/kubectl:v1.29.9",
    "k8s.gcr.io/pause:3.8":            "registry.k8s.io/pause:3.8",
    "k8s.gcr.io/coredns/coredns:v1.9": "registry.k8s.io/coredns/coredns:v1.9.3",
}

class ImageTagMigration(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return (
            finding.behavior == "image_tag_migration_remediation"
            and finding.raw.get("reason") == "ImagePullBackOff"
        )

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        current_image = finding.raw["current_image"]
        new_image = KNOWN_MIGRATIONS.get(current_image)
        if new_image is None:
            raise ValueError(f"No migration mapping for {current_image!r}")
        patch = {
            "spec": {"template": {"spec": {"containers": [
                {"name": finding.container_name, "image": new_image}
            ]}}}
        }
        return FixCandidate(
            description=f"Migrate {current_image} -> {new_image}",
            patch_type="strategic-merge",
            payload=patch,
            references=["https://kubernetes.io/blog/2023/03/10/image-registry-redirect/"],
        )
```

**Smoke test:** Apply patch to a test namespace; confirm pod reaches `Running`
within 120 s; verify `kubectl get deployment -o jsonpath='{.spec.template.spec.containers[0].image}'`
equals the new tag.

---

### 2. ProbeTuning

**Applies to:** `probe_tuning_remediation` findings where a readiness or
liveness probe reports `connection refused` during container startup.

```python
class ProbeTuning(Remediation):
    STARTUP_INITIAL_DELAY = 10
    STARTUP_FAILURE_THRESHOLD = 30
    STARTUP_PERIOD = 5

    def applies_to(self, finding: Finding) -> bool:
        return finding.behavior == "probe_tuning_remediation"

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        container = finding.container_name
        existing_probe = finding.raw.get("existing_liveness_probe", {})
        startup_probe = {
            "httpGet": existing_probe.get("httpGet") or existing_probe.get("tcpSocket"),
            "initialDelaySeconds": self.STARTUP_INITIAL_DELAY,
            "periodSeconds": self.STARTUP_PERIOD,
            "failureThreshold": self.STARTUP_FAILURE_THRESHOLD,
        }
        patch = {
            "spec": {"template": {"spec": {"containers": [
                {"name": container, "startupProbe": startup_probe}
            ]}}}
        }
        return FixCandidate(
            description=f"Add startupProbe to {container}; failureThreshold={self.STARTUP_FAILURE_THRESHOLD}",
            patch_type="strategic-merge",
            payload=patch,
            references=["https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/"],
        )
```

**Smoke test:** Deploy with patch; assert pod does not restart within the first
`failureThreshold * periodSeconds` seconds; confirm readiness gate passes.

---

### 3. OrphanJobCleanup

**Applies to:** Jobs present in the cluster that no known controller owns (see
Section 13 — orphan job detection).

```python
class OrphanJobCleanup(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return (
            finding.behavior == "orphan_job_remediation"
            and finding.resource_kind == "Job"
        )

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        cmd = (
            f"kubectl delete job {finding.resource_name} "
            f"-n {finding.namespace} --cascade=foreground"
        )
        return FixCandidate(
            description=f"Delete orphan Job {finding.namespace}/{finding.resource_name}",
            patch_type="kubectl-cmd",
            payload=cmd,
            requires_review=True,
            references=["https://kubernetes.io/docs/concepts/workloads/controllers/job/"],
        )
```

**Smoke test:** Verify job is absent post-delete; confirm dependent pods
terminated; assert no side-effects on sibling jobs sharing the same label
selector.

---

### 4. OOMKilledRestartWithBumpProposal

**Applies to:** Pods in `OOMKilled` state. A bare restart will re-OOM; instead
emit a proposed memory limit increase and file it for review.

```python
class OOMKilledRestartWithBumpProposal(Remediation):
    DEFAULT_BUMP_PERCENT = 30

    def applies_to(self, finding: Finding) -> bool:
        return finding.raw.get("reason") == "OOMKilled"

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        bump_pct = finding.raw.get("bump_percent", self.DEFAULT_BUMP_PERCENT)
        current_mem = finding.raw["current_memory_limit_bytes"]
        new_mem_mib = int(current_mem * (1 + bump_pct / 100) / 2**20)
        patch = {
            "spec": {"template": {"spec": {"containers": [
                {"name": finding.container_name,
                 "resources": {"limits": {"memory": f"{new_mem_mib}Mi"}}}
            ]}}}
        }
        return FixCandidate(
            description=f"Propose memory limit {current_mem // 2**20}Mi -> {new_mem_mib}Mi (+{bump_pct}%)",
            patch_type="strategic-merge",
            payload=patch,
            requires_review=True,
            references=["https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/"],
        )
```

**Smoke test:** Apply in staging only; run load scenario that previously caused
OOM; assert `OOMKilled` event count is zero over a 10-minute window.

---

### 5. PVCResize

**Applies to:** PVCs whose usage exceeds 85 % of capacity, where the underlying
StorageClass has `allowVolumeExpansion: true`.

```python
class PVCResize(Remediation):
    DEFAULT_GROWTH_PERCENT = 50

    def applies_to(self, finding: Finding) -> bool:
        sc = finding.raw.get("storage_class_allow_expansion", False)
        usage_pct = finding.raw.get("usage_percent", 0)
        return finding.resource_kind == "PersistentVolumeClaim" and sc and usage_pct > 85

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        current_gi = finding.raw["capacity_gi"]
        growth = finding.raw.get("growth_percent", self.DEFAULT_GROWTH_PERCENT)
        new_gi = int(current_gi * (1 + growth / 100))
        patch = {"spec": {"resources": {"requests": {"storage": f"{new_gi}Gi"}}}}
        return FixCandidate(
            description=f"Expand PVC {finding.resource_name} {current_gi}Gi -> {new_gi}Gi",
            patch_type="strategic-merge",
            payload=patch,
            references=["https://kubernetes.io/docs/concepts/storage/persistent-volumes/#expanding-persistent-volumes-claims"],
        )
```

**Smoke test:** Patch PVC; confirm `kubectl get pvc` shows new capacity within
resize-controller reconcile window (usually < 60 s for online expansion); assert
workload pod remains running with no restart.

---

### 6. DNSConfigFix

**Applies to:** Pods failing kube-dns resolution because `dnsPolicy` is set to
`None` without a matching `dnsConfig`, or set to `Default` in a host-network
pod that bypasses cluster DNS.

```python
class DNSConfigFix(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return finding.behavior == "dns_resolution_failure"

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        cluster_dns_ip = k8s_state.get("cluster_dns_ip", "10.96.0.10")
        patch = {
            "spec": {"template": {"spec": {
                "dnsPolicy": "ClusterFirst",
                "dnsConfig": {
                    "nameservers": [cluster_dns_ip],
                    "searches": [
                        f"{finding.namespace}.svc.cluster.local",
                        "svc.cluster.local",
                        "cluster.local",
                    ],
                },
            }}}
        }
        return FixCandidate(
            description=f"Set dnsPolicy=ClusterFirst and inject dnsConfig for {finding.resource_name}",
            patch_type="strategic-merge",
            payload=patch,
            references=["https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/"],
        )
```

**Smoke test:** `kubectl exec <pod> -- nslookup kubernetes.default`; assert
exits 0 and returns the ClusterIP.

---

### 7. NodeSelectorMismatch

**Applies to:** Pods stuck in `Pending` because their `nodeSelector` matches no
currently schedulable node.

```python
class NodeSelectorMismatch(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return (
            finding.raw.get("reason") == "Unschedulable"
            and "MatchNodeSelector" in finding.raw.get("message", "")
        )

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        # Derive the corrected label value from the set of actual node labels.
        correct_key = finding.raw["mismatched_label_key"]
        available_values = k8s_state.get("node_label_values", {}).get(correct_key, [])
        if not available_values:
            raise ValueError(f"No nodes carry label {correct_key!r}; manual intervention required")
        patch = {
            "spec": {"template": {"spec": {
                "nodeSelector": {correct_key: available_values[0]}
            }}}
        }
        return FixCandidate(
            description=f"Correct nodeSelector {correct_key}={available_values[0]}",
            patch_type="strategic-merge",
            payload=patch,
            requires_review=True,
            references=["https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/"],
        )
```

**Smoke test:** After patch, assert pod leaves `Pending` within 60 s; confirm
target node's labels include the patched value.

---

### 8. TolerationMissing

**Applies to:** Pods stuck in `Pending` because all candidate nodes carry taints
that the pod does not tolerate.

```python
class TolerationMissing(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return (
            finding.raw.get("reason") == "Unschedulable"
            and "untolerated taint" in finding.raw.get("message", "").lower()
        )

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        taint = finding.raw["blocking_taint"]   # {"key": ..., "effect": ..., "value": ...}
        toleration = {
            "key": taint["key"],
            "operator": "Equal",
            "value": taint.get("value", ""),
            "effect": taint["effect"],
        }
        patch = {
            "spec": {"template": {"spec": {
                "tolerations": [toleration]
            }}}
        }
        return FixCandidate(
            description=f"Add toleration for taint {taint['key']}={taint.get('value','')}:{taint['effect']}",
            patch_type="strategic-merge",
            payload=patch,
            requires_review=True,
            references=["https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/"],
        )
```

**Smoke test:** Assert pod schedules on the tainted node; assert taint is not
removed (fix is on the pod, not the node).

---

### 9. HPAEnableMetricsServer

**Applies to:** HPAs reporting `unable to get metrics for resource` or
`no metrics server installed`.

```python
METRICS_SERVER_MANIFEST = "https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"

class HPAEnableMetricsServer(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return (
            finding.resource_kind == "HorizontalPodAutoscaler"
            and "unable to get metrics" in finding.raw.get("message", "").lower()
        )

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        metrics_installed = k8s_state.get("metrics_server_deployed", False)
        if not metrics_installed:
            cmd = f"kubectl apply -f {METRICS_SERVER_MANIFEST}"
        else:
            # metrics-server present but RBAC broken; patch ClusterRole
            cmd = (
                "kubectl patch clusterrolebinding system:metrics-server "
                "--type=json "
                "-p '[{\"op\":\"add\",\"path\":\"/subjects/-\","
                "\"value\":{\"kind\":\"ServiceAccount\","
                "\"name\":\"metrics-server\","
                "\"namespace\":\"kube-system\"}}]'"
            )
        return FixCandidate(
            description="Install metrics-server or repair its RBAC so HPA can scrape resource metrics",
            patch_type="kubectl-cmd",
            payload=cmd,
            references=[
                "https://github.com/kubernetes-sigs/metrics-server",
                "https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/",
            ],
        )
```

**Smoke test:** `kubectl top nodes` exits 0; HPA `TARGETS` column shows
`<current>/<desired>` rather than `<unknown>`; trigger a load spike and assert
replica count changes.

---

### 10. PDBTooStrict

**Applies to:** `PodDisruptionBudget` objects blocking node drains because
`minAvailable` equals the total replica count, leaving zero disruption budget.

```python
class PDBTooStrict(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return (
            finding.resource_kind == "PodDisruptionBudget"
            and finding.raw.get("disruptions_allowed", 0) == 0
        )

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        replicas = finding.raw["matched_pods"]
        # Allow at least 1 disruption; if single replica, we cannot avoid downtime.
        if replicas <= 1:
            raise ValueError(
                f"PDB {finding.resource_name}: only {replicas} replica(s). "
                "Scale up before relaxing PDB."
            )
        new_min = replicas - 1
        patch = {"spec": {"minAvailable": new_min}}
        return FixCandidate(
            description=f"Relax PDB {finding.resource_name}: minAvailable {replicas} -> {new_min}",
            patch_type="strategic-merge",
            payload=patch,
            requires_review=True,
            references=["https://kubernetes.io/docs/tasks/run-application/configure-pdb/"],
        )
```

**Smoke test:** `kubectl drain <node> --ignore-daemonsets --delete-emptydir-data`
completes without `Cannot evict pod` errors; assert workload maintains quorum
throughout.

---

## Dispatch Logic

The audit engine iterates findings and selects the first matching remediation:

```python
REGISTRY: list[Remediation] = [
    ImageTagMigration(),
    ProbeTuning(),
    OrphanJobCleanup(),
    OOMKilledRestartWithBumpProposal(),
    PVCResize(),
    DNSConfigFix(),
    NodeSelectorMismatch(),
    TolerationMissing(),
    HPAEnableMetricsServer(),
    PDBTooStrict(),
]

def dispatch(finding: Finding, k8s_state: dict) -> FixCandidate | None:
    for handler in REGISTRY:
        if handler.applies_to(finding):
            return handler.generate_fix(finding, k8s_state)
    return None
```

All `FixCandidate` objects with `requires_review=True` are routed to the PR
workflow defined in Section 14. All others proceed to the sandbox execution
pipeline (Section 18).
