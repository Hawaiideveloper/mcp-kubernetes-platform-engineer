
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

## 2026-06-06 — Org runners do not advertise an albright-runners label

**What happened:** US-020 CI/CD workflows used `runs-on: albright-runners` per the org CLAUDE.md convention. After opening Wave 1 integration PR #3, all three checks (Lint, Type-check, Test) sat in `queued` for 5+ minutes. `gh api /orgs/AlbrightLaboratories/actions/runners` showed 7+ online runners (`albright-runners-cg7p2-*` runner set), but every one had `labels=` empty — only the implicit `self-hosted`, `Linux`, `X64` labels were advertised. Job runner_name stayed null because no runner matched the requested label.

**Why:** The ARC runner-set name (`albright-runners-cg7p2`) is a Kubernetes resource name, not an Actions Runner label. Labels must be added explicitly via the ARC RunnerSet spec (`spec.template.spec.labels: [albright-runners]`) or at runner registration time.

**Fix applied here (workaround):** Patched both CI workflows to `runs-on: [self-hosted, Linux, X64]` so they match the implicit labels every org runner already advertises. This unblocks Wave 1.

**Real fix (follow-up):** Open a PR against the `arc` repo to add `albright-runners` to the RunnerSet labels, then revert these workflows back to `runs-on: albright-runners` per org convention.

## 2026-06-06 — Personal-account repo cannot use org self-hosted runners

**What happened:** Patched workflows from `runs-on: albright-runners` to `runs-on: [self-hosted, Linux, X64]` to match implicit org-runner labels. PR #3 checks still stayed queued 5+ minutes. Investigation: the repo is owned by user `Hawaiideveloper`, not the `AlbrightLaboratories` org. Org-level runners (in runner group \"Default\", visibility=all) only run jobs for org repos. The repo has no user-level self-hosted runners (`gh api /repos/.../actions/runners` returns empty).

**Why:** GitHub Actions self-hosted runner scoping: org runners require the workflow repo to be inside the org. Personal-account repos must add runners at the user or repo level.

**Fix applied (workaround):** Patched both workflows to `runs-on: ubuntu-latest`. GitHub-hosted runners are free for public repos and run immediately.

**Real fix (follow-up):** Transfer `mcp-kubernetes-platform-engineer` to the `AlbrightLaboratories` org (matches the convention of every other repo + lets org runners + the Master TOC auto-updater + the claude-md-sweep workflows all apply automatically). Once transferred, revert workflows back to `runs-on: albright-runners` and complete the arc-RunnerSet label follow-up from the previous lesson.
