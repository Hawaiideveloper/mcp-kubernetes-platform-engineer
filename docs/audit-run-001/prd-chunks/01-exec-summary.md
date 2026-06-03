# PRD Section 01 — Executive Summary and Roadmap

## TL;DR

`mcp-kubernetes-platform-engineer` is intended to become an auto-remediating Kubernetes platform
engineer: a system that watches the live cluster event stream, classifies failures, executes a
deterministic restart-first escalation ladder, verifies healing in a vcluster sandbox before
applying to production namespaces, proposes changes for GitOps-gated namespaces via GitHub PR, and
feeds every healed session back into a DPO learning loop so the NIM-backed model improves with
each incident. Today it is none of those things. An audit of 48 review agents across all source
components produced 480 confirmed defects — 117 critical, 215 high, 116 medium, 10 low, 22 info —
spanning every layer of the stack: 129 behavior gaps (nothing is implemented), 79 MCP tool stubs
that return hardcoded strings instead of real API responses, 54 enhanced-tool schemas that are
dead code never wired into the server, 73 Python defects including the absence of any
`kubernetes` client import, 45 shell-script failures, 43 false documentation claims, 38 broken
Kubernetes manifests, and 19 vacuous tests that mock the very methods they claim to exercise. The
README and CHANGELOG assert "Production Ready," a 390-test suite, live cluster IP readiness, and
45,720+ indexed GitHub issues; every one of those claims is directly contradicted by stub-only
manager code. Closing this gap requires three focused sprints and a commitment to not marking any
story DONE until it is deployed and verified in production.

---

## Why This Matters

- **The k8sgpt gap.** k8sgpt ships approximately 20 analyzers (pod, node, service, ingress, PVC,
  HPA, event, deployment, replicaset, statefulset, daemonset, cronjob, networkpolicy, pdb,
  configmap, secret, rbac, gateway, certificate, and resource-quota checks) backed by a real
  `client-go` Kubernetes client. This repo currently ships zero working analyzers. Until Sprint 2
  reaches analyzer parity, `mcp-kubernetes-platform-engineer` cannot replace or complement
  k8sgpt for any production use case. The differentiating bet — sandbox-verified, GitOps-gated,
  DPO-learning remediation — only matters once the diagnostic foundation is solid.

- **The cluster events that triggered this work.** The Albright Laboratories GPU cluster and the
  trading namespaces (`ibkr-live-trader`, `daxxon-trading`, `brightflow-live`) have experienced
  incidents where auto-remediation tooling with no namespace guard could cause financial or
  infrastructure harm. The 117 critical findings include two independent reports of a missing
  trading-namespace hardblock (§10), meaning any caller can today pass those namespace names to
  `execute_remediation` without restriction. A real Kubernetes client that can actually call the
  API combined with that missing guard is a live risk that must be closed in Sprint 1 before any
  real client integration goes in.

- **The corey-coder DPO learning loop.** The longer-term value of this system is its ability to
  produce DPO training pairs from resolved remediation sessions — chosen actions (those that
  healed the cluster) versus rejected alternatives — and emit them as structured GitHub issue
  bodies for nightly model fine-tuning. That loop is entirely unimplemented (finding
  `behavior:dpo_pair_extraction`): no `DPOPair` datatype, no extraction logic, no emission path.
  Sprint 3 closes this gap and connects the remediator output to the corey-coder nightly audit
  cycle.

---

## Roadmap

### Sprint 1 — Gut and Rebuild (weeks 1–2)

Goal: replace all stubs with a real Kubernetes client, remove dead code, retract false claims, and
establish a green CI baseline.

| Work item | Finding references |
|---|---|
| Add `kubernetes` Python client; implement `initialize()` with in-cluster / kubeconfig loading | `mcp-tool:execute_remediation`, `mcp-tool:get_recommendations`, `mcp-tool:diagnose_cluster_health`, `mcp-tool:performance_analysis` |
| Trading-namespace hardblock: `TRADING_BLOCKED_NAMESPACES` constant, `check_namespace_allowed()`, `ProtectedNamespaceError` | `behavior:trading_ns_hardblock` (two independent findings) |
| Wire `enhanced_tools.py` into `mcp_server.py`; remove dead-code stubs | `src/enhanced_tools.py` (two critical findings), `enhanced:kubectl_rollout`, `enhanced:helm_install`, `enhanced:helm_upgrade`, `enhanced:helm_status`, `enhanced:kubectl_delete` |
| Rewrite `README.md`, `CHANGELOG.md`, `GETTING_STARTED.md`, `GettingStarted.md`, `functional_unit_test.md`, `coming_soon.md` to remove all false production-readiness claims | `README.md`, `CHANGELOG.md`, `GETTING_STARTED.md`, `GettingStarted.md`, `functional_unit_test.md`, `coming_soon.md` |
| Fix all shell scripts: `set -euo pipefail`, remove hardcoded paths, add input validation | `setup-vscode-k8s.sh` (two findings), `setup-vscode-nodeport.sh` (two findings), `push-and-deploy.sh` (two findings), `logs.sh`, `stop.sh`, `security-scan-demo.sh`, `mcp-port-forward.sh` |
| Fix `src/logger.py` loguru `exc_info` misuse (stack traces silently swallowed) | `src/logger.py` |
| Fix `k8s/kustomization.yaml` missing `.env` files; pin image tag off `latest` | `k8s/kustomization.yaml` |
| Fix `k8s/ingress.yaml`: enable TLS redirect, remove stdio-only port routing | `k8s/ingress.yaml` |
| Implement structured append-only `AuditLogger` | `behavior:audit_log` |
| Set up GitHub Actions CI: lint (ruff/shellcheck), pytest with mocked k8s client, `kustomize build` dry-run, image build | (no existing CI; Sprint 1 establishes baseline) |

