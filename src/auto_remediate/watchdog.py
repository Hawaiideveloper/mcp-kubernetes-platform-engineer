"""
watchdog.py — 5-minute post-remediation watchdog (US-004).

Monitors a pod for up to 5 minutes after a remediation action and returns
a structured WatchResult: healed, still-sick, deleted, namespace-deleted,
or timeout.
"""

from __future__ import annotations

import asyncio
import datetime
import time
from dataclasses import dataclass, field
from typing import List, Literal, Optional

from kubernetes import client, watch as k8s_watch


@dataclass
class WatchResult:
    result: Literal["healed", "still-sick", "deleted", "namespace-deleted", "timeout"]
    duration_seconds: float
    events_seen: List[dict] = field(default_factory=list)
    restart_count_delta: int = 0
    final_phase: str = "Unknown"


async def run_watchdog(
    namespace: str,
    pod_name: str,
    timeout_seconds: int = 300,
) -> WatchResult:
    """Monitor a single pod for up to timeout_seconds.

    Returns a WatchResult with the final health verdict.
    """
    core_v1 = client.CoreV1Api()
    start_time = time.monotonic()
    deadline = start_time + timeout_seconds

    # --- baseline snapshot ---
    try:
        pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
    except client.exceptions.ApiException as exc:
        if exc.status == 404:
            return WatchResult(
                result="deleted",
                duration_seconds=0.0,
                events_seen=[],
                restart_count_delta=0,
                final_phase="Unknown",
            )
        raise

    baseline_restart = _sum_restart_counts(pod)
    events_seen: list[dict] = []
    event_timestamps_seen: set[str] = set()

    # --- async event stream (runs concurrently with readiness poll) ---
    stop_event = asyncio.Event()

    async def stream_events() -> None:
        w = k8s_watch.Watch()
        field_sel = (
            f"involvedObject.name={pod_name},"
            f"involvedObject.namespace={namespace},"
            "type=Warning"
        )
        for raw_event in w.stream(
            core_v1.list_namespaced_event,
            namespace=namespace,
            field_selector=field_sel,
            timeout_seconds=timeout_seconds,
        ):
            if stop_event.is_set():
                w.stop()
                break
            obj = raw_event["object"]
            uid = str(getattr(obj.metadata, "uid", id(obj)))
            if uid not in event_timestamps_seen:
                event_timestamps_seen.add(uid)
                events_seen.append(
                    {
                        "reason": obj.reason,
                        "message": obj.message,
                        "last_timestamp": str(obj.last_timestamp),
                        "count": obj.count,
                    }
                )
            await asyncio.sleep(0)  # yield to event loop

    event_task = asyncio.create_task(stream_events())

    # --- readiness poll loop ---
    result: Optional[Literal["healed", "still-sick", "deleted", "namespace-deleted", "timeout"]] = None
    final_phase = pod.status.phase or "Unknown"
    restart_count_delta = 0

    try:
        while time.monotonic() < deadline:
            elapsed = time.monotonic() - start_time
            interval = _poll_interval(elapsed)

            await asyncio.sleep(interval)

            try:
                pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            except client.exceptions.ApiException as exc:
                if exc.status == 404:
                    result = "deleted"
                    break
                raise

            final_phase = pod.status.phase or "Unknown"
            current_restart = _sum_restart_counts(pod)
            restart_count_delta = current_restart - baseline_restart

            # check namespace deletion via pod unknown phase + no node
            if final_phase == "Unknown" and not pod.spec.node_name:
                result = "namespace-deleted"
                break

            if _is_healed(pod, events_seen, restart_count_delta, start_time):
                result = "healed"
                break

            if _is_still_sick(pod, events_seen, restart_count_delta):
                result = "still-sick"
                break

    finally:
        stop_event.set()
        event_task.cancel()
        try:
            await event_task
        except asyncio.CancelledError:
            pass

    if result is None:
        result = "still-sick"  # timed out without healing

    return WatchResult(
        result=result,
        duration_seconds=time.monotonic() - start_time,
        events_seen=events_seen,
        restart_count_delta=restart_count_delta,
        final_phase=final_phase,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poll_interval(elapsed: float) -> float:
    """Return poll interval (seconds) based on elapsed time since watch start."""
    if elapsed < 60:
        return 5.0
    if elapsed < 180:
        return 15.0
    return 30.0


def _sum_restart_counts(pod: client.V1Pod) -> int:
    total = 0
    statuses = (pod.status.container_statuses or []) + (
        pod.status.init_container_statuses or []
    )
    for cs in statuses:
        total += cs.restart_count or 0
    return total


def _is_ready(pod: client.V1Pod) -> bool:
    for cond in pod.status.conditions or []:
        if cond.type == "Ready" and cond.status == "True":
            return True
    return False


def _recent_warning_events(events_seen: list[dict], window_seconds: int = 60) -> bool:
    """Return True if any collected event has a last_timestamp within window."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(seconds=window_seconds)
    for ev in events_seen:
        ts_str = ev.get("last_timestamp", "")
        if not ts_str or ts_str == "None":
            continue
        try:
            ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ts_naive = ts.replace(tzinfo=None)
            if ts_naive >= cutoff:
                return True
        except ValueError:
            pass
    return False


def _is_healed(
    pod: client.V1Pod,
    events_seen: list[dict],
    restart_delta: int,
    start_time: float,
) -> bool:
    if pod.status.phase != "Running":
        return False
    if not _is_ready(pod):
        return False
    if _recent_warning_events(events_seen):
        return False
    if restart_delta != 0:
        return False
    return True


def _is_still_sick(
    pod: client.V1Pod,
    events_seen: list[dict],
    restart_delta: int,
) -> bool:
    if pod.status.phase in ("Failed", "Unknown"):
        return True
    for cs in pod.status.container_statuses or []:
        waiting = cs.state.waiting if cs.state else None
        if waiting and waiting.reason in (
            "CrashLoopBackOff",
            "OOMKilled",
            "Error",
            "ImagePullBackOff",
            "ErrImagePull",
        ):
            return True
    if restart_delta > 0:
        return True
    # finalizer stuck: terminating longer than 90 s
    if pod.metadata.deletion_timestamp and pod.metadata.finalizers:
        del_ts = pod.metadata.deletion_timestamp
        if hasattr(del_ts, "replace"):
            del_ts_naive = del_ts.replace(tzinfo=None)
            age = (datetime.datetime.utcnow() - del_ts_naive).total_seconds()
            if age > 90:
                return True
    return False
