#!/usr/bin/env python3
"""Mark a task done after the deliverables landed."""
import sqlite3, sys, time, pathlib
DB = pathlib.Path(__file__).resolve().parent.parent / 'docs/audit-run-001/worklist.db'
task_id = int(sys.argv[1]); pr_draft = sys.argv[2] if len(sys.argv) > 2 else None
con = sqlite3.connect(DB, isolation_level=None, timeout=10)
con.execute("PRAGMA journal_mode=WAL")
con.execute("BEGIN IMMEDIATE")
con.execute("UPDATE tasks SET status='done', completed_at=?, pr_draft_path=? WHERE id=? AND status IN ('claimed','in_progress')",
            (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), pr_draft, task_id))
con.execute("COMMIT")
print(f"task {task_id} marked done")
