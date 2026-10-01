"""Isolated model qualification; never writes production cache or site output."""
import argparse
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

if __package__:
    from . import fetch
else:
    import fetch


# Candidate prompt only: production fetch.py and its cache/profile stay unchanged.
CONSERVATIVE_IPA_INSTRUCTIONS = (
    "Transcribe every supplied English item into accurate contemporary Southern British "
    "non-rhotic IPA for relaxed but clear connected speech. Preserve every spoken word "
    "and its lexical identity, stressed vowels/diphthongs and normal lexical stress. "
    "Use ordinary weak forms for unstressed function words and natural linking between "
    "words. Light consonant elision is optional only in familiar unstressed consonant "
    "clusters; never invent consonant substitutions or delete/change a content word's "
    "stressed vowel. If unsure about a reduction, use the normal British pronunciation "
    "in connected speech instead of an exaggerated reduction. Check each transcription "
    "against its own source text before returning it. Use IPA primary/secondary stress "
    "marks and separate IPA symbols tʃ and dʒ, not ligatures. Speak written numbers as "
    "English words. Do not pronounce non-spoken liturgical symbols +, *, or dagger marks; "
    "do not copy digits, parentheses, brackets, colon labels or quotation marks into IPA. "
    "Use ordinary IPA spaces and stress/length marks. Return only the IPA guide for each "
    "supplied id, without slashes, brackets, labels, explanations, markdown, capital "
    "letters or respelling. Do not paraphrase, substitute names, or omit spoken content."
)

# Bounded lexical checks for the observed failures, not a general IPA evaluator.
# Accept light linking, dark l and glottal t; do not enforce one exact whole guide.
IPA_REGRESSION_CASES = (
    ("almighty-and-praise", "We praise you, the Lord God Almighty, *",
     (r"ɔː[lɫ][ˈˌ]?maɪ[tʔ][iɪ]", r"preɪ[zʒ]")),
    ("whatever-and-because", "But whatever gains I had, these I have come to consider a loss because of Christ.",
     (r"w[ɒɔ]ˈ?[tʔ]ˈ?[eɛ]və", r"b[ɪə]ˈ?k[ɒə]z[\s‿ˈˌ]*(?:əv|ɒv)")),
)


def verify_ipa_regressions(guides: dict[str, str]) -> list[dict]:
    samples = []
    failures = []
    for name, source, patterns in IPA_REGRESSION_CASES:
        guide = guides.get(source, "")
        passed = all(re.search(pattern, guide) for pattern in patterns)
        samples.append({"case": name, "source": source, "guide": guide,
                        "lexical_checks": "passed" if passed else "failed"})
        if not passed:
            failures.append(name)
    logging.info("IPA lexical regression samples: %s", json.dumps(samples, ensure_ascii=False))
    if failures:
        raise ValueError("IPA lexical regressions failed: " + ", ".join(failures))
    return samples


def qualification_date(value: str) -> datetime:
    if not value:
        return datetime.now(fetch.VN_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=fetch.VN_TZ)


def paired_rows(body: str) -> list[tuple[str, str]]:
    rows = []
    for row in fetch.fragment_soup(body).select(".learner-row"):
        left = row.select_one(".learner-english")
        right = row.select_one(".learner-pronunciation")
        if left is None or right is None:
            raise ValueError("Incomplete paired learner row")
        rows.append((left.get_text(" ", strip=True), right.get_text(" ", strip=True)))
    if not rows or any(not left or not right for left, right in rows):
        raise ValueError("Empty learner content")
    return rows


