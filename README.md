<!-- toc-backlink -->
> 📚 **Master TOC:** [Org-wide repo index](https://github.com/AlbrightLaboratories/daxxon-ai-gpu-01/issues/17) — auto-updated every 15 min from this repo's commit stream. No manual entry needed; just write commit subjects that read well as one-line bullets.

# corey-fl-loop — autonomous Kubernetes auto-remediator

> **Status: v0.1.0 — observer live in cluster.**
> Runtime is deployed in namespace `corey-fl-loop`, the observer loop finds real cluster issues on a 30s interval, and the write side (restart, GitOps PR, DPO) is the next milestone.

---

## What this is

A self-improving Kubernetes auto-remediator that beats `k8sgpt` on the whole remediation loop — diagnose, sandbox-verify, GitOps-gated fix, DPO learning — not just the diagnose step.

The full goal, architecture, and resume runbook are in [`the_goal-inprogress.md`](the_goal-inprogress.md). Read that first.

## What it does today (v0.1.0)

- Connects to the in-cluster Kubernetes API via a read-only ServiceAccount.
- Runs an analyzer loop on a 30-second interval against all namespaces.
- Emits structured findings (`namespace/kind/name`, severity, category, fingerprint, message) for ImagePullBackOff, CrashLoopBackOff, OOMKilled, probe failures, FailedMount, and more.
- Deduplicates findings within a 5-minute rolling window.
- Appends each finding to `/tmp/audit.log`.
- Survives pod restart cleanly (PVC + bootstrap re-establishes tooling).
- Observes trading namespaces (`ibkr-live-trader`, `daxxon-trading`, `brightflow-live`) but never acts on them — enforced by `SafetyGate` per US-006.

## What it does NOT do yet

No write actions. The restart-first ladder, GitOps PR generator, vcluster sandbox verifier, DPO issue emission, and persistent audit log are all merged as modules on `main`, but the runtime entrypoint does not yet wire them into the loop. That is the v0.2 milestone.

## Deploy

```bash
kubectl apply -f k8s/auto-remediate.yaml
kubectl -n corey-fl-loop rollout status deploy/auto-remediate --timeout=180s
kubectl -n corey-fl-loop logs deploy/auto-remediate --tail=30
```

Expected after ~3 minutes: tick=1 findings=N where N is the number of distinct cluster issues currently visible.

## Tear down

```bash
kubectl delete -f k8s/auto-remediate.yaml
```

## Architecture (one paragraph)

A read-only ServiceAccount-backed Deployment in namespace `corey-fl-loop`. The pod runs `python3 -m auto_remediate.runtime`, which loads the in-cluster k8s client and drives `PodAnalyzer` (and, in the v0.2 milestone, the rest of the analyzer set) on a 30s interval. Findings are deduplicated by fingerprint within a 5-minute window and logged to stdout + `/tmp/audit.log`. The companion infrastructure — `corey-fl-redis` (24h task queue), `corey-fl-agent` (orchestration pod) — lives in `corey-coder`.

## Code layout

```
src/
  auto_remediate/        # runtime, ladder, watchdog, NIM backend, DPO, audit, safety
  analyzers/             # Pod, Service, Ingress, PVC, Node, Deployment, RS, STS,
                         #   CronJob, NetPol, PDB, HPA — k8sgpt-parity, plus the
                         #   orphan-job cleaner for the manual-cw5-003 class
  watchers/              # event stream + classifier
  gitops/                # PR generation
  models/                # Finding, DPO pair, validator results
infra/
  redis/redis.yaml       # corey-fl-redis (corey-coder ns)
  agent/corey-fl-agent.yaml  # orchestration pod for sub-agents
k8s/
  auto-remediate.yaml    # runtime Deployment + RBAC + namespace
  rbac/                  # four-identity RBAC split (reader / applier / sandbox / pr-bot)
scripts/runner/          # claim_task, mark_done, mark_failed, heartbeat
tests/unit/              # Wave 1-4 unit tests
docs/audit-run-001/      # 50-agent audit (480 findings), 25-section PRD, proofs
```

## Acceptance proofs

- [`docs/audit-run-001/proofs/acceptance/wave4-deploy.md`](docs/audit-run-001/proofs/acceptance/wave4-deploy.md) — §22 acceptance criteria after Wave 4 (all 25 stories merged, runtime Ready).
- [`docs/audit-run-001/proofs/acceptance/runtime-v1-live.md`](docs/audit-run-001/proofs/acceptance/runtime-v1-live.md) — runtime observer loop live in cluster, finding real issues, deduping across ticks.

## Versioning

- Pre-release commits: `Alpha-{build}-{sha6}-{maj}-{min}_{patch}-{date}`.
- Release commits: `{build}-{sha6}-{maj}-{min}_{patch}-{date}` (no `Alpha-` prefix).
- Every commit must update `CHANGELOG.md` and include the version string in the commit body.
- Build number is monotonic, stored in `corey-fl-redis` (`build_counter`), incremented atomically by sub-agents and by manual commits.

## Releases

- [v0.1.0](https://github.com/Hawaiideveloper/mcp-kubernetes-platform-engineer/releases/tag/v0.1.0) — observer live in cluster.

## Lessons learned

[`Lessons_Learned.md`](Lessons_Learned.md) — every failure that cost more than one retry, with root cause and prevention. Required reading before extending the runtime.

## Contributing

This repo is driven by `prd.json`. New work lands as user stories there, gets claimed atomically from `corey-fl-redis` by sub-agents in `corey-fl-agent`, ships as a feature branch + PR, merges via the integration merger pattern. The full operational manual is in [`the_goal-inprogress.md`](the_goal-inprogress.md) §9.

## License

MIT.
