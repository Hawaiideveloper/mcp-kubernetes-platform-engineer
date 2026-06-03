# PRD Section 10 — Service, Endpoints, and Ingress Analyzers

## Context

The audit confirmed that `ServiceAnalyzer` and `IngressAnalyzer` are entirely absent from `src/`.
No code inspects `V1Endpoints`, `V1EndpointSlice`, or `V1Ingress` objects.
No TLS expiry check, host-conflict scan, or endpoint-readiness test exists anywhere.
Both analyzers inherit `BaseAnalyzer` (Section 09).

## 1. ServiceAnalyzer

### 1.1 Class Signature

```python
# src/analyzers/service_analyzer.py
from __future__ import annotations
import json, logging
from typing import List, Optional
from kubernetes.client import CoreV1Api, AppsV1Api, V1Service, V1Endpoints
from kubernetes.client.exceptions import ApiException
from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)

class ServiceAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "service"

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        svcs = (self.core_v1.list_namespaced_service(namespace).items if namespace
                else self.core_v1.list_service_for_all_namespaces().items)
        findings: List[Finding] = []
        for svc in svcs:
            findings.extend(self._evaluate_service(svc))
        return findings
```

### 1.2 Kubernetes-Client API Calls

| Call | Return type | Purpose |
|---|---|---|
| `CoreV1Api.list_namespaced_service(ns)` | `V1ServiceList` | Enumerate services in one namespace |
| `CoreV1Api.list_service_for_all_namespaces()` | `V1ServiceList` | Enumerate all services cluster-wide |
| `CoreV1Api.read_namespaced_endpoints(name, ns)` | `V1Endpoints` | Read endpoint subsets for a named service |
| `CoreV1Api.list_namespaced_pod(ns, label_selector=sel)` | `V1PodList` | Confirm pods matching the service selector |
| `CoreV1Api.list_namespaced_event(ns, field_selector=...)` | `V1EventList` | Correlate events to the service object |

### 1.3 Detection Logic

```python
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
            ep = self.core_v1.read_namespaced_endpoints(name, ns)
            r = sum(len(s.addresses or []) for s in (ep.subsets or []))
            nr = sum(len(s.not_ready_addresses or []) for s in (ep.subsets or []))
            if r == 0 and nr > 0:
                findings.append(Finding(ref, "high", "endpoints-not-ready",
                    Evidence(evts, "", json.dumps({"ready": r, "not_ready": nr})),
                    "EndpointReadinessRemediator",
                    f"Service {ns}/{name} has {nr} endpoint(s), all NotReady."))
        except ApiException:
            pass
        for pd in (svc.spec.ports or []):
            t = pd.target_port
            if not any((isinstance(t, int) and cp.container_port == t) or
                       (isinstance(t, str) and cp.name == t)
                       for pod in pods for c in (pod.spec.containers or [])
                       for cp in (c.ports or [])):
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
```

### 1.4 Finding Mapping Table

| category | severity | suggested_fix_class | Trigger |
|---|---|---|---|
| `selector-no-pods` | high | `SelectorMismatchRemediator` | `spec.selector` resolves to zero pods |
| `endpoints-not-ready` | high | `EndpointReadinessRemediator` | All `V1EndpointSubset.addresses` empty, `not_ready_addresses` non-empty |
| `port-mismatch` | medium | `PortMismatchRemediator` | `spec.ports[*].targetPort` not found in any matched pod `containerPort` |
| `headless-misuse` | low | `HeadlessServiceRemediator` | `spec.clusterIP == "None"` with at least one matched pod not ready |

## 2. IngressAnalyzer

### 2.1 Class Signature

```python
# src/analyzers/ingress_analyzer.py
from __future__ import annotations
import datetime, json, logging
from typing import Dict, List, Optional, Tuple
from kubernetes.client import CoreV1Api, AppsV1Api, NetworkingV1Api, V1Ingress, V1Secret
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
```

### 2.2 Kubernetes-Client API Calls

