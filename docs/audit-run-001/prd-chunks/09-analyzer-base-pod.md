# PRD Section 09 — Analyzer Base Class + Pod Analyzer

## Context

The audit found no `BaseAnalyzer`, `Finding`, or abstract analyzer contract anywhere in `src/`. `DiagnosticsManager.troubleshoot_pod_issues` (lines 110-125) returns a hardcoded `CrashLoopBackOff` scenario for every pod, never calling `kubernetes.client`. This section specifies the foundation.

---

## 1. Finding Dataclass

```python
# src/analyzers/base.py
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

Severity = Literal["critical", "high", "medium", "low", "info"]

@dataclass(frozen=True)
class ResourceRef:
    kind: str        # e.g. "Pod"
    namespace: str   # "" for cluster-scoped
    name: str
    uid: str         # V1ObjectMeta.uid — must not default to ""

@dataclass(frozen=True)
class Evidence:
    events: tuple[str, ...]   # tuple so it is hashable
    log_tail: str             # last N lines or ""
    status_snapshot: str      # JSON-serialized subset of pod.status

@dataclass(frozen=True)
class Finding:
    resource: ResourceRef
    severity: Severity
    category: str                  # "image-pull" | "crash-loop" | "oom-killed" | ...
    evidence: Evidence
    suggested_fix_class: str       # maps 1:1 to a Remediator subclass name
    root_cause_hypothesis: str

    def fingerprint(self) -> str:
        key = f"{self.resource.kind}/{self.resource.namespace}/{self.resource.name}/{self.category}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint": self.fingerprint(),
            "resource": {"kind": self.resource.kind, "namespace": self.resource.namespace,
                         "name": self.resource.name, "uid": self.resource.uid},
            "severity": self.severity,
            "category": self.category,
            "evidence": {"events": list(self.evidence.events),
                         "log_tail": self.evidence.log_tail,
                         "status_snapshot": self.evidence.status_snapshot},
            "suggested_fix_class": self.suggested_fix_class,
            "root_cause_hypothesis": self.root_cause_hypothesis,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
```

`frozen=True` enables `__hash__`. `Evidence.events` is a `tuple` to preserve hashability. `fingerprint()` excludes `restart_count` and `log_tail` so the same pod/category yields the same key across poll cycles.

---

## 2. BaseAnalyzer Abstract Class

```python
# src/analyzers/base.py  (continued)
import logging
from abc import ABC, abstractmethod
from typing import List

from kubernetes.client import CoreV1Api, AppsV1Api

logger = logging.getLogger(__name__)

class BaseAnalyzer(ABC):
    """
    Lifecycle per run_safe() call:
      1. pre_check()       — lightweight gate (RBAC / API reachability)
      2. analyze()         — fetch_resources -> evaluate -> emit Findings
    run_safe() deduplicates by fingerprint and catches all exceptions.
    """
    ANALYZER_ID: str = ""

    def __init__(self, core_v1: CoreV1Api, apps_v1: AppsV1Api, log_tail_lines: int = 100) -> None:
        self.core_v1 = core_v1
        self.apps_v1 = apps_v1
        self.log_tail_lines = log_tail_lines

    async def pre_check(self) -> bool:
        return True

    @abstractmethod
    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]: ...

    async def run_safe(self, namespace: Optional[str] = None) -> List[Finding]:
        if not await self.pre_check():
            logger.info("analyzer %s: pre_check failed, skipping", self.ANALYZER_ID)
            return []
        try:
            findings = await self.analyze(namespace)
            seen: set[str] = set()
            deduped: List[Finding] = []
            for f in findings:
                fp = f.fingerprint()
                if fp not in seen:
                    seen.add(fp)
                    deduped.append(f)
            return deduped
        except Exception as exc:
            logger.exception("analyzer %s raised: %s", self.ANALYZER_ID, exc)
            return []
```

---

## 3. PodAnalyzer

### 3.1 Field Reads by Failure Mode

| Condition | Primary field | Secondary |
|---|---|---|
| ImagePullBackOff | `container_status.state.waiting.reason` in `{"ImagePullBackOff","ErrImagePull"}` | `container_status.image` |
| CrashLoopBackOff | `container_status.state.waiting.reason == "CrashLoopBackOff"` | `container_status.restart_count` |
| OOMKilled | `container_status.last_state.terminated.reason == "OOMKilled"` | `last_state.terminated.exit_code == 137` |
| Probe failure | event `reason in {"Unhealthy"}` | event `message` |
| Init-container failure | `pod.status.init_container_statuses[*].state.waiting.reason` | `last_state.terminated.exit_code` |
| Pending / scheduling | `pod.status.phase == "Pending"` + event `reason == "FailedScheduling"` | event `message` |
| FailedMount | event `reason == "FailedMount"` | event `message` |

### 3.2 Implementation

