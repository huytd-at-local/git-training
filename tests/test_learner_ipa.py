import unittest
from unittest.mock import patch
from scripts import fetch


class IpaValidationTest(unittest.TestCase):
    def test_latin_only_and_connected_speech(self):
        for source, guide in [("men.", "men"), ("help.", "help"), ("Yes.", "jes"),
                              ("Let us", "let əs"), ("Help us", "help ʌs"),
                              ("I", "aɪ"), ("men", "mɛn")]:
            with self.subTest(guide=guide):
                self.assertEqual(fetch.validate_casual_british_ipa(source, guide), guide)

    def test_reject_invalid(self):
        for guide in ("", "Đờ men", "mén", "MEN", "/men/", "[men]", "<b>men</b>",
                      "plain respelling", "Here is the IPA: men", "ˈˌ", "mmm", "men" * 200,
                      "let men help us"):
            with self.subTest(guide=guide):
                with self.assertRaises(fetch.LearnerLanguageError):
                    fetch.validate_casual_british_ipa("Let men help us.", guide)

    def test_repair_keeps_men_and_reports_reason(self):
        language = fetch.LearnerLanguage("test-key", "test")
        language.cache = {"pronunciations": {}, "glossaries": {}}
        language.save = lambda: None
        replies = [{"items": [{"id": "0", "guide": "men"}, {"id": "1", "guide": "/help/"}]},
                   {"items": [{"id": "1", "guide": "help"}]}]
        with patch.object(language, "request_json", side_effect=replies) as request, patch.object(fetch.time, "sleep"):
            self.assertEqual(language.pronunciations(["men.", "help."]), {"men.": "men", "help.": "help"})
            retry = request.call_args_list[1].args[3]["items"]
            self.assertEqual([item["id"] for item in retry], ["1"])
            self.assertIn("repair_reason", retry[0])
        with patch.object(language, "request_json") as request:
            self.assertEqual(language.pronunciations(["men."]), {"men.": "men"})
            request.assert_not_called()
