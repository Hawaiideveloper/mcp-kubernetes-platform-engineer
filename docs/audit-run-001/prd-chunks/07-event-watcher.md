# PRD Section 07 — Cluster Event Stream Watcher

## Architecture

A single controller pod runs the watcher as a long-lived asyncio task alongside the MCP server
process. It does not run as a separate Deployment; it shares the pod so it inherits the same
ServiceAccount and RBAC grants already defined in `k8s/rbac.yaml` (Events: get, list, watch).

```
mcp-kubernetes-platform-engineer pod
  ├── MCP server (stdio handler, tool dispatch)
  └── EventStreamWatcher task (asyncio background task)
       │  streams from k8s API
       │  filters, deduplicates, classifies
       └──> SQLite work queue  <── remediation worker consumes
```

The watcher uses the synchronous `kubernetes` Python client wrapped in
`asyncio.get_event_loop().run_in_executor` so the watch loop does not block the event loop.
Alternatively, `kubernetes_asyncio` may be used directly if it is added to `requirements.txt`.
The canonical API call is:

```python
from kubernetes import client, watch

core_v1 = client.CoreV1Api()
w = watch.Watch()

for raw_event in w.stream(
    core_v1.list_event_for_all_namespaces,
    timeout_seconds=0,          # stream indefinitely
    resource_version=last_rv,   # resume from last seen position
):
    event_obj = raw_event["object"]   # kubernetes.client.models.CoreV1Event
    event_type = raw_event["type"]    # ADDED | MODIFIED | DELETED
    ...
```

`timeout_seconds=0` keeps the connection open until the server terminates it or a network error
occurs. The watcher stores `event_obj.metadata.resource_version` after every processed event so
that a reconnect can pass `resource_version=last_rv` and resume without replaying the full history.
A `resource_version` of `""` (empty string) forces a full relist — used only when the API returns
HTTP 410 Gone, which means the version fell out of the watch cache.

---

## Reconnect Strategy

Reconnect uses exponential backoff `[1, 2, 4, 8, 16, 30]` seconds. On `ApiException(status=410)`
the watcher resets `last_rv = ""` to force a full relist, then reconnects. A `stop_event:
asyncio.Event` provides clean shutdown. Clean exits (no exception) reset the attempt counter to
zero.

---

## Filter: Which Events Are Actionable

Only `Type == "Warning"` events pass the filter. Normal events (`Type == "Normal"`) are discarded
immediately.

Within Warning events, two categories are dropped:

1. **Low-signal probe spam.** `Reason == "Unhealthy"` events are rate-limited: at most one queue
   entry per (namespace, pod name) per 120 seconds. A burst of probe failures produces a single
   deduplicated entry with an incrementing count.

2. **NodeNotReady during rolling restarts.** `Reason == "NodeNotReady"` is kept (it is genuinely
   interesting) but flagged with `fix_class = "node-issue"` rather than the pod-level classes.

All other Warning reasons proceed to the deduplication step.

```python
DROP_REASONS: set[str] = set()          # nothing unconditionally dropped today

RATE_LIMITED_REASONS: dict[str, int] = {
    "Unhealthy": 120,   # seconds between queue entries for the same pod
}
```

---

## Deduplication

The same incident often produces tens of identical events within seconds. Before inserting into the
queue, the watcher checks whether an entry with the same `(namespace, involvedObject.name, reason)`
was inserted within the last 60 seconds. If so, it increments the `count` column and updates
`last_seen` instead of creating a new row.

```python
DEDUP_WINDOW_SECONDS = 60
```

The dedup key is `(ev.metadata.namespace, ev.involved_object.name, ev.reason)`. This keeps the
queue small during cascading failures and prevents the remediation worker from attempting the same
fix ten times simultaneously.

---

## Classification: Event Reason to fix_class

The watcher maps `event.reason` (and optionally `event.involved_object.kind`) to a `fix_class`
string. The fix_class drives which remediation handler the worker invokes (see PRD sections 03, 09,
and 17).

