#!/usr/bin/env python3
"""Atomically claim the lowest-id queued task whose blockers are all done."""
import sqlite3, sys, json, os, time, pathlib

DB = pathlib.Path(__file__).resolve().parent.parent / 'docs/audit-run-001/worklist.db'
agent_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('AGENT_ID','unknown')

con = sqlite3.connect(DB, isolation_level=None, timeout=10)
con.execute("PRAGMA journal_mode=WAL")
con.execute("BEGIN IMMEDIATE")
try:
    done_slugs = {r[0] for r in con.execute("SELECT slug FROM tasks WHERE status='done'")}
    rows = con.execute("SELECT id,slug,title,prd_section,branch,deliverable_paths,blockers FROM tasks WHERE status='queued' ORDER BY id").fetchall()
    chosen = None
    for r in rows:
        blockers = json.loads(r[6])
        if all(b in done_slugs for b in blockers):
            chosen = r; break
    if not chosen:
        con.execute("COMMIT")
        print(json.dumps({"claimed": False, "reason": "no claimable task (queue empty or all blocked)"}))
        sys.exit(2)
    con.execute("UPDATE tasks SET status='claimed', claimed_by=?, claimed_at=? WHERE id=?", (agent_id, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), chosen[0]))
    con.execute("COMMIT")
    print(json.dumps({
        "claimed": True, "id": chosen[0], "slug": chosen[1], "title": chosen[2],
        "prd_section": chosen[3], "branch": chosen[4],
        "deliverable_paths": json.loads(chosen[5]),
        "blockers": json.loads(chosen[6])
    }))
except Exception as e:
    con.execute("ROLLBACK")
    print(json.dumps({"claimed": False, "error": str(e)}))
    sys.exit(1)
