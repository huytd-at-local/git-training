import logging
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup
from scripts import fetch
from tests.english_test_helpers import decrypt_english_pages, encrypted_shell_ciphertext


SAMPLE = "God, come to my assistance."
SAMPLE_IPA = "ɡˈɒd kˈʌm tə maɪ ɐsˈɪstəns"
VERSION_OUTPUT = "eSpeak NG text-to-speech: 1.52.0  Data at: /usr/share/espeak-ng-data\n"


def day_site(date, body=f"<p>{SAMPLE}</p>"):
    return fetch.EnglishDaySite(
        date,
        [fetch.Prayer(title, slug, body) for title, slug in fetch.ENGLISH_PRAYERS],
        fetch.LiturgicalDay("Sunday", "", "test", "August 23"),
    )


def snapshot(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


class EspeakContractTest(unittest.TestCase):
    def test_voice_plain_ipa_stdin_and_no_shell(self):
        source = "--help; $(touch /tmp/should-not-exist) `echo x` & café"
        with patch.object(fetch.subprocess, "run", return_value=SimpleNamespace(stdout="  ˈkæfeɪ\n \t ə  ")) as run:
            self.assertEqual(fetch.espeak_ipa(source), "ˈkæfeɪ ə")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["espeak-ng", "-q", "--ipa", "-v", "en-GB-x-rp", "--stdin"])
        self.assertEqual(kwargs["input"], source)
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["timeout"], fetch.TIMEOUT_SECONDS)

    def test_version_preflight(self):
        with patch.object(fetch.subprocess, "run", return_value=SimpleNamespace(stdout=VERSION_OUTPUT)) as run:
            fetch.require_espeak_ng()
        self.assertEqual(run.call_args.args[0], ["espeak-ng", "--version"])

    def test_unexpected_or_unparseable_version(self):
        for version in ("1.51", "1.52.1", "1.52.0-dev", "1.52.00"):
            with self.subTest(version=version), patch.object(
                fetch.subprocess, "run", return_value=SimpleNamespace(stdout=VERSION_OUTPUT.replace("1.52.0", version))
            ):
                with self.assertRaisesRegex(fetch.LearnerBuildError, f"requires eSpeak NG 1.52.0; found {version}"):
                    fetch.require_espeak_ng()
        with patch.object(fetch.subprocess, "run", return_value=SimpleNamespace(stdout="unrecognized output")):
            with self.assertRaisesRegex(fetch.LearnerBuildError, "found unknown"):
                fetch.require_espeak_ng()

    def test_missing_executable_is_clear(self):
        with patch.object(fetch.subprocess, "run", side_effect=FileNotFoundError()):
            for call in (fetch.require_espeak_ng, lambda: fetch.espeak_ipa(SAMPLE)):
                with self.assertRaisesRegex(fetch.LearnerBuildError, "requires espeak-ng 1.52.0 on PATH"):
                    call()

    def test_nonzero_exit_is_clear(self):
        error = subprocess.CalledProcessError(2, ["espeak-ng"], stderr="Failed to read voice 'en-GB-x-rp'")
        with patch.object(fetch.subprocess, "run", side_effect=error):
            for call in (fetch.require_espeak_ng, lambda: fetch.espeak_ipa(SAMPLE)):
                with self.assertRaisesRegex(fetch.LearnerBuildError, "exit 2.*Failed to read voice"):
                    call()

    def test_timeout_is_clear(self):
        with patch.object(fetch.subprocess, "run", side_effect=subprocess.TimeoutExpired(["espeak-ng"], 30)):
            with self.assertRaisesRegex(fetch.LearnerBuildError, "could not run.*timed out"):
                fetch.espeak_ipa(SAMPLE)

    def test_empty_output_is_rejected(self):
        with patch.object(fetch.subprocess, "run", return_value=SimpleNamespace(stdout=" \n\t ")):
            with self.assertRaisesRegex(fetch.LearnerBuildError, "empty IPA"):
                fetch.espeak_ipa(SAMPLE)

    def test_preflight_failure_prevents_pronunciation(self):
        with patch.object(fetch, "require_espeak_ng", side_effect=fetch.LearnerBuildError("wrong version")), patch.object(fetch, "espeak_ipa") as ipa:
            with self.assertRaises(fetch.LearnerBuildError):
                fetch.prepare_english_learner_bodies([day_site(datetime(2026, 8, 23))])
            ipa.assert_not_called()

    def test_unique_fragments_and_exact_source_rows(self):
        site = day_site(datetime(2026, 8, 23), f'<h2>Hymn</h2><p>{SAMPLE}</p><p>{SAMPLE}</p><p>Lord, help us.</p>')
        with patch.object(fetch, "require_espeak_ng") as preflight, patch.object(fetch, "espeak_ipa", return_value=SAMPLE_IPA) as ipa:
            bodies = fetch.prepare_english_learner_bodies([site])
            self.assertEqual([call.args[0] for call in ipa.call_args_list], [SAMPLE, "Lord, help us."])
            preflight.assert_called_once()
            for body in bodies["2026-08-23"].values():
                soup = BeautifulSoup(body, "lxml")
                self.assertEqual([h.get_text() for h in soup.select("h2, h3")], ["Hymn"])
                self.assertEqual(len(soup.select("section")), 3)
                self.assertEqual([p.get_text() for p in soup.select(".learner-english p")], [SAMPLE, SAMPLE, "Lord, help us."])
                self.assertEqual([p.get_text() for p in soup.select(".learner-pronunciation p")], [SAMPLE_IPA] * 3)
            fetch.prepare_english_learner_bodies([site])
            self.assertEqual(ipa.call_count, 4, "Each new build must regenerate its unique fragments")

    def test_build_selects_today_and_shares_prepared_bodies(self):
        today = datetime(2026, 8, 23, tzinfo=fetch.VN_TZ)
        with patch.object(fetch, "fetch_english_day", side_effect=lambda _session, date: day_site(date)) as source, patch.object(fetch, "prepare_english_learner_bodies", return_value={"prepared": {}}) as prepare, patch.object(fetch, "write_english_bundle_atomic") as write:
            fetch.build_english_breviary(today, "123456")
        self.assertEqual([call.args[1] for call in source.call_args_list], [today + timedelta(days=offset) for offset in (-1, 0, 1)])
        self.assertEqual([site.date for site in prepare.call_args.args[0]], [today])
        self.assertIs(write.call_args.args[3], prepare.return_value)
        self.assertEqual([site.date for site in write.call_args.args[1]], [today])


class LocalEnglishBundleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        site_patch = patch.object(fetch, "SITE_DIR", self.root / "site")
        build_patch = patch.object(fetch, "BUILD_DIR", self.root / "build")
        site_patch.start()
        build_patch.start()
        self.addCleanup(site_patch.stop)
        self.addCleanup(build_patch.stop)
        self.today = datetime(2026, 8, 23, tzinfo=fetch.VN_TZ)
        self.site = day_site(self.today, "<h2>Hymn</h2>" + f"<p>{SAMPLE}</p>" * 24)
        self.english_root = fetch.SITE_DIR / "breviary/en"
        self.english_root.mkdir(parents=True)
        (self.english_root / "index.html").write_text("previous complete bundle")
        stale = self.english_root / "learner-responsive/morning-prayer-2.html"
        stale.parent.mkdir()
        stale.write_text("stale numbered page")

    def test_real_engine_golden_and_determinism(self):
        fetch.require_espeak_ng()
        self.assertEqual(fetch.ESPEAK_NG_VOICE, "en-GB-x-rp")
        self.assertEqual(fetch.espeak_ipa(SAMPLE), SAMPLE_IPA)
        self.assertEqual(fetch.espeak_ipa(SAMPLE), SAMPLE_IPA)

    def test_real_engine_complete_atomic_bundle(self):
        bodies = fetch.prepare_english_learner_bodies([self.site])
        reading_sites = [day_site(self.today + timedelta(days=offset)) for offset in (-1, 0, 1)]
        fetch.write_english_bundle_atomic(reading_sites, [self.site], "123456", bodies)
        fetch.validate_encrypted_english_bundle(self.english_root)
        for mode in ("learner", "learner-responsive"):
            root = self.english_root / mode
            shell = (root / "index.html").read_text()
            self.assertIn(fetch.LEARNER_PROFILE_CLASS, shell)
            self.assertTrue((root / "2026-08-23/index.html").is_file())
            self.assertFalse((root / "2026-08-22").exists())
            self.assertFalse((root / "2026-08-24").exists())
        responsive = self.english_root / "learner-responsive"
        self.assertFalse(list(responsive.rglob("*-2.html")))
        for _, slug in fetch.ENGLISH_PRAYERS:
            prepared = BeautifulSoup(bodies["2026-08-23"][slug], "lxml")
            expected_rows = [str(row) for row in prepared.select(".learner-row")]
            for mode in ("learner", "learner-responsive"):
                root = self.english_root / mode
                prayer_files = [root / f"{slug}.html"]
                if mode == "learner":
                    prayer_files += sorted(root.glob(f"{slug}-*.html"), key=lambda path: int(path.stem.rsplit("-", 1)[1]))
                    self.assertGreater(len(prayer_files), 1)
                pages = [{"id": "index", "ciphertext": encrypted_shell_ciphertext(root / "index.html")}]
                pages += [{"id": str(i), "ciphertext": encrypted_shell_ciphertext(path)} for i, path in enumerate(prayer_files)]
                plaintext = decrypt_english_pages(pages, "123456")
                actual_rows = []
                for i in range(len(prayer_files)):
                    soup = BeautifulSoup(plaintext[str(i)], "lxml")
                    actual_rows.extend(str(row) for row in soup.select(".learner-row"))
                    self.assertEqual([h.get_text() for h in soup.select("h2, h3")], ["Hymn"] if i == 0 else [])
                    self.assertEqual(len(soup.select("section:not(.liturgical-day)")), len(soup.select(".learner-row")))
                self.assertEqual(actual_rows, expected_rows)

    def test_engine_failure_preserves_entire_previous_bundle(self):
        before = snapshot(self.english_root)
        with patch.object(fetch, "fetch_english_day", side_effect=lambda _session, date: day_site(date)), patch.object(fetch, "espeak_ipa", side_effect=fetch.LearnerBuildError("synthetic CLI failure")), self.assertLogs(level=logging.ERROR):
            self.assertFalse(fetch.update_english_breviary_optional(self.today, "123456"))
        self.assertEqual(snapshot(self.english_root), before)

    def test_staging_failure_preserves_entire_previous_bundle(self):
        bodies = {"2026-08-23": {slug: fetch.learner_row_html(SAMPLE, SAMPLE_IPA) for _, slug in fetch.ENGLISH_PRAYERS}}
        before = snapshot(self.english_root)
        with patch.object(fetch, "write_english_learner_responsive", side_effect=RuntimeError("synthetic writer failure")):
            with self.assertRaisesRegex(RuntimeError, "writer failure"):
                fetch.write_english_bundle_atomic([self.site], [self.site], "123456", bodies)
        self.assertEqual(snapshot(self.english_root), before)
        self.assertFalse(self.english_root.with_name("en.bundle-new").exists())

    def test_validation_failure_preserves_entire_previous_bundle(self):
        bodies = {"2026-08-23": {slug: fetch.learner_row_html(SAMPLE, SAMPLE_IPA) for _, slug in fetch.ENGLISH_PRAYERS}}
        before = snapshot(self.english_root)
        with patch.object(fetch, "validate_encrypted_english_bundle", side_effect=ValueError("synthetic validation failure")):
            with self.assertRaisesRegex(ValueError, "validation failure"):
                fetch.write_english_bundle_atomic([self.site], [self.site], "123456", bodies)
        self.assertEqual(snapshot(self.english_root), before)

    def test_source_failure_remains_optional(self):
        before = snapshot(self.english_root)
        with patch.object(fetch, "fetch_english_day", side_effect=ValueError("synthetic source outage")), self.assertLogs(level=logging.ERROR):
            self.assertFalse(fetch.update_english_breviary_optional(self.today, "123456"))
        self.assertEqual(snapshot(self.english_root), before)


if __name__ == "__main__":
    unittest.main()
