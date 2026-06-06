# Changelog

All notable changes documented per Keep-a-Changelog 1.1.0 and SemVer.
Pre-release versions: `Alpha-{build_number}-{parent_sha6}-{major}-{minor}_{patch}-{date}`
Release versions: `{build_number}-{parent_sha6}-{major}-{minor}_{patch}-{date}`

## [Alpha-10-aaf4e4-0-1_0-2026-06-06] — 2026-06-06

### Added
- the_goal-inprogress.md §9 Resume runbook: pod-discovery one-liners, health check, re-seed procedure, 19-task table, verbatim sub-agent prompt template for Waves 2-5, CHANGELOG insertion algorithm, batch-PR command, full-rebuild procedure, post-restart recovery, critic-loop notes, session-close checklist.

### Reason
Make the_goal-inprogress.md self-sufficient for cold resume after session close.

### Files changed
- the_goal-inprogress.md (append §9)
- CHANGELOG.md

## [Alpha-9-168973-0-1_0-2026-06-05] — 2026-06-05

### Added
- the_goal-inprogress.md — comprehensive narrative of the corey-fl-loop initiative: goal, big picture, what is built (Phase A audit, Phase C PRD, Phase 1 Redis, Phase 2 setup + Wave 1), where things live, lessons learned, what is left (Waves 2-5, validators, critic, hour-11 flush, LoRA, runtime deploy), acceptance criteria, and resume instructions.

### Reason
Pause point — capture the full picture so any future session can pick up cold.

### Files changed
- the_goal-inprogress.md (new)
- CHANGELOG.md

## [Alpha-5-168973-0-1_0-2026-06-05] — 2026-06-05
### Added
- (US-002) AuditInventory module (src/audit_inventory.py) parses all-findings.json and exposes severity/fix-class breakdowns, component summaries, and pattern analysis over the 480 audit findings.
- (US-002) 29 unit tests (tests/unit/test_US_002_audit_inventory.py) covering fixture and real data; all pass including real-data assertions (critical=117, high=215, total=480).
### Files
- src/audit_inventory.py
- tests/unit/test_US_002_audit_inventory.py
- docs/audit-run-001/proofs/US-002/pytest-output.txt

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