| Reason | involvedObject.kind | fix_class |
|---|---|---|
| `BackOff` | Pod | `restart-first-ladder` |
| `OOMKilling` | Pod | `restart-first-ladder` |
| `ImagePullBackOff` | Pod | `image-tag-migration` |
| `ErrImagePull` | Pod | `image-tag-migration` |
| `FailedScheduling` | Pod | `resource-shortage` |
| `FailedMount` | Pod | `pvc-issue` |
| `FailedAttachVolume` | Pod | `pvc-issue` |
| `Evicted` | Pod | `resource-shortage` |
| `NodeNotReady` | Node | `node-issue` |
| `FailedCreate` | ReplicaSet | `resource-shortage` |
| `Killing` | Pod | `ignored` (normal shutdown) |

Reasons not in the table are given `fix_class = "unknown"` and inserted into the queue with
`status = "queued"` so a human can review them. They do not block the watcher.

```python
REASON_TO_FIX_CLASS: dict[tuple[str, str], str] = {
    ("BackOff",             "Pod"):        "restart-first-ladder",
    ("OOMKilling",          "Pod"):        "restart-first-ladder",
    ("ImagePullBackOff",    "Pod"):        "image-tag-migration",
    ("ErrImagePull",        "Pod"):        "image-tag-migration",
    ("FailedScheduling",    "Pod"):        "resource-shortage",
    ("FailedMount",         "Pod"):        "pvc-issue",
    ("FailedAttachVolume",  "Pod"):        "pvc-issue",
    ("Evicted",             "Pod"):        "resource-shortage",
    ("NodeNotReady",        "Node"):       "node-issue",
    ("FailedCreate",        "ReplicaSet"): "resource-shortage",
    ("Killing",             "Pod"):        "ignored",
}

def classify(self, ev: client.CoreV1Event) -> str:
    kind = ev.involved_object.kind or ""
    reason = ev.reason or ""
    return REASON_TO_FIX_CLASS.get((reason, kind), "unknown")
```

---

## Queue: SQLite Work Queue

The queue is a SQLite database at `$DATA_DIR/worklist.db` (see PRD section 25 for the full schema
and migration plan). The watcher only writes to this table; the remediation worker only reads and
updates it.

```sql
CREATE TABLE IF NOT EXISTS work_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ns          TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    reason      TEXT    NOT NULL,
    fix_class   TEXT    NOT NULL,
    first_seen  TEXT    NOT NULL,   -- ISO-8601 UTC
    last_seen   TEXT    NOT NULL,   -- ISO-8601 UTC
    count       INTEGER NOT NULL DEFAULT 1,
    status      TEXT    NOT NULL DEFAULT 'queued'
                CHECK(status IN ('queued','claimed','resolved','escalated'))
);

CREATE INDEX IF NOT EXISTS idx_wq_status ON work_queue(status);
CREATE INDEX IF NOT EXISTS idx_wq_dedup  ON work_queue(ns, name, reason, last_seen);
```

Insert path: `_upsert` queries for an existing `status='queued'` row with matching
`(ns, name, reason)` and `last_seen > now - 60s`. If found, it runs `UPDATE ... SET count=count+1,
last_seen=?`. If not found, it runs `INSERT`. Both branches execute inside a single
`sqlite3.connect(db_path)` context manager for atomicity.

---

## Backpressure

If the count of `status='queued'` rows exceeds `QUEUE_DEPTH_LIMIT` (default: 50), the watcher
pauses classification: it continues draining the watch stream (to keep `resource_version` current
and avoid a 410 on reconnect) but does not call `_upsert`. It emits a Prometheus counter
`event_watcher_backpressure_total` and logs at ERROR level. When the depth drops below the limit,
classification resumes automatically.

```python
QUEUE_DEPTH_LIMIT = 50

# inside the event processing loop:
if fix_class != "ignored" and self._queue_depth() < QUEUE_DEPTH_LIMIT:
    self._upsert(ev, fix_class)
else:
    BACKPRESSURE_COUNTER.inc()
    logger.error("work queue depth at limit; classification paused")
```

`_queue_depth()` runs `SELECT COUNT(*) FROM work_queue WHERE status='queued'`. The Prometheus
counter `event_watcher_backpressure_total` is exposed on the `/metrics` endpoint (wired Sprint 1).
The watch stream continues draining so `resource_version` stays current.

