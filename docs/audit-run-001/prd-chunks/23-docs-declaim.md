# PRD Section 23: Documentation De-Claim + Master TOC Backlink

## Context

Multiple reviewers independently flagged the same documentation failures:
all manager classes return hardcoded stub data, yet the docs claim production
deployment, 390 tests, 45,720+ live-indexed issues, 99.9% uptime, and hardcoded
lab IPs as generic instructions. Every overclaim listed below is cited directly
from `docs/audit-run-001/all-findings.json` (kind=doc entries).

---

## 1. Find-and-Strip: Overclaims by File

### README.md

| Line | Current text | Replacement |
|------|-------------|-------------|
| 58 | `Production Ready: Successfully deployed in both Docker containers and Kubernetes clusters with full authentication, persistent storage, and comprehensive documentation integration (1,029+ official Kubernetes reference files).` | `Status: Alpha -- diagnose-only. All manager methods return stub data. No Kubernetes API client is loaded. See /docs/audit-run-001/ for details.` |
| 56 | `monitors 17+ major Kubernetes repositories and automatically updates its knowledge base every hour` | `intends to monitor Kubernetes repositories (polling loop not yet implemented)` |
| 82 | `Official Kubernetes documentation (1,029+ files)` | `Kubernetes documentation (scraped at startup from kubernetes.io; count varies; empty until scrape completes)` |
| 120 | `Documentation: 1,029 official Kubernetes reference files integrated` | `Documentation: indexed at startup via HTTP scrape; no bundled corpus` |
| 150 | `Comprehensive Documentation - 1,029 official Kubernetes reference documents integrated` | `Documentation - scraped at startup; requires network; may be incomplete` |
| 202 | `Live Issue Database -- Monitors 17 major Kubernetes repositories with 45,720+ indexed issues` | `Issue Database -- populated at runtime via GitHub API (requires GITHUB_TOKEN; count unverified; may be 0 on cold start)` |
| 1101 | `Kubernetes Deployment: Successfully running on cluster at 172.100.10.107:30001` | Remove line entirely. |
| 1104 | `Documentation: 1,029 official Kubernetes reference files integrated` | `Documentation: scraped at startup; no bundled corpus` |
| 1109 | `External Health Check: curl http://172.100.10.107:30001/health` | Remove line entirely. The server runs stdio only; no HTTP listener exists. |

Evidence citations: `README.md:58`, `README.md:204`, `README.md:113-133`, `README.md:477-480`, `README.md:1101`, `README.md:1109`; corroborated by `k8s_manager.py:29`, `k8s_manager.py:49`.

### CHANGELOG.md

| Line | Current text | Replacement |
|------|-------------|-------------|
| 71 | `[1.0.0] - 2025-09-01 PRODUCTION READY RELEASE` | `[1.0.0] - 2025-09-01 DEVELOPMENT PREVIEW (stub implementation)` |
| 103 | `Complete test infrastructure with 390 comprehensive tests` | `Test scaffolding: 55 test functions across unit/ and production/ directories` |
| 104 | `Production-ready functional unit test suite covering all 45,720+ Kubernetes GitHub issues` | `Mock-based test suite validating response structure only; no real k8s API calls` |
| 184 | `390 Total Tests across 5 categories (Unit, Integration, Performance, Security, Production)` | `55 test functions across 2 categories (unit, production); integration/performance/security missing` |
| 327 | `Phase 3: Production Readiness COMPLETE` | `Phase 3: Production Readiness -- NOT COMPLETE -- see /docs/audit-run-001/` |
| 328 | `Comprehensive test suite (390 tests)` | `Test scaffolding only (55 tests, mock-based)` |
| 379 | `Service Availability: 99.9% uptime since deployment` | Remove line. No uptime tracking exists in the codebase. |
| 465 | `Test Coverage Enhancement - Expanded from basic tests to 390 comprehensive tests` | `Test scaffolding present; 55 test functions; integration/performance/security suites absent` |
| 488 | `Total Tests: 390 comprehensive tests` | `Total tests: 55 (pytest --collect-only verified)` |