| Call | Return type | Purpose |
|---|---|---|
| `NetworkingV1Api.list_namespaced_ingress(ns)` | `V1IngressList` | Enumerate ingresses in one namespace |
| `NetworkingV1Api.list_ingress_for_all_namespaces()` | `V1IngressList` | Enumerate all ingresses cluster-wide |
| `CoreV1Api.read_namespaced_service(name, ns)` | `V1Service` | Confirm backend service exists |
| `CoreV1Api.read_namespaced_secret(name, ns)` | `V1Secret` | Read TLS secret for expiry inspection |
| `CoreV1Api.list_namespaced_event(ns, field_selector=...)` | `V1EventList` | Correlate events to the ingress object |

### 2.3 Detection Logic

```python
    def _ref(self, ing: V1Ingress) -> ResourceRef:
        return ResourceRef("Ingress", ing.metadata.namespace, ing.metadata.name,
                           ing.metadata.uid or "")

    def _check_backends(self, ing: V1Ingress) -> List[Finding]:
        ref, ns, name = self._ref(ing), ing.metadata.namespace, ing.metadata.name
        findings: List[Finding] = []
        for rule in (ing.spec.rules or []):
            for path in (rule.http.paths if rule.http else []):
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
        for tls_entry in (ing.spec.tls or []):
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
    def _cert_days_remaining(self, cert_pem_b64: str) -> Optional[int]:
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
        for rule in (ing.spec.rules or []):
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
```

### 2.4 Finding Mapping Table

| category | severity | suggested_fix_class | Trigger |
|---|---|---|---|
| `missing-backend` | high | `IngressBackendRemediator` | Backend service name absent or `read_namespaced_service` returns 404 |
| `tls-secret-missing` | critical | `TLSSecretRemediator` | `read_namespaced_secret` returns 404 for `spec.tls[*].secretName` |
| `tls-expiry` | critical (<=7d) / high (<30d) | `TLSRenewalRemediator` | Certificate `not_valid_after_utc` within threshold |
| `host-conflict` | high | `HostConflictRemediator` | Two ingresses share same `(host, ingressClass)` pair |
| `unsupported-annotation` | medium | `AnnotationMigrationRemediator` | Nginx-specific annotation present with non-nginx controller |

## 3. Unit Tests

```python
# tests/analyzers/test_service_analyzer.py
import asyncio
from unittest.mock import MagicMock
from kubernetes.client import (
    V1Service, V1ServiceSpec, V1ServicePort, V1ObjectMeta,
    V1Endpoints, V1EndpointSubset, V1EndpointAddress,
    V1Pod, V1PodSpec, V1Container, V1ContainerPort, V1PodStatus,
)
from src.analyzers.service_analyzer import ServiceAnalyzer

run = lambda coro: asyncio.get_event_loop().run_until_complete(coro)

def _svc(name, target_port=8080):
    return V1Service(
        metadata=V1ObjectMeta(name=name, namespace="default", uid="u1"),
        spec=V1ServiceSpec(selector={"app": name}, cluster_ip="10.0.0.1",
                           ports=[V1ServicePort(port=80, target_port=target_port)]))

def _pod(app, container_port=8080):
    return V1Pod(
        metadata=V1ObjectMeta(name="p", namespace="default", uid="u2",
                              labels={"app": app}),
        spec=V1PodSpec(containers=[V1Container(name="c", image="i",
                       ports=[V1ContainerPort(container_port=container_port)])]),
        status=V1PodStatus(container_statuses=[]))

def _core(svc, pods=None, ep=None):
    c = MagicMock()
    c.list_service_for_all_namespaces.return_value.items = [svc]
    c.list_namespaced_pod.return_value.items = pods or []
    c.read_namespaced_endpoints.return_value = ep or V1Endpoints(subsets=[])
    c.list_namespaced_event.return_value.items = []
    return c

def test_selector_no_pods_emits_high():
    fs = run(ServiceAnalyzer(core_v1=_core(_svc("x")), apps_v1=MagicMock()).analyze())
    assert fs[0].category == "selector-no-pods" and fs[0].severity == "high"

def test_port_mismatch_when_target_port_absent():
    ep = V1Endpoints(subsets=[V1EndpointSubset(
        addresses=[V1EndpointAddress(ip="1.2.3.4")], not_ready_addresses=[])])
    fs = run(ServiceAnalyzer(
        core_v1=_core(_svc("mm", target_port=9999), [_pod("mm", 8080)], ep),
        apps_v1=MagicMock()).analyze())
    assert any(f.category == "port-mismatch" for f in fs)

def test_endpoints_not_ready_high():
    ep = V1Endpoints(subsets=[V1EndpointSubset(
        addresses=[], not_ready_addresses=[V1EndpointAddress(ip="1.2.3.4")])])
    fs = run(ServiceAnalyzer(
        core_v1=_core(_svc("nr"), [_pod("nr")], ep),
        apps_v1=MagicMock()).analyze())
    assert any(f.category == "endpoints-not-ready" and f.severity == "high" for f in fs)
```

