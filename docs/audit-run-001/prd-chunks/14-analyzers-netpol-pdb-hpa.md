# PRD Section 14 — NetworkPolicy, PDB, and HPA Analyzers

## Context

The audit found zero network-policy, PDB, or HPA analysis anywhere in `src/`.
`DiagnosticsManager._check_networking()` returns a hardcoded `'network_policies: 5'` dict;
no call to `NetworkingV1Api`, `PolicyV1Api`, or `AutoscalingV2Api` exists anywhere.
All three analyzers extend `BaseAnalyzer` from section 09.

---

## 1. NetworkPolicyAnalyzer

### 1.1 Failure Modes

| Finding type | Condition |
|---|---|
| `orphan_policy` | `spec.podSelector` matches zero live pods |
| `service_ingress_denied` | A policy blocks ingress on a port a Service forwards to live pods |
| `egress_dns_blocked` | Egress rules exist but none permit port 53 UDP/TCP toward kube-system |
| `no_default_deny` | Namespace has `env=production` label but no default-deny NetworkPolicy |

### 1.2 Signature and API Calls

```python
# src/analyzers/network_policy_analyzer.py
from __future__ import annotations
import json, logging
from typing import Dict, List, Literal, Optional
from kubernetes.client import CoreV1Api, NetworkingV1Api
from kubernetes.client.exceptions import ApiException
from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)
NetPolFindingType = Literal["orphan_policy","service_ingress_denied","egress_dns_blocked","no_default_deny"]

class NetworkPolicyAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "network_policy"

    def __init__(self, core_v1: CoreV1Api, networking_v1: NetworkingV1Api, **kwargs) -> None:
        super().__init__(core_v1=core_v1, **kwargs)
        self.networking_v1 = networking_v1

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        # API calls:
        #   NetworkingV1Api.list_namespaced_network_policy(ns)
        #   CoreV1Api.list_namespaced_pod(ns, label_selector=...)
        #   CoreV1Api.list_namespaced_service(ns)
        #   CoreV1Api.read_namespace(ns)  — for env=production label check
        findings: List[Finding] = []
        for ns in (self._resolve_namespaces(namespace)):
            policies = self.networking_v1.list_namespaced_network_policy(ns).items
            pods     = self.core_v1.list_namespaced_pod(ns).items
            services = self.core_v1.list_namespaced_service(ns).items
            ns_labels = self.core_v1.read_namespace(ns).metadata.labels or {}
            findings.extend(self._check_orphan(policies, pods, ns))
            findings.extend(self._check_service_ingress_denied(policies, pods, services, ns))
            findings.extend(self._check_egress_dns(policies, ns))
            findings.extend(self._check_no_default_deny(policies, ns_labels, ns))
        return findings
```

### 1.3 Detection Logic

**Orphan policy** — For each `V1NetworkPolicy`, build a label-selector string from
`spec.pod_selector.match_labels` and call `list_namespaced_pod(label_selector=...)`. Empty
`.items` → `orphan_policy`. Note: a completely empty `pod_selector` (no keys) matches ALL pods
and is not an orphan.

**Service ingress denied** — For each `V1Service` with `spec.selector`, find backing pods.
For each backing pod, check whether any NetworkPolicy `spec.ingress` rule permits the Service
port from any source. If none does, emit `service_ingress_denied`.

**Egress DNS blocked** — For each NetworkPolicy with non-empty `spec.egress`, verify at least
one rule allows `ports=[{port:53,protocol:UDP},{port:53,protocol:TCP}]` toward
`namespaceSelector: {kubernetes.io/metadata.name: kube-system}`. Missing → `egress_dns_blocked`.

**No default deny** — A default-deny policy has an empty `pod_selector` and either no ingress/
egress entries or `policyTypes=[Ingress,Egress]` with no rules. If namespace has `env=production`
and no such policy exists, emit `no_default_deny`.

### 1.4 Finding Mapping