Evidence citations: `CHANGELOG.md:71`, `CHANGELOG.md:83-88`, `CHANGELOG.md:103`, `CHANGELOG.md:328`, `CHANGELOG.md:379`, `CHANGELOG.md:490`; corroborated by `k8s_manager.py:29`, `mcp_server.py:640`.

### GETTING_STARTED.md

| Line | Current text | Replacement |
|------|-------------|-------------|
| 7 | `curl -fsSL https://raw.githubusercontent.com/your-org/mcp-kubernetes-platform-engineer/main/start.sh \| bash` | Replace `your-org` with `Hawaiideveloper` and add note: this installs and runs a stub server. |
| 141 | `45,720+ indexed Kubernetes GitHub issues` | `Issues indexed at runtime via GitHub API (count varies; requires GITHUB_TOKEN)` |
| 142 | `Real-time cluster analysis (if kubectl configured)` | `Cluster analysis (stub implementation; real API integration pending; see /docs/audit-run-001/)` |
| 147-152 | `server automatically updates its knowledge base every hour` and `Learns from community solutions` | Remove. No scheduler exists; no ML is implemented. |
| 163 | `Learns from community solutions` | Remove. Keyword matching only; no ML. |
| 201 | `curl http://localhost:3001/health` | Remove. The server is stdio-only; no HTTP listener on any port. |
| 219 | `curl http://localhost:3001/stats \| jq` | Remove. No /stats endpoint exists. |

Evidence citations: `GETTING_STARTED.md:141`, `GETTING_STARTED.md:142`, `GETTING_STARTED.md:149-153`, `GETTING_STARTED.md:70`, `GETTING_STARTED.md:201`, `GETTING_STARTED.md:219`.

### functional_unit_test.md

| Line | Current text | Replacement |
|------|-------------|-------------|
| 5 | `Based on analysis of 45,720+ closed Kubernetes GitHub issues` | Remove or replace with: `Based on mock-only test stubs; no live data source` |
| 31-36 | `75 Integration Tests ... Kubernetes API Integration -- 15 tests` | Remove. No integration test directory exists. |
| 57 | `TOTAL: 390 COMPREHENSIVE TESTS` | `TOTAL: 55 TEST FUNCTIONS (mock-based)` |
| 79 | `manager.analyze_issue_pattern()` | Mark as `[planned -- not yet implemented]`; method does not exist. |
| 279 | `doc_manager.get_solution_documentation()` | Mark as `[planned -- not yet implemented]`; method does not exist. |
| 298 | `doc_manager.get_best_practices_for_issue()` | Mark as `[planned -- not yet implemented]`; method does not exist. |
| 312 | `doc_manager.get_commands_for_issue()` | Mark as `[planned -- not yet implemented]`; method does not exist. |
| 331 | `manager.initialize_database()` | Mark as `[planned -- not yet implemented]`; method does not exist. |

Evidence citations: `functional_unit_test.md:57`, `functional_unit_test.md:31-36`, `functional_unit_test.md:79`, `functional_unit_test.md:279`.

### VSCODE_SETUP.md

| Line | Current text | Replacement |
|------|-------------|-------------|
| 38-50 | Config snippet points to `src/main.py --stdio` | Change to `src/mcp_server.py`; main.py runs HTTP, not stdio MCP. |
| 64 | Pressing Tab triggers Copilot suggestions powered by MCP | Remove. No code path supports tab-completion via MCP. |
| 69 | `References to actual GitHub issues and solutions` | `References to indexed GitHub issues (when GITHUB_TOKEN is set and DB is populated)` |
| 161 | `The MCP server will provide responses based on real GitHub issues and community solutions!` | `The MCP server returns stub data for cluster operations. GitHub issue search is available when GITHUB_TOKEN is configured.` |

Evidence citations: `VSCODE_SETUP.md:38-50`, `VSCODE_SETUP.md:64`, `VSCODE_SETUP.md:69`, `VSCODE_SETUP.md:161`.

### VSCODE_K8S_INTEGRATION.md

| Locations | Current text | Replacement |
|-----------|-------------|-------------|
| Lines 55, 121, 166, 255 | `curl http://172.100.10.107:30001/health` | Replace all with `curl http://<NODE_IP>:<NODE_PORT>/health` and add note: `/health` is only available when running `src/main.py` in HTTP mode, not the default stdio MCP mode. |
| 244 | `Health endpoint responds: {"status":"healthy",...}` | Qualify as HTTP-mode only; stdio mode has no health endpoint. |

