# Section 04 — 5-Minute Watchdog

## Purpose

After the restart-first ladder issues any remediation action, the watchdog
monitors the targeted resource for up to 5 minutes and returns a structured
verdict: **healed** or **still-sick**. This section defines the health
criteria, the polling strategy, the async implementation, and the test
fixtures that prove both happy and failure paths.

---

## 1. Health Verdicts

### 1.1 Healed

A resource is considered healed when ALL three conditions hold simultaneously
at the moment of evaluation:

1. **Readiness probe true** — the pod reports `Ready` condition
   `status: "True"` in `pod.status.conditions`.
2. **Zero new Warning events in the last 60 s** — no `Event` objects with
   `type: Warning` referencing this pod/resource have `last_timestamp` within
   the trailing 60-second window.
3. **Restart count not increasing** — the `restart_count` sampled at verdict
   time equals the restart count sampled at watch start (delta == 0 after the
   initial baseline is established).

### 1.2 Still Sick

A resource is still sick if ANY of the following is observed:

- Pod phase is not `Running` (e.g. `Pending`, `Failed`, `Unknown`).
- `Ready` condition remains `False` past `initialDelaySeconds` (derived from
  the container's readiness probe; default assumed 30 s when not set).
- New `Warning` events appear referencing this resource after baseline.
- `restart_count` increased compared to the value recorded at watch start.
- Finalizers are present and the pod has been in `Terminating` state for more
  than 90 s without progressing.

---

## 2. Polling Backoff Schedule

| Window           | Poll interval | Rationale                                      |
|------------------|---------------|------------------------------------------------|
| 0 – 60 s         | 5 s           | Catch fast crashloops immediately              |
| 61 – 180 s       | 15 s          | Reduce API pressure during normal startup      |
| 181 – 300 s      | 30 s          | Long-tail observation before final verdict     |

The event stream runs **continuously** via a `watch.Watch()` context for the
full 5-minute window, independent of the readiness poll loop.

---

## 3. WatchResult Payload

```python
from dataclasses import dataclass, field
from typing import List, Literal

@dataclass
class WatchResult:
    result: Literal["healed", "still-sick", "deleted", "namespace-deleted", "timeout"]
    duration_seconds: float
    events_seen: List[dict]          # raw event objects collected during watch
    restart_count_delta: int         # final_restart_count - baseline_restart_count
    final_phase: str                 # last observed pod.status.phase
```

---

## 4. Watch Implementation

```python
import asyncio
import time
from typing import Optional

from kubernetes import client, watch as k8s_watch


async def run_watchdog(
    namespace: str,
    pod_name: str,
    timeout_seconds: int = 300,
) -> WatchResult:
    """
    Monitor a single pod for up to timeout_seconds.
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
    result: Optional[str] = None
    final_phase = pod.status.phase or "Unknown"
    restart_count_delta = 0

    try:
        while time.monotonic() < deadline:
            elapsed = time.monotonic() - start_time
            interval = _poll_interval(elapsed)

            await asyncio.sleep(interval)

            try:
                pod = core_v1.read_namespaced_pod(
                    name=pod_name, namespace=namespace
                )
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
    import datetime
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
        import datetime
        del_ts = pod.metadata.deletion_timestamp
        if hasattr(del_ts, "replace"):
            del_ts_naive = del_ts.replace(tzinfo=None)
            age = (datetime.datetime.utcnow() - del_ts_naive).total_seconds()
            if age > 90:
                return True
    return False
```

---

## 5. Stop Conditions

| Condition                        | `WatchResult.result`  |
|----------------------------------|-----------------------|
| Healed criteria all met          | `"healed"`            |
| Still-sick criteria met          | `"still-sick"`        |
| Pod 404 during poll              | `"deleted"`           |
| Phase Unknown, no node assigned  | `"namespace-deleted"` |
| 5-minute deadline reached        | `"still-sick"`        |

---

## 6. Tests

```python
import asyncio
import datetime
from unittest.mock import MagicMock, patch

import pytest

from your_package.watchdog import run_watchdog, WatchResult


# ---------------------------------------------------------------------------
# Fake kubernetes fixtures
# ---------------------------------------------------------------------------

def _make_pod(
    phase: str,
    ready: bool,
    restart_count: int = 0,
    waiting_reason: str = None,
    node_name: str = "node-1",
) -> MagicMock:
    pod = MagicMock()
    pod.status.phase = phase
    pod.spec.node_name = node_name
    pod.metadata.deletion_timestamp = None
    pod.metadata.finalizers = []

    cond = MagicMock()
    cond.type = "Ready"
    cond.status = "True" if ready else "False"
    pod.status.conditions = [cond]

    cs = MagicMock()
    cs.restart_count = restart_count
    if waiting_reason:
        cs.state.waiting.reason = waiting_reason
    else:
        cs.state.waiting = None
    pod.status.container_statuses = [cs]
    pod.status.init_container_statuses = []

    return pod


class FakeWatch:
    """Drives a sequence of synthetic events then stops."""

    def __init__(self, events):
        self._events = iter(events)

    def stream(self, *args, **kwargs):
        for ev in self._events:
            yield ev

    def stop(self):
        pass


# ---------------------------------------------------------------------------
# Happy path: Pending -> Running -> Ready
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_watchdog_healed_pending_to_ready():
    pod_sequence = [
        _make_pod("Pending", ready=False),
        _make_pod("Pending", ready=False),
        _make_pod("Running", ready=False),
        _make_pod("Running", ready=True),
    ]
    call_count = 0

    def fake_read_pod(name, namespace):
        nonlocal call_count
        pod = pod_sequence[min(call_count, len(pod_sequence) - 1)]
        call_count += 1
        return pod

    with (
        patch("your_package.watchdog.client.CoreV1Api") as mock_api_cls,
        patch("your_package.watchdog.k8s_watch.Watch", return_value=FakeWatch([])),
        patch("your_package.watchdog._poll_interval", return_value=0.01),
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
# Failure path: Pending -> CrashLoopBackOff -> stuck
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_watchdog_still_sick_crashloop():
    pod_sequence = [
        _make_pod("Pending", ready=False),
        _make_pod("Running", ready=False, restart_count=1),
        _make_pod("Running", ready=False, restart_count=2, waiting_reason="CrashLoopBackOff"),
        _make_pod("Running", ready=False, restart_count=3, waiting_reason="CrashLoopBackOff"),
    ]
    call_count = 0

    def fake_read_pod(name, namespace):
        nonlocal call_count
        pod = pod_sequence[min(call_count, len(pod_sequence) - 1)]
        call_count += 1
        return pod

    with (
        patch("your_package.watchdog.client.CoreV1Api") as mock_api_cls,
        patch("your_package.watchdog.k8s_watch.Watch", return_value=FakeWatch([])),
        patch("your_package.watchdog._poll_interval", return_value=0.01),
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
```
