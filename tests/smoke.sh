#!/usr/bin/env sh
set -eu

PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m compileall scripts
test -f site/index.html
test -f site/style.css

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
grep -q 'display: none;' site/style.css
grep -q 'illuminated-initial' site/style.css
grep -q 'class="illuminated-initial"' site/kinh-sang*.html
grep -q 'class="illuminated-initial"' site/kinh-chieu*.html
grep -q 'class="illuminated-initial"' site/kinh-sach*.html
grep -q 'p > .pre' site/style.css
grep -q 'p > .body' site/style.css
grep -q '.antiphon .pre' site/style.css
grep -q 'window.location.replace' site/index.html
grep -q 'getUTCHours' site/index.html
! grep -q 'getHours' site/index.html
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
import re
import unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
from scripts.fetch import block_units

for path in Path("site").rglob("*.html"):
    text = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(text, "lxml")
    if re.search(r"<sup>\d{3,}</sup>", text):
        raise SystemExit(f"Wide verse number missing class in {path}")
    if 'class="verse-line"' in text and '</span><br/><span class="verse-line"' in text:
        raise SystemExit(f"Unexpected blank-line br between verse lines in {path}")
    for initial in soup.select(".illuminated-initial"):
        value = initial.get_text("", strip=True)
        if not value or not unicodedata.category(value[0]).startswith("L"):
            raise SystemExit(f"Illuminated initial is not a letter in {path}: {value!r}")
    if 'class="page-nav paged-nav"' in text:
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

required_initial_pages = [
    Path("site/kinh-sang.html"),
    Path("site/kinh-sang-6.html"),
    Path("site/kinh-chieu-4.html"),
]
for path in required_initial_pages:
    if 'class="illuminated-initial"' not in path.read_text(encoding="utf-8"):
        raise SystemExit(f"Missing illuminated initial in {path}")

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
                        if "updated" in classes:
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

dated_indexes = sorted(Path("site").glob("20??-??-??/index.html"))
if len(dated_indexes) < 3:
    raise SystemExit("Expected yesterday/today/tomorrow dated indexes")

for path in Path("site").glob("*.html"):
    text = path.read_text(encoding="utf-8")
    if text.count("Chúa Nhật Tuần XI - Mùa Thường Niên") > 1:
        raise SystemExit(f"Repeated liturgical title in {path}")
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
