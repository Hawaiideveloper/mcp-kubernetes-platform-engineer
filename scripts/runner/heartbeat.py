#!/usr/bin/env python3
import sys
import time
import redis
import os
r = redis.Redis(host=os.environ.get("REDIS_HOST","corey-fl-redis"), port=6379, decode_responses=True)
sid = sys.argv[1]; note = sys.argv[2] if len(sys.argv) > 2 else ""
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
r.hset(f"task:{sid}", mapping={"heartbeat_at": ts, "progress_note": note})
print(f"hb {sid} {ts}")
