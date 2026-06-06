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

## [Alpha-8-168973-0-1_0-2026-06-05] — 2026-06-05
### Added
- (US-021) Applied 8 concrete security patches: SQL injection fix (parameterized queries in github_issues_manager), GITHUB_TOKEN moved to env-file in start.sh, empty secret placeholder removed from k8s/secret.yaml, hardcoded private IP replaced in docs, NetworkPolicy default-deny + allow-ingress-nginx created, setup-vscode-k8s.sh hardcoded path fixed, update.sh error handling hardened, and loguru logger exc_info replaced with opt(exception=).
- (US-021) Kubernetes manifest hardening: readOnlyRootFilesystem=true, seccompProfile RuntimeDefault, KUBECONFIG dir-path env removed, PSA baseline/restricted labels on namespace, helm password passed via --password-stdin.
### Files
- src/github_issues_manager.py
- src/logger.py
- src/helm_manager.py
- k8s/secret.yaml
- k8s/namespace.yaml
- k8s/deployment.yaml
- k8s/networkpolicy.yaml (new)
- VSCODE_K8S_INTEGRATION.md
- README.md
- setup-vscode-k8s.sh
- start.sh
- update.sh
- tests/unit/test_us021_security.py (new)

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
