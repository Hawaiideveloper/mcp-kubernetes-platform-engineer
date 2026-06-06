#!/usr/bin/env python3
"""Atomically claim the highest-priority queued task from corey-fl-redis."""
import json
import os
import sys
import time
import redis
REDIS_HOST = os.environ.get("REDIS_HOST", "corey-fl-redis")
AGENT_ID = os.environ.get("AGENT_ID", f"agent-{os.getpid()}")
r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
popped = r.zpopmin("queue:pending", 1)
if not popped:
    print(json.dumps({"claimed": False, "reason": "queue empty"})); sys.exit(2)
story_id, priority = popped[0]
key = f"task:{story_id}"
status = r.hget(key, "status")
if status not in (None, "pending", "needs_fix"):
    r.zadd("queue:pending", {story_id: priority})
    print(json.dumps({"claimed": False, "reason": f"unexpected status {status!r}, requeued"})); sys.exit(3)
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
r.hset(key, mapping={"status":"claimed","assigned_agent":AGENT_ID,"claimed_at":ts})
task = r.hgetall(key); task["priority"] = int(priority)
print(json.dumps({"claimed": True, "story_id": story_id, "agent": AGENT_ID, "task": task}, default=str))
