from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from kubernetes.client import (
    V1LabelSelector,
    V1NetworkPolicy,
    V1NetworkPolicySpec,
    V1ObjectMeta,
)

from src.analyzers.network_policy_analyzer import NetworkPolicyAnalyzer


def run(coro):
    return asyncio.run(coro)


def _mkanalyzer(policies=None, pods=None, ns_labels=None, services=None):
    core, net = MagicMock(), MagicMock()
    core.list_namespaced_pod.return_value.items = pods or []
    core.list_namespaced_service.return_value.items = services or []
    core.read_namespace.return_value.metadata.labels = ns_labels or {}
    net.list_namespaced_network_policy.return_value.items = policies or []
    a = NetworkPolicyAnalyzer(core_v1=core, networking_v1=net, apps_v1=MagicMock())
    a._resolve_namespaces = lambda ns: ["default"]
    return a


def test_orphan_policy():
    p = V1NetworkPolicy(
        metadata=V1ObjectMeta(name="isolate-foo", namespace="default", uid="p1"),
        spec=V1NetworkPolicySpec(
            pod_selector=V1LabelSelector(match_labels={"app": "foo"}),
            policy_types=["Ingress"],
        ),
    )
    cats = [f.category for f in run(_mkanalyzer(policies=[p], pods=[]).analyze())]
    assert "orphan_policy" in cats


def test_no_default_deny_production():
    cats = [
        f.category
        for f in run(_mkanalyzer(ns_labels={"env": "production"}).analyze())
    ]
    assert "no_default_deny" in cats


def test_egress_dns_blocked():
    p = V1NetworkPolicy(
        metadata=V1ObjectMeta(name="deny-egress", namespace="default", uid="p2"),
        spec=V1NetworkPolicySpec(
            pod_selector=V1LabelSelector(match_labels={}),
            policy_types=["Egress"],
            egress=[],
        ),
    )
    cats = [f.category for f in run(_mkanalyzer(policies=[p]).analyze())]
    assert "egress_dns_blocked" in cats


def test_clean_namespace():
    assert run(_mkanalyzer().analyze()) == []


def test_no_orphan_for_empty_selector():
    p = V1NetworkPolicy(
        metadata=V1ObjectMeta(name="default-deny", namespace="default", uid="p3"),
        spec=V1NetworkPolicySpec(
            pod_selector=V1LabelSelector(match_labels={}),
            policy_types=["Ingress"],
        ),
    )
    cats = [f.category for f in run(_mkanalyzer(policies=[p], pods=[]).analyze())]
    assert "orphan_policy" not in cats
