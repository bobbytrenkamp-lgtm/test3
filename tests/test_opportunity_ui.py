from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class _IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.append(attributes["id"])


class OpportunityFinderUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "web" / "opportunity-finder.js").read_text(encoding="utf-8")

    def test_finder_precedes_governed_review_and_ids_are_unique(self):
        self.assertLess(self.html.index('data-view="opportunity-finder"'),
                        self.html.index('data-view="opportunity-review"'))
        parser = _IdCollector()
        parser.feed(self.html)
        duplicates = {value for value in parser.ids if parser.ids.count(value) > 1}
        self.assertEqual(duplicates, set())

    def test_product_boundary_and_honest_missing_score_are_explicit(self):
        self.assertIn("Screening tiers are analyst workflow priorities", self.html)
        self.assertIn("Validated opportunity score", self.js)
        self.assertIn("Insufficient governed realized acquisition outcome data", self.js)
        self.assertNotIn("AI says buy", self.html + self.js)
        self.assertNotIn("Expected NOI upside", self.html + self.js)

    def test_ui_calls_authoritative_server_workflow(self):
        for marker in ("/api/opportunities?", "/versions`,", "/screen`,", "/archive`,"):
            self.assertIn(marker, self.js)
        self.assertIn("evidence_supported_noi_delta", self.js)
        self.assertIn("screening_currency_status", self.js)
        self.assertNotIn("screeningTier:", self.js)

    def test_finder_review_bridge_remains_segregated_from_underwriting(self):
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Send to Opportunity Review", self.js)
        self.assertIn("/review-artifacts`,", self.js)
        self.assertIn("/api/opportunity-candidate-review-artifacts", app)
        self.assertIn("Independent reviewer required", app)
        self.assertIn("workflow priority, not a score", app)
        self.assertIn("Validated score", app)
        self.assertIn("Promote to Deal Pipeline", app)
        self.assertIn("underwriting remains unchanged", app)
        self.assertNotIn("automaticUnderwritingApply=true", self.js + app)

    def test_permissions_and_xss_boundaries_are_visible_in_client(self):
        malicious = '<img src=x onerror=alert(1)>'
        self.assertIn("['analyst','admin']", self.js)
        self.assertIn("escapeHTML(property)", self.js)
        self.assertIn("escapeHTML(item.address", self.js)
        self.assertIn("escapeHTML(reason.statement)", self.js)
        self.assertIn("escapeHTML(unit)", self.js)
        self.assertIn("encodeURIComponent(candidateId)", self.js)
        escaped = (malicious.replace("&", "&amp;").replace("<", "&lt;")
                   .replace(">", "&gt;").replace("'", "&#39;").replace('"', "&quot;"))
        self.assertEqual(escaped, "&lt;img src=x onerror=alert(1)&gt;")
        self.assertNotIn(malicious, escaped)

    def test_exact_financial_strings_and_latest_screening_are_preserved(self):
        self.assertIn("detail.latest_screening||detail.current_screening", self.js)
        self.assertIn("body:JSON.stringify(payload)", self.js)
        self.assertNotIn("notation:Math.abs", self.js)
        self.assertIn("function exactPercent", self.js)
        self.assertIn("BigInt", self.js)
        self.assertIn("const raw=String(value).trim()", self.js)

    def test_outdated_screening_cannot_mix_historic_metrics_with_latest_evidence(self):
        self.assertIn("screeningCurrent=detail.screening_currency_status==='CURRENT'", self.js)
        self.assertIn("current?item.rent_gap_pct:null", self.js)
        self.assertIn("current?item.evidence_supported_noi_delta:null", self.js)
        self.assertIn("screeningCurrent?result:{}", self.js)
        self.assertIn("The displayed run is historic", self.js)

    def test_server_pagination_and_accessible_controls_exist(self):
        self.assertIn("opportunity-page-size", self.html)
        self.assertIn("opportunity-previous", self.html)
        self.assertIn("opportunity-next", self.html)
        self.assertIn('role="status" aria-live="polite"', self.html)
        self.assertIn('aria-label="Opportunity summary"', self.html)
        self.assertIn('name="rent_gap_min"', self.html)
        self.assertIn('name="basis_discount_min"', self.html)
        self.assertIn("'rent_gap_min','basis_discount_min'", self.js)
        self.assertIn("finder.page*finder.limit", self.js)
        self.assertIn("pendingCandidate", self.js)

    def test_empty_state_history_and_governance_labels_are_explicit(self):
        self.assertIn("No opportunity candidates yet.", self.js)
        self.assertIn("No candidates match these filters.", self.js)
        self.assertIn("Evidence-supported NOI delta", self.js)
        self.assertIn("screening pending", self.js)
        self.assertIn("Changed evidence / rescreen", self.html)
        self.assertIn("not an Underwrite forecast", self.js)


if __name__ == "__main__":
    unittest.main()