```python
# src/analyzers/pod_analyzer.py
from __future__ import annotations
import json, logging
from typing import List, Optional

from kubernetes.client import (CoreV1Api, AppsV1Api, V1Pod, V1ContainerStatus,
                                V1ContainerState)
from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef, Severity

logger = logging.getLogger(__name__)
_IMAGE_PULL_REASONS = frozenset({"ImagePullBackOff", "ErrImagePull"})

class PodAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "pod"

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        pods = (self.core_v1.list_namespaced_pod(namespace).items if namespace
                else self.core_v1.list_pod_for_all_namespaces().items)
        findings: List[Finding] = []
        for pod in pods:
            findings.extend(self._evaluate_pod(pod))
        return findings

    def _evaluate_pod(self, pod: V1Pod) -> List[Finding]:
        ns, name, uid = pod.metadata.namespace, pod.metadata.name, pod.metadata.uid or ""
        ref = ResourceRef(kind="Pod", namespace=ns, name=name, uid=uid)
        events = self._fetch_events(ns, name)
        event_messages = tuple(f"{e.reason}: {e.message}" for e in events if e.reason)
        findings: List[Finding] = []

        for cs in (pod.status.init_container_statuses or []):
            f = self._check_container(ref, cs, event_messages, is_init=True)
            if f: findings.append(f)
        for cs in (pod.status.container_statuses or []):
            f = self._check_container(ref, cs, event_messages, is_init=False)
            if f: findings.append(f)

        findings.extend(self._check_pending(ref, pod, event_messages))
        findings.extend(self._check_probes(ref, events, event_messages))
        findings.extend(self._check_mount(ref, events, event_messages))
        return findings

    def _check_container(self, ref, cs: V1ContainerStatus, evts, is_init) -> Optional[Finding]:
        label = ("init-container" if is_init else "container") + f"/{cs.name}"
        snap = json.dumps({"name": cs.name, "ready": cs.ready,
                           "restart_count": cs.restart_count,
                           "state": str(cs.state), "last_state": str(cs.last_state)})
        if cs.state and cs.state.waiting:
            reason = cs.state.waiting.reason or ""
            if reason in _IMAGE_PULL_REASONS:
                return Finding(ref, "high", "image-pull",
                               Evidence(evts, self._log(ref, cs.name), snap),
                               "ImageTagRemediator",
                               f"{label} cannot pull {cs.image!r}: {reason}")
            if reason == "CrashLoopBackOff":
                sev = self._crash_sev(cs.restart_count or 0)
                return Finding(ref, sev, "crash-loop",
                               Evidence(evts, self._log(ref, cs.name), snap),
                               "RestartFirstLadderRemediator",
                               f"{label} crash-looping (restarts={cs.restart_count})")
        if cs.last_state and cs.last_state.terminated:
            t = cs.last_state.terminated
            if t.reason == "OOMKilled" or t.exit_code == 137:
                return Finding(ref, "high", "oom-killed",
                               Evidence(evts, self._log(ref, cs.name), snap),
                               "MemoryLimitRemediator",
                               f"{label} OOMKilled (exit_code={t.exit_code})")
        return None

    def _check_pending(self, ref, pod: V1Pod, evts) -> List[Finding]:
        if (pod.status.phase or "").lower() != "pending": return []
        sched = [m for m in evts if "FailedScheduling" in m]
        if not sched: return []
        return [Finding(ref, "medium", "pending-scheduling",
                        Evidence(evts, "", json.dumps({"phase": pod.status.phase})),
                        "NodeAffinityRemediator", f"Pod stuck Pending: {sched[0]}")]

    def _check_probes(self, ref, events, evts) -> List[Finding]:
        bad = [e for e in events if e.reason == "Unhealthy"]
        if not bad: return []
        return [Finding(ref, "medium", "probe-failure",
                        Evidence(evts, "", ""), "ProbeTuningRemediator",
                        f"Probe failure: {bad[-1].message or 'probe failed'}")]

    def _check_mount(self, ref, events, evts) -> List[Finding]:
        bad = [e for e in events if e.reason == "FailedMount"]
        if not bad: return []
        return [Finding(ref, "high", "failed-mount",
                        Evidence(evts, "", ""), "PVCRemediator",
                        f"FailedMount: {bad[-1].message or ''}")]

    def _crash_sev(self, restarts: int) -> Severity:
        if restarts >= 5: return "critical"
        if restarts >= 2: return "high"
        return "medium"

    def _log(self, ref: ResourceRef, container: str) -> str:
        try:
            return self.core_v1.read_namespaced_pod_log(
                ref.name, ref.namespace, container=container,
                tail_lines=self.log_tail_lines)
        except ApiException: return ""

    def _fetch_events(self, ns, name):
        try:
            return self.core_v1.list_namespaced_event(
                ns, field_selector=f"involvedObject.name={name}").items
        except ApiException: return []
```

