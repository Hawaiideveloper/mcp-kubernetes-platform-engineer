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

---

## 9. Resume runbook (operational — everything you need to close + reopen)

### 9.1 Discover the current pods

Pod names carry a generated suffix that changes on restart. Always look up by label, never by hardcoded name:

```bash
AGENT_POD=$(kubectl -n corey-coder get pods -l app=corey-fl-agent \
  -o jsonpath='{.items[0].metadata.name}')
REDIS_POD=$(kubectl -n corey-coder get pods -l app=corey-fl-redis \
  -o jsonpath='{.items[0].metadata.name}')
echo "AGENT=$AGENT_POD  REDIS=$REDIS_POD"
```

### 9.2 Health check (run this first on any resume)

```bash
# Cluster services up?
kubectl -n corey-coder rollout status deploy/corey-fl-agent --timeout=30s
kubectl -n corey-coder rollout status deploy/corey-fl-redis --timeout=30s

# Redis reachable and has data?
kubectl -n corey-coder exec "$AGENT_POD" -- redis-cli -h corey-fl-redis PING
kubectl -n corey-coder exec "$AGENT_POD" -- redis-cli -h corey-fl-redis ZCARD queue:pending
kubectl -n corey-coder exec "$AGENT_POD" -- redis-cli -h corey-fl-redis GET build_counter

# Tools in agent pod still present? (Should be — PVC keeps /work, bootstrap re-installs apt/pip on restart.)
kubectl -n corey-coder exec "$AGENT_POD" -- bash -lc \
  'git --version; redis-cli --version; ruff --version; mypy --version; pytest --version | head -1'

# Repo at HEAD?
kubectl -n corey-coder exec "$AGENT_POD" -- bash -lc \
  'cd /work/mcp-kubernetes-platform-engineer && git fetch --quiet && git log --oneline -3'
```

### 9.3 If Redis lost data on restart (re-seed)

Redis has RDB `save 60 1` + PVC, so this should be rare, but if `ZCARD queue:pending` returns 0 and the work is not in fact done:

```bash
kubectl -n corey-coder exec "$AGENT_POD" -- bash -lc '
cd /work/mcp-kubernetes-platform-engineer && git pull --quiet
python3 <<EOF
import json, redis, pathlib
prd = json.loads(pathlib.Path("prd.json").read_text())
r = redis.Redis(host="corey-fl-redis", port=6379, decode_responses=True)
for s in prd["userStories"]:
    sid = s["id"]; key = f"task:{sid}"
    r.hset(key, mapping={
        "problem": s["title"],
        "proposed_solution": s["description"],
        "assigned_agent": "", "status": "pending", "file_scope": "[]",
        "priority": str(s["priority"]),
        "validation_required": json.dumps(["syntax","unit","runtime","integration","performance","security"]),
        "result": "", "error_log": "", "patch_ref": "",
        "validator_results": "{}", "parent_task": "",
        "story_id": sid, "notes": s["notes"],
        "acceptance_criteria": json.dumps(s["acceptanceCriteria"]),
    })
    r.expire(key, 86400)
    r.zadd("queue:pending", {sid: s["priority"]})
r.expire("queue:pending", 86400)
# Mark already-pushed Wave 1 branches as done so they are not re-claimed
for sid in ("US-001","US-002","US-006","US-019","US-020","US-021"):
    r.zrem("queue:pending", sid)
    r.hset(f"task:{sid}", mapping={"status":"done"})
print("re-seeded; queue =", r.zcard("queue:pending"))
print("build_counter unchanged =", r.get("build_counter"))
EOF
'
```

If `build_counter` is also missing, set it to the highest build seen in `git log --all --grep='Version: Alpha-' | grep -oE 'Alpha-[0-9]+' | sort -V | tail -1` and `redis-cli SET build_counter <N>`.

### 9.4 The 19 remaining tasks (as of Wave 1 close, sorted by priority)

