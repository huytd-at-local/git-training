#!/usr/bin/env sh
set -eu

PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m compileall scripts
test -f site/index.html
test -f site/style.css
test -f site/kindle.js

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
  grep -q 'kindle.js' "$file"
  grep -q 'Trang chủ' "$file"
  ! grep -q 'Update Required' "$file"
  ! grep -q 'Flash plugin' "$file"
  ! grep -q 'itunes.apple.com' "$file"
  ! grep -q 'play.google.com' "$file"
done

grep -q 'Ca vịnh' site/kinh-chieu.html
grep -q 'Ca vịnh' site/kinh-sang.html
grep -q 'Tv 94 (95)' site/kinh-sang.html
! grep -q 'Tv 94 (95)' site/kinh-sach.html
grep -q 'class="verse-line"' site/kinh-sang.html
grep -q 'class="verse-line"' site/kinh-toi.html
grep -q '.antiphon .pre' site/style.css
! grep -q 'class="reading-ref"' site/*.html
grep -q 'Xin Thiên Chúa toàn năng' site/kinh-sang.html
grep -q 'Xin Thiên Chúa toàn năng' site/kinh-chieu.html
! grep -Eq '<span class="pre">(Chủ sự|Cộng đoàn|ĐC|X|Đ)</span>' site/*.html
! grep -q 'Ha-lê-lui-a. Ha-lê-lui-a. Ha-lê-lui-a' site/kinh-toi.html

if test -f .cache/source.html && grep -Eq '<(em|i)([ >])' .cache/source.html; then
  grep -REq '(<em[ >]|class="[^"]*(italic|note)[^"]*")' site/*.html
fi

"$PYTHON_BIN" - <<'PY'
from pathlib import Path
for path in Path("site").glob("*.html"):
    text = path.read_text(encoding="utf-8")
    if 'class="verse-line"' in text and '</span><br/><span class="verse-line"' in text:
        raise SystemExit(f"Unexpected blank-line br between verse lines in {path}")
PY

if test -f build/kinh-toi.json; then
  "$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("build/kinh-toi.json").read_text(encoding="utf-8"))
season = payload.get("date_info", {}).get("season")
html = Path("site/kinh-toi.html").read_text(encoding="utf-8")
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