```python
# tests/analyzers/test_ingress_analyzer.py
import asyncio
from unittest.mock import MagicMock
from kubernetes.client import (
    V1Ingress, V1IngressSpec, V1IngressRule, V1HTTPIngressRuleValue,
    V1HTTPIngressPath, V1IngressBackend, V1IngressServiceBackend,
    V1ServiceBackendPort, V1ObjectMeta, V1IngressTLS,
)
from kubernetes.client.exceptions import ApiException
from src.analyzers.ingress_analyzer import IngressAnalyzer

run = lambda coro: asyncio.get_event_loop().run_until_complete(coro)

def _ing(name, host="ex.com", svc="web", tls_secret=None, annotations=None, ic="nginx"):
    backend = V1IngressBackend(service=V1IngressServiceBackend(
        name=svc, port=V1ServiceBackendPort(number=80)))
    return V1Ingress(
        metadata=V1ObjectMeta(name=name, namespace="default", uid="u1",
                              annotations=annotations or {}),
        spec=V1IngressSpec(ingress_class_name=ic,
            rules=[V1IngressRule(host=host, http=V1HTTPIngressRuleValue(paths=[
                V1HTTPIngressPath(path="/", path_type="Prefix", backend=backend)]))],
            tls=[V1IngressTLS(secret_name=tls_secret, hosts=[host])] if tls_secret else []))

def _ia(ingresses, svc_exc=None, secret_exc=None, controller="nginx"):
    c, n = MagicMock(), MagicMock()
    n.list_ingress_for_all_namespaces.return_value.items = ingresses
    c.list_namespaced_event.return_value.items = []
    c.read_namespaced_service.side_effect = svc_exc
    c.read_namespaced_secret.side_effect = secret_exc
    if not secret_exc:
        c.read_namespaced_secret.return_value = MagicMock(data={})
        c.read_namespaced_secret.side_effect = None
    return IngressAnalyzer(core_v1=c, apps_v1=MagicMock(), networking_v1=n,
                           installed_controller=controller)

def test_missing_backend_service_high():
    fs = run(_ia([_ing("x")], svc_exc=ApiException(status=404)).analyze())
    assert any(f.category == "missing-backend" and f.severity == "high" for f in fs)

def test_tls_secret_missing_critical():
    fs = run(_ia([_ing("x", tls_secret="gone")],
                 secret_exc=ApiException(status=404)).analyze())
    assert any(f.category == "tls-secret-missing" and f.severity == "critical" for f in fs)

def test_host_conflict_across_two_ingresses():
    fs = run(_ia([_ing("i1", host="shared.com"), _ing("i2", host="shared.com")]).analyze())
    assert any(f.category == "host-conflict" for f in fs)

def test_nginx_annotation_on_traefik_medium():
    ann = {"nginx.ingress.kubernetes.io/rewrite-target": "/"}
    fs = run(_ia([_ing("x", annotations=ann)], controller="traefik").analyze())
    assert any(f.category == "unsupported-annotation" and f.severity == "medium" for f in fs)
```

## 4. Implementation Notes

- Wrap all `kubernetes.client` calls in `asyncio.to_thread()` to avoid blocking the event loop on large clusters.
- `IngressAnalyzer.__init__` accepts `networking_v1` as an injectable dependency so unit tests mock it without patching the module.
- `_cert_days_remaining` requires `cryptography`; when absent returns `None` and logs one `WARNING` at startup.
- `host_map` is local to a single `analyze()` call; repeated runs re-emit host-conflict findings, collapsed by the SQLite deduplication layer (Section 21).
- `ServiceAnalyzer` skips services with empty `spec.selector` (ExternalName or manually managed Endpoints).
- `fingerprint()` excludes mutable fields (events, log tail) so the same broken resource yields the same key across poll cycles.