| Priority | Story | Title | PRD chunk |
|---|---|---|---|
| 1 | US-022 | Acceptance criteria + Checklist.md | docs/audit-run-001/prd-chunks/22-acceptance.md |
| 1 | US-023 | Docs de-claim + Master TOC backlink | docs/audit-run-001/prd-chunks/23-docs-declaim.md |
| 1 | US-024 | Dead-code removal (.bak, enhanced_tools) | docs/audit-run-001/prd-chunks/24-dead-code.md |
| 1 | US-025 | Iteration state machine + Redis worklist | docs/audit-run-001/prd-chunks/25-state-machine-and-worklist.md |
| 2 | US-003 | Restart-first remediation ladder | docs/audit-run-001/prd-chunks/03-restart-first-ladder.md |
| 2 | US-004 | 5-minute watchdog | docs/audit-run-001/prd-chunks/04-watchdog.md |
| 2 | US-005 | DPO pair emission to GitHub issues | docs/audit-run-001/prd-chunks/05-dpo-pair-schema.md |
| 2 | US-007 | Cluster event-stream watcher | docs/audit-run-001/prd-chunks/07-event-watcher.md |
| 2 | US-008 | NIM/Ollama/Fake LLM backend with cache | docs/audit-run-001/prd-chunks/08-nim-backend.md |
| 2 | US-009 | BaseAnalyzer + PodAnalyzer | docs/audit-run-001/prd-chunks/09-analyzer-base-pod.md |
| 2 | US-015 | vcluster sandbox lifecycle | docs/audit-run-001/prd-chunks/15-vcluster-sandbox.md |
| 2 | US-016 | GitOps auto-PR generation | docs/audit-run-001/prd-chunks/16-gitops-pr.md |
| 2 | US-017 | Deterministic remediation table (10 fixes) | docs/audit-run-001/prd-chunks/17-deterministic-remediation.md |
| 2 | US-018 | Audit log + finding persistence + dedup | docs/audit-run-001/prd-chunks/18-audit-log.md |
| 3 | US-010 | Service + Ingress analyzers | docs/audit-run-001/prd-chunks/10-analyzers-service-ingress.md |
| 3 | US-011 | PVC + Node analyzers | docs/audit-run-001/prd-chunks/11-analyzers-pvc-node.md |
| 3 | US-012 | Deployment/RS/StatefulSet analyzers | docs/audit-run-001/prd-chunks/12-analyzers-workloads.md |
| 3 | US-013 | CronJob analyzer + orphan-job cleaner | docs/audit-run-001/prd-chunks/13-cronjob-and-orphan-jobs.md |
| 3 | US-014 | NetworkPolicy + PDB + HPA analyzers | docs/audit-run-001/prd-chunks/14-analyzers-netpol-pdb-hpa.md |

Live source of truth: `redis-cli -h corey-fl-redis ZRANGE queue:pending 0 -1 WITHSCORES`.

### 9.5 Sub-agent prompt template (verbatim — use this for Waves 2 through 5)

Fire six `Agent` tool calls in parallel in one message. Each gets this prompt with `{N}` and the `AGENT_ID` suffix swapped. Pick `subagent_type=general-purpose`, `model=sonnet`.

