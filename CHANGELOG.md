# Changelog

All notable changes documented per Keep-a-Changelog 1.1.0 and SemVer.
Pre-release versions: `Alpha-{build_number}-{parent_sha6}-{major}-{minor}_{patch}-{date}`
Release versions: `{build_number}-{parent_sha6}-{major}-{minor}_{patch}-{date}`

## [Alpha-11-8873e1-0-1_0-2026-06-06] — 2026-06-06

### Fixed
- CI runs-on changed from albright-runners to [self-hosted, Linux, X64] so jobs actually get picked up. Org runners do not currently advertise the albright-runners label; tracked as follow-up against the arc repo.

### Files changed
- .github/workflows/ci.yml
- .github/workflows/release.yml
- Lessons_Learned.md
- CHANGELOG.md

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

## [Alpha-7-168973-0-1_0-2026-06-05] — 2026-06-05
### Added
- (US-006) SafetyGate hardblock for trading namespaces (ibkr-live-trader, daxxon-trading, brightflow-live) and fnmatch patterns (*-live, *-trading, *-trader, ibkr-*). System namespaces are also blocked; all decisions are written to an append-only audit log.
### Files
- config/safety.yaml
- src/safety_config.py
- src/audit.py
- src/safety_gate.py
- tests/test_safety_gate.py
- docs/audit-run-001/proofs/US-006/pytest-output.txt

## [Alpha-6-168973-0-1_0-2026-06-05] — 2026-06-05

### Added
- (US-001) Namespace guard module: TRADING_BLOCKED_NAMESPACES constant, ProtectedNamespaceError, and check_namespace_allowed() that blocks automated remediation against trading namespaces (ibkr-live-trader, daxxon-trading, brightflow-live).
- (US-001) AuditLogger: thread-safe, append-only JSONL audit writer with guard-rejection and remediation-action convenience methods.
- (US-001) Roadmap: three-sprint structured baseline data as code, Sprint 1 marked IN_PROGRESS with trading hardblock items done.

### Files
- src/auto_remediate/__init__.py (new)
- src/auto_remediate/namespace_guard.py (new)
- src/auto_remediate/audit_logger.py (new)
- src/auto_remediate/roadmap.py (new)
- tests/unit/test_US_001_exec_summary.py (new, 32 tests passing)
- docs/audit-run-001/proofs/US-001/pytest-output.txt (new)

## [Alpha-5-168973-0-1_0-2026-06-05] — 2026-06-05
### Added
- (US-002) AuditInventory module (src/audit_inventory.py) parses all-findings.json and exposes severity/fix-class breakdowns, component summaries, and pattern analysis over the 480 audit findings.
- (US-002) 29 unit tests (tests/unit/test_US_002_audit_inventory.py) covering fixture and real data; all pass including real-data assertions (critical=117, high=215, total=480).
### Files
- src/audit_inventory.py
- tests/unit/test_US_002_audit_inventory.py
- docs/audit-run-001/proofs/US-002/pytest-output.txt

## [Alpha-4-168973-0-1_0-2026-06-05] — 2026-06-05
### Added
- (US-019) Four-identity RBAC split: reader ClusterRole, namespaced applier Roles for brightflow-dashboard and triton-inference, sandbox Role template, and pr-bot ServiceAccount with automountServiceAccountToken=false. Trading namespaces have no applier binding.
- (US-019) rbac_identities.py, rbac_audit_logger.py, rbac_ci_check.py modules with 28 passing unit tests covering namespace classification, §18 audit record schema, pre/post-action logging contracts, degraded-session detection, and CI violation detection.
### Files
- k8s/rbac/reader-cluster-role.yaml
- k8s/rbac/reader-service-account.yaml
- k8s/rbac/reader-cluster-role-binding.yaml
- k8s/rbac/applier-role-template.yaml
- k8s/rbac/applier-service-account.yaml
- k8s/rbac/applier-role-binding-template.yaml
- k8s/rbac/applier-role-brightflow-dashboard.yaml
- k8s/rbac/applier-role-binding-brightflow-dashboard.yaml
- k8s/rbac/applier-role-triton-inference.yaml
- k8s/rbac/applier-role-binding-triton-inference.yaml
- k8s/rbac/sandbox-role-template.yaml
- k8s/rbac/sandbox-service-account.yaml
- k8s/rbac/sandbox-role-binding-template.yaml
- k8s/rbac/pr-bot-service-account.yaml
- src/auto_remediate/rbac_identities.py
- src/auto_remediate/rbac_audit_logger.py
- src/auto_remediate/rbac_ci_check.py
- tests/unit/test_US019_rbac_split.py
- docs/audit-run-001/proofs/US-019/pytest-output.txt

## [Alpha-3-168973-0-1_0-2026-06-05] — 2026-06-05
### Added
- (US-020) Added CI/CD GitHub Actions workflows using albright-runners with lint, type-check, test, build/Trivy scan, and GHCR push jobs. Deployment image pinned to digest, imagePullPolicy set to IfNotPresent, pre-commit hooks configured, and Dependabot enabled for pip and GitHub Actions.
### Files
- .github/workflows/ci.yml
- .github/workflows/release.yml
- .github/dependabot.yml
- .pre-commit-config.yaml
- k8s/deployment.yaml (image digest pin + pull policy)
- tests/test_US_020_cicd.py
- docs/audit-run-001/proofs/US-020/test-output.txt

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
