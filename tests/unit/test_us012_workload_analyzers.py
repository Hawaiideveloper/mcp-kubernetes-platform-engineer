import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from kubernetes.client import (
    V1Deployment, V1DeploymentSpec, V1DeploymentStatus, V1ObjectMeta,
    V1DeploymentCondition, V1PodTemplateSpec, V1PodSpec, V1Container,
    V1ResourceRequirements, V1ReplicaSet, V1ReplicaSetSpec, V1ReplicaSetStatus,
    V1StatefulSet, V1Pod, V1PodStatus,
    V1PersistentVolumeClaim, V1PersistentVolumeClaimStatus,
    CoreV1Event,
)
from src.analyzers.deployment_analyzer import DeploymentAnalyzer
from src.analyzers.replicaset_analyzer import ReplicaSetAnalyzer
from src.analyzers.statefulset_analyzer import StatefulSetAnalyzer

_old = datetime.now(timezone.utc) - timedelta(minutes=10)


def _deploy(name, desired=3, available=1, conditions=None):
    return V1Deployment(
        metadata=V1ObjectMeta(name=name, namespace="default", uid="uid1"),
        spec=V1DeploymentSpec(
            replicas=desired,
            selector=MagicMock(),
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(),
                spec=V1PodSpec(containers=[
                    V1Container(name="app", image="app:v1",
                                resources=V1ResourceRequirements(requests={}))
                ]),
            ),
        ),
        status=V1DeploymentStatus(
            replicas=desired, available_replicas=available, ready_replicas=available,
            conditions=conditions or [],
        ),
    )


def _analyzer_deploy(deps, nodes=None):
    c = MagicMock()
    a = MagicMock()
    a.list_deployment_for_all_namespaces.return_value.items = deps
    c.list_node.return_value.items = nodes or []
    return DeploymentAnalyzer(core_v1=c, apps_v1=a)


def test_replica_mismatch_after_five_min():
    cond = V1DeploymentCondition(
        type="Available", status="False",
        last_transition_time=_old, reason="MinimumReplicasUnavailable", message=""
    )
    dep = _deploy("app", desired=3, available=1, conditions=[cond])
    fs = asyncio.run(_analyzer_deploy([dep]).analyze())
    assert any(f.category == "replica-mismatch" for f in fs)
    assert all(f.severity == "high" for f in fs if f.category == "replica-mismatch")


def test_replica_mismatch_suppressed_under_five_min():
    recent = datetime.now(timezone.utc) - timedelta(minutes=2)
    cond = V1DeploymentCondition(
        type="Available", status="False",
        last_transition_time=recent, reason="MinimumReplicasUnavailable", message=""
    )
    dep = _deploy("app", desired=3, available=1, conditions=[cond])
    fs = asyncio.run(_analyzer_deploy([dep]).analyze())
    assert not any(f.category == "replica-mismatch" for f in fs)


def test_rollout_stuck_progress_deadline():
    cond = V1DeploymentCondition(
        type="Progressing", status="False",
        reason="ProgressDeadlineExceeded",
        last_transition_time=_old, message="exceeded"
    )
    dep = _deploy("app", desired=3, available=3, conditions=[cond])
    fs = asyncio.run(_analyzer_deploy([dep]).analyze())
    assert any(f.category == "rollout-stuck" and f.severity == "critical" for f in fs)


def test_impossible_resource_request():
    node = MagicMock()
    node.status.capacity = {"cpu": "4", "memory": "8Gi"}
    dep = _deploy("bigapp")
    dep.spec.template.spec.containers[0].resources = V1ResourceRequirements(
        requests={"cpu": "100", "memory": "1Ti"}
    )
    a = MagicMock()
    a.list_deployment_for_all_namespaces.return_value.items = [dep]
    c = MagicMock()
    c.list_node.return_value.items = [node]
    analyzer = DeploymentAnalyzer(core_v1=c, apps_v1=a)
    fs = asyncio.run(analyzer.analyze())
    assert any(f.category == "impossible-resource-request" for f in fs)


def test_image_not_found_fires_when_probe_returns_false():
    dep = _deploy("app", desired=1, available=1)
    image_probe = MagicMock(return_value=False)
    a = MagicMock()
    a.list_deployment_for_all_namespaces.return_value.items = [dep]
    c = MagicMock()
    c.list_node.return_value.items = []
    analyzer = DeploymentAnalyzer(core_v1=c, apps_v1=a, image_probe_fn=image_probe)
    fs = asyncio.run(analyzer.analyze())
    assert any(f.category == "image-not-found" for f in fs)


def test_image_not_found_skipped_when_no_probe():
    dep = _deploy("app", desired=1, available=1)
    fs = asyncio.run(_analyzer_deploy([dep]).analyze())
    assert not any(f.category == "image-not-found" for f in fs)


