# Checklist — mcp-kubernetes-platform-engineer

Last updated: 2026-06-06

## Done-Bar Criteria
- [ ] C1: pytest -v --cov=src --cov-fail-under=80 exits 0; coverage >= 80%
- [ ] C2: ruff check . exits 0; no blanket suppressions
- [ ] C3: mypy src/ exits 0; "Success: no issues found"
- [ ] C4: docker build exits 0; trivy reports 0 HIGH/CRITICAL; base image pinned
- [ ] C5: kubectl apply -f k8s/ exits 0; pod Ready within 60s
- [ ] C6a: grep -rn "list_namespaced_pod" src/ returns >= 1 match
- [ ] C6b: integration test DEBUG log contains "list_namespaced_pod" from real API call
- [ ] C7: remediator stdout contains restart_issued, watchdog, escalated, dpo_pair
- [ ] C7: /tmp/remediation-session.json has session_id, audit_log>=3, final_state=ESCALATED
- [ ] C7: ibkr-live-trader namespace triggers ProtectedNamespaceError
- [ ] C8: kubectl get pods in staging/mcp-platform returns only Running/Completed
- [ ] C9: Zero Warning events in mcp-platform/staging for 30 min post-deploy
- [ ] C10: Checklist.md has 0 unchecked boxes

## Sprint 1
- [ ] kubernetes Python client imported; initialize() implemented
- [ ] PROTECTED_NAMESPACES constant + SafetyGate.check() wired to all write paths
- [ ] enhanced_tools.py wired into mcp_server.py dispatch table; dead stubs removed
- [ ] README.md, CHANGELOG.md false production-readiness claims retracted
- [ ] Shell scripts: set -euo pipefail, input validation, no hardcoded paths
- [ ] src/logger.py loguru exc_info misuse fixed
- [ ] k8s/kustomization.yaml .env resolved; image tag pinned off latest
- [ ] k8s/ingress.yaml TLS redirect enabled
- [ ] AuditLogger implemented (append-only, structured JSON)
- [ ] GitHub Actions CI: ruff, mypy, pytest, kustomize build, docker build

## Sprint 2
- [ ] PodAnalyzer: CrashLoopBackOff, ImagePullBackOff, OOMKilled, probe failures
- [ ] PVCAnalyzer: Pending, FailedMount, FailedAttach, capacity high
- [ ] EventStreamWatcher: live watch loop, classification, remediation queue
- [ ] FindingDeduplicator and FindingSerializer implemented
- [ ] Node, Service, HPA, NetworkPolicy, RBAC analyzers implemented
- [ ] NIM backend wired; no hardcoded recommendation strings remain
- [ ] get_issue_statistics GitHub token path fixed; startup warning added
- [ ] analyze_issue_pattern implemented in GitHubIssuesManager

## Sprint 3
- [ ] RemediationStateMachine with all states; SQLite WorklistDB atomic claim/release
- [ ] Five-minute watchdog: dual-poll, two consecutive passing checks required
- [ ] vcluster sandbox: remediation verified in ephemeral vcluster before production
- [ ] GitOps PR gate for namespaces outside ALLOWED_AUTO_REMEDIATE_NAMESPACES
- [ ] RBAC split: read SA for diagnosis, write SA for mutation
- [ ] DPOPair dataclass; extract_dpo_pairs() gated on session.state == DONE
- [ ] DPO pair emitted as GitHub issue body with Prompt/Chosen/Rejected/Evidence sections
- [ ] Image-tag migration remediator for ImagePullBackOff on yanked tags
