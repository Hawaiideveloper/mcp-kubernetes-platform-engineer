"""
deterministic_remediation.py — US-017: Deterministic Remediation Table

Pure-function fixers for 10 known failure patterns.
Each Remediation subclass returns a FixCandidate without LLM involvement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    uid: str
    behavior: str
    namespace: str
    resource_kind: str
    resource_name: str
    container_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FixCandidate:
    description: str
    patch_type: str          # "strategic-merge" | "json-patch" | "kubectl-cmd"
    payload: str | list[dict] | dict
    requires_review: bool = False
    references: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Remediation base class
# ---------------------------------------------------------------------------

class Remediation(ABC):
    @abstractmethod
    def applies_to(self, finding: Finding) -> bool: ...

    @abstractmethod
    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate: ...


# ---------------------------------------------------------------------------
# 1. ImageTagMigration
# ---------------------------------------------------------------------------

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
        patch: dict[str, Any] = {
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


# ---------------------------------------------------------------------------
# 2. ProbeTuning
# ---------------------------------------------------------------------------

class ProbeTuning(Remediation):
    STARTUP_INITIAL_DELAY = 10
    STARTUP_FAILURE_THRESHOLD = 30
    STARTUP_PERIOD = 5

    def applies_to(self, finding: Finding) -> bool:
        return finding.behavior == "probe_tuning_remediation"

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        container = finding.container_name
        existing_probe = finding.raw.get("existing_liveness_probe", {})
        startup_probe: dict[str, Any] = {
            "httpGet": existing_probe.get("httpGet") or existing_probe.get("tcpSocket"),
            "initialDelaySeconds": self.STARTUP_INITIAL_DELAY,
            "periodSeconds": self.STARTUP_PERIOD,
            "failureThreshold": self.STARTUP_FAILURE_THRESHOLD,
        }
        patch: dict[str, Any] = {
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


# ---------------------------------------------------------------------------
# 3. OrphanJobCleanup
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 4. OOMKilledRestartWithBumpProposal
# ---------------------------------------------------------------------------

class OOMKilledRestartWithBumpProposal(Remediation):
    DEFAULT_BUMP_PERCENT = 30

    def applies_to(self, finding: Finding) -> bool:
        return finding.raw.get("reason") == "OOMKilled"

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        bump_pct = finding.raw.get("bump_percent", self.DEFAULT_BUMP_PERCENT)
        current_mem = finding.raw["current_memory_limit_bytes"]
        new_mem_mib = int(current_mem * (1 + bump_pct / 100) / 2**20)
        patch: dict[str, Any] = {
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


# ---------------------------------------------------------------------------
# 5. PVCResize
# ---------------------------------------------------------------------------

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
        patch: dict[str, Any] = {"spec": {"resources": {"requests": {"storage": f"{new_gi}Gi"}}}}
        return FixCandidate(
            description=f"Expand PVC {finding.resource_name} {current_gi}Gi -> {new_gi}Gi",
            patch_type="strategic-merge",
            payload=patch,
            references=["https://kubernetes.io/docs/concepts/storage/persistent-volumes/#expanding-persistent-volumes-claims"],
        )


# ---------------------------------------------------------------------------
# 6. DNSConfigFix
# ---------------------------------------------------------------------------

class DNSConfigFix(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return finding.behavior == "dns_resolution_failure"

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        cluster_dns_ip = k8s_state.get("cluster_dns_ip", "10.96.0.10")
        patch: dict[str, Any] = {
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


# ---------------------------------------------------------------------------
# 7. NodeSelectorMismatch
# ---------------------------------------------------------------------------

class NodeSelectorMismatch(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return (
            finding.raw.get("reason") == "Unschedulable"
            and "MatchNodeSelector" in finding.raw.get("message", "")
        )

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        correct_key = finding.raw["mismatched_label_key"]
        available_values = k8s_state.get("node_label_values", {}).get(correct_key, [])
        if not available_values:
            raise ValueError(f"No nodes carry label {correct_key!r}; manual intervention required")
        patch: dict[str, Any] = {
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


# ---------------------------------------------------------------------------
# 8. TolerationMissing
# ---------------------------------------------------------------------------

class TolerationMissing(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return (
            finding.raw.get("reason") == "Unschedulable"
            and "untolerated taint" in finding.raw.get("message", "").lower()
        )

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        taint = finding.raw["blocking_taint"]
        toleration: dict[str, Any] = {
            "key": taint["key"],
            "operator": "Equal",
            "value": taint.get("value", ""),
            "effect": taint["effect"],
        }
        patch: dict[str, Any] = {
            "spec": {"template": {"spec": {
                "tolerations": [toleration]
            }}}
        }
        return FixCandidate(
            description=f"Add toleration for taint {taint['key']}={taint.get('value', '')}:{taint['effect']}",
            patch_type="strategic-merge",
            payload=patch,
            requires_review=True,
            references=["https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/"],
        )


# ---------------------------------------------------------------------------
# 9. HPAEnableMetricsServer
# ---------------------------------------------------------------------------

METRICS_SERVER_MANIFEST = (
    "https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"
)


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


# ---------------------------------------------------------------------------
# 10. PDBTooStrict
# ---------------------------------------------------------------------------

class PDBTooStrict(Remediation):
    def applies_to(self, finding: Finding) -> bool:
        return (
            finding.resource_kind == "PodDisruptionBudget"
            and finding.raw.get("disruptions_allowed", 0) == 0
        )

    def generate_fix(self, finding: Finding, k8s_state: dict) -> FixCandidate:
        replicas = finding.raw["matched_pods"]
        if replicas <= 1:
            raise ValueError(
                f"PDB {finding.resource_name}: only {replicas} replica(s). "
                "Scale up before relaxing PDB."
            )
        new_min = replicas - 1
        patch: dict[str, Any] = {"spec": {"minAvailable": new_min}}
        return FixCandidate(
            description=f"Relax PDB {finding.resource_name}: minAvailable {replicas} -> {new_min}",
            patch_type="strategic-merge",
            payload=patch,
            requires_review=True,
            references=["https://kubernetes.io/docs/tasks/run-application/configure-pdb/"],
        )


# ---------------------------------------------------------------------------
# Dispatch registry
# ---------------------------------------------------------------------------

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
    """Return the first matching FixCandidate, or None if no handler applies."""
    for handler in REGISTRY:
        if handler.applies_to(finding):
            return handler.generate_fix(finding, k8s_state)
    return None
