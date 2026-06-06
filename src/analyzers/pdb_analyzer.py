from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

from kubernetes.client import AppsV1Api, CoreV1Api, PolicyV1Api
from kubernetes.client.exceptions import ApiException

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)


class PDBAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "pdb"

    def __init__(
        self, core_v1: CoreV1Api, apps_v1: AppsV1Api, policy_v1: PolicyV1Api
    ) -> None:
        super().__init__(core_v1=core_v1, apps_v1=apps_v1)
        self.policy_v1 = policy_v1

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        if namespace:
            result = await asyncio.to_thread(
                self.policy_v1.list_namespaced_pod_disruption_budget, namespace
            )
        else:
            result = await asyncio.to_thread(
                self.policy_v1.list_pod_disruption_budget_for_all_namespaces
            )
        pdbs = result.items
        findings: List[Finding] = []
        for pdb in pdbs:
            findings.extend(await self._evaluate_pdb(pdb))
        return findings

    async def _evaluate_pdb(self, pdb) -> List[Finding]:
        findings: List[Finding] = []
        ns = pdb.metadata.namespace or "default"
        name = pdb.metadata.name or ""
        uid = pdb.metadata.uid or ""
        ref = ResourceRef(kind="PodDisruptionBudget", namespace=ns, name=name, uid=uid)

        if pdb.spec and pdb.spec.selector:
            sel = pdb.spec.selector
            if sel.match_expressions:
                logger.warning(
                    "PDB %s/%s uses matchExpressions — skipped (deferred)", ns, name
                )
                return []
            ml = sel.match_labels or {}
            label_selector = ",".join(f"{k}={v}" for k, v in ml.items())
            pods_result = await asyncio.to_thread(
                self.core_v1.list_namespaced_pod, ns,
                label_selector=label_selector,
            )
            matched_pods = pods_result.items
        else:
            matched_pods = []

        if not matched_pods:
            findings.append(
                Finding(
                    resource=ref,
                    severity="medium",  # type: ignore[arg-type]
                    category="selector_mismatch",
                    evidence=Evidence(
                        (), "", json.dumps({"detail": "selector matches no pods"})
                    ),
                    suggested_fix_class="PDBSelectorRemediator",
                    root_cause_hypothesis=f"PDB {name} selector matches no live pods",
                )
            )
            return findings

        if pdb.status and pdb.status.disruptions_allowed == 0:
            findings.append(
                Finding(
                    resource=ref,
                    severity="high",  # type: ignore[arg-type]
                    category="eviction_blocked",
                    evidence=Evidence(
                        (), "",
                        json.dumps({
                            "detail": "disruptions_allowed=0",
                            "pods": len(matched_pods),
                        }),
                    ),
                    suggested_fix_class="PDBEvictionRemediator",
                    root_cause_hypothesis=(
                        f"PDB {name} blocks all evictions (disruptions_allowed=0)"
                    ),
                )
            )

        owner_missing = True
        for pod in matched_pods:
            if not (pod.metadata and pod.metadata.owner_references):
                continue
            for owner_ref in pod.metadata.owner_references:
                kind = owner_ref.kind or ""
                oname = owner_ref.name or ""
                try:
                    if kind == "ReplicaSet":
                        rs = await asyncio.to_thread(
                            self.apps_v1.read_namespaced_replica_set, oname, ns
                        )
                        if rs.metadata.owner_references:
                            for rs_owner in rs.metadata.owner_references:
                                if rs_owner.kind == "Deployment":
                                    await asyncio.to_thread(
                                        self.apps_v1.read_namespaced_deployment,
                                        rs_owner.name, ns,
                                    )
                                    owner_missing = False
                    elif kind == "StatefulSet":
                        await asyncio.to_thread(
                            self.apps_v1.read_namespaced_stateful_set, oname, ns
                        )
                        owner_missing = False
                    elif kind == "Deployment":
                        await asyncio.to_thread(
                            self.apps_v1.read_namespaced_deployment, oname, ns
                        )
                        owner_missing = False
                except ApiException as exc:
                    if exc.status == 404:
                        continue
                    raise

        if owner_missing:
            findings.append(
                Finding(
                    resource=ResourceRef(
                        kind="PodDisruptionBudget", namespace=ns, name=name, uid=uid
                    ),
                    severity="low",  # type: ignore[arg-type]
                    category="no_owner_workload",
                    evidence=Evidence(
                        (), "", json.dumps({"detail": "owner workload not found"})
                    ),
                    suggested_fix_class="PDBOrphanRemediator",
                    root_cause_hypothesis=(
                        f"PDB {name} matched pods have no live owner workload"
                    ),
                )
            )

        return findings
