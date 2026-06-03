# PRD Section 12 — Deployment, ReplicaSet, and StatefulSet Analyzers

## Context

The audit found zero `DeploymentAnalyzer`, `ReplicaSetAnalyzer`, or `StatefulSetAnalyzer` classes in `src/`.
`DiagnosticsManager` stubs in `diagnostics_manager.py` return hardcoded dicts and never call
`kubernetes.client.AppsV1Api`. This section specifies all three analyzers, their k8s API surface,
Finding mappings, and test suites. All three extend `BaseAnalyzer` (section 09).

---

## 1. DeploymentAnalyzer

### 1.1 Class Signature

```python
# src/analyzers/deployment_analyzer.py
from __future__ import annotations
import json, logging
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
        # Optional callable: image_probe_fn(image: str) -> bool (True = exists)
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
```

### 1.2 Kubernetes API Calls

| Call | SDK Method | Purpose |
|---|---|---|
| List deployments | `apps_v1.list_namespaced_deployment(ns)` or `list_deployment_for_all_namespaces()` | Enumerate workloads |
| Read rollout history | `apps_v1.list_namespaced_replica_set(ns, label_selector=owner_selector)` | Detect multiple active RSs (used by ReplicaSetAnalyzer) |
| Node capacity | `core_v1.list_node()` | Validate resource requests against largest schedulable node |

### 1.3 Detection Rules and Finding Mapping

```python
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

        # Rule 1: Replica mismatch persisting >5 min
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
                            evidence=Evidence(
                                events=(), log_tail="", status_snapshot=snap
                            ),
                            suggested_fix_class="ReplicaRemediator",
                            root_cause_hypothesis=(
                                f"Deployment {name}: desired={desired} "
                                f"available={available} for {age}s"
                            ),
                        ))

        # Rule 2: Rollout stuck (ProgressDeadlineExceeded)
        for cond in dep.status.conditions or []:
            if (
                cond.type == "Progressing"
                and cond.reason == "ProgressDeadlineExceeded"
            ):
                findings.append(Finding(
                    resource=ref,
                    severity="critical",
                    category="rollout-stuck",
                    evidence=Evidence(events=(), log_tail="", status_snapshot=snap),
                    suggested_fix_class="RollbackRemediator",
                    root_cause_hypothesis=(
                        f"Deployment {name} rollout exceeded deadline: "
                        f"{cond.message or 'ProgressDeadlineExceeded'}"
                    ),
                ))

        # Rule 3: Image tag not found in registry (requires image_probe_fn)
        if self._image_probe:
            for container in dep.spec.template.spec.containers or []:
                if not self._image_probe(container.image):
                    findings.append(Finding(
                        resource=ref,
                        severity="high",
                        category="image-not-found",
                        evidence=Evidence(
                            events=(), log_tail="",
                            status_snapshot=json.dumps({"image": container.image})
                        ),
                        suggested_fix_class="ImageTagRemediator",
                        root_cause_hypothesis=(
                            f"Image {container.image!r} not found in registry"
                        ),
                    ))

        # Rule 4: Impossible resource requests (exceeds largest schedulable node)
        node_capacity = self._largest_node_capacity()
        for container in dep.spec.template.spec.containers or []:
            reqs = (container.resources or {})
            if hasattr(reqs, "requests") and reqs.requests:
                cpu_req = _parse_cpu(reqs.requests.get("cpu", "0"))
                mem_req = _parse_mem(reqs.requests.get("memory", "0"))
                if cpu_req > node_capacity["cpu"] or mem_req > node_capacity["memory"]:
                    findings.append(Finding(
                        resource=ref,
                        severity="critical",
                        category="impossible-resource-request",
                        evidence=Evidence(
                            events=(), log_tail="",
                            status_snapshot=json.dumps({
                                "container": container.name,
                                "requests": reqs.requests,
                                "largest_node": node_capacity,
                            }),
                        ),
                        suggested_fix_class="ResourceRequestRemediator",
                        root_cause_hypothesis=(
                            f"Container {container.name!r} requests exceed largest "
                            f"schedulable node capacity"
                        ),
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
```

---

## 2. ReplicaSetAnalyzer

### 2.1 Class Signature

