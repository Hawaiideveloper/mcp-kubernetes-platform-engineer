from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from kubernetes.client import (
    V1Container,
    V1ContainerPort,
    V1EndpointAddress,
    V1EndpointSubset,
    V1Endpoints,
    V1ObjectMeta,
    V1Pod,
    V1PodSpec,
    V1PodStatus,
    V1Service,
    V1ServicePort,
    V1ServiceSpec,
)

from src.analyzers.service_analyzer import ServiceAnalyzer


def _svc(name, target_port=8080):
    return V1Service(
        metadata=V1ObjectMeta(name=name, namespace="default", uid="u1"),
        spec=V1ServiceSpec(
            selector={"app": name},
            cluster_ip="10.0.0.1",
            ports=[V1ServicePort(port=80, target_port=target_port)],
        ),
    )


def _pod(app, container_port=8080):
    return V1Pod(
        metadata=V1ObjectMeta(name="p", namespace="default", uid="u2", labels={"app": app}),
        spec=V1PodSpec(
            containers=[V1Container(name="c", image="i",
                        ports=[V1ContainerPort(container_port=container_port)])]
        ),
        status=V1PodStatus(container_statuses=[]),
    )


def _core(svc, pods=None, ep=None):
    c = MagicMock()
    c.list_service_for_all_namespaces.return_value.items = [svc]
    c.list_namespaced_pod.return_value.items = pods or []
    c.read_namespaced_endpoints.return_value = ep or V1Endpoints(subsets=[])
    c.list_namespaced_event.return_value.items = []
    return c


def run(coro):
    return asyncio.run(coro)


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


def test_empty_selector_skipped():
    svc = V1Service(
        metadata=V1ObjectMeta(name="ext", namespace="default", uid="u3"),
        spec=V1ServiceSpec(selector={}, cluster_ip="10.0.0.2", ports=[]),
    )
    c = MagicMock()
    c.list_service_for_all_namespaces.return_value.items = [svc]
    fs = run(ServiceAnalyzer(core_v1=c, apps_v1=MagicMock()).analyze())
    assert fs == []


def test_kubernetes_client_called_for_endpoints():
    ep = V1Endpoints(subsets=[V1EndpointSubset(
        addresses=[V1EndpointAddress(ip="5.6.7.8")], not_ready_addresses=[])])
    core = _core(_svc("runtime-check", target_port=8080), [_pod("runtime-check")], ep)
    run(ServiceAnalyzer(core_v1=core, apps_v1=MagicMock()).analyze())
    core.read_namespaced_endpoints.assert_called_once_with("runtime-check", "default")
