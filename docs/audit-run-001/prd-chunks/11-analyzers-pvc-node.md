# PRD Section 11 — PVC/Storage and Node Analyzers

## Context

No `PVCAnalyzer` or `NodeAnalyzer` exists. `DiagnosticsManager._check_storage` (266-275)
and `MonitoringManager._analyze_node_resources` (220-230) return hardcoded strings.
Both analyzers extend `BaseAnalyzer` / `Finding` from section 09.

---

## 1. PVCAnalyzer

### 1.1 Class Signature

```python
# src/analyzers/pvc_analyzer.py
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import List, Optional
from kubernetes.client import CoreV1Api, AppsV1Api
from kubernetes.client.exceptions import ApiException
from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)
_NFS_PROVISIONERS = frozenset({
    "nfs.csi.k8s.io", "cluster.local/nfs-provisioner", "nfs-subdir-external-provisioner",
})

class PVCAnalyzer(BaseAnalyzer):
    # daxxon-ai-gpu-01 note: NFS-backed PVCs require manual `apt-get install -y nfs-common`
    # on Ubuntu 24.04 nodes — the provisioner does not automate this step.
    ANALYZER_ID = "pvc"

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        pvcs = (self.core_v1.list_namespaced_persistent_volume_claim(namespace).items
                if namespace else
                self.core_v1.list_persistent_volume_claim_for_all_namespaces().items)
        scs  = self._fetch_storage_classes()
        pods = (self.core_v1.list_namespaced_pod(namespace).items if namespace
                else self.core_v1.list_pod_for_all_namespaces().items)
        out: List[Finding] = []
        for pvc in pvcs: out.extend(self._evaluate_pvc(pvc, scs, pods))
        return out
```

### 1.2 Kubernetes API Calls

| Check | API Method |
|---|---|
| List PVCs | `core_v1.list_persistent_volume_claim_for_all_namespaces()` |
| StorageClasses | `core_v1.list_storage_class()` |
| Events | `core_v1.list_namespaced_event(ns, field_selector="involvedObject.name=<name>")` |
| Pods | `core_v1.list_pod_for_all_namespaces()` |
| Capacity | metrics-server custom objects (raises on absence; skipped gracefully) |

### 1.3 Detection Logic (condensed)