def _make_rs(name, ns, owner_dep, spec_replicas, status_replicas, uid="ruid"):
    owner_ref = MagicMock()
    owner_ref.kind = "Deployment"
    owner_ref.name = owner_dep
    rs = V1ReplicaSet(
        metadata=V1ObjectMeta(
            name=name, namespace=ns, uid=uid,
            owner_references=[owner_ref]
        ),
        spec=V1ReplicaSetSpec(replicas=spec_replicas, selector=MagicMock(), template=MagicMock()),
        status=V1ReplicaSetStatus(replicas=status_replicas),
    )
    return rs


def test_dangling_replicaset():
    rs = _make_rs("app-abc", "default", "app", spec_replicas=0, status_replicas=0)
    a = MagicMock()
    a.list_replica_set_for_all_namespaces.return_value.items = [rs]
    analyzer = ReplicaSetAnalyzer(core_v1=MagicMock(), apps_v1=a)
    fs = asyncio.run(analyzer.analyze())
    assert any(f.category == "dangling-replicaset" for f in fs)


def test_multiple_active_replicasets():
    rs1 = _make_rs("app-abc", "default", "app", 2, 2, "uid1")
    rs2 = _make_rs("app-def", "default", "app", 1, 1, "uid2")
    a = MagicMock()
    a.list_replica_set_for_all_namespaces.return_value.items = [rs1, rs2]
    analyzer = ReplicaSetAnalyzer(core_v1=MagicMock(), apps_v1=a)
    fs = asyncio.run(analyzer.analyze())
    assert any(f.category == "rollout-in-progress" for f in fs)


def _sts_analyzer(sts_list, pods, pvcs, events):
    a = MagicMock()
    a.list_stateful_set_for_all_namespaces.return_value.items = sts_list
    c = MagicMock()
    c.list_namespaced_pod.return_value.items = pods
    c.list_namespaced_persistent_volume_claim.return_value.items = pvcs
    c.list_namespaced_event.return_value.items = events
    return StatefulSetAnalyzer(core_v1=c, apps_v1=a)


def test_pvc_binding_pending():
    sts = V1StatefulSet(
        metadata=V1ObjectMeta(name="db", namespace="default", uid="suid"),
        spec=MagicMock(), status=MagicMock()
    )
    pod = V1Pod(
        metadata=V1ObjectMeta(name="db-0", namespace="default", uid="puid"),
        status=V1PodStatus(phase="Pending")
    )
    ev = CoreV1Event(reason="FailedMount", message="Unable to attach volume", involved_object=MagicMock(), metadata=MagicMock())
    analyzer = _sts_analyzer([sts], [pod], [], [ev])
    fs = asyncio.run(analyzer.analyze())
    assert any(f.category == "pvc-binding-pending" for f in fs)


def test_ordinal_gap_detected():
    sts = V1StatefulSet(
        metadata=V1ObjectMeta(name="db", namespace="default", uid="suid"),
        spec=MagicMock(), status=MagicMock()
    )
    pods = [
        V1Pod(metadata=V1ObjectMeta(name="db-1", namespace="default", uid="p1"), status=V1PodStatus(phase="Running")),
        V1Pod(metadata=V1ObjectMeta(name="db-2", namespace="default", uid="p2"), status=V1PodStatus(phase="Running")),
    ]
    analyzer = _sts_analyzer([sts], pods, [], [])
    fs = asyncio.run(analyzer.analyze())
    ordinal_findings = [f for f in fs if f.category == "ordinal-gap"]
    assert ordinal_findings
    assert ordinal_findings[0].severity == "critical"


def test_pvc_template_failure_lost():
    sts = V1StatefulSet(
        metadata=V1ObjectMeta(name="db", namespace="default", uid="suid"),
        spec=MagicMock(), status=MagicMock()
    )
    pvc = V1PersistentVolumeClaim(
        metadata=V1ObjectMeta(name="data-db-0", namespace="default", uid="pvuid"),
        status=V1PersistentVolumeClaimStatus(phase="Lost")
    )
    analyzer = _sts_analyzer([sts], [], [pvc], [])
    fs = asyncio.run(analyzer.analyze())
    assert any(f.category == "pvc-template-failure" for f in fs)


def test_no_findings_healthy_deployment():
    cond = V1DeploymentCondition(
        type="Available", status="True",
        last_transition_time=_old, reason="MinimumReplicasAvailable", message=""
    )
    dep = _deploy("app", desired=3, available=3, conditions=[cond])
    fs = asyncio.run(_analyzer_deploy([dep]).analyze())
    assert not any(f.category in ("replica-mismatch", "rollout-stuck") for f in fs)
