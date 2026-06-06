from __future__ import annotations

import json
import logging
from typing import List, Optional

from kubernetes.client import V1Endpoints, V1Service
from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)


class ServiceAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "service"

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        svcs = (
            self.core_v1.list_namespaced_service(namespace).items
            if namespace
            else self.core_v1.list_service_for_all_namespaces().items
        )
        findings: List[Finding] = []
        for svc in svcs:
            findings.extend(self._evaluate_service(svc))
        return findings

    def _evaluate_service(self, svc: V1Service) -> List[Finding]:
        ns, name = svc.metadata.namespace, svc.metadata.name
        ref = ResourceRef("Service", ns, name, svc.metadata.uid or "")
        selector = svc.spec.selector or {}
        if not selector:
            return []
        label_sel = ",".join(f"{k}={v}" for k, v in selector.items())
        evts = self._events(ns, name)
        findings: List[Finding] = []
        try:
            pods = self.core_v1.list_namespaced_pod(ns, label_selector=label_sel).items
        except ApiException:
            pods = []
        if not pods:
            return [Finding(ref, "high", "selector-no-pods",
                Evidence(evts, "", json.dumps({"selector": selector})),
                "SelectorMismatchRemediator",
                f"Service {ns}/{name} selector {selector!r} matches no pods.")]
        try:
            ep: V1Endpoints = self.core_v1.read_namespaced_endpoints(name, ns)
            r = sum(len(s.addresses or []) for s in (ep.subsets or []))
            nr = sum(len(s.not_ready_addresses or []) for s in (ep.subsets or []))
            if r == 0 and nr > 0:
                findings.append(Finding(ref, "high", "endpoints-not-ready",
                    Evidence(evts, "", json.dumps({"ready": r, "not_ready": nr})),
                    "EndpointReadinessRemediator",
                    f"Service {ns}/{name} has {nr} endpoint(s), all NotReady."))
        except ApiException:
            pass
        for pd in svc.spec.ports or []:
            t = pd.target_port
            if not any(
                (isinstance(t, int) and cp.container_port == t)
                or (isinstance(t, str) and cp.name == t)
                for pod in pods
                for c in (pod.spec.containers or [])
                for cp in (c.ports or [])
            ):
                findings.append(Finding(ref, "medium", "port-mismatch",
                    Evidence(evts, "", json.dumps({"port": pd.port, "targetPort": str(t)})),
                    "PortMismatchRemediator",
                    f"Service port {pd.port}->targetPort {t!r} not in any matched pod."))
        if svc.spec.cluster_ip == "None":
            for pod in pods:
                if any(not cs.ready for cs in (pod.status.container_statuses or [])):
                    findings.append(Finding(ref, "low", "headless-misuse",
                        Evidence(evts, "", json.dumps({"clusterIP": "None"})),
                        "HeadlessServiceRemediator",
                        f"Service {ns}/{name} is headless but a matched pod is not ready."))
                    break
        return findings

    def _events(self, ns: str, name: str) -> tuple:
        try:
            items = self.core_v1.list_namespaced_event(
                ns, field_selector=f"involvedObject.name={name}").items
            return tuple(f"{e.reason}: {e.message}" for e in items if e.reason)
        except ApiException:
            return ()
