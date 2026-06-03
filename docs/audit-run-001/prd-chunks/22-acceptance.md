# PRD Section 22 — Acceptance Criteria and Definition of Done

## Overview

A story is not DONE until it is deployed and every criterion below is simultaneously green
in a live or staging cluster. No exceptions. The exact commands and expected output
substrings below are the authoritative verification record.

---

## Criterion 1 — Unit Tests Pass with Coverage Gate

```
pytest -v --cov=src --cov-report=term-missing --cov-fail-under=80
```

Required output substrings: `passed`, `TOTAL ... 80%` (or higher).
Exit code must be `0`. Tests that mock the method under test do not count toward coverage.

---

## Criterion 2 — Linting Passes Clean

```
ruff check .
```

Required output: `All checks passed!`
Exit code must be `0`. No `noqa: ALL` or blanket `per-file-ignores` suppressions permitted.

---

## Criterion 3 — Type Checking Passes Clean

```
mypy src/
```

Required output substring: `Success: no issues found`
Exit code must be `0`. Type stubs for `kubernetes`, `loguru`, and `pydantic` must be
installed. `--ignore-missing-imports` is not a substitute.

---

## Criterion 4 — Docker Image Builds and Passes Security Scan

```
docker build -t mcp-k8s-pe:ci .
trivy image --exit-code 1 --severity HIGH,CRITICAL mcp-k8s-pe:ci
```

Required build output: `Successfully built` or (BuildKit) `writing image sha256:`
Required trivy output: `Total: 0 (HIGH: 0, CRITICAL: 0)`
Trivy exit code must be `0`. Base image must be pinned (not `latest`). Scan runs against
the locally built tag, not a pulled remote image.

---

## Criterion 5 — Manifest Applies and Pod Reaches Ready Within 60s

```
kubectl apply -f k8s/
kubectl wait --for=condition=Ready pod -l app=mcp-k8s-pe \
  -n mcp-platform --timeout=60s
```

Required apply output: at least one `configured` or `created` line.
Required wait output: `pod/mcp-k8s-pe-... condition met`
Exit code must be `0` for both. `timed out waiting for the condition`,
`CrashLoopBackOff`, or `ImagePullBackOff` during wait fails this criterion.

---

## Criterion 6 — Real Kubernetes API Call Is Wired and Exercised

**Check 6a — source contains the real call:**

```
grep -rn "list_namespaced_pod" src/
```

Required: at least one match such as `src/kubernetes_manager.py:NN: ... list_namespaced_pod(`
Zero matches means the client is not wired; criterion fails.

**Check 6b — integration test log confirms the call at runtime:**

```
pytest -v -m integration --log-cli-level=DEBUG 2>&1 | grep "list_namespaced_pod"
```

Required: at least one output line containing `list_namespaced_pod` from an actual API
response path, not from a mock setup line. A test that mocks `list_namespaced_pod` does
not satisfy this check.

---

## Criterion 7 — End-to-End Ladder Completes a Full Cycle

**Setup:**

```
kubectl create namespace scratch-remediation-test 2>/dev/null || true
kubectl run crash-test --image=busybox --restart=Always \
  --command -- sh -c 'exit 1' -n scratch-remediation-test
```

**Run remediator:**

```
python -m src.remediator \
  --namespace scratch-remediation-test \
  --watch-minutes 5 \
  --session-log /tmp/remediation-session.json \
  2>&1 | tee /tmp/remediation-stdout.txt
```

**Verification commands and required output:**

```
grep "restart_issued"  /tmp/remediation-stdout.txt   # at least one match
grep "watchdog"        /tmp/remediation-stdout.txt   # at least one match
grep "escalated"       /tmp/remediation-stdout.txt   # at least one match (pod never recovers)
grep "dpo_pair"        /tmp/remediation-stdout.txt   # at least one match
```

```
python3 -c "
import json, sys
s = json.load(open('/tmp/remediation-session.json'))
assert 'session_id' in s
assert len(s.get('audit_log', [])) >= 3
assert s.get('final_state') == 'ESCALATED'
print('session_id:', s['session_id'])
print('audit_entries:', len(s['audit_log']))
print('final_state:', s['final_state'])
"
```

Required output:
```
session_id: <UUID>
audit_entries: <N>=3 or greater
final_state: ESCALATED
```

The python3 assertion script exit code must be `0`. Missing `final_state` means the audit
logger is not wired; criterion fails. Trading namespace guard also verified here:

```
python -m src.remediator --namespace ibkr-live-trader --dry-run 2>&1 \
  | grep "ProtectedNamespaceError"
```

Required: at least one line containing `ProtectedNamespaceError`.

---

## Criterion 8 — No Unresolved Pods in Allowlisted Namespaces

After Criterion 7 completes and the scratch namespace is deleted:

```
kubectl delete namespace scratch-remediation-test --wait=true
kubectl get pods -A \
  | grep -E "^(staging|mcp-platform)\s" \
  | grep -v "Running" \
  | grep -v "Completed" \
  | grep -v "STATUS"
```

Required output: empty (zero lines). A grep exit code of `1` (no matches) is the passing
state. Any pod name in the output fails this criterion.

---

## Criterion 9 — No Warning Events for 30 Minutes Post-Deploy

Run 30 minutes after Criterion 5 completes:

```
kubectl get events -A --field-selector type=Warning \
  --sort-by='.lastTimestamp' -o json \
  | python3 -c "
import json, sys, time
data = json.load(sys.stdin)
allowed_ns = {'mcp-platform', 'staging'}
warnings = [
    e for e in data.get('items', [])
    if e.get('type') == 'Warning'
    and e.get('involvedObject', {}).get('namespace') in allowed_ns
]
print('Warning event count:', len(warnings))
for e in warnings:
    print(' -', e.get('reason'), e.get('message','')[:80])
sys.exit(1 if warnings else 0)
"
```

Required output: `Warning event count: 0`
Exit code must be `0`. Events outside `mcp-platform` and `staging` are excluded.

---

## Criterion 10 — All Checklist.md Boxes Ticked

```
python3 -c "
import re, pathlib, sys
text = pathlib.Path('Checklist.md').read_text()
unchecked = re.findall(r'- \[ \]', text)
checked   = re.findall(r'- \[x\]', text, re.IGNORECASE)
print(f'Checked:   {len(checked)}')
print(f'Unchecked: {len(unchecked)}')
sys.exit(1 if unchecked else 0)
"
```

Required output:
```
Checked:   <N>
Unchecked: 0
```
Exit code must be `0`. `Checklist.md` must be committed to the repo root and reflect actual
state, not aspirational state.

---

## Iteration Loop — Phase E Protocol

Phase E re-runs all ten criteria after each implementation batch.

1. Run criteria 1 through 10 in order. Record pass/fail with exact command output.
2. For each failure, extract the specific failing evidence (test names, file paths, CVE IDs,
   event names, unchecked items).
3. File each failure as a re-queued implementation task with the exact output attached.
4. Implement the fix. Commit. Re-run all ten criteria from criterion 1.
5. Repeat up to **5 iterations**. After iteration 5, if any criterion is still failing,
   escalate to the human operator: post to the project discussion thread with the title
   `[ESCALATION] Phase E iteration 5 — criteria <N> still failing — human review required`,
   attaching the full command output for every failing criterion. Stop automated iteration.

All ten criteria must be simultaneously green in the same run. A run where 9 pass but
`Checklist.md` has unchecked items is a failing run.

---

## Checklist.md (repo root template — initialize with all boxes unchecked)

```markdown
# Checklist — mcp-kubernetes-platform-engineer

Last updated: YYYY-MM-DD

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
```