```python
    def _evaluate_pvc(self, pvc, scs, pods):
        ns,name,uid = pvc.metadata.namespace,pvc.metadata.name,pvc.metadata.uid or ""
        ref=ResourceRef("PersistentVolumeClaim",ns,name,uid)
        phase=(pvc.status.phase or "").strip(); sc=pvc.spec.storage_class_name or ""
        evts=self._fetch_events(ns,name)
        msgs=tuple(f"{e.reason}: {e.message}" for e in evts if e.reason)
        snap=json.dumps({"phase":phase,"storageClass":sc}); out=[]
        if phase=="Pending":
            if sc and sc not in scs:
                out.append(Finding(ref,"high","pvc-pending-no-sc",Evidence(msgs,"",snap),
                                   "StorageClassRemediator",f"SC {sc!r} absent"))
            elif any("ProvisioningFailed" in m or "no persistent volumes" in m.lower() for m in msgs):
                out.append(Finding(ref,"high","pvc-pending-no-pv",Evidence(msgs,"",snap),
                                   "PVProvisioningRemediator","No matching PV"))
            else:
                out.append(Finding(ref,"medium","pvc-pending-unknown",Evidence(msgs,"",snap),
                                   "PVCPendingRemediator","PVC Pending; no event"))
        if phase=="Bound":
            out.extend(self._check_mount_failed(ref,pods,msgs,snap))
            out.extend(self._check_capacity(ref,pvc,snap))
            out.extend(self._check_rwo_multi_node(ref,pvc,pods,msgs,snap))
        out.extend(self._check_nfs_advisory(ref,sc,scs,snap))
        return out

    def _check_mount_failed(self, ref, pods, msgs, snap):
        out=[]
        for pod in pods:
            if pod.metadata.namespace!=ref.namespace: continue
            if not any(v.persistent_volume_claim and v.persistent_volume_claim.claim_name==ref.name
                       for v in (pod.spec.volumes or [])): continue
            bad=[e for e in self._fetch_events(pod.metadata.namespace,pod.metadata.name)
                 if e.reason in ("FailedMount","FailedAttach") and self._within_last_hour(e.last_timestamp)]
            if bad: out.append(Finding(ref,"high","pvc-mount-failed",Evidence(msgs,"",snap),
                                       "PVCMountRemediator",f"FailedMount on {pod.metadata.name}"))
        return out

    def _check_capacity(self, ref, pvc, snap):
        try:
            used = self._fetch_volume_used_bytes(ref.namespace, ref.name)
            cap  = self._parse_capacity(pvc.status.capacity or {})
            if cap and used is not None and used / cap > 0.85:
                sev = "critical" if used / cap > 0.95 else "high"
                return [Finding(ref, sev, "pvc-capacity-high", Evidence((),"",snap),
                                "VolumeExpansionRemediator", f"PVC at {used/cap:.0%} capacity")]
        except Exception as exc:
            logger.debug("capacity skipped %s/%s: %s", ref.namespace, ref.name, exc)
        return []

    def _check_rwo_multi_node(self, ref, pvc, pods, msgs, snap):
        if "ReadWriteOnce" not in (pvc.spec.access_modes or []): return []
        nodes = {p.spec.node_name for p in pods if p.metadata.namespace == ref.namespace
                 and any(v.persistent_volume_claim and v.persistent_volume_claim.claim_name == ref.name
                         for v in (p.spec.volumes or [])) and p.spec.node_name}
        return ([Finding(ref,"high","pvc-rwo-multi-node",Evidence(msgs,"",snap),
                         "RWOConflictRemediator",f"RWO PVC on nodes: {sorted(nodes)}")]
                if len(nodes) > 1 else [])

    def _check_nfs_advisory(self, ref, sc, scs, snap):
        if (scs.get(sc) or {}).get("provisioner","") in _NFS_PROVISIONERS:
            return [Finding(ref,"info","pvc-nfs-common-advisory",Evidence((),"",snap),
                            "NFSNodePrepRemediator",
                            "NFS PVC — nodes need: apt-get install -y nfs-common")]
        return []

    def _fetch_events(self, ns, name):
        try: return self.core_v1.list_namespaced_event(
                ns, field_selector=f"involvedObject.name={name}").items
        except ApiException: return []

    def _fetch_storage_classes(self):
        try: return {s.metadata.name: {"provisioner": s.provisioner}
                     for s in self.core_v1.list_storage_class().items}
        except ApiException: return {}

    @staticmethod
    def _within_last_hour(ts):
        if ts is None: return False
        delta = datetime.now(timezone.utc) - (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))
        return delta.total_seconds() < 3600

    @staticmethod
    def _parse_capacity(cap):
        raw = cap.get("storage","")
        for s,m in [("Gi",1<<30),("Mi",1<<20),("Ki",1<<10),("G",10**9),("M",10**6),("K",10**3)]:
            if raw.endswith(s): return int(raw[:-len(s)])*m
        return int(raw) if raw.isdigit() else None

    def _fetch_volume_used_bytes(self, ns, pvc_name):
        raise NotImplementedError("plug in metrics-server client")
```

### 1.4 Finding Mapping

| Condition | Category | Severity | `suggested_fix_class` |
|---|---|---|---|
| StorageClass missing | `pvc-pending-no-sc` | high | `StorageClassRemediator` |
| No matching PV | `pvc-pending-no-pv` | high | `PVProvisioningRemediator` |
| Pending, no event | `pvc-pending-unknown` | medium | `PVCPendingRemediator` |
| FailedMount / FailedAttach | `pvc-mount-failed` | high | `PVCMountRemediator` |
| Capacity 85-95 % | `pvc-capacity-high` | high | `VolumeExpansionRemediator` |
| Capacity >95 % | `pvc-capacity-high` | critical | `VolumeExpansionRemediator` |
| RWO multi-node | `pvc-rwo-multi-node` | high | `RWOConflictRemediator` |
| NFS provisioner | `pvc-nfs-common-advisory` | info | `NFSNodePrepRemediator` |

---

## 2. NodeAnalyzer

### 2.1 Class Signature

