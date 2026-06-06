from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from kubernetes.client import (
    V1ObjectMeta,
    V2CrossVersionObjectReference,
    V2HorizontalPodAutoscaler,
    V2HorizontalPodAutoscalerCondition,
    V2HorizontalPodAutoscalerSpec,
    V2HorizontalPodAutoscalerStatus,
)
from kubernetes.client.exceptions import ApiException

from src.analyzers.hpa_analyzer import HPAAnalyzer


def run(coro):
    return asyncio.run(coro)


_NOW = datetime.now(timezone.utc)


def _hpa(name, current, max_r, min_r=1, conditions=None, last_scale=None):
    return V2HorizontalPodAutoscaler(
        metadata=V1ObjectMeta(name=name, namespace="default", uid="h1"),
        spec=V2HorizontalPodAutoscalerSpec(
            max_replicas=max_r,
            min_replicas=min_r,
            scale_target_ref=V2CrossVersionObjectReference(
                api_version="apps/v1", kind="Deployment", name=name
            ),
        ),
        status=V2HorizontalPodAutoscalerStatus(
            current_replicas=current,
            desired_replicas=current,
            conditions=conditions or [],
            last_scale_time=last_scale,
        ),
    )


def _mkanalyzer(hpas, deployment_exists=True):
    auto, apps, core = MagicMock(), MagicMock(), MagicMock()
    auto.list_horizontal_pod_autoscaler_for_all_namespaces.return_value.items = hpas
    if not deployment_exists:
        apps.read_namespaced_deployment.side_effect = ApiException(status=404)
    return HPAAnalyzer(core_v1=core, apps_v1=apps, autoscaling_v2=auto)


def test_capped_at_max():
    findings = run(
        _mkanalyzer(
            [_hpa("w", 10, 10, last_scale=_NOW - timedelta(hours=2))]
        ).analyze()
    )
    assert any(f.category == "capped_at_max" and f.severity == "high" for f in findings)


def test_no_metrics():
    cond = V2HorizontalPodAutoscalerCondition(
        type="ScalingActive",
        status="False",
        reason="FailedGetResourceMetric",
        message="unable to get metrics",
    )
    findings = run(_mkanalyzer([_hpa("api", 1, 5, conditions=[cond])]).analyze())
    assert any(f.category == "no_metrics" for f in findings)


def test_target_missing():
    findings = run(
        _mkanalyzer([_hpa("gone", 1, 5)], deployment_exists=False).analyze()
    )
    assert any(f.category == "target_missing" for f in findings)


def test_healthy_hpa_no_findings():
    findings = run(
        _mkanalyzer(
            [_hpa("ok", 3, 10, last_scale=_NOW - timedelta(minutes=5))]
        ).analyze()
    )
    assert findings == []
