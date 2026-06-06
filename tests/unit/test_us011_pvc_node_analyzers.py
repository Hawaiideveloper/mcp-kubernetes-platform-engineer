from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import Optional
from unittest.mock import MagicMock

import pytest

SRC_PVC = os.path.join(
    os.path.dirname(__file__), "..", "..", "src", "analyzers", "pvc_analyzer.py"
)
SRC_NODE = os.path.join(
    os.path.dirname(__file__), "..", "..", "src", "analyzers", "node_analyzer.py"
)


@pytest.mark.skipif(not os.path.exists(SRC_PVC), reason="pvc_analyzer.py not found")
class TestPVCAnalyzer:
    @staticmethod
    def _pvc(name: str, phase: str, sc: str = "sc", modes: Optional[list] = None):
        p = MagicMock()
        p.metadata.namespace = "ns"
        p.metadata.name = name
        p.metadata.uid = "u"
        p.status.phase = phase
        p.spec.storage_class_name = sc
        p.status.capacity = {}
        p.spec.access_modes = modes or ["ReadWriteOnce"]
        return p

    @staticmethod
    def _make_analyzer(pvcs, scs=None, pods=None):
        from src.analyzers.pvc_analyzer import PVCAnalyzer
        c = MagicMock()
        c.list_persistent_volume_claim_for_all_namespaces.return_value.items = pvcs
        c.list_namespaced_event.return_value.items = []
        c.list_storage_class.return_value.items = scs or []
        c.list_pod_for_all_namespaces.return_value.items = pods or []
        return PVCAnalyzer(core_v1=c, apps_v1=MagicMock())

    def test_pending_missing_sc(self):
        analyzer = self._make_analyzer([self._pvc("p", "Pending", sc="gone")])
        findings = asyncio.run(analyzer.analyze())
        cats = {f.category for f in findings}
        assert "pvc-pending-no-sc" in cats

    def test_pending_unknown(self):
        # Empty sc triggers pvc-pending-unknown (not in any SC map)
        analyzer = self._make_analyzer([self._pvc("p", "Pending", sc="")])
        findings = asyncio.run(analyzer.analyze())
        cats = {f.category for f in findings}
        assert "pvc-pending-unknown" in cats

    def test_mount_failed(self):
        pod = MagicMock()
        pod.metadata.namespace = "ns"
        pod.spec.node_name = "n1"
        v = MagicMock()
        v.persistent_volume_claim.claim_name = "p"
        pod.spec.volumes = [v]
        evt = MagicMock()
        evt.reason = "FailedMount"
        evt.message = "err"
        evt.last_timestamp = datetime.now(timezone.utc)
        a = self._make_analyzer([self._pvc("p", "Bound")], pods=[pod])
        a.core_v1.list_namespaced_event.return_value.items = [evt]
        findings = asyncio.run(a.analyze())
        cats = {f.category for f in findings}
        assert "pvc-mount-failed" in cats

    def test_rwo_multi_node(self):
        def _pod(node_name: str):
            p = MagicMock()
            p.metadata.namespace = "ns"
            p.spec.node_name = node_name
            v = MagicMock()
            v.persistent_volume_claim.claim_name = "p"
            p.spec.volumes = [v]
            return p

        a = self._make_analyzer(
            [self._pvc("p", "Bound")],
            pods=[_pod("a"), _pod("b")],
        )
        findings = asyncio.run(a.analyze())
        cats = {f.category for f in findings}
        assert "pvc-rwo-multi-node" in cats

    def test_nfs_advisory(self):
        sc = MagicMock()
        sc.metadata.name = "nfs-sc"
        sc.provisioner = "nfs.csi.k8s.io"
        a = self._make_analyzer(
            [self._pvc("p", "Bound", sc="nfs-sc")],
            scs=[sc],
        )
        findings = asyncio.run(a.analyze())
        cats = {f.category for f in findings}
        assert "pvc-nfs-common-advisory" in cats

    def test_runtime_call_made(self):
        """Runtime validator: kubernetes client call exercised via mock."""
        a = self._make_analyzer([])
        asyncio.run(a.analyze())
        a.core_v1.list_persistent_volume_claim_for_all_namespaces.assert_called_once()


@pytest.mark.skipif(not os.path.exists(SRC_NODE), reason="node_analyzer.py not found")
class TestNodeAnalyzer:
    @staticmethod
    def _cond(t: str, s: str, hb=None):
        c = MagicMock()
        c.type = t
        c.status = s
        c.last_heartbeat_time = hb
        c.last_transition_time = hb
        return c

    @staticmethod
    def _make_analyzer(conds, taints: int = 0, ver: str = "v1.28.4", cp: Optional[int] = None):
        from src.analyzers.node_analyzer import NodeAnalyzer
        n = MagicMock()
        n.metadata.name = "nx"
        n.metadata.uid = "u"
        n.status.conditions = conds
        n.spec.taints = [MagicMock()] * taints
        n.status.node_info.kubelet_version = ver
        c = MagicMock()
        c.list_node.return_value.items = [n]
        return NodeAnalyzer(core_v1=c, apps_v1=MagicMock(), control_plane_minor=cp)

    def test_not_ready(self):
        a = self._make_analyzer([self._cond("Ready", "Unknown")])
        findings = asyncio.run(a.analyze())
        cats = {(f.category, f.severity) for f in findings}
        assert ("node-not-ready", "critical") in cats

    def test_pressures(self):
        a = self._make_analyzer([
            self._cond("Ready", "True"),
            self._cond("MemoryPressure", "True"),
            self._cond("DiskPressure", "True"),
            self._cond("PIDPressure", "True"),
        ])
        findings = asyncio.run(a.analyze())
        cats = {f.category for f in findings}
        assert {"node-memorypressure", "node-diskpressure", "node-pidpressure"}.issubset(cats)

    def test_kubelet_stale_and_skew_and_taints(self):
        stale = datetime.now(timezone.utc) - timedelta(minutes=5)
        a = self._make_analyzer(
            [self._cond("Ready", "True", hb=stale)],
            taints=6,
            ver="v1.26.0",
            cp=28,
        )
        findings = asyncio.run(a.analyze())
        cats = {f.category for f in findings}
        assert "node-kubelet-stale" in cats
        assert "node-high-taint-count" in cats
        assert "node-version-skew" in cats

    def test_healthy_zero_findings(self):
        a = self._make_analyzer(
            [
                self._cond("Ready", "True"),
                self._cond("DiskPressure", "False"),
                self._cond("MemoryPressure", "False"),
                self._cond("PIDPressure", "False"),
            ],
            cp=28,
        )
        findings = asyncio.run(a.analyze())
        assert findings == []

    def test_runtime_call_made(self):
        """Runtime validator: kubernetes client call exercised via mock."""
        a = self._make_analyzer([self._cond("Ready", "True")])
        asyncio.run(a.analyze())
        a.core_v1.list_node.assert_called_once()
