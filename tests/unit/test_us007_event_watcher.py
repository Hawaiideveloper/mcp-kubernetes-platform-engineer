"""Unit tests for US-007: EventStreamWatcher."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "crashloop-stream.json"

sys.path.insert(0, str(REPO / "src"))

from watchers.event_watcher import (  # noqa: E402
    BACKPRESSURE_COUNTER,
    QUEUE_DEPTH_LIMIT,
    EventStreamWatcher,
)


# ---------------------------------------------------------------------------
# Helpers — use MagicMock so we avoid CoreV1Event constructor constraints
# ---------------------------------------------------------------------------


def _make_event(
    reason: str,
    kind: str,
    ns: str = "default",
    name: str = "test-pod",
    ev_type: str = "Warning",
    rv: str = "12345",
) -> MagicMock:
    ev = MagicMock()
    ev.reason = reason
    ev.type = ev_type
    ev.message = f"fake {reason}"
    ev.metadata.namespace = ns
    ev.metadata.resource_version = rv
    ev.involved_object.kind = kind
    ev.involved_object.name = name
    ev.involved_object.namespace = ns
    return ev


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason,kind,expected",
    [
        ("BackOff", "Pod", "restart-first-ladder"),
        ("OOMKilling", "Pod", "restart-first-ladder"),
        ("ImagePullBackOff", "Pod", "image-tag-migration"),
        ("ErrImagePull", "Pod", "image-tag-migration"),
        ("FailedScheduling", "Pod", "resource-shortage"),
        ("FailedMount", "Pod", "pvc-issue"),
        ("FailedAttachVolume", "Pod", "pvc-issue"),
        ("Evicted", "Pod", "resource-shortage"),
        ("NodeNotReady", "Node", "node-issue"),
        ("FailedCreate", "ReplicaSet", "resource-shortage"),
        ("Killing", "Pod", "ignored"),
        ("SomeUnknown", "Pod", "unknown"),
    ],
)
def test_classify(reason: str, kind: str, expected: str, tmp_path: Path) -> None:
    watcher = EventStreamWatcher(core_v1=MagicMock(), db_path=str(tmp_path / "wq.db"))
    ev = _make_event(reason, kind)
    assert watcher.classify(ev) == expected


# ---------------------------------------------------------------------------
# Deduplication within window
# ---------------------------------------------------------------------------


def test_dedup_within_window(tmp_path: Path) -> None:
    watcher = EventStreamWatcher(core_v1=MagicMock(), db_path=str(tmp_path / "wq.db"))
    ev = _make_event("BackOff", "Pod")
    watcher._upsert(ev, "restart-first-ladder")
    watcher._upsert(ev, "restart-first-ladder")
    with sqlite3.connect(watcher._db_path) as con:
        rows = con.execute("SELECT count FROM work_queue").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 2


# ---------------------------------------------------------------------------
# Replay fixture
# ---------------------------------------------------------------------------


def _fixture_to_mock_events(stream_data: list) -> list:
    """Convert raw JSON fixture records to MagicMock event objects."""
    events = []
    for record in stream_data:
        obj = record.get("object", {})
        meta = obj.get("metadata", {})
        inv = obj.get("involvedObject", {})
        ev = MagicMock()
        ev.type = obj.get("type", "Warning")
        ev.reason = obj.get("reason", "")
        ev.message = obj.get("message", "")
        ev.metadata.namespace = meta.get("namespace", "default")
        ev.metadata.resource_version = meta.get("resourceVersion", "")
        ev.involved_object.kind = inv.get("kind", "Pod")
        ev.involved_object.name = inv.get("name", "")
        ev.involved_object.namespace = inv.get("namespace", "default")
        events.append({"type": record.get("type", "ADDED"), "object": ev})
    return events


def test_replay_crashloop_stream(tmp_path: Path) -> None:
    with open(FIXTURES) as f:
        stream_fixture = json.load(f)

    mock_events = _fixture_to_mock_events(stream_fixture)
    watcher = EventStreamWatcher(core_v1=MagicMock(), db_path=str(tmp_path / "wq.db"))

    with patch("kubernetes.watch.Watch") as MockWatch:
        MockWatch.return_value.stream.return_value = iter(mock_events)
        watcher._consume_stream()

    with sqlite3.connect(watcher._db_path) as con:
        rows = con.execute(
            "SELECT reason, fix_class, status FROM work_queue ORDER BY id"
        ).fetchall()

    # Fixture: BackOff (deduped to 1 row), ImagePullBackOff, FailedMount;
    # Killing is ignored; Normal type is filtered.
    assert len(rows) == 3
    assert all(r[2] == "queued" for r in rows)
    reasons = {r[0] for r in rows}
    assert "BackOff" in reasons
    assert "ImagePullBackOff" in reasons
    assert "FailedMount" in reasons


# ---------------------------------------------------------------------------
# Backpressure
# ---------------------------------------------------------------------------


def test_backpressure_no_insert_at_limit(tmp_path: Path) -> None:
    watcher = EventStreamWatcher(core_v1=MagicMock(), db_path=str(tmp_path / "wq.db"))

    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(watcher._db_path) as con:
        for i in range(QUEUE_DEPTH_LIMIT):
            con.execute(
                "INSERT INTO work_queue (ns,kind,name,reason,fix_class,first_seen,last_seen)"
                " VALUES (?,?,?,?,?,?,?)",
                ("default", "Pod", f"pod-{i}", "BackOff", "restart-first-ladder", now, now),
            )

    assert watcher._queue_depth() == QUEUE_DEPTH_LIMIT

    before = BACKPRESSURE_COUNTER._value.get()
    ev = _make_event("OOMKilling", "Pod", name="new-pod")

    with patch("kubernetes.watch.Watch") as MockWatch:
        MockWatch.return_value.stream.return_value = iter([{"type": "ADDED", "object": ev}])
        watcher._consume_stream()

    after = BACKPRESSURE_COUNTER._value.get()
    assert after > before, "Backpressure counter must increment when queue full"
    assert watcher._queue_depth() == QUEUE_DEPTH_LIMIT, "No new row must be inserted"


# ---------------------------------------------------------------------------
# Resource version tracking
# ---------------------------------------------------------------------------


def test_resource_version_tracked(tmp_path: Path) -> None:
    watcher = EventStreamWatcher(core_v1=MagicMock(), db_path=str(tmp_path / "wq.db"))
    ev = _make_event("BackOff", "Pod", rv="99999")

    with patch("kubernetes.watch.Watch") as MockWatch:
        MockWatch.return_value.stream.return_value = iter([{"type": "ADDED", "object": ev}])
        watcher._consume_stream()

    assert watcher._last_rv == "99999"
