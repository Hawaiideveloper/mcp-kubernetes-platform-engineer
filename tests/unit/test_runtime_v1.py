"""Unit tests for auto_remediate.runtime — Runtime Integration v1."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Minimal stub types so we can test without a live k8s cluster
# ---------------------------------------------------------------------------


class _Ref:
    kind = "Pod"
    namespace = "default"
    name = "test-pod"
    uid = "uid-001"


class _Finding:
    resource = _Ref()
    severity = "high"
    category = "crash-loop"
    root_cause_hypothesis = "container crash-looping (restarts=3)"
    suggested_fix_class = "RestartFirstLadderRemediator"

    def fingerprint(self) -> str:
        return "deadbeef01234567"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def _fresh_rt():
    """Reload the module so module-level state (_SEEN, _SHUTDOWN) is reset."""
    import importlib
    import auto_remediate.runtime as rt

    importlib.reload(rt)
    return rt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_import():
    """Module can be imported without a live cluster."""
    import auto_remediate.runtime  # noqa: F401


def test_one_iteration_writes_audit_log(tmp_path):
    """A single finding is appended to the audit log on first iteration."""
    audit_file = tmp_path / "audit.log"
    finding = _Finding()

    rt = _fresh_rt()

    with patch.object(rt, "AUDIT", audit_file):
        rt._process_findings([finding])

    assert audit_file.exists(), "audit.log should be created"
    content = audit_file.read_text()
    assert "crash-loop" in content
    assert "test-pod" in content
    assert "default" in content


def test_dedup_same_finding_not_written_twice(tmp_path):
    """The same finding within the dedup window is only written once."""
    audit_file = tmp_path / "audit.log"
    finding = _Finding()

    rt = _fresh_rt()

    with patch.object(rt, "AUDIT", audit_file):
        rt._process_findings([finding])  # first — should write
        rt._process_findings([finding])  # second — should be deduped

    lines = [ln for ln in audit_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected 1 line (deduped), got {len(lines)}: {lines}"


def test_dedup_expires_after_window(tmp_path):
    """A finding outside the dedup window is written again."""
    audit_file = tmp_path / "audit.log"
    finding = _Finding()

    rt = _fresh_rt()

    with patch.object(rt, "AUDIT", audit_file):
        # write once
        rt._process_findings([finding])
        # backdate the expiry so it appears expired
        key = rt._dedup_key(finding)
        rt._SEEN.clear()
        rt._SEEN.append((time.time() - 1, key))  # already expired
        # second write should now go through
        rt._process_findings([finding])

    lines = [ln for ln in audit_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2, f"expected 2 lines after expiry, got {len(lines)}"


def test_run_loop_calls_analyzer_and_writes(tmp_path):
    """_run_loop calls run_safe on the analyzer and writes the finding."""
    audit_file = tmp_path / "audit.log"
    health_file = tmp_path / "healthz"
    finding = _Finding()

    mock_analyzer = MagicMock()
    mock_analyzer.run_safe = AsyncMock(return_value=[finding])

    rt = _fresh_rt()

    # stop() returns True after the first tick
    call_count = 0

    def _stop() -> bool:
        nonlocal call_count
        call_count += 1
        # Allow at least 3 calls before stopping: loop-check + sleep-check
        return call_count > 3

    async def _one_shot():
        with patch.object(rt, "AUDIT", audit_file), patch.object(
            rt, "HEALTH", health_file
        ), patch.object(rt, "LOOP_INTERVAL", 0):
            await rt._run_loop(mock_analyzer, stop=_stop)

    _run(_one_shot())

    mock_analyzer.run_safe.assert_called()
    assert audit_file.exists()
    content = audit_file.read_text()
    assert "crash-loop" in content