### 3.3 Severity Rubric

| Condition | restarts >= 5 | restarts 2-4 | restarts < 2 |
|---|---|---|---|
| CrashLoopBackOff | critical | high | medium |
| OOMKilled | high | high | medium |
| ImagePullBackOff | high | high | n/a |
| Probe failure | medium | medium | medium |
| FailedMount | high | high | n/a |
| Pending/scheduling | medium | medium | medium |

`_crash_sev` uses `restart_count` as a proxy. `DeploymentAnalyzer` (section 10) promotes severity when `spec.replicas == 1`.

---

## 4. Tests

```python
# tests/analyzers/test_pod_analyzer.py
import asyncio, json, pytest
from unittest.mock import MagicMock
from kubernetes.client import (V1Pod, V1ObjectMeta, V1PodStatus, V1ContainerStatus,
    V1ContainerState, V1ContainerStateWaiting, V1ContainerStateTerminated, V1Event)
from src.analyzers.pod_analyzer import PodAnalyzer

def _pod(name, ns="default", uid="u1"):
    return V1Pod(metadata=V1ObjectMeta(name=name, namespace=ns, uid=uid),
                 status=V1PodStatus(phase="Running", container_statuses=[]))

def _analyzer(pods=None, events=None, log=""):
    c = MagicMock()
    c.list_pod_for_all_namespaces.return_value.items = pods or []
    c.list_namespaced_event.return_value.items = events or []
    c.read_namespaced_pod_log.return_value = log
    return PodAnalyzer(core_v1=c, apps_v1=MagicMock())

run = lambda coro: asyncio.get_event_loop().run_until_complete(coro)

def test_image_pull_backoff():
    pod = _pod("bad")
    pod.status.container_statuses = [V1ContainerStatus(
        name="app", image="bad:v1", ready=False, restart_count=0,
        state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="ImagePullBackOff")),
        last_state=V1ContainerState())]
    fs = run(_analyzer(pods=[pod]).analyze())
    assert len(fs) == 1 and fs[0].category == "image-pull"
    assert fs[0].suggested_fix_class == "ImageTagRemediator"
    assert fs[0].severity == "high"

def test_crash_loop_critical_at_5():
    pod = _pod("crasher")
    pod.status.container_statuses = [V1ContainerStatus(
        name="app", image="app:v1", ready=False, restart_count=5,
        state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="CrashLoopBackOff")),
        last_state=V1ContainerState())]
    fs = run(_analyzer(pods=[pod], log="panic\n").analyze())
    assert fs[0].category == "crash-loop" and fs[0].severity == "critical"
    assert "panic" in fs[0].evidence.log_tail

def test_oom_killed_exit_137():
    pod = _pod("oom")
    pod.status.container_statuses = [V1ContainerStatus(
        name="app", image="app:v1", ready=False, restart_count=1,
        state=V1ContainerState(),
        last_state=V1ContainerState(
            terminated=V1ContainerStateTerminated(reason="OOMKilled", exit_code=137)))]
    fs = run(_analyzer(pods=[pod]).analyze())
    assert fs[0].category == "oom-killed" and fs[0].suggested_fix_class == "MemoryLimitRemediator"

def test_finding_hashable_and_json():
    pod = _pod("img2")
    pod.status.container_statuses = [V1ContainerStatus(
        name="app", image="bad:v1", ready=False, restart_count=0,
        state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="ImagePullBackOff")),
        last_state=V1ContainerState())]
    fs = run(_analyzer(pods=[pod]).analyze())
    assert len({fs[0]}) == 1                       # hashable
    parsed = json.loads(fs[0].to_json())
    assert parsed["category"] == "image-pull"
    assert "fingerprint" in parsed
    assert isinstance(parsed["evidence"]["events"], list)

def test_dedup_across_runs():
    pod = _pod("img3")
    pod.status.container_statuses = [V1ContainerStatus(
        name="app", image="bad:v1", ready=False, restart_count=0,
        state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="ImagePullBackOff")),
        last_state=V1ContainerState())]
    a = _analyzer(pods=[pod])
    f1 = run(a.run_safe())[0]
    f2 = run(a.run_safe())[0]
    assert f1.fingerprint() == f2.fingerprint()
```

---

## 5. Implementation Notes

- All `kubernetes.client` calls are synchronous; wrap in `asyncio.to_thread()` in production to avoid blocking the event loop.
- `_log()` must handle `ApiException` with `status=400` (container not started yet) and `status=404` (pod deleted); return `""` in both cases.
- `fingerprint()` intentionally excludes `restart_count` and `log_tail` so a finding for the same pod/category yields the same key across every poll cycle, enabling SQLite deduplication (section 21).
- `suggested_fix_class` strings are the authoritative registry keys; the Remediator registry (section 15) maps them to callables at import time. Never check these strings at call sites.
