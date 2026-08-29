#!/usr/bin/env sh
set -eu

PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m compileall scripts
test -f .github/workflows/pages.yml
test -f .github/workflows/retry-pages-deployment.yml
grep -q '^  build:$' .github/workflows/pages.yml
grep -q '^  deploy:$' .github/workflows/pages.yml
grep -q '^    needs: build$' .github/workflows/pages.yml
grep -q 'Restore encrypted English learner edition' .github/workflows/pages.yml
grep -q 'Seed encrypted learner edition from Pages artifact' .github/workflows/pages.yml
grep -q 'BREVIARY_REFRESH_LEARNER' .github/workflows/pages.yml
grep -q 'breviary-learner-language-v3.json' .github/workflows/pages.yml
grep -q 'breviary-learner-edition-v2-' .github/workflows/pages.yml
! grep -q 'breviary-learner-language-v2.json' .github/workflows/pages.yml
grep -q 'actions/upload-pages-artifact@v4' .github/workflows/pages.yml
grep -q 'actions/deploy-pages@v4' .github/workflows/pages.yml
grep -q '^  actions: write$' .github/workflows/retry-pages-deployment.yml
grep -q "github.event.workflow_run.run_attempt < 3" .github/workflows/retry-pages-deployment.yml
grep -q 'listJobsForWorkflowRunAttempt' .github/workflows/retry-pages-deployment.yml
grep -q 'reRunFailedJobs' .github/workflows/retry-pages-deployment.yml
grep -q "buildSucceeded('Generate static site')" .github/workflows/retry-pages-deployment.yml
grep -q "buildSucceeded('Upload Pages artifact')" .github/workflows/retry-pages-deployment.yml
grep -q "failed('Deploy to GitHub Pages')" .github/workflows/retry-pages-deployment.yml
test -f site/index.html
test -f site/style.css
test -f site/debug/index.html
test -f site/debug/metrics.html
test -f site/debug/encrypted-breviary.html
test -f site/debug/encrypted-breviary-legacy.html
test -f site/debug/encrypted-breviary-session-2.html
test -f scripts/encrypt_breviary.js
test -f scripts/decrypt_breviary.js
grep -q 'BREVIARY_EN_PASSCODE' .github/workflows/pages.yml
! grep -R -q '211216' scripts site .github tests vendor
test -f vendor/sjcl.js
test -f vendor/SJCL-LICENSE.txt
test -f site/breviary/index.html
test -f site/breviary/kinh-sang.html

debug_pattern_count=$(find site/debug -type f -name '[pPvVrRaAmMbB][0-9][0-9].html' | wc -l | tr -d ' ')
test "$debug_pattern_count" -eq 42
grep -q 'window.innerHeight' site/debug/metrics.html
grep -q 'nav.bottomGap' site/debug/metrics.html
grep -q 'document.scroll' site/debug/metrics.html
grep -q 'Đo thông số trình duyệt Kindle' site/debug/index.html
grep -q 'Thử mở Breviary bằng passcode' site/debug/index.html
grep -q 'Thử passcode bản Kindle cũ' site/debug/index.html
grep -q "AES-GCM" site/debug/encrypted-breviary.html
grep -q "PBKDF2" site/debug/encrypted-breviary.html
grep -q "iterations: ITERATIONS" site/debug/encrypted-breviary.html
grep -q "Passcode không đúng" site/debug/encrypted-breviary.html
grep -q "UNSUPPORTED:" site/debug/encrypted-breviary.html
! grep -Eq 'value="[0-9]{6}"' site/debug/encrypted-breviary.html
! grep -q 'Evening Prayer' site/debug/encrypted-breviary.html
grep -q 'mode.*ccm' site/debug/encrypted-breviary-legacy.html
grep -q 'PASS LEGACY' site/debug/encrypted-breviary-legacy.html
grep -q 'window.sjcl.decrypt' site/debug/encrypted-breviary-legacy.html
grep -q 'PASS LEGACY + SESSION' site/debug/encrypted-breviary-legacy.html
grep -q 'sessionStorage.setItem' site/debug/encrypted-breviary-legacy.html
grep -q 'encrypted-breviary-session-2.html' site/debug/encrypted-breviary-legacy.html
grep -q 'BSD-2-Clause' vendor/SJCL-LICENSE.txt
! grep -q '<script[^>]* src=' site/debug/encrypted-breviary-legacy.html
! grep -Eq 'value="[0-9]{6}"' site/debug/encrypted-breviary-legacy.html
! grep -q 'Evening Prayer' site/debug/encrypted-breviary-legacy.html
grep -q 'PASS SESSION' site/debug/encrypted-breviary-session-2.html
grep -q 'sessionStorage.getItem' site/debug/encrypted-breviary-session-2.html
grep -q 'LOCKED: Chưa có khóa phiên' site/debug/encrypted-breviary-session-2.html
! grep -q 'Night Prayer' site/debug/encrypted-breviary-session-2.html

if test -d site/breviary/en; then
  test -f site/breviary/en/index.html
  grep -q 'DIVINE_OFFICE_URL' scripts/fetch.py
  ! grep -qi 'ibreviary' scripts/fetch.py
  grep -q 'breviary-en-key-v1' site/breviary/en/index.html
  grep -q 'mode.*ccm' site/breviary/en/index.html
  grep -q 'var CIPHERTEXT = "{\\"iv\\"' site/breviary/en/index.html
  grep -q 'session key was not retained' site/breviary/en/index.html
  ! grep -R -q '<script[^>]* src=' site/breviary/en
  ! grep -R -q 'Office of Readings' site/breviary/en
  ! grep -R -q 'Morning Prayer' site/breviary/en
  ! grep -R -q 'Evening Prayer' site/breviary/en
  ! grep -R -q 'Night Prayer' site/breviary/en
fi
grep -q 'display: block;' site/style.css
for file in site/debug/[pPvVrRaAmMbB][0-9][0-9].html; do
  grep -q 'DEBUG [PVRAMB][0-9][0-9]' "$file"
  grep -q 'class="page-nav paged-nav"' "$file"
  grep -q 'Mục lục' "$file"
done

pages="
kinh-sach
kinh-sang
kinh-trua-gio-ba
kinh-trua-gio-sau
kinh-trua-gio-chin
kinh-chieu
kinh-toi
"

for page in $pages; do
  file="site/$page.html"
  test -f "$file"
  test -s "$file"
  grep -q '<main>' "$file"
  grep -q 'Mục lục' "$file"
  grep -q '&#9654;' "$file"
  grep -q '&#9664;' "$file"
  ! grep -q 'Trang sau' "$file"
  ! grep -q 'Trang trước' "$file"
  ! grep -q 'Update Required' "$file"
  ! grep -q 'Flash plugin' "$file"
  ! grep -q 'itunes.apple.com' "$file"
  ! grep -q 'play.google.com' "$file"