```python
# src/analyzers/replicaset_analyzer.py
from __future__ import annotations
import json, logging
from collections import defaultdict
from typing import List, Optional

from kubernetes.client import AppsV1Api, CoreV1Api, V1ReplicaSet
from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)


class ReplicaSetAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "replicaset"

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        rsets = (
            self.apps_v1.list_namespaced_replica_set(namespace).items
            if namespace
            else self.apps_v1.list_replica_set_for_all_namespaces().items
        )
        findings: List[Finding] = []

        # Group RSs by owner Deployment
        by_owner: dict[str, list[V1ReplicaSet]] = defaultdict(list)
        for rs in rsets:
            for ref in rs.metadata.owner_references or []:
                if ref.kind == "Deployment":
                    by_owner[f"{rs.metadata.namespace}/{ref.name}"].append(rs)

        for owner_key, owned in by_owner.items():
            ns, dep_name = owner_key.split("/", 1)

            # Rule 1: RS with replicas=0 left dangling (not the current RS)
            dangling = [
                rs for rs in owned
                if (rs.spec.replicas or 0) == 0
                and (rs.status.replicas or 0) == 0
            ]
            for rs in dangling:
                ref = ResourceRef(
                    kind="ReplicaSet",
                    namespace=rs.metadata.namespace,
                    name=rs.metadata.name,
                    uid=rs.metadata.uid or "",
                )
                findings.append(Finding(
                    resource=ref,
                    severity="low",
                    category="dangling-replicaset",
                    evidence=Evidence(
                        events=(),
                        log_tail="",
                        status_snapshot=json.dumps({
                            "owner_deployment": dep_name,
                            "spec_replicas": rs.spec.replicas,
                        }),
                    ),
                    suggested_fix_class="DanglingRSRemediator",
                    root_cause_hypothesis=(
                        f"ReplicaSet {rs.metadata.name} owned by {dep_name} "
                        f"has replicas=0 and is safe to prune"
                    ),
                ))

            # Rule 2: Multiple active RSs (rollout half-complete)
            active = [
                rs for rs in owned
                if (rs.status.replicas or 0) > 0
            ]
            if len(active) > 1:
                active_names = [rs.metadata.name for rs in active]
                ref = ResourceRef(
                    kind="Deployment",
                    namespace=ns,
                    name=dep_name,
                    uid="",
                )
                findings.append(Finding(
                    resource=ref,
                    severity="medium",
                    category="rollout-in-progress",
                    evidence=Evidence(
                        events=(),
                        log_tail="",
                        status_snapshot=json.dumps({"active_replicasets": active_names}),
                    ),
                    suggested_fix_class="RolloutMonitorRemediator",
                    root_cause_hypothesis=(
                        f"Deployment {dep_name} has {len(active)} active ReplicaSets "
                        f"indicating a rollout is incomplete: {active_names}"
                    ),
                ))

        return findings
```

### 2.2 Kubernetes API Calls

| Call | SDK Method | Purpose |
|---|---|---|
| List ReplicaSets | `apps_v1.list_namespaced_replica_set(ns)` | Enumerate all RSs in scope |
| List (cluster-wide) | `apps_v1.list_replica_set_for_all_namespaces()` | Cross-namespace sweep |

---

## 3. StatefulSetAnalyzer

### 3.1 Class Signature

