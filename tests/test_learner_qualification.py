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
                          '<p>Lord, make haste to help me.</p><p>Father and Spirit help us.</p>'
                          + ''.join(f'<p>{source}</p>' for _, source, _ in qualification.IPA_REGRESSION_CASES))
             for title, slug in fetch.ENGLISH_PRAYERS],
            fetch.LiturgicalDay("Qualification fixture", "Memorial", "fixture"),
        )

    @staticmethod
    def model_reply(language, label, schema, instructions, payload):
        language.total_requests += 1
        if label == "casual_british_ipa":
            known = {
                qualification.IPA_REGRESSION_CASES[0][1]: "wiː preɪz juː ðə lɔːd ɡɒd ɔːlˈmaɪti",
                qualification.IPA_REGRESSION_CASES[1][1]: "bʌt wɒtˈevə ɡeɪnz aɪ hæd bɪˈkɒz əv kraɪst",
            }
            return {"items": [{"id": item["id"], "guide": known.get(item["text"], "fəˈnetɪk ˈsɑːmpəl")} for item in payload["items"]]}
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
        self.assertEqual(result["regression_extra_requests"], 0)
        self.assertEqual(result["regressions_present_in_full_day"], 2)
        self.assertTrue(all(item["lexical_checks"] == "passed" for item in result["ipa_regression_samples"]))
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
        original_prompt = fetch.LEARNER_IPA_INSTRUCTIONS

        def check_isolation(language, date, root):
            self.assertEqual(language.models, ["candidate"])
            self.assertEqual(language.cache, {"pronunciations": {}, "glossaries": {}})
            self.assertTrue(fetch.LEARNER_CACHE_FILE.is_relative_to(root))
            self.assertEqual(fetch.LEARNER_REQUESTS_PER_WINDOW, 4)
            self.assertEqual(fetch.LEARNER_IPA_INSTRUCTIONS, qualification.CONSERVATIVE_IPA_INSTRUCTIONS)
            return {"test": "isolated"}

        with patch.dict(os.environ, {fetch.LEARNER_GEMINI_API_KEY_ENV: "test-key",
                                    fetch.LEARNER_GEMINI_MODEL_ENV: "candidate",
                                    fetch.LEARNER_GEMINI_FALLBACK_MODELS_ENV: "production-fallback",
                                    "GITHUB_STEP_SUMMARY": ""}), patch(
            "sys.argv", ["check_learner_model.py", "--scope", "full-day", "--date", "2026-10-01", "--ipa-prompt", "conservative"]
        ), patch.object(qualification, "qualify_full_day", side_effect=check_isolation), patch("builtins.print"):
            qualification.main()
        self.assertEqual(fetch.LEARNER_CACHE_FILE, original_cache)
        self.assertEqual(fetch.LEARNER_REQUESTS_PER_WINDOW, original_rpm)
        self.assertEqual(fetch.LEARNER_IPA_INSTRUCTIONS, original_prompt)

    def test_lexical_checks_accept_connected_speech_and_reject_observed_errors(self):
        sources = [source for _, source, _ in qualification.IPA_REGRESSION_CASES]
        guides = {sources[0]: "wiː preɪʒ juː ðə lɔːd ɡɒd ˌɔːɫˈmaɪʔi",
                  sources[1]: "bʌʔ wɒʔˈevə ɡeɪnz bɪkəz‿əv kraɪst"}
        self.assertEqual(len(qualification.verify_ipa_regressions(guides)), 2)
        variants = {sources[0]: "wiː preɪz juː ðə lɔːd ɡɒd ɔːlˈmaɪtɪ",
                    sources[1]: "bʌt wɔtˈɛvə ɡeɪnz bəˈkəz əv kraɪst"}
        self.assertEqual(len(qualification.verify_ipa_regressions(variants)), 2)
        for source, bad_guide in ((sources[0], "wiː preɪ juː ðə lɔːd ɡɒd ˈɔːlməti"),
                                  (sources[1], "bʌt wʌbˈevə ɡeɪnz bɪˈkɒv əv kraɪst")):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "lexical regressions failed"):
                qualification.verify_ipa_regressions({**guides, source: bad_guide})

    def test_large_batch_lexical_error_is_not_hidden_by_a_standalone_sample(self):
        def faulty_reply(language, label, schema, instructions, payload):
            reply = self.model_reply(language, label, schema, instructions, payload)
            if label == "casual_british_ipa":
                for item, output in zip(payload["items"], reply["items"]):
                    if item["text"] == qualification.IPA_REGRESSION_CASES[0][1]:
                        output["guide"] = "wiː preɪz juː ðə lɔːd ɡɒd ˈɔːlməti"
            return reply

        language = fetch.LearnerLanguage("test-key", "candidate")
        with patch.object(fetch, "fetch_english_day", return_value=self.site), patch.object(
            fetch.LearnerLanguage, "request_json", autospec=True, side_effect=faulty_reply
        ) as request, self.assertRaisesRegex(ValueError, "Full-day IPA lexical regression failed"):
            qualification.qualify_full_day(language, self.date, self.root)
        self.assertEqual(request.call_count, 3)


if __name__ == "__main__":
    unittest.main()
