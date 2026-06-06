from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from kubernetes.client import AppsV1Api, AutoscalingV2Api, CoreV1Api
from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)

_CAP_MINUTES = 30
_STALE_HOURS = 24


class HPAAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "hpa"

    def __init__(
        self,
        core_v1: CoreV1Api,
        apps_v1: AppsV1Api,
        autoscaling_v2: AutoscalingV2Api,
        cap_threshold_minutes: int = _CAP_MINUTES,
        stale_scale_hours: int = _STALE_HOURS,
    ) -> None:
        super().__init__(core_v1=core_v1, apps_v1=apps_v1)
        self.autoscaling_v2 = autoscaling_v2
        self.cap_threshold_minutes = cap_threshold_minutes
        self.stale_scale_hours = stale_scale_hours

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        if namespace:
            result = await asyncio.to_thread(
                self.autoscaling_v2.list_namespaced_horizontal_pod_autoscaler, namespace
            )
        else:
            result = await asyncio.to_thread(
                self.autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces
            )
        hpas = result.items
        findings: List[Finding] = []
        for hpa in hpas:
            findings.extend(await self._evaluate_hpa(hpa))
        return findings

    async def _evaluate_hpa(self, hpa) -> List[Finding]:
        findings: List[Finding] = []
        ns = hpa.metadata.namespace or "default"
        name = hpa.metadata.name or ""
        uid = hpa.metadata.uid or ""
        ref = ResourceRef(
            kind="HorizontalPodAutoscaler", namespace=ns, name=name, uid=uid
        )

        spec = hpa.spec
        status = hpa.status
        max_r = spec.max_replicas if spec else 0
        min_r = spec.min_replicas if spec and spec.min_replicas else 1
        current = status.current_replicas if status and status.current_replicas else 0
        last_scale = status.last_scale_time if status else None
        conditions = status.conditions if status else []

        target_name = (
            spec.scale_target_ref.name
            if spec and spec.scale_target_ref
            else ""
        )
        try:
            await asyncio.to_thread(
                self.apps_v1.read_namespaced_deployment, target_name, ns
            )
        except ApiException as exc:
            if exc.status == 404:
                findings.append(
                    Finding(
                        resource=ref,
                        severity="high",  # type: ignore[arg-type]
                        category="target_missing",
                        evidence=Evidence(
                            (), "",
                            json.dumps({
                                "detail": f"Deployment {target_name} not found"
                            }),
                        ),
                        suggested_fix_class="HPAOrphanRemediator",
                        root_cause_hypothesis=(
                            f"HPA {name} target Deployment {target_name} missing"
                        ),
                    )
                )
                return findings

        for cond in conditions or []:
            ctype = getattr(cond, "type", "")
            cstatus = getattr(cond, "status", "")
            reason = getattr(cond, "reason", "") or ""
            if ctype == "ScalingActive" and (
                cstatus == "False" or reason.startswith("FailedGet")
            ):
                findings.append(
                    Finding(
                        resource=ref,
                        severity="high",  # type: ignore[arg-type]
                        category="no_metrics",
                        evidence=Evidence(
                            (), "",
                            json.dumps({"detail": reason or "ScalingActive=False"}),
                        ),
                        suggested_fix_class="HPAMetricsRemediator",
                        root_cause_hypothesis=f"HPA {name} cannot get metrics: {reason}",
                    )
                )

        if current == max_r and max_r > 0:
            now = datetime.now(timezone.utc)
            capped_long_enough = True
            if last_scale is not None:
                ls = last_scale
                if ls.tzinfo is None:
                    ls = ls.replace(tzinfo=timezone.utc)
                capped_long_enough = (now - ls) >= timedelta(
                    minutes=self.cap_threshold_minutes
                )
            if capped_long_enough:
                findings.append(
                    Finding(
                        resource=ref,
                        severity="high",  # type: ignore[arg-type]
                        category="capped_at_max",
                        evidence=Evidence(
                            (), "",
                            json.dumps({
                                "detail": f"current={current} == max={max_r}"
                            }),
                        ),
                        suggested_fix_class="HPACeilingRemediator",
                        root_cause_hypothesis=(
                            f"HPA {name} capped at maxReplicas={max_r}"
                        ),
                    )
                )

        if min_r == max_r:
            logger.warning(
                "HPA %s/%s: minReplicas==maxReplicas, skipping never_scaling", ns, name
            )
        elif current == min_r and not any(
            f.category == "no_metrics" for f in findings
        ):
            now = datetime.now(timezone.utc)
            stale = True
            if last_scale is not None:
                ls = last_scale
                if ls.tzinfo is None:
                    ls = ls.replace(tzinfo=timezone.utc)
                stale = (now - ls) >= timedelta(hours=self.stale_scale_hours)
            if stale:
                findings.append(
                    Finding(
                        resource=ref,
                        severity="medium",  # type: ignore[arg-type]
                        category="never_scaling",
                        evidence=Evidence(
                            (), "",
                            json.dumps({
                                "detail": f"current={current} == min={min_r}, stale"
                            }),
                        ),
                        suggested_fix_class="HPAThresholdRemediator",
                        root_cause_hypothesis=(
                            f"HPA {name} never scaled up (stuck at min={min_r})"
                        ),
                    )
                )

        return findings