```python
# src/analyzers/statefulset_analyzer.py
from __future__ import annotations
import json, logging
from typing import List, Optional

from kubernetes.client import AppsV1Api, CoreV1Api, V1StatefulSet
from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)


class StatefulSetAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "statefulset"

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        sets = (
            self.apps_v1.list_namespaced_stateful_set(namespace).items
            if namespace
            else self.apps_v1.list_stateful_set_for_all_namespaces().items
        )
        findings: List[Finding] = []
        for sts in sets:
            findings.extend(self._evaluate(sts))
        return findings

    def _evaluate(self, sts: V1StatefulSet) -> List[Finding]:
        ns = sts.metadata.namespace
        name = sts.metadata.name
        uid = sts.metadata.uid or ""
        ref = ResourceRef(kind="StatefulSet", namespace=ns, name=name, uid=uid)
        findings: List[Finding] = []

        # Rule 1: Pods stuck Pending due to PVC binding failure
        pods = self._list_pods(ns, name)
        pending = [p for p in pods if (p.status.phase or "").lower() == "pending"]
        for pod in pending:
            events = self._fetch_events(ns, pod.metadata.name)
            pvc_events = [e for e in events if e.reason in ("FailedMount", "Unbound")]
            if pvc_events:
                snap = json.dumps({
                    "pod": pod.metadata.name,
                    "phase": pod.status.phase,
                })
                findings.append(Finding(
                    resource=ResourceRef(
                        kind="Pod", namespace=ns,
                        name=pod.metadata.name, uid=pod.metadata.uid or ""
                    ),
                    severity="high",
                    category="pvc-binding-pending",
                    evidence=Evidence(
                        events=tuple(
                            f"{e.reason}: {e.message}" for e in pvc_events
                        ),
                        log_tail="",
                        status_snapshot=snap,
                    ),
                    suggested_fix_class="PVCRemediator",
                    root_cause_hypothesis=(
                        f"StatefulSet {name} pod {pod.metadata.name} "
                        f"stuck Pending due to PVC binding failure"
                    ),
                ))

        # Rule 2: Pod ordinal gap (pod-0 missing while pod-N exists)
        ordinals = sorted(
            int(p.metadata.name.rsplit("-", 1)[-1])
            for p in pods
            if p.metadata.name.rsplit("-", 1)[-1].isdigit()
        )
        if ordinals and ordinals != list(range(ordinals[-1] + 1)):
            expected = set(range(ordinals[-1] + 1))
            missing = sorted(expected - set(ordinals))
            snap = json.dumps({"present_ordinals": ordinals, "missing_ordinals": missing})
            findings.append(Finding(
                resource=ref,
                severity="critical",
                category="ordinal-gap",
                evidence=Evidence(events=(), log_tail="", status_snapshot=snap),
                suggested_fix_class="StatefulSetOrdinalRemediator",
                root_cause_hypothesis=(
                    f"StatefulSet {name}: ordinals {missing} missing "
                    f"while higher ordinals are present"
                ),
            ))

        # Rule 3: VolumeClaimTemplate failures (PVCs in Lost or Pending)
        pvcs = self._list_pvcs(ns, name)
        for pvc in pvcs:
            phase = pvc.status.phase or ""
            if phase in ("Lost", "Pending"):
                findings.append(Finding(
                    resource=ResourceRef(
                        kind="PersistentVolumeClaim", namespace=ns,
                        name=pvc.metadata.name, uid=pvc.metadata.uid or ""
                    ),
                    severity="high",
                    category="pvc-template-failure",
                    evidence=Evidence(
                        events=(),
                        log_tail="",
                        status_snapshot=json.dumps({
                            "pvc": pvc.metadata.name,
                            "phase": phase,
                        }),
                    ),
                    suggested_fix_class="PVCRemediator",
                    root_cause_hypothesis=(
                        f"StatefulSet {name} VolumeClaimTemplate PVC "
                        f"{pvc.metadata.name} is in phase {phase!r}"
                    ),
                ))

        return findings

    def _list_pods(self, ns: str, sts_name: str):
        try:
            return self.core_v1.list_namespaced_pod(
                ns, label_selector=f"statefulset.kubernetes.io/pod-name"
            ).items
        except ApiException:
            return []

    def _list_pvcs(self, ns: str, sts_name: str):
        try:
            return self.core_v1.list_namespaced_persistent_volume_claim(
                ns, label_selector=f"app={sts_name}"
            ).items
        except ApiException:
            return []

    def _fetch_events(self, ns: str, pod_name: str):
        try:
            return self.core_v1.list_namespaced_event(
                ns, field_selector=f"involvedObject.name={pod_name}"
            ).items
        except ApiException:
            return []
```

### 3.2 Kubernetes API Calls

| Call | SDK Method | Purpose |
|---|---|---|
| List StatefulSets | `apps_v1.list_namespaced_stateful_set(ns)` | Enumerate workloads |
| List Pods | `core_v1.list_namespaced_pod(ns, label_selector=...)` | Detect Pending pods and ordinal gaps |
| List PVCs | `core_v1.list_namespaced_persistent_volume_claim(ns, ...)` | Detect Lost/Pending PVCs |
| List Events | `core_v1.list_namespaced_event(ns, field_selector=...)` | Surface FailedMount / Unbound reasons |

---

## 4. Tests

