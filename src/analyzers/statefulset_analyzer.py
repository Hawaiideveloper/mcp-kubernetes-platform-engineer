from __future__ import annotations
import json
import logging
from typing import List, Optional

from kubernetes.client import V1StatefulSet
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

        pods = self._list_pods(ns, name)
        pending = [p for p in pods if (p.status.phase or "").lower() == "pending"]
        for pod in pending:
            events = self._fetch_events(ns, pod.metadata.name)
            pvc_events = [e for e in events if e.reason in ("FailedMount", "Unbound")]
            if pvc_events:
                snap = json.dumps({"pod": pod.metadata.name, "phase": pod.status.phase})
                findings.append(Finding(
                    resource=ResourceRef(kind="Pod", namespace=ns, name=pod.metadata.name, uid=pod.metadata.uid or ""),
                    severity="high",
                    category="pvc-binding-pending",
                    evidence=Evidence(
                        events=tuple(f"{e.reason}: {e.message}" for e in pvc_events),
                        log_tail="",
                        status_snapshot=snap,
                    ),
                    suggested_fix_class="PVCRemediator",
                    root_cause_hypothesis=f"StatefulSet {name} pod {pod.metadata.name} stuck Pending due to PVC binding failure",
                ))

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
                root_cause_hypothesis=f"StatefulSet {name}: ordinals {missing} missing while higher ordinals are present",
            ))

        pvcs = self._list_pvcs(ns, name)
        for pvc in pvcs:
            phase = pvc.status.phase or ""
            if phase in ("Lost", "Pending"):
                findings.append(Finding(
                    resource=ResourceRef(kind="PersistentVolumeClaim", namespace=ns, name=pvc.metadata.name, uid=pvc.metadata.uid or ""),
                    severity="high",
                    category="pvc-template-failure",
                    evidence=Evidence(events=(), log_tail="", status_snapshot=json.dumps({"pvc": pvc.metadata.name, "phase": phase})),
                    suggested_fix_class="PVCRemediator",
                    root_cause_hypothesis=f"StatefulSet {name} VolumeClaimTemplate PVC {pvc.metadata.name} is in phase {phase!r}",
                ))

        return findings

    def _list_pods(self, ns: str, sts_name: str):
        try:
            return self.core_v1.list_namespaced_pod(
                ns, label_selector="statefulset.kubernetes.io/pod-name"
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
