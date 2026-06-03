# Section 16 — GitOps Auto-PR Generation

## Context

Findings `behavior:gitops_pr_generation` (high, medium x2, info) and `behavior:safety_allowlist`
(high x3, info) share a root cause: the remediator has no path from a verified fix to a
mergeable manifest change in a GitOps repo. `execute_remediation` in
`src/k8s_manager.py:166-210` accepts any namespace and any target with no gating — no PR,
no audit trail, no namespace policy.

The invariant enforced by this section: every fix the auto-remediator proposes is expressed as
a manifest diff committed to a GitOps repo. ArgoCD or Flux applies the diff to the cluster.
The remediator never calls `kubectl apply` outside an ephemeral vcluster sandbox.

---

## 1. Architecture

```
Finding + SandboxResult
        |
        v
GitOpsPRGenerator.create_pr()
  1. load repo config for namespace (config/safety.yaml)
  2. git clone <gitops-repo>  (ephemeral, discarded after push)
  3. write patched manifest to canonical path in clone
  4. git commit -m "[auto-remediate] ..."
  5. git push origin <branch>
  6. gh pr create  (or comment if PR already open)
  7. if auto-merge eligible: gh pr merge --auto --squash
        |
        v
ArgoCD / Flux observes repo -> applies diff to cluster
```

The remediator pod holds no persistent git checkout between runs.

---

## 2. Target Repo Configuration

Configured in `config/safety.yaml` under the `gitops` key. No hardcoded defaults — the
operator must supply `default_repo`.

```yaml
gitops:
  default_repo: "https://github.com/AlbrightLaboratories/k8s-manifests.git"
  default_base_branch: "main"

  repo_overrides:
    ibkr-live-trader:
      repo: "https://github.com/AlbrightLaboratories/ibkr-real-money-gateway.git"
      base_branch: "main"
      policy: "pr-only"
      assignee: "corey-albright"

    daxxon-trading:
      repo: "https://github.com/AlbrightLaboratories/daxxon-trading.git"
      base_branch: "main"
      policy: "pr-only"
      assignee: "corey-albright"

    brightflow-live:
      repo: "https://github.com/AlbrightLaboratories/brightflow-live.git"
      base_branch: "main"
      policy: "pr-only"
      assignee: "corey-albright"
```

`policy: "pr-only"` means the PR is opened and never auto-merged regardless of any other gate
condition. The trading-repo entries mirror the trading-namespace hardblock (Section 06) and the
org safety rule: never push main of `brightflow-live`, `ibkr-real-money-gateway`, or
`daxxon-trading` even under broad fix authorization.

---

## 3. PR Title Format

```
[auto-remediate] ns/<ns> <kind>/<name>: <fix-class>
```

Examples:

```
[auto-remediate] ns/staging deployment/api-server: probe-fix
[auto-remediate] ns/ibkr-live-trader statefulset/ib-gateway: resource-limit
```

Total length must not exceed 120 characters. Truncate `<name>` with `...` if needed.
`<fix-class>` must be a value from the deterministic table (Section 6).

---

## 4. PR Body Template

The literal template rendered by `GitOpsPRGenerator`. All `{{ }}` fields are filled at runtime.

```markdown
## Auto-Remediation Report

**Finding ID:** `{{ finding_id }}`
**Severity:** `{{ severity }}`
**Namespace:** `{{ namespace }}`
**Resource:** `{{ kind }}/{{ name }}`
**Fix class:** `{{ fix_class }}`
**Sandbox verified:** `{{ sandbox_green }}`

---

## Evidence

### Kubernetes Events

```
{{ events_block }}
```

### Relevant Logs (last 100 lines)

```
{{ logs_block }}
```

---

## Proposed Manifest Diff

```diff
{{ manifest_diff }}
```

---

## Sandbox Run

**Sandbox log:** {{ sandbox_log_url }}

**Smoke-test result:**

```
{{ smoke_test_output }}
```

**Verdict:** {{ sandbox_verdict }}

---

## Review Checklist

- [ ] Diff is consistent with described fix class
- [ ] No unrelated files changed
- [ ] Smoke-test output confirms the symptom is resolved
- [ ] Change is safe to apply to the live namespace

<!-- auto-remediate:finding_id={{ finding_id }} fix_id={{ fix_id }} -->
```

The HTML comment on the last line is the machine-readable idempotency key (Section 7).

---

## 5. Labels

Labels are created in the target repo if absent (`gh label create --force`).

| Label                      | Applied when                                                |
|----------------------------|-------------------------------------------------------------|
| `auto-remediate`           | Always                                                      |
| `severity/<s>`             | Matches `finding.severity`                                  |
| `fix-class/<c>`            | Matches `finding.fix_class`                                 |
| `sandbox-verified/true`    | `sandbox_result.verdict == "healed"`                        |
| `sandbox-verified/false`   | `sandbox_result.verdict != "healed"`                        |
| `human-review-required`    | Trading namespace OR non-deterministic fix-class OR sandbox red |

---

## 6. Auto-Merge Gate

A PR is eligible for auto-merge only when all five conditions hold simultaneously:

1. `sandbox_result.verdict == "healed"`
2. Namespace is in `ALLOWED_AUTO_MERGE_NAMESPACES` (env var, comma-separated, default empty)
3. `fix_class` is in the deterministic set:
   `{"probe-fix", "resource-limit", "image-tag", "replica-count", "annotation-patch"}`
