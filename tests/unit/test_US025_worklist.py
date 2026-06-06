"""Unit tests for US-025: WorklistDB atomic claim + iteration state machine."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from worklist import MAX_ITERATIONS, WorklistDB, should_escalate
from worklist_seed import CANONICAL_TASKS, topological_sort


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> WorklistDB:
    return WorklistDB(tmp_path / "test.db")


@pytest.fixture
def seeded_db(db: WorklistDB) -> WorklistDB:
    """DB with tasks 1 and 2 inserted; task 2 blocks on task 1."""
    db.seed(
        [
            {
                "prd_section": "09",
                "title": "Task one",
                "blockers": [],
                "deliverable_paths": [],
            },
            {
                "prd_section": "09",
                "title": "Task two",
                "blockers": [1],
                "deliverable_paths": [],
            },
        ]
    )
    return db


# ---------------------------------------------------------------------------
# Task tests
# ---------------------------------------------------------------------------


class TestClaimAtomicity:
    def test_ten_threads_no_duplicates(self, db: WorklistDB) -> None:
        """10 threads claim simultaneously; each task id appears at most once."""
        tasks = [
            {
                "prd_section": "T",
                "title": f"task-{i}",
                "blockers": [],
                "deliverable_paths": [],
            }
            for i in range(10)
        ]
        db.seed(tasks)

        results: list[int] = []
        lock = threading.Lock()
        errors: list[Exception] = []

        def worker(agent_no: int) -> None:
            try:
                task = db.claim_next(f"agent-{agent_no}")
                if task is not None:
                    with lock:
                        results.append(task.id)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Unexpected errors: {errors}"
        assert len(results) == len(set(results)), "Duplicate task ids claimed!"

    def test_blocked_task_not_claimed(self, seeded_db: WorklistDB) -> None:
        """claim_next returns task 1, not task 2 (which is blocked)."""
        task = seeded_db.claim_next("agent-a")
        assert task is not None
        assert task.id == 1, f"Expected task 1, got {task.id}"

    def test_blocker_done_unblocks(self, seeded_db: WorklistDB) -> None:
        """After task 1 is done, claim_next returns task 2."""
        seeded_db.claim_next("agent-a")  # claim task 1
        seeded_db.complete(1, "agent-a", "http://example.com/pr/1")
        task = seeded_db.claim_next("agent-b")
        assert task is not None
        assert task.id == 2

    def test_no_tasks_returns_none(self, db: WorklistDB) -> None:
        """Empty worklist returns None immediately."""
        assert db.claim_next("agent-x") is None

    def test_seed_idempotent(self, db: WorklistDB) -> None:
        """Seeding the same tasks twice does not create duplicates."""
        payload = [
            {
                "prd_section": "X",
                "title": "Dup task",
                "blockers": [],
                "deliverable_paths": [],
            }
        ]
        db.seed(payload)
        db.seed(payload)
        counts = db.count_by_status()
        assert counts.get("queued", 0) == 1

    def test_mark_in_progress(self, seeded_db: WorklistDB) -> None:
        task = seeded_db.claim_next("agent-a")
        assert task is not None
        seeded_db.mark_in_progress(task.id, "agent-a")
        counts = seeded_db.count_by_status()
        assert counts.get("in_progress", 0) == 1

    def test_fail_sets_status(self, seeded_db: WorklistDB) -> None:
        task = seeded_db.claim_next("agent-a")
        assert task is not None
        seeded_db.fail(task.id, "agent-a", "test failure")
        counts = seeded_db.count_by_status()
        assert counts.get("failed", 0) == 1


# ---------------------------------------------------------------------------
# Audit-run state machine tests
# ---------------------------------------------------------------------------


class TestIterationStateMachine:
    def test_ensure_creates_run(self, db: WorklistDB) -> None:
        run = db.ensure_audit_run("audit-run-001")
        assert run.run_label == "audit-run-001"
        assert run.phase == "review"
        assert run.iteration_count == 0

    def test_ensure_idempotent(self, db: WorklistDB) -> None:
        db.ensure_audit_run("audit-run-001")
        run = db.ensure_audit_run("audit-run-001")
        assert run.iteration_count == 0

    def test_advance_phase(self, db: WorklistDB) -> None:
        db.ensure_audit_run("audit-run-001")
        run = db.advance_phase("audit-run-001", "synthesize")
        assert run.phase == "synthesize"

    def test_increment_iteration_resets_phase(self, db: WorklistDB) -> None:
        db.ensure_audit_run("audit-run-001")
        db.advance_phase("audit-run-001", "verify")
        run = db.increment_iteration("audit-run-001")
        assert run.iteration_count == 1
        assert run.phase == "review"

    def test_escalate_on_max_iterations(self, db: WorklistDB) -> None:
        db.ensure_audit_run("audit-run-001")
        run = None
        for _ in range(MAX_ITERATIONS):
            run = db.increment_iteration("audit-run-001")
        assert run is not None
        assert run.phase == "escalate"
        assert run.stopped_reason is not None

    def test_should_escalate(self) -> None:
        assert should_escalate(MAX_ITERATIONS) is True
        assert should_escalate(MAX_ITERATIONS - 1) is False
        assert should_escalate(0) is False


# ---------------------------------------------------------------------------
# Topological sort tests
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    def test_cycle_raises(self) -> None:
        tasks = [
            {"id": 1, "prd_section": "A", "title": "A", "blockers": [2]},
            {"id": 2, "prd_section": "B", "title": "B", "blockers": [1]},
        ]
        with pytest.raises(ValueError, match="cycle"):
            topological_sort(tasks)

    def test_linear_chain_order(self) -> None:
        tasks = [
            {"id": 3, "prd_section": "C", "title": "C", "blockers": [2]},
            {"id": 1, "prd_section": "A", "title": "A", "blockers": []},
            {"id": 2, "prd_section": "B", "title": "B", "blockers": [1]},
        ]
        ordered = topological_sort(tasks)
        ids = [t["id"] for t in ordered]
        assert ids.index(1) < ids.index(2)
        assert ids.index(2) < ids.index(3)

    def test_no_edges_stable_by_id(self) -> None:
        tasks = [
            {"id": 3, "prd_section": "C", "title": "C", "blockers": []},
            {"id": 1, "prd_section": "A", "title": "A", "blockers": []},
            {"id": 2, "prd_section": "B", "title": "B", "blockers": []},
        ]
        ordered = topological_sort(tasks)
        assert [t["id"] for t in ordered] == [1, 2, 3]

    def test_canonical_tasks_no_cycle(self) -> None:
        ordered = topological_sort(CANONICAL_TASKS)
        assert len(ordered) == 25

    def test_canonical_tasks_dependency_order(self) -> None:
        ordered = topological_sort(CANONICAL_TASKS)
        id_to_pos = {t["id"]: i for i, t in enumerate(ordered)}
        for task in CANONICAL_TASKS:
            for blocker_id in task.get("blockers", []):
                assert id_to_pos[blocker_id] < id_to_pos[task["id"]], (
                    f"Task {task['id']} appears before blocker {blocker_id}"
                )
