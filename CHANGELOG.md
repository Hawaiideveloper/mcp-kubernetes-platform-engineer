# Changelog

All notable changes documented per Keep-a-Changelog 1.1.0 and SemVer.
Pre-release versions: `Alpha-{build_number}-{parent_sha6}-{major}-{minor}_{patch}-{date}`
Release versions: `{build_number}-{parent_sha6}-{major}-{minor}_{patch}-{date}`

## [Alpha-2-fb53c1-0-1_0-2026-06-04] — 2026-06-04

### Added
- `scripts/runner/claim_task.py` — atomic ZPOPMIN claim against `corey-fl-redis`; idempotent on requeued tasks.
- `scripts/runner/mark_done.py`, `mark_failed.py`, `heartbeat.py` — task lifecycle ops, used by sub-agents via `kubectl exec`.
- `infra/redis/redis.yaml` — PVC `corey-fl-redis-data` (1Gi local-path) + RDB `save 60 1` + memory request bumped to 128Mi.

### Removed
- `scripts/claim_task.py`, `scripts/mark_done.py` — SQLite-era stubs, superseded by Redis runner.
- `docs/audit-run-001/worklist.db` — SQLite worklist, superseded by Redis hashes + queue:pending zset.

### Fixed
- Redis lost all 25 tasks on first pod restart (no persistence). Documented in Lessons_Learned. RDB+PVC now in place.

### Files changed
- infra/redis/redis.yaml, Lessons_Learned.md, CHANGELOG.md, scripts/runner/*.py, scripts/claim_task.py (deleted), scripts/mark_done.py (deleted), docs/audit-run-001/worklist.db (deleted)

## [Alpha-1-ccfe7b-0-1_0-2026-06-03] — 2026-06-03

### Added
- `prd.json` — 25 userStories converted from PRD chunks per gold-prompt schema.
- `infra/redis/redis.yaml` — corey-fl-redis Deployment + Service in corey-coder ns; 256Mi LRU, no persistence, 24h TTL on keys, readOnlyRootFilesystem, non-root.
- Lessons_Learned.md — first entry on Docker daemon down + ARM/x86_64 mismatch decision.
- 25 task hashes seeded into Redis under key `task:US-*` with 86400s TTL.
- `queue:pending` sorted set scored by story priority.

### Reason
Phase 1 of the corey-fl-loop gold-prompt structure. Redis must live in-cluster
(corey-coder ns) because the dev workstation is arm64 and cluster nodes are
x86_64; local Docker is also unavailable on the host.

### Files changed
- prd.json (new)
- infra/redis/redis.yaml (new)
- Lessons_Learned.md (new)
- CHANGELOG.md (new)
