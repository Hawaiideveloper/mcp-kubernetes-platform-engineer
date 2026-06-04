#!/usr/bin/env python3
"""Mark a task needs_fix; requeue at slightly higher priority for critic loop."""
import json, sys, time, redis, os
r = redis.Redis(host=os.environ.get("REDIS_HOST","corey-fl-redis"), port=6379, decode_responses=True)
if len(sys.argv) < 3:
    print("usage: mark_failed.py <story_id> <error>", file=sys.stderr); sys.exit(64)
sid, err = sys.argv[1], sys.argv[2]
key = f"task:{sid}"
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
prio = float(r.hget(key, "priority") or 2)
r.hset(key, mapping={"status":"needs_fix","error_log":err,"failed_at":ts})
r.zadd("queue:pending", {sid: max(0.0, prio - 0.5)})
print(json.dumps({"ok": True, "story_id": sid, "requeued_at": prio - 0.5}))
