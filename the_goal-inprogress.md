# the_goal — in progress

A complete write-up of what this initiative is, what we have built, where we are right now, and what is left. Comprehensive on purpose. Nothing about author identity — work is authored by the user under the user's git config.

---

## 1. The goal

Convert `mcp-kubernetes-platform-engineer` from a hollow MCP scaffold into an **autonomous, self-improving Kubernetes auto-remediator** that meaningfully outperforms `k8sgpt` on the whole remediation loop, not just the diagnose step.

Concretely, the finished system will do all of the following without a human in the loop for the safe-to-touch namespaces:

1. **Watch the cluster event stream.** Every Warning event is classified, deduped, and queued.
2. **Diagnose.** A library of k8sgpt-parity analyzers (Pod, Service, Ingress, PVC, Node, Deployment/RS/STS, CronJob, NetworkPolicy, PDB, HPA) emits structured `Finding`s with severity and a proposed fix class.
3. **Pick a fix.** A deterministic remediation table maps each fix class to a pure Python function that produces a manifest diff or a `kubectl` command sequence. The LLM (NIM) is only used to *explain* the finding, never to generate commands.
4. **Try the cheap thing first.** A restart-first ladder issues `kubectl rollout restart` and watches for five minutes. If the pod heals, done. If not, escalate.
5. **Verify in a sandbox.** Every candidate fix is applied to an ephemeral vcluster, run through a smoke test keyed to the fix class, and only proceeds if the sandbox stays green.
6. **Land it via GitOps.** The fix becomes a PR against the manifests repo with the finding, the evidence, and the sandbox log attached. ArgoCD applies. Allowlisted namespaces auto-merge; trading namespaces (`ibkr-live-trader`, `daxxon-trading`, `brightflow-live`) never auto-merge — PR opens, label `human-review-required`, assignee set.
7. **Learn from every loop.** Every (failed_action → working_fix) pair becomes a DPO record posted as a GitHub issue with label `dpo-pair`. `corey-coder` ingests these nightly into a JSONL training set. The LoRA loop fine-tunes on the dataset.
8. **Audit everything.** Every action (detect, classify, sandbox, PR, restart, observe, escalate) appends one record to a 90-day audit log. The audit log answers what-happened-when after the fact.

The hard target: `kubectl get pods -A | grep -v Running | grep -v Completed | grep -v STATUS` returns empty across the allowlist, and no new Warning events for 30 consecutive minutes after the remediator deploys.

### Why this exists at all

The first conversation that started this work was a cluster-events triage. Roughly: `brightflow-dashboard` was crash-looping on readiness, `daxxon-3` was timing out on liveness, `bitnami/kubectl:1.30` had been yanked from Docker Hub and was causing `ImagePullBackOff` everywhere, and CronJob orphans were piling up. Three classes of failure, all auto-fixable in principle, all eating cycles in practice. The conclusion was: build the thing that fixes them.

The second step was to audit the existing repo to see whether it could be the foundation. It could not — the managers returned hardcoded fake data, the README claimed production readiness against a stub server, and `enhanced_tools.py` was never imported. The decision was to gut-and-rebuild.

### Why this beats `k8sgpt`

`k8sgpt` is a diagnose tool. It reads cluster state, runs ~20 analyzers, and prints (or post-processes) findings. It does not verify fixes. It does not write fixes. It does not learn. It is one-shot prompts per finding with no agent loop.

This system is k8sgpt-parity on diagnosis plus all of: sandbox verification before apply, GitOps PR with audit trail, restart-first ladder for transient failures, hard-block on trading namespaces, deterministic command generation (LLM never writes commands), DPO emission for offline learning, hour-11 export to a vector store for retrieval-augmented context on future runs, and an internal critic that gates merges on validator pass.

---

## 2. The big picture