---

## Tests

### Unit Test: Event Classification

```python
# tests/test_event_watcher.py

import pytest
from unittest.mock import MagicMock
from kubernetes import client
from src.watchers.event_watcher import EventStreamWatcher

def _make_event(reason: str, kind: str) -> client.CoreV1Event:
    ev = client.CoreV1Event()
    ev.reason = reason
    ev.type = "Warning"
    ev.metadata = client.V1ObjectMeta(namespace="default")
    ev.involved_object = client.V1ObjectReference(kind=kind, name="test-pod")
    ev.message = f"fake {reason}"
    return ev

@pytest.mark.parametrize("reason,kind,expected", [
    ("BackOff",          "Pod",        "restart-first-ladder"),
    ("ImagePullBackOff", "Pod",        "image-tag-migration"),
    ("FailedMount",      "Pod",        "pvc-issue"),
    ("FailedScheduling", "Pod",        "resource-shortage"),
    ("NodeNotReady",     "Node",       "node-issue"),
    ("Killing",          "Pod",        "ignored"),
    ("SomeUnknown",      "Pod",        "unknown"),
])
def test_classify(reason, kind, expected, tmp_path):
    watcher = EventStreamWatcher(
        core_v1=MagicMock(),
        db_path=str(tmp_path / "worklist.db"),
    )
    ev = _make_event(reason, kind)
    assert watcher.classify(ev) == expected
```

### Unit Test: Deduplication Within Window

```python
def test_dedup_within_window(tmp_path):
    watcher = EventStreamWatcher(core_v1=MagicMock(), db_path=str(tmp_path / "worklist.db"))
    ev = _make_event("BackOff", "Pod")
    watcher._upsert(ev, "restart-first-ladder")
    watcher._upsert(ev, "restart-first-ladder")  # second call in same 60s window
    with sqlite3.connect(watcher._db_path) as con:
        rows = con.execute("SELECT count FROM work_queue").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 2   # count incremented, not a second row
```

### Replay Test: Recorded Cluster Failure Stream

```python
# tests/fixtures/crashloop-stream.json -- recorded from a real cluster failure
# Format: [{"type": "ADDED"|"MODIFIED", "object": <CoreV1Event dict>}, ...]

def test_replay_crashloop_stream(tmp_path):
    with open("tests/fixtures/crashloop-stream.json") as f:
        stream_fixture = json.load(f)
    watcher = EventStreamWatcher(core_v1=MagicMock(), db_path=str(tmp_path / "worklist.db"))
    with patch("kubernetes.watch.Watch") as MockWatch:
        MockWatch.return_value.stream.return_value = iter(stream_fixture)
        watcher._consume_stream()
    with sqlite3.connect(watcher._db_path) as con:
        rows = con.execute(
            "SELECT reason, fix_class, status FROM work_queue ORDER BY id"
        ).fetchall()
    # Fixture contains 3 distinct (ns, name, reason) tuples from the failure.
    assert len(rows) == 3
    assert all(r[2] == "queued" for r in rows)
    reasons = {r[0] for r in rows}
    assert "BackOff" in reasons
    assert "ImagePullBackOff" in reasons
```

The fixture `tests/fixtures/crashloop-stream.json` is recorded from a live cluster
(`kubectl get events --watch -o json`) during a CrashLoopBackOff incident. It is committed as a
stable golden input and never regenerated automatically.

---

## Acceptance Criteria

- `EventStreamWatcher` is implemented in `src/watchers/event_watcher.py`.
- `watch.Watch().stream(core_v1.list_event_for_all_namespaces, ...)` is the actual API call; no
  mocked or canned event list is used in production code.
- Reconnect with `resource_version` resume is exercised by the unit test suite.
- All five classification paths in the table above have a passing parametrized test.
- The deduplication test confirms a 60-second window produces one queue row with count=2, not two
  rows.
- The replay test passes against the committed fixture and asserts exact queue state.
- Backpressure test: pre-fill 50 queued rows, assert a 51st event does not add a row and
  increments the Prometheus counter.
- No story is marked DONE until the watcher is running in the production cluster and at least one
  real Warning event has been correctly routed through the queue to the remediation worker.
