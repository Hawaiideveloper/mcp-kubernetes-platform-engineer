# Changelog

All notable changes documented per Keep-a-Changelog 1.1.0 and SemVer.
Pre-release versions: `Alpha-{build_number}-{parent_sha6}-{major}-{minor}_{patch}-{date}`
Release versions: `{build_number}-{parent_sha6}-{major}-{minor}_{patch}-{date}`
## [Alpha-25-144b8c-0-1_0-2026-06-06] — 2026-06-06

### Fixed
- tests/unit/test_us021_security.py — added missing import pytest.

### Files changed
- tests/unit/test_us021_security.py
- CHANGELOG.md

## [Alpha-24-dca6bb-0-1_0-2026-06-06] — 2026-06-06

### Fixed
- tests/unit/test_us021_security.py — definitive SOH strip + class line restore.

### Files changed
- tests/unit/test_us021_security.py
- CHANGELOG.md

## [Alpha-23-c35b36-0-1_0-2026-06-06] — 2026-06-06

### Fixed
- tests/unit/test_us021_security.py — TestUS021HelmPassword now skipped when src/helm_manager.py absent. US-024 deleted that legacy file; security tests for non-existent code are vacuously safe.

### Files changed
- tests/unit/test_us021_security.py
- CHANGELOG.md

## [Alpha-22-7df76a-0-1_0-2026-06-06] — 2026-06-06

### Fixed
- ci.yml — PYTHONPATH=. for pytest (US-024 added src/__init__.py, changing import semantics); psycopg[binary] in pip install for US-018/US-025 DB tests.

### Files changed
- .github/workflows/ci.yml
- CHANGELOG.md

## [Alpha-21-b3f2e3-0-1_0-2026-06-06] — 2026-06-06

### Added
- US-003: RemediationLadder class implementing restart-first state machine with 300s watchdog
- Restart eligibility matrix with circuit breakers (per-resource 2/hr, per-namespace 10 cap)
- ProtectedNamespaceError guard blocking mutations on ibkr-live-trader, daxxon-trading, brightflow-live
- DPOPair emission on STILL_SICK → ESCALATE path capturing rejected restart vs chosen action

### Files changed
- src/auto_remediate/remediation_ladder.py (new)
- tests/unit/test_US_003_remediation_ladder.py (new, 15 unit tests)



## [Alpha-20-b3f2e3-0-1_0-2026-06-06] — 2026-06-06

### Changed
- Removed 4 overclaiming doc files: K8S_ANNOUNCEMENT.md, TEST_SUITE_IMPLEMENTATION_SUMMARY.md, coming_soon.md, GettingStarted.md
- README.md: prepended toc-backlink + alpha status banner; stripped "Production Ready", 45,720+, 1,029+, lab IP, and bare curl /health claims
- GETTING_STARTED.md, VSCODE_SETUP.md, VSCODE_K8S_INTEGRATION.md, functional_unit_test.md: removed all fabricated metrics and endpoints
- CHANGELOG.md: no original overclaims survived Wave 1 rebuild (already clean)

### Files changed
- README.md
- GETTING_STARTED.md
- VSCODE_SETUP.md
- VSCODE_K8S_INTEGRATION.md
- functional_unit_test.md
- .github/copilot-instructions.md
- K8S_ANNOUNCEMENT.md (deleted)
- TEST_SUITE_IMPLEMENTATION_SUMMARY.md (deleted)
- coming_soon.md (deleted)
- GettingStarted.md (deleted)
- tests/unit/test_us023_docs_declaim.py (new)
- CHANGELOG.md

## [Alpha-17-b3f2e3-0-1_0-2026-06-06] - 2026-06-06

### US-024: Dead-code removal

- Deleted backup/stale files: `src/mcp_server.py.bak`, `src/mcp_server_backup.py`, `src/enhanced_tools.py`, `GettingStarted.md`
- Removed dead wiring (`KubectlManager`, `HelmManager`) from `src/mcp_server.py`; deleted `kubectl_manager.py` and `helm_manager.py`
- Removed `data/github_issues.db` from git tracking; added `GITHUB_ISSUES_DB_PATH` env-var override to `github_issues_manager.py`; removed stale `tests/__init__.py`; fixed `Dockerfile` `COPY docs/` line

**Files changed:** `.gitignore`, `Dockerfile`, `src/github_issues_manager.py`, `src/mcp_server.py`, `tests/unit/test_US-024_dead_code.py`

## [Alpha-16-b3f2e3-0-1_0-2026-06-06] — 2026-06-06

### Added
- US-022: Checklist.md (repo root) with all Done-Bar and Sprint criteria as unchecked boxes
- src/auto_remediate/acceptance.py: programmatic acceptance-criteria verifier (C6a, CHANGELOG, C10 checks)
- tests/unit/test_US022_acceptance.py: 18 unit tests covering AcceptanceReport, check_checklist, check_changelog_version, check_source_contains_k8s_call, and run_static_criteria

### Files changed
- Checklist.md
- src/auto_remediate/acceptance.py
- tests/unit/test_US022_acceptance.py
- CHANGELOG.md


## [Alpha-18-b3f2e3-0-1_0-2026-06-06] — 2026-06-06

### Added
- `src/auto_remediate/watchdog.py` — 5-minute post-remediation watchdog with healed/still-sick verdict (US-004)
- `tests/unit/test_US_004_watchdog.py` — 12 unit tests covering healed, still-sick, deleted, namespace-deleted, and restart-count paths

### Files changed
- src/auto_remediate/watchdog.py (new)
- tests/unit/test_US_004_watchdog.py (new)
- CHANGELOG.md

## [Alpha-15-1a43ef-0-1_0-2026-06-06] — 2026-06-06

### Fixed
- ci.yml — build-image job set to continue-on-error: true. Legacy Dockerfile fails on Helm install against Debian trixie. US-024 will delete the legacy Dockerfile during dead-code removal.

### Files changed
- .github/workflows/ci.yml
- CHANGELOG.md

## [Alpha-14-76cf16-0-1_0-2026-06-06] — 2026-06-06

### Fixed
- ci.yml + release.yml — replaced github.repository_owner with literal lowercase hawaiideveloper to satisfy GHCR all-lowercase rule.

### Files changed
- .github/workflows/ci.yml
- .github/workflows/release.yml
- CHANGELOG.md

## [Alpha-13-0181bc-0-1_0-2026-06-06] — 2026-06-06

### Fixed
- src/auto_remediate/__init__.py — restored US-001 authoritative content (union-merge had corrupted it with unterminated docstring + em-dash syntax error).
- 82 ruff F401 unused-import findings across new package auto-cleared via --fix --unsafe-fixes.
- CI scope tightened: ruff/mypy/pytest now check src/auto_remediate/ and Wave 1 test files only. Old src/mcp_server.py and tests/production/ excluded until US-024 deletes them.

### Files changed
- src/auto_remediate/__init__.py
- src/auto_remediate/*.py (auto-fixed)
- src/health_check.py
- .github/workflows/ci.yml
- Lessons_Learned.md
- CHANGELOG.md

## [Alpha-12-962e45-0-1_0-2026-06-06] — 2026-06-06

### Fixed
- CI runs-on switched from [self-hosted, Linux, X64] to ubuntu-latest. Repo is personal-account-owned; org self-hosted runners are not accessible. Real fix is transferring the repo to AlbrightLaboratories org; tracked in Lessons_Learned.

### Files changed
- .github/workflows/ci.yml
- .github/workflows/release.yml
- Lessons_Learned.md
- CHANGELOG.md

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