Sprint 1 exit criterion: `pytest` green on mocked-client unit tests, `kustomize build k8s/`
succeeds on a clean clone, image builds and pushes to GHCR, no source file contains the string
`stub implementation`.

---

### Sprint 2 — Analyzer Parity (weeks 3–5)

Goal: implement the ~20 k8sgpt-equivalent analyzers using the real Kubernetes client wired in
Sprint 1, backed by the NIM inference backend for AI-assisted root-cause summary.

| Analyzer | Finding reference |
|---|---|
| `PodAnalyzer` — CrashLoopBackOff, ImagePullBackOff, OOMKilled, probe failures | `behavior:analyzer_pod` |
| `PVCAnalyzer` — Pending (no PV/StorageClass), FailedMount/FailedAttach, capacity high | `behavior:analyzer_pvc` |
| `EventStreamWatcher` — live watch loop, classification rules, remediation queue routing | `behavior:event_stream_watcher` (two findings) |
| `FindingDeduplicator` — collapse identical root-cause findings across N resources | `behavior:finding_dedup` |
| `FindingSerializer` — canonical `Finding` dataclass, `FindingStore`, DPO-pair export contract | `behavior:finding_serialization` |
| Node analyzer, Service analyzer, HPA analyzer, NetworkPolicy analyzer, RBAC analyzer | (Sprint 2 scope; correspond to k8sgpt analyzer list) |
| NIM backend integration: replace hardcoded recommendation strings with NIM-generated summaries | `mcp-tool:get_recommendations`, `mcp-tool:get_best_practices` |
| Fix `get_issue_statistics` GitHub token path; add `GITHUB_TOKEN` startup warning | `mcp-tool:get_issue_statistics` |
| Implement `analyze_issue_pattern` in `GitHubIssuesManager`; remove vacuous mocks from tests | `functional_unit_test.md` |

Sprint 2 exit criterion: `kubectl get pods -A | grep -v Running` is empty in a staging cluster
after running the analyzer suite against deliberately-injected failures (one CrashLoopBackOff, one
ImagePullBackOff, one Pending PVC) and the remediator resolves all three within 30 minutes.

---

### Sprint 3 — Differentiators (weeks 6–8)

Goal: implement the capabilities that go beyond k8sgpt and make this system the production
auto-remediator for the Albright Laboratories cluster fleet.

| Work item | Finding reference |
|---|---|
| `RemediationStateMachine` — IDLE → RESTART_ISSUED → WAITING → VERIFY → ESCALATED → RESOLVED; SQLite-backed `WorklistDB` with atomic claim/release | `behavior:iteration_state_machine`, `behavior:restart_first_ladder`, `behavior:worklist_sqlite` |
| Five-minute watchdog: dual-poll readiness + zero-warning-event gate; `healed` requires two consecutive passing polls | `behavior:five_min_watchdog` |
| vcluster sandbox: run remediation in an ephemeral vcluster before applying to the target namespace | (Sprint 3 design task; referenced in PRD framing) |
| GitOps PR gate: for namespaces not in `ALLOWED_AUTO_REMEDIATE_NAMESPACES`, serialize the patch as a GitHub PR instead of applying directly | `behavior:safety_allowlist` |
| RBAC split: read `ServiceAccount` for all diagnostic tools; write `ServiceAccount` for remediation; `ProtectedNamespaceError` for trading namespaces | `behavior:rbac_split` |
| DPO pair extraction: `DPOPair` dataclass, `extract_dpo_pairs(session)`, GitHub issue body emission, gate on `session.state == DONE` | `behavior:dpo_pair_extraction` |
| Image-tag migration remediator: detect `ImagePullBackOff` caused by yanked tags, propose concrete replacement via registry API | `behavior:image_tag_migration_remediation` |

Sprint 3 exit criterion: a live cluster event (CrashLoopBackOff injected in `staging` namespace)
triggers the full ladder, heals within 5 minutes as confirmed by the watchdog, produces a DPO
pair emitted to GitHub, and the `ibkr-live-trader` namespace returns `ProtectedNamespaceError`
when targeted by `execute_remediation`.

---

## Success Criteria Reference

Full success criteria and acceptance test specifications are defined in §22. The headline bar is:

- `pytest` green (all unit tests pass against mocked kubernetes client; no test mocks the method
  it is testing).
- Image builds and pushes to GHCR without error from a clean clone.
- Cluster events clean for 30 consecutive minutes after injecting a standard failure set (one
  CrashLoopBackOff, one ImagePullBackOff, one Pending PVC, one node taint).
- `kubectl get pods -A | grep -v Running` returns empty output in the staging cluster after the
  remediator completes its ladder.

See §3 for the full restart-first escalation ladder, §10 for the trading-namespace hardblock
specification, §15 for the vcluster sandbox protocol, §18 for the GitOps PR gate, and §21 for the
DPO extraction schema.
