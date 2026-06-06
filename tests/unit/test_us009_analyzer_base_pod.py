from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

from kubernetes.client import (
    V1ContainerState,
    V1ContainerStateTerminated,
    V1ContainerStateWaiting,
    V1ContainerStatus,
    V1ObjectMeta,
    V1Pod,
    V1PodStatus,
)

from src.analyzers.pod_analyzer import PodAnalyzer


def _pod(name, ns="default", uid="u1"):
    return V1Pod(
        metadata=V1ObjectMeta(name=name, namespace=ns, uid=uid),
        status=V1PodStatus(phase="Running", container_statuses=[]),
    )


def _analyzer(pods=None, events=None, log=""):
    c = MagicMock()
    c.list_pod_for_all_namespaces.return_value.items = pods or []
    c.list_namespaced_event.return_value.items = events or []
    c.read_namespaced_pod_log.return_value = log
    return PodAnalyzer(core_v1=c, apps_v1=MagicMock())


def run(coro):
    return asyncio.run(coro)


def test_image_pull_backoff():
    pod = _pod("bad")
    pod.status.container_statuses = [
        V1ContainerStatus(
            name="app", image="bad:v1", ready=False, restart_count=0, image_id="",
            state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="ImagePullBackOff")),
            last_state=V1ContainerState(),
        )
    ]
    fs = run(_analyzer(pods=[pod]).analyze())
    assert len(fs) == 1 and fs[0].category == "image-pull"
    assert fs[0].suggested_fix_class == "ImageTagRemediator"
    assert fs[0].severity == "high"


def test_crash_loop_critical_at_5():
    pod = _pod("crasher")
    pod.status.container_statuses = [
        V1ContainerStatus(
            name="app", image="app:v1", ready=False, restart_count=5, image_id="",
            state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="CrashLoopBackOff")),
            last_state=V1ContainerState(),
        )
    ]
    fs = run(_analyzer(pods=[pod], log="panic").analyze())
    assert fs[0].category == "crash-loop" and fs[0].severity == "critical"
    assert "panic" in fs[0].evidence.log_tail


def test_crash_loop_high_at_3():
    pod = _pod("crasher2")
    pod.status.container_statuses = [
        V1ContainerStatus(
            name="app", image="app:v1", ready=False, restart_count=3, image_id="",
            state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="CrashLoopBackOff")),
            last_state=V1ContainerState(),
        )
    ]
    fs = run(_analyzer(pods=[pod]).analyze())
    assert fs[0].severity == "high"


def test_crash_loop_medium_at_1():
    pod = _pod("crasher3")
    pod.status.container_statuses = [
        V1ContainerStatus(
            name="app", image="app:v1", ready=False, restart_count=1, image_id="",
            state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="CrashLoopBackOff")),
            last_state=V1ContainerState(),
        )
    ]
    fs = run(_analyzer(pods=[pod]).analyze())
    assert fs[0].severity == "medium"


def test_oom_killed_exit_137():
    pod = _pod("oom")
    pod.status.container_statuses = [
        V1ContainerStatus(
            name="app", image="app:v1", ready=False, restart_count=1, image_id="",
            state=V1ContainerState(),
            last_state=V1ContainerState(
                terminated=V1ContainerStateTerminated(reason="OOMKilled", exit_code=137)
            ),
        )
    ]
    fs = run(_analyzer(pods=[pod]).analyze())
    assert fs[0].category == "oom-killed"
    assert fs[0].suggested_fix_class == "MemoryLimitRemediator"


def test_finding_hashable_and_json():
    pod = _pod("img2")
    pod.status.container_statuses = [
        V1ContainerStatus(
            name="app", image="bad:v1", ready=False, restart_count=0, image_id="",
            state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="ImagePullBackOff")),
            last_state=V1ContainerState(),
        )
    ]
    fs = run(_analyzer(pods=[pod]).analyze())
    assert len({fs[0]}) == 1
    parsed = json.loads(fs[0].to_json())
    assert parsed["category"] == "image-pull"
    assert "fingerprint" in parsed
    assert isinstance(parsed["evidence"]["events"], list)


def test_dedup_across_runs():
    pod = _pod("img3")
    pod.status.container_statuses = [
        V1ContainerStatus(
            name="app", image="bad:v1", ready=False, restart_count=0, image_id="",
            state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="ImagePullBackOff")),
            last_state=V1ContainerState(),
        )
    ]
    a = _analyzer(pods=[pod])
    f1 = run(a.run_safe())[0]
    f2 = run(a.run_safe())[0]
    assert f1.fingerprint() == f2.fingerprint()


def test_no_findings_for_running_pod():
    pod = _pod("ok")
    pod.status.container_statuses = [
        V1ContainerStatus(
            name="app", image="app:v1", ready=True, restart_count=0, image_id="",
            state=V1ContainerState(),
            last_state=V1ContainerState(),
        )
    ]
    fs = run(_analyzer(pods=[pod]).analyze())
    assert fs == []


def test_err_image_pull_reason():
    pod = _pod("err-img")
    pod.status.container_statuses = [
        V1ContainerStatus(
            name="app", image="bad:v1", ready=False, restart_count=0, image_id="",
            state=V1ContainerState(waiting=V1ContainerStateWaiting(reason="ErrImagePull")),
            last_state=V1ContainerState(),
        )
    ]
    fs = run(_analyzer(pods=[pod]).analyze())
    assert fs[0].category == "image-pull"


def test_pending_scheduling_finding():
    pod = _pod("pending-pod")
    pod.status.phase = "Pending"
    pod.status.container_statuses = []
    evt = MagicMock()
    evt.reason = "FailedScheduling"
    evt.message = "0/3 nodes available"
    a = _analyzer(pods=[pod], events=[evt])
    fs = run(a.analyze())
    assert any(f.category == "pending-scheduling" for f in fs)
    sched_f = next(f for f in fs if f.category == "pending-scheduling")
    assert sched_f.suggested_fix_class == "NodeAffinityRemediator"


def test_probe_failure_finding():
    pod = _pod("probe-fail")
    evt = MagicMock()
    evt.reason = "Unhealthy"
    evt.message = "Readiness probe failed"
    a = _analyzer(pods=[pod], events=[evt])
    fs = run(a.analyze())
    assert any(f.category == "probe-failure" for f in fs)


def test_failed_mount_finding():
    pod = _pod("mount-fail")
    evt = MagicMock()
    evt.reason = "FailedMount"
    evt.message = "Unable to mount volumes"
    a = _analyzer(pods=[pod], events=[evt])
    fs = run(a.analyze())
    assert any(f.category == "failed-mount" for f in fs)
    mount_f = next(f for f in fs if f.category == "failed-mount")
    assert mount_f.suggested_fix_class == "PVCRemediator"
    assert mount_f.severity == "high"
