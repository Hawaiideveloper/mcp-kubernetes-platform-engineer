from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes.client import AppsV1Api, CoreV1Api
from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)

_PRESSURE = frozenset({"MemoryPressure", "DiskPressure", "PIDPressure"})
_STALE_SEC = 120
_MAX_TAINTS = 5
_SKEW_ALLOWED = 1


class NodeAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "node"

    def __init__(
        self,
        core_v1: CoreV1Api,
        apps_v1: AppsV1Api,
        log_tail_lines: int = 100,
        control_plane_minor: Optional[int] = None,
    ) -> None:
        super().__init__(core_v1, apps_v1, log_tail_lines)
        self._cp_minor = control_plane_minor

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        try:
            nodes = self.core_v1.list_node().items
        except ApiException as exc:
            logger.error("list_node: %s", exc)
            return []
        out: List[Finding] = []
        for n in nodes:
            out.extend(self._evaluate_node(n))
        return out

    def _evaluate_node(self, node) -> List[Finding]:  # type: ignore[no-untyped-def]
        name = node.metadata.name
        uid = node.metadata.uid or ""
        ref = ResourceRef("Node", "", name, uid)
        conds = node.status.conditions or []
        taints = node.spec.taints or []
        snap = json.dumps({
            "conditions": [{"type": c.type, "status": c.status} for c in conds],
            "taints": len(taints),
        })
        out: List[Finding] = []

        for c in conds:
            if c.type == "Ready" and c.status != "True":
                out.append(Finding(
                    ref, "critical", "node-not-ready",
                    Evidence((), "", snap),
                    "NodeRemediator",
                    f"{name} NotReady",
                ))
            if c.type in _PRESSURE and c.status == "True":
                out.append(Finding(
                    ref, "high", f"node-{c.type.lower()}",
                    Evidence((), "", snap),
                    "NodePressureRemediator",
                    f"{name} {c.type}",
                ))
            ts = c.last_heartbeat_time or c.last_transition_time
            if ts is not None:
                delta = datetime.now(timezone.utc) - (
                    ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
                )
                if delta.total_seconds() > _STALE_SEC:
                    out.append(Finding(
                        ref, "high", "node-kubelet-stale",
                        Evidence((), "", snap),
                        "KubeletRestartRemediator",
                        f"{name} kubelet silent >{_STALE_SEC}s",
                    ))

        if len(taints) > _MAX_TAINTS:
            out.append(Finding(
                ref, "medium", "node-high-taint-count",
                Evidence((), "", snap),
                "TaintAuditRemediator",
                f"{name} has {len(taints)} taints",
            ))

        if self._cp_minor is not None:
            raw = getattr(node.status.node_info, "kubelet_version", "") or ""
            parts = raw.lstrip("v").split(".")
            if len(parts) >= 2 and parts[1].isdigit():
                skew = self._cp_minor - int(parts[1])
                if skew > _SKEW_ALLOWED:
                    out.append(Finding(
                        ref, "medium", "node-version-skew",
                        Evidence((), "", snap),
                        "NodeUpgradeRemediator",
                        f"{name} {raw} {skew} minor(s) behind CP",
                    ))

        return out