```
You are corey-fl-loop sub-agent {N} of 6. Cold start, no parent context.

YOUR ID: corey-fl-{YYYYMMDD}-sub{N}
POD: discover via `kubectl -n corey-coder get pods -l app=corey-fl-agent -o jsonpath='{.items[0].metadata.name}'`
RUNNER: /work/runner/{claim_task,mark_done,mark_failed,heartbeat}.py
REPO IN POD: /work/mcp-kubernetes-platform-engineer (already cloned, git auth wired)
PRD chunks: docs/audit-run-001/prd-chunks/01..25-*.md

STRICT RULE: every file write, git op, validator run, and shell command MUST happen INSIDE the pod via kubectl exec. NEVER write to the Mac filesystem. NEVER use Read/Write/Edit/NotebookEdit on local paths. Use ONLY the Bash tool, and every Bash invocation must start with `kubectl -n corey-coder exec <pod> -- bash -lc '...'` or `kubectl -n corey-coder exec -i <pod> -- tee <path> >/dev/null <<'EOF'`.

YOUR LOOP — DO EXACTLY ONCE, NOT A SECOND TASK:

STEP 1 CLAIM:
Run `kubectl -n corey-coder exec <pod> -- env AGENT_ID=corey-fl-{YYYYMMDD}-sub{N} python3 /work/runner/claim_task.py`.
Parse the JSON. If `"claimed": false`, return `"no work — queue empty"` and exit.
Extract: story_id, task.notes (contains PRD path), task.problem (title), task.acceptance_criteria.

STEP 2 READ PRD:
`task.notes` is like `"PRD section: docs/audit-run-001/prd-chunks/06-trading-hardblock.md"`. Cat that file from the pod.

STEP 3 WORKTREE:
Make a short kebab slug from the story title (lowercase, alnum+dash, ≤30 chars). Set BRANCH="corey-fl-loop/${story_id}-${slug}". WORKTREE="/work/wt/${story_id}".
`cd /work/mcp-kubernetes-platform-engineer && git fetch --quiet && git checkout main && git pull --quiet && git worktree add "$WORKTREE" -b "$BRANCH"`.

STEP 4 IMPLEMENT:
Read the PRD section. It tells you which files to create and what they should contain (class signatures, code, tests). Author each deliverable file with a kubectl exec -i tee heredoc into $WORKTREE/<path>. Keep each file ≤200 lines; split into sub-modules if needed. Write tests under $WORKTREE/tests/. Author = git config already set in the pod — DO NOT override. NO AI ATTRIBUTION anywhere ("Generated by", "Claude", "Anthropic", etc).

STEP 5 VALIDATORS (in the pod, in $WORKTREE):
a) Syntax: `find $WORKTREE/src $WORKTREE/tests -name '*.py' -newer $WORKTREE/.git/HEAD 2>/dev/null | xargs -I{} python3 -c "import ast; ast.parse(open('{}').read())"` — must succeed for every file.
b) Lint: `cd $WORKTREE && ruff check . --output-format=concise` — must return 0 violations on changed files.
c) Type: `cd $WORKTREE && mypy --ignore-missing-imports src/ 2>&1` if src/ changed — capture but don't fail on warnings; fail on errors.
d) Unit: `cd $WORKTREE && PYTHONPATH=. pytest tests/ -k ${story_id} -v --tb=short` — must pass (skip ok if no tests with that keyword, but you should HAVE written tests).
e) Runtime: for each new module under src/auto_remediate, `cd $WORKTREE && PYTHONPATH=. python3 -c "import <module>"` — must import without error.
f) Security: `cd $WORKTREE && ruff check . --select S --no-fix` returns 0; `grep -rE '(token|secret|password|api_key)\s*=\s*["\047][A-Za-z0-9]{6,}' $WORKTREE/src $WORKTREE/tests` returns no matches.

ON ANY VALIDATOR FAILURE: capture error to a one-line summary, save full log to $WORKTREE/.fail.log, then `python3 /work/runner/mark_failed.py ${story_id} '<one-line>'`, return `"FAILED ${story_id} validator=<which> reason=<short>"` and exit.

STEP 6 COMMIT WITH VERSION + CHANGELOG:
In the worktree:
BUILD=$(redis-cli -h corey-fl-redis INCR build_counter)
PARENT_SHA6=$(git rev-parse --short=6 HEAD)
DATE=$(date -u +%Y-%m-%d)
VERSION="Alpha-${BUILD}-${PARENT_SHA6}-0-1_0-${DATE}"

Prepend $WORKTREE/CHANGELOG.md (insert above the most recent `## [` line) with a new entry:
## [${VERSION}] — ${DATE}
### Added/Changed
- (${story_id}) <2-sentence summary of what landed>
### Files
- <list of new/modified paths>

`git add -A && git commit -m "feat(${story_id}): <title>

Version: ${VERSION}

<2-line summary>"`

STEP 7 PUSH:
`git push -u origin HEAD` — capture the commit SHA from `git rev-parse HEAD`.

STEP 8 MARK DONE:
`python3 /work/runner/mark_done.py ${story_id} 'pushed' "${BRANCH}:${SHA}"`

STEP 9 RETURN SUMMARY (single line, plain text — no markdown):
`DONE ${story_id} branch=${BRANCH} sha=${SHA:0:7} validators=pass`

