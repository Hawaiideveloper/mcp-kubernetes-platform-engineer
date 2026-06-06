from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, cast

from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef, Severity

logger = logging.getLogger(__name__)

_NFS_PROVISIONERS = frozenset({
    "nfs.csi.k8s.io",
    "cluster.local/nfs-provisioner",
    "nfs-subdir-external-provisioner",
})


class PVCAnalyzer(BaseAnalyzer):
    # daxxon-ai-gpu-01 note: NFS-backed PVCs require manual apt-get install -y nfs-common
    # on Ubuntu 24.04 nodes — the provisioner does not automate this step.
    ANALYZER_ID = "pvc"

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        pvcs = (
            self.core_v1.list_namespaced_persistent_volume_claim(namespace).items
            if namespace
            else self.core_v1.list_persistent_volume_claim_for_all_namespaces().items
        )
        scs = self._fetch_storage_classes()
        pods = (
            self.core_v1.list_namespaced_pod(namespace).items
            if namespace
            else self.core_v1.list_pod_for_all_namespaces().items
        )
        out: List[Finding] = []
        for pvc in pvcs:
            out.extend(self._evaluate_pvc(pvc, scs, pods))
        return out

    def _evaluate_pvc(self, pvc, scs, pods):  # type: ignore[no-untyped-def]
        ns = pvc.metadata.namespace
        name = pvc.metadata.name
        uid = pvc.metadata.uid or ""
        ref = ResourceRef("PersistentVolumeClaim", ns, name, uid)
        phase = (pvc.status.phase or "").strip()
        sc = pvc.spec.storage_class_name or ""
        evts = self._fetch_events(ns, name)
        msgs = tuple(f"{e.reason}: {e.message}" for e in evts if e.reason)
        snap = json.dumps({"phase": phase, "storageClass": sc})
        out: List[Finding] = []

        if phase == "Pending":
            if sc and sc not in scs:
                out.append(Finding(
                    ref, "high", "pvc-pending-no-sc",
                    Evidence(msgs, "", snap),
                    "StorageClassRemediator",
                    f"SC {sc!r} absent",
                ))
            elif any(
                "ProvisioningFailed" in m or "no persistent volumes" in m.lower()
                for m in msgs
            ):
                out.append(Finding(
                    ref, "high", "pvc-pending-no-pv",
                    Evidence(msgs, "", snap),
                    "PVProvisioningRemediator",
                    "No matching PV",
                ))
            else:
                out.append(Finding(
                    ref, "medium", "pvc-pending-unknown",
                    Evidence(msgs, "", snap),
                    "PVCPendingRemediator",
                    "PVC Pending; no event",
                ))

        if phase == "Bound":
            out.extend(self._check_mount_failed(ref, pods, msgs, snap))
            out.extend(self._check_capacity(ref, pvc, snap))
            out.extend(self._check_rwo_multi_node(ref, pvc, pods, msgs, snap))

        out.extend(self._check_nfs_advisory(ref, sc, scs, snap))
        return out

    def _check_mount_failed(self, ref: ResourceRef, pods, msgs, snap) -> List[Finding]:  # type: ignore[no-untyped-def]
        out: List[Finding] = []
        for pod in pods:
            if pod.metadata.namespace != ref.namespace:
                continue
            if not any(
                v.persistent_volume_claim
                and v.persistent_volume_claim.claim_name == ref.name
                for v in (pod.spec.volumes or [])
            ):
                continue
            bad = [
                e for e in self._fetch_events(pod.metadata.namespace, pod.metadata.name)
                if e.reason in ("FailedMount", "FailedAttach")
                and self._within_last_hour(e.last_timestamp)
            ]
            if bad:
                out.append(Finding(
                    ref, "high", "pvc-mount-failed",
                    Evidence(msgs, "", snap),
                    "PVCMountRemediator",
                    f"FailedMount on {pod.metadata.name}",
                ))
        return out

    def _check_capacity(self, ref: ResourceRef, pvc, snap: str) -> List[Finding]:  # type: ignore[no-untyped-def]
        try:
            used = self._fetch_volume_used_bytes(ref.namespace, ref.name)
            cap = self._parse_capacity(pvc.status.capacity or {})
            if cap and used is not None and used / cap > 0.85:
                sev: Severity = cast(Severity, "critical" if used / cap > 0.95 else "high")
                return [Finding(
                    ref, sev, "pvc-capacity-high",
                    Evidence((), "", snap),
                    "VolumeExpansionRemediator",
                    f"PVC at {used / cap:.0%} capacity",
                )]
        except Exception as exc:
            logger.debug("capacity skipped %s/%s: %s", ref.namespace, ref.name, exc)
        return []

    def _check_rwo_multi_node(self, ref: ResourceRef, pvc, pods, msgs, snap) -> List[Finding]:  # type: ignore[no-untyped-def]
        if "ReadWriteOnce" not in (pvc.spec.access_modes or []):
            return []
        nodes = {
            p.spec.node_name
            for p in pods
            if p.metadata.namespace == ref.namespace
            and any(
                v.persistent_volume_claim
                and v.persistent_volume_claim.claim_name == ref.name
                for v in (p.spec.volumes or [])
            )
            and p.spec.node_name
        }
        if len(nodes) > 1:
            return [Finding(
                ref, "high", "pvc-rwo-multi-node",
                Evidence(msgs, "", snap),
                "RWOConflictRemediator",
                f"RWO PVC on nodes: {sorted(nodes)}",
            )]
        return []

    def _check_nfs_advisory(self, ref: ResourceRef, sc: str, scs: dict, snap: str) -> List[Finding]:
        if (scs.get(sc) or {}).get("provisioner", "") in _NFS_PROVISIONERS:
            return [Finding(
                ref, "info", "pvc-nfs-common-advisory",
                Evidence((), "", snap),
                "NFSNodePrepRemediator",
                "NFS PVC — nodes need: apt-get install -y nfs-common",
            )]
        return []

    def _fetch_events(self, ns: str, name: str):  # type: ignore[no-untyped-def]
        try:
            return self.core_v1.list_namespaced_event(
                ns, field_selector=f"involvedObject.name={name}"
            ).items
        except ApiException:
            return []

    def _fetch_storage_classes(self) -> dict:
        try:
            return {
                s.metadata.name: {"provisioner": s.provisioner}
                for s in self.core_v1.list_storage_class().items
            }
        except ApiException:
            return {}

    @staticmethod
    def _within_last_hour(ts) -> bool:  # type: ignore[no-untyped-def]
        if ts is None:
            return False
        delta = datetime.now(timezone.utc) - (
            ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        )
        return delta.total_seconds() < 3600

    @staticmethod
    def _parse_capacity(cap: dict) -> Optional[int]:
        raw = cap.get("storage", "")
        for s, m in [
            ("Gi", 1 << 30),
            ("Mi", 1 << 20),
            ("Ki", 1 << 10),
            ("G", 10**9),
            ("M", 10**6),
            ("K", 10**3),
        ]:
            if raw.endswith(s):
                return int(raw[: -len(s)]) * m
        return int(raw) if raw.isdigit() else None

    def _fetch_volume_used_bytes(self, ns: str, pvc_name: str) -> Optional[int]:
        raise NotImplementedError("plug in metrics-server client")
