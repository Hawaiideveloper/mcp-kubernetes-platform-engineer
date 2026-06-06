from __future__ import annotations

import json
import logging
from typing import List, Optional

from kubernetes.client import (
    V1Pod,
)
from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef, Severity

logger = logging.getLogger(__name__)

_IMAGE_PULL_REASONS = frozenset({"ImagePullBackOff", "ErrImagePull"})


class PodAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "pod"

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        if namespace:
            pods = self.core_v1.list_namespaced_pod(namespace).items
        else:
            pods = self.core_v1.list_pod_for_all_namespaces().items
        findings: List[Finding] = []
        for pod in pods:
            findings.extend(self._evaluate_pod(pod))
        return findings

    def _evaluate_pod(self, pod: V1Pod) -> List[Finding]:
        ns = pod.metadata.namespace
        name = pod.metadata.name
        uid = pod.metadata.uid or ""
        ref = ResourceRef(kind="Pod", namespace=ns, name=name, uid=uid)

        events = self._fetch_events(ns, name)
        event_messages = tuple(
            f"{e.reason}: {e.message}" for e in events if e.reason
        )
        findings: List[Finding] = []

        for cs in pod.status.init_container_statuses or []:
            f = self._check_container(ref, cs, event_messages, is_init=True)
            if f:
                findings.append(f)
        for cs in pod.status.container_statuses or []:
            f = self._check_container(ref, cs, event_messages, is_init=False)
            if f:
                findings.append(f)

        findings.extend(self._check_pending(ref, pod, event_messages))
        findings.extend(self._check_probes(ref, events, event_messages))
        findings.extend(self._check_mount(ref, events, event_messages))
        return findings

    def _check_container(self, ref, cs, evts, is_init):
        label = ("init-container" if is_init else "container") + f"/{cs.name}"
        snap = json.dumps(
            {
                "name": cs.name,
                "ready": cs.ready,
                "restart_count": cs.restart_count,
                "state": str(cs.state),
                "last_state": str(cs.last_state),
            }
        )
        if cs.state and cs.state.waiting:
            reason = cs.state.waiting.reason or ""
            if reason in _IMAGE_PULL_REASONS:
                return Finding(
                    ref, "high", "image-pull",
                    Evidence(evts, self._log(ref, cs.name), snap),
                    "ImageTagRemediator",
                    f"{label} cannot pull {cs.image!r}: {reason}",
                )
            if reason == "CrashLoopBackOff":
                sev = self._crash_sev(cs.restart_count or 0)
                return Finding(
                    ref, sev, "crash-loop",
                    Evidence(evts, self._log(ref, cs.name), snap),
                    "RestartFirstLadderRemediator",
                    f"{label} crash-looping (restarts={cs.restart_count})",
                )
        if cs.last_state and cs.last_state.terminated:
            t = cs.last_state.terminated
            if t.reason == "OOMKilled" or t.exit_code == 137:
                return Finding(
                    ref, "high", "oom-killed",
                    Evidence(evts, self._log(ref, cs.name), snap),
                    "MemoryLimitRemediator",
                    f"{label} OOMKilled (exit_code={t.exit_code})",
                )
        return None

    def _check_pending(self, ref, pod, evts):
        if (pod.status.phase or "").lower() != "pending":
            return []
        sched = [m for m in evts if "FailedScheduling" in m]
        if not sched:
            return []
        return [Finding(
            ref, "medium", "pending-scheduling",
            Evidence(evts, "", json.dumps({"phase": pod.status.phase})),
            "NodeAffinityRemediator",
            f"Pod stuck Pending: {sched[0]}",
        )]

    def _check_probes(self, ref, events, evts):
        bad = [e for e in events if e.reason == "Unhealthy"]
        if not bad:
            return []
        return [Finding(
            ref, "medium", "probe-failure",
            Evidence(evts, "", ""),
            "ProbeTuningRemediator",
            "Probe failure: " + (bad[-1].message or "probe failed"),
        )]

    def _check_mount(self, ref, events, evts):
        bad = [e for e in events if e.reason == "FailedMount"]
        if not bad:
            return []
        return [Finding(
            ref, "high", "failed-mount",
            Evidence(evts, "", ""),
            "PVCRemediator",
            "FailedMount: " + (bad[-1].message or ""),
        )]

    def _crash_sev(self, restarts: int) -> Severity:
        if restarts >= 5:
            return "critical"
        if restarts >= 2:
            return "high"
        return "medium"

    def _log(self, ref: ResourceRef, container: str) -> str:
        try:
            return self.core_v1.read_namespaced_pod_log(
                ref.name,
                ref.namespace,
                container=container,
                tail_lines=self.log_tail_lines,
            )
        except ApiException:
            return ""

    def _fetch_events(self, ns: str, name: str) -> list:
        try:
            return self.core_v1.list_namespaced_event(
                ns,
                field_selector=f"involvedObject.name={name}",
            ).items
        except ApiException:
            return []
