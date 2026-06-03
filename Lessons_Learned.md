
## 2026-06-03 — Docker daemon not running on dev host

**What happened:** First Redis container boot failed — `docker run` returned `connect: no such file or directory` for `/var/run/docker.sock`. Docker.app is installed at `/Applications/Docker.app` but the daemon was not started.

**Why:** Docker Desktop on macOS is a GUI app; the daemon does not autostart on login unless explicitly configured. The host had `redis-server` available natively via Homebrew, but the spec requires a Docker container (so the same compose/manifest can move to the Kubernetes cluster verbatim).

**Fix applied:** `open -a Docker` to launch Docker Desktop, then poll `docker info` with a 5-min timeout before retrying `docker run`. If it does not come up in 5 min, fall back to logging another entry and asking the operator to start Docker manually.

**Prevent next time:** Add a `scripts/preflight.sh` that checks `docker info` and `redis-cli -p 16379 PING` before any Phase 1 work; refuse to start the agent loop if either fails.
