import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_learner_model as qualification
from scripts import fetch


class QualificationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.date = qualification.qualification_date("2026-10-01")
        for name, value in (("CACHE_DIR", self.root / "cache"),
                            ("LEARNER_CACHE_FILE", self.root / "cache" / "language.json")):
            patcher = patch.object(fetch, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.site = fetch.EnglishDaySite(
            self.date,
            [fetch.Prayer(title, slug, '<h2>Prayer</h2><p>God, come to my assistance.</p>'
                          '<p>Lord, make haste to help me.</p><p>Father and Spirit help us.</p>')
             for title, slug in fetch.ENGLISH_PRAYERS],
            fetch.LiturgicalDay("Qualification fixture", "Memorial", "fixture"),
        )

    @staticmethod
    def model_reply(language, label, schema, instructions, payload):
        language.total_requests += 1
        if label == "casual_british_ipa":
            return {"items": [{"id": item["id"], "guide": "fəˈnetɪk ˈsɑːmpəl"} for item in payload["items"]]}
        return {"items": [{"id": item["id"], "terms": [
            {"term": term, "definition": "a simple word in this prayer"}
            for term in ("God", "assistance", "Lord", "haste", "Father", "Spirit")
        ]} for item in payload["items"]]}

    def test_complete_cold_warm_and_both_encrypted_modes(self):
        language = fetch.LearnerLanguage("test-key", "candidate")
        with patch.object(fetch, "fetch_english_day", return_value=self.site), patch.object(
            fetch.LearnerLanguage, "request_json", autospec=True, side_effect=self.model_reply
        ) as request:
            result = qualification.qualify_full_day(language, self.date, self.root)
        self.assertEqual(request.call_count, 3)  # source IPA, glossary, glossary IPA
        self.assertEqual(result["cold_requests"], 3)
        self.assertEqual(result["warm_requests"], 0)
        self.assertEqual(result["automated_gate"], "passed")
        self.assertEqual(len(result["audit_samples"]), 5)
        self.assertEqual(result["kindle_pages"]["learner"], result["kindle_pages"]["learner-dated"])
        self.assertTrue((self.root / "cache" / "language.json").is_file())
        # Deliberate tampering after encryption must be detected, not merely file existence.
        body = fetch.learner_row_html("changed source", "tʃeɪndʒd")
        with self.assertRaisesRegex(ValueError, "round-trip changed"):
            qualification.verify_editions(self.root / "en", self.site,
                                          {"2026-10-01": {prayer.slug: body for prayer in self.site.prayers}}, "123456")

    def test_incomplete_source_day_stops_before_model_calls(self):
        incomplete = fetch.EnglishDaySite(self.date, self.site.prayers[:4], self.site.liturgical_day)
        language = fetch.LearnerLanguage("test-key", "candidate")
        with patch.object(fetch, "fetch_english_day", return_value=incomplete), patch.object(
            fetch.LearnerLanguage, "request_json"
        ) as request, self.assertRaisesRegex(ValueError, "complete five-Office"):
            qualification.qualify_full_day(language, self.date, self.root)
        request.assert_not_called()

    def test_invalid_date_and_incomplete_rows_fail_closed(self):
        with self.assertRaises(ValueError):
            qualification.qualification_date("2026-02-30")
        with self.assertRaisesRegex(ValueError, "Incomplete paired"):
            qualification.paired_rows('<section class="learner-row"><div class="learner-english">text</div></section>')
        self.assertEqual(str(self.date.tzinfo), "Asia/Ho_Chi_Minh")

    def test_entrypoint_isolates_cache_and_disables_fallback(self):
        original_cache = fetch.LEARNER_CACHE_FILE
        original_rpm = fetch.LEARNER_REQUESTS_PER_WINDOW

        def check_isolation(language, date, root):
            self.assertEqual(language.models, ["candidate"])
            self.assertEqual(language.cache, {"pronunciations": {}, "glossaries": {}})
            self.assertTrue(fetch.LEARNER_CACHE_FILE.is_relative_to(root))
            self.assertEqual(fetch.LEARNER_REQUESTS_PER_WINDOW, 4)
            return {"test": "isolated"}

        with patch.dict(os.environ, {fetch.LEARNER_GEMINI_API_KEY_ENV: "test-key",
                                    fetch.LEARNER_GEMINI_MODEL_ENV: "candidate",
                                    fetch.LEARNER_GEMINI_FALLBACK_MODELS_ENV: "production-fallback",
                                    "GITHUB_STEP_SUMMARY": ""}), patch(
            "sys.argv", ["check_learner_model.py", "--scope", "full-day", "--date", "2026-10-01"]
        ), patch.object(qualification, "qualify_full_day", side_effect=check_isolation), patch("builtins.print"):
            qualification.main()
        self.assertEqual(fetch.LEARNER_CACHE_FILE, original_cache)
        self.assertEqual(fetch.LEARNER_REQUESTS_PER_WINDOW, original_rpm)


if __name__ == "__main__":
    unittest.main()
