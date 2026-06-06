from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List, Literal, Optional

from kubernetes.client import CoreV1Api, NetworkingV1Api

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)

NetPolFindingType = Literal[
    "orphan_policy", "service_ingress_denied", "egress_dns_blocked", "no_default_deny"
]

_SEVERITY: Dict[str, str] = {
    "orphan_policy": "medium",
    "service_ingress_denied": "high",
    "egress_dns_blocked": "high",
    "no_default_deny": "medium",
}
_FIX_CLASS: Dict[str, str] = {
    "orphan_policy": "NetPolOrphanRemediator",
    "service_ingress_denied": "NetPolIngressRemediator",
    "egress_dns_blocked": "NetPolEgressDNSRemediator",
    "no_default_deny": "NetPolDefaultDenyRemediator",
}


class NetworkPolicyAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "network_policy"

    def __init__(
        self, core_v1: CoreV1Api, networking_v1: NetworkingV1Api, **kwargs
    ) -> None:
        from unittest.mock import MagicMock
        super().__init__(core_v1=core_v1, apps_v1=kwargs.get("apps_v1", MagicMock()))
        self.networking_v1 = networking_v1

    def _resolve_namespaces(self, namespace: Optional[str]) -> List[str]:
        if namespace:
            return [namespace]
        try:
            ns_list = self.core_v1.list_namespace()
            return [n.metadata.name for n in ns_list.items]
        except Exception:
            return ["default"]

    def _make_finding(
        self, kind: str, ns: str, name: str, uid: str, ftype: str, detail: str
    ) -> Finding:
        return Finding(
            resource=ResourceRef(kind=kind, namespace=ns, name=name, uid=uid),
            severity=_SEVERITY[ftype],  # type: ignore[arg-type]
            category=ftype,
            evidence=Evidence((), "", json.dumps({"detail": detail})),
            suggested_fix_class=_FIX_CLASS[ftype],
            root_cause_hypothesis=detail,
        )

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        findings: List[Finding] = []
        for ns in self._resolve_namespaces(namespace):
            policies = await asyncio.to_thread(
                self.networking_v1.list_namespaced_network_policy, ns
            )
            pods = await asyncio.to_thread(self.core_v1.list_namespaced_pod, ns)
            services = await asyncio.to_thread(self.core_v1.list_namespaced_service, ns)
            ns_obj = await asyncio.to_thread(self.core_v1.read_namespace, ns)
            ns_labels = ns_obj.metadata.labels or {}
            findings.extend(self._check_orphan(policies.items, pods.items, ns))
            findings.extend(
                self._check_service_ingress_denied(
                    policies.items, pods.items, services.items, ns
                )
            )
            findings.extend(self._check_egress_dns(policies.items, ns))
            findings.extend(
                self._check_no_default_deny(policies.items, ns_labels, ns)
            )
        return findings

    def _check_orphan(self, policies, pods, ns: str) -> List[Finding]:
        findings: List[Finding] = []
        pod_label_sets = [
            p.metadata.labels or {}
            for p in pods
            if p.metadata and p.metadata.labels
        ]
        for pol in policies:
            ml = (
                pol.spec.pod_selector.match_labels
                if pol.spec and pol.spec.pod_selector
                else None
            )
            if not ml:
                continue
            matched = any(
                all(pl.get(k) == v for k, v in ml.items()) for pl in pod_label_sets
            )
            if not matched:
                name = pol.metadata.name or ""
                uid = pol.metadata.uid or ""
                findings.append(
                    self._make_finding(
                        "NetworkPolicy", ns, name, uid, "orphan_policy",
                        f"NetworkPolicy {name} selector {ml} matches no pods",
                    )
                )
        return findings

    def _check_service_ingress_denied(
        self, policies, pods, services, ns: str
    ) -> List[Finding]:
        findings: List[Finding] = []
        for svc in services:
            if not (svc.spec and svc.spec.selector):
                continue
            sel = svc.spec.selector
            backing = [
                p for p in pods
                if p.metadata and p.metadata.labels
                and all(p.metadata.labels.get(k) == v for k, v in sel.items())
            ]
            if not backing:
                continue
            svc_ports = {
                p.target_port if p.target_port else p.port
                for p in (svc.spec.ports or [])
            }
            ingress_rules: List = []
            for pol in policies:
                if pol.spec and pol.spec.ingress:
                    ingress_rules.extend(pol.spec.ingress)
            if not ingress_rules and policies:
                svc_name = svc.metadata.name or ""
                svc_uid = svc.metadata.uid or ""
                findings.append(
                    self._make_finding(
                        "Service", ns, svc_name, svc_uid, "service_ingress_denied",
                        f"Service {svc_name} ports {svc_ports} blocked by NetworkPolicy",
                    )
                )
        return findings

    def _check_egress_dns(self, policies, ns: str) -> List[Finding]:
        findings: List[Finding] = []
        for pol in policies:
            if not (pol.spec and pol.spec.egress is not None):
                continue
            if not pol.spec.egress:
                name = pol.metadata.name or ""
                uid = pol.metadata.uid or ""
                findings.append(
                    self._make_finding(
                        "NetworkPolicy", ns, name, uid, "egress_dns_blocked",
                        f"NetworkPolicy {name} has egress rules but none permit DNS (port 53)",
                    )
                )
                continue
            has_dns = False
            for rule in pol.spec.egress:
                rule_ports = rule.ports or []
                for p in rule_ports:
                    if p.port in (53, "53"):
                        has_dns = True
                        break
                if has_dns:
                    break
            if not has_dns:
                name = pol.metadata.name or ""
                uid = pol.metadata.uid or ""
                findings.append(
                    self._make_finding(
                        "NetworkPolicy", ns, name, uid, "egress_dns_blocked",
                        f"NetworkPolicy {name} has egress rules but none permit DNS (port 53)",
                    )
                )
        return findings

    def _check_no_default_deny(
        self, policies, ns_labels: dict, ns: str
    ) -> List[Finding]:
        if ns_labels.get("env") != "production":
            return []
        for pol in policies:
            if not pol.spec:
                continue
            sel_labels = (
                pol.spec.pod_selector.match_labels
                if pol.spec.pod_selector
                else None
            )
            is_empty_sel = not sel_labels
            has_no_ingress = not pol.spec.ingress
            has_no_egress = pol.spec.egress is None or pol.spec.egress == []
            if is_empty_sel and has_no_ingress and has_no_egress:
                return []
        return [
            Finding(
                resource=ResourceRef("Namespace", ns, ns, ""),
                severity="medium",  # type: ignore[arg-type]
                category="no_default_deny",
                evidence=Evidence(
                    (), "", json.dumps({"detail": "no default-deny policy"})
                ),
                suggested_fix_class=_FIX_CLASS["no_default_deny"],
                root_cause_hypothesis=f"Namespace {ns} is production but has no default-deny",
            )
        ]