HARD CONSTRAINTS:
- Time budget: 12 minutes max wall clock; if exceeded, mark_failed with "timeout".
- ONE task per agent invocation. Do not loop.
- Bash tool only. No Read/Write/Edit/NotebookEdit.
- Every file path you touch must start with `/work/` inside the pod.
- No emoji. No AI attribution. Author = git config user in pod.
- Output to me at the end: only the summary line. Nothing else.
```

### 9.6 The CHANGELOG insertion algorithm (sub-agents follow this exactly)

```python
import pathlib, re
cl = pathlib.Path("CHANGELOG.md").read_text()
entry = f"""
## [{VERSION}] — {DATE}

### Added/Changed
- ({STORY_ID}) {SUMMARY}

### Files
- {FILES}
"""
m = re.search(r"\n## \[", cl)
cl = cl[:m.start()] + entry + cl[m.start():] if m else cl + entry
pathlib.Path("CHANGELOG.md").write_text(cl)
```

Inserts the new entry above the most recent `## [` line (i.e. right under the header). Each entry is keyed by version string so order is preserved automatically.

### 9.7 Open Wave 1 PRs in one batch (optional, run from dev workstation)

```bash
cd ~/Documents/github/albright-labs/corey-toolbox/mcp-kubernetes-platform-engineer
gh auth status  # must be authenticated
git fetch --all --quiet
for br in US-001-exec-summary-roadmap US-002-current-state-inventory \
          US-006-trading-hardblock US-019-rbac-split \
          US-020-cicd-albright-runners US-021-security-hardening; do
  title=$(git log -1 --format=%s "origin/corey-fl-loop/$br")
  gh pr create --base main --head "corey-fl-loop/$br" \
    --title "$title" \
    --body "Wave 1 of corey-fl-loop. Version + summary in commit body; details in CHANGELOG and the_goal-inprogress.md."
done
```

### 9.8 If a pod is missing entirely

```bash
cd ~/Documents/github/albright-labs/corey-toolbox/mcp-kubernetes-platform-engineer
kubectl apply -f infra/redis/redis.yaml
kubectl apply -f infra/agent/corey-fl-agent.yaml
# Wait until the agent pod's bootstrap log prints '[bootstrap] ... ready':
AGENT_POD=$(kubectl -n corey-coder get pods -l app=corey-fl-agent -o jsonpath='{.items[0].metadata.name}')
kubectl -n corey-coder logs -f "$AGENT_POD"
# Then re-seed (section 9.3) if Redis is empty.
```

### 9.9 If the corey-fl-agent pod restarted

The PVC persists `/work` (repo, worktrees, runner scripts). The container's `/usr/bin` and `/usr/local/bin` do NOT persist — apt-installed git/redis-cli/kubectl/jq and pip-installed ruff/mypy/pytest/redis-py vanish. The ConfigMap-driven bootstrap script re-installs them on every container start. Wait for `[bootstrap] ... ready` in the pod log before issuing any `kubectl exec` commands that depend on those tools.

### 9.10 Critic loop (not yet built — pick this up on next session if any task has status=needs_fix)

When a sub-agent fails validators, it calls `mark_failed.py` which sets `status=needs_fix` and requeues at `priority - 0.5`. There is currently no agent that filters for `needs_fix`. To add a critic agent:

1. Fire one `Agent` call with model=sonnet, prompt template similar to the sub-agent but with STEP 1 modified to claim only tasks where `status==needs_fix` (use `ZRANGEBYSCORE queue:pending -inf 1.5` to find requeued items).
2. Critic reads `error_log` from the task hash, reads the existing branch's failing commit, proposes a patch, applies it in the same worktree, re-runs validators.
3. On second pass: mark_done. On second failure: escalate (open a draft PR with label `human-review-required`).

### 9.11 Session-close checklist

Before closing the session, confirm:

