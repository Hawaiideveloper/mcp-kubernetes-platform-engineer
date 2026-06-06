from __future__ import annotations

import datetime
import json
import logging
from typing import Dict, List, Optional, Tuple

from kubernetes.client import (
    AppsV1Api, CoreV1Api, NetworkingV1Api, V1Ingress, V1Secret,
)
from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)

_NGINX_ONLY_ANNOTATIONS = frozenset({
    "nginx.ingress.kubernetes.io/rewrite-target",
    "nginx.ingress.kubernetes.io/use-regex",
    "nginx.ingress.kubernetes.io/proxy-body-size",
    "nginx.ingress.kubernetes.io/ssl-passthrough",
})


class IngressAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "ingress"
    TLS_WARN_DAYS = 30

    def __init__(self, core_v1: CoreV1Api, apps_v1: AppsV1Api,
                 networking_v1: Optional[NetworkingV1Api] = None,
                 installed_controller: str = "nginx") -> None:
        super().__init__(core_v1, apps_v1)
        self.networking_v1 = networking_v1 or NetworkingV1Api()
        self.installed_controller = installed_controller

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        ings = (self.networking_v1.list_namespaced_ingress(namespace).items if namespace
                else self.networking_v1.list_ingress_for_all_namespaces().items)
        findings: List[Finding] = []
        host_map: Dict[Tuple[str, str], str] = {}
        for ing in ings:
            findings.extend(self._check_backends(ing))
            findings.extend(self._check_tls(ing))
            findings.extend(self._check_annotations(ing))
            self._detect_host_conflicts(ing, host_map, findings)
        return findings

    def _ref(self, ing: V1Ingress) -> ResourceRef:
        return ResourceRef("Ingress", ing.metadata.namespace,
                           ing.metadata.name, ing.metadata.uid or "")

    def _check_backends(self, ing: V1Ingress) -> List[Finding]:
        ref, ns, name = self._ref(ing), ing.metadata.namespace, ing.metadata.name
        findings: List[Finding] = []
        for rule in ing.spec.rules or []:
            for path in rule.http.paths if rule.http else []:
                svc_name = (path.backend.service.name
                            if path.backend and path.backend.service else None)
                if not svc_name:
                    findings.append(Finding(ref, "high", "missing-backend",
                        Evidence((), "", json.dumps({"host": rule.host})),
                        "IngressBackendRemediator",
                        f"Ingress {ns}/{name} rule host={rule.host!r} has no backend."))
                    continue
                try:
                    self.core_v1.read_namespaced_service(svc_name, ns)
                except ApiException as exc:
                    if exc.status == 404:
                        findings.append(Finding(ref, "high", "missing-backend",
                            Evidence((), "", json.dumps({"service": svc_name})),
                            "IngressBackendRemediator",
                            f"Ingress {ns}/{name} backend service {svc_name!r} not found."))
        return findings

    def _check_tls(self, ing: V1Ingress) -> List[Finding]:
        ref, ns, name = self._ref(ing), ing.metadata.namespace, ing.metadata.name
        findings: List[Finding] = []
        for tls_entry in ing.spec.tls or []:
            sn = tls_entry.secret_name
            if not sn:
                continue
            try:
                secret: V1Secret = self.core_v1.read_namespaced_secret(sn, ns)
            except ApiException as exc:
                if exc.status == 404:
                    findings.append(Finding(ref, "critical", "tls-secret-missing",
                        Evidence((), "", json.dumps({"secret": sn})),
                        "TLSSecretRemediator",
                        f"Ingress {ns}/{name} TLS secret {sn!r} does not exist."))
                continue
            days = self._cert_days_remaining((secret.data or {}).get("tls.crt"))
            if days is not None and days < self.TLS_WARN_DAYS:
                findings.append(Finding(ref, "critical" if days <= 7 else "high", "tls-expiry",
                    Evidence((), "", json.dumps({"secret": sn, "days_remaining": days})),
                    "TLSRenewalRemediator",
                    f"Ingress {ns}/{name} TLS secret {sn!r} expires in {days} day(s)."))
        return findings

    def _cert_days_remaining(self, cert_pem_b64: Optional[str]) -> Optional[int]:
        if not cert_pem_b64:
            return None
        import base64
        try:
            pem = base64.b64decode(cert_pem_b64)
            from cryptography import x509 as cx509
            from cryptography.hazmat.backends import default_backend
            cert = cx509.load_pem_x509_certificate(pem, default_backend())
            return (cert.not_valid_after_utc
                    - datetime.datetime.now(tz=datetime.timezone.utc)).days
        except Exception:
            return None

    def _detect_host_conflicts(self, ing: V1Ingress,
                               host_map: Dict[Tuple[str, str], str],
                               findings: List[Finding]) -> None:
        ref = self._ref(ing)
        fqn = f"{ing.metadata.namespace}/{ing.metadata.name}"
        ic = (ing.spec.ingress_class_name or
              (ing.metadata.annotations or {}).get("kubernetes.io/ingress.class", "default"))
        for rule in ing.spec.rules or []:
            key = (rule.host or "", ic)
            if key in host_map and host_map[key] != fqn:
                findings.append(Finding(ref, "high", "host-conflict",
                    Evidence((), "", json.dumps({"host": key[0], "ingressClass": ic,
                                                 "conflicting": host_map[key]})),
                    "HostConflictRemediator",
                    f"Ingress {fqn} and {host_map[key]} both claim "
                    f"host {key[0]!r} on ingressClass {ic!r}."))
            else:
                host_map[key] = fqn

    def _check_annotations(self, ing: V1Ingress) -> List[Finding]:
        ref, ns, name = self._ref(ing), ing.metadata.namespace, ing.metadata.name
        anns = ing.metadata.annotations or {}
        if self.installed_controller == "nginx":
            return []
        return [Finding(ref, "medium", "unsupported-annotation",
                    Evidence((), "", json.dumps({"annotation": a,
                                                 "controller": self.installed_controller})),
                    "AnnotationMigrationRemediator",
                    f"Ingress {ns}/{name} uses nginx annotation {a!r} "
                    f"but controller is {self.installed_controller!r}.")
                for a in _NGINX_ONLY_ANNOTATIONS if a in anns]