done

grep -q 'Ca vịnh' site/kinh-chieu*.html
grep -q 'Ca vịnh' site/kinh-sang*.html
grep -q 'Tv 94 (95)' site/kinh-sang*.html
! grep -q 'Tv 94 (95)' site/kinh-sach.html
grep -q 'class="verse-line"' site/kinh-sang*.html
grep -q 'class="verse-line"' site/kinh-toi*.html
grep -q 'wide-verse-number' site/style.css
grep -q '.verse-line > sup' site/style.css
grep -q 'line-height: 0;' site/style.css
grep -q 'display: none;' site/style.css
grep -q 'illuminated-initial' site/style.css
grep -q 'class="illuminated-initial"' site/kinh-sang*.html
grep -q 'class="illuminated-initial"' site/kinh-chieu*.html
grep -q 'class="illuminated-initial"' site/kinh-sach*.html
grep -q 'p > .pre' site/style.css
grep -q 'p > .body' site/style.css
grep -q '.antiphon .pre' site/style.css
! grep -q 'window.location.replace' site/index.html
! grep -q 'getUTCHours' site/index.html
! grep -q '<script>' site/index.html
grep -q 'class="date-nav"' site/index.html
! grep -q 'class="date-nav"' site/kinh-sang.html
! grep -q 'class="page-count"' site/kinh-sang.html
! grep -q 'class="reading-ref"' site/*.html
! grep -REq '<span class="pre">(Chủ sự|Cộng đoàn|X|Đ):?</span>' site
grep -q '<span class="pre">ĐC:</span>' site/kinh-sang*.html
! grep -q 'Ha-lê-lui-a. Ha-lê-lui-a. Ha-lê-lui-a' site/kinh-toi*.html

if test -f .cache/source.html && grep -Eq '<(em|i)([ >])' .cache/source.html; then
  grep -REq '(<em[ >]|class="[^"]*(italic|note)[^"]*")' site/*.html
fi

"$PYTHON_BIN" - <<'PY'
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import scripts.fetch as fetch_module
from scripts.fetch import (
    ENGLISH_PRAYERS,
    GEMINI_GENERATE_CONTENT_URL,
    LEARNER_FIRST_PAGE_TARGET_UNITS,
    LEARNER_IPA_INSTRUCTIONS,
    LEARNER_PAGE_TARGET_UNITS,
    LEARNER_PROFILE_CLASS,
    PAGE_TARGET_UNITS,
    Prayer,
    block_units,
    debug_production_verse,
    debug_prose,
    debug_verse,
    english_prayer_inner,
    gemini_retry_seconds,
    html_blocks,
    learner_html_blocks,
    learner_edition_profile_matches,
    learner_page_units,
    learner_prayer_body,
    learner_body_from_decrypted_pages,
    learner_row_html,
    rebalance_learner_pages,
    page_units,
    prepare_english_learner_bodies,
    paginate_learner_html,
    restore_english_learner_bodies,
    text_units,
    validate_casual_british_ipa,
    EnglishDaySite,
    LiturgicalDay,
    LearnerLanguage,
    LearnerLanguageError,
    build_english_breviary,
    write_english_breviary,
    write_english_learner,
)

expected_breviary_css = (
    Path("site/style.css").read_text(encoding="utf-8").rstrip()
    + "\n\n"
    + fetch_module.BREVIARY_CSS.lstrip()
)
if Path("site/breviary.css").read_text(encoding="utf-8") != expected_breviary_css:
    raise SystemExit("Committed Breviary CSS drifted from the build-time source")
if "font-size: 38px;" not in fetch_module.BREVIARY_CSS or "line-height: 1.28;" not in fetch_module.BREVIARY_CSS:
    raise SystemExit("Build-time learner CSS lost the Paperwhite readability calibration")
if fetch_module.LEARNER_PAGE_TARGET_UNITS != 18.0:
    raise SystemExit("Learner later-page budget no longer reserves Paperwhite navigation space")
if fetch_module.LEARNER_FIRST_PAGE_TARGET_UNITS != 15.0:
    raise SystemExit("Learner first-page budget drifted from the verified Paperwhite capture")
if fetch_module.LEARNER_ROW_SPACING_UNITS < 0.20:
    raise SystemExit("Learner page model omitted the table-cell vertical padding")

expected_english_prayers = [
    "Invitatory",
    "Office of Readings",
    "Morning Prayer",
    "Midmorning Prayer",
    "Midday Prayer",
    "Midafternoon Prayer",
    "Evening Prayer",
    "Night Prayer",
]
if [title for title, _ in ENGLISH_PRAYERS] != expected_english_prayers:
    raise SystemExit("English Breviary menu no longer matches the Divine Office hours")
english_inner = english_prayer_inner(
    type("Prayer", (), {"title": "Morning Prayer"})(),
    None,
    "<p>Prayer text.</p>",
    1,
    1,
    '<nav class="page-nav paged-nav breviary-nav">nav</nav>',
    "now",
)
if english_inner.count('class="page-nav paged-nav breviary-nav"') != 1:
    raise SystemExit("English prayer page must have only the bottom Breviary navigation")

class FakeGeminiResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": '{"items": []}'}]}}]}

gemini_call = {}
original_post = fetch_module.requests.post
try:
    def fake_gemini_post(url, **kwargs):
        gemini_call["url"] = url
        gemini_call.update(kwargs)
        return FakeGeminiResponse()

    fetch_module.requests.post = fake_gemini_post
    response = LearnerLanguage("test-key", "gemini-test").request_json(
        "smoke", {"type": "object", "properties": {"items": {"type": "array"}}}, "Use JSON.", {"items": []}
    )
finally:
    fetch_module.requests.post = original_post
if response != {"items": []}:
    raise SystemExit("Gemini structured response parsing failed")
if gemini_call["url"] != GEMINI_GENERATE_CONTENT_URL.format(model="gemini-test"):
    raise SystemExit("Learner request does not use the Gemini generateContent endpoint")
if gemini_call["headers"].get("x-goog-api-key") != "test-key":
    raise SystemExit("Learner request does not send the Gemini API key header")
config = gemini_call["json"].get("generationConfig", {})
if config.get("responseMimeType") != "application/json" or "responseJsonSchema" not in config:
    raise SystemExit("Learner request does not enforce Gemini structured JSON output")

ipa_source = "The IPA is designed to represent those qualities of speech that are part of lexical"
ipa_example = (
    "ði ˌaɪ piː ˈeɪ ɪz dɪˈzaɪn tə ˌreprɪˈzent ðəʊz ˈkwɒlətiz əv spiːtʃ "
    "ðətə ˈpɑːtəv ˈleksɪkəl"
)
ipa_request = {}
ipa_language = LearnerLanguage("test-key", "gemini-test")
ipa_language.cache = {
    "pronunciations": {fetch_module.learner_cache_key(ipa_source): "Đờ AI-PI-ÂY"},
    "glossaries": {},
}
ipa_language.save = lambda: None

def fake_ipa_request(name, schema, instructions, payload):
    ipa_request.update({"name": name, "schema": schema, "instructions": instructions, "payload": payload})
    return {"items": [{"id": "0", "guide": ipa_example}]}

ipa_language.request_json = fake_ipa_request
if ipa_language.pronunciations([ipa_source]) != {ipa_source: ipa_example}:
    raise SystemExit("Learner IPA transcription was not accepted verbatim")
if ipa_request.get("name") != "casual_british_ipa":
    raise SystemExit("Learner pronunciation request still uses the legacy profile")
if ipa_request.get("instructions") != LEARNER_IPA_INSTRUCTIONS:
    raise SystemExit("Learner IPA request did not use the canonical connected-speech prompt")
for required in ("weak forms", "linked words", "sound deletion", "without slashes"):
    if required not in LEARNER_IPA_INSTRUCTIONS:
        raise SystemExit(f"Learner IPA prompt omitted {required}")
for invalid_guide in ("Đờ AI-PI-ÂY", "/ði aɪ piː eɪ/", "plain respelling"):
    try:
        validate_casual_british_ipa(ipa_source, invalid_guide)
    except LearnerLanguageError:
        pass
    else:
        raise SystemExit(f"Learner IPA validation accepted invalid output: {invalid_guide}")

class FakeRateLimitedGeminiResponse:
    headers = {"retry-after": "5"}
    text = "Please retry in 51.5s."

if gemini_retry_seconds(FakeRateLimitedGeminiResponse()) != 51.5:
    raise SystemExit("Learner retry must respect the longer Gemini quota delay")

class FakeUnavailableGeminiResponse:
    status_code = 503
    headers = {}
    text = "Temporarily overloaded."

    def raise_for_status(self):
        raise fetch_module.requests.HTTPError("503")

transient_responses = [FakeUnavailableGeminiResponse(), FakeGeminiResponse()]
transient_delays = []
original_sleep = fetch_module.time.sleep
try:
    fetch_module.requests.post = lambda *_args, **_kwargs: transient_responses.pop(0)
    fetch_module.time.sleep = transient_delays.append
    response = LearnerLanguage("test-key", "gemini-test").request_json(
        "smoke", {"type": "object", "properties": {"items": {"type": "array"}}}, "Use JSON.", {"items": []}
    )
finally:
    fetch_module.requests.post = original_post
    fetch_module.time.sleep = original_sleep
if response != {"items": []} or transient_delays != [10]:
    raise SystemExit("Learner request must retry a temporary Gemini 503")

class FakeLearnerLanguage:
    def pronunciations(self, texts):
        return {text: "fəˈnetɪk ˈsɑːmpəl" for text in texts}

    def glossary(self, prayer_title, source_text):
        return [
            {"term": term, "definition": "a simple word in this prayer"}
            for term in ("God", "assistance", "Lord", "haste", "Father", "Spirit")
        ]

learner_body = learner_prayer_body(
    Prayer(
        "Morning Prayer",
        "morning-prayer",
        "<div class=\"stanza\"><div>God, come to my assistance.</div>"
        "<div>Lord, make haste to help me.</div></div>"
        "<h2>Hymn</h2><p>Father and Spirit help us in this prayer.</p>",
    ),
    FakeLearnerLanguage(),
)
if learner_body.count("learner-row") < 8:
    raise SystemExit("Learner mode must pair each source line and glossary explanation")
if "Words in this prayer" not in learner_body or "fəˈnetɪk ˈsɑːmpəl" not in learner_body:
    raise SystemExit("Learner mode is missing glossary IPA output")
if 'class="learner-pronunciation" lang="en-GB"' not in learner_body or 'lang="vi"' in learner_body:
    raise SystemExit("Learner IPA column has the wrong language metadata")
learner_pages = paginate_learner_html(learner_body)
for number, learner_page in enumerate(learner_pages):
    limit = LEARNER_FIRST_PAGE_TARGET_UNITS if number == 0 else LEARNER_PAGE_TARGET_UNITS
    if learner_page_units(learner_html_blocks(learner_page)) > limit:
        raise SystemExit("Learner page exceeds its independent Kindle fill budget")

# A learner heading must travel with at least its first paired line; otherwise
# Paperwhite pages can end with a stranded heading and a large blank area.
heading_fixture = "\n".join(
    [learner_row_html("First short prayer line.", "fɜːst ʃɔːt preə laɪn") for _ in range(14)]
    + [
        "<h2>Psalmody</h2>",
        learner_row_html(
            "The first line after the heading stays together.",
            "ðə fɜːst laɪn ˈɑːftə ðə ˈhedɪŋ steɪz təˈɡeðə",
        ),
    ]
    + [learner_row_html("Another short prayer line.", "əˈnʌðə ʃɔːt preə laɪn") for _ in range(12)]
)
heading_pages = paginate_learner_html(heading_fixture)
for number, heading_page in enumerate(heading_pages[:-1]):
    if learner_html_blocks(heading_page)[-1].lstrip().startswith("<h2"):
        raise SystemExit("Learner heading was stranded at the end of a Kindle page")
wrapped_heading_pages = paginate_learner_html(f"<div>{heading_fixture}</div>")
if wrapped_heading_pages != heading_pages:
    raise SystemExit("A neutral learner transport wrapper collapsed Kindle pagination")
recovered_wrapped_body = learner_body_from_decrypted_pages(
    [f"<h1>Morning Prayer</h1><div>{heading_fixture}</div><nav>Index</nav>"]
)
if paginate_learner_html(recovered_wrapped_body) != heading_pages:
    raise SystemExit("Learner restore could not recover the deployed one-page cache")

# Rebalancing must not move an end-of-page heading forward and immediately
# pull it back forever.  The recovered production cache exposed this cycle.
short_row = learner_row_html("Short line.", "ʃɔːt laɪn")
oscillation_fixture = [
    [short_row] * 18,
    [short_row] * 17 + ["<h2>Psalmody</h2>"],
    [short_row] * 4,
]
rebalanced_fixture = rebalance_learner_pages(oscillation_fixture)
if any(page and page[-1].lstrip().startswith("<h2") for page in rebalanced_fixture[:-1]):
    raise SystemExit("Learner rebalancing stranded a heading without following content")

test_day = EnglishDaySite(
    datetime(2026, 8, 23),
    [Prayer(title, slug, "<p>God, come to my assistance.</p>") for title, slug in ENGLISH_PRAYERS],
    LiturgicalDay("Sunday", "", "test", "August 23"),
)

class BatchLearnerLanguage:
    def __init__(self):
        self.pronunciation_calls = []
        self.glossary_calls = []

    def pronunciations(self, texts):
        self.pronunciation_calls.append(list(texts))
        return {text: "fəˈnetɪk ˈsɑːmpəl" for text in texts}

    def glossaries(self, prayers):
        self.glossary_calls.append(list(prayers))
        return {
            prayer_id: [
                {"term": term, "definition": "a simple word in this prayer"}
                for term in ("God", "come", "to", "my", "assistance", "help")
            ]
            for prayer_id, _, _ in prayers
        }

    def save(self):
        return None

batch_language = BatchLearnerLanguage()
batched_bodies = prepare_english_learner_bodies([test_day], batch_language)
if len(batch_language.pronunciation_calls) != 2 or len(batch_language.glossary_calls) != 1:
    raise SystemExit("Learner preparation must batch pronunciation and glossary API work")
if len(batch_language.glossary_calls[0]) != len(ENGLISH_PRAYERS):
    raise SystemExit("Learner glossary work must include all prayers in one preparation pass")
if set(batched_bodies["2026-08-23"]) != {slug for _, slug in ENGLISH_PRAYERS}:
    raise SystemExit("Batched learner preparation omitted a prayer")

# The ordinary English Breviary remains a three-day edition, but learner
# generation must spend its free API budget only on the current day.
def learner_test_site(date):
    return EnglishDaySite(
        date=date,
        liturgical_day=test_day.liturgical_day,
        prayers=test_day.prayers,
    )

learner_today = datetime(2026, 8, 23, tzinfo=fetch_module.VN_TZ)
learner_sites_by_date = {
    (learner_today + timedelta(days=offset)).date(): learner_test_site(
        (learner_today + timedelta(days=offset)).date()
    )
    for offset in (-1, 0, 1)
}
original_fetch_english_day = fetch_module.fetch_english_day
original_learner_language = fetch_module.LearnerLanguage
original_write_english_breviary = fetch_module.write_english_breviary
original_write_english_learner = fetch_module.write_english_learner
original_learner_key = os.environ.get(fetch_module.LEARNER_GEMINI_API_KEY_ENV)
original_learner_refresh = os.environ.get(fetch_module.LEARNER_REFRESH_ENV)
today_only_language = BatchLearnerLanguage()
learner_write_sites = []
try:
    fetch_module.fetch_english_day = lambda _session, date: learner_sites_by_date[date.date()]
    fetch_module.LearnerLanguage = lambda _key: today_only_language
    fetch_module.write_english_breviary = lambda *_args, **_kwargs: None
    fetch_module.write_english_learner = lambda sites, *_args: learner_write_sites.append(sites)
    os.environ[fetch_module.LEARNER_GEMINI_API_KEY_ENV] = "test-key"
    os.environ[fetch_module.LEARNER_REFRESH_ENV] = "1"
    build_english_breviary(learner_today, "123456")
finally:
    fetch_module.fetch_english_day = original_fetch_english_day
    fetch_module.LearnerLanguage = original_learner_language
    fetch_module.write_english_breviary = original_write_english_breviary
    fetch_module.write_english_learner = original_write_english_learner
    if original_learner_key is None:
        os.environ.pop(fetch_module.LEARNER_GEMINI_API_KEY_ENV, None)
    else:
        os.environ[fetch_module.LEARNER_GEMINI_API_KEY_ENV] = original_learner_key
    if original_learner_refresh is None:
        os.environ.pop(fetch_module.LEARNER_REFRESH_ENV, None)
    else:
        os.environ[fetch_module.LEARNER_REFRESH_ENV] = original_learner_refresh
if len(today_only_language.glossary_calls) != 1 or len(today_only_language.glossary_calls[0]) != len(ENGLISH_PRAYERS):
    raise SystemExit("Learner build must generate glossaries for today only")
if len(learner_write_sites) != 1 or [site.date for site in learner_write_sites[0]] != [learner_today.date()]:
    raise SystemExit("Learner writer must receive today only")

# A legacy encrypted edition must force one IPA regeneration even on a push;
# otherwise its Vietnamese-style rows would be silently repackaged forever.
legacy_profile_language = BatchLearnerLanguage()
legacy_profile_writes = []
original_site_dir = fetch_module.SITE_DIR
try:
    with tempfile.TemporaryDirectory() as temporary_dir:
        fetch_module.SITE_DIR = Path(temporary_dir) / "site"
        legacy_root = fetch_module.SITE_DIR / "breviary" / "en" / "learner"
        legacy_root.mkdir(parents=True)
        (legacy_root / "index.html").write_text(
            '<body class="breviary-page learner-page"></body>', encoding="utf-8"
        )
        if learner_edition_profile_matches(legacy_root):
            raise SystemExit("Legacy learner edition was mistaken for the IPA profile")
        fetch_module.fetch_english_day = lambda _session, date: learner_sites_by_date[date.date()]
        fetch_module.LearnerLanguage = lambda _key: legacy_profile_language
        fetch_module.write_english_breviary = lambda *_args, **_kwargs: None
        fetch_module.write_english_learner = (
            lambda sites, _passcode, bodies: legacy_profile_writes.append((sites, bodies))
        )
        os.environ[fetch_module.LEARNER_GEMINI_API_KEY_ENV] = "test-key"
        os.environ[fetch_module.LEARNER_REFRESH_ENV] = "0"
        build_english_breviary(learner_today, "123456")
finally:
    fetch_module.SITE_DIR = original_site_dir
    fetch_module.fetch_english_day = original_fetch_english_day
    fetch_module.LearnerLanguage = original_learner_language
    fetch_module.write_english_breviary = original_write_english_breviary
    fetch_module.write_english_learner = original_write_english_learner
    if original_learner_key is None:
        os.environ.pop(fetch_module.LEARNER_GEMINI_API_KEY_ENV, None)
    else:
        os.environ[fetch_module.LEARNER_GEMINI_API_KEY_ENV] = original_learner_key
    if original_learner_refresh is None:
        os.environ.pop(fetch_module.LEARNER_REFRESH_ENV, None)
    else:
        os.environ[fetch_module.LEARNER_REFRESH_ENV] = original_learner_refresh
if len(legacy_profile_writes) != 1 or not legacy_profile_language.pronunciation_calls:
    raise SystemExit("Legacy learner cache did not force a one-time IPA refresh")

# A normal push restores the encrypted learner directory from the Actions
# cache, repaginates it locally, and must not spend Gemini quota again.
normal_rebuilds = []
repaged_builds = []
original_site_dir = fetch_module.SITE_DIR
try:
    with tempfile.TemporaryDirectory() as temporary_dir:
        fetch_module.SITE_DIR = Path(temporary_dir) / "site"
        learner_root = fetch_module.SITE_DIR / "breviary" / "en" / "learner"
        learner_bodies = {
            "2026-08-23": {slug: learner_body for _, slug in ENGLISH_PRAYERS}
        }
        write_english_learner([test_day], "123456", learner_bodies)
        preserved_page = learner_root / "index.html"
        if not learner_edition_profile_matches(learner_root):
            raise SystemExit("Encrypted learner output omitted its IPA profile marker")
        if LEARNER_PROFILE_CLASS not in preserved_page.read_text(encoding="utf-8"):
            raise SystemExit("Learner IPA profile marker is not visible outside ciphertext")
        fetch_module.refresh_preserved_learner_stylesheet(learner_root)
        if f"v={fetch_module.BREVIARY_CSS_VERSION}-encrypted-learner" not in preserved_page.read_text(encoding="utf-8"):
            raise SystemExit("Preserved learner CSS reference was not cache-busted")
        fetch_module.fetch_english_day = lambda _session, date: learner_sites_by_date[date.date()]
        fetch_module.LearnerLanguage = lambda *_args: (_ for _ in ()).throw(
            SystemExit("A push with a cached learner must not call Gemini")
        )
        fetch_module.write_english_breviary = lambda *_args, **kwargs: normal_rebuilds.append(kwargs)
        fetch_module.write_english_learner = lambda sites, _passcode, bodies: repaged_builds.append((sites, bodies))
        os.environ[fetch_module.LEARNER_GEMINI_API_KEY_ENV] = "test-key"
        os.environ[fetch_module.LEARNER_REFRESH_ENV] = "0"
        build_english_breviary(learner_today, "123456")
finally:
    fetch_module.SITE_DIR = original_site_dir
    fetch_module.fetch_english_day = original_fetch_english_day
    fetch_module.LearnerLanguage = original_learner_language
    fetch_module.write_english_breviary = original_write_english_breviary
    fetch_module.write_english_learner = original_write_english_learner
    if original_learner_key is None:
        os.environ.pop(fetch_module.LEARNER_GEMINI_API_KEY_ENV, None)
    else:
        os.environ[fetch_module.LEARNER_GEMINI_API_KEY_ENV] = original_learner_key
    if original_learner_refresh is None:
        os.environ.pop(fetch_module.LEARNER_REFRESH_ENV, None)
    else:
        os.environ[fetch_module.LEARNER_REFRESH_ENV] = original_learner_refresh
if normal_rebuilds != [{"preserve_learner": False, "include_learner_link": True}]:
    raise SystemExit("A push must rebuild normal English around the locally repaginated learner")
if len(repaged_builds) != 1 or [site.date for site in repaged_builds[0][0]] != [learner_today.date()]:
    raise SystemExit("A push must repaginate today's cached learner edition")
if set(repaged_builds[0][1]["2026-08-23"]) != {slug for _, slug in ENGLISH_PRAYERS}:
    raise SystemExit("A push lost cached learner rows while repaginating")

with tempfile.TemporaryDirectory() as temporary_dir:
    original_site_dir = fetch_module.SITE_DIR
    fetch_module.SITE_DIR = Path(temporary_dir) / "site"
    try:
        write_english_breviary([test_day], "123456")
        learner_bodies = {
            "2026-08-23": {slug: learner_body for _, slug in ENGLISH_PRAYERS}
        }
        write_english_learner([test_day], "123456", learner_bodies)
        learner_index = fetch_module.SITE_DIR / "breviary" / "en" / "learner" / "index.html"
        if not learner_index.is_file():
            raise SystemExit("Learner writer did not create its encrypted root index")
        restored_bodies = restore_english_learner_bodies(
            learner_index.parent, "123456", test_day.date
        )
        restored_morning = restored_bodies["2026-08-23"]["morning-prayer"]
        if restored_morning.count("learner-row") != learner_body.count("learner-row"):
            raise SystemExit("Cached learner re-pagination lost paired rows")
        original_page_count = len(paginate_learner_html(learner_body))
        restored_pages = paginate_learner_html(restored_morning)
        if original_page_count < 2 or len(restored_pages) != original_page_count:
            raise SystemExit(
                "Cached learner round trip collapsed a multi-page Office into one page"
            )
        if any(
            learner_page_units(learner_html_blocks(page))
            > (fetch_module.LEARNER_FIRST_PAGE_TARGET_UNITS if index == 0 else fetch_module.LEARNER_PAGE_TARGET_UNITS)
            for index, page in enumerate(restored_pages)
        ):
            raise SystemExit("Restored learner Office exceeds its Kindle page budget")
        write_english_learner([test_day], "123456", restored_bodies)
        write_english_breviary([test_day], "123456", preserve_learner=True)
        if not learner_index.is_file():
            raise SystemExit("Normal English rebuild removed the learner edition without an API key")
    finally:
        fetch_module.SITE_DIR = original_site_dir

if text_units(debug_prose(115)) != 11:
    raise SystemExit("Kindle prose calibration drifted from the measured 48-character line")
if not block_units(debug_verse(15)) < PAGE_TARGET_UNITS:
    raise SystemExit("15-line stanza should remain inside the calibrated Kindle budget")
if not block_units(debug_verse(16)) > PAGE_TARGET_UNITS:
    raise SystemExit("16-line stanza should exceed the calibrated Kindle budget")
if not block_units(debug_production_verse(14)) < PAGE_TARGET_UNITS:
    raise SystemExit("14-line production verse should fit the calibrated Kindle budget")
if not block_units(debug_production_verse(15)) > PAGE_TARGET_UNITS:
    raise SystemExit("15-line production verse should exceed the calibrated Kindle budget")

divineoffice_stanza = """
<div class=\"stanza\">
  <div>God Father, praise and glory</div>
  <div>Your children come to sing.</div>
  <div>Goodwill and peace to mankind.</div>
  <div>The gifts your kingdom brings.</div>
</div>
"""
if block_units(divineoffice_stanza) < 4:
    raise SystemExit("Divine Office stanza lines must be measured as separate Kindle rows")

# Regression for 2026-08-16 Kinh Sang 19/23: its 17 visible lines were split
# across seven paragraphs. The old model counted only the lines and ignored
# 7 x 16px of paragraph margins, leaving the bottom navigation below the
# initial Kindle viewport.
fragmented_lines = "".join(
    "<p>" + "<br>".join(f"Dong {line}" for line in range(1, count + 1)) + "</p>"
    for count in (3, 3, 2, 2, 3, 2, 2)
)
single_paragraph_lines = "<p>" + "<br>".join(
    f"Dong {line}" for line in range(1, 18)
) + "</p>"
if not page_units(html_blocks(single_paragraph_lines)) <= PAGE_TARGET_UNITS:
    raise SystemExit("A single 17-line paragraph should retain the measured Kindle capacity")
if not page_units(html_blocks(fragmented_lines)) > PAGE_TARGET_UNITS:
    raise SystemExit("Paragraph margins must push the fragmented 17-line regression over budget")

index_html = Path("site/index.html").read_text(encoding="utf-8")
current_day_names = set(re.findall(r'href="(\d{4}-\d{2}-\d{2})/index\.html"', index_html))
if len(current_day_names) != 3:
    raise SystemExit(f"Expected exactly three day links, found: {sorted(current_day_names)}")

for path in Path("site").rglob("*.html"):
    text = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(text, "lxml")
    if re.search(r"<sup>\d{3,}</sup>", text):
        raise SystemExit(f"Wide verse number missing class in {path}")
    if (path.parent == Path("site") or path.parent.name in current_day_names) and re.search(r"<sup>\d+[A-Za-z]+</sup>", text):
        raise SystemExit(f"Lettered verse marker leaked into {path}")
    if 'class="verse-line"' in text and '</span><br/><span class="verse-line"' in text:
        raise SystemExit(f"Unexpected blank-line br between verse lines in {path}")
    in_psalm_or_canticle = False
    for node in soup.find_all(["h2", "h3", "p"]):
        classes = set(node.get("class", [])) if hasattr(node, "get") else set()
        node_text = node.get_text(" ", strip=True)
        key = unicodedata.normalize("NFD", node_text).encode("ascii", "ignore").decode("ascii").lower()
        key = re.sub(r"[^a-z0-9]+", " ", key).strip()
        if node.name in {"h2", "h3"}:
            in_psalm_or_canticle = False
            continue
        if "indexing" in classes:
            in_psalm_or_canticle = key.startswith("tv ") or key.startswith("tc ")
            continue
        if not in_psalm_or_canticle or node.name != "p":
            continue
        first = next((child for child in node.children if not (isinstance(child, str) and not child.strip())), None)
        if getattr(first, "name", None) == "span" and not first.get("class"):
            first_text = re.sub(r"\s+", " ", first.get_text(" ", strip=True))
            if re.fullmatch(r"\d+ \d+", first_text):
                raise SystemExit(f"Psalm/canticle chapter marker leaked in {path}: {first_text!r}")
        if re.fullmatch(r"\d+", node.get_text(" ", strip=True) or ""):
            raise SystemExit(f"Psalm/canticle standalone chapter marker leaked in {path}: {node_text!r}")
    for initial in soup.select(".illuminated-initial"):
        value = initial.get_text("", strip=True)
        if not value or not unicodedata.category(value[0]).startswith("L"):
            raise SystemExit(f"Illuminated initial is not a letter in {path}: {value!r}")
    if 'class="page-nav paged-nav"' in text and "debug-page" not in text:
        main = soup.find("main")
        if not main:
            raise SystemExit(f"Missing main in {path}")
        for updated in soup.select("p.updated"):
            label = updated.get_text(" ", strip=True)
            if label.startswith("Trang "):
                raise SystemExit(f"Paged note should include prayer title in {path}: {label!r}")
        for nav in main.find_all("nav"):
            nav.decompose()
        units = sum(
            block_units(str(child))
            for child in main.find_all(["h1", "h2", "h3", "p", "div"], recursive=False)
        )
        if units > 20:
            raise SystemExit(f"Page likely too long for Kindle viewport: {path} ({units} units)")

if 'class="illuminated-initial"' in Path("site/kinh-sang-2.html").read_text(encoding="utf-8"):
    raise SystemExit("Unexpected repeated invitatory initial after repeated antiphon")

def require_initial_after_heading(pattern: str, heading_prefix: str, skip_classes=()):
    def page_key(path: Path):
        if "-" in path.stem and path.stem.rsplit("-", 1)[1].isdigit():
            base, number = path.stem.rsplit("-", 1)
            return path.parent, base, int(number)
        return path.parent, path.stem, 1

    page_map = {page_key(path): path for path in Path("site").glob(pattern)}
    found = 0
    for path in Path("site").glob(pattern):
        parent, base, number = page_key(path)
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
        for heading in soup.find_all(["h2", "h3"]):
            if not heading.get_text(" ", strip=True).startswith(heading_prefix):
                continue
            found += 1
            node = heading.find_next_sibling()
            while node is not None:
                classes = set(node.get("class", [])) if hasattr(node, "get") else set()
                if classes & set(skip_classes):
                    node = node.find_next_sibling()
                    continue
                if getattr(node, "name", None) in {"p", "div"} and node.get_text(" ", strip=True):
                    if not node.select_one(".illuminated-initial"):
                        raise SystemExit(f"Missing illuminated initial after {heading_prefix} in {path}")
                    break
                node = node.find_next_sibling()
            else:
                next_path = page_map.get((parent, base, number + 1))
                if next_path:
                    next_soup = BeautifulSoup(next_path.read_text(encoding="utf-8"), "lxml")
                    for candidate in next_soup.find_all(["p", "div"], recursive=True):
                        if candidate.find_parent(["p", "h2", "h3"]):
                            continue
                        classes = set(candidate.get("class", [])) if hasattr(candidate, "get") else set()
                        if "updated" in classes or classes & set(skip_classes):
                            continue
                        if candidate.get_text(" ", strip=True):
                            if not candidate.select_one(".illuminated-initial"):
                                raise SystemExit(f"Missing illuminated initial after {heading_prefix} in {next_path}")
                            break
                    else:
                        raise SystemExit(f"Could not find body after {heading_prefix} in {path}")
                else:
                    raise SystemExit(f"Could not find body after {heading_prefix} in {path}")
    if not found:
        raise SystemExit(f"Could not find heading: {heading_prefix} in {pattern}")

require_initial_after_heading("kinh-sang*.html", "Lời Chúa")
require_initial_after_heading("kinh-*.html", "Xướng đáp")
require_initial_after_heading("kinh-chieu*.html", "Thánh ca Tin Mừng", skip_classes=("antiphon",))

found_marian_canticle = False
for path in Path("site").glob("kinh-toi*.html"):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    for title in soup.find_all(class_="title"):
        if not any(name in title.get_text(" ", strip=True) for name in ("Salve Regina", "Ave Regina", "Sub tuum", "Regina caeli")):
            continue
        first_body = title.find_next_sibling("p")
        if not first_body or not first_body.select_one(".illuminated-initial"):
            raise SystemExit(f"Missing illuminated initial in Marian canticle in {path}")
        found_marian_canticle = True
        break
if not found_marian_canticle:
    raise SystemExit("Could not find Marian canticle title in Kinh Tối")

for pattern in ("kinh-sang*.html", "kinh-chieu*.html"):
    visible_text = "\n".join(
        BeautifulSoup(path.read_text(encoding="utf-8"), "lxml").get_text("", strip=True)
        for path in Path("site").glob(pattern)
    )
    if "Xin Thiên Chúa toàn năng" not in visible_text:
        raise SystemExit(f"Missing visible blessing text in {pattern}")

if Path("build/kinh-sach.json").exists():
    import json

    payload = json.loads(Path("build/kinh-sach.json").read_text(encoding="utf-8"))
    prayer_items = payload.get("prayer")
    prayer_payload = prayer_items[0] if isinstance(prayer_items, list) and prayer_items else {}
    if not prayer_payload.get("tedeum"):
        office_html = "\n".join(path.read_text(encoding="utf-8") for path in Path("site").glob("kinh-sach*.html"))
        if "Te Deum" in office_html or "Thánh thi “Lạy Thiên Chúa”" in office_html:
            raise SystemExit("Te Deum rendered even though source payload disables it")

for slug, root_key in [
    ("kinh-sach", "office"),
    ("kinh-sang", "morning"),
    ("kinh-trua-gio-ba", "daytime"),
    ("kinh-trua-gio-sau", "daytime"),
    ("kinh-trua-gio-chin", "daytime"),
    ("kinh-chieu", "evening"),
]:
    payload_path = Path(f"build/{slug}.json")
    if not payload_path.exists():
        continue
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    season = str(payload.get("date_info", {}).get("season") or "").strip().lower()
    prayer_items = payload.get("prayer")
    prayer_payload = prayer_items[0] if isinstance(prayer_items, list) and prayer_items else {}
    root = prayer_payload.get(root_key, {})
    if season in {"easter", "eas"} or not isinstance(root, dict):
        continue
    has_easter_responsory = any(
        isinstance(value, dict)
        and "responsory" in key.lower()
        and "only-easter" in str(value.get("CONTENT") or "")
        for key, value in root.items()
    )
    if not has_easter_responsory:
        continue
    html = "\n".join(path.read_text(encoding="utf-8") for path in Path("site").glob(f"{slug}*.html"))
    visible_text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    if "Ha-lê-lui-a. Ha-lê-lui-a." in visible_text:
        raise SystemExit(f"Easter responsory variant leaked into non-Easter output for {slug}")

for path in Path("site").rglob("kinh-sang*.html"):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    markers = soup.find_all(string=lambda value: value and "Tc Đn 3,57-88.56" in value)
    for marker in markers:
        marker_node = marker.parent
        content_node = marker_node.find_next("p") if marker_node else None
        following_text = []
        node = content_node.find_next_sibling() if content_node else None
        while node is not None:
            if getattr(node, "name", None) in {"h2", "h3"}:
                break
            following_text.append(node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node).strip())
            node = node.find_next_sibling()
        if "Vinh danh Chúa Cha" in "\n".join(following_text):
            raise SystemExit(f"Unexpected Glory Be after Daniel canticle in {path}")

responsive_index = Path("site/index-responsive.html")
if not responsive_index.exists():
    raise SystemExit("Missing responsive index")
responsive_index_html = responsive_index.read_text(encoding="utf-8")
if 'class="responsive-page responsive-index"' not in responsive_index_html:
    raise SystemExit("Responsive index missing responsive body class")
if "Trở về bản Kindle" not in responsive_index_html:
    raise SystemExit("Responsive index missing Kindle return link")
if "kinh-sang-responsive.html" not in responsive_index_html:
    raise SystemExit("Responsive index missing responsive prayer links")

kindle_index_html = Path("site/index.html").read_text(encoding="utf-8")
if "Phiên bản này dành cho trình duyệt web tối giản của Kindle" not in kindle_index_html:
    raise SystemExit("Kindle index missing explanatory note")
if "index-responsive.html" not in kindle_index_html:
    raise SystemExit("Kindle index missing responsive link")
if kindle_index_html.find('class="home-list"') > kindle_index_html.find('class="kindle-note"'):
    raise SystemExit("Kindle index note should appear after prayer list")
if kindle_index_html.find('class="home-list"') > kindle_index_html.find('class="mode-switch"'):
    raise SystemExit("Kindle index mode switch should appear after prayer list")
if responsive_index_html.find('class="home-list"') > responsive_index_html.find('class="mode-switch"'):
    raise SystemExit("Responsive index mode switch should appear after prayer list")
if ".responsive-page .note" not in Path("site/style.css").read_text(encoding="utf-8"):
    raise SystemExit("Responsive note font rule missing")

for title, slug in [
    ("Kinh Sách", "kinh-sach"),
    ("Kinh Sáng", "kinh-sang"),
    ("Kinh Trưa - Giờ Ba", "kinh-trua-gio-ba"),
    ("Kinh Trưa - Giờ Sáu", "kinh-trua-gio-sau"),
    ("Kinh Trưa - Giờ Chín", "kinh-trua-gio-chin"),
    ("Kinh Chiều", "kinh-chieu"),
    ("Kinh Tối", "kinh-toi"),
]:
    path = Path(f"site/{slug}-responsive.html")
    if not path.exists():
        raise SystemExit(f"Missing responsive prayer page: {path}")
    text = path.read_text(encoding="utf-8")
    if 'class="responsive-page responsive-prayer"' not in text:
        raise SystemExit(f"Responsive prayer missing body class: {path}")
    if 'class="page-nav responsive-nav"' not in text:
        raise SystemExit(f"Responsive prayer missing three-button nav: {path}")
    if "Mục lục" not in text or "index-responsive.html" not in text:
        raise SystemExit(f"Responsive prayer missing responsive index link: {path}")
    if 'class="page-nav paged-nav"' in text or "Trang 2/" in text:
        raise SystemExit(f"Responsive prayer should not be paginated: {path}")

dated_day_names = {
    path.name
    for path in Path("site").iterdir()
    if path.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name)
}
if dated_day_names != current_day_names:
    raise SystemExit(
        f"Dated directories do not match yesterday/today/tomorrow: "
        f"expected {sorted(current_day_names)}, found {sorted(dated_day_names)}"
    )
for day_name in current_day_names:
    if not (Path("site") / day_name / "index.html").is_file():
        raise SystemExit(f"Missing dated index for {day_name}")

for path in Path("site").rglob("*.html"):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    for title in soup.select(".feast-title"):
        text = title.get_text(" ", strip=True)
        if "<br" in text.lower():
            raise SystemExit(f"Liturgical title contains literal br markup in {path}: {text!r}")

expected_john_title = "Ngày 24 tháng 6 - SINH NHẬT THÁNH GIO-AN TẨY GIẢ"
john_index = Path("site/2026-06-24/index.html")
if john_index.exists():
    text = BeautifulSoup(john_index.read_text(encoding="utf-8"), "lxml").select_one(".feast-title").get_text(" ", strip=True)
    if text != expected_john_title:
        raise SystemExit(f"Unexpected June 24 liturgical title: {text!r}")

for path in [Path("site/2026-06-23/kinh-chieu.html"), Path("site/2026-06-23/kinh-toi.html")]:
    if path.exists():
        text = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml").select_one(".feast-title").get_text(" ", strip=True)
        if text != expected_john_title:
            raise SystemExit(f"Expected evening vigil title in {path}: {text!r}")

for path in Path("site").glob("*.html"):
    text = path.read_text(encoding="utf-8")
    if text.count("Chúa Nhật Tuần XI - Mùa Thường Niên") > 1:
        raise SystemExit(f"Repeated liturgical title in {path}")

# The Breviary skin must consume the exact same page fragments as the original
# Kindle mode. Only its shell classes, ornaments, and navigation may differ.
for root in [Path("site"), *(Path("site") / name for name in current_day_names)]:
    breviary_root = Path("site/breviary") if root == Path("site") else Path("site/breviary") / root.name
    original_pages = {}
    for path in root.glob("kinh-*.html"):
        text = path.read_text(encoding="utf-8")
        if 'class="page-nav paged-nav"' in text:
            original_pages[path.name] = path
    breviary_pages = {path.name: path for path in breviary_root.glob("kinh-*.html")}
    if set(original_pages) != set(breviary_pages):
        raise SystemExit(f"Breviary page boundaries differ in {breviary_root}")
    for name, original_path in original_pages.items():
        original_soup = BeautifulSoup(original_path.read_text(encoding="utf-8"), "lxml")
        breviary_soup = BeautifulSoup(breviary_pages[name].read_text(encoding="utf-8"), "lxml")
        for soup in (original_soup, breviary_soup):
            for nav in soup.select("nav.page-nav"):
                nav.decompose()
        if original_soup.main.decode_contents().strip() != breviary_soup.main.decode_contents().strip():
            raise SystemExit(f"Breviary content drifted from original page: {breviary_pages[name]}")

breviary_first = Path("site/breviary/kinh-sang.html").read_text(encoding="utf-8")
breviary_second = Path("site/breviary/kinh-sang-2.html").read_text(encoding="utf-8")
breviary_first_soup = BeautifulSoup(breviary_first, "lxml")
breviary_second_soup = BeautifulSoup(breviary_second, "lxml")
if set(breviary_first_soup.body.get("class", [])) != {"breviary-page", "breviary-first"}:
    raise SystemExit("Breviary first page missing distinct first-page treatment")
if set(breviary_second_soup.body.get("class", [])) != {"breviary-page"}:
    raise SystemExit("Breviary continuation page should return to the minimal treatment")
if "&#8249;" not in breviary_second or "&#8250;" not in breviary_second:
    raise SystemExit("Breviary navigation missing lightweight chevrons")
if "&#9664;" in breviary_second or "&#9654;" in breviary_second:
    raise SystemExit("Breviary navigation retained modern solid arrows")
breviary_soup = BeautifulSoup(breviary_first, "lxml")
if len(breviary_soup.find_all("link", rel="stylesheet")) != 1:
    raise SystemExit("Breviary pages must keep exactly one stylesheet request")
stylesheet_href = breviary_soup.find("link", rel="stylesheet").get("href")
if not re.fullmatch(r"\.\./breviary\.css\?v=\d+", stylesheet_href or ""):
    raise SystemExit(f"Breviary page uses unexpected stylesheet: {stylesheet_href}")
breviary_css = Path("site/breviary.css").read_text(encoding="utf-8")
if "✠" not in breviary_css or "url(" in breviary_css or "@import" in breviary_css:
    raise SystemExit("Breviary ornaments must be request-free CSS and Unicode")
heading_cross_rule = re.search(
    r"\.breviary-page h2:before,\s*\.breviary-page h3:before\s*\{([^}]+)\}",
    breviary_css,
    re.DOTALL,
)
if not heading_cross_rule:
    raise SystemExit("Breviary heading-cross rule missing")
heading_cross_css = heading_cross_rule.group(1)
if "right: 100%" not in heading_cross_css or "margin-right:" not in heading_cross_css:
    raise SystemExit("Heading cross must be right-anchored with an explicit gap")
if re.search(r"(^|;)\s*left\s*:", heading_cross_css):
    raise SystemExit("Heading cross must not use glyph-width-dependent left positioning")
if breviary_soup.find("style"):
    raise SystemExit("Breviary page should not duplicate shared CSS inline")
PY

if test -f build/kinh-toi.json; then
  "$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
from bs4 import BeautifulSoup

payload = json.loads(Path("build/kinh-toi.json").read_text(encoding="utf-8"))
season = payload.get("date_info", {}).get("season")
html = "\n".join(path.read_text(encoding="utf-8") for path in Path("site").glob("kinh-toi*.html"))
visible_text = "\n".join(
    BeautifulSoup(path.read_text(encoding="utf-8"), "lxml").get_text("", strip=True)
    for path in Path("site").glob("kinh-toi*.html")
)
if season == "easter":
    expected_hymn = "Ngôi Lời Thánh Phụ quang vinh"
else:
    day = int(payload.get("date_info", {}).get("today", {}).get("date", 0))
    if day % 2 == 0:
        expected_hymn = "Đêm tối xuống dần trên cõi thế"
    else:
        expected_hymn = "Muôn lạy Chúa Ki-tô Ánh Sáng"
if expected_hymn not in visible_text:
    raise SystemExit(f"Missing expected Kinh Tối hymn: {expected_hymn}")
if season not in {"christmas", "easter"}:
    day = int(payload.get("date_info", {}).get("today", {}).get("date", 0))
    titles = [
        "Kính chào Đức Nữ Vương",
        "Kính lạy Bà, Vị Nữ Hoàng Thiên Quốc",
        "Lạy Đức Mẹ Chúa Trời",
    ]
    expected = titles[day % len(titles)]
    if expected not in html:
        raise SystemExit(f"Missing expected Marian antiphon: {expected}")
PY
fi
