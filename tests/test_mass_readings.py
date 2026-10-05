import copy
import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from bs4 import BeautifulSoup
from scripts import fetch


FIXTURES = Path(__file__).parent / "fixtures/mass-readings"


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def text(fragment):
    return re.sub(r"\s+", " ", BeautifulSoup(fragment, "lxml").get_text(" ", strip=True)).strip()


def selected_source_parts(mass):
    first = mass["reading1"][0]
    gospel = mass["gospel"][0]
    second = mass["reading2"][0] if mass.get("reading2") else None
    parts = [
        ("Ca nhập lễ", mass["introit"][0], False),
        ("Bài đọc 1", first, True),
        ("Đáp ca", {"INDEXING": first["INDEXING_2"], "CONTENT": first["CONTENT_2"]}, False),
        ("Bài đọc 2", second, True),
        ("Tung hô Tin Mừng", {"INDEXING": gospel["INDEXING_2"], "CONTENT": gospel["CONTENT_2"]}, False),
        ("Tin Mừng", gospel, True),
        ("Ca hiệp lễ", mass["communion"][0], False),
    ]
    return [(title, fields, reading) for title, fields, reading in parts if fields is not None]


class MassSourceTest(unittest.TestCase):
    def test_fetch_requests_explicit_vietnam_date(self):
        session = Mock()
        session.post.return_value.json.return_value = fixture("weekday")
        date = datetime(2026, 10, 3, tzinfo=fetch.VN_TZ)
        prayer = fetch.fetch_mass_reading(session, date)
        args, kwargs = session.post.call_args
        self.assertEqual(args, (fetch.MASS_READING_URL,))
        self.assertEqual(kwargs["data"], {
            "day": 3, "month": 10, "year": 2026,
            "seldate": "Sat Oct 03 2026 00:00:00 GMT+0700 (Indochina Time)",
        })
        self.assertEqual(kwargs["headers"]["X-Requested-With"], "XMLHttpRequest")
        self.assertEqual(kwargs["headers"]["Referer"], fetch.MASS_READING_URL)
        session.post.return_value.raise_for_status.assert_called_once()
        # This fixture's data.today is October 4, not the requested October 3.
        self.assertIn("Thứ Bảy", prayer.liturgical_day.title)

    def test_fetch_failures_identify_source_and_requested_day(self):
        for failure in (requests.Timeout("offline"), requests.HTTPError("503"), ValueError("invalid JSON")):
            with self.subTest(failure=failure):
                session = Mock()
                session.post.side_effect = failure
                with self.assertRaisesRegex(ValueError, "Mass readings for 2026-10-03 failed"):
                    fetch.fetch_mass_reading(session, datetime(2026, 10, 3))
        for payload in (None, {}, {"success": False, "data": None}, {"success": True, "data": None}):
            with self.subTest(payload=payload):
                session = Mock()
                session.post.return_value.json.return_value = payload
                with self.assertRaisesRegex(ValueError, "Mass readings for 2026-10-03 failed"):
                    fetch.fetch_mass_reading(session, datetime(2026, 10, 3))

    def test_source_defaults_and_exact_normal_content(self):
        for name in ("weekday", "sunday-multiple-masses", "multiple-readings", "long-short-gospel"):
            with self.subTest(name=name):
                payload = fixture(name)
                original = copy.deepcopy(payload)
                prayer = fetch.render_mass_reading(payload["data"])
                mass = payload["data"]["mass_reading"][0]
                source_parts = selected_source_parts(mass)
                soup = BeautifulSoup(prayer.body_html, "lxml")
                self.assertEqual([h.get_text() for h in soup.select("h2")], [title for title, _, _ in source_parts])
                for heading, (title, fields, reading) in zip(soup.select("h2"), source_parts):
                    siblings = []
                    for sibling in heading.next_siblings:
                        if getattr(sibling, "name", None) == "h2":
                            break
                        siblings.append(str(sibling))
                    expected = [fields[key] for key in ("INDEXING", "TITLE", "EPITOMIZE", "LEAD") if fields.get(key) and (reading or key == "INDEXING")]
                    expected.append(fields["CONTENT"])
                    self.assertEqual(text("".join(siblings)), text(" ".join(expected)), title)
                self.assertEqual(payload, original, "Rendering must not mutate source choices")
                self.assertIsNone(soup.select_one("script, style, button, select, a"))
                # Every source verse marker remains a regular, visible superscript.
                expected_numbers = [number.get_text() for _, fields, _ in source_parts for number in BeautifulSoup(fields["CONTENT"], "lxml").select("sup")]
                self.assertEqual([number.get_text() for number in soup.select("sup")], expected_numbers)
                self.assertIsNone(soup.select_one(".verse-line > sup"))

    def test_mass_has_its_own_liturgical_metadata(self):
        prayer = fetch.render_mass_reading(fixture("sunday-multiple-masses")["data"])
        self.assertEqual(prayer.liturgical_day.title, "Kính trọng thể lễ Đức Mẹ Mân Côi")
        self.assertEqual(prayer.liturgical_day.date_title, "Ngày 07 tháng 10")

    def test_first_gospel_is_full_form(self):
        data = fixture("long-short-gospel")["data"]
        prayer = fetch.render_mass_reading(data)
        self.assertIn("Mt 22,1-14", prayer.body_html)
        self.assertNotIn("Mt 22,1-10", prayer.body_html)
        self.assertIn("14", [node.get_text() for node in BeautifulSoup(prayer.body_html, "lxml").select("sup")])

    def test_missing_second_reading_has_no_empty_heading(self):
        prayer = fetch.render_mass_reading(fixture("weekday")["data"])
        self.assertNotIn("Bài đọc 2", prayer.body_html)

    def test_special_default_variants_and_source_emphasis(self):
        payload = fixture("special")
        prayer = fetch.render_mass_reading(payload["data"])
        soup = BeautifulSoup(prayer.body_html, "lxml")
        self.assertEqual([h.get_text(" ", strip=True) for h in soup.select("h2")], ["Bài đọc 1", "Đáp ca", "Tin Mừng"])
        self.assertIn("Bài đọc đầy đủ mặc định.", soup.get_text())
        self.assertNotIn("không được chọn", soup.get_text())
        self.assertNotIn("Menu lựa chọn nguồn", soup.get_text())
        self.assertIsNone(soup.select_one("button, script, select"))
        self.assertEqual(soup.select_one("em").get_text(), "Lời hướng dẫn nguồn.")
        self.assertEqual(soup.select_one("sup").get_text(), "1a")

    def test_seasonal_variants_match_source_in_normal_and_special_formats(self):
        seasons = {"LNT": "lent", "CHR": "christmas", "ADV": "advent", "EAS": "easter", "ORD": "ordinary"}
        markers = "".join(f'<p class="only-{name}">ONLY-{name}</p><p class="not-{name}">NOT-{name}</p>' for name in seasons.values())
        for fixture_name in ("weekday", "special"):
            for code, selected in seasons.items():
                data = fixture(fixture_name)["data"]
                mass = data["mass_reading"][0]
                mass["date_info"]["season"] = code
                if fixture_name == "special":
                    mass["special_content"] += markers
                else:
                    mass["gospel"][0]["CONTENT_2"] = markers
                body = fetch.render_mass_reading(data).body_html
                with self.subTest(format=fixture_name, season=code):
                    for name in seasons.values():
                        self.assertEqual(f"ONLY-{name}" in body, name == selected)
                        self.assertEqual(f"NOT-{name}" in body, name != selected)

    def test_required_normal_readings_fail_clearly(self):
        for part, field in (("reading1", None), ("gospel", None), ("reading1", "CONTENT"), ("reading1", "CONTENT_2"), ("gospel", "CONTENT")):
            with self.subTest(part=part, field=field):
                data = fixture("weekday")["data"]
                if field:
                    data["mass_reading"][0][part][0][field] = ""
                else:
                    data["mass_reading"][0][part] = []
                with self.assertRaisesRegex(ValueError, "Mass reading.*missing"):
                    fetch.render_mass_reading(data)

    def test_missing_mass_metadata_and_special_content_fail(self):
        for data in (None, {}, {"mass_reading": []}, {"mass_reading": [None]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                fetch.render_mass_reading(data)
        for field, value in (("date_info", None), ("special_content", None), ("special_content", "<script>hidden()</script>")):
            data = fixture("special")["data"]
            data["mass_reading"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                fetch.render_mass_reading(data)

    def test_real_fixture_pagination_preserves_text_and_budget(self):
        for name in ("weekday", "sunday-multiple-masses", "multiple-readings", "long-short-gospel", "special"):
            with self.subTest(name=name):
                body = fetch.render_mass_reading(fixture(name)["data"]).body_html
                pages = fetch.paginate_html(body)
                self.assertEqual(text(" ".join(pages)), text(body))
                for index, page in enumerate(pages):
                    budget = fetch.FIRST_PAGE_TARGET_UNITS if index == 0 else fetch.PAGE_TARGET_UNITS
                    self.assertLessEqual(fetch.page_units(fetch.html_blocks(page)), budget)


class VietnameseModesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site_dir = Path(self.temp.name) / "site"
        self.site_dir.mkdir()
        (self.site_dir / "style.css").write_text((fetch.SITE_DIR / "style.css").read_text())
        self.site_patch = patch.object(fetch, "SITE_DIR", self.site_dir)
        self.site_patch.start()
        self.addCleanup(self.site_patch.stop)
        self.today = datetime(2026, 10, 4, tzinfo=fetch.VN_TZ)
        self.days = []
        for offset in (-1, 0, 1):
            date = self.today + timedelta(days=offset)
            prayers = [fetch.Prayer(title, slug, f"<h2>Mẫu {title}</h2><p>Nội dung nguyên bản của {title}, ngày {date.day}.</p>") for title, slug in fetch.PRAYERS]
            metadata = fetch.LiturgicalDay("Tên lễ giờ kinh", "", "test")
            self.days.append(fetch.DaySite(date, prayers, metadata, []))

    def prepared_days(self):
        responses = [fixture("weekday"), fixture("sunday-multiple-masses"), fixture("weekday")]
        session = Mock()
        session.post.return_value.json.side_effect = responses
        return fetch.add_mass_readings(session, self.days)

    def test_seven_source_prayers_are_unchanged_and_all_dates_added(self):
        prepared = self.prepared_days()
        self.assertEqual(len(fetch.PRAYERS), 7)
        self.assertEqual(len(fetch.VIETNAMESE_ENTRIES), 8)
        self.assertEqual(fetch.VIETNAMESE_ENTRIES[-1], fetch.MASS_READING)
        for old, new in zip(self.days, prepared):
            self.assertEqual(new.date, old.date)
            self.assertEqual(new.prayers[:7], old.prayers)
            self.assertTrue(all(a is b for a, b in zip(new.prayers, old.prayers)))
            self.assertEqual(len(new.prayers), 8)

    def test_all_three_modes_indexes_navigation_content_and_cleanup(self):
        days = self.prepared_days()
        stale = self.site_dir / "bai-doc-thanh-le-99.html"
        stale.write_text("stale")
        (self.site_dir / "breviary").mkdir()
        (self.site_dir / "breviary/bai-doc-thanh-le-99.html").write_text("stale")
        with patch.object(fetch, "write_debug_site"):
            fetch.write_site(days)
        self.assertFalse(stale.exists())
        self.assertFalse((self.site_dir / "breviary/bai-doc-thanh-le-99.html").exists())
        for day in days:
            mass = day.prayers[-1]
            date_name = fetch.date_dir_name(day.date)
            roots = [(self.site_dir / date_name, self.site_dir / "breviary" / date_name)]
            if day.date == self.today:
                roots.append((self.site_dir, self.site_dir / "breviary"))
            for kindle_root, breviary_root in roots:
                for index in (kindle_root / "index.html", kindle_root / "index-responsive.html", breviary_root / "index.html"):
                    soup = BeautifulSoup(index.read_text(), "lxml")
                    items = soup.select(".home-list li a")
                    self.assertEqual([item.get_text() for item in items], [title for title, _ in fetch.VIETNAMESE_ENTRIES])
                    for item in items:
                        self.assertTrue((index.parent / item["href"]).is_file(), item["href"])
                kindle_pages = [kindle_root / fetch.prayer_page_filename(mass.slug, i) for i in range(1, len(fetch.paginate_html(mass.body_html)) + 1)]
                fragments = []
                for page in kindle_pages:
                    original = BeautifulSoup(page.read_text(), "lxml")
                    breviary = BeautifulSoup((breviary_root / page.name).read_text(), "lxml")
                    original_nav = original.main.select_one("nav.page-nav")
                    breviary_nav = breviary.main.select_one("nav.page-nav")
                    self.assertEqual([a["href"] for a in original_nav.select("a.nav-icon")], [a["href"] for a in breviary_nav.select("a.nav-icon")])
                    original_nav.decompose()
                    breviary_nav.decompose()
                    self.assertEqual(original.main.decode_contents(), breviary.main.decode_contents())
                    for node in original.select("main > h1, main > .updated, main > .liturgical-day"):
                        node.decompose()
                    fragments.append(str(original.main))
                self.assertEqual(text(" ".join(fragments)), text(mass.body_html))
                responsive_path = kindle_root / fetch.responsive_prayer_filename(mass.slug)
                responsive = BeautifulSoup(responsive_path.read_text(), "lxml")
                self.assertIsNotNone(responsive.select_one(".responsive-nav"))
                self.assertIsNone(responsive.select_one(".paged-nav"))
                self.assertEqual(responsive.select_one(".feast-title").get_text(), mass.liturgical_day.title)
                for node in responsive.select("main > h1, main > .updated, main > .liturgical-day, main > nav"):
                    node.decompose()
                self.assertEqual(text(str(responsive.main)), text(mass.body_html))
                self.assertFalse(list(kindle_root.glob("bai-doc-thanh-le-*-responsive.html")))
                self.assertEqual([h.get_text() for h in responsive.select("h2")], [h.get_text() for h in BeautifulSoup(mass.body_html, "lxml").select("h2")])
                night = BeautifulSoup((kindle_root / "kinh-toi.html").read_text(), "lxml")
                self.assertIn("bai-doc-thanh-le.html", [a["href"] for a in night.select("nav a")])
                first_mass = BeautifulSoup(kindle_pages[0].read_text(), "lxml")
                self.assertIn("kinh-toi.html", [a["href"] for a in first_mass.select("nav a")])
                last_mass = BeautifulSoup(kindle_pages[-1].read_text(), "lxml")
                self.assertEqual(len({a["href"] for a in last_mass.select("nav a")}), 2)  # previous and index; no next entry

    def test_breviary_only_snapshot_includes_mass_pages(self):
        with patch.object(fetch, "write_debug_site"):
            fetch.write_site(self.prepared_days())
        kindle_pages = {path.name: path.read_text() for path in self.site_dir.glob("bai-doc-thanh-le*.html") if not path.name.endswith("-responsive.html")}
        with patch.object(fetch, "ROOT", Path(self.temp.name)):
            fetch.write_breviary_snapshot()
        self.assertIn("Bài đọc Thánh lễ", (self.site_dir / "breviary/index.html").read_text())
        for name, original in kindle_pages.items():
            source = BeautifulSoup(original, "lxml")
            snapshot = BeautifulSoup((self.site_dir / "breviary" / name).read_text(), "lxml")
            source.select_one("nav.page-nav").decompose()
            snapshot.select_one("nav.page-nav").decompose()
            self.assertEqual(source.main.decode_contents(), snapshot.main.decode_contents())

    def test_source_failure_never_calls_site_writer(self):
        old_page = self.site_dir / "index.html"
        old_page.write_text("last published content")
        session = Mock()
        session.post.return_value.json.return_value = {"success": False}
        with patch.object(fetch.requests, "Session", return_value=session), patch.object(fetch, "fetch_source", return_value="source"), patch.object(fetch, "save_debug_source"), patch.object(fetch, "build_prayers_from_api", side_effect=lambda _session, _source, _date: (self.days[0].prayers, self.days[0].liturgical_day, [])), patch.object(fetch, "write_site") as writer, patch.object(fetch, "write_error_page"), patch.object(fetch.sys, "argv", ["fetch.py"]), self.assertLogs(level="ERROR"):
            self.assertEqual(fetch.main(), 1)
        writer.assert_not_called()
        self.assertEqual(old_page.read_text(), "last published content")


if __name__ == "__main__":
    unittest.main()