```python
# tests/analyzers/test_workload_analyzers.py
import asyncio, json, pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from kubernetes.client import (
    V1Deployment, V1DeploymentSpec, V1DeploymentStatus, V1ObjectMeta,
    V1DeploymentCondition, V1PodTemplateSpec, V1PodSpec, V1Container,
    V1ResourceRequirements, V1ReplicaSet, V1ReplicaSetSpec, V1ReplicaSetStatus,
    V1ObjectReference, V1StatefulSet, V1StatefulSetSpec, V1StatefulSetStatus,
    V1Pod, V1PodStatus, V1PersistentVolumeClaim, V1PersistentVolumeClaimStatus,
    V1Event,
)
from src.analyzers.deployment_analyzer import DeploymentAnalyzer
from src.analyzers.replicaset_analyzer import ReplicaSetAnalyzer
from src.analyzers.statefulset_analyzer import StatefulSetAnalyzer

run = lambda coro: asyncio.get_event_loop().run_until_complete(coro)
_old = datetime.now(timezone.utc) - timedelta(minutes=10)


def _deploy(name, desired=3, available=1, conditions=None):
    return V1Deployment(
        metadata=V1ObjectMeta(name=name, namespace="default", uid="uid1"),
        spec=V1DeploymentSpec(
            replicas=desired,
            selector=MagicMock(),
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(),
                spec=V1PodSpec(containers=[
                    V1Container(name="app", image="app:v1",
                                resources=V1ResourceRequirements(requests={}))
                ]),
            ),
        ),
        status=V1DeploymentStatus(
            replicas=desired, available_replicas=available, ready_replicas=available,
            conditions=conditions or [],
        ),
    )


def _analyzer_deploy(deps, nodes=None):
    c = MagicMock()
    a = MagicMock()
    a.list_deployment_for_all_namespaces.return_value.items = deps
    c.list_node.return_value.items = nodes or []
    return DeploymentAnalyzer(core_v1=c, apps_v1=a)


# --- DeploymentAnalyzer tests ---

def test_replica_mismatch_after_five_min():
    cond = V1DeploymentCondition(
        type="Available", status="False",
        last_transition_time=_old, reason="MinimumReplicasUnavailable", message=""
    )
    dep = _deploy("app", desired=3, available=1, conditions=[cond])
    fs = run(_analyzer_deploy([dep]).analyze())
    assert any(f.category == "replica-mismatch" for f in fs)
    assert all(f.severity == "high" for f in fs if f.category == "replica-mismatch")


def test_replica_mismatch_suppressed_under_five_min():
    recent = datetime.now(timezone.utc) - timedelta(minutes=2)
    cond = V1DeploymentCondition(
        type="Available", status="False",
        last_transition_time=recent, reason="MinimumReplicasUnavailable", message=""
    )
    dep = _deploy("app", desired=3, available=1, conditions=[cond])
    fs = run(_analyzer_deploy([dep]).analyze())
    assert not any(f.category == "replica-mismatch" for f in fs)


def test_rollout_stuck_progress_deadline():
    cond = V1DeploymentCondition(
        type="Progressing", status="False",
        reason="ProgressDeadlineExceeded",
        last_transition_time=_old, message="exceeded"
    )
    dep = _deploy("app", desired=3, available=3, conditions=[cond])
    fs = run(_analyzer_deploy([dep]).analyze())
    assert any(f.category == "rollout-stuck" and f.severity == "critical" for f in fs)


def test_impossible_resource_request():
    node = MagicMock()
    node.status.capacity = {"cpu": "4", "memory": "8Gi"}
    dep = _deploy("bigapp")
    dep.spec.template.spec.containers[0].resources = V1ResourceRequirements(
        requests={"cpu": "100", "memory": "1Ti"}
    )
    a = MagicMock()
    a.list_deployment_for_all_namespaces.return_value.items = [dep]
    c = MagicMock()
    c.list_node.return_value.items = [node]
    analyzer = DeploymentAnalyzer(core_v1=c, apps_v1=a)
    fs = run(analyzer.analyze())
    assert any(f.category == "impossible-resource-request" for f in fs)


# --- ReplicaSetAnalyzer tests ---

def _make_rs(name, ns, owner_dep, spec_replicas, status_replicas, uid="ruid"):
    rs = V1ReplicaSet(
        metadata=V1ObjectMeta(
            name=name, namespace=ns, uid=uid,
            owner_references=[MagicMock(kind="Deployment", name=owner_dep)]
        ),
        spec=V1ReplicaSetSpec(replicas=spec_replicas, selector=MagicMock(),
                              template=MagicMock()),
        status=V1ReplicaSetStatus(replicas=status_replicas),
    )
    return rs


def test_dangling_replicaset():
    rs = _make_rs("app-abc", "default", "app", spec_replicas=0, status_replicas=0)
    a = MagicMock()
    a.list_replica_set_for_all_namespaces.return_value.items = [rs]
    analyzer = ReplicaSetAnalyzer(core_v1=MagicMock(), apps_v1=a)
    fs = run(analyzer.analyze())
    assert any(f.category == "dangling-replicaset" for f in fs)


def test_multiple_active_replicasets():
    rs1 = _make_rs("app-abc", "default", "app", 2, 2, "uid1")
    rs2 = _make_rs("app-def", "default", "app", 1, 1, "uid2")
    a = MagicMock()
    a.list_replica_set_for_all_namespaces.return_value.items = [rs1, rs2]
    analyzer = ReplicaSetAnalyzer(core_v1=MagicMock(), apps_v1=a)
    fs = run(analyzer.analyze())
    assert any(f.category == "rollout-in-progress" for f in fs)


# --- StatefulSetAnalyzer tests ---

def _sts_analyzer(sts_list, pods, pvcs, events):
    a = MagicMock()
    a.list_stateful_set_for_all_namespaces.return_value.items = sts_list
    c = MagicMock()
    c.list_namespaced_pod.return_value.items = pods
    c.list_namespaced_persistent_volume_claim.return_value.items = pvcs
    c.list_namespaced_event.return_value.items = events
    return StatefulSetAnalyzer(core_v1=c, apps_v1=a)


def test_pvc_binding_pending():
    sts = V1StatefulSet(
        metadata=V1ObjectMeta(name="db", namespace="default", uid="suid"),
        spec=MagicMock(), status=MagicMock()
    )
    pod = V1Pod(
        metadata=V1ObjectMeta(name="db-0", namespace="default", uid="puid"),
        status=V1PodStatus(phase="Pending")
    )
    ev = V1Event(reason="FailedMount", message="Unable to attach volume", involved_object=MagicMock())
    analyzer = _sts_analyzer([sts], [pod], [], [ev])
    fs = run(analyzer.analyze())
    assert any(f.category == "pvc-binding-pending" for f in fs)


def test_ordinal_gap_detected():
    sts = V1StatefulSet(
        metadata=V1ObjectMeta(name="db", namespace="default", uid="suid"),
        spec=MagicMock(), status=MagicMock()
    )
    pods = [
        V1Pod(metadata=V1ObjectMeta(name="db-1", namespace="default", uid="p1"),
              status=V1PodStatus(phase="Running")),
        V1Pod(metadata=V1ObjectMeta(name="db-2", namespace="default", uid="p2"),
              status=V1PodStatus(phase="Running")),
    ]
    analyzer = _sts_analyzer([sts], pods, [], [])
    fs = run(analyzer.analyze())
    ordinal_findings = [f for f in fs if f.category == "ordinal-gap"]
    assert ordinal_findings
    assert ordinal_findings[0].severity == "critical"


def test_pvc_template_failure_lost():
    sts = V1StatefulSet(
        metadata=V1ObjectMeta(name="db", namespace="default", uid="suid"),
        spec=MagicMock(), status=MagicMock()
    )
    pvc = V1PersistentVolumeClaim(
        metadata=V1ObjectMeta(name="data-db-0", namespace="default", uid="pvuid"),
        status=V1PersistentVolumeClaimStatus(phase="Lost")
    )
    analyzer = _sts_analyzer([sts], [], [pvc], [])
    fs = run(analyzer.analyze())
    assert any(f.category == "pvc-template-failure" for f in fs)
```

