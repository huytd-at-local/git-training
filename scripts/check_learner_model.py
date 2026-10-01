"""Isolated model qualification; never writes production cache or site output."""
import argparse
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

if __package__:
    from . import fetch
else:
    import fetch


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
    return {"date": date_name, "model": language.model, "requests_per_minute": fetch.LEARNER_REQUESTS_PER_WINDOW,
            "cold_requests": cold_requests, "cold_seconds": cold_seconds, "warm_requests": warm.total_requests,
            "source_units": len(source_units), "unique_source_units": len(set(source_units)),
            "encrypted_round_trip": "passed: both modes, root and dated", "kindle_pages": page_counts,
            "audit_samples": audit, "automated_gate": "passed", "manual_quality_review": "required"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("sample", "full-day"), default="sample")
    parser.add_argument("--date", default="")
    args = parser.parse_args()
    date = qualification_date(args.date)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with tempfile.TemporaryDirectory(prefix="learner-qualification-") as directory:
        root = Path(directory)
        with patch.object(fetch, "CACHE_DIR", root / "cache"), patch.object(fetch, "LEARNER_CACHE_FILE", root / "cache" / "language.json"), patch.object(fetch, "LEARNER_REQUESTS_PER_WINDOW", 4), patch.dict(os.environ, {fetch.LEARNER_GEMINI_FALLBACK_MODELS_ENV: ""}):
            language = fetch.LearnerLanguage(os.environ[fetch.LEARNER_GEMINI_API_KEY_ENV])
            if args.scope == "full-day":
                result = qualify_full_day(language, date, root)
            else:
                sentences = ["Glory be to the Father, and to the Son, and to the Holy Spirit.",
                             "Lord, open my lips, and my mouth will proclaim your praise.",
                             "Have mercy on us and forgive us our sins.", "Let us give thanks to the Lord our God."]
                result = {"model": language.model, "ipa": language.pronunciations(sentences),
                          "glossary": language.glossary("Morning Prayer", " ".join(sentences))}
            encoded = json.dumps(result, ensure_ascii=False, indent=2)
            print(encoded)
            summary = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary:
                with open(summary, "a", encoding="utf-8") as stream:
                    stream.write("\n### Isolated learner qualification\n\n```json\n" + encoded + "\n```\n")


if __name__ == "__main__":
    main()
