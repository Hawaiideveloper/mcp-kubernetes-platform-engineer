#!/usr/bin/env python3
"""Mark a claimed task done."""
import json, sys, time, redis, os
r = redis.Redis(host=os.environ.get("REDIS_HOST","corey-fl-redis"), port=6379, decode_responses=True)
if len(sys.argv) < 2:
    print("usage: mark_done.py <story_id> [result] [proof_ref]", file=sys.stderr); sys.exit(64)
sid = sys.argv[1]
result = sys.argv[2] if len(sys.argv) > 2 else ""
proof  = sys.argv[3] if len(sys.argv) > 3 else ""
key = f"task:{sid}"
status = r.hget(key, "status")
if status != "claimed":
    print(json.dumps({"ok": False, "reason": f"status={status!r}"})); sys.exit(3)
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
r.hset(key, mapping={"status":"done","completed_at":ts,"result":result,"patch_ref":proof})
print(json.dumps({"ok": True, "story_id": sid, "completed_at": ts}))
