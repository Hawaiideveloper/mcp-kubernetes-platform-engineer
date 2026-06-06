from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes.client import AppsV1Api, CoreV1Api, V1Deployment
from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)
_FIVE_MINUTES = 300


class DeploymentAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "deployment"

    def __init__(
        self,
        core_v1: CoreV1Api,
        apps_v1: AppsV1Api,
        image_probe_fn=None,
        log_tail_lines: int = 100,
    ) -> None:
        super().__init__(core_v1, apps_v1, log_tail_lines)
        self._image_probe = image_probe_fn

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        deps = (
            self.apps_v1.list_namespaced_deployment(namespace).items
            if namespace
            else self.apps_v1.list_deployment_for_all_namespaces().items
        )
        findings: List[Finding] = []
        for dep in deps:
            findings.extend(self._evaluate(dep))
        return findings

    def _evaluate(self, dep: V1Deployment) -> List[Finding]:
        ns = dep.metadata.namespace
        name = dep.metadata.name
        uid = dep.metadata.uid or ""
        ref = ResourceRef(kind="Deployment", namespace=ns, name=name, uid=uid)
        snap = json.dumps({
            "spec_replicas": dep.spec.replicas,
            "ready_replicas": dep.status.ready_replicas,
            "available_replicas": dep.status.available_replicas,
        })
        findings: List[Finding] = []

        desired = dep.spec.replicas or 0
        available = dep.status.available_replicas or 0
        if available < desired:
            for cond in dep.status.conditions or []:
                if cond.type == "Available" and cond.status == "False":
                    age = _condition_age_seconds(cond.last_transition_time)
                    if age >= _FIVE_MINUTES:
                        findings.append(Finding(
                            resource=ref,
                            severity="high",
                            category="replica-mismatch",
                            evidence=Evidence(events=(), log_tail="", status_snapshot=snap),
                            suggested_fix_class="ReplicaRemediator",
                            root_cause_hypothesis=(
                                f"Deployment {name}: desired={desired} available={available} for {age}s"
                            ),
                        ))

        for cond in dep.status.conditions or []:
            if cond.type == "Progressing" and cond.reason == "ProgressDeadlineExceeded":
                findings.append(Finding(
                    resource=ref,
                    severity="critical",
                    category="rollout-stuck",
                    evidence=Evidence(events=(), log_tail="", status_snapshot=snap),
                    suggested_fix_class="RollbackRemediator",
                    root_cause_hypothesis=(
                        f"Deployment {name} rollout exceeded deadline: {cond.message or 'ProgressDeadlineExceeded'}"
                    ),
                ))

        if self._image_probe:
            for container in dep.spec.template.spec.containers or []:
                if not self._image_probe(container.image):
                    findings.append(Finding(
                        resource=ref,
                        severity="high",
                        category="image-not-found",
                        evidence=Evidence(events=(), log_tail="", status_snapshot=json.dumps({"image": container.image})),
                        suggested_fix_class="ImageTagRemediator",
                        root_cause_hypothesis=f"Image {container.image!r} not found in registry",
                    ))

        node_capacity = self._largest_node_capacity()
        for container in dep.spec.template.spec.containers or []:
            reqs = container.resources
            if reqs is not None and hasattr(reqs, "requests") and reqs.requests:
                cpu_req = _parse_cpu(reqs.requests.get("cpu", "0"))
                mem_req = _parse_mem(reqs.requests.get("memory", "0"))
                if cpu_req > node_capacity["cpu"] or mem_req > node_capacity["memory"]:
                    findings.append(Finding(
                        resource=ref,
                        severity="critical",
                        category="impossible-resource-request",
                        evidence=Evidence(events=(), log_tail="", status_snapshot=json.dumps({"container": container.name, "requests": reqs.requests, "largest_node": node_capacity})),
                        suggested_fix_class="ResourceRequestRemediator",
                        root_cause_hypothesis=f"Container {container.name!r} requests exceed largest schedulable node capacity",
                    ))

        return findings

    def _largest_node_capacity(self) -> dict:
        try:
            nodes = self.core_v1.list_node().items
            max_cpu = max((_parse_cpu(n.status.capacity.get("cpu", "0")) for n in nodes), default=0)
            max_mem = max((_parse_mem(n.status.capacity.get("memory", "0")) for n in nodes), default=0)
            return {"cpu": max_cpu, "memory": max_mem}
        except ApiException:
            return {"cpu": float("inf"), "memory": float("inf")}


def _condition_age_seconds(last_transition_time) -> float:
    if last_transition_time is None:
        return 0.0
    now = datetime.now(timezone.utc)
    if last_transition_time.tzinfo is None:
        last_transition_time = last_transition_time.replace(tzinfo=timezone.utc)
    return (now - last_transition_time).total_seconds()


def _parse_cpu(val: str) -> float:
    if val.endswith("m"):
        return float(val[:-1]) / 1000
    return float(val or 0)


def _parse_mem(val: str) -> int:
    suffixes = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
    for suffix, mult in suffixes.items():
        if val.endswith(suffix):
            return int(val[: -len(suffix)]) * mult
    return int(val or 0)
