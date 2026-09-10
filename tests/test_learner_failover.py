import os
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch
from scripts import fetch


def response(status):
    result = Mock(status_code=status, text="upstream error", headers={})
    result.json.return_value = {"candidates": [{"content": {"parts": [{"text": '{"items": []}'}]}}]}
    result.raise_for_status.side_effect = fetch.requests.HTTPError() if status >= 400 else None
    return result


class FailoverTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"BREVIARY_LEARNER_FALLBACK_MODEL": "backup", "GITHUB_STEP_SUMMARY": ""})
        env.start()
        self.addCleanup(env.stop)
        self.language = fetch.LearnerLanguage("test-key", "primary")

    def request(self):
        return self.language.request_json("test", {}, "JSON", {"items": []})

    @patch.object(fetch.time, "sleep")
    def test_sticky_fallback(self, _sleep):
        with patch.object(fetch.requests, "post", side_effect=[response(503)] * 3 + [response(200)] * 2) as post:
            self.request()
            self.request()
        self.assertEqual([call.args[0].split("models/")[1] for call in post.call_args_list],
                         ["primary:generateContent"] * 3 + ["backup:generateContent"] * 2)

    @patch.object(fetch.time, "sleep")
    def test_both_models_fail_bounded(self, _sleep):
        with patch.object(fetch.requests, "post", return_value=response(503)) as post:
            with self.assertRaises(fetch.LearnerTransientError):
                self.request()
        self.assertEqual(post.call_count, 6)

    @patch.object(fetch.time, "sleep")
    def test_no_fallback_for_permanent_or_quota_errors(self, _sleep):
        for status in (400, 401, 403, 404, 429):
            with self.subTest(status=status), patch.object(fetch.requests, "post", return_value=response(status)):
                with self.assertRaises(fetch.LearnerLanguageError):
                    self.request()
                self.assertFalse(self.language.fallback_used)

    @patch.object(fetch.time, "sleep")
    def test_connection_failure_fallback(self, _sleep):
        with patch.object(fetch.requests, "post", side_effect=[fetch.requests.ConnectionError()] * 3 + [response(200)]):
            self.request()
        self.assertTrue(self.language.fallback_used)

    def test_budget_and_cache(self):
        self.language.cache = {"pronunciations": {fetch.learner_cache_key("Glory"): "ˈɡlɔːri"}, "glossaries": {}}
        with patch.object(fetch.requests, "post") as post:
            self.assertEqual(self.language.pronunciations(["Glory"]), {"Glory": "ˈɡlɔːri"})
            self.language.total_requests = 120
            with self.assertRaisesRegex(fetch.LearnerLanguageError, "budget"):
                self.request()
            self.language.total_requests = 0
            self.language.deadline = 0
            with self.assertRaisesRegex(fetch.LearnerLanguageError, "budget"):
                self.request()
            post.assert_not_called()

    def test_artifact_freshness_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            target = datetime.now(fetch.VN_TZ).strftime("%Y-%m-%d")
            command = [sys.executable, "scripts/check_learner_freshness.py", directory]
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            for mode in ("learner", "learner-responsive"):
                page = Path(directory) / "breviary/en" / mode / target / "index.html"
                page.parent.mkdir(parents=True)
                page.write_text('var CIPHERTEXT = "fixture";')
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
