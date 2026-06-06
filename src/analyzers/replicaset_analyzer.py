from __future__ import annotations
import json
import logging
from collections import defaultdict
from typing import List, Optional

from kubernetes.client import V1ReplicaSet

from .base import BaseAnalyzer, Evidence, Finding, ResourceRef

logger = logging.getLogger(__name__)


class ReplicaSetAnalyzer(BaseAnalyzer):
    ANALYZER_ID = "replicaset"

    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]:
        rsets = (
            self.apps_v1.list_namespaced_replica_set(namespace).items
            if namespace
            else self.apps_v1.list_replica_set_for_all_namespaces().items
        )
        findings: List[Finding] = []

        by_owner: dict[str, list[V1ReplicaSet]] = defaultdict(list)
        for rs in rsets:
            for ref in rs.metadata.owner_references or []:
                if ref.kind == "Deployment":
                    by_owner[f"{rs.metadata.namespace}/{ref.name}"].append(rs)

        for owner_key, owned in by_owner.items():
            ns, dep_name = owner_key.split("/", 1)

            dangling = [
                rs for rs in owned
                if (rs.spec.replicas or 0) == 0 and (rs.status.replicas or 0) == 0
            ]
            for rs in dangling:
                ref = ResourceRef(
                    kind="ReplicaSet",
                    namespace=rs.metadata.namespace,
                    name=rs.metadata.name,
                    uid=rs.metadata.uid or "",
                )
                findings.append(Finding(
                    resource=ref,
                    severity="low",
                    category="dangling-replicaset",
                    evidence=Evidence(
                        events=(),
                        log_tail="",
                        status_snapshot=json.dumps({"owner_deployment": dep_name, "spec_replicas": rs.spec.replicas}),
                    ),
                    suggested_fix_class="DanglingRSRemediator",
                    root_cause_hypothesis=(
                        f"ReplicaSet {rs.metadata.name} owned by {dep_name} has replicas=0 and is safe to prune"
                    ),
                ))

            active = [rs for rs in owned if (rs.status.replicas or 0) > 0]
            if len(active) > 1:
                active_names = [rs.metadata.name for rs in active]
                resource_ref = ResourceRef(kind="Deployment", namespace=ns, name=dep_name, uid="")
                findings.append(Finding(
                    resource=resource_ref,
                    severity="medium",
                    category="rollout-in-progress",
                    evidence=Evidence(
                        events=(),
                        log_tail="",
                        status_snapshot=json.dumps({"active_replicasets": active_names}),
                    ),
                    suggested_fix_class="RolloutMonitorRemediator",
                    root_cause_hypothesis=(
                        f"Deployment {dep_name} has {len(active)} active ReplicaSets indicating a rollout is incomplete: {active_names}"
                    ),
                ))

        return findings