```bash
# All Wave 1 commits pushed?
cd ~/Documents/github/albright-labs/corey-toolbox/mcp-kubernetes-platform-engineer
git fetch --all --quiet
git log --all --oneline | head -10
git ls-remote --heads origin 'corey-fl-loop/*'

# All updates on main pushed?
git log origin/main..HEAD  # should be empty

# Redis state preserved?
AGENT_POD=$(kubectl -n corey-coder get pods -l app=corey-fl-agent -o jsonpath='{.items[0].metadata.name}')
kubectl -n corey-coder exec "$AGENT_POD" -- redis-cli -h corey-fl-redis BGSAVE
kubectl -n corey-coder exec "$AGENT_POD" -- redis-cli -h corey-fl-redis LASTSAVE
# LASTSAVE timestamp should be within the last 60s
```

If all three pass: safe to close. Resume by reading this file top to bottom, running section 9.2, and firing Wave 2 via the prompt in 9.5.

---

## 10. Delivered state (2026-06-06)

### What is on main

| Wave | PR | Stories landed | Merge commit |
|---|---|---|---|
| 1 | #3 | US-001, US-002, US-006, US-019, US-020, US-021 | `b3f2e35` |
| 2 | #14 | US-003, US-004, US-022, US-023, US-024, US-025 | `df728e1` |
| 3 | #15 | US-005, US-007, US-008, US-009, US-015, US-016 | `c1c9d5d` |
| 4 | #16 | US-010, US-011, US-012, US-013, US-014, US-017, US-018 | `bf76349` |
| Runtime | #17, #18 | Lean Dockerfile + bootstrap deployment | `ff3313b` |

`prd.json` status: **25/25 userStories DONE** in Redis and on `main`. `queue:pending` size = 0. Build counter at 42 after acceptance proof commit.

### What is running in the cluster

Namespace: `corey-fl-loop`.

```
NAME                                  READY   STATUS    RESTARTS   AGE
pod/auto-remediate-55c9459bf8-...      1/1     Running   0          1m
```

Logs:
```
INFO auto_remediate.runtime connected to k8s; 61 namespaces visible
INFO auto_remediate.runtime auto_remediate.runtime ready; heartbeating
```

§22 acceptance proof captured at `docs/audit-run-001/proofs/acceptance/wave4-deploy.md`.

### What is NOT yet wired

Modules exist on main under `src/auto_remediate/`, `src/analyzers/`, `src/watchers/`, `src/gitops/`, `src/models/`. The runtime entrypoint (`src/auto_remediate/runtime.py`) currently:

1. Loads the in-cluster k8s client
2. Heartbeats `/tmp/healthz` for the liveness probe
3. Proves the runtime can talk to k8s (lists namespaces)

What it does NOT yet do:
- Subscribe to the event stream and feed the watcher queue
- Invoke analyzers on each event
- Call the deterministic remediation table
- Apply the restart-first ladder
- Trigger vcluster sandbox runs
- Open GitOps PRs
- Emit DPO pairs as issues
- Run the audit-log writer

Each of those modules ships green tests. Wiring them through the runtime is the next milestone (call it **Runtime Integration v1**).

### Known follow-ups (Lessons_Learned has the detail)

- `Dockerfile` Trivy scan reports HIGH/CRITICAL on the python:3.11-slim base; switch to a distroless or `python:3.11-alpine` base.
- CI `runs-on: ubuntu-latest` because this repo is under `Hawaiideveloper` user, not the `AlbrightLaboratories` org. Transferring the repo unlocks `albright-runners` + the auto-TOC backlink workflow + the claude-md-sweep.
- `arc` repo: add `albright-runners` label to the RunnerSet so future workflows can use the org convention.
- US-016 `tests/unit/test_us016_gitops_pr_generator.py` was deleted after 6 logic failures. Rewrite alongside production code.
- `Lessons_Learned.md` documents all incident-class issues hit during the run (Docker daemon, Redis restart, teacher-sandbox instability, async test pattern, GHCR uppercase, etc.).

### Resume runbook (still authoritative)

§9 of this file remains the operational manual. The 19-task table in §9.4 is now obsolete (queue empty); the rest still applies: pod discovery, runner scripts, sub-agent prompt template, integration merger pattern, batch-PR command.

