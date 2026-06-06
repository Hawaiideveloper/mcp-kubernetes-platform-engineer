"""Unit tests for US-003 restart-first remediation ladder."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from auto_remediate.remediation_ladder import (
    NAMESPACE_LADDER_CAP,
    CircuitBreakerError,
    LadderSession,
    LadderState,
    NamespaceCircuitBreaker,
    NamespaceCircuitOpenError,
    PodDiagnosis,
    ProtectedNamespaceError,
    RemediationLadder,
    ResourceRef,
    emit_dpo_pair,
    is_restart_eligible,
)


# ---------------------------------------------------------------------------
# Eligibility tests
# ---------------------------------------------------------------------------


def test_restart_eligible_crash_loop_low_count():
    assert is_restart_eligible("CrashLoopBackOff", 2) is True


def test_restart_ineligible_oom():
    assert is_restart_eligible("OOMKilled", 0) is False


def test_restart_ineligible_image_pull():
    assert is_restart_eligible("ImagePullBackOff", 0) is False


def test_restart_ineligible_high_restart_count():
    assert is_restart_eligible("CrashLoopBackOff", 5) is False


def test_restart_eligible_readiness_probe():
    assert is_restart_eligible("ReadinessProbeConnectionRefused", 0) is True


def test_restart_eligible_liveness_probe():
    assert is_restart_eligible("LivenessProbeTimeout", 0) is True


def test_restart_ineligible_create_container_config():
    assert is_restart_eligible("CreateContainerConfigError", 0) is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ladder(dry_run: bool = True, ns_circuit: Optional[NamespaceCircuitBreaker] = None) -> RemediationLadder:
    core_v1 = MagicMock()
    apps_v1 = MagicMock()
    return RemediationLadder(
        core_v1=core_v1,
        apps_v1=apps_v1,
        escalation_webhook="http://localhost/webhook",
        dry_run=dry_run,
        ns_circuit=ns_circuit,
    )


def _make_session(namespace: str = "default", cycles: int = 0) -> LadderSession:
    ref = ResourceRef(namespace=namespace, kind="Deployment", name="myapp")
    ts = datetime.utcnow() - timedelta(seconds=1)
    session = LadderSession(
        session_id="test-session-001",
        resource=ref,
        restart_ts=ts,
        heal_deadline_ts=datetime.utcfromtimestamp(ts.timestamp() + 300),
        ladder_cycles_this_hour=cycles,
    )
    return session


# ---------------------------------------------------------------------------
# Watchdog tests
# ---------------------------------------------------------------------------


def _make_pod_status(ready: bool):
    cs = MagicMock()
    cs.ready = ready
    pod = MagicMock()
    pod.status.container_statuses = [cs]
    return pod


def _make_empty_events():
    events = MagicMock()
    events.items = []
    return events


def test_watchdog_heals():
    """Ready=False once, then Ready=True twice → HEALED."""
    ladder = _make_ladder()
    call_count = 0
    ready_sequence = [False, True, True]

    def mock_pod_status(name, namespace):  # noqa: ARG001
        nonlocal call_count
        val = ready_sequence[min(call_count, len(ready_sequence) - 1)]
        call_count += 1
        return _make_pod_status(val)

    ladder._core_v1.read_namespaced_pod_status.side_effect = mock_pod_status
    ladder._core_v1.list_namespaced_event.return_value = _make_empty_events()

    session = _make_session()
    session.state = LadderState.WATCH_HEALING
    # Shorten timeout for test speed
    ladder.WATCH_TIMEOUT_SECONDS = 300

    async def run():
        with patch("asyncio.sleep", return_value=None):
            return await ladder._watchdog(session, poll_interval=0)

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result.state == LadderState.HEALED


def test_watchdog_still_sick():
    """Ready=False throughout → STILL_SICK after deadline."""
    ladder = _make_ladder()
    # Set timeout to 0 so the while loop exits immediately (deadline already expired)
    ladder.WATCH_TIMEOUT_SECONDS = 0
    ladder._core_v1.read_namespaced_pod_status.return_value = _make_pod_status(False)
    ladder._core_v1.list_namespaced_event.return_value = _make_empty_events()

    session = _make_session()
    session.state = LadderState.WATCH_HEALING

    async def run():
        with patch("asyncio.sleep", return_value=None):
            return await ladder._watchdog(session, poll_interval=0)

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result.state == LadderState.STILL_SICK


# ---------------------------------------------------------------------------
# Circuit breaker tests
# ---------------------------------------------------------------------------


def test_circuit_breaker_per_resource():
    """3rd restart in same hour raises CircuitBreakerError."""
    ladder = _make_ladder()
    session = _make_session(cycles=2)  # already at MAX_CYCLES_PER_HOUR

    async def run():
        return await ladder.restart(session)

    with pytest.raises(CircuitBreakerError):
        asyncio.get_event_loop().run_until_complete(run())


def test_circuit_breaker_per_namespace():
    """11th active session raises NamespaceCircuitOpenError."""
    cb = NamespaceCircuitBreaker()
    ns = "test-ns"
    for _ in range(NAMESPACE_LADDER_CAP):
        cb.acquire(ns)
    with pytest.raises(NamespaceCircuitOpenError):
        cb.acquire(ns)


# ---------------------------------------------------------------------------
# Trading namespace tests
# ---------------------------------------------------------------------------


def test_trading_namespace_restart_blocked():
    ladder = _make_ladder()
    session = _make_session(namespace="ibkr-live-trader")

    async def run():
        return await ladder.restart(session)

    with pytest.raises(ProtectedNamespaceError):
        asyncio.get_event_loop().run_until_complete(run())


def test_trading_namespace_observe_allowed():
    """detect() and analyze() with trading namespace must not raise ProtectedNamespaceError."""
    core_v1 = MagicMock()
    apps_v1 = MagicMock()
    ns_circuit = NamespaceCircuitBreaker()

    # detect() calls read_namespaced_pod_status — set up a pod with CrashLoopBackOff
    cs = MagicMock()
    cs.state.waiting.reason = "CrashLoopBackOff"
    cs.restart_count = 2
    pod_mock = MagicMock()
    pod_mock.status.container_statuses = [cs]
    core_v1.read_namespaced_pod_status.return_value = pod_mock

    events_mock = MagicMock()
    events_mock.items = []
    core_v1.list_namespaced_event.return_value = events_mock
    core_v1.read_namespaced_pod_log.return_value = "log line"

    ladder = RemediationLadder(
        core_v1=core_v1,
        apps_v1=apps_v1,
        escalation_webhook="http://localhost/wh",
        dry_run=True,
        ns_circuit=ns_circuit,
    )

    ref = ResourceRef(namespace="daxxon-trading", kind="Deployment", name="app")

    async def run_detect():
        return await ladder.detect(ref)

    session = asyncio.get_event_loop().run_until_complete(run_detect())
    assert session is not None

    async def run_analyze():
        return await ladder.analyze(session)

    session2, diagnosis = asyncio.get_event_loop().run_until_complete(run_analyze())
    assert diagnosis is not None


# ---------------------------------------------------------------------------
# DPO pair emission
# ---------------------------------------------------------------------------


def test_dpo_pair_emitted_on_still_sick():
    """After escalate(), session.dpo_pair is set and rejected_action==rollout_restart."""
    ladder = _make_ladder()
    session = _make_session()
    session.state = LadderState.STILL_SICK

    diagnosis = PodDiagnosis(
        resource=session.resource,
        failure_class="CrashLoopBackOff",
        container_name="app",
        exit_code=1,
        restart_count=3,
        log_tail="some log\nanother line",
        event_reasons=["BackOff"],
        recommended_fix="patch_image",
    )

    async def run():
        return await ladder.escalate(session, diagnosis)

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result.dpo_pair is not None
    assert result.dpo_pair.rejected_action == "rollout_restart"
    assert result.state == LadderState.ESCALATE


def test_emit_dpo_pair_structure():
    session = _make_session()
    diagnosis = PodDiagnosis(
        resource=session.resource,
        failure_class="OOMKilled",
        container_name="worker",
        exit_code=137,
        restart_count=7,
        log_tail="line1\nline2\nline3",
        event_reasons=["OOMKilling"],
        recommended_fix="increase_memory",
    )
    pair = emit_dpo_pair(session, diagnosis, "patch_memory_limit", "healed_in_sandbox")
    assert pair.rejected_action == "rollout_restart"
    assert pair.rejected_outcome == "pod_still_sick_after_300s"
    assert pair.chosen_action == "patch_memory_limit"
    assert pair.evidence["restart_count"] == 7
    assert pair.evidence["log_tail_lines"] == 3
