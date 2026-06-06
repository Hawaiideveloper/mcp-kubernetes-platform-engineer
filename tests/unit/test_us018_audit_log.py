"""
tests/unit/test_us018_audit_log.py — PRD §18 unit tests.

Covers:
  - AuditLogger.append / reopen (AC-18-3, AC-18-7)
  - upsert_finding dedup (AC-18-5)
  - query_audit_log namespace + time filters (AC-18-6)
  - root_cause_hash normalization
  - All eight action verbs round-trip
  - Write failure emits to stderr without raising (AC-18-2)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "src"))

from auto_remediate.audit_logger import AuditLogger, VALID_ACTIONS  # noqa: E402
from auto_remediate.audit_query import query_audit_log  # noqa: E402
from auto_remediate.finding_store import SCHEMA_SQL, upsert_finding  # noqa: E402
from auto_remediate.root_cause import root_cause_hash  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(i: int, ns: str = "default") -> dict:
    return {
        "timestamp": f"2026-06-02T00:{i // 60:02d}:{i % 60:02d}.000Z",
        "actor": "remediator/sa-auto-fix",
        "action": "detect",
        "target": {"kind": "Pod", "namespace": ns, "name": f"pod-{i}"},
        "finding_id": f"find_{i:04x}",
        "fix_id": None,
        "sandbox_id": None,
        "pr_url": None,
        "outcome": "success",
        "evidence_pointer": f"gs://evidence/find_{i:04x}.json",
        "dpo_pair_url": None,
    }


# ---------------------------------------------------------------------------
# AuditLogger tests
# ---------------------------------------------------------------------------

def test_append_1000_records():
    """AC-18-7: 1000 records written, all present after simulated rotation."""
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))

        for i in range(1000):
            logger.append(_make_record(i))

        lines = log_path.read_text().splitlines()
        assert len(lines) == 1000, f"expected 1000, got {len(lines)}"

        # Simulate rotation
        rotated = Path(d) / "audit.jsonl.20260602"
        log_path.rename(rotated)
        logger.reopen()

        logger.append(_make_record(1001, ns="post-rotation"))

        assert rotated.exists()
        assert len(rotated.read_text().splitlines()) == 1000
        assert len(log_path.read_text().splitlines()) == 1


def test_write_failure_emits_to_stderr(capsys):
    """AC-18-2: write failure emits to stderr, does NOT raise."""
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))
        # Close the fd to force an OSError on next write
        os.close(logger._fd)
        logger._fd = -1  # invalid fd
        logger.append({"test": "should_not_raise"})
        captured = capsys.readouterr()
        assert captured.err != ""


def test_log_action_valid_verbs():
    """All eight action verbs accepted without ValueError."""
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))
        for verb in VALID_ACTIONS:
            logger.log_action(
                actor="remediator/sa-test",
                action=verb,
                target={"kind": "Pod", "namespace": "test", "name": "p"},
                finding_id="find_0001",
                outcome="success",
                evidence_pointer="gs://ev/x.json",
            )
        lines = log_path.read_text().splitlines()
        assert len(lines) == len(VALID_ACTIONS)


def test_log_action_invalid_verb():
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))
        with pytest.raises(ValueError):
            logger.log_action(
                actor="x",
                action="explode",
                target={"kind": "Pod", "namespace": "x", "name": "p"},
                finding_id="find_1",
                outcome="success",
                evidence_pointer="gs://ev/x.json",
            )


# ---------------------------------------------------------------------------
# Finding-store tests
# ---------------------------------------------------------------------------

async def _setup_db(db_path: str):
    import aiosqlite
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.executescript(SCHEMA_SQL)
    return db


def test_dedup_50_identical_findings():
    """AC-18-5: 50 identical findings produce one row with occurrence_count=50."""
    async def _run():
        with tempfile.TemporaryDirectory() as d:
            db_path = os.path.join(d, "findings.db")
            db = await _setup_db(db_path)
            rc_hash = "aaabbbccc"
            for _ in range(50):
                await upsert_finding(
                    db,
                    ns="payments",
                    kind="Deployment",
                    name="checkout-api",
                    severity="high",
                    root_cause_hash=rc_hash,
                )
            async with db.execute(
                "SELECT occurrence_count FROM findings WHERE root_cause_hash = ?",
                (rc_hash,),
            ) as cur:
                row = await cur.fetchone()
            assert row is not None, "finding not persisted"
            assert row[0] == 50, f"expected 50 occurrences, got {row[0]}"
            async with db.execute("SELECT COUNT(*) FROM findings") as cur:
                count = (await cur.fetchone())[0]
            assert count == 1, f"dedup failed: {count} rows found"
            await db.close()

    asyncio.run(_run())


def test_different_findings_are_separate_rows():
    async def _run():
        with tempfile.TemporaryDirectory() as d:
            db_path = os.path.join(d, "findings.db")
            db = await _setup_db(db_path)
            for i in range(5):
                await upsert_finding(
                    db,
                    ns="payments",
                    kind="Deployment",
                    name=f"svc-{i}",
                    severity="high",
                    root_cause_hash=f"hash-{i}",
                )
            async with db.execute("SELECT COUNT(*) FROM findings") as cur:
                count = (await cur.fetchone())[0]
            assert count == 5
            await db.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Query API tests
# ---------------------------------------------------------------------------

def test_query_audit_log_ns_filter():
    """AC-18-6: ns=payments returns only payments records."""
    async def _run():
        with tempfile.TemporaryDirectory() as d:
            log_path = Path(d) / "audit.jsonl"
            records = []
            for i in range(200):
                ns = "payments" if i % 2 == 0 else "infra"
                records.append(_make_record(i, ns=ns))
            log_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

            results = await query_audit_log(
                log_path=str(log_path), ns="payments", limit=500
            )
            assert len(results) == 100, f"expected 100, got {len(results)}"
            assert all(r["target"]["namespace"] == "payments" for r in results)

    asyncio.run(_run())


def test_query_audit_log_time_range():
    """since/until filter works correctly."""
    async def _run():
        with tempfile.TemporaryDirectory() as d:
            log_path = Path(d) / "audit.jsonl"
            records = []
            for i in range(200):
                ns = "payments" if i % 2 == 0 else "infra"
                records.append(_make_record(i, ns=ns))
            log_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

            results_range = await query_audit_log(
                log_path=str(log_path),
                since="2026-06-02T00:01:00.000Z",
                until="2026-06-02T00:02:00.000Z",
                limit=500,
            )
            for r in results_range:
                assert r["timestamp"] >= "2026-06-02T00:01:00.000Z"
                assert r["timestamp"] <= "2026-06-02T00:02:00.000Z"

    asyncio.run(_run())


def test_query_requires_at_least_one_filter():
    async def _run():
        with tempfile.TemporaryDirectory() as d:
            log_path = Path(d) / "audit.jsonl"
            log_path.write_text("")
            with pytest.raises(ValueError, match="At least one filter"):
                await query_audit_log(log_path=str(log_path))

    asyncio.run(_run())


def test_query_limit_max_500():
    async def _run():
        with tempfile.TemporaryDirectory() as d:
            log_path = Path(d) / "audit.jsonl"
            log_path.write_text("")
            with pytest.raises(ValueError, match="500"):
                await query_audit_log(log_path=str(log_path), ns="x", limit=501)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Root-cause hash tests
# ---------------------------------------------------------------------------

def test_root_cause_hash_normalizes_uuid():
    msg1 = "pod 3fa85f64-5717-4562-b3fc-2c963f66afa6 crashed"
    msg2 = "pod a1b2c3d4-0000-0000-0000-000000000001 crashed"
    assert root_cause_hash(msg1) == root_cause_hash(msg2)


def test_root_cause_hash_normalizes_ip():
    assert root_cause_hash("connect 10.0.0.1 failed") == root_cause_hash("connect 192.168.1.100 failed")


def test_root_cause_hash_normalizes_timestamp():
    a = "error at 2026-06-01T12:00:00 in pod"
    b = "error at 2026-07-04T08:30:00 in pod"
    assert root_cause_hash(a) == root_cause_hash(b)


def test_root_cause_hash_different_messages():
    assert root_cause_hash("oom killed") != root_cause_hash("crash loop backoff")
