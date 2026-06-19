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
    if 'class="page-nav paged-nav"' in text:
        main = soup.find("main")
        if not main:
            raise SystemExit(f"Missing main in {path}")
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
    Path("site/kinh-chieu-17.html"),
]
for path in required_initial_pages:
    if 'class="illuminated-initial"' not in path.read_text(encoding="utf-8"):
        raise SystemExit(f"Missing illuminated initial in {path}")

if 'class="illuminated-initial"' in Path("site/kinh-sang-2.html").read_text(encoding="utf-8"):
    raise SystemExit("Unexpected repeated invitatory initial after repeated antiphon")

def require_initial_after_heading(pattern: str, heading_prefix: str, skip_classes=()):
    for path in Path("site").glob(pattern):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
        for heading in soup.find_all(["h2", "h3"]):
            if not heading.get_text(" ", strip=True).startswith(heading_prefix):
                continue
            node = heading.find_next_sibling()
            while node is not None:
                classes = set(node.get("class", [])) if hasattr(node, "get") else set()
                if classes & set(skip_classes):
                    node = node.find_next_sibling()
                    continue
                if getattr(node, "name", None) in {"p", "div"} and node.get_text(" ", strip=True):
                    if not node.select_one(".illuminated-initial"):
                        raise SystemExit(f"Missing illuminated initial after {heading_prefix} in {path}")
                    return
                node = node.find_next_sibling()
    raise SystemExit(f"Could not find heading: {heading_prefix} in {pattern}")

require_initial_after_heading("kinh-sang*.html", "Lời Chúa")

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
    if not payload.get("tedeum"):
        office_html = "\n".join(path.read_text(encoding="utf-8") for path in Path("site").glob("kinh-sach*.html"))
        if "Te Deum" in office_html or "Thánh thi “Lạy Thiên Chúa”" in office_html:
            raise SystemExit("Te Deum rendered even though source payload disables it")

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

payload = json.loads(Path("build/kinh-toi.json").read_text(encoding="utf-8"))
season = payload.get("date_info", {}).get("season")
html = "\n".join(path.read_text(encoding="utf-8") for path in Path("site").glob("kinh-toi*.html"))
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