---

## 5. Finding Category Registry

| Category | Analyzer | Severity | `suggested_fix_class` |
|---|---|---|---|
| `replica-mismatch` | DeploymentAnalyzer | high | `ReplicaRemediator` |
| `rollout-stuck` | DeploymentAnalyzer | critical | `RollbackRemediator` |
| `image-not-found` | DeploymentAnalyzer | high | `ImageTagRemediator` |
| `impossible-resource-request` | DeploymentAnalyzer | critical | `ResourceRequestRemediator` |
| `dangling-replicaset` | ReplicaSetAnalyzer | low | `DanglingRSRemediator` |
| `rollout-in-progress` | ReplicaSetAnalyzer | medium | `RolloutMonitorRemediator` |
| `pvc-binding-pending` | StatefulSetAnalyzer | high | `PVCRemediator` |
| `ordinal-gap` | StatefulSetAnalyzer | critical | `StatefulSetOrdinalRemediator` |
| `pvc-template-failure` | StatefulSetAnalyzer | high | `PVCRemediator` |

---

## 6. Implementation Notes

- All `kubernetes.client` calls are synchronous; wrap each in `asyncio.to_thread()` in the async analyze path to avoid blocking the event loop.
- `replica-mismatch` is only emitted when `lastTransitionTime` is more than 5 minutes old. A deployment mid-rollout with a transient mismatch must not fire.
- `image-not-found` requires an injected `image_probe_fn`. When `None`, the check is skipped. The probe callable must handle registry auth failures gracefully and return `True` (assume exists) on timeout.
- `ordinal-gap` detection parses the numeric suffix from pod names. Non-numeric suffixes (e.g. canary pods) are ignored.
- `_list_pods` for StatefulSetAnalyzer should use the `app=<sts_name>` label selector in production; the exact label key depends on the StatefulSet's `spec.selector.matchLabels`. The implementation above is illustrative; callers must derive the selector from `sts.spec.selector.match_labels`.
- `suggested_fix_class` values here are the registry keys consumed by the Remediator registry (section 15). Never compare them at call sites.
