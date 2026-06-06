"""US-023: Verify documentation de-claim patches are applied correctly."""
from pathlib import Path

REPO = Path("/work/wt/US-023")


def _text(filename: str) -> str:
    return (REPO / filename).read_text()


class TestDeletedFiles:
    def test_k8s_announcement_deleted(self):
        assert not (REPO / "K8S_ANNOUNCEMENT.md").exists()

    def test_test_suite_summary_deleted(self):
        assert not (REPO / "TEST_SUITE_IMPLEMENTATION_SUMMARY.md").exists()

    def test_coming_soon_deleted(self):
        assert not (REPO / "coming_soon.md").exists()

    def test_getting_started_lowercase_deleted(self):
        assert not (REPO / "GettingStarted.md").exists()


class TestReadme:
    def test_starts_with_toc_backlink(self):
        readme = _text("README.md")
        assert readme.startswith("<!-- toc-backlink -->")

    def test_status_banner_present(self):
        readme = _text("README.md")
        assert "Alpha -- diagnose-only" in readme

    def test_no_production_ready_overclaim(self):
        readme = _text("README.md")
        # Should not have bare production-ready claim
        lines = [line for line in readme.splitlines() if "Production Ready" in line]
        # Allow only lines that are already qualified/negated
        bad = [line for line in lines if "not" not in line.lower() and "alpha" not in line.lower() and "stub" not in line.lower()]
        assert bad == [], f"Unqualified Production Ready claims: {bad}"

    def test_no_45720_claim(self):
        readme = _text("README.md")
        assert "45,720" not in readme

    def test_no_raw_lab_ip(self):
        readme = _text("README.md")
        assert "172.100.10.107" not in readme

    def test_no_hardcoded_localhost_health(self):
        readme = _text("README.md")
        bad_lines = [line for line in readme.splitlines()
                     if "curl http://localhost:3001/health" in line and "NOTE" not in line]
        assert bad_lines == [], f"Bare health curl found: {bad_lines}"


class TestChangelog:
    def test_changelog_exists(self):
        assert (REPO / "CHANGELOG.md").exists()

    def test_no_390_test_overclaim(self):
        text = _text("CHANGELOG.md")
        assert "390 comprehensive tests" not in text
        assert "390 Total Tests" not in text

    def test_no_45720_claim(self):
        text = _text("CHANGELOG.md")
        assert "45,720" not in text

    def test_no_99_9_uptime_claim(self):
        text = _text("CHANGELOG.md")
        assert "99.9% uptime since deployment" not in text


class TestGettingStarted:
    def test_no_45720_claim(self):
        text = _text("GETTING_STARTED.md")
        assert "45,720" not in text

    def test_no_bare_health_curl(self):
        text = _text("GETTING_STARTED.md")
        bad = [line for line in text.splitlines()
               if "curl http://localhost:3001/health" in line and "NOTE" not in line]
        assert bad == [], f"Bare health curl in GETTING_STARTED: {bad}"

    def test_no_bare_stats_curl(self):
        text = _text("GETTING_STARTED.md")
        assert "curl http://localhost:3001/stats" not in text


class TestVscodeK8sIntegration:
    def test_no_raw_lab_ip(self):
        text = _text("VSCODE_K8S_INTEGRATION.md")
        assert "172.100.10.107" not in text


class TestFunctionalUnitTest:
    def test_no_45720_claim(self):
        text = _text("functional_unit_test.md")
        assert "45,720" not in text

    def test_no_390_total_tests_overclaim(self):
        text = _text("functional_unit_test.md")
        assert "TOTAL: 390 COMPREHENSIVE TESTS" not in text

    def test_updated_test_count(self):
        text = _text("functional_unit_test.md")
        assert "55 TEST FUNCTIONS" in text