```python
# src/analyzers/node_analyzer.py
from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import List, Optional
from kubernetes.client import CoreV1Api, AppsV1Api
from kubernetes.client.exceptions import ApiException
from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)
_PRESSURE = frozenset({"MemoryPressure","DiskPressure","PIDPressure"})
_STALE_SEC, _MAX_TAINTS, _SKEW_ALLOWED = 120, 5, 1

class NodeAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "node"

    def __init__(self, core_v1: CoreV1Api, apps_v1: AppsV1Api,
                 log_tail_lines: int = 100, control_plane_minor: Optional[int] = None):
        super().__init__(core_v1, apps_v1, log_tail_lines)
        self._cp_minor = control_plane_minor

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        try: nodes = self.core_v1.list_node().items
        except ApiException as exc: logger.error("list_node: %s", exc); return []
        out = []
        for n in nodes: out.extend(self._evaluate_node(n))
        return out
```

### 2.2 Kubernetes API Calls

| Check | API Method |
|---|---|
| All nodes | `core_v1.list_node()` |
| Conditions / taints / version | parsed from returned `V1Node` object |
| Control-plane minor | injected by caller (`core_v1.get_api_versions()` at startup) |

### 2.3 Detection Logic

```python
    def _evaluate_node(self, node):
        name = node.metadata.name; uid = node.metadata.uid or ""
        ref  = ResourceRef("Node","",name,uid)
        conds = node.status.conditions or []
        taints = node.spec.taints or []
        snap = json.dumps({"conditions":[{"type":c.type,"status":c.status} for c in conds],
                           "taints":len(taints)})
        out = []
        for c in conds:
            if c.type=="Ready" and c.status!="True":
                out.append(Finding(ref,"critical","node-not-ready",Evidence((),"",snap),
                                   "NodeRemediator",f"{name} NotReady"))
            if c.type in _PRESSURE and c.status=="True":
                out.append(Finding(ref,"high",f"node-{c.type.lower()}",Evidence((),"",snap),
                                   "NodePressureRemediator",f"{name} {c.type}"))
            ts = c.last_heartbeat_time or c.last_transition_time
            if ts is not None:
                delta = datetime.now(timezone.utc) - (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))
                if delta.total_seconds() > _STALE_SEC:
                    out.append(Finding(ref,"high","node-kubelet-stale",Evidence((),"",snap),
                                       "KubeletRestartRemediator",f"{name} kubelet silent >{_STALE_SEC}s"))
        if len(taints) > _MAX_TAINTS:
            out.append(Finding(ref,"medium","node-high-taint-count",Evidence((),"",snap),
                               "TaintAuditRemediator",f"{name} has {len(taints)} taints"))
        if self._cp_minor is not None:
            raw = getattr(node.status.node_info,"kubelet_version","") or ""
            parts = raw.lstrip("v").split(".")
            if len(parts)>=2 and parts[1].isdigit():
                skew = self._cp_minor - int(parts[1])
                if skew > _SKEW_ALLOWED:
                    out.append(Finding(ref,"medium","node-version-skew",Evidence((),"",snap),
                                       "NodeUpgradeRemediator",f"{name} {raw} {skew} minor(s) behind CP"))
        return out
```

### 2.4 Finding Mapping

| Condition | Category | Severity | `suggested_fix_class` |
|---|---|---|---|
| Node NotReady | `node-not-ready` | critical | `NodeRemediator` |
| DiskPressure | `node-diskpressure` | high | `NodePressureRemediator` |
| MemoryPressure | `node-memorypressure` | high | `NodePressureRemediator` |
| PIDPressure | `node-pidpressure` | high | `NodePressureRemediator` |
| Kubelet stale >2 min | `node-kubelet-stale` | high | `KubeletRestartRemediator` |
| Taint count >5 | `node-high-taint-count` | medium | `TaintAuditRemediator` |
| Version skew >1 minor | `node-version-skew` | medium | `NodeUpgradeRemediator` |

---

## 3. Tests