```python
_SEVERITY: Dict[NetPolFindingType, str] = {
    "orphan_policy": "medium", "service_ingress_denied": "high",
    "egress_dns_blocked": "high", "no_default_deny": "medium",
}
_FIX_CLASS: Dict[NetPolFindingType, str] = {
    "orphan_policy": "NetPolOrphanRemediator",
    "service_ingress_denied": "NetPolIngressRemediator",
    "egress_dns_blocked": "NetPolEgressDNSRemediator",
    "no_default_deny": "NetPolDefaultDenyRemediator",
}
# Usage inside _make_finding():
#   Finding(ResourceRef("NetworkPolicy", ns, name, uid), _SEVERITY[t], t,
#           Evidence((), "", json.dumps({"detail": detail})), _FIX_CLASS[t], detail)
```

### 1.5 Tests

```python
# tests/analyzers/test_network_policy_analyzer.py
import asyncio
from unittest.mock import MagicMock
from kubernetes.client import V1NetworkPolicy, V1NetworkPolicySpec, V1LabelSelector, V1ObjectMeta
from src.analyzers.network_policy_analyzer import NetworkPolicyAnalyzer

run = lambda c: asyncio.get_event_loop().run_until_complete(c)

def _mkanalyzer(policies=None, pods=None, ns_labels=None):
    core, net = MagicMock(), MagicMock()
    core.list_namespaced_pod.return_value.items     = pods or []
    core.list_namespaced_service.return_value.items = []
    core.read_namespace.return_value.metadata.labels = ns_labels or {}
    net.list_namespaced_network_policy.return_value.items = policies or []
    a = NetworkPolicyAnalyzer(core_v1=core, networking_v1=net, apps_v1=MagicMock())
    a._resolve_namespaces = lambda ns: ["default"]
    return a

def test_orphan_policy():
    p = V1NetworkPolicy(
        metadata=V1ObjectMeta(name="isolate-foo", namespace="default", uid="p1"),
        spec=V1NetworkPolicySpec(pod_selector=V1LabelSelector(match_labels={"app":"foo"}),
                                 policy_types=["Ingress"]))
    cats = [f.category for f in run(_mkanalyzer(policies=[p], pods=[]).analyze())]
    assert "orphan_policy" in cats

def test_no_default_deny_production():
    cats = [f.category for f in run(_mkanalyzer(ns_labels={"env":"production"}).analyze())]
    assert "no_default_deny" in cats

def test_egress_dns_blocked():
    p = V1NetworkPolicy(
        metadata=V1ObjectMeta(name="deny-egress", namespace="default", uid="p2"),
        spec=V1NetworkPolicySpec(pod_selector=V1LabelSelector(match_labels={}),
                                 policy_types=["Egress"], egress=[]))
    cats = [f.category for f in run(_mkanalyzer(policies=[p]).analyze())]
    assert "egress_dns_blocked" in cats

def test_clean_namespace():
    assert run(_mkanalyzer().analyze()) == []
```
---

## 2. PDBAnalyzer

### 2.1 Failure Modes and Finding Mapping

| Finding type | Condition | Severity | suggested_fix_class |
|---|---|---|---|
| `eviction_blocked` | `status.disruptions_allowed == 0` and matched pods > 0 | high | `PDBEvictionRemediator` |
| `selector_mismatch` | PDB selector matches zero live pods | medium | `PDBSelectorRemediator` |
| `no_owner_workload` | All matched pods' owner Deployment/StatefulSet returns 404 | low | `PDBOrphanRemediator` |

### 2.2 Signature and API Calls

```python
# src/analyzers/pdb_analyzer.py
from __future__ import annotations
import logging
from typing import List, Optional
from kubernetes.client import CoreV1Api, AppsV1Api, PolicyV1Api
from kubernetes.client.exceptions import ApiException
from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)

class PDBAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "pdb"

    def __init__(self, core_v1: CoreV1Api, apps_v1: AppsV1Api, policy_v1: PolicyV1Api) -> None:
        super().__init__(core_v1=core_v1, apps_v1=apps_v1)
        self.policy_v1 = policy_v1

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        # API calls:
        #   PolicyV1Api.list_namespaced_pod_disruption_budget(ns)          if namespace given
        #   PolicyV1Api.list_pod_disruption_budget_for_all_namespaces()    otherwise
        #   CoreV1Api.list_namespaced_pod(ns, label_selector=matchLabels)
        #   AppsV1Api.read_namespaced_deployment(name, ns)  — 404 → no_owner_workload
        #   AppsV1Api.read_namespaced_stateful_set(name, ns)
        pdbs = (self.policy_v1.list_namespaced_pod_disruption_budget(namespace).items
                if namespace else
                self.policy_v1.list_pod_disruption_budget_for_all_namespaces().items)
        findings: List[Finding] = []
        for pdb in pdbs:
            findings.extend(self._evaluate_pdb(pdb))
        return findings
    # _evaluate_pdb: checks disruptions_allowed==0, empty pod list, 404 on owner
    # matchExpressions selectors are logged as WARNING and skipped (deferred)
```

