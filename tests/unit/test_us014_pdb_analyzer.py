from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from kubernetes.client import (
    V1LabelSelector,
    V1ObjectMeta,
    V1PodDisruptionBudget,
    V1PodDisruptionBudgetSpec,
    V1PodDisruptionBudgetStatus,
)

from src.analyzers.pdb_analyzer import PDBAnalyzer


def run(coro):
    return asyncio.run(coro)


def _pdb(name, disruptions_allowed=1, match_labels=None, ns="default"):
    return V1PodDisruptionBudget(
        metadata=V1ObjectMeta(name=name, namespace=ns, uid="d1"),
        spec=V1PodDisruptionBudgetSpec(
            selector=V1LabelSelector(match_labels=match_labels or {"app": name})
        ),
        status=V1PodDisruptionBudgetStatus(
            disruptions_allowed=disruptions_allowed,
            current_healthy=1,
            desired_healthy=1,
            expected_pods=1,
        ),
    )


def _mkanalyzer(pdbs, pods=None):
    policy, core, apps = MagicMock(), MagicMock(), MagicMock()
    policy.list_pod_disruption_budget_for_all_namespaces.return_value.items = pdbs
    core.list_namespaced_pod.return_value.items = (
        pods if pods is not None else [MagicMock()]
    )
    return PDBAnalyzer(core_v1=core, apps_v1=apps, policy_v1=policy)


def test_eviction_blocked():
    findings = run(_mkanalyzer([_pdb("tight", disruptions_allowed=0)]).analyze())
    assert any(
        f.category == "eviction_blocked" and f.severity == "high" for f in findings
    )


def test_selector_mismatch():
    a = _mkanalyzer([_pdb("ghost", match_labels={"app": "nonexistent"})])
    a.core_v1.list_namespaced_pod.return_value.items = []
    findings = run(a.analyze())
    assert any(f.category == "selector_mismatch" for f in findings)


def test_healthy_pdb_no_blocking():
    findings = run(_mkanalyzer([_pdb("ok", disruptions_allowed=2)]).analyze())
    assert not any(f.category == "eviction_blocked" for f in findings)