4. The PR has received no human review request
5. The target repo `policy != "pr-only"`

Auto-merge is enacted by:

```bash
gh pr merge --auto --squash --delete-branch <pr_number> --repo <repo>
```

`--auto` delegates merge timing to GitHub's required-checks gate; the remediator does not poll.

### Trading-Namespace Rule

For any namespace matched by the trading-namespace list (exact or pattern, per Section 06):

- PR is opened with the standard body.
- `gh pr merge` is **never** called.
- Label `human-review-required` is added.
- Assignee is set from `config/safety.yaml`: `gh pr edit <pr_number> --add-assignee <assignee>`.
- The finding's `auto_merge_eligible` is stored as `False` in the PR idempotency record so
  subsequent runs cannot escalate it.

---

## 7. Idempotency

The same `(finding_id, fix_id)` pair opens at most one PR. Subsequent runs comment on the
existing PR.

```python
IDEMPOTENCY_MARKER = "<!-- auto-remediate:finding_id={fid} fix_id={xid} -->"

def find_existing_pr(repo: str, finding_id: str, fix_id: str) -> dict | None:
    marker = IDEMPOTENCY_MARKER.format(fid=finding_id, xid=fix_id)
    out = subprocess.run(
        ["gh", "pr", "list", "--repo", repo, "--state", "open",
         "--search", f'"{marker}" in:body', "--json", "number,url"],
        capture_output=True, text=True, check=True,
    ).stdout
    prs = json.loads(out)
    return prs[0] if prs else None
```

If a PR is found, a re-run comment is posted via `gh pr comment` containing: timestamp, new
sandbox verdict, any change in evidence, and whether the verdict changed since last run.

---

## 8. Dry-Run Mode

Activated by `dry_run=True` or `GITOPS_DRY_RUN=true`. In dry-run mode:

- No `gh` calls are made.
- The PR title and full body are written to stdout.
- `PRResult.pr_url == "dry-run://not-created"`, `pr_number == 0`.
- Exit code is 0 on success, non-zero on template rendering failure.

```bash
GITOPS_DRY_RUN=true python -m src.gitops.pr_generator \
  --finding-id BEH-016 --namespace staging \
  --kind Deployment --name api-server \
  --fix-class probe-fix --sandbox-verdict healed
```

---

## 9. Implementation Sketch

`src/gitops/pr_generator.py` uses the `gh` CLI exclusively (not PyGithub) so that
authentication is handled by the existing `GH_TOKEN` environment variable with no additional
Python dependency.

Key signatures:

```python
@dataclass
class PRResult:
    pr_url: str
    pr_number: int
    was_existing: bool
    auto_merge_eligible: bool

async def create_remediation_pr(
    finding: Finding,
    fix_id: str,
    sandbox: SandboxResult,
    dry_run: bool = False,
) -> PRResult: ...
```

Internal flow: load config -> build title and body -> idempotency check -> ensure labels exist
-> `gh pr create` -> if `auto_merge_eligible`: `gh pr merge --auto --squash`.

---

## 10. Tests

`tests/unit/test_gitops_pr_generator.py` — `gh` CLI mocked via
`unittest.mock.patch("src.gitops.pr_generator.subprocess.run")`.

| Test name                                    | Assertion                                                     |
|----------------------------------------------|---------------------------------------------------------------|
| `test_dry_run_emits_to_stdout`               | Title and body on stdout; no subprocess calls                 |
| `test_title_format`                          | Exact format; len <= 120                                      |
| `test_title_truncation`                      | 100-char name truncated with `...`; len <= 120                |
| `test_labels_include_severity_and_fix_class` | `severity/high`, `fix-class/probe-fix`, `sandbox-verified/true` present; `human-review-required` absent for allowlisted sandbox-green |
| `test_trading_namespace_never_auto_merged`   | No `gh pr merge` call; `human-review-required` label present; assignee set |
| `test_idempotency_comments_on_existing_pr`   | Second call posts comment, no `gh pr create`                  |
| `test_sandbox_red_blocks_auto_merge`         | `auto_merge_eligible == False`; no `gh pr merge` call         |
| `test_nondeterministic_fix_class_blocks_merge` | `fix_class="rewrite"` -> `auto_merge_eligible == False`     |

---

## 11. Acceptance Criteria

| ID   | Criterion                                                                                     |
|------|-----------------------------------------------------------------------------------------------|
| AC-1 | Every proposed fix reaches the cluster as a GitOps PR diff; `kubectl apply` never called outside sandbox |
| AC-2 | Trading namespaces (`ibkr-live-trader`, `daxxon-trading`, `brightflow-live`) open a PR and never auto-merge |
| AC-3 | PR title matches `[auto-remediate] ns/<ns> <kind>/<name>: <fix-class>`                      |
| AC-4 | PR body contains finding ID, events, logs, diff, sandbox log URL, smoke-test output, and idempotency key |
| AC-5 | Same `(finding_id, fix_id)` on second run comments on existing PR; no duplicate PR opened    |
| AC-6 | Sandbox-red findings never auto-merge; `human-review-required` label applied                 |
| AC-7 | `GITOPS_DRY_RUN=true` emits full PR body to stdout; zero `gh` subprocess calls               |
| AC-8 | Non-deterministic fix classes (`rewrite`, `design`) block auto-merge regardless of namespace |
