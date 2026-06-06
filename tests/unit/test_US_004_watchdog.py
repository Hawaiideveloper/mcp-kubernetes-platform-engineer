"""
tests/unit/test_US_004_watchdog.py — Unit tests for the 5-minute watchdog (US-004).

Covers:
  - Happy path: Pending -> Running -> Ready (healed)
  - Failure path: CrashLoopBackOff (still-sick)
  - Pod deleted during watch (deleted)
  - Namespace deletion detection (namespace-deleted)
  - Restart count increase triggers still-sick
  - Poll interval schedule correctness
  - Helper: _sum_restart_counts
  - Helper: _recent_warning_events
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from auto_remediate.watchdog import (
    WatchResult,
    _poll_interval,
    _recent_warning_events,
    _sum_restart_counts,
    run_watchdog,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_pod(
    phase: str,
    ready: bool,
    restart_count: int = 0,
    waiting_reason: str | None = None,
    node_name: str | None = "node-1",
    deletion_timestamp: datetime.datetime | None = None,
    finalizers: list[str] | None = None,
) -> MagicMock:
    pod = MagicMock()
    pod.status.phase = phase
    pod.spec.node_name = node_name
    pod.metadata.deletion_timestamp = deletion_timestamp
    pod.metadata.finalizers = finalizers or []

    cond = MagicMock()
    cond.type = "Ready"
    cond.status = "True" if ready else "False"
    pod.status.conditions = [cond]

    cs = MagicMock()
    cs.restart_count = restart_count
    if waiting_reason:
        cs.state.waiting = MagicMock(reason=waiting_reason)
    else:
        cs.state.waiting = None
    pod.status.container_statuses = [cs]
    pod.status.init_container_statuses = []

    return pod


class FakeWatch:
    """Drives a sequence of synthetic Warning events then stops."""

    def __init__(self, events: list) -> None:
        self._events = events

    def stream(self, *args, **kwargs):  # noqa: ANN002
        yield from self._events

    def stop(self) -> None:
        pass


def _api_404() -> MagicMock:
    exc = MagicMock()
    exc.status = 404
    api_exc = Exception.__new__(Exception)
    # Simulate kubernetes.client.exceptions.ApiException
    api_exc.status = 404
    api_exc.__class__.__name__ = "ApiException"
    return api_exc


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


def test_poll_interval_schedule() -> None:
    assert _poll_interval(0) == 5.0
    assert _poll_interval(59) == 5.0
    assert _poll_interval(60) == 15.0
    assert _poll_interval(179) == 15.0
    assert _poll_interval(180) == 30.0
    assert _poll_interval(300) == 30.0


def test_sum_restart_counts_multiple_containers() -> None:
    pod = MagicMock()
    cs1 = MagicMock()
    cs1.restart_count = 3
    cs2 = MagicMock()
    cs2.restart_count = 2
    init_cs = MagicMock()
    init_cs.restart_count = 1
    pod.status.container_statuses = [cs1, cs2]
    pod.status.init_container_statuses = [init_cs]
    assert _sum_restart_counts(pod) == 6


def test_sum_restart_counts_empty() -> None:
    pod = MagicMock()
    pod.status.container_statuses = []
    pod.status.init_container_statuses = []
    assert _sum_restart_counts(pod) == 0


def test_recent_warning_events_none_when_old() -> None:
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=120)).isoformat()
    events = [{"last_timestamp": old_ts, "reason": "OOMKilled", "message": "x", "count": 1}]
    assert _recent_warning_events(events, window_seconds=60) is False


def test_recent_warning_events_true_when_recent() -> None:
    recent_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=10)).isoformat()
    events = [{"last_timestamp": recent_ts, "reason": "OOMKilled", "message": "x", "count": 1}]
    assert _recent_warning_events(events, window_seconds=60) is True


def test_recent_warning_events_skips_none_ts() -> None:
    events = [{"last_timestamp": "None", "reason": "Backoff", "message": "y", "count": 1}]
    assert _recent_warning_events(events, window_seconds=60) is False


# ---------------------------------------------------------------------------
# run_watchdog: happy path — pod transitions Pending -> Running -> Ready
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_healed_pending_to_ready() -> None:
    pod_sequence = [
        _make_pod("Pending", ready=False),
        _make_pod("Pending", ready=False),
        _make_pod("Running", ready=False),
        _make_pod("Running", ready=True),
    ]
    call_count = 0

    def fake_read_pod(name: str, namespace: str) -> MagicMock:
        nonlocal call_count
        pod = pod_sequence[min(call_count, len(pod_sequence) - 1)]
        call_count += 1
        return pod

    with (
        patch("auto_remediate.watchdog.client.CoreV1Api") as mock_api_cls,
        patch("auto_remediate.watchdog.k8s_watch.Watch", return_value=FakeWatch([])),
        patch("auto_remediate.watchdog._poll_interval", return_value=0.01),
    ):
        mock_api = mock_api_cls.return_value
        mock_api.read_namespaced_pod.side_effect = fake_read_pod
        mock_api.list_namespaced_event.return_value = iter([])

        result: WatchResult = await run_watchdog(
            namespace="default", pod_name="my-pod", timeout_seconds=5
        )

    assert result.result == "healed"
    assert result.restart_count_delta == 0
    assert result.final_phase == "Running"


# ---------------------------------------------------------------------------
# run_watchdog: failure path — CrashLoopBackOff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_still_sick_crashloop() -> None:
    pod_sequence = [
        _make_pod("Pending", ready=False),
        _make_pod("Running", ready=False, restart_count=1),
        _make_pod("Running", ready=False, restart_count=2, waiting_reason="CrashLoopBackOff"),
        _make_pod("Running", ready=False, restart_count=3, waiting_reason="CrashLoopBackOff"),
    ]
    call_count = 0

    def fake_read_pod(name: str, namespace: str) -> MagicMock:
        nonlocal call_count
        pod = pod_sequence[min(call_count, len(pod_sequence) - 1)]
        call_count += 1
        return pod

    with (
        patch("auto_remediate.watchdog.client.CoreV1Api") as mock_api_cls,
        patch("auto_remediate.watchdog.k8s_watch.Watch", return_value=FakeWatch([])),
        patch("auto_remediate.watchdog._poll_interval", return_value=0.01),
    ):
        mock_api = mock_api_cls.return_value
        mock_api.read_namespaced_pod.side_effect = fake_read_pod
        mock_api.list_namespaced_event.return_value = iter([])

        result: WatchResult = await run_watchdog(
            namespace="default", pod_name="crasher", timeout_seconds=5
        )

    assert result.result == "still-sick"
    assert result.restart_count_delta >= 1
    assert result.final_phase == "Running"


# ---------------------------------------------------------------------------
# run_watchdog: pod deleted (404) during baseline read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_pod_deleted_at_baseline() -> None:
    from kubernetes.client.exceptions import ApiException

    api_exc = ApiException(status=404)

    with patch("auto_remediate.watchdog.client.CoreV1Api") as mock_api_cls:
        mock_api = mock_api_cls.return_value
        mock_api.read_namespaced_pod.side_effect = api_exc

        result: WatchResult = await run_watchdog(
            namespace="default", pod_name="gone-pod", timeout_seconds=5
        )

    assert result.result == "deleted"
    assert result.duration_seconds == 0.0


# ---------------------------------------------------------------------------
# run_watchdog: pod deleted (404) during poll loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_pod_deleted_during_poll() -> None:
    from kubernetes.client.exceptions import ApiException

    baseline_pod = _make_pod("Running", ready=False)
    api_exc = ApiException(status=404)

    call_count = 0

    def fake_read_pod(name: str, namespace: str) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return baseline_pod
        raise api_exc

    with (
        patch("auto_remediate.watchdog.client.CoreV1Api") as mock_api_cls,
        patch("auto_remediate.watchdog.k8s_watch.Watch", return_value=FakeWatch([])),
        patch("auto_remediate.watchdog._poll_interval", return_value=0.01),
    ):
        mock_api = mock_api_cls.return_value
        mock_api.read_namespaced_pod.side_effect = fake_read_pod
        mock_api.list_namespaced_event.return_value = iter([])

        result: WatchResult = await run_watchdog(
            namespace="default", pod_name="vanishing-pod", timeout_seconds=5
        )

    assert result.result == "deleted"


# ---------------------------------------------------------------------------
# run_watchdog: namespace deleted (Unknown phase, no node)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_namespace_deleted() -> None:
    baseline_pod = _make_pod("Running", ready=False)
    ns_deleted_pod = _make_pod("Unknown", ready=False, node_name=None)

    call_count = 0

    def fake_read_pod(name: str, namespace: str) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return baseline_pod
        return ns_deleted_pod

    with (
        patch("auto_remediate.watchdog.client.CoreV1Api") as mock_api_cls,
        patch("auto_remediate.watchdog.k8s_watch.Watch", return_value=FakeWatch([])),
        patch("auto_remediate.watchdog._poll_interval", return_value=0.01),
    ):
        mock_api = mock_api_cls.return_value
        mock_api.read_namespaced_pod.side_effect = fake_read_pod
        mock_api.list_namespaced_event.return_value = iter([])

        result: WatchResult = await run_watchdog(
            namespace="default", pod_name="ns-del-pod", timeout_seconds=5
        )

    assert result.result == "namespace-deleted"


# ---------------------------------------------------------------------------
# run_watchdog: restart count increase -> still-sick
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_still_sick_restart_count_increase() -> None:
    pod_sequence = [
        _make_pod("Running", ready=True, restart_count=0),
        _make_pod("Running", ready=True, restart_count=1),
    ]
    call_count = 0

    def fake_read_pod(name: str, namespace: str) -> MagicMock:
        nonlocal call_count
        pod = pod_sequence[min(call_count, len(pod_sequence) - 1)]
        call_count += 1
        return pod

    with (
        patch("auto_remediate.watchdog.client.CoreV1Api") as mock_api_cls,
        patch("auto_remediate.watchdog.k8s_watch.Watch", return_value=FakeWatch([])),
        patch("auto_remediate.watchdog._poll_interval", return_value=0.01),
    ):
        mock_api = mock_api_cls.return_value
        mock_api.read_namespaced_pod.side_effect = fake_read_pod
        mock_api.list_namespaced_event.return_value = iter([])

        result: WatchResult = await run_watchdog(
            namespace="default", pod_name="restart-pod", timeout_seconds=5
        )

    assert result.result == "still-sick"
    assert result.restart_count_delta >= 1