Evidence citations: `VSCODE_K8S_INTEGRATION.md:55`, `VSCODE_K8S_INTEGRATION.md:121`, `VSCODE_K8S_INTEGRATION.md:166`, `VSCODE_K8S_INTEGRATION.md:255`, `VSCODE_K8S_INTEGRATION.md:244`.

### coming_soon.md

| Line | Current text | Replacement |
|------|-------------|-------------|
| Section header | `Metrics & Success Criteria` | `Target Metrics (Not Yet Measured -- Future State)` |
| 178-179 | `Code coverage maintained above 95%` / `Test coverage maintained above 95%` | `Target: 95%+ code coverage (current baseline: unmeasured)` |
| 195-196 | `API response time under 2 seconds for 99% of requests` | `Target: p99 < 2s (current baseline: not benchmarked)` |
| 199 | `Bug resolution time under 24 hours for critical issues` | `Target: < 24h for critical bugs (no SLA currently in effect)` |
| Top of file | (no disclaimer) | Add: `NOTE: All features listed in this document are aspirational. The current codebase contains stub implementations returning hardcoded data. No Kubernetes API calls are made.` |

Evidence citations: `coming_soon.md:179`, `coming_soon.md:196`, `coming_soon.md:200`.

---

## 2. Files to Delete Entirely

The following files must be removed. Each has been flagged by multiple reviewers
as either actively misleading or redundant. Deletion is preferred over correction
because the volume of false claims would require a near-total rewrite that
produces no additional value over the surviving documents.

| File | Reason | Reviewer citations |
|------|--------|-------------------|
| `K8S_ANNOUNCEMENT.md` | Marketing copy making at least four falsifiable production claims (hourly learning, automated remediation, 1,029+ docs, deep diagnostics) all contradicted by stub managers. No informational value that README does not cover. | 5 separate findings in all-findings.json |
| `TEST_SUITE_IMPLEMENTATION_SUMMARY.md` | Claims 390 tests; actual count is 55. Claims five test directories; only two exist. Claims full Kubernetes API integration; zero kubernetes client calls exist. Summary fabricates the state of the repo. | 5 separate findings |
| `coming_soon.md` | Presents aspirational SLA/coverage targets under a heading titled "Metrics & Success Criteria" with no disclaimer, implying they are current state. Full deletion preferred; roadmap items should move to GitHub Issues where they can be tracked honestly. | 4 separate findings |
| `GettingStarted.md` | Duplicate of `GETTING_STARTED.md`. Instructs users to `curl http://localhost:3001/health` (endpoint does not exist). Claims the server is "production-ready". The canonical file is `GETTING_STARTED.md`; delete this one. | 4 separate findings |

Deletion commands:

```
git rm K8S_ANNOUNCEMENT.md
git rm TEST_SUITE_IMPLEMENTATION_SUMMARY.md
git rm coming_soon.md
git rm GettingStarted.md
```

---

## 3. README.md Restructure Proposal

The current README.md is 1,114 lines and leads with marketing claims. After
applying the find-and-strip changes above, restructure as follows.

### Required header block (prepend verbatim, before all other content)

```
<!-- toc-backlink -->
> Master TOC: [Org-wide repo index](https://github.com/AlbrightLaboratories/daxxon-ai-gpu-01/issues/17) -- auto-updated every 15 min from this repo's commit stream. No manual entry needed; just write commit subjects that read well as one-line bullets.
```

### Status banner (immediately after the toc-backlink block)

```
> STATUS: Alpha -- diagnose-only / not production ready.
> All cluster-facing tools return stub/hardcoded data.
> No Kubernetes API client is initialized.
> See docs/audit-run-001/ for the full audit record.
```

### Proposed section order

1. `<!-- toc-backlink -->` block (verbatim, as above)
2. Status banner (as above)
3. Project title and one-sentence description
4. Quick start (real, verified steps only -- remove curl /health, remove lab IPs)
5. Architecture diagram (real -- show stdio MCP transport, show which managers
   are stubs vs functional)