### 2.3 Tests

```python
# tests/analyzers/test_pdb_analyzer.py
import asyncio
from unittest.mock import MagicMock
from kubernetes.client import (V1ObjectMeta, V1LabelSelector, V1PodDisruptionBudget,
    V1PodDisruptionBudgetSpec, V1PodDisruptionBudgetStatus)
from src.analyzers.pdb_analyzer import PDBAnalyzer

run = lambda c: asyncio.get_event_loop().run_until_complete(c)

def _pdb(name, disruptions_allowed=1, match_labels=None, ns="default"):
    return V1PodDisruptionBudget(
        metadata=V1ObjectMeta(name=name, namespace=ns, uid="d1"),
        spec=V1PodDisruptionBudgetSpec(
            selector=V1LabelSelector(match_labels=match_labels or {"app": name})),
        status=V1PodDisruptionBudgetStatus(
            disruptions_allowed=disruptions_allowed, current_healthy=1,
            desired_healthy=1, expected_pods=1))

def _mkanalyzer(pdbs, pods=None):
    policy, core, apps = MagicMock(), MagicMock(), MagicMock()
    policy.list_pod_disruption_budget_for_all_namespaces.return_value.items = pdbs
    core.list_namespaced_pod.return_value.items = pods if pods is not None else [MagicMock()]
    return PDBAnalyzer(core_v1=core, apps_v1=apps, policy_v1=policy)

def test_eviction_blocked():
    findings = run(_mkanalyzer([_pdb("tight", disruptions_allowed=0)]).analyze())
    assert any(f.category == "eviction_blocked" and f.severity == "high" for f in findings)

def test_selector_mismatch():
    a = _mkanalyzer([_pdb("ghost", match_labels={"app": "nonexistent"})])
    a.core_v1.list_namespaced_pod.return_value.items = []
    findings = run(a.analyze())
    assert any(f.category == "selector_mismatch" for f in findings)

def test_healthy_pdb_no_blocking():
    findings = run(_mkanalyzer([_pdb("ok", disruptions_allowed=2)]).analyze())
    assert not any(f.category == "eviction_blocked" for f in findings)
```
---

## 3. HPAAnalyzer

### 3.1 Failure Modes and Finding Mapping

| Finding type | Condition | Severity | suggested_fix_class |
|---|---|---|---|
| `no_metrics` | `conditions[ScalingActive].reason` starts with `FailedGet` or `status=False` | high | `HPAMetricsRemediator` |
| `capped_at_max` | `current_replicas == max_replicas` for > `cap_threshold_minutes` | high | `HPACeilingRemediator` |
| `never_scaling` | `current == min`, `last_scale_time` None or older than `stale_scale_hours`, metrics present | medium | `HPAThresholdRemediator` |
| `target_missing` | `scale_target_ref` Deployment returns 404 | high | `HPAOrphanRemediator` |

### 3.2 Signature and API Calls