```python
# tests/analyzers/test_pvc_analyzer.py + test_node_analyzer.py
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from src.analyzers.pvc_analyzer import PVCAnalyzer
from src.analyzers.node_analyzer import NodeAnalyzer

run = lambda c: asyncio.get_event_loop().run_until_complete(c)

def _pvc(name, phase, sc="sc", modes=None):
    p=MagicMock(); p.metadata.namespace="ns"; p.metadata.name=name; p.metadata.uid="u"
    p.status.phase=phase; p.spec.storage_class_name=sc; p.status.capacity={}
    p.spec.access_modes=modes or ["ReadWriteOnce"]; return p

def _pvc_az(pvcs, scs=None, pods=None):
    c=MagicMock(); c.list_persistent_volume_claim_for_all_namespaces.return_value.items=pvcs
    c.list_namespaced_event.return_value.items=[]; c.list_storage_class.return_value.items=scs or []
    c.list_pod_for_all_namespaces.return_value.items=pods or []; return PVCAnalyzer(core_v1=c,apps_v1=MagicMock())

def test_pending_missing_sc():
    assert any(f.category=="pvc-pending-no-sc"
               for f in run(_pvc_az([_pvc("p","Pending",sc="gone")]).analyze()))

def test_mount_failed():
    pod=MagicMock(); pod.metadata.namespace="ns"; pod.spec.node_name="n1"
    v=MagicMock(); v.persistent_volume_claim.claim_name="p"; pod.spec.volumes=[v]
    evt=MagicMock(); evt.reason="FailedMount"; evt.message="err"
    evt.last_timestamp=datetime.now(timezone.utc)
    a=_pvc_az([_pvc("p","Bound")],pods=[pod])
    a.core_v1.list_namespaced_event.return_value.items=[evt]
    assert any(f.category=="pvc-mount-failed" for f in run(a.analyze()))

def test_rwo_multi_node():
    def _pod(node):
        p=MagicMock(); p.metadata.namespace="ns"; p.spec.node_name=node
        v=MagicMock(); v.persistent_volume_claim.claim_name="p"; p.spec.volumes=[v]; return p
    assert any(f.category=="pvc-rwo-multi-node"
               for f in run(_pvc_az([_pvc("p","Bound")],pods=[_pod("a"),_pod("b")]).analyze()))

def test_nfs_advisory():
    sc=MagicMock(); sc.metadata.name="nfs-sc"; sc.provisioner="nfs.csi.k8s.io"
    assert any(f.category=="pvc-nfs-common-advisory"
               for f in run(_pvc_az([_pvc("p","Bound",sc="nfs-sc")],scs=[sc]).analyze()))

# --- Node helpers ---
def _cond(t,s,hb=None):
    c=MagicMock(); c.type=t; c.status=s; c.last_heartbeat_time=hb; c.last_transition_time=hb; return c

def _node_az(conds, taints=0, ver="v1.28.4", cp=None):
    n=MagicMock(); n.metadata.name="nx"; n.metadata.uid="u"
    n.status.conditions=conds; n.spec.taints=[MagicMock()]*taints
    n.status.node_info.kubelet_version=ver
    c=MagicMock(); c.list_node.return_value.items=[n]
    return NodeAnalyzer(core_v1=c, apps_v1=MagicMock(), control_plane_minor=cp)

def test_not_ready():
    assert any(f.category=="node-not-ready" and f.severity=="critical"
               for f in run(_node_az([_cond("Ready","Unknown")]).analyze()))

def test_pressures():
    cats={f.category for f in run(_node_az([_cond("Ready","True"),
          _cond("MemoryPressure","True"),_cond("DiskPressure","True"),
          _cond("PIDPressure","True")]).analyze())}
    assert {"node-memorypressure","node-diskpressure","node-pidpressure"}.issubset(cats)

def test_kubelet_stale_and_skew_and_taints():
    stale=datetime.now(timezone.utc)-timedelta(minutes=5)
    cats={f.category for f in run(
        _node_az([_cond("Ready","True",hb=stale)],taints=6,ver="v1.26.0",cp=28).analyze())}
    assert "node-kubelet-stale" in cats
    assert "node-high-taint-count" in cats
    assert "node-version-skew" in cats

def test_healthy_zero_findings():
    assert run(_node_az([_cond("Ready","True"),_cond("DiskPressure","False"),
                          _cond("MemoryPressure","False"),_cond("PIDPressure","False")],cp=28
                        ).analyze()) == []
```

---

## 4. Implementation Notes

- All `kubernetes.client` calls are synchronous; wrap in `asyncio.to_thread()` (same as `PodAnalyzer`).
- `_fetch_volume_used_bytes` raises `NotImplementedError`; `_check_capacity` catches all exceptions so the analyzer works without metrics-server.
- Resolve `_cp_minor` once at startup via `core_v1.get_api_versions()`, not per-node.
- `pvc-nfs-common-advisory` is `info` severity — render separately to avoid alert fatigue.
- `fingerprint()` excludes event messages and capacity bytes for stable dedup in SQLite (section 21).