6. MCP tools overview (accurate capability table: Functional / Partial / Stub)
7. Installation and configuration (keep; remove overclaims)
8. Contribution guide (add: how to replace a stub manager with a real
   implementation, how to run the 55 existing tests, how to add tests)
9. Known limitations (generated from the audit findings)
10. License

Sections to remove entirely from the current README:
- "Production Deployment Status" (Kubernetes Cluster Deployment)
- "Knowledge Growth Metrics"
- "Continuous Learning and Knowledge Evolution" (How It Works subsection)
- Any embedded curl examples targeting port 3001 or the lab IP

---

## 4. CHANGELOG.md: Phase 3 Rewrite

Replace the existing Phase 3 entry in CHANGELOG.md:

**Before (CHANGELOG.md:327-332):**
```
### Phase 3: Production Readiness COMPLETE
- [x] Comprehensive test suite (390 tests)
- [x] Issue pattern recognition for 45,720+ GitHub issues
- [x] Production-grade error handling and logging
- [x] Performance optimization and load testing
- [x] Security hardening and vulnerability testing
```

**After:**
```
### Phase 3: Production Readiness -- NOT COMPLETE -- see /docs/audit-run-001/

Audit run 001 (2026-06-02) found the following blockers:

- Test count: 55 functions across 2 directories (claimed 390 across 5)
- Kubernetes API client: not initialized in any manager (all stubs)
- HTTP REST endpoints: do not exist (server is stdio-only)
- Issue count: runtime-dependent, unverified (claimed 45,720+)
- Uptime claim: removed (no uptime tracking code exists)
- 3 of 5 test directories (integration/, performance/, security/) absent

Full findings: docs/audit-run-001/all-findings.json
```

Also replace the [1.0.0] release header:

**Before (CHANGELOG.md:71):**
```
## [1.0.0] - 2025-09-01 PRODUCTION READY RELEASE
```

**After:**
```
## [1.0.0] - 2025-09-01 DEVELOPMENT PREVIEW

NOTE: This release was incorrectly labeled production-ready. All cluster-facing
managers return stub data. No Kubernetes API calls are made. See
docs/audit-run-001/ for the full audit record. A corrected 1.1.0 will ship
when real implementations replace the stubs.
```

---

## 5. Commit Subject Convention

Follow the org Master TOC pattern: `<type>(<scope>): <imperative outcome>`.

Examples for this work:

```
docs(readme): replace production-ready claims with alpha status banner
docs(changelog): rewrite phase-3 complete entry with audit-accurate status
chore(cleanup): delete K8S_ANNOUNCEMENT, TEST_SUITE_IMPLEMENTATION_SUMMARY, coming_soon, GettingStarted
docs(vscode): remove hardcoded lab IP 172.100.10.107 from integration guide
docs(getting-started): remove curl /health references and 45720+ issue claim
```

Avoid: `Update README`, `Fix docs`, `Misc cleanup`. These do not read as
useful TOC bullets and obscure the scope of the change.

---

## 6. Acceptance Criteria

- [ ] `grep -r "Production Ready" README.md CHANGELOG.md` returns zero hits
- [ ] `grep -r "390" README.md CHANGELOG.md GETTING_STARTED.md` returns zero hits
- [ ] `grep -r "45,720" .` returns zero hits across all docs
- [ ] `grep -r "99.9%" .` returns zero hits
- [ ] `grep -r "172.100.10" .` returns zero hits
- [ ] `grep -r "localhost:3001" .` returns zero hits
- [ ] `K8S_ANNOUNCEMENT.md` does not exist
- [ ] `TEST_SUITE_IMPLEMENTATION_SUMMARY.md` does not exist
- [ ] `coming_soon.md` does not exist
- [ ] `GettingStarted.md` does not exist (lowercase-G duplicate)
- [ ] `README.md` starts with the `<!-- toc-backlink -->` block
- [ ] `README.md` second block is the alpha status banner
- [ ] CHANGELOG.md Phase 3 entry reads "NOT COMPLETE -- see /docs/audit-run-001/"
- [ ] `pytest --collect-only -q` count matches the count stated in all updated docs
