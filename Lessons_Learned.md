
## 2026-06-03 — Docker daemon not running on dev host

**What happened:** First Redis container boot failed — `docker run` returned `connect: no such file or directory` for `/var/run/docker.sock`. Docker.app is installed at `/Applications/Docker.app` but the daemon was not started.

**Why:** Docker Desktop on macOS is a GUI app; the daemon does not autostart on login unless explicitly configured. The host had `redis-server` available natively via Homebrew, but the spec requires a Docker container (so the same compose/manifest can move to the Kubernetes cluster verbatim).

**Fix applied:** `open -a Docker` to launch Docker Desktop, then poll `docker info` with a 5-min timeout before retrying `docker run`. If it does not come up in 5 min, fall back to logging another entry and asking the operator to start Docker manually.

**Prevent next time:** Add a `scripts/preflight.sh` that checks `docker info` and `redis-cli -p 16379 PING` before any Phase 1 work; refuse to start the agent loop if either fails.

## 2026-06-03 — Redis lost all 25 tasks on pod restart

**What happened:** Set up `corey-fl-redis` with `--save "" --appendonly no` and `emptyDir` volume, reasoning "24h TTL on keys, no persistence needed." The pod restarted ~76 min later (cause TBD, possibly OOM-bump from earlier 64Mi request). All task hashes and the `queue:pending` zset wiped. Discovered when smoke-test reported `ZCARD queue:pending = 0` and `KEYS task:US-* = (empty)`.

**Why:** "24h TTL" is about key expiry, not pod uptime. A pod restart with no persistence loses everything. Conflated two different lifetimes.

**Fix applied:** 
1. RDB snapshot policy `save 60 1` (snapshot if ≥1 write in 60s) — minimal write amplification, bounded data-loss window of 60s.
2. PVC `corey-fl-redis-data` (1Gi, local-path storage class) replacing emptyDir for `/data`.
3. Bumped memory request to 128Mi (limit still 320Mi) so the pod doesn't get killed under burst seed.

**Prevent next time:** Default to RDB + PVC for any "task queue" Redis even when keys are explicitly TTL'd. EmptyDir + no-persistence is only correct for *true* cache patterns where the consumer can recompute from source — and even then, document explicitly.
