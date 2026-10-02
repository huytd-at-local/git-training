import json
import os
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

from scripts import fetch


def response(status, payload=None):
    result = Mock(status_code=status, text="upstream error", headers={})
    if payload is None:
        payload = {"items": []}
    result.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]
    }
    result.raise_for_status.side_effect = fetch.requests.HTTPError() if status >= 400 else None
    return result


class FailoverTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(
            os.environ,
            {
                "BREVIARY_LEARNER_FALLBACK_MODELS": "backup,tertiary",
                "BREVIARY_LEARNER_FALLBACK_MODEL": "",
                "GITHUB_STEP_SUMMARY": "",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        # Advance a fake clock on sleeps so real rolling-window throttling
        # remains enabled without slowing mocked HTTP/failover tests.
        self.now = 0.0
        monotonic = patch.object(fetch.time, "monotonic", side_effect=lambda: self.now)
        monotonic.start()
        self.addCleanup(monotonic.stop)
        sleeper = patch.object(fetch.time, "sleep", side_effect=self.advance_clock)
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)
        self.language = fetch.LearnerLanguage("test-key", "primary")

    def advance_clock(self, seconds):
        self.now += seconds

    def request(self):
        return self.language.request_json("test", {}, "JSON", {"items": []})

    @staticmethod
    def called_models(post):
        return [call.args[0].split("models/")[1] for call in post.call_args_list]

    def test_three_model_chain_is_one_way_and_sticky(self):
        replies = [response(503)] * 3 + [response(503)] * 3 + [response(200)] + [response(200)]
        with patch.object(fetch.requests, "post", side_effect=replies) as post:
            self.request()
            self.request()
        self.assertEqual(
            self.called_models(post),
            ["primary:generateContent"] * 3
            + ["backup:generateContent"] * 3
            + ["tertiary:generateContent"] * 2,
        )
        self.assertEqual(self.language.model, "tertiary")
        self.assertEqual(self.language.models, ["primary", "backup", "tertiary"])

    def test_all_models_fail_bounded(self):
        with patch.object(fetch.requests, "post", return_value=response(503)) as post:
            with self.assertRaises(fetch.LearnerTransientError):
                self.request()
        self.assertEqual(post.call_count, 9)
        self.assertEqual(self.language.model, "tertiary")

    def test_server_errors_advance_to_next_model(self):
        for status in (500, 502, 503, 504):
            language = fetch.LearnerLanguage("test-key", "primary")
            with self.subTest(status=status), patch.object(
                fetch.requests,
                "post",
                side_effect=[response(status)] * 3 + [response(200)],
            ) as post:
                language.request_json("test", {}, "JSON", {"items": []})
                self.assertEqual(post.call_count, 4)
                self.assertEqual(language.model, "backup")

    def test_no_fallback_for_permanent_or_quota_errors(self):
        for status, expected_calls in ((400, 1), (401, 1), (403, 1), (404, 1), (429, 3)):
            with self.subTest(status=status), patch.object(fetch.requests, "post", return_value=response(status)) as post:
                with self.assertRaises(fetch.LearnerLanguageError):
                    self.request()
                self.assertEqual(post.call_count, expected_calls)
                self.assertEqual(self.language.model, "primary")

    def test_connection_and_timeout_advance_to_next_model(self):
        for exception in (fetch.requests.ConnectionError(), fetch.requests.Timeout()):
            language = fetch.LearnerLanguage("test-key", "primary")
            with self.subTest(exception=type(exception).__name__), patch.object(
                fetch.requests,
                "post",
                side_effect=[exception] * 3 + [response(200)],
            ) as post:
                language.request_json("test", {}, "JSON", {"items": []})
                self.assertEqual(post.call_count, 4)
                self.assertEqual(language.model, "backup")

    def test_other_request_errors_do_not_fallback(self):
        with patch.object(fetch.requests, "post", side_effect=fetch.requests.RequestException("bad request")) as post:
            with self.assertRaises(fetch.LearnerLanguageError):
                self.request()
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.language.model, "primary")

    def test_invalid_json_does_not_fallback(self):
        invalid = response(200)
        invalid.json.side_effect = ValueError("not json")
        with patch.object(fetch.requests, "post", return_value=invalid) as post:
            with self.assertRaises(fetch.LearnerLanguageError):
                self.request()
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.language.model, "primary")

    def test_semantic_validation_does_not_fallback(self):
        invalid_ipa = response(200, {"items": [{"id": "0", "guide": "/bad/"}]})
        self.language.cache = {"pronunciations": {}, "glossaries": {}}
        self.language.save = lambda: None
        with patch.object(fetch.requests, "post", return_value=invalid_ipa) as post:
            with self.assertRaises(fetch.LearnerLanguageError):
                self.language.pronunciations(["Glory"])
        self.assertEqual(post.call_count, 3)
        self.assertEqual(self.language.model, "primary")

    def test_switching_preserves_shared_budget_and_deadline(self):
        original_deadline = self.language.deadline
        with patch.object(fetch.requests, "post", side_effect=[response(503)] * 3 + [response(200)]):
            self.request()
        self.assertEqual(self.language.total_requests, 4)
        self.assertEqual(self.language.deadline, original_deadline)
        self.assertEqual(self.language.model, "backup")

    def test_fifth_request_waits_for_the_four_slot_window(self):
        self.assertEqual(fetch.LEARNER_REQUESTS_PER_WINDOW, 4)
        self.assertEqual(fetch.LEARNER_REQUEST_WINDOW_SECONDS, 60.0)
        for _ in range(4):
            self.language.wait_for_request_slot()
        self.sleep.assert_not_called()
        self.language.wait_for_request_slot()
        self.sleep.assert_called_once_with(62.0)
        self.assertEqual(self.language.request_timestamps, [62.0])
        self.assertEqual(self.language.total_requests, 5)

    def test_request_at_window_boundary_reuses_expired_slots(self):
        for _ in range(4):
            self.language.wait_for_request_slot()
        self.now = 60.0
        self.language.wait_for_request_slot()
        self.sleep.assert_not_called()
        self.assertEqual(self.language.request_timestamps, [60.0])
        self.assertEqual(self.language.total_requests, 5)

    def test_http_retries_and_fallback_share_request_slots(self):
        sent_at = []
        replies = [response(503)] * 3 + [response(200)] * 2

        def send(*_args, **_kwargs):
            sent_at.append(self.now)
            return replies.pop(0)

        with patch.object(fetch.requests, "post", side_effect=send) as post:
            self.request()
            self.request()
        self.assertEqual(sent_at, [0.0, 10.0, 30.0, 30.0, 62.0])
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [10.0, 20.0, 32.0])
        self.assertEqual(self.called_models(post), ["primary:generateContent"] * 3 + ["backup:generateContent"] * 2)
        self.assertEqual(self.language.request_timestamps, [10.0, 30.0, 30.0, 62.0])
        self.assertEqual(self.language.total_requests, 5)

    def test_cache_hit_uses_no_http_request(self):
        self.language.cache = {"pronunciations": {fetch.learner_cache_key("Glory"): "ˈɡlɔːri"}, "glossaries": {}}
        with patch.object(fetch.requests, "post") as post:
            self.assertEqual(self.language.pronunciations(["Glory"]), {"Glory": "ˈɡlɔːri"})
        post.assert_not_called()

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


if __name__ == "__main__":
    unittest.main()