```python
# src/analyzers/hpa_analyzer.py
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from kubernetes.client import CoreV1Api, AppsV1Api, AutoscalingV2Api
from kubernetes.client.exceptions import ApiException
from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)
_CAP_MINUTES = 30
_STALE_HOURS  = 24

class HPAAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "hpa"

    def __init__(self, core_v1: CoreV1Api, apps_v1: AppsV1Api,
                 autoscaling_v2: AutoscalingV2Api,
                 cap_threshold_minutes: int = _CAP_MINUTES,
                 stale_scale_hours: int = _STALE_HOURS) -> None:
        super().__init__(core_v1=core_v1, apps_v1=apps_v1)
        self.autoscaling_v2 = autoscaling_v2
        self.cap_threshold_minutes = cap_threshold_minutes
        self.stale_scale_hours = stale_scale_hours

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        # API calls:
        #   AutoscalingV2Api.list_namespaced_horizontal_pod_autoscaler(ns)
        #   AutoscalingV2Api.list_horizontal_pod_autoscaler_for_all_namespaces()
        #   AppsV1Api.read_namespaced_deployment(name, ns)  — 404 → target_missing
        hpas = (self.autoscaling_v2.list_namespaced_horizontal_pod_autoscaler(namespace).items
                if namespace else
                self.autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces().items)
        findings: List[Finding] = []
        for hpa in hpas:
            findings.extend(self._evaluate_hpa(hpa))
        return findings
    # _evaluate_hpa: check conditions, cap, stale scaling, target 404
    # minReplicas==maxReplicas is degenerate — log WARNING and skip never_scaling check
```

### 3.3 Tests

```python
# tests/analyzers/test_hpa_analyzer.py
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from kubernetes.client import (V1ObjectMeta, V2HorizontalPodAutoscaler,
    V2HorizontalPodAutoscalerSpec, V2HorizontalPodAutoscalerStatus,
    V2CrossVersionObjectReference, V2HorizontalPodAutoscalerCondition)
from kubernetes.client.exceptions import ApiException
from src.analyzers.hpa_analyzer import HPAAnalyzer

run = lambda c: asyncio.get_event_loop().run_until_complete(c)
_NOW = datetime.now(timezone.utc)

def _hpa(name, current, max_r, min_r=1, conditions=None, last_scale=None):
    return V2HorizontalPodAutoscaler(
        metadata=V1ObjectMeta(name=name, namespace="default", uid="h1"),
        spec=V2HorizontalPodAutoscalerSpec(
            max_replicas=max_r, min_replicas=min_r,
            scale_target_ref=V2CrossVersionObjectReference(
                api_version="apps/v1", kind="Deployment", name=name)),
        status=V2HorizontalPodAutoscalerStatus(
            current_replicas=current, desired_replicas=current,
            conditions=conditions or [], last_scale_time=last_scale))

def _mkanalyzer(hpas, deployment_exists=True):
    auto, apps, core = MagicMock(), MagicMock(), MagicMock()
    auto.list_horizontal_pod_autoscaler_for_all_namespaces.return_value.items = hpas
    if not deployment_exists:
        apps.read_namespaced_deployment.side_effect = ApiException(status=404)
    return HPAAnalyzer(core_v1=core, apps_v1=apps, autoscaling_v2=auto)

def test_capped_at_max():
    findings = run(_mkanalyzer([_hpa("w", 10, 10, last_scale=_NOW-timedelta(hours=2))]).analyze())
    assert any(f.category == "capped_at_max" and f.severity == "high" for f in findings)

def test_no_metrics():
    cond = V2HorizontalPodAutoscalerCondition(
        type="ScalingActive", status="False",
        reason="FailedGetResourceMetric", message="unable to get metrics")
    findings = run(_mkanalyzer([_hpa("api", 1, 5, conditions=[cond])]).analyze())
    assert any(f.category == "no_metrics" for f in findings)

def test_target_missing():
    findings = run(_mkanalyzer([_hpa("gone", 1, 5)], deployment_exists=False).analyze())
    assert any(f.category == "target_missing" for f in findings)

def test_healthy_hpa_no_findings():
    findings = run(_mkanalyzer([_hpa("ok", 3, 10, last_scale=_NOW-timedelta(minutes=5))]).analyze())
    assert findings == []
```
---

## 4. Implementation Notes

- Wrap all `kubernetes.client` calls in `asyncio.to_thread()` to avoid blocking the event loop.
- `NetworkPolicyAnalyzer`: empty `V1LabelSelector` (no keys) matches ALL pods and is not an orphan.
- `PDBAnalyzer`: PDBs using `matchExpressions` are skipped with a `WARNING`; deferred to follow-up.
- `HPAAnalyzer`: `minReplicas == maxReplicas` is logged at `WARNING` and excluded from `never_scaling`.
- `ANALYZER_ID` values register in the central registry (section 09); watchdog (section 04) dispatches by ID.
- `suggested_fix_class` strings are Remediator registry keys (section 15); never branch on them at call sites.