def verify_editions(root: Path, site, bodies, passcode: str) -> dict:
    date_name = fetch.date_dir_name(site.date)
    fetch.validate_encrypted_english_bundle(root)
    expected = {prayer.slug for prayer in site.prayers}
    if set(bodies[date_name]) != expected:
        raise ValueError("Learner bodies do not cover all five Offices")
    page_counts = {}
    for mode in ("learner", "learner-responsive"):
        mode_root = root / mode
        for shell_root in (mode_root, mode_root / date_name):
            if not fetch.learner_edition_profile_matches(shell_root):
                raise ValueError(f"Missing date/profile for {mode}")
            # Only the root unlock page is passcode-encrypted. Dated indexes
            # and all prayer pages use the key derived from that root page.
            sources = [{"id": "unlock", "ciphertext": fetch.encrypted_shell_ciphertext(mode_root / "index.html")}]
            if shell_root != mode_root:
                sources.append({"id": "dated-index", "ciphertext": fetch.encrypted_shell_ciphertext(shell_root / "index.html")})
            page_ids = {}
            for slug in sorted(expected):
                paths = fetch.learner_page_files(shell_root, slug) if mode == "learner" else [shell_root / f"{slug}.html"]
                page_ids[slug] = [f"{slug}-{index}" for index in range(len(paths))]
                sources.extend({"id": page_id, "ciphertext": fetch.encrypted_shell_ciphertext(path)} for page_id, path in zip(page_ids[slug], paths))
            decrypted = fetch.decrypt_english_pages(sources, passcode)
            restored = {slug: "\n".join(decrypted[page_id] for page_id in ids) for slug, ids in page_ids.items()}
            if mode == "learner":
                page_counts[mode + ("-dated" if shell_root != mode_root else "")] = sum(map(len, page_ids.values()))
            for slug in expected:
                if paired_rows(restored[slug]) != paired_rows(bodies[date_name][slug]):
                    raise ValueError(f"Encrypted round-trip changed rows: {mode}/{slug}")
    return page_counts