```
+----------------------------------------------------------------------------+
|                          KUBERNETES CLUSTER                                |
|                                                                            |
|   +----------------+   +----------------------+   +--------------------+   |
|   |  event stream  |   |   corey-fl-redis     |   |   corey-fl-agent   |   |
|   |  (kube events) |-->| (24h task queue +   |<--| (stable pod, PVC,  |   |
|   |  Warning only  |   |  build_counter +    |   |  tools, repo)      |   |
|   +----------------+   |  HSET task:US-XXX)  |   +--------------------+   |
|                        +----------------------+        ^                   |
|                                                        |                   |
|                                                        | kubectl exec      |
|                                                        |                   |
|   +------------------+   +------------------+   +------+-----+              |
|   |  6 sub-agents    |   |    critic        |   |   main     |              |
|   |  (Claude Max     |-->|  (Claude Max     |-->| orchestrator|             |
|   |  Agent calls)    |   |  Agent call)     |   |  (this CC)  |             |
|   +------------------+   +------------------+   +------+------+              |
|                                                        |                    |
|                                                        v                    |
|                                              corey-rag (PG+pgvector)        |
|                                              corey-ollama (embeddings)      |
+----------------------------------------------------------------------------+

GITHUB:
  main branch + feature branches corey-fl-loop/US-XXX-<slug>
  every commit carries Alpha-{build}-{sha6}-{maj}-{min}_{patch}-{date}
  every commit updates CHANGELOG.md
  author = git config user, no AI attribution anywhere
```

Six sub-agents drain the Redis queue in parallel waves. Each sub-agent claims one task atomically via `ZPOPMIN`, opens a git worktree inside `corey-fl-agent`, authors files in the worktree via `kubectl exec`, runs six validators in-pod, and either pushes a branch + `mark_done` or `mark_failed`. The critic picks up `needs_fix` items in subsequent waves. After Redis fills up with `done` and `done`/`needs_fix` resolved entries, the hour-11 job exports JSONL to `corey-rag` for retrieval and LoRA fine-tune.

---

## 3. What we have built so far

### Phase A — audit (DONE)

Goal: figure out whether the existing code could be the foundation. Verdict: no.

- 50 review agents fired in parallel across 112 components (Python sources, k8s manifests, shell scripts, docs, MCP tool definitions, behavioral specs).
- Each agent wrote a JSON report to `docs/audit-run-001/reports/agent-NN.json`.
- 48 of 50 reports parsed cleanly (two had JSON escape issues; counted but not aggregated).
- 480 total findings. **117 critical, 215 high, 116 medium, 10 low, 22 info.**
- Top consensus findings: `src/helm_manager.py` (7 reviewers), `behavior:rbac_split` (6), `behavior:audit_log` (6), `mcp-tool:diagnose_cluster_health` (6), `k8s/pvc.yaml` (6), `enhanced:kubectl_describe` (6).
- Five recurring patterns: managers return hardcoded data, `enhanced_tools.py` is dead code (never imported), docs overclaim production readiness, tests self-mock their own returns, security gaps (SQL injection, secret leakage).
- Persisted at `docs/audit-run-001/all-findings.json`.

### Phase C — PRD synthesis (DONE)

Goal: produce a buildable spec for what the gut-and-rebuild looks like.

- 25 synthesis agents fired in parallel, each authoring one PRD section.
- All 25 chunks written under `docs/audit-run-001/prd-chunks/01..25-*.md`.
- Stitched into `docs/audit-run-001/PRD.md` (9197 lines).
- Sections cover: restart-first ladder, 5-min watchdog, DPO pair schema, trading hardblock, event watcher, NIM backend + cache, BaseAnalyzer + Pod, Service/Ingress, PVC/Node, Deployment/RS/STS, CronJob/orphans, NetPol/PDB/HPA, vcluster sandbox lifecycle, GitOps PR generation, deterministic remediation table, audit log, RBAC split, CI/CD on `albright-runners`, security hardening, acceptance criteria + Checklist.md, docs de-claim, dead-code removal, iteration state machine + Redis worklist.

### `prd.json` (DONE)

The 25 PRD sections converted into the gold-prompt schema:

- `prd.json` at repo root, 25 `userStories`, each with `acceptanceCriteria` (12 criteria covering syntax/lint/type/unit/runtime/integration/perf/security/CHANGELOG/version/author/proof), `priority` (10 P1, 10 P2, 5 P3), `passes: false`, `notes` pointing back at its PRD chunk.
- Project umbrella branch: `hawaiideveloper/auto-remediator-rebuild` (not actually used yet — feature branches go directly under `corey-fl-loop/US-XXX-*`).

### Phase 1 — Redis task queue (DONE)

`corey-fl-redis` Deployment + Service in `corey-coder` namespace.

- Image: `redis:7-alpine`.
- Persistence: RDB `save 60 1` (snapshot if ≥1 write in 60s), PVC `corey-fl-redis-data` 1Gi local-path, **no AOF**.
- Memory: 128Mi request / 320Mi limit, `maxmemory 256mb`, `allkeys-lru` eviction.
- Security: `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, capabilities drop ALL, non-root UID 999.
- Network: ClusterIP `10.110.74.18:6379`, DNS `corey-fl-redis.corey-coder.svc:6379`.
- TTL: 86400s on every task hash and on `queue:pending`.
- 25 tasks seeded as `HSET task:US-XXX` with the gold-prompt schema (problem, proposed_solution, assigned_agent, status, file_scope, priority, validation_required, result, error_log, patch_ref, validator_results, parent_task, story_id, notes, acceptance_criteria).
- `queue:pending` is a sorted set scored by `priority` (1 = highest). `ZPOPMIN` gives atomic claim.
- `build_counter` integer used by every commit for the `Alpha-{build}-...` version.

### Phase 2 setup — runner scripts + stable agent pod (DONE)

- `scripts/runner/claim_task.py` — `ZPOPMIN queue:pending` + `HSET status=claimed assigned_agent=$AGENT_ID`. Idempotent on requeued tasks.
- `scripts/runner/mark_done.py` — `HSET status=done completed_at=$ts result=$result patch_ref=$proof`.
- `scripts/runner/mark_failed.py` — `HSET status=needs_fix error_log=$err`, requeues at `priority - 0.5` so the critic gets it next.
- `scripts/runner/heartbeat.py` — touches `heartbeat_at` and `progress_note`.

`corey-fl-agent` Deployment + PVC in `corey-coder`:

- Image: `python:3.11-slim` (stable, in-cluster, x86_64).
- PVC: `corey-fl-agent-work` 1Gi local-path mounted at `/work`. Survives restarts.
- Bootstrap script in a `ConfigMap` mounted at `/bootstrap/bootstrap.sh`. Idempotent:
  - apt-installs `git ca-certificates curl jq redis-tools netcat-openbsd`.
  - pip-installs `redis kubernetes pyyaml ruff mypy pytest`.
  - downloads `kubectl 1.30.0`.
  - configures git user `Corey the Don Hawaiideveloper <hawaiideveloper@gmail.com>` plus a credential helper reading `/root/.git-credentials`.
  - clones the repo into `/work/mcp-kubernetes-platform-engineer` if missing; pulls `main` if present.
  - copies `scripts/runner/*.py` into `/work/runner/` for agent use.
- GitHub token sourced from existing `github-credentials` secret (`token` key, classic `ghp_` PAT). Never logged, never written to anything but `/root/.git-credentials`.
- Resources: 200m/256Mi requests, 2/2Gi limits.
- Sleep loop keeps the pod up between agent invocations.

### Phase 2 — Wave 1 (DONE)

Six sub-agents fired in parallel. Each cold-start, claimed one task, worked entirely inside `corey-fl-agent` via `kubectl exec`, ran six validators, committed with version + CHANGELOG, pushed a feature branch, and called `mark_done`.

Six branches landed on GitHub:

| Story | Branch | Highlights of what landed |
|---|---|---|
| US-001 | `corey-fl-loop/US-001-exec-summary-roadmap` | Exec summary doc grounded in audit counts |
| US-002 | `corey-fl-loop/US-002-current-state-inventory` | Severity/fix-class breakdown + critical-30 table |
| US-006 | `corey-fl-loop/US-006-trading-hardblock` | `SafetyGate` + `config/safety.yaml` + tests asserting trading ns rejects mutating actions |
| US-019 | `corey-fl-loop/US-019-rbac-split` | 9 RBAC YAMLs (reader / per-ns applier / sandbox / pr-bot) + 3 audit modules + 312-line test file |
| US-020 | `corey-fl-loop/US-020-cicd-albright-runners` | `.github/workflows/{ci,release}.yml` + dependabot + pre-commit + deployment.yaml digest patch + 323-line tests |
| US-021 | `corey-fl-loop/US-021-security-hardening` | Eight concrete patches (SQL injection, token leak, empty secret, hardcoded IP, NetworkPolicy, broken setup script, error-swallow, loguru API) with tests |

Queue: 25 → 19. `build_counter`: 2 → 8 (every sub-agent INCR'd once). Author on every commit: `Corey the Don Hawaiideveloper <hawaiideveloper@gmail.com>`. Zero AI attribution mentions across all six commit messages (`git log --format='%B' | grep -iE 'claude|anthropic|generated by|co-authored-by'` returns nothing on all six branches).

---

## 4. Where things live (paths, services, secrets)

### In the cluster (`corey-coder` namespace)

| Resource | Purpose |
|---|---|
| `Deployment/corey-fl-redis` | Task queue (24h TTL) |
| `Service/corey-fl-redis` (ClusterIP 10.110.74.18:6379) | Redis endpoint |
| `PVC/corey-fl-redis-data` (1Gi local-path) | RDB snapshots |
| `Deployment/corey-fl-agent` | Stable agent pod, x86_64, all tools |
| `PVC/corey-fl-agent-work` (5Gi local-path) | `/work` (repo + runner + worktrees) |
| `ConfigMap/corey-fl-agent-bootstrap` | Idempotent bootstrap script |
| `Secret/github-credentials` (key `token`) | GitHub PAT for git push |
| `Deployment/corey-rag` | PostgreSQL 16 + pgvector + MCP API (hour-11 destination) |
| `Service/corey-rag` | 5432 (pg) + 8002 (MCP API) |
| `Deployment/corey-ollama` | Embeddings provider (currently 0/1 — needs attention before hour-11) |

### In the repo (paths)

| Path | What |
|---|---|
| `prd.json` | 25 userStories per gold-prompt schema |
| `CHANGELOG.md` | Versioned entries from build 1 onward |
| `Lessons_Learned.md` | Incident log (Docker daemon, Redis restart, teacher-sandbox instability) |
| `infra/redis/redis.yaml` | Redis Deployment + Service + PVC |
| `infra/agent/corey-fl-agent.yaml` | Agent pod + PVC + bootstrap ConfigMap |
| `scripts/runner/{claim_task,mark_done,mark_failed,heartbeat}.py` | Task lifecycle |
| `docs/audit-run-001/all-findings.json` | 480 audit findings |
| `docs/audit-run-001/reports/agent-NN.json` | Per-agent review JSON |
| `docs/audit-run-001/prd-chunks/01..25-*.md` | PRD sections, source of truth for each user story |
| `docs/audit-run-001/PRD.md` | Stitched PRD (9197 lines) |
| `docs/audit-run-001/proofs/US-XXX/` | Validator proof artifacts (started by Wave 1) |
| `src/auto_remediate/` | New package created by Wave 1 sub-agents |
| `k8s/rbac/` | Four-identity RBAC YAMLs from US-019 |
| `.github/workflows/{ci,release}.yml` | CI/CD from US-020 |

### On the dev workstation

The dev workstation is Apple Silicon (arm64). The cluster is x86_64. Architectural mismatch means **no builds, no shared services, no agent work** runs on the dev workstation. The dev workstation only:

- runs `kubectl` against the cluster
- runs `gh` for PR operations
- runs Claude Code (this orchestrator) which only invokes Bash → `kubectl exec` for any actual file or git operation

Local Docker is broken on the dev workstation. Local Homebrew Redis is intentionally unused because the same manifest must move into the cluster verbatim.

### Versioning convention

Every commit follows:

- Pre-release: `Alpha-{build_number}-{parent_sha6}-{major}-{minor}_{patch}-{date}`
- Release: `{build_number}-{parent_sha6}-{major}-{minor}_{patch}-{date}` (drop the `Alpha-` prefix)

`build_number` increments via `redis-cli INCR build_counter`. `parent_sha6` is `git rev-parse --short=6 HEAD` from before the commit. `major.minor.patch` starts at `0.1.0` and stays there until a real release decision. Every commit also prepends a `CHANGELOG.md` entry. The gold-prompt rule "never ambiguous about which version we are on" is satisfied by tying the version into the commit message body and the changelog entry.

---

## 5. Lessons learned so far

Three real incidents, all logged in `Lessons_Learned.md`. Each is a permanent rule for this repo going forward.

1. **Docker daemon on the dev workstation cannot be relied on.** First attempt to host Redis as a local container failed because Docker Desktop was not running and starting it interactively does not fit the workflow. Lesson: shared services for cluster targets go in the cluster, full stop.
2. **ARM dev workstation vs x86_64 cluster.** Anything built on the dev workstation without `--platform linux/amd64` will not run on the cluster. Lesson: use a sandbox pod in the cluster for all builds, all tests, and all ephemeral services. The dev workstation only edits source and invokes `kubectl`.
3. **Redis with no persistence loses data on pod restart.** First Redis pod was deployed with `--save "" --appendonly no` and `emptyDir`. It restarted about 76 minutes later and wiped all 25 task hashes plus `queue:pending`. Lesson: any Redis used as a *queue* (even with 24h key TTL) needs RDB snapshots + a PVC. Cache-only patterns where the consumer can recompute from source are the only exception.
4. **The teacher-sandbox pod is too unstable for agent work.** It had 71 restarts in 47 hours (~ one restart every 40 minutes). Apt-installed tools and cloned repos vanished on each restart. Lesson: build a dedicated, owned agent pod with a PVC for `/work` and an idempotent bootstrap that re-establishes tools on every restart. That is what `corey-fl-agent` is.

Future lessons will be appended to the same file. The unwritten rule is that every failure that costs more than a single retry gets a `Lessons_Learned.md` entry naming the root cause and the prevention.

---

## 6. What is left to do

The remaining work is the rest of the gold-prompt loop. Roughly:

### Phase 2 — Waves 2 through 5 (19 tasks left)

Tasks still in `queue:pending`: US-003, US-004, US-005, US-007 through US-018, US-022 through US-025. That is 19 tasks. With 6 sub-agents per wave it takes 4 more waves to drain. Each wave is one parallel fire of six `Agent` tool calls, each running the same sub-agent prompt with a different `AGENT_ID`. Pattern is now proven — Wave 1 ran clean.

A risk to flag: the priority-1 work (highest-value, lowest blast-radius, lots of docs + safety) is mostly done in Wave 1. Wave 2 onward will start hitting the larger code-authoring stories (analyzers, vcluster, NIM, deterministic remediations, audit log). Failures will start surfacing. The critic loop (below) becomes necessary at that point.

### Phase 3 — six validators (in progress, partially implemented inline)

Wave 1 sub-agents ran the six validators inline as a shell pipeline. That is fine for one task but does not scale to a critic loop. The proper structure is six callable validator modules:

| Validator | What it does | Pass criterion |
|---|---|---|
| Syntax | `ast.parse` every new `.py` | All parse |
| Unit | `pytest -k <story_id> -v` | All pass |
| Runtime | Import the new module, run a hello-world from it | Exit 0 |
| Integration | Apply candidate manifest to vcluster, run smoke test | Smoke green |
| Performance | Handler p95 < 2s on fixture data | Threshold met |
| Security | `ruff check --select S` + secret grep + trivy on image | 0 findings |

Each validator stores its result in `validator_results[<name>]` on the task hash. The critic reads that map.

### Phase 4 to 8 — execution + correction + verification (in progress)

The execution flow is already running (Wave 1 proved it end-to-end). What is missing:

- **Critic agent.** When `mark_failed` requeues a task at `priority - 0.5`, no agent currently picks it up before fresh tasks. The critic is a dedicated `Agent` call that filters for `status=needs_fix`, reads the `error_log`, proposes a fix, and either patches the existing branch or marks it for human review.
- **Conflict prevention via worktrees.** Worktrees are already in use. What is not in place: a per-task Redis SETNX lock around git push to prevent two waves on the same task from racing if the critic accidentally claims an in-progress task.
- **Patch-only merges.** Right now sub-agents push a feature branch directly. The PRD calls for patches against the GitOps repo (manifests repo). For repo-internal work this is fine; for cluster-state changes (US-022 deterministic remediations) this needs to point at the GitOps target instead of `origin`.
- **Verification gate.** Task is only DONE if `kubectl logs` or `kubectl get pods` or an API response proves the fix landed. For repo-internal user stories this maps to "PR merged + CI green"; for cluster-touching stories this maps to "pod healthy after apply". Not yet implemented as a hard gate.

### Phases 9 and 10 — hour-11 JSONL flush to corey-rag

Before the Redis 24h TTL fires, a job exports every `done` and resolved-`needs_fix` task to JSONL:

```
{"problem": "...", "initial_solution": "...", "final_solution": "...",
 "errors": [...], "fixes": [...], "validation_proof": {...}, "story_id": "US-XXX",
 "version": "Alpha-N-...", "completed_at": "..."}
```

The JSONL is shipped into `corey-rag` (PG + pgvector) via the MCP API on port 8002. Embeddings come from `corey-ollama`. **Blocker:** `corey-ollama` is currently `0/1` — must be back up before the hour-11 job is wired or the embedder will fail. Tracked under the LoRA-readiness checklist.

### Phase 11 — LoRA learning loop

Out of scope for this initial sprint. Once corey-rag has accumulated DPO pairs for several weeks, fine-tune a small adapter on (rejected, chosen) pairs. Loop is: failures → fixes → success → adapter updates → fewer failures next time. Targeted improvement metric: percent of fixes that pass on first sandbox attempt.

### Phase 12 — CHANGELOG + version enforcement

Every commit on this branch and on every feature branch already includes a version and a CHANGELOG entry. Wave 1 demonstrated this works manually. What is missing:

- **Pre-commit hook** that refuses to commit if `CHANGELOG.md` was not modified.
- **Pre-commit hook** that refuses to commit if the commit subject or body does not contain `Alpha-` (until the first true release) or a release-format version string.
- **CI check** that enforces the same on PRs.

These hooks belong in `.pre-commit-config.yaml` from US-020.

### Phase Z — the actual auto-remediator runs

Everything above is repo work. The actual runtime — the watcher that observes cluster events, the ladder that issues restarts, the sandbox that verifies fixes, the PR generator that opens patches — is the union of the deliverables from US-003 through US-018 and US-022 through US-025. Once those land, the next step is:

1. Build the container image from the new `src/auto_remediate/` package.
2. Apply RBAC from `k8s/rbac/`.
3. Deploy.
4. Watch the cluster events stream get classified, the safe-namespace pods get restart-first remediated, and the trading namespaces get PR-only proposals.
5. Verify the done bar: pytest green, image build green, `kubectl get pods -A | grep -v Running | grep -v Completed | grep -v STATUS` returns nothing in the allowlist, 30 min of clean events, hour-11 export wrote to corey-rag.

---

## 7. Acceptance criteria — definition of done

The hard, measurable bar (from `docs/audit-run-001/prd-chunks/22-acceptance.md`):

| # | Criterion | How to verify |
|---|---|---|
| 1 | All 25 user stories status = `done` in Redis | `redis-cli ZCARD queue:pending` returns 0 AND every `task:US-XXX` has `status=done` |
| 2 | `pytest -v` green, coverage ≥ 80% on `src/` | CI green on main |
| 3 | `ruff check .` returns 0 violations | CI green |
| 4 | `mypy src/` returns 0 errors | CI green |
| 5 | Image builds and pushes to ghcr | `docker manifest inspect` returns a digest |
| 6 | RBAC applied successfully | `kubectl get clusterrole,role,sa -A | grep auto-remediate` returns the four identities |
| 7 | Remediator deploys and reaches Ready | `kubectl rollout status` succeeds in <60s |
| 8 | Real `kubernetes` client calls exercised | `grep -r "list_namespaced_pod" src/` returns hits AND integration test log shows the call |
| 9 | End-to-end: detect → restart → watch → escalate → DPO issue → audit log | Filed DPO issue exists; audit log has the trail |
| 10 | `kubectl get pods -A | grep -v Running` is empty for the allowlist | One-shot CLI check |
| 11 | No new Warning events for 30 min after deploy | `kubectl get events -w` clean for 30 min |
| 12 | All PRD checklist items ticked | `Checklist.md` is all `[x]` |

Iteration is allowed. If any criterion fails, the failing finding is requeued and the loop runs again. Max five iterations before escalating to a human.

---

## 8. Where we left off (resume point)

State at the moment this note was written:

- Branch `main` at `168973e feat(corey-fl-loop Phase 2 setup): runner scripts + Redis persistence`.
- Six feature branches pushed under `corey-fl-loop/US-*`, no PRs opened yet.
- Redis `queue:pending` size = 19. `build_counter` = 8. Twenty-five task hashes intact, six with `status=done`.
- `corey-fl-agent` pod healthy at `corey-fl-agent-688bf4bf5f-6nzw5`, `/work` clean, runner scripts in place, repo at HEAD.
- `corey-fl-redis` pod healthy with PVC, RDB snapshots functioning.
- No outstanding `needs_fix` tasks. The critic loop has not been triggered yet.
- No PRs from Wave 1 feature branches — they sit on origin, ready for review or for a batch merge.
- The dev workstation has nothing to do until Wave 2 fires. It only edits this `the_goal-inprogress.md` file (which was authored in-pod, per the all-activity-in-pod rule) and commits it.

To resume: fire Wave 2 with six fresh `Agent` calls using the same sub-agent prompt template with `AGENT_ID` suffixes `sub7` through `sub12`. Each will claim one of the 19 remaining tasks. After Wave 2, decide whether to keep firing or pause to merge the accumulated feature branches into main first.

Or, if reviewing first: `gh pr list --state open --search "corey-fl-loop"` shows nothing yet because no PRs have been opened. To open all six Wave 1 branches as PRs in one batch:

```
for br in US-001-exec-summary-roadmap US-002-current-state-inventory \
          US-006-trading-hardblock US-019-rbac-split \
          US-020-cicd-albright-runners US-021-security-hardening; do
  gh pr create --base main --head "corey-fl-loop/$br" \
    --title "$(git log -1 --format=%s "origin/corey-fl-loop/$br")" \
    --body "Wave 1 — see CHANGELOG and the per-story commit body for the version + summary."
done
```

The system as it stands is end-to-end functional for the parallel-agent loop. What it does not yet do is the actual runtime auto-remediation — that comes when the remaining user stories land and the package gets deployed. Everything before that is scaffolding to make the runtime safe, verifiable, and learnable.

---

*This file is meant to be readable cold. If you are picking this up from a fresh session and want to continue: read this top to bottom, then look at the latest CHANGELOG entry, then look at `redis-cli ZCARD queue:pending` to see how much work is left.*
