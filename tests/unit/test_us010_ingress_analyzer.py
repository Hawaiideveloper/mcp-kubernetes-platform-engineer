from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from kubernetes.client import (
    V1HTTPIngressPath,
    V1HTTPIngressRuleValue,
    V1Ingress,
    V1IngressBackend,
    V1IngressRule,
    V1IngressServiceBackend,
    V1IngressSpec,
    V1IngressTLS,
    V1ObjectMeta,
    V1ServiceBackendPort,
)
from kubernetes.client.exceptions import ApiException

from src.analyzers.ingress_analyzer import IngressAnalyzer


def _ing(name, host="ex.com", svc="web", tls_secret=None, annotations=None, ic="nginx"):
    backend = V1IngressBackend(service=V1IngressServiceBackend(
        name=svc, port=V1ServiceBackendPort(number=80)))
    return V1Ingress(
        metadata=V1ObjectMeta(name=name, namespace="default", uid="u1",
                              annotations=annotations or {}),
        spec=V1IngressSpec(
            ingress_class_name=ic,
            rules=[V1IngressRule(host=host, http=V1HTTPIngressRuleValue(paths=[
                V1HTTPIngressPath(path="/", path_type="Prefix", backend=backend)]))],
            tls=[V1IngressTLS(secret_name=tls_secret, hosts=[host])] if tls_secret else []))


def _ia(ingresses, svc_exc=None, secret_exc=None, controller="nginx"):
    c, n = MagicMock(), MagicMock()
    n.list_ingress_for_all_namespaces.return_value.items = ingresses
    c.list_namespaced_event.return_value.items = []
    if svc_exc:
        c.read_namespaced_service.side_effect = svc_exc
    else:
        c.read_namespaced_service.return_value = MagicMock()
        c.read_namespaced_service.side_effect = None
    if secret_exc:
        c.read_namespaced_secret.side_effect = secret_exc
    else:
        c.read_namespaced_secret.return_value = MagicMock(data={})
        c.read_namespaced_secret.side_effect = None
    return IngressAnalyzer(core_v1=c, apps_v1=MagicMock(), networking_v1=n,
                           installed_controller=controller)


def run(coro):
    return asyncio.run(coro)


def test_missing_backend_service_high():
    fs = run(_ia([_ing("x")], svc_exc=ApiException(status=404)).analyze())
    assert any(f.category == "missing-backend" and f.severity == "high" for f in fs)


def test_tls_secret_missing_critical():
    fs = run(_ia([_ing("x", tls_secret="gone")], secret_exc=ApiException(status=404)).analyze())
    assert any(f.category == "tls-secret-missing" and f.severity == "critical" for f in fs)


def test_host_conflict_across_two_ingresses():
    fs = run(_ia([_ing("i1", host="shared.com"), _ing("i2", host="shared.com")]).analyze())
    assert any(f.category == "host-conflict" for f in fs)


def test_nginx_annotation_on_traefik_medium():
    ann = {"nginx.ingress.kubernetes.io/rewrite-target": "/"}
    fs = run(_ia([_ing("x", annotations=ann)], controller="traefik").analyze())
    assert any(f.category == "unsupported-annotation" and f.severity == "medium" for f in fs)


def test_clean_ingress_no_findings():
    fs = run(_ia([_ing("ok")]).analyze())
    assert fs == []


def test_kubernetes_networking_client_called():
    ia = _ia([_ing("runtime")])
    run(ia.analyze())
    ia.networking_v1.list_ingress_for_all_namespaces.assert_called_once()