def qualify_full_day(language, date: datetime, root: Path) -> dict:
    with fetch.requests.Session() as session:
        site = fetch.fetch_english_day(session, date)
    expected = {slug for _, slug in fetch.ENGLISH_PRAYERS}
    if len(site.prayers) != 5 or {prayer.slug for prayer in site.prayers} != expected:
        raise ValueError("Source day is not the complete five-Office workload")
    source_units = [value for prayer in site.prayers for kind, value in fetch.learner_source_units(prayer.body_html) if kind == "sentence"]
    if not source_units:
        raise ValueError("Source day has no learner sentences")
    started = time.monotonic()
    bodies = fetch.prepare_english_learner_bodies([site], language)
    cold_seconds = round(time.monotonic() - started, 2)
    cold_requests = language.total_requests
    if cold_requests == 0:
        raise ValueError("Cold qualification made no model requests")
    # Reload the on-disk isolated cache, not the original in-memory state.
    warm = fetch.LearnerLanguage(language.api_key, language.model)
    warm_bodies = fetch.prepare_english_learner_bodies([site], warm)
    if warm.total_requests != 0 or warm_bodies != bodies:
        raise ValueError("Warm-cache qualification did not reuse all language work")
    english_root = root / "en"
    # Synthetic passcode, never the real site's secret. Output is temporary only.
    passcode = "123456"
    fetch.write_english_breviary([site], passcode, target_root=english_root)
    fetch.write_english_learner([site], passcode, bodies, target_root=english_root / "learner")
    fetch.write_english_learner_responsive([site], passcode, bodies, target_root=english_root / "learner-responsive")
    page_counts = verify_editions(english_root, site, bodies, passcode)
    date_name = fetch.date_dir_name(date)
    audit = {}
    for prayer in site.prayers:
        body = bodies[date_name][prayer.slug]
        rows = paired_rows(body)
        source_rows = fetch.fragment_soup(body).select(".learner-row:not(.learner-glossary-row)")
        original = [value for kind, value in fetch.learner_source_units(prayer.body_html) if kind == "sentence"]
        if [row.select_one(".learner-english").get_text(" ", strip=True) for row in source_rows] != original:
            raise ValueError(f"Source content changed: {prayer.slug}")
        glossary_rows = fetch.fragment_soup(body).select(".learner-glossary-row")
        if not 6 <= len(glossary_rows) <= 12:
            raise ValueError(f"Incomplete glossary: {prayer.slug}")
        glossary = paired_rows(str(glossary_rows[0]))[0]
        audit[prayer.slug] = {"source_rows": len(original), "glossary_rows": len(glossary_rows),
                             "ipa_samples": [rows[0], rows[len(original) // 2]], "glossary_sample": glossary}
    # Inspect actual full-day rows too, so a standalone small sample cannot
    # hide a recurrence of the same errors in a large batch. No repair/filtering.
    all_rows = dict(row for prayers in bodies.values() for body in prayers.values() for row in paired_rows(body))
    present = [source for _, source, _ in IPA_REGRESSION_CASES if source in all_rows]
    for name, source, patterns in IPA_REGRESSION_CASES:
        if source in all_rows and not all(re.search(pattern, all_rows[source]) for pattern in patterns):
            logging.error("Full-day IPA regression: %s source=%r guide=%r", name, source, all_rows[source])
            raise ValueError(f"Full-day IPA lexical regression failed: {name}")
    regression_requests_before = language.total_requests
    regression_guides = language.pronunciations([source for _, source, _ in IPA_REGRESSION_CASES])
    regression_samples = verify_ipa_regressions(regression_guides)
    return {"date": date_name, "model": language.model, "requests_per_minute": fetch.LEARNER_REQUESTS_PER_WINDOW,
            "cold_requests": cold_requests, "cold_seconds": cold_seconds, "warm_requests": warm.total_requests,
            "source_units": len(source_units), "unique_source_units": len(set(source_units)),
            "regression_extra_requests": language.total_requests - regression_requests_before,
            "regressions_present_in_full_day": len(present), "ipa_regression_samples": regression_samples,
            "encrypted_round_trip": "passed: both modes, root and dated", "kindle_pages": page_counts,
            "audit_samples": audit, "automated_gate": "passed", "manual_quality_review": "required"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("sample", "full-day"), default="sample")
    parser.add_argument("--date", default="")
    parser.add_argument("--ipa-prompt", choices=("baseline", "conservative"), default="baseline")
    args = parser.parse_args()
    date = qualification_date(args.date)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with tempfile.TemporaryDirectory(prefix="learner-qualification-") as directory:
        root = Path(directory)
        prompt = CONSERVATIVE_IPA_INSTRUCTIONS if args.ipa_prompt == "conservative" else fetch.LEARNER_IPA_INSTRUCTIONS
        with patch.object(fetch, "CACHE_DIR", root / "cache"), patch.object(fetch, "LEARNER_CACHE_FILE", root / "cache" / "language.json"), patch.object(fetch, "LEARNER_REQUESTS_PER_WINDOW", 4), patch.object(fetch, "LEARNER_IPA_INSTRUCTIONS", prompt), patch.dict(os.environ, {fetch.LEARNER_GEMINI_FALLBACK_MODELS_ENV: ""}):
            language = fetch.LearnerLanguage(os.environ[fetch.LEARNER_GEMINI_API_KEY_ENV])
            if args.scope == "full-day":
                result = qualify_full_day(language, date, root)
            else:
                sentences = ["Glory be to the Father, and to the Son, and to the Holy Spirit.",
                             "Lord, open my lips, and my mouth will proclaim your praise.",
                             "Have mercy on us and forgive us our sins.", "Let us give thanks to the Lord our God."]
                result = {"model": language.model, "ipa": language.pronunciations(sentences),
                          "glossary": language.glossary("Morning Prayer", " ".join(sentences))}
            result["ipa_prompt"] = args.ipa_prompt
            encoded = json.dumps(result, ensure_ascii=False, indent=2)
            print(encoded)
            summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary:
                with open(summary, "a", encoding="utf-8") as stream:
                    stream.write("\n### Isolated learner qualification\n\n```json\n" + encoded + "\n```\n")


if __name__ == "__main__":
    main()