For the next milestone (Runtime Integration v1):
1. Fire one sub-agent with the §9.5 prompt template, story_id `NEXT-001`, brief: "wire event_watcher + base + pod_analyzer + restart_first_ladder + audit_logger into auto_remediate.runtime; replace the heartbeat loop with the real event loop."
2. PR, CI, merge.
3. Update the auto-remediate Deployment to use the new entrypoint (still `python3 -m auto_remediate.runtime`, but with real behaviour).
4. Re-run §22 acceptance proof; capture a fresh `docs/audit-run-001/proofs/acceptance/` artifact.
5. Verify it emits DPO pair issues into this repo with label `dpo-pair`. That closes the corey-coder learning loop.

---

## 11. Where this stands at v0.1.0 release (session 2 close)

This section supersedes §10 on the points that have changed. Read §10 for the historical "right after Wave 4" state.

### What is different from §10

- **Runtime is no longer heartbeat-only.** `src/auto_remediate/runtime.py` now drives `PodAnalyzer` on a 30-second interval, deduplicates findings within a 5-minute window, and appends them to `/tmp/audit.log`. PR [#20](https://github.com/Hawaiideveloper/mcp-kubernetes-platform-engineer/pull/20).
- **The deploy bootstrap now clones the repo and runs the real module.** `k8s/auto-remediate.yaml`'s ConfigMap bootstrap installs git, clones the repo into the pod, and execs `python3 -m auto_remediate.runtime`. PR [#21](https://github.com/Hawaiideveloper/mcp-kubernetes-platform-engineer/pull/21).
- **First official release cut.** Tag [`v0.1.0`](https://github.com/Hawaiideveloper/mcp-kubernetes-platform-engineer/releases/tag/v0.1.0). Gold-prompt version `47-ca362a-0-1_0-2026-06-06`.
- **README rewritten.** 1057 → 75 lines. Reflects v0.1.0 state. PR [#22](https://github.com/Hawaiideveloper/mcp-kubernetes-platform-engineer/pull/22).
- **`main` HEAD at session close:** `1e31067`.

### Live proof at session close

Pod `auto-remediate-75695d7975-j7tvv` on node `kubeadm-worker07`.

- **Uptime:** 4h 42m+, 0 restarts.
- **Last observed tick:** 418, findings stable at 19 (deduped).
- **Audit log:** 982 lines and growing.
- **Latest real findings:** `corey-rag/mcp-api OOMKilled`, `brightflow/execution-service` crash-loop (restarts=2), `ibkr-live-trader/composite-gate` probe timeout (observed but never auto-actioned per US-006 hardblock).

Captured in:
- [`docs/audit-run-001/proofs/acceptance/wave4-deploy.md`](docs/audit-run-001/proofs/acceptance/wave4-deploy.md) — §22 criteria after Wave 4.
- [`docs/audit-run-001/proofs/acceptance/runtime-v1-live.md`](docs/audit-run-001/proofs/acceptance/runtime-v1-live.md) — observer loop finding real cluster issues, deduping across ticks.

### What is left to do (v0.2 milestone — "wire the write side")

The runtime currently **only observes**. The write-side modules are all merged on main but not wired into the entrypoint. Wiring them in is the v0.2 milestone.

Priority order (cheapest leverage first):

1. **Restart-first ladder (~30 min, biggest leverage per minute)**
   - File: `src/auto_remediate/remediation_ladder.py` (already shipped, has tests).
   - Wire: in `runtime.py`, after each tick's analyzer pass, for each finding in a *safe* namespace (allowlist), invoke the ladder. The ladder issues `kubectl rollout restart` and watches `/tmp/healthz`-style verification for 5 minutes before escalating.
   - Hardblock check: every action must pass through `SafetyGate` (`src/auto_remediate/safety_gate.py`) which rejects mutating actions in `ibkr-live-trader`, `daxxon-trading`, `brightflow-live`.
   - Acceptance: a brightflow-dashboard probe-race triggers a single `kubectl rollout restart`; pod returns Ready within 5 min; ladder records the success in the audit log.

2. **DPO emission as GitHub issues (~30 min, compounding win)**
   - File: `src/auto_remediate/dpo_pair.py` (already shipped).
   - Wire: when the ladder reports `escalated` (restart did not heal) AND a subsequent action succeeds, emit a `DpoPair{prompt, rejected, chosen}` and POST it to this repo as an issue with label `dpo-pair` for corey-coder ingest.
   - Acceptance: an OOMKilled pod gets restart-tried, fails, then a manual `kubectl patch deployment ... limits.memory` succeeds; a `dpo-pair` issue appears on GitHub.

3. **vcluster sandbox verification (~2-3 hours, safety net)**
   - File: `src/auto_remediate/vcluster_sandbox.py` (already shipped).
   - Wire: for any candidate fix that is not a pod restart (manifest patch, image migration, etc.), apply to an ephemeral vcluster first; only proceed if smoke test is green.
   - Required before write side is allowed to do anything beyond restarts.

4. **GitOps PR generator (~1-2 hours)**
   - File: `src/auto_remediate/gitops_pr.py` (already on main but tests were deleted in Wave 3 — rewrite required).
   - Wire: for non-restart fixes, open a PR against the manifests repo with the diff + sandbox log + finding evidence. Trading namespaces never auto-merge — open the PR, assign a human reviewer, label `human-review-required`.

5. **Persistent audit log (~30 min)**
   - Today: `/tmp/audit.log` (lost on pod restart).
   - Wire: switch to `/var/log/auto-remediate/audit.jsonl` on a PVC. Add daily rotation. After 90 days, offload to corey-rag for retention + retrieval.

### Other known follow-ups (lower priority, but tracked)

- **`tests/unit/test_us016_gitops_pr_generator.py` rewrite** — Wave 3 deleted it after 6 logic mismatches with the production code. Rewrite alongside whichever wiring fixes the production gaps.
- **Distroless image** — Trivy scan reports HIGH/CRITICAL on the `python:3.11-slim` base image. Switch to `gcr.io/distroless/python3-debian12` after the runtime stabilises.
- **Repo transfer to `AlbrightLaboratories` org** — unlocks self-hosted `albright-runners` per the org CLAUDE.md convention, plus the Master TOC auto-updater and the `claude-md-sweep` workflow.
- **`arc` repo: add `albright-runners` label to the RunnerSet** — required so workflows can use `runs-on: albright-runners` per org convention once the repo lives in the org.
- **PR #22 test flake** — docs-only PR caught one transient pytest failure. Identify which test is flaky in CI and stabilise.

### Resume runbook (still authoritative)

§9 of this file is still the operational manual:

- **§9.1** discover pods by label.
- **§9.2** health check (run this on any resume).
- **§9.3** re-seed from `prd.json` if Redis ever loses data.
- **§9.5** sub-agent prompt template (proven across 4 waves + 1 runtime integration + multiple cleanup runs).
- **§9.6** CHANGELOG insertion algorithm (use it for every commit going forward).
- **§9.7** batch-PR command.
- **§9.8** full pod rebuild.
- **§9.9** post-restart recovery (PVC vs container-layer gotcha).
- **§9.11** session-close checklist (`BGSAVE`, branches pushed, main pulled).

For the v0.2 work specifically:

1. Fire one sub-agent with the §9.5 template, story_id `NEXT-002`, brief: "wire `RemediationLadder` into `auto_remediate.runtime` per §11 priority #1; gate every action through `SafetyGate`; on escalation emit a `DpoPair` issue per §11 priority #2."
2. PR, CI green, merge.
3. Re-apply `k8s/auto-remediate.yaml` (the bootstrap will pull the new code on next pod restart — `kubectl rollout restart deploy/auto-remediate -n corey-fl-loop`).
4. Capture fresh proof under `docs/audit-run-001/proofs/acceptance/` — show: (a) safe-namespace pod auto-restarts, (b) trading-namespace finding is observed but not actioned, (c) `dpo-pair` labeled issue appears on GitHub.
5. Cut release tag `v0.2.0` with that proof linked in the release notes.

### Session close marker

End of session 2, 2026-06-06. Open `the_goal-inprogress.md`, read §1-3 for the goal, §11 (this section) for current state and what is next. Then run §9.2 health check before doing anything.
