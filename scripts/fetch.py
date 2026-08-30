#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from zoneinfo import ZoneInfo


SOURCE_URL = "https://ktcgkpv.org/readings/prayer"
DIVINE_OFFICE_URL = "https://divineoffice.org/"
ENGLISH_BREVIARY_PASSCODE_ENV = "BREVIARY_EN_PASSCODE"
LEARNER_GEMINI_API_KEY_ENV = "BREVIARY_LEARNER_GEMINI_API_KEY"
LEARNER_GEMINI_MODEL_ENV = "BREVIARY_LEARNER_GEMINI_MODEL"
LEARNER_REFRESH_ENV = "BREVIARY_REFRESH_LEARNER"
LEARNER_GEMINI_DEFAULT_MODEL = "gemini-3.6-flash"
GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
LEARNER_PRONUNCIATION_PROFILE = "casual-british-ipa-v1"
LEARNER_PROFILE_CLASS = f"learner-profile-{LEARNER_PRONUNCIATION_PROFILE}"
TIMEOUT_SECONDS = 30
ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
CACHE_DIR = ROOT / ".cache"
BUILD_DIR = ROOT / "build"
SJCL_PATH = ROOT / "vendor" / "sjcl.js"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

USER_AGENT = (
    "kindle-gkpv-static/1.0 "
    "(GitHub Pages daily static mirror; contact: repository maintainer)"
)

GLORY_LINES = [
    "Vinh danh Chúa Cha và Chúa Con,",
    "cùng vinh danh Thánh Thần Thiên Chúa,",
    "tự muôn đời và chính hiện nay",
    "luôn mãi đến thiên thu vạn đại. A-men.",
]

API_ORDER = [
    "hymn",
    "psalm1",
    "canticle",
    "psalm2",
    "psalm3",
    "reading",
    "responsory",
    "readingleading",
    "reading1",
    "responsory1",
    "reading2",
    "responsory2",
    "tedeum",
    "gospel",
    "gospel_canticle",
    "intercession",
    "prayer",
]

PRAYERS = [
    ("Kinh Sách", "kinh-sach"),
    ("Kinh Sáng", "kinh-sang"),
    ("Kinh Trưa - Giờ Ba", "kinh-trua-gio-ba"),
    ("Kinh Trưa - Giờ Sáu", "kinh-trua-gio-sau"),
    ("Kinh Trưa - Giờ Chín", "kinh-trua-gio-chin"),
    ("Kinh Chiều", "kinh-chieu"),
    ("Kinh Tối", "kinh-toi"),
]

ENGLISH_PRAYERS = [
    ("Invitatory", "invitatory"),
    ("Office of Readings", "office-of-readings"),
    ("Morning Prayer", "morning-prayer"),
    ("Midmorning Prayer", "midmorning-prayer"),
    ("Midday Prayer", "midday-prayer"),
    ("Midafternoon Prayer", "midafternoon-prayer"),
    ("Evening Prayer", "evening-prayer"),
    ("Night Prayer", "night-prayer"),
]
ENGLISH_SESSION_KEY = "breviary-en-key-v1"
ENGLISH_LEARNER_SESSION_KEY = "breviary-en-learner-key-v1"
ENCRYPT_HELPER = ROOT / "scripts" / "encrypt_breviary.js"
DECRYPT_HELPER = ROOT / "scripts" / "decrypt_breviary.js"

BREVIARY_CSS = """
/* Monastic Breviary: ornament only; production pagination metrics stay unchanged. */
    .breviary-page {
      color: #0d0d0d;
      background: #fff;
    }

    .breviary-page h1,
    .breviary-page h2,
    .breviary-page h3,
    .breviary-page .liturgical-day,
    .breviary-page .page-nav {
      position: relative;
    }

    .breviary-page h1 {
      letter-spacing: 0.035em;
      text-transform: uppercase;
    }

    .breviary-first h1:before,
    .breviary-index h1:before {
      content: "✠";
      position: absolute;
      top: -0.82em;
      left: 0;
      width: 100%;
      color: #8b0000;
      font-size: 0.62em;
      line-height: 1;
      text-align: center;
    }

    .breviary-page h2:before,
    .breviary-page h3:before {
      content: "✠";
      position: absolute;
      right: 100%;
      margin-right: 0.22em;
      color: #8b0000;
      font-size: 0.68em;
      font-weight: normal;
      white-space: nowrap;
    }

    .breviary-page .pre,
    .breviary-page .label,
    .breviary-page .rubric,
    .breviary-page .illuminated-initial {
      color: #8b0000;
    }

    .breviary-page .medieval-rule {
      margin: 18px 0;
      color: #8b0000;
      font-size: 26px;
      line-height: 1;
      text-align: center;
      border-top: 1px solid #777;
    }

    .breviary-page .medieval-rule:before,
    .breviary-page .medieval-rule:after {
      content: "";
      display: inline-block;
      width: 30%;
    }

    .breviary-encrypted .passcode-gate {
      margin: 20px 0;
      padding: 22px 0;
      border-top: 1px solid #777;
      border-bottom: 1px solid #777;
    }

    .breviary-encrypted .passcode-ornament {
      color: #8b0000;
      text-align: center;
    }

    .breviary-encrypted label,
    .breviary-encrypted input,
    .breviary-encrypted button {
      display: block;
      width: 100%;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 40px;
    }

    .breviary-encrypted label {
      margin: 10px 0 8px 0;
      font-weight: bold;
    }

    .breviary-encrypted input,
    .breviary-encrypted button {
      min-height: 82px;
      margin: 0 0 14px 0;
      padding: 12px;
      color: #111;
      background: #fff;
      border: 2px solid #777;
      border-radius: 0;
    }

    .breviary-encrypted button {
      font-weight: bold;
    }

    .breviary-encrypted .passcode-status,
    .breviary-encrypted .decrypt-status {
      font-size: 34px;
    }

    .breviary-encrypted .passcode-error {
      font-weight: bold;
    }

    .breviary-page .liturgical-day:after,
    .breviary-page .page-nav:last-child:before {
      content: "✠";
      position: absolute;
      left: 46%;
      width: 8%;
      color: #8b0000;
      background: #fff;
      font-size: 0.72em;
      font-weight: normal;
      line-height: 1;
      text-align: center;
    }

    .breviary-page .liturgical-day:after {
      bottom: -0.52em;
    }

    .breviary-page .page-nav:last-child:before {
      top: -0.52em;
    }

    .breviary-page .page-nav a,
    .breviary-page .page-nav span {
      border-color: transparent;
    }

    .breviary-page .paged-nav .nav-icon {
      font-family: Georgia, "Times New Roman", serif;
      font-size: 46px;
      font-weight: normal;
    }

    .breviary-page .nav-index {
      font-variant: small-caps;
      letter-spacing: 0.035em;
    }

    /* English learner mode: CSS 2.1 table layout is reliable on Kindle's
       legacy WebKit and keeps the two columns in lockstep without scripts. */
    .learner-page main {
      max-width: none;
    }

    .learner-page .learner-note {
      margin: 0 0 18px;
      font-size: 26px;
      text-align: center;
    }

    .learner-page .learner-row {
      display: table;
      width: 100%;
      table-layout: fixed;
      margin: 0;
    }

    .learner-page .learner-english,
    .learner-page .learner-pronunciation {
      display: table-cell;
      box-sizing: border-box;
      vertical-align: top;
      font-size: 38px;
      line-height: 1.28;
      overflow-wrap: break-word;
      word-wrap: break-word;
    }

    .learner-page .learner-english {
      width: 56%;
      padding: 5px 10px 5px 0;
    }

    .learner-page .learner-pronunciation {
      width: 44%;
      padding: 5px 0 5px 10px;
      border-left: 1px solid #8b0000;
      color: #333;
    }

    .learner-page .learner-english p,
    .learner-page .learner-pronunciation p {
      margin: 0;
    }

    .learner-page .learner-glossary {
      margin-top: 22px;
      padding-top: 4px;
      border-top: 1px solid #777;
    }

    .learner-page .learner-glossary h2 {
      margin-top: 14px;
    }
"""
BREVIARY_CSS_VERSION = "9"

PAGE_TARGET_UNITS = 17.4
FIRST_PAGE_TARGET_UNITS = 14.4
# Kindle Paperwhite 3 renders roughly 48-50 Vietnamese characters per line in
# the production CSS. Keep a small safety margin instead of using the measured
# maximum directly.
CHARS_PER_READING_LINE = 48
VERSE_LINE_SPACING_UNITS = 0.10
# Fractional line-height costs derived from the production CSS at 40px with a
# 1.46 line-height: a normal paragraph has 16px of bottom margin, a paragraph
# created by the splitter has 10px, and a stanza has 20px.  Counting these is
# important for pages made from many short paragraphs: their text lines may fit
# while the accumulated margins still push the navigation below the viewport.
PARAGRAPH_SPACING_UNITS = 0.27
SPLIT_PARAGRAPH_SPACING_UNITS = 0.17
STANZA_SPACING_UNITS = 0.34
MIN_UNITS_BEFORE_HEADING_BREAK = 7
MIN_PAGE_UNITS = 12
SPLIT_PARAGRAPH_MIN_LINES = 4
SPLIT_PARAGRAPH_CHUNK_LINES = 2

# The learner mode is deliberately calibrated independently: a paired row has
# two narrow reading columns and its height is the taller column, not the sum.
# Paperwhite 3 captures on 2026-08-23 show that the first-page 15-unit budget
# keeps navigation visible, while a 26-unit later-page budget scrolls by about
# 3-8 rendered lines.  Budget in physical CSS height so a font-size change can
# no longer leave the paginator using stale line counts.  The later-page 875px
# content allowance reserves the same bottom navigation/chrome safety space as
# the established Vietnamese paginator.
LEARNER_FONT_SIZE_PX = 38.0
LEARNER_LINE_HEIGHT = 1.28
LEARNER_LINE_HEIGHT_PX = LEARNER_FONT_SIZE_PX * LEARNER_LINE_HEIGHT
LEARNER_PAGE_CONTENT_HEIGHT_PX = 875.0
LEARNER_FIRST_PAGE_CONTENT_HEIGHT_PX = 730.0
LEARNER_PAGE_TARGET_UNITS = round(
    LEARNER_PAGE_CONTENT_HEIGHT_PX / LEARNER_LINE_HEIGHT_PX, 1
)
LEARNER_FIRST_PAGE_TARGET_UNITS = round(
    LEARNER_FIRST_PAGE_CONTENT_HEIGHT_PX / LEARNER_LINE_HEIGHT_PX, 1
)
LEARNER_MIN_PAGE_UNITS = 14.0
LEARNER_LEFT_CHARS_PER_LINE = 25
LEARNER_RIGHT_CHARS_PER_LINE = 22
# Each table-cell has 5px top and bottom padding in the production CSS.
LEARNER_ROW_SPACING_UNITS = round(10.0 / LEARNER_LINE_HEIGHT_PX, 2)
LEARNER_MAX_FRAGMENT_CHARS = 92
# The Gemini free tier currently exposes a 20-requests-per-minute ceiling for
# this project.  A current-day learner build can contain about 925 distinct
# source lines.  These limits keep a cold-cache build to nine requests:
# seven quick pronunciation batches, one glossary batch, and one
# glossary-guide batch.  A larger 600-line batch exceeded the HTTP response
# timeout on the free tier, so the request count is intentionally traded for
# reliable, short individual responses.
LEARNER_GUIDANCE_BATCH_SIZE = 150
LEARNER_GLOSSARY_BATCH_SIZE = 12
LEARNER_MAX_RETRIES = 3
LEARNER_MAX_RETRY_SECONDS = 60
LEARNER_CACHE_FILE = CACHE_DIR / "breviary-learner-language-v3.json"

LEARNER_IPA_INSTRUCTIONS = (
    "Transcribe each English item in casual, contemporary British English using only the "
    "International Phonetic Alphabet (IPA). Model smooth natural connected speech in a "
    "standard Southern British/non-rhotic accent: use normal weak forms and reductions, join "
    "linked words where that makes the connection clear, and show a small amount of ordinary "
    "sound deletion. Preserve the supplied wording; do not paraphrase or omit content beyond "
    "natural connected-speech deletion. Use IPA primary and secondary stress marks. Return the "
    "transcription alone, without slashes, brackets, respelling, translations, explanations, "
    "labels, markdown, or capital letters. Example: 'The IPA is designed to represent those "
    "qualities of speech that are part of lexical' becomes 'ði ˌaɪ piː ˈeɪ ɪz dɪˈzaɪn tə "
    "ˌreprɪˈzent ðəʊz ˈkwɒlətiz əv spiːtʃ ðətə ˈpɑːtəv ˈleksɪkəl'."
)
LEARNER_IPA_EVIDENCE = frozenset("ɑɒæʌəɜɛɪʊɔŋθðʃʒɡɹɾʔˈˌː")
VIETNAMESE_PRONUNCIATION_MARKS = frozenset("\u0300\u0301\u0302\u0303\u0306\u0309\u031b\u0323")

LABEL_PATTERNS = [
    r"^ĐC\b",
    r"^Chủ sự\b",
    r"^Cộng đoàn\b",
    r"^Thánh thi\b",
    r"^Ca vịnh\b",
    r"^Tv\s*\d+",
    r"^Lời Chúa\b",
    r"^Xướng đáp\b",
    r"^Lời nguyện\b",
    r"^Kết thúc\b",
    r"^Tin Mừng\b",
    r"^Bài đọc\b",
]

BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "dd",
    "details",
    "dialog",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}

DROP_TAGS = {
    "audio",
    "button",
    "canvas",
    "footer",
    "form",
    "iframe",
    "input",
    "nav",
    "noscript",
    "script",
    "select",
    "style",
    "svg",
    "video",
}

DROP_ATTR_RE = re.compile(
    r"(menu|navbar|nav-|header|footer|audio|player|podcast|app|download|share|"
    r"social|advert|ads|modal|drawer|sidebar|toolbar|breadcrumb)",
    re.I,
)


@dataclass(frozen=True)
class Prayer:
    title: str
    slug: str
    body_html: str
    liturgical_day: LiturgicalDay | None = None


@dataclass(frozen=True)
class LiturgicalDay:
    title: str
    rank: str
    selector: str
    date_title: str = ""


@dataclass(frozen=True)
class DaySite:
    date: datetime
    prayers: list[Prayer]
    liturgical_day: LiturgicalDay | None
    debug_lines: list[str]


@dataclass(frozen=True)
class EnglishDaySite:
    date: datetime
    prayers: list[Prayer]
    liturgical_day: LiturgicalDay


@dataclass(frozen=True)
class DebugPattern:
    code: str
    title: str
    description: str
    body_html: str

    @property
    def filename(self) -> str:
        return f"{self.code.lower()}.html"


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format="%(levelname)s: %(message)s", level=level)


def normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("đ", "d").replace("Đ", "D")
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def fetch_source(session: requests.Session, url: str) -> str:
    logging.info("Fetching %s", url)
    response = session.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    if response.encoding is None:
        response.encoding = "utf-8"
    return response.text


def fetch_prayer_json(
    session: requests.Session,
    date: datetime,
    active_prayer: str,
    daytime_hour: str | None = None,
) -> dict:
    data = {
        "day": date.day,
        "month": date.month,
        "year": date.year,
        "seldate": date.strftime("%a %b %d %Y 00:00:00 GMT+0700 (Indochina Time)"),
        "active_prayer": active_prayer,
        "daytime_hour": daytime_hour or "",
        "feast_cd": "",
    }
    logging.info("Fetching AJAX prayer active_prayer=%s daytime_hour=%s", active_prayer, daytime_hour)
    response = session.post(
        SOURCE_URL,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": SOURCE_URL,
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise ValueError(f"AJAX prayer request failed: {payload.get('msg')}")
    return payload["data"]


def divineoffice_request(session: requests.Session, url: str) -> str:
    logging.info("Fetching Divine Office %s", url)
    response = session.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Referer": DIVINE_OFFICE_URL,
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def divineoffice_inline_tokens(node, inherited_class: str = "") -> list[str | None]:
    if isinstance(node, Comment):
        return []
    if isinstance(node, NavigableString):
        value = str(node).replace("\xa0", " ")
        if not value:
            return []
        escaped = html.escape(value, quote=False)
        if inherited_class:
            return [f'<span class="{inherited_class}">{escaped}</span>']
        return [escaped]
    if not isinstance(node, Tag):
        return []
    if node.name == "br":
        return [None]
    if node.name == "a":
        return []

    classes = set(node.get("class", []))
    child_class = inherited_class
    style = str(node.get("style", "")).lower().replace(" ", "")
    if "color:#ff0000" in style or "color:red" in style:
        child_class = "rubric"
    elif "note" in classes:
        child_class = "note"

    tokens: list[str | None] = []
    for child in node.children:
        tokens.extend(divineoffice_inline_tokens(child, child_class))

    if node.name in {"em", "i", "strong", "b"} and not child_class:
        tag_name = "strong" if node.name in {"strong", "b"} else "em"
        wrapped: list[str | None] = []
        for token in tokens:
            wrapped.append(None if token is None else f"<{tag_name}>{token}</{tag_name}>")
        return wrapped
    return tokens


def divineoffice_heading_level(value: str) -> int | None:
    key = normalize_key(value)
    if key in {
        "hymn",
        "psalmody",
        "reading",
        "readings",
        "responsory",
        "canticle of zechariah",
        "canticle of mary",
        "intercessions",
        "concluding prayer",
        "dismissal",
        "acclamation",
    }:
        return 2
    if key.startswith(("psalm ", "canticle ", "gospel canticle", "reading ")):
        return 3
    return None


def render_divineoffice_group(lines: list[str]) -> str:
    joined = " ".join(lines)
    soup = BeautifulSoup(f"<div>{joined}</div>", "lxml")
    wrapper = soup.find("div")
    plain = wrapper.get_text(" ", strip=True) if wrapper else ""
    if not plain:
        return ""
    heading_level = divineoffice_heading_level(plain) if wrapper and wrapper.select_one(".rubric") else None
    if heading_level:
        return f"<h{heading_level}>{html.escape(plain)}</h{heading_level}>"
    if len(lines) == 1 and lines[0].lstrip().startswith('<span class="rubric">'):
        return f'<p class="label">{lines[0]}</p>'
    if len(lines) == 1:
        return f"<p>{lines[0]}</p>"
    return '<div class="stanza">' + "".join(f"<div>{line}</div>" for line in lines) + "</div>"


def render_divineoffice_paragraph(node: Tag) -> list[str]:
    tokens = divineoffice_inline_tokens(node)
    raw_lines: list[str] = []
    current = ""
    for token in tokens:
        if token is None:
            raw_lines.append(current.strip())
            current = ""
        else:
            current += token
    raw_lines.append(current.strip())

    rendered: list[str] = []
    group: list[str] = []
    for line in raw_lines:
        if line:
            group.append(line)
            continue
        if group:
            block = render_divineoffice_group(group)
            if block:
                rendered.append(block)
            group = []
    if group:
        block = render_divineoffice_group(group)
        if block:
            rendered.append(block)
    return rendered


def is_divineoffice_content_paragraph(node: Tag) -> bool:
    if node.find_parent(["audio", "table", "style", "script"]):
        return False
    for parent in [node, *node.parents]:
        if not isinstance(parent, Tag):
            continue
        classes = " ".join(parent.get("class", []))
        if any(
            value in classes
            for value in ("powerpress_player", "table-container", "stc-content-filter", "no-print")
        ):
            return False
    return True


def parse_divineoffice_prayer(source: str, title: str, slug: str) -> Prayer:
    soup = BeautifulSoup(source, "lxml")
    intro = soup.select_one(".section-intro.is-prayer")
    entry = intro.find_next_sibling("div", class_="entry") if isinstance(intro, Tag) else None
    if not isinstance(entry, Tag):
        raise ValueError(f"Divine Office prayer content container missing for {title}")

    blocks: list[str] = []
    started = title == "Invitatory"
    title_key = normalize_key(title)
    for node in entry.find_all("p"):
        if not is_divineoffice_content_paragraph(node):
            continue
        text = node.get_text(" ", strip=True)
        key = normalize_key(text)
        if not started:
            if key.startswith(title_key):
                started = True
            continue
        if key.startswith("please help us bring the liturgy of the hours"):
            break
        blocks.extend(render_divineoffice_paragraph(node))

    body_html = "\n".join(block for block in blocks if block.strip())
    if not started or len(BeautifulSoup(body_html, "lxml").get_text(" ", strip=True)) < 100:
        raise ValueError(f"Divine Office prayer content missing or too short for {title}")
    return Prayer(title, slug, body_html)


def fetch_english_day(session: requests.Session, date: datetime) -> EnglishDaySite:
    date_query = date.strftime("%Y%m%d")
    index_source = divineoffice_request(session, f"{DIVINE_OFFICE_URL}?date={date_query}")
    index_soup = BeautifulSoup(index_source, "lxml")
    hrefs: dict[str, str] = {}
    expected_titles = [title for title, _ in ENGLISH_PRAYERS]
    for link in index_soup.select(".prayers-grid a.prayers-grid-item"):
        heading = link.find("h3")
        href = link.get("href")
        name = heading.get_text(" ", strip=True) if heading else ""
        if name in expected_titles and href:
            hrefs[name] = urljoin(DIVINE_OFFICE_URL, href)
    if set(hrefs) != set(expected_titles):
        raise ValueError(f"Divine Office prayer menu mismatch: {sorted(hrefs)}")

    prayers: list[Prayer] = []
    date_title = ""
    day_title = ""
    for title, slug in ENGLISH_PRAYERS:
        source = divineoffice_request(session, hrefs[title])
        source_soup = BeautifulSoup(source, "lxml")
        if not date_title:
            date_node = source_soup.select_one(".section-intro.is-prayer .mobile-prayer-date")
            heading_node = source_soup.select_one(".section-intro.is-prayer .intro-title")
            date_title = date_node.get_text(" ", strip=True) if date_node else date.strftime("%B %-d")
            heading = heading_node.get_text(" ", strip=True) if heading_node else ""
            prefix = f"{title} for "
            day_title = heading[len(prefix) :] if heading.startswith(prefix) else heading
        prayers.append(parse_divineoffice_prayer(source, title, slug))
    liturgical_day = LiturgicalDay(day_title or "Liturgy of the Hours", "", "Divine Office", date_title)
    return EnglishDaySite(date, prayers, liturgical_day)


def save_debug_source(source: str) -> None:
    for directory in (CACHE_DIR, BUILD_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "source.html"
        path.write_text(source, encoding="utf-8")
        logging.info("Saved raw source to %s", path.relative_to(ROOT))


def append_debug(lines: list[str]) -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    (BUILD_DIR / "debug.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def should_drop(tag: Tag) -> bool:
    if tag.attrs is None:
        return True
    if tag.name in DROP_TAGS:
        return True
    attrs = " ".join(
        str(value)
        for key, value in tag.attrs.items()
        if key in {"id", "class", "role", "aria-label"}
    )
    return bool(attrs and DROP_ATTR_RE.search(attrs))


def clean_soup(source: str) -> BeautifulSoup:
    soup = BeautifulSoup(source, "lxml")
    for tag in list(soup.find_all(True)):
        if should_drop(tag):
            tag.decompose()
    return soup


def fragment_soup(fragment: str | None) -> BeautifulSoup:
    return BeautifulSoup(f"<div>{fragment or ''}</div>", "lxml")


class LearnerLanguageError(RuntimeError):
    """Raised when the build-time language enrichment is unavailable or invalid."""


def github_actions_warning(title: str, message: str) -> None:
    """Expose an optional-stage failure without failing the publishable core."""
    if os.environ.get("GITHUB_ACTIONS", "").casefold() != "true":
        return
    escaped_title = title.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    escaped_message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::warning title={escaped_title}::{escaped_message}")


def learner_cache_key(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def validate_casual_british_ipa(source_text: str, guide: str) -> str:
    """Reject legacy respelling or decorated model output before it reaches Kindle."""
    value = re.sub(r"\s+", " ", guide).strip()
    decomposed = unicodedata.normalize("NFD", value)
    has_vietnamese_spelling = "đ" in value.casefold() or any(
        mark in VIETNAMESE_PRONUNCIATION_MARKS for mark in decomposed
    )
    if (
        not value
        or len(value) > 500
        or any("A" <= character <= "Z" for character in value)
        or any(character in value for character in "/[]")
        or has_vietnamese_spelling
        or not any(character in LEARNER_IPA_EVIDENCE for character in value)
    ):
        raise LearnerLanguageError(f"Casual British IPA response is invalid for {source_text!r}")
    return value


def load_learner_language_cache() -> dict[str, dict]:
    empty = {"pronunciations": {}, "glossaries": {}}
    if not LEARNER_CACHE_FILE.exists():
        return empty
    try:
        loaded = json.loads(LEARNER_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logging.warning("Ignoring invalid learner language cache: %s", error)
        return empty
    if not isinstance(loaded, dict):
        return empty
    return {
        "pronunciations": loaded.get("pronunciations", {}) if isinstance(loaded.get("pronunciations"), dict) else {},
        "glossaries": loaded.get("glossaries", {}) if isinstance(loaded.get("glossaries"), dict) else {},
    }


def gemini_response_text(response: dict) -> str:
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise LearnerLanguageError("Gemini response did not contain a candidate")
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise LearnerLanguageError("Gemini response did not contain text parts")
    value = "".join(
        item.get("text", "") for item in parts if isinstance(item, dict) and isinstance(item.get("text"), str)
    ).strip()
    if not value:
        raise LearnerLanguageError("Gemini response did not contain text output")
    return value


def gemini_retry_seconds(response: requests.Response) -> float:
    retry_after = response.headers.get("retry-after", "").strip()
    candidates: list[float] = []
    try:
        candidates.append(float(retry_after))
    except ValueError:
        pass
    match = re.search(r"retry in\s+(\d+(?:\.\d+)?)s", response.text, flags=re.IGNORECASE)
    if match:
        candidates.append(float(match.group(1)))
    if candidates:
        return max(1.0, min(max(candidates), LEARNER_MAX_RETRY_SECONDS))
    return 10.0


class LearnerLanguage:
    """Build-time British pronunciation and beginner glossary generator.

    Its cache stays under .cache so source text and model output never become a
    separate public, unencrypted website artifact.
    """

    def __init__(self, api_key: str, model: str | None = None) -> None:
        if not api_key:
            raise LearnerLanguageError(f"{LEARNER_GEMINI_API_KEY_ENV} is required")
        self.api_key = api_key
        self.model = model or os.environ.get(LEARNER_GEMINI_MODEL_ENV, LEARNER_GEMINI_DEFAULT_MODEL)
        self.cache = load_learner_language_cache()
        self.changed = False

    def save(self) -> None:
        if not self.changed:
            return
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        LEARNER_CACHE_FILE.write_text(
            json.dumps(self.cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def request_json(self, name: str, schema: dict, instructions: str, payload: dict) -> dict:
        request_body = {
            "systemInstruction": {"parts": [{"text": instructions}]},
            "contents": [{"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        for attempt in range(LEARNER_MAX_RETRIES):
            try:
                response = requests.post(
                    GEMINI_GENERATE_CONTENT_URL.format(model=self.model),
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": self.api_key,
                    },
                    json=request_body,
                    timeout=TIMEOUT_SECONDS * 3,
                )
            except requests.RequestException as error:
                if attempt + 1 == LEARNER_MAX_RETRIES:
                    raise LearnerLanguageError(f"Gemini {name} request failed: {error}") from error
                delay = min(2**attempt, LEARNER_MAX_RETRY_SECONDS)
                logging.warning("Gemini %s request failed; retrying in %ss", name, delay)
                time.sleep(delay)
                continue
            status_code = getattr(response, "status_code", None)
            if status_code in {429, 500, 502, 503, 504} and attempt + 1 < LEARNER_MAX_RETRIES:
                delay = gemini_retry_seconds(response)
                if status_code != 429:
                    delay = max(delay, min(10 * (2**attempt), LEARNER_MAX_RETRY_SECONDS))
                issue = "rate-limited" if status_code == 429 else f"temporarily unavailable ({status_code})"
                logging.warning(
                    "Gemini %s %s; retrying in %.1fs (%d/%d)",
                    issue,
                    name,
                    delay,
                    attempt + 1,
                    LEARNER_MAX_RETRIES,
                )
                time.sleep(delay)
                continue
            try:
                response.raise_for_status()
            except requests.HTTPError as error:
                detail = re.sub(r"\s+", " ", response.text).strip()[:600]
                raise LearnerLanguageError(
                    f"Gemini {name} request failed ({response.status_code}): {detail or error}"
                ) from error
            try:
                return json.loads(gemini_response_text(response.json()))
            except (ValueError, json.JSONDecodeError) as error:
                raise LearnerLanguageError(f"Invalid Gemini {name} response: {error}") from error
        raise LearnerLanguageError(f"Gemini {name} request exhausted retries")

    def pronunciations(self, texts: list[str]) -> dict[str, str]:
        unique = list(dict.fromkeys(text for text in texts if text.strip()))
        result: dict[str, str] = {}
        missing: list[str] = []
        for text in unique:
            cached = self.cache["pronunciations"].get(learner_cache_key(text))
            if isinstance(cached, str) and cached.strip():
                try:
                    result[text] = validate_casual_british_ipa(text, cached)
                    continue
                except LearnerLanguageError:
                    logging.warning("Ignoring invalid cached IPA for %r", text)
            missing.append(text)

        schema = {
            "type": "object",
            "required": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "guide"],
                        "properties": {
                            "id": {"type": "string"},
                            "guide": {"type": "string"},
                        },
                    },
                }
            },
        }
        for offset in range(0, len(missing), LEARNER_GUIDANCE_BATCH_SIZE):
            batch = missing[offset : offset + LEARNER_GUIDANCE_BATCH_SIZE]
            pending = [{"id": str(index), "text": text} for index, text in enumerate(batch)]
            for semantic_attempt in range(LEARNER_MAX_RETRIES):
                payload = self.request_json(
                    "casual_british_ipa", schema, LEARNER_IPA_INSTRUCTIONS, {"items": pending}
                )
                guides = payload.get("items")
                by_id = (
                    {
                        item.get("id"): item.get("guide")
                        for item in guides
                        if isinstance(item, dict)
                    }
                    if isinstance(guides, list)
                    else {}
                )
                unresolved: list[dict[str, str]] = []
                for item in pending:
                    guide = by_id.get(item["id"])
                    if not isinstance(guide, str):
                        unresolved.append(item)
                        continue
                    try:
                        validated = validate_casual_british_ipa(item["text"], guide)
                    except LearnerLanguageError:
                        unresolved.append(item)
                        continue
                    result[item["text"]] = validated
                    self.cache["pronunciations"][learner_cache_key(item["text"])] = validated
                    self.changed = True
                # Preserve every valid item before repairing only the incomplete
                # subset. A later model omission must not discard useful work.
                self.save()
                pending = unresolved
                if not pending:
                    break
                if semantic_attempt + 1 == LEARNER_MAX_RETRIES:
                    raise LearnerLanguageError(
                        "Casual British IPA response remained incomplete for "
                        + ", ".join(repr(item["text"]) for item in pending)
                    )
                delay = min(2**semantic_attempt, LEARNER_MAX_RETRY_SECONDS)
                logging.warning(
                    "Gemini omitted or invalidated %d IPA item(s); retrying only those items in %ss (%d/%d)",
                    len(pending),
                    delay,
                    semantic_attempt + 1,
                    LEARNER_MAX_RETRIES,
                )
                time.sleep(delay)
        return result

    def glossary(self, prayer_title: str, source_text: str) -> list[dict[str, str]]:
        return self.glossaries([("single", prayer_title, source_text)])["single"]

    def glossaries(self, prayers: list[tuple[str, str, str]]) -> dict[str, list[dict[str, str]]]:
        result: dict[str, list[dict[str, str]]] = {}
        missing: list[tuple[str, str, str, str]] = []
        for prayer_id, prayer_title, source_text in prayers:
            cache_key = learner_cache_key(f"{prayer_title}\n{source_text}")
            cached = self.cache["glossaries"].get(cache_key)
            if isinstance(cached, list) and all(isinstance(item, dict) for item in cached):
                result[prayer_id] = cached
            else:
                missing.append((prayer_id, prayer_title, source_text, cache_key))
        if not missing:
            return result
        schema = {
            "type": "object",
            "required": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "terms"],
                        "properties": {
                            "id": {"type": "string"},
                            "terms": {
                                "type": "array",
                                "minItems": 6,
                                "maxItems": 12,
                                "items": {
                                    "type": "object",
                                    "required": ["term", "definition"],
                                    "properties": {
                                        "term": {"type": "string"},
                                        "definition": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                }
            },
        }
        instructions = (
            "For each supplied prayer, select 6 to 12 English words or short phrases that could "
            "confuse a learner of English after about six months of study. Return exactly one "
            "item for each supplied id. Copy every selected term exactly from its own prayer. "
            "For each, write one very simple English definition, maximum 12 words. Do not "
            "translate, use markdown, or add terms that do not appear in that prayer."
        )
        for offset in range(0, len(missing), LEARNER_GLOSSARY_BATCH_SIZE):
            pending = missing[offset : offset + LEARNER_GLOSSARY_BATCH_SIZE]
            for semantic_attempt in range(LEARNER_MAX_RETRIES):
                payload = self.request_json(
                    "beginner_prayer_glossaries",
                    schema,
                    instructions,
                    {
                        "items": [
                            {"id": prayer_id, "prayer_title": title, "prayer_text": text}
                            for prayer_id, title, text, _ in pending
                        ]
                    },
                )
                groups = payload.get("items")
                by_id = (
                    {
                        group.get("id"): group.get("terms")
                        for group in groups
                        if isinstance(group, dict)
                    }
                    if isinstance(groups, list)
                    else {}
                )
                unresolved: list[tuple[str, str, str, str]] = []
                for prayer_id, title, source_text, cache_key in pending:
                    terms = by_id.get(prayer_id)
                    if not isinstance(terms, list):
                        unresolved.append((prayer_id, title, source_text, cache_key))
                        continue
                    try:
                        validated = self.validate_glossary_terms(terms, source_text)
                    except LearnerLanguageError:
                        unresolved.append((prayer_id, title, source_text, cache_key))
                        continue
                    result[prayer_id] = validated
                    self.cache["glossaries"][cache_key] = validated
                    self.changed = True
                # A partial structured response is repairable. Save valid groups
                # now, then ask Gemini only for the missing or invalid IDs.
                self.save()
                pending = unresolved
                if not pending:
                    break
                if semantic_attempt + 1 == LEARNER_MAX_RETRIES:
                    raise LearnerLanguageError(
                        "Glossary response remained incomplete for "
                        + ", ".join(prayer_id for prayer_id, _, _, _ in pending)
                    )
                delay = min(2**semantic_attempt, LEARNER_MAX_RETRY_SECONDS)
                logging.warning(
                    "Gemini omitted or invalidated %d glossary item(s); retrying only those items in %ss (%d/%d)",
                    len(pending),
                    delay,
                    semantic_attempt + 1,
                    LEARNER_MAX_RETRIES,
                )
                time.sleep(delay)
        return result

    @staticmethod
    def validate_glossary_terms(items: list, source_text: str) -> list[dict[str, str]]:
        validated: list[dict[str, str]] = []
        source_key = re.sub(r"\s+", " ", source_text).casefold()
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            term = item.get("term")
            definition = item.get("definition")
            if not isinstance(term, str) or not isinstance(definition, str):
                continue
            term = re.sub(r"\s+", " ", term).strip()
            definition = re.sub(r"\s+", " ", definition).strip()
            term_key = term.casefold()
            if (
                not term
                or not definition
                or len(definition.split()) > 12
                or term_key in seen
                or term_key not in source_key
            ):
                continue
            seen.add(term_key)
            validated.append({"term": term, "definition": definition})
        if len(validated) < 6:
            raise LearnerLanguageError("Glossary response did not provide six valid source terms")
        return validated


def set_inner_html(tag: Tag, fragment: str | None) -> None:
    tag.clear()
    soup = fragment_soup(fragment)
    wrapper = soup.find("div")
    if not wrapper:
        return
    for child in list(wrapper.contents):
        tag.append(child)


def resolve_payload_value(payload_root: dict, class_name: str):
    match = re.match(r"^(?P<root>[a-zA-Z_]+)\[(?P<key>[^\]]+)\](?:\[(?P<field>[^\]]+)\])?$", class_name)
    if not match:
        return None
    root_name = match.group("root")
    key = match.group("key")
    field = match.group("field")
    root_value = ci_get(payload_root, root_name)
    if isinstance(root_value, dict):
        value = ci_get(root_value, key)
    else:
        value = ci_get(payload_root, key)
    if field and isinstance(value, dict):
        value = ci_get(value, field)
    return value


def fill_payload_placeholders(container: Tag, prayer_data: dict, root_key: str) -> None:
    root = prayer_data.get(root_key)
    if not isinstance(root, dict):
        raise ValueError(f"Missing {root_key} data")
    payload_root = dict(root)
    if isinstance(prayer_data.get("first_invitatory"), dict):
        payload_root["first_invitatory"] = prayer_data["first_invitatory"]

    for tag in list(container.find_all(True)):
        classes = tag.get("class", [])
        if not isinstance(classes, list):
            continue
        for class_name in classes:
            value = resolve_payload_value(payload_root, class_name)
            if value is None:
                continue
            set_inner_html(tag, str(value))
            break


def remove_disabled_glory_blocks(container: Tag, root: dict) -> None:
    for glory in list(container.select(".glory")):
        previous = glory.find_previous_sibling()
        while isinstance(previous, Tag) and not previous.get_text(strip=True):
            previous = previous.find_previous_sibling()
        if not isinstance(previous, Tag):
            continue
        content_key = None
        for class_name in previous.get("class", []):
            match = re.match(r"^[a-zA-Z_]+\[(?P<key>[^\]]+)\]\[content\]$", class_name)
            if match:
                content_key = match.group("key")
                break
        section = ci_get(root, content_key, {}) if content_key else {}
        if isinstance(section, dict) and not ci_get(section, "glory", False):
            glory.decompose()


def normalize_season(value: object) -> str:
    season = str(value or "").strip().lower()
    return {
        "eas": "easter",
        "easter": "easter",
        "chr": "christmas",
        "christmas": "christmas",
    }.get(season, season)


def filter_seasonal_variants(container: Tag, season_value: object) -> None:
    season = normalize_season(season_value)
    for tag in list(container.select(".christmas, .easter")):
        classes = set(tag.get("class", []))
        if season not in {normalize_season(cls) for cls in classes}:
            tag.decompose()

    if season == "easter":
        for tag in list(container.select(".not-easter")):
            tag.decompose()
    else:
        for tag in list(container.select(".only-easter")):
            tag.decompose()


def unwrap_preserving_children(tag: Tag) -> None:
    tag.unwrap()


def sanitize_render_dom(container: Tag) -> None:
    for tag in list(container.select("script, style, ul.dropdown-menu, button, select, audio, video, iframe, canvas, svg")):
        tag.decompose()

    for tag in list(container.select(".content-selection")):
        unwrap_preserving_children(tag)

    for icon in list(container.select("i.fa")):
        icon.decompose()

    for tag in list(container.find_all(True)):
        if tag.name == "i":
            tag.name = "em"
        if tag.name == "b":
            tag.name = "strong"
        if tag.name == "h4":
            tag.name = "h2"

        classes = tag.get("class", [])
        if not isinstance(classes, list):
            classes = []
        style = str(tag.get("style", ""))
        if "font-style" in style and "italic" in style:
            classes.append("note")
        if any(cls in {"epitomize", "leading"} for cls in classes):
            classes.append("note")
        if classes:
            kept = []
            for cls in classes:
                if cls in {"note", "pre", "body", "antiphon", "glory", "division-header", "title", "indexing", "section", "right-indexing", "small-text"}:
                    kept.append(cls)
            if kept:
                tag["class"] = sorted(set(kept), key=kept.index)
            elif tag.has_attr("class"):
                del tag["class"]
        for attr in list(tag.attrs):
            if attr not in {"class", "href"}:
                del tag[attr]

    for tag in list(container.find_all(True)):
        if tag.name in {"p", "div", "h2", "h3", "span"} and not tag.get_text(strip=True) and not tag.find(["br", "sup"]):
            tag.decompose()


def post_process_render_dom(container: Tag) -> None:
    for sup in list(container.find_all("sup")):
        if re.fullmatch(r"\d+[A-Za-z]+", sup.get_text(strip=True)):
            sup.decompose()

    def is_psalm_or_canticle_indexing(text: str) -> bool:
        key = normalize_key(text)
        return key.startswith("tv ") or key.startswith("tc ")

    def meaningful_sibling(node: Tag | NavigableString | None, direction: str):
        while node is not None:
            if isinstance(node, NavigableString) and not str(node).strip():
                node = node.previous_sibling if direction == "previous" else node.next_sibling
                continue
            return node
        return None

    def is_plain_digit_span(node: Tag) -> bool:
        return (
            isinstance(node, Tag)
            and node.name == "span"
            and not node.get("class")
            and re.fullmatch(r"\d+", node.get_text("", strip=True) or "")
        )

    def is_chapter_verse_marker(node: Tag) -> bool:
        if not isinstance(node, Tag) or node.name != "span" or node.get("class"):
            return False
        sup = node.find("sup", recursive=False)
        if not isinstance(sup, Tag) or not re.fullmatch(r"\d+", sup.get_text("", strip=True) or ""):
            return False
        chapter = next((child for child in node.children if isinstance(child, Tag) and child is not sup), None)
        if not isinstance(chapter, Tag) or not is_plain_digit_span(chapter):
            return False
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        return bool(re.fullmatch(r"\d+ \d+", text))

    def remove_psalm_chapter_markers(paragraph: Tag) -> None:
        soup = BeautifulSoup("", "lxml")
        for span in list(paragraph.select(".verse-continuation")):
            if re.fullmatch(r"\d+", span.get_text("", strip=True) or ""):
                span.decompose()

        for marker in list(paragraph.find_all("span", recursive=False)):
            if not is_chapter_verse_marker(marker):
                continue
            sup = marker.find("sup", recursive=False)
            if not isinstance(sup, Tag):
                continue
            next_node = meaningful_sibling(marker.next_sibling, "next")
            verse = soup.new_tag("span")
            verse["class"] = ["verse-line"]
            verse.append(sup.extract())
            verse.append(NavigableString(" "))
            if isinstance(next_node, Tag) and next_node.name == "span":
                verse.append(next_node.extract())
            elif isinstance(next_node, NavigableString) and str(next_node).strip():
                verse.append(NavigableString(str(next_node).strip()))
                next_node.extract()
            marker.replace_with(verse)

        for span in list(paragraph.find_all("span", recursive=False)):
            if span.get("class") or not re.fullmatch(r"\d+", span.get_text("", strip=True) or ""):
                continue
            previous = meaningful_sibling(span.previous_sibling, "previous")
            next_node = meaningful_sibling(span.next_sibling, "next")
            previous_is_verse = isinstance(previous, Tag) and any(
                cls in previous.get("class", []) for cls in ("verse-line", "verse-continuation")
            )
            next_is_verse = isinstance(next_node, Tag) and any(
                cls in next_node.get("class", []) for cls in ("verse-line", "verse-continuation")
            )
            next_is_text_span = isinstance(next_node, Tag) and next_node.name == "span" and bool(next_node.get_text(" ", strip=True))
            if (previous_is_verse and next_is_verse) or next_is_verse or next_is_text_span:
                span.decompose()

    in_psalm_or_canticle = False
    for node in container.find_all(["h2", "h3", "p"], recursive=True):
        classes = set(node.get("class", []))
        text = node.get_text(" ", strip=True)
        if node.name in {"h2", "h3"}:
            in_psalm_or_canticle = False
            continue
        if "indexing" in classes:
            in_psalm_or_canticle = is_psalm_or_canticle_indexing(text)
            continue
        if in_psalm_or_canticle and node.name == "p":
            remove_psalm_chapter_markers(node)

    for pre in container.select(".pre"):
        text = pre.get_text("", strip=True)
        if text and not text.endswith(":"):
            pre.clear()
            pre.append(f"{text}:")
        next_sibling = pre.next_sibling
        if isinstance(next_sibling, Tag) and "body" in next_sibling.get("class", []):
            pre.insert_after(NavigableString(" "))

    for sup in container.find_all("sup"):
        text = sup.get_text(strip=True)
        if text.isdigit() and len(text) >= 3:
            classes = list(sup.get("class", []))
            if "wide-verse-number" not in classes:
                classes.append("wide-verse-number")
                sup["class"] = classes
        next_sibling = sup.next_sibling
        if isinstance(next_sibling, Tag) and next_sibling.name == "span":
            sup.insert_after(NavigableString(" "))
        elif isinstance(next_sibling, NavigableString) and str(next_sibling) and not str(next_sibling).startswith((" ", "\n")):
            next_sibling.replace_with(NavigableString(" " + str(next_sibling)))

    soup = BeautifulSoup("", "lxml")
    for sup in list(container.find_all("sup")):
        if sup.find_parent(class_="verse-line"):
            continue
        if not sup.get_text(strip=True).isdigit():
            continue
        next_node = sup.next_sibling
        while isinstance(next_node, NavigableString) and not str(next_node).strip():
            next_node = next_node.next_sibling
        if not isinstance(next_node, Tag) or next_node.name != "span":
            continue
        verse = soup.new_tag("span")
        verse["class"] = ["verse-line"]
        sup.insert_before(verse)
        verse.append(sup.extract())
        if isinstance(verse.next_sibling, NavigableString) and not str(verse.next_sibling).strip():
            verse.append(verse.next_sibling.extract())
        if verse.next_sibling is next_node:
            verse.append(next_node.extract())

    def remove_br_between_verse_blocks() -> None:
        for br in list(container.find_all("br")):
            previous = br.previous_sibling
            while isinstance(previous, NavigableString) and not str(previous).strip():
                previous = previous.previous_sibling
            next_node = br.next_sibling
            while isinstance(next_node, NavigableString) and not str(next_node).strip():
                next_node = next_node.next_sibling
            if (
                isinstance(previous, Tag)
                and isinstance(next_node, Tag)
                and any(cls in previous.get("class", []) for cls in ("verse-line", "verse-continuation"))
                and any(cls in next_node.get("class", []) for cls in ("verse-line", "verse-continuation"))
            ):
                br.decompose()

    remove_br_between_verse_blocks()

    for span in container.find_all("span"):
        if span.get("class") or span.find_parent(class_="verse-line"):
            continue
        parent = span.parent
        if not isinstance(parent, Tag) or parent.name != "p":
            continue
        text = span.get_text(" ", strip=True)
        if not text:
            continue
        has_numbered_sibling = any(
            isinstance(sibling, Tag) and "verse-line" in sibling.get("class", [])
            for sibling in parent.children
        )
        previous = parent.find_previous_sibling("p")
        previous_verse_related = isinstance(previous, Tag) and previous.select_one(
            ".verse-line, .verse-continuation"
        )
        if has_numbered_sibling or previous_verse_related:
            span["class"] = ["verse-continuation"]

    in_psalm_or_canticle = False
    for node in container.find_all(["h2", "h3", "p"], recursive=True):
        classes = set(node.get("class", []))
        text = node.get_text(" ", strip=True)
        if node.name in {"h2", "h3"}:
            in_psalm_or_canticle = False
            continue
        if "indexing" in classes:
            in_psalm_or_canticle = is_psalm_or_canticle_indexing(text)
            continue
        if in_psalm_or_canticle and node.name == "p":
            remove_psalm_chapter_markers(node)

    remove_br_between_verse_blocks()

def html_children(container: Tag) -> str:
    return "\n".join(str(child) for child in container.contents if not isinstance(child, Comment)).strip()


INITIAL_HEADING_KEYS = {
    "thanh thi",
    "thanh ca tin mung",
    "ca van kinh duc me",
    "loi chua",
    "loi cau",
    "loi nguyen",
    "thanh thi lay thien chua",
    "xuong dap",
}


def first_letter_range(text: str) -> tuple[int, int] | None:
    for index, character in enumerate(text):
        if not unicodedata.category(character).startswith("L"):
            continue
        end = index + 1
        while end < len(text) and unicodedata.category(text[end]).startswith("M"):
            end += 1
        return index, end
    return None


def add_initial_to_node(node: Tag) -> bool:
    if node.select_one(".illuminated-initial"):
        return False

    for descendant in node.descendants:
        if not isinstance(descendant, NavigableString):
            continue
        parent = descendant.parent
        if not isinstance(parent, Tag):
            continue
        if parent.name in {"sup", "script", "style"}:
            continue
        if parent.find_parent(["sup", "script", "style"]):
            continue
        text = str(descendant)
        letter_range = first_letter_range(text)
        if not letter_range:
            continue
        index, end = letter_range
        initial = text[index:end]
        soup = BeautifulSoup("", "lxml")
        initial_tag = soup.new_tag("span")
        initial_tag["class"] = ["illuminated-initial"]
        initial_tag.string = initial
        replacement: list[NavigableString | Tag] = []
        if index:
            replacement.append(NavigableString(text[:index]))
        replacement.append(initial_tag)
        if end < len(text):
            replacement.append(NavigableString(text[end:]))
        descendant.replace_with(*replacement)
        return True
    return False


def add_illuminated_initials(fragment: str) -> str:
    soup = fragment_soup(fragment)
    wrapper = soup.find("div")
    if not isinstance(wrapper, Tag):
        return fragment

    current_section = ""
    pending_after_heading = False
    pending_after_antiphon = False
    pending_after_reading_intro = False
    previous_was_content = False
    last_structural_key = ""

    def starts_with_heading_key(key: str) -> bool:
        return any(key == heading_key or key.startswith(heading_key + " ") for heading_key in INITIAL_HEADING_KEYS)

    def transform_role_line(node: Tag, section_key: str) -> tuple[Tag | None, bool]:
        if node.name != "p":
            return None, False
        pre = node.find(class_="pre", recursive=False)
        body = node.find(class_="body", recursive=False)
        if not isinstance(pre, Tag) or not isinstance(body, Tag):
            return None, False

        label_key = normalize_key(pre.get_text(" ", strip=True).rstrip(":"))
        prefix_response = False
        if section_key in {"giao dau", "ket thuc"}:
            if label_key == "chu su":
                prefix_response = False
            elif label_key == "cong doan":
                prefix_response = True
            else:
                return None, False
        elif section_key.startswith("xuong dap"):
            if label_key == "x":
                prefix_response = False
            elif label_key == "d":
                prefix_response = True
            else:
                return None, False
        else:
            return None, False

        pre.decompose()
        for child in list(node.contents):
            if child is body:
                break
            if isinstance(child, NavigableString) and not str(child).strip():
                child.extract()
        if prefix_response and not body.get_text("", strip=True).startswith("—"):
            body.insert(0, NavigableString("— "))
        return body, True

    def is_content_block(node: Tag) -> bool:
        if node.name not in {"p", "div"}:
            return False
        if node.name == "div" and node.find(["p", "h2", "h3", "div"], recursive=False):
            return False
        classes = set(node.get("class", []))
        if classes & {"antiphon", "label", "note", "indexing", "right-indexing", "section", "title"}:
            return False
        text = node.get_text(" ", strip=True)
        if not text:
            return False
        return bool(node.select_one(".verse-line, .verse-continuation") or node.name == "p")

    for node in wrapper.find_all(["h2", "h3", "p", "div"], recursive=True):
        if node.find_parent(["p", "h2", "h3"]):
            continue
        classes = set(node.get("class", []))
        text = node.get_text(" ", strip=True)
        key = normalize_key(text)

        if node.name in {"h2", "h3"}:
            current_section = key
            pending_after_heading = starts_with_heading_key(key)
            pending_after_antiphon = False
            pending_after_reading_intro = False
            previous_was_content = False
            last_structural_key = key
            continue

        if "antiphon" in classes:
            pending_after_antiphon = not previous_was_content or last_structural_key.startswith("tv 94")
            pending_after_heading = False
            pending_after_reading_intro = False
            previous_was_content = False
            last_structural_key = ""
            continue

        if "note" in classes and key.startswith("trich "):
            pending_after_reading_intro = True
            pending_after_heading = False
            pending_after_antiphon = False
            previous_was_content = False
            last_structural_key = key
            continue

        transformed_body, role_transformed = transform_role_line(node, current_section)
        if role_transformed:
            if current_section.startswith("xuong dap") and not previous_was_content and isinstance(transformed_body, Tag):
                add_initial_to_node(transformed_body)
            if current_section in {"giao dau", "ket thuc"} and isinstance(transformed_body, Tag) and not transformed_body.get_text("", strip=True).startswith("—"):
                body = transformed_body
                add_initial_to_node(body)
            previous_was_content = True
            last_structural_key = ""
            continue

        if pending_after_heading or pending_after_antiphon or pending_after_reading_intro:
            if is_content_block(node):
                add_initial_to_node(node)
                pending_after_heading = False
                pending_after_antiphon = False
                pending_after_reading_intro = False
                previous_was_content = True
                last_structural_key = ""
            continue

        if is_content_block(node):
            previous_was_content = True
            last_structural_key = ""
            continue

        if classes & {"indexing", "right-indexing", "section", "title"}:
            last_structural_key = key

    return html_children(wrapper)


def render_intro_html(source: str, prayer_data: dict, root_key: str) -> str:
    soup = BeautifulSoup(source, "lxml")
    wrapper = BeautifulSoup("<div></div>", "lxml").div
    heading = soup.new_tag("h2")
    heading.string = "Giáo đầu"
    wrapper.append(heading)

    if root_key in {"office", "morning"} and isinstance(prayer_data.get("first_invitatory"), dict):
        intro = soup.find(id="firstInvitatory")
        if not isinstance(intro, Tag):
            raise ValueError("Could not find #firstInvitatory in source HTML")
        intro = BeautifulSoup(str(intro), "lxml").find(id="firstInvitatory")
        if not isinstance(intro, Tag):
            raise ValueError("Could not clone #firstInvitatory")
        intro.attrs = {}
        for tag in list(intro.select("#inviPsalm, .poem.hidden")):
            tag.decompose()
        for poem in list(intro.select(".poem")):
            if root_key == "office" or poem.get("id") != "psalm94":
                poem.decompose()
        psalm94 = intro.find(id="psalm94")
        if root_key == "morning" and isinstance(psalm94, Tag) and not psalm94.select_one(".indexing"):
            heading_soup = BeautifulSoup('<p class="indexing">Tv 94 (95)</p>', "lxml")
            heading = heading_soup.find("p")
            if isinstance(heading, Tag):
                psalm94.insert(0, heading)
        fill_payload_placeholders(intro, prayer_data, root_key)
        sanitize_render_dom(intro)
        wrapper.append(intro)
    else:
        intro = soup.find(id="commonInvitatory")
        if not isinstance(intro, Tag):
            raise ValueError("Could not find #commonInvitatory in source HTML")
        intro = BeautifulSoup(str(intro), "lxml").find(id="commonInvitatory")
        if not isinstance(intro, Tag):
            raise ValueError("Could not clone #commonInvitatory")
        intro.attrs = {}
        sanitize_render_dom(intro)
        wrapper.append(intro)

    post_process_render_dom(wrapper)
    return html_children(wrapper)


def render_lay_ending_html(source: str) -> str:
    soup = BeautifulSoup(source, "lxml")
    ending = soup.find(id="ending2")
    if not isinstance(ending, Tag):
        raise ValueError("Could not find #ending2 in source HTML")
    wrapper = BeautifulSoup("<div></div>", "lxml").div
    heading = soup.new_tag("h2")
    heading["class"] = ["division-header"]
    heading.string = "Kết thúc"
    wrapper.append(heading)
    ending = BeautifulSoup(str(ending), "lxml").find(id="ending2")
    if not isinstance(ending, Tag):
        raise ValueError("Could not clone #ending2")
    ending.attrs = {}
    for tag in list(ending.select(".ending-opt")):
        tag.decompose()
    sanitize_render_dom(ending)
    wrapper.append(ending)
    post_process_render_dom(wrapper)
    return html_children(wrapper)


def render_dom_prayer(title: str, slug: str, source: str, payload: dict, root_key: str, tab_id: str) -> Prayer:
    prayer_items = payload.get("prayer")
    if isinstance(prayer_items, list):
        if not prayer_items:
            raise ValueError(f"No prayer data returned for {title}")
        prayer_data = prayer_items[0]
    elif isinstance(prayer_items, dict):
        prayer_data = prayer_items
    else:
        raise ValueError(f"Unexpected prayer data for {title}: {type(prayer_items).__name__}")

    soup = BeautifulSoup(source, "lxml")
    tab = soup.find(id=tab_id)
    if not isinstance(tab, Tag):
        raise ValueError(f"Could not find #{tab_id} in source HTML")
    normal = tab.select_one(".normal-content")
    if not isinstance(normal, Tag):
        raise ValueError(f"Could not find #{tab_id} .normal-content in source HTML")

    fill_payload_placeholders(normal, prayer_data, root_key)
    filter_seasonal_variants(normal, payload.get("date_info", {}).get("season"))
    root = prayer_data.get(root_key, {})
    if isinstance(root, dict):
        remove_disabled_glory_blocks(normal, root)
    if isinstance(root, dict) and ci_get(root, "feast_hide"):
        for tag in list(normal.select(".feast-hide")):
            tag.decompose()
    if root_key == "office" and not prayer_data.get("tedeum"):
        for heading in list(normal.find_all(["h2", "h3", "h4"])):
            if "te deum" not in normalize_key(heading.get_text(" ", strip=True)):
                continue
            division = heading.find_parent(class_="division")
            if isinstance(division, Tag):
                division.decompose()
            else:
                heading.decompose()
    sanitize_render_dom(normal)
    post_process_render_dom(normal)
    body_parts = [render_intro_html(source, prayer_data, root_key), html_children(normal)]
    if root_key in {"morning", "evening"}:
        body_parts.append(render_lay_ending_html(source))
    body = "\n".join(part for part in body_parts if part)
    return Prayer(title, slug, add_illuminated_initials(body))


def clean_liturgical_title(value: str) -> str:
    value = re.sub(r"\s*<br\s*/?>\s*", " - ", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip()


def extract_liturgical_day(payloads: list[dict]) -> LiturgicalDay | None:
    for payload in payloads:
        info = payload.get("date_info")
        if not isinstance(info, dict):
            continue
        main_title = clean_liturgical_title(str(info.get("main_title") or ""))
        sub_title = clean_liturgical_title(str(info.get("sub_title") or ""))
        daily_title = clean_liturgical_title(str(info.get("daily_title") or ""))
        title = sub_title or main_title or daily_title
        date_title = main_title if sub_title and main_title != sub_title else daily_title
        rank = str(info.get("rank") or info.get("type") or "").strip()
        if title or rank:
            selector = "payload.date_info.sub_title/main_title/rank" if sub_title else "payload.date_info.main_title/rank"
            return LiturgicalDay(title=title, rank=rank, selector=selector, date_title=date_title)
        feasts = payload.get("feasts")
        if isinstance(feasts, list) and feasts:
            title = clean_liturgical_title(str(feasts[0].get("text") or ""))
            if title:
                return LiturgicalDay(title=title, rank=rank, selector="payload.feasts[0].text")
    return None


class LineCollector:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.current = ""

    def push_text(self, text: str) -> None:
        text = text.replace("\xa0", " ").replace("\r", "")
        parts = text.split("\n")
        for index, part in enumerate(parts):
            collapsed = re.sub(r"[ \t\f\v]+", " ", part)
            if collapsed:
                if self.current and not self.current.endswith((" ", "(", "“", "‘")):
                    self.current += " "
                self.current += collapsed.strip()
            if index < len(parts) - 1:
                self.break_line()

    def break_line(self) -> None:
        line = self.current.strip()
        if line:
            self.lines.append(line)
        self.current = ""

    def blank_line(self) -> None:
        self.break_line()
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def finish(self) -> list[str]:
        self.break_line()
        return trim_blank_lines(self.lines)


def collect_lines(node: Tag | BeautifulSoup) -> list[str]:
    collector = LineCollector()

    def walk(child: Tag | NavigableString) -> None:
        if isinstance(child, Comment):
            return
        if isinstance(child, NavigableString):
            collector.push_text(str(child))
            return
        if not isinstance(child, Tag):
            return
        if child.name == "br":
            collector.break_line()
            return
        if child.name == "hr":
            collector.blank_line()
            return

        is_block = child.name in BLOCK_TAGS
        if is_block:
            collector.break_line()

        for inner in child.children:
            walk(inner)

        if child.name in {"h1", "h2", "h3", "h4", "p", "li", "div", "section", "article", "tr"}:
            collector.break_line()
        if child.name in {"h1", "h2", "h3", "h4", "section", "article", "blockquote", "ul", "ol"}:
            collector.blank_line()

    walk(node)
    return collector.finish()


def html_fragment_lines(fragment: str | None) -> list[str]:
    if not fragment:
        return []
    soup = BeautifulSoup(f"<div>{fragment}</div>", "lxml")
    return collect_lines(soup)


def add_html(lines: list[str], label: str | None, fragment: str | None) -> None:
    fragment_lines = html_fragment_lines(fragment)
    if not fragment_lines:
        return
    if label:
        lines.extend(["", label])
    lines.extend(fragment_lines)


def ci_get(data: dict, key: str, default=None):
    for item_key, value in data.items():
        if item_key.lower() == key.lower():
            return value
    return default


def render_antiphon(lines: list[str], data: dict, key: str) -> None:
    add_html(lines, "ĐC", ci_get(data, key))


def render_psalm(lines: list[str], root: dict, key: str) -> None:
    psalm = ci_get(root, key)
    if not isinstance(psalm, dict):
        return

    key_l = key.lower()
    number = re.sub(r"\D+", "", key)
    antiphon_key = f"antiphon{number}" if number else "antiphon"
    if key_l == "canticle" and ci_get(root, "antiphon2"):
        antiphon_key = "antiphon2"
    if key_l == "psalm2" and ci_get(root, "canticle") and ci_get(root, "antiphon3"):
        antiphon_key = "antiphon3"
    render_antiphon(lines, root, antiphon_key)

    heading_parts = [
        ci_get(psalm, "INDEXING"),
        ci_get(psalm, "TITLE"),
        ci_get(psalm, "SECTION"),
    ]
    heading = " - ".join(str(part) for part in heading_parts if part)
    if heading:
        lines.extend(["", heading])
    add_html(lines, None, ci_get(psalm, "EPITOMIZE"))
    add_html(lines, None, ci_get(psalm, "CONTENT"))
    if ci_get(psalm, "glory", key_l != "canticle"):
        lines.extend(GLORY_LINES)
    render_antiphon(lines, root, antiphon_key)


def render_reading_block(lines: list[str], label: str, data: dict) -> None:
    lines.extend(["", label])
    heading_parts = [
        ci_get(data, "INDEXING"),
        ci_get(data, "TITLE"),
        ci_get(data, "SECTION"),
    ]
    heading = " - ".join(str(part) for part in heading_parts if part)
    if heading:
        lines.append(heading)
    add_html(lines, None, ci_get(data, "EPITOMIZE"))
    add_html(lines, None, ci_get(data, "LEAD"))
    add_html(lines, None, ci_get(data, "CONTENT"))


def render_structured_value(lines: list[str], root: dict, key: str, value) -> None:
    key_l = key.lower()
    labels = {
        "hymn": "Thánh thi",
        "canticle": "Thánh ca",
        "reading": "Lời Chúa",
        "responsory": "Xướng đáp",
        "readingleading": "Dẫn vào bài đọc",
        "reading1": "Bài đọc 1",
        "responsory1": "Xướng đáp 1",
        "reading2": "Bài đọc 2",
        "responsory2": "Xướng đáp 2",
        "tedeum": "Thánh thi Lạy Thiên Chúa",
        "gospel": "Tin Mừng",
        "gospel_canticle": "Thánh ca Tin Mừng",
        "intercession": "Lời cầu",
        "prayer": "Lời nguyện",
    }

    if key_l.startswith("psalm"):
        render_psalm(lines, root, key)
        return
    if isinstance(value, str):
        add_html(lines, labels.get(key_l, key), value)
        return
    if isinstance(value, dict):
        if key_l in {"reading", "reading1", "reading2", "gospel"}:
            render_reading_block(lines, labels.get(key_l, key), value)
            return
        if key_l in {"canticle", "gospel_canticle"}:
            render_psalm(lines, root, key)
            if ci_get(value, "CONTENT") and not any(
                ci_get(root, antiphon_key) for antiphon_key in ("antiphon", "antiphon2", "antiphon4")
            ):
                render_reading_block(lines, labels.get(key_l, key), value)
            return
        render_data_dict(lines, value)


def ordered_items(data: dict):
    used: set[str] = set()
    lower_map = {key.lower(): key for key in data}
    for wanted in API_ORDER:
        if wanted in lower_map:
            key = lower_map[wanted]
            used.add(key)
            yield key, data[key]
    for key, value in data.items():
        if key not in used and not key.lower().startswith("antiphon") and key.lower() not in {
            "number",
            "indexing",
            "section",
            "title",
            "epitomize",
            "content",
            "lead",
            "glory",
            "feast_hide",
        }:
            yield key, value


def render_data_dict(lines: list[str], data: dict) -> None:
    for key, value in ordered_items(data):
        render_structured_value(lines, data, key, value)


def render_api_prayer(title: str, slug: str, payload: dict, root_key: str) -> Prayer:
    prayer_items = payload.get("prayer")
    if isinstance(prayer_items, list):
        if not prayer_items:
            raise ValueError(f"No prayer data returned for {title}")
        prayer_data = prayer_items[0]
    elif isinstance(prayer_items, dict):
        prayer_data = prayer_items
    else:
        raise ValueError(f"Unexpected prayer data for {title}: {type(prayer_items).__name__}")

    root = prayer_data.get(root_key)
    if not isinstance(root, dict):
        raise ValueError(f"Missing {root_key} data for {title}")

    lines: list[str] = []
    first_invitatory = prayer_data.get("first_invitatory")
    if isinstance(first_invitatory, dict):
        lines.extend(
            [
                "",
                "Giáo đầu",
                "Chủ sự",
                "Lạy Chúa Trời, xin mở miệng con,",
                "Cộng đoàn",
                "cho con cất tiếng ngợi khen Ngài.",
            ]
        )
        add_html(lines, "ĐC", first_invitatory.get("antiphon"))

    render_data_dict(lines, root)
    body = render_line_groups(trim_blank_lines(lines))
    return Prayer(title, slug, add_illuminated_initials(body))


def selected_night_hymn_class(payload: dict, selection_day: int | None = None) -> str:
    night_payload = payload.get("prayer", {}).get("night", {})
    explicit = ""
    if isinstance(night_payload, dict):
        explicit = str(
            night_payload.get("hymn_cd")
            or night_payload.get("hymn_code")
            or night_payload.get("hymn")
            or ""
        ).strip()
    explicit = explicit.lower().removeprefix(".")
    if explicit in {"1", "hymn1"}:
        return "hymn1"
    if explicit in {"2", "hymn2"}:
        return "hymn2"
    if explicit == "easter":
        return "easter"

    date_info = payload.get("date_info", {})
    season = date_info.get("season") if isinstance(date_info, dict) else None
    if season == "easter":
        return "easter"

    if selection_day is None:
        today = date_info.get("today", {}) if isinstance(date_info, dict) else {}
        try:
            selection_day = int(today.get("date") or 0) if isinstance(today, dict) else 0
        except (TypeError, ValueError):
            selection_day = 0
    if selection_day:
        return f"hymn{(selection_day % 2) + 1}"
    return "hymn1"


def filter_night_dom(night: Tag, payload: dict, selection_day: int | None = None) -> Tag:
    night_payload = payload.get("prayer", {}).get("night", {})
    psalm_code = str(night_payload.get("code") or "")
    prayer_code = str(night_payload.get("prayer_cd") or "")
    reading_code = str(night_payload.get("reading_cd") or "")
    season = normalize_season(payload.get("date_info", {}).get("season"))
    today = payload.get("date_info", {}).get("today", {})
    try:
        day_number = int(today.get("date") or 0) if isinstance(today, dict) else 0
    except (TypeError, ValueError):
        day_number = 0

    for tag in list(night.select("script, style, .dropdown-menu, .content-selection, .hymnSelection, .exclamationSelection")):
        tag.decompose()

    for tag in list(night.select(".day-option")):
        classes = set(tag.get("class", []))
        parent_division = tag.find_parent(class_="division")
        parent_classes = set(parent_division.get("class", [])) if isinstance(parent_division, Tag) else set()
        if "prayer" in parent_classes:
            keep = prayer_code and prayer_code in classes
        elif "reading" in parent_classes:
            keep = reading_code and reading_code in classes
        else:
            keep = psalm_code and psalm_code in classes
        if not keep:
            tag.decompose()

    for tag in list(night.select(".christmas, .easter")):
        classes = set(tag.get("class", []))
        if not season or season not in classes:
            tag.decompose()

    if season == "easter":
        for tag in list(night.select(".not-easter")):
            tag.decompose()
    else:
        for tag in list(night.select(".only-easter")):
            tag.decompose()

    if season in {"christmas", "easter"}:
        for tag in list(night.select(".exclamation.division > .body.normal")):
            tag.decompose()
    else:
        exclamation_count = len(night.select(".exclamation.division > .body.normal"))
        selected_exclamation = f"exclamation{(day_number % exclamation_count) + 1}" if exclamation_count else "exclamation1"
        for tag in list(night.select(".exclamation.division > .body.normal")):
            classes = set(tag.get("class", []))
            if selected_exclamation not in classes:
                tag.decompose()

    selected_hymn = selected_night_hymn_class(payload, selection_day)
    for tag in list(night.select(".hymn.division > .body")):
        classes = set(tag.get("class", []))
        if selected_hymn not in classes:
            tag.decompose()

    return night


def render_night_prayer(title: str, slug: str, source: str, payload: dict, date: datetime) -> Prayer:
    soup = BeautifulSoup(source, "lxml")
    night = soup.find(id="nightPrayer")
    if not isinstance(night, Tag):
        raise ValueError("Could not find #nightPrayer in source HTML")
    night = filter_night_dom(night, payload, date.day)
    sanitize_render_dom(night)
    post_process_render_dom(night)
    intro = render_intro_html(source, {"night": {}}, "night")
    body = intro + "\n" + html_children(night)
    return Prayer(title, slug, add_illuminated_initials(body))


def write_payload_debug(name: str, payload: dict) -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    path = BUILD_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_prayers_from_api(session: requests.Session, source: str, date: datetime) -> tuple[list[Prayer], LiturgicalDay | None, list[str]]:
    jobs = [
        ("Kinh Sách", "kinh-sach", "officeReading", None, "office", "officeReading"),
        ("Kinh Sáng", "kinh-sang", "morningPrayer", None, "morning", "morningPrayer"),
        ("Kinh Trưa - Giờ Ba", "kinh-trua-gio-ba", "daytimePrayer", "h3", "daytime", "daytimePrayer"),
        ("Kinh Trưa - Giờ Sáu", "kinh-trua-gio-sau", "daytimePrayer", "h6", "daytime", "daytimePrayer"),
        ("Kinh Trưa - Giờ Chín", "kinh-trua-gio-chin", "daytimePrayer", "h9", "daytime", "daytimePrayer"),
        ("Kinh Chiều", "kinh-chieu", "eveningPrayer", None, "evening", "eveningPrayer"),
    ]
    prayers: list[Prayer] = []
    payloads: list[dict] = []
    for title, slug, active_prayer, hour, root_key, tab_id in jobs:
        payload = fetch_prayer_json(session, date, active_prayer, hour)
        payloads.append(payload)
        write_payload_debug(slug, payload)
        prayer = render_dom_prayer(title, slug, source, payload, root_key, tab_id)
        prayers.append(Prayer(prayer.title, prayer.slug, prayer.body_html, extract_liturgical_day([payload])))

    night_payload = fetch_prayer_json(session, date, "nightPrayer")
    payloads.append(night_payload)
    write_payload_debug("kinh-toi", night_payload)
    prayer = render_night_prayer("Kinh Tối", "kinh-toi", source, night_payload, date)
    prayers.append(Prayer(prayer.title, prayer.slug, prayer.body_html, extract_liturgical_day([night_payload])))
    liturgical_day = extract_liturgical_day(payloads)
    debug_lines = [
        f"URL fetched: {SOURCE_URL}",
        f"Fetch time Asia/Ho_Chi_Minh: {date.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "Main content selector used: #prayerContent tab .normal-content plus #nightPrayer",
    ]
    if liturgical_day:
        debug_lines.append(f"Liturgical-day selector used: {liturgical_day.selector}")
        debug_lines.append(f"Liturgical-day title: {liturgical_day.title}")
        debug_lines.append(f"Liturgical-day rank: {liturgical_day.rank}")
    else:
        warning = "WARNING: liturgical day not found; tried payload.date_info.main_title/rank and payload.feasts[0].text"
        logging.warning(warning)
        debug_lines.append(warning)
    for prayer in prayers:
        count = len(BeautifulSoup(prayer.body_html, "lxml").find_all(["h2", "h3", "p", "div"]))
        debug_lines.append(f"Rendered block count {prayer.slug}: {count}")
    return prayers, liturgical_day, debug_lines


def trim_blank_lines(lines: Iterable[str]) -> list[str]:
    trimmed: list[str] = []
    previous_blank = True
    for raw in lines:
        line = raw.strip()
        if not line:
            if not previous_blank:
                trimmed.append("")
            previous_blank = True
            continue
        trimmed.append(line)
        previous_blank = False
    while trimmed and trimmed[-1] == "":
        trimmed.pop()
    return trimmed


def content_root(soup: BeautifulSoup) -> Tag:
    for selector in (
        "main",
        "article",
        "#content",
        ".content",
        ".reading",
        ".readings",
        ".prayer",
        ".prayers",
    ):
        found = soup.select_one(selector)
        if found and found.get_text(strip=True):
            logging.info("Using content selector %s", selector)
            return found
    logging.warning("No clear content selector found; falling back to <body>")
    body = soup.body
    if body is None:
        raise ValueError("HTML has no body")
    return body


def candidates_for(title: str) -> list[str]:
    key = normalize_key(title)
    compact = key.replace(" ", "")
    words = key.split()
    return [title, key, compact, "-".join(words), "_".join(words)]


def find_explicit_sections(root: Tag) -> list[Prayer] | None:
    found: list[Prayer] = []
    used: set[int] = set()

    for title, slug in PRAYERS:
        title_key = normalize_key(title)
        title_words = title_key.split()
        matches: list[Tag] = []
        for tag in root.find_all(True):
            if id(tag) in used:
                continue
            attrs = " ".join(
                " ".join(value) if isinstance(value, list) else str(value)
                for key, value in tag.attrs.items()
                if key in {"id", "class", "data-title", "aria-label", "name"}
            )
            attr_key = normalize_key(attrs)
            if not attr_key:
                continue
            if title_key in attr_key or all(word in attr_key for word in title_words):
                text_len = len(tag.get_text(" ", strip=True))
                if text_len > 200:
                    matches.append(tag)
        if not matches:
            return None
        match = min(matches, key=lambda tag: len(tag.get_text(" ", strip=True)))
        used.add(id(match))
        lines = collect_lines(match)
        if lines:
            body = render_line_groups(lines)
            found.append(Prayer(title, slug, add_illuminated_initials(body)))

    if len(found) == len(PRAYERS):
        logging.info("Split prayers using explicit DOM attributes")
        return found
    return None


def marker_match(line: str) -> int | None:
    key = normalize_key(line)
    key = re.sub(r"^\d+\s+", "", key)
    key = re.sub(r"^(?:gio\s+)?", "", key)

    variants = {
        "kinh sach": 0,
        "kinh sang": 1,
        "kinh trua gio ba": 2,
        "gio ba": 2,
        "kinh ba": 2,
        "kinh trua gio sau": 3,
        "gio sau": 3,
        "kinh sau": 3,
        "kinh trua gio chin": 4,
        "gio chin": 4,
        "kinh chin": 4,
        "kinh chieu": 5,
        "kinh toi": 6,
    }
    for marker, index in variants.items():
        if key == marker or key.startswith(marker + " "):
            return index
    return None


def split_by_markers(lines: list[str]) -> list[Prayer] | None:
    starts: dict[int, int] = {}
    for index, line in enumerate(lines):
        matched = marker_match(line)
        if matched is not None and matched not in starts:
            starts[matched] = index

    if len(starts) < len(PRAYERS):
        missing = [title for i, (title, _) in enumerate(PRAYERS) if i not in starts]
        logging.warning("Fallback marker split missing sections: %s", ", ".join(missing))
        return None

    ordered = sorted(starts.items(), key=lambda item: item[1])
    prayers: list[Prayer] = []
    for order_index, (prayer_index, start) in enumerate(ordered):
        end = ordered[order_index + 1][1] if order_index + 1 < len(ordered) else len(lines)
        title, slug = PRAYERS[prayer_index]
        body = render_line_groups(trim_blank_lines(lines[start:end]))
        prayers.append(Prayer(title, slug, add_illuminated_initials(body)))

    prayers.sort(key=lambda prayer: [slug for _, slug in PRAYERS].index(prayer.slug))
    logging.warning("Using fallback split by heading/text markers")
    return prayers


def split_prayers(root: Tag) -> list[Prayer]:
    explicit = find_explicit_sections(root)
    if explicit:
        return explicit

    lines = collect_lines(root)
    logging.info("Collected %d content lines for fallback parsing", len(lines))
    by_marker = split_by_markers(lines)
    if by_marker:
        return by_marker

    raise ValueError("Could not split source into all 7 prayer sections")


def is_label(line: str) -> bool:
    return any(re.search(pattern, line, re.I) for pattern in LABEL_PATTERNS)


def is_heading(line: str) -> bool:
    key = normalize_key(line)
    if marker_match(line) is not None:
        return True
    if len(line) <= 80 and any(
        token in key
        for token in (
            "thanh thi",
            "giao dau",
            "ca vinh",
            "loi chua",
            "xuong dap",
            "loi nguyen",
            "ket thuc",
            "tin mung",
            "bai doc",
        )
    ):
        return True
    return False


def line_to_html(line: str) -> str:
    escaped = html.escape(line, quote=True)
    if is_heading(line):
        return f'<h2>{escaped}</h2>'
    if is_label(line):
        return f'<p class="label"><strong>{escaped}</strong></p>'
    return f"<div>{escaped}</div>"


def render_line_groups(lines: list[str]) -> str:
    parts: list[str] = []
    stanza: list[str] = []

    def flush_stanza() -> None:
        nonlocal stanza
        if stanza:
            parts.append('<div class="stanza">')
            parts.extend(line_to_html(line) for line in stanza)
            parts.append("</div>")
            stanza = []

    for line in lines:
        if not line:
            flush_stanza()
            continue
        if is_heading(line) or is_label(line):
            flush_stanza()
            parts.append(line_to_html(line))
        else:
            stanza.append(line)
    flush_stanza()
    return "\n".join(parts)


def liturgical_day_html(liturgical_day: LiturgicalDay | None) -> str:
    if not liturgical_day:
        return ""
    title = html.escape(liturgical_day.title)
    date_title_value = liturgical_day.date_title
    if normalize_key(date_title_value) == normalize_key(liturgical_day.title):
        date_title_value = ""
    date_title = html.escape(date_title_value)
    rank = html.escape(liturgical_day.rank)
    date_html = f'  <div class="feast-date">{date_title}</div>\n' if date_title else ""
    rank_html = f'  <div class="feast-rank">{rank}</div>\n' if rank else ""
    return (
        '<section class="liturgical-day">\n'
        f"{date_html}"
        f'  <div class="feast-title">{title}</div>\n'
        f"{rank_html}"
        "</section>"
    )


def clean_output_html(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines()) + "\n"


def page_shell(
    title: str,
    body: str,
    updated: str,
    nav: str,
    liturgical_day: LiturgicalDay | None = None,
    show_metadata: bool = True,
    show_title: bool = True,
    page_note: str = "",
    css_href: str = "style.css",
    extra_head: str = "",
    bottom_nav: str | None = None,
    body_class: str = "",
) -> str:
    escaped_title = html.escape(title, quote=True)
    escaped_css_href = html.escape(css_href, quote=True)
    body_class_attr = f' class="{html.escape(body_class, quote=True)}"' if body_class else ""
    feast_html = liturgical_day_html(liturgical_day) if show_metadata else ""
    metadata_html = (
        f'    <p class="updated">Cập nhật: {html.escape(updated)}</p>\n'
        f"    {feast_html}\n"
        if show_metadata
        else ""
    )
    page_note_html = f'    <p class="updated">{html.escape(page_note)}</p>\n' if page_note else ""
    title_html = f"    <h1>{html.escape(title)}</h1>\n" if show_title else ""
    return clean_output_html(f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <link rel="stylesheet" href="{escaped_css_href}">
{extra_head}
</head>
<body{body_class_attr}>
  <main>
    {nav}
{title_html}{metadata_html}{page_note_html}
    {body}
    {bottom_nav if bottom_nav is not None else nav}
  </main>
</body>
</html>
""")


def nav_html(previous_prayer: Prayer | None, next_prayer: Prayer | None) -> str:
    prev_link = (
        f'<a href="{previous_prayer.slug}.html">Giờ trước</a>'
        if previous_prayer
        else '<span>Giờ trước</span>'
    )
    next_link = (
        f'<a href="{next_prayer.slug}.html">Giờ sau</a>'
        if next_prayer
        else '<span>Giờ sau</span>'
    )
    return (
        '<nav class="page-nav">'
        '<a href="index.html">Trang chủ</a>'
        f"{prev_link}"
        f"{next_link}"
        "</nav>"
    )


def prayer_page_filename(slug: str, page_number: int) -> str:
    return f"{slug}.html" if page_number == 1 else f"{slug}-{page_number}.html"


def responsive_prayer_filename(slug: str) -> str:
    return f"{slug}-responsive.html"


def date_dir_name(date: datetime) -> str:
    return date.strftime("%Y-%m-%d")


def day_href(date: datetime, slug: str = "index", page_number: int = 1) -> str:
    filename = "index.html" if slug == "index" else prayer_page_filename(slug, page_number)
    return f"{date_dir_name(date)}/{filename}"


def relative_day_href(from_dir: str, target_date: datetime, slug: str = "index", page_number: int = 1) -> str:
    href = day_href(target_date, slug, page_number)
    return f"../{href}" if from_dir else href


def date_nav_html(
    current_date: datetime,
    available_dates: list[datetime],
    from_dir: str,
    slug: str = "index",
    responsive: bool = False,
) -> str:
    items: list[str] = []
    for date in available_dates:
        label = f"{date.day}/{date.month}"
        if responsive and slug == "index":
            href = f"{date_dir_name(date)}/index-responsive.html"
            href = f"../{href}" if from_dir else href
        elif responsive:
            filename = responsive_prayer_filename(slug)
            href = f"{date_dir_name(date)}/{filename}"
            href = f"../{href}" if from_dir else href
        else:
            href = relative_day_href(from_dir, date, slug)
        cls = ' class="active"' if date.date() == current_date.date() else ""
        items.append(f'<a{cls} href="{href}">{html.escape(label)}</a>')
    return '<nav class="date-nav">' + "".join(items) + "</nav>"


def text_units(text: str) -> int:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return 0
    return max(1, (len(normalized) + CHARS_PER_READING_LINE - 1) // CHARS_PER_READING_LINE)


def block_units(block_html: str) -> float:
    soup = BeautifulSoup(block_html, "lxml")
    text = soup.get_text(" ", strip=True)
    br_count = len(soup.find_all("br"))
    heading_count = len(soup.find_all(["h2", "h3"]))
    explicit_lines = br_count + 1 if text else 0
    base_units = max(text_units(text), explicit_lines)

    # A verse line is a block of its own, so estimating the complete paragraph
    # as continuous prose can undercount it. Count every displayed verse line
    # independently and include the small CSS gap after it. Production output
    # commonly wraps one verse-line in its own <p>, whose bottom margin also
    # needs a fractional unit.
    verse_lines = soup.select(".verse-line, .verse-continuation")
    verse_spacing_units = 0.0
    if verse_lines:
        verse_units = 0
        for verse_line in verse_lines:
            verse_text = verse_line.get_text(" ", strip=True)
            verse_explicit_lines = len(verse_line.find_all("br")) + 1 if verse_text else 0
            verse_units += max(text_units(verse_text), verse_explicit_lines)
        base_units = max(base_units, verse_units)
        verse_spacing_units = len(verse_lines) * VERSE_LINE_SPACING_UNITS

    # Divine Office represents a hymn stanza as a sequence of plain <div>
    # elements.  Those elements are block-level on Kindle, but treating the
    # parent as ordinary prose merges the lines while measuring.  That lets a
    # page absorb an extra stanza and pushes the fixed bottom navigation below
    # the viewport.  Vietnamese production pages use verse-line spans instead,
    # so this only corrects the separate English source shape.
    stanza_lines = soup.select(".stanza > div")
    if stanza_lines:
        stanza_units = 0
        for stanza_line in stanza_lines:
            stanza_text = stanza_line.get_text(" ", strip=True)
            stanza_explicit_lines = (
                len(stanza_line.find_all("br")) + 1 if stanza_text else 0
            )
            stanza_units += max(text_units(stanza_text), stanza_explicit_lines)
        base_units = max(base_units, stanza_units)

    paragraph_spacing_units = 0.0
    for paragraph in soup.find_all("p"):
        classes = set(paragraph.get("class", []))
        paragraph_spacing_units += (
            SPLIT_PARAGRAPH_SPACING_UNITS
            if "split-block" in classes
            else PARAGRAPH_SPACING_UNITS
        )

    stanza_spacing_units = len(soup.select(".stanza")) * STANZA_SPACING_UNITS

    # The antiphon label and body are display:block in the Kindle stylesheet.
    # Count them separately even when their combined text is short.
    for antiphon in soup.select(".antiphon"):
        antiphon_units = 0
        for selector in (".pre", ".body"):
            part = antiphon.select_one(selector)
            if part is None:
                continue
            part_text = part.get_text(" ", strip=True)
            part_explicit_lines = len(part.find_all("br")) + 1 if part_text else 0
            antiphon_units += max(text_units(part_text), part_explicit_lines)
        base_units = max(base_units, antiphon_units)

    return max(
        1.0,
        base_units
        + heading_count
        + verse_spacing_units
        + paragraph_spacing_units
        + stanza_spacing_units,
    )


def is_heading_block(block_html: str) -> bool:
    soup = BeautifulSoup(block_html, "lxml")
    first = soup.find(["h2", "h3"])
    return bool(first and first.get_text(strip=True))


def page_units(blocks: list[str]) -> float:
    return sum(block_units(block) for block in blocks)


def paragraph_lines(node: Tag) -> list[str]:
    if len(node.find_all("br", recursive=False)) + 1 < SPLIT_PARAGRAPH_MIN_LINES:
        return []

    lines: list[str] = []
    current: list[str] = []
    for child in node.contents:
        if isinstance(child, Tag) and child.name == "br":
            line = "".join(current).strip()
            if line:
                lines.append(line)
            current = []
            continue
        current.append(str(child))

    line = "".join(current).strip()
    if line:
        lines.append(line)

    return lines if len(lines) >= SPLIT_PARAGRAPH_MIN_LINES else []


def render_split_paragraph(node: Tag, lines: list[str]) -> str:
    classes = [class_name for class_name in node.get("class", []) if class_name != "split-block"]
    classes.append("split-block")
    class_attr = html.escape(" ".join(classes), quote=True)
    return f'<p class="{class_attr}">{"<br/>".join(lines)}</p>'


def paragraph_text_tokens(node: Tag) -> list[str]:
    if node.find("br"):
        return []

    tokens: list[str] = []
    for child in node.contents:
        if isinstance(child, NavigableString):
            tokens.extend(re.findall(r"\s+|\S+\s*", str(child)))
        elif isinstance(child, Tag):
            tokens.append(str(child))
    return [token for token in tokens if token]


def render_split_tokens_paragraph(node: Tag, tokens: list[str]) -> str:
    classes = [class_name for class_name in node.get("class", []) if class_name != "split-block"]
    classes.append("split-block")
    class_attr = html.escape(" ".join(classes), quote=True)
    return f'<p class="{class_attr}">{"".join(tokens).strip()}</p>'


def split_text_paragraph_to_fit(paragraph: Tag, remaining_units: float) -> tuple[str, str] | None:
    if remaining_units < 4:
        return None

    # The previous 30-character estimate deliberately allowed two extra units.
    # With the calibrated 48-character estimate that overshoot can become two
    # real Kindle lines, so the split must respect the remaining page budget.
    allowed_units = remaining_units
    tokens = paragraph_text_tokens(paragraph)
    if len(tokens) < 8:
        return None

    best_cut = 0
    for cut in range(1, len(tokens)):
        prefix = render_split_tokens_paragraph(paragraph, tokens[:cut])
        if block_units(prefix) <= allowed_units:
            best_cut = cut
        else:
            break

    if best_cut <= 0 or best_cut >= len(tokens):
        return None

    preferred_cut = best_cut
    for punctuation in (r"[.!?][”\"]?$", r"[;:,”“]$"):
        for cut in range(best_cut, max(0, best_cut - 60), -1):
            candidate = render_split_tokens_paragraph(paragraph, tokens[:cut])
            text = BeautifulSoup(candidate, "lxml").get_text(" ", strip=True)
            if re.search(punctuation, text) and block_units(candidate) >= max(2, remaining_units - 4):
                preferred_cut = cut
                break
        if preferred_cut != best_cut:
            break
    best_cut = preferred_cut

    suffix = render_split_tokens_paragraph(paragraph, tokens[best_cut:])
    if not BeautifulSoup(suffix, "lxml").get_text(" ", strip=True):
        return None

    prefix = render_split_tokens_paragraph(paragraph, tokens[:best_cut])
    return prefix, suffix


def split_block_to_fit(block_html: str, remaining_units: float) -> tuple[str, str] | None:
    if remaining_units < 2:
        return None

    soup = BeautifulSoup(block_html, "lxml")
    paragraph = soup.find("p")
    if not paragraph:
        return None

    lines = paragraph_lines(paragraph)
    if not lines:
        return split_text_paragraph_to_fit(paragraph, remaining_units)

    best_cut = 0
    for cut in range(SPLIT_PARAGRAPH_CHUNK_LINES, len(lines)):
        prefix = render_split_paragraph(paragraph, lines[:cut])
        if block_units(prefix) <= remaining_units:
            best_cut = cut
        else:
            break

    if best_cut <= 0:
        return None
    if len(lines) - best_cut == 1 and best_cut > SPLIT_PARAGRAPH_CHUNK_LINES:
        best_cut -= 1

    prefix = render_split_paragraph(paragraph, lines[:best_cut])
    suffix = render_split_paragraph(paragraph, lines[best_cut:])
    return prefix, suffix


def rebalance_short_pages(pages: list[list[str]]) -> list[list[str]]:
    index = 1
    while index < len(pages):
        current_units = page_units(pages[index])
        if index < len(pages) - 1 and pages[index + 1]:
            next_block = pages[index + 1][0]
            next_units = block_units(next_block)
            if current_units + next_units <= PAGE_TARGET_UNITS:
                pages[index].append(pages[index + 1].pop(0))
                if not pages[index + 1]:
                    del pages[index + 1]
                continue
            split = split_block_to_fit(next_block, PAGE_TARGET_UNITS - current_units)
            if split:
                prefix, suffix = split
                pages[index].append(prefix)
                pages[index + 1][0] = suffix
                continue

        if current_units >= MIN_PAGE_UNITS:
            index += 1
            continue

        if index > 0 and pages[index - 1]:
            previous_block = pages[index - 1][-1]
            previous_units = block_units(previous_block)
            previous_remaining_units = page_units(pages[index - 1][:-1])
            if (
                current_units + previous_units <= PAGE_TARGET_UNITS
                and previous_remaining_units >= MIN_PAGE_UNITS
            ):
                pages[index].insert(0, pages[index - 1].pop())
                continue

        if index == len(pages) - 1 and pages[index - 1]:
            combined_units = page_units(pages[index - 1]) + current_units
            if combined_units <= PAGE_TARGET_UNITS:
                pages[index - 1].extend(pages[index])
                del pages[index]
                continue

        index += 1

    index = 0
    while index < len(pages):
        if pages[index]:
            index += 1
            continue
        del pages[index]
    return pages


def html_blocks(fragment: str) -> list[str]:
    soup = fragment_soup(fragment)
    wrapper = soup.find("div")
    if not wrapper:
        return []

    blocks: list[str] = []

    def collect(node) -> None:
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            if node.strip():
                blocks.append(f"<p>{html.escape(str(node).strip())}</p>")
            return
        if not isinstance(node, Tag):
            return

        classes = set(node.get("class", []))
        if node.name in {"h2", "h3"} or classes & {
            "antiphon",
            "indexing",
            "label",
            "note",
            "right-indexing",
            "stanza",
            "title",
        }:
            blocks.append(str(node))
            return

        if node.name == "p":
            verse_lines = node.select(".verse-line, .verse-continuation")
            if len(verse_lines) > 1:
                for verse_line in verse_lines:
                    blocks.append(f"<p>{verse_line}</p>")
            else:
                blocks.append(str(node))
            return

        meaningful_children = [
            child
            for child in node.contents
            if not (isinstance(child, NavigableString) and not child.strip())
        ]
        if node.name == "div" and meaningful_children:
            for child in meaningful_children:
                collect(child)
            return

        blocks.append(str(node))

    for child in list(wrapper.contents):
        collect(child)
    return blocks


def paginate_html(fragment: str) -> list[str]:
    blocks = html_blocks(fragment)
    if not blocks:
        return [fragment]

    pages: list[list[str]] = []
    current: list[str] = []
    current_units = 0
    pending = list(blocks)

    while pending:
        block = pending.pop(0)
        units = block_units(block)
        target = FIRST_PAGE_TARGET_UNITS if not pages else PAGE_TARGET_UNITS
        if current and is_heading_block(block) and current_units >= MIN_UNITS_BEFORE_HEADING_BREAK:
            pages.append(current)
            current = []
            current_units = 0
            target = PAGE_TARGET_UNITS
        if current and current_units + units > target:
            split = split_block_to_fit(block, target - current_units)
            if split:
                prefix, suffix = split
                current.append(prefix)
                pages.append(current)
                current = []
                current_units = 0
                pending.insert(0, suffix)
                continue
            pages.append(current)
            current = []
            current_units = 0
            target = PAGE_TARGET_UNITS
        if not current and units > target:
            split = split_block_to_fit(block, target)
            if split:
                prefix, suffix = split
                pages.append([prefix])
                pending.insert(0, suffix)
                continue
        current.append(block)
        current_units += units

    if current:
        pages.append(current)

    pages = rebalance_short_pages(pages)
    return ["\n".join(page) for page in pages]


def split_learner_fragments(value: str) -> list[str]:
    """Split source prose into paired, Kindle-sized reading units.

    A unit normally is one sentence. Very long liturgical sentences are split
    at a natural clause or word boundary so one two-column row can never force
    the fixed page navigation out of the Paperwhite viewport.
    """
    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    for match in re.finditer(r"[.!?]+(?:[\"”’)]*)", text):
        end = match.end()
        following = text[end:].lstrip()
        before = text[start:end]
        abbreviation = re.search(r"\b(?:St|Mr|Mrs|Ms|Dr|Fr|No|R|V)\.$", before)
        if abbreviation or not following or not re.match(r"[A-Z“]", following):
            continue
        sentences.append(text[start:end].strip())
        start = end
    if text[start:].strip():
        sentences.append(text[start:].strip())
    if not sentences:
        sentences = [text]

    fragments: list[str] = []
    for sentence in sentences:
        remaining = sentence
        while len(remaining) > LEARNER_MAX_FRAGMENT_CHARS:
            cut = max(
                remaining.rfind(marker, 0, LEARNER_MAX_FRAGMENT_CHARS + 1)
                for marker in ("; ", ": ", ", ", " — ", " ")
            )
            if cut <= 0:
                break
            fragment = remaining[:cut].rstrip(" ,;:")
            if fragment:
                fragments.append(fragment)
            remaining = remaining[cut:].lstrip(" ,;:")
        if remaining:
            fragments.append(remaining)
    return fragments


def learner_left_html(text: str) -> str:
    escaped = html.escape(text)
    if escaped.startswith("—"):
        return '<span class="rubric">—</span>' + escaped[1:]
    return escaped


def learner_row_html(english_text: str, pronunciation: str, *, glossary: bool = False) -> str:
    classes = "learner-row learner-glossary-row" if glossary else "learner-row"
    return (
        f'<section class="{classes}">'
        f'<div class="learner-english"><p>{learner_left_html(english_text)}</p></div>'
        f'<div class="learner-pronunciation" lang="en-GB"><p>{html.escape(pronunciation)}</p></div>'
        "</section>"
    )


def learner_source_units(body_html: str) -> list[tuple[str, str]]:
    """Return ('heading' | 'sentence', HTML/text) units from Divine Office HTML."""
    units: list[tuple[str, str]] = []
    for block in html_blocks(body_html):
        soup = fragment_soup(block)
        wrapper = soup.find("div")
        if wrapper is None:
            continue
        node = next((child for child in wrapper.children if isinstance(child, Tag)), None)
        if node is None:
            continue
        if node.name in {"h2", "h3"}:
            units.append(("heading", str(node)))
            continue
        lines = node.select(":scope > div") if "stanza" in set(node.get("class", [])) else [node]
        for line in lines:
            line_text = line.get_text(" ", strip=True)
            units.extend(("sentence", fragment) for fragment in split_learner_fragments(line_text))
    return units


def learner_prayer_body(
    prayer: Prayer,
    language: LearnerLanguage,
    *,
    units: list[tuple[str, str]] | None = None,
    pronunciations: dict[str, str] | None = None,
    glossary: list[dict[str, str]] | None = None,
    glossary_guides: dict[str, str] | None = None,
) -> str:
    units = units if units is not None else learner_source_units(prayer.body_html)
    sentences = [value for kind, value in units if kind == "sentence"]
    pronunciations = pronunciations if pronunciations is not None else language.pronunciations(sentences)
    rendered: list[str] = []
    for kind, value in units:
        if kind == "heading":
            rendered.append(value)
        else:
            rendered.append(learner_row_html(value, pronunciations[value]))

    source_text = " ".join(sentences)
    glossary = glossary if glossary is not None else language.glossary(prayer.title, source_text)
    glossary_left = [f"{item['term']} — {item['definition']}" for item in glossary]
    glossary_guides = glossary_guides if glossary_guides is not None else language.pronunciations(glossary_left)
    rendered.append('<section class="learner-glossary"><h2>Words in this prayer</h2>')
    rendered.extend(
        learner_row_html(left, glossary_guides[left], glossary=True)
        for left in glossary_left
    )
    rendered.append("</section>")
    return "\n".join(rendered)


def learner_html_blocks(fragment: str) -> list[str]:
    soup = fragment_soup(fragment)
    wrapper = soup.find("div")
    if not wrapper:
        return []
    # Be tolerant of neutral transport wrappers.  Cached/decrypted content
    # used to acquire one of these and the paginator silently counted that
    # wrapper as a single, page-sized block.
    while True:
        children = [child for child in wrapper.children if isinstance(child, Tag)]
        if (
            len(children) == 1
            and children[0].name == "div"
            and not children[0].attrs
        ):
            wrapper = children[0]
            continue
        break
    blocks: list[str] = []
    for child in wrapper.children:
        if isinstance(child, NavigableString):
            continue
        if not isinstance(child, Tag):
            continue
        if "learner-glossary" in set(child.get("class", [])):
            for glossary_child in child.children:
                if isinstance(glossary_child, Tag):
                    blocks.append(str(glossary_child))
            continue
        blocks.append(str(child))
    return blocks


def learner_text_units(text: str, chars_per_line: int) -> float:
    normalized = re.sub(r"\s+", " ", text).strip()
    return float(max(1, (len(normalized) + chars_per_line - 1) // chars_per_line))


def learner_block_units(block_html: str) -> float:
    soup = fragment_soup(block_html)
    row = soup.select_one(".learner-row")
    if row:
        left = row.select_one(".learner-english")
        right = row.select_one(".learner-pronunciation")
        left_text = left.get_text(" ", strip=True) if left else ""
        right_text = right.get_text(" ", strip=True) if right else ""
        return max(
            learner_text_units(left_text, LEARNER_LEFT_CHARS_PER_LINE),
            learner_text_units(right_text, LEARNER_RIGHT_CHARS_PER_LINE),
        ) + LEARNER_ROW_SPACING_UNITS
    heading = soup.find(["h2", "h3"])
    if heading:
        return 1.8 + learner_text_units(heading.get_text(" ", strip=True), LEARNER_LEFT_CHARS_PER_LINE)
    return block_units(block_html)


def learner_page_units(blocks: list[str]) -> float:
    return sum(learner_block_units(block) for block in blocks)


def rebalance_learner_pages(pages: list[list[str]]) -> list[list[str]]:
    index = 1
    while index < len(pages):
        current_units = learner_page_units(pages[index])
        if index < len(pages) - 1 and pages[index + 1]:
            # Do not leave a section heading alone at the end of a page.  This
            # is particularly conspicuous in the two-column learner layout.
            if is_heading_block(pages[index][-1]):
                heading = pages[index][-1]
                following = pages[index + 1][0]
                remaining = learner_page_units(pages[index][:-1])
                if (
                    remaining >= LEARNER_MIN_PAGE_UNITS
                    and learner_page_units([heading, following]) <= LEARNER_PAGE_TARGET_UNITS
                ):
                    pages[index].pop()
                    pages[index + 1].insert(0, heading)
                    # This page is already above the minimum fill.  Advance
                    # to the page that received the heading; otherwise the
                    # generic pull-forward branch below can move the heading
                    # straight back and oscillate forever.
                    index += 1
                    continue
            candidate = pages[index + 1][0]
            if current_units + learner_block_units(candidate) <= LEARNER_PAGE_TARGET_UNITS:
                pages[index].append(pages[index + 1].pop(0))
                if not pages[index + 1]:
                    del pages[index + 1]
                continue
        if current_units >= LEARNER_MIN_PAGE_UNITS:
            index += 1
            continue
        if index > 0 and pages[index - 1]:
            candidate = pages[index - 1][-1]
            remaining = learner_page_units(pages[index - 1][:-1])
            if (
                current_units + learner_block_units(candidate) <= LEARNER_PAGE_TARGET_UNITS
                and remaining >= LEARNER_MIN_PAGE_UNITS
            ):
                pages[index].insert(0, pages[index - 1].pop())
                continue
        index += 1
    return [page for page in pages if page]


def paginate_learner_html(fragment: str) -> list[str]:
    blocks = learner_html_blocks(fragment)
    if not blocks:
        return [fragment]
    pages: list[list[str]] = []
    current: list[str] = []
    current_units = 0.0
    for position, block in enumerate(blocks):
        units = learner_block_units(block)
        target = LEARNER_FIRST_PAGE_TARGET_UNITS if not pages else LEARNER_PAGE_TARGET_UNITS
        if units > target:
            raise LearnerLanguageError("A learner row exceeds the Kindle page budget")
        if current and is_heading_block(block) and position + 1 < len(blocks):
            # Keep a heading with at least its first following line.  Unlike
            # the Vietnamese single-column paginator, the learner rows are
            # short enough that a fixed early-heading threshold made half-full
            # pages and orphan headings on Paperwhite 3.
            next_units = learner_block_units(blocks[position + 1])
            if current_units + units + next_units > target:
                pages.append(current)
                current = []
                current_units = 0.0
                target = LEARNER_PAGE_TARGET_UNITS
        if current and current_units + units > target:
            pages.append(current)
            current = []
            current_units = 0.0
        current.append(block)
        current_units += units
    if current:
        pages.append(current)
    pages = rebalance_learner_pages(pages)
    return ["\n".join(page) for page in pages]


def page_nav_html(
    previous_href: str | None,
    next_href: str | None,
    page_number: int,
    page_count: int,
    index_href: str = "index.html",
) -> str:
    previous_item = (
        f'<a class="nav-icon" href="{previous_href}">&#9664;</a>' if previous_href else '<span class="nav-icon">&#9664;</span>'
    )
    next_item = f'<a class="nav-icon" href="{next_href}">&#9654;</a>' if next_href else '<span class="nav-icon">&#9654;</span>'
    return (
        '<nav class="page-nav paged-nav">'
        f"{previous_item}"
        f"{next_item}"
        f'<a class="nav-index" href="{index_href}">Mục lục</a>'
        f"{previous_item}"
        f"{next_item}"
        "</nav>"
    )


def breviary_page_nav_html(
    previous_href: str | None,
    next_href: str | None,
    index_href: str = "index.html",
) -> str:
    previous_item = (
        f'<a class="nav-icon" href="{previous_href}">&#8249;</a>'
        if previous_href
        else '<span class="nav-icon">&#8249;</span>'
    )
    next_item = (
        f'<a class="nav-icon" href="{next_href}">&#8250;</a>'
        if next_href
        else '<span class="nav-icon">&#8250;</span>'
    )
    return (
        '<nav class="page-nav paged-nav breviary-nav">'
        f"{previous_item}"
        f"{next_item}"
        f'<a class="nav-index" href="{index_href}">Mục lục</a>'
        f"{previous_item}"
        f"{next_item}"
        "</nav>"
    )


def responsive_page_nav_html(
    previous_prayer: Prayer | None,
    next_prayer: Prayer | None,
    index_href: str = "index-responsive.html",
) -> str:
    previous_item = (
        f'<a class="nav-icon" href="{responsive_prayer_filename(previous_prayer.slug)}">&#9664;</a>'
        if previous_prayer
        else '<span class="nav-icon">&#9664;</span>'
    )
    next_item = (
        f'<a class="nav-icon" href="{responsive_prayer_filename(next_prayer.slug)}">&#9654;</a>'
        if next_prayer
        else '<span class="nav-icon">&#9654;</span>'
    )
    return (
        '<nav class="page-nav responsive-nav">'
        f"{previous_item}"
        f'<a class="nav-index" href="{index_href}">Mục lục</a>'
        f"{next_item}"
        "</nav>"
    )


def write_day_site(
    target_dir: Path,
    css_href: str,
    prayers: list[Prayer],
    liturgical_day: LiturgicalDay | None,
    date: datetime,
    available_dates: list[datetime],
    updated: str,
    from_dir: str,
    paginated: dict[str, list[str]] | None = None,
) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for _, slug in PRAYERS:
        for path in target_dir.glob(f"{slug}*.html"):
            path.unlink()
    index_items = "\n".join(
        f'<li><a href="{slug}.html">{html.escape(title)}</a></li>' for title, slug in PRAYERS
    )
    index_body = f"""
{date_nav_html(date, available_dates, from_dir)}
<section class="home-list">
  <ul>
    {index_items}
  </ul>
</section>
<p class="kindle-note">Phiên bản này dành cho trình duyệt web tối giản của Kindle.</p>
<p class="mode-switch"><a href="index-responsive.html">Mở bản responsive</a> <a href="{('breviary/index.html' if not from_dir else '../breviary/' + from_dir + '/index.html')}">Mở bản Breviary</a></p>
"""
    (target_dir / "index.html").write_text(
        page_shell(
            "Các Giờ Kinh Phụng Vụ",
            index_body,
            updated,
            "",
            liturgical_day,
            css_href=css_href,
            bottom_nav="",
        ),
        encoding="utf-8",
    )

    prayer_by_slug = {prayer.slug: prayer for prayer in prayers}
    ordered = [prayer_by_slug[slug] for _, slug in PRAYERS]
    responsive_index_items = "\n".join(
        f'<li><a href="{responsive_prayer_filename(slug)}">{html.escape(title)}</a></li>' for title, slug in PRAYERS
    )
    responsive_index_body = f"""
{date_nav_html(date, available_dates, from_dir, responsive=True)}
<section class="home-list">
  <ul>
    {responsive_index_items}
  </ul>
</section>
<p class="mode-switch"><a href="index.html">Trở về bản Kindle</a></p>
"""
    (target_dir / "index-responsive.html").write_text(
        page_shell(
            "Các Giờ Kinh Phụng Vụ",
            responsive_index_body,
            updated,
            "",
            liturgical_day,
            css_href=css_href,
            bottom_nav="",
            body_class="responsive-page responsive-index",
        ),
        encoding="utf-8",
    )

    for index, prayer in enumerate(ordered):
        previous_prayer = ordered[index - 1] if index > 0 else None
        next_prayer = ordered[index + 1] if index + 1 < len(ordered) else None
        nav = responsive_page_nav_html(previous_prayer, next_prayer)
        (target_dir / responsive_prayer_filename(prayer.slug)).write_text(
            page_shell(
                prayer.title,
                prayer.body_html,
                updated,
                "",
                prayer.liturgical_day or liturgical_day,
                css_href=css_href,
                bottom_nav=nav,
                body_class="responsive-page responsive-prayer",
            ),
            encoding="utf-8",
        )

    if paginated is None:
        paginated = {prayer.slug: paginate_html(prayer.body_html) for prayer in ordered}
    for index, prayer in enumerate(ordered):
        pages = paginated[prayer.slug]
        page_count = len(pages)
        for page_index, page_body in enumerate(pages, start=1):
            previous_href = None
            next_href = None

            if page_index > 1:
                previous_href = prayer_page_filename(prayer.slug, page_index - 1)
            elif index > 0:
                previous_prayer = ordered[index - 1]
                previous_href = prayer_page_filename(previous_prayer.slug, len(paginated[previous_prayer.slug]))

            if page_index < page_count:
                next_href = prayer_page_filename(prayer.slug, page_index + 1)
            elif index + 1 < len(ordered):
                next_prayer = ordered[index + 1]
                next_href = prayer_page_filename(next_prayer.slug, 1)

            index_href = "index.html" if from_dir else day_href(date)
            nav = page_nav_html(previous_href, next_href, page_index, page_count, index_href)
            page_note = f"{prayer.title} {page_index}/{page_count}" if page_index > 1 else ""
            (target_dir / prayer_page_filename(prayer.slug, page_index)).write_text(
                page_shell(
                    prayer.title,
                    page_body,
                    updated,
                    "",
                    prayer.liturgical_day or liturgical_day,
                    show_metadata=page_index == 1,
                    show_title=page_index == 1,
                    page_note=page_note,
                    css_href=css_href,
                    bottom_nav=nav,
                ),
                encoding="utf-8",
            )


def write_breviary_day_site(
    target_dir: Path,
    css_href: str,
    prayers: list[Prayer],
    liturgical_day: LiturgicalDay | None,
    date: datetime,
    available_dates: list[datetime],
    updated: str,
    from_dir: str,
    paginated: dict[str, list[str]],
) -> None:
    """Write the Breviary skin without recalculating any pagination."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for _, slug in PRAYERS:
        for path in target_dir.glob(f"{slug}*.html"):
            path.unlink()

    index_items = "\n".join(
        f'<li><a href="{slug}.html">{html.escape(title)}</a></li>' for title, slug in PRAYERS
    )
    original_index_href = f"../../{from_dir}/index.html" if from_dir else "../index.html"
    index_body = f"""
{date_nav_html(date, available_dates, from_dir)}
<section class="home-list">
  <ul>
    {index_items}
  </ul>
</section>
<p class="kindle-note">Monastic Breviary · bản tối giản dành cho Kindle.</p>
<p class="mode-switch"><a href="{original_index_href}">Trở về bản Kindle</a></p>
"""
    (target_dir / "index.html").write_text(
        page_shell(
            "Các Giờ Kinh Phụng Vụ",
            index_body,
            updated,
            "",
            liturgical_day,
            css_href=css_href,
            bottom_nav="",
            body_class="breviary-page breviary-index",
        ),
        encoding="utf-8",
    )

    prayer_by_slug = {prayer.slug: prayer for prayer in prayers}
    ordered = [prayer_by_slug[slug] for _, slug in PRAYERS]
    for index, prayer in enumerate(ordered):
        pages = paginated[prayer.slug]
        page_count = len(pages)
        for page_index, page_body in enumerate(pages, start=1):
            previous_href = None
            next_href = None

            if page_index > 1:
                previous_href = prayer_page_filename(prayer.slug, page_index - 1)
            elif index > 0:
                previous_prayer = ordered[index - 1]
                previous_href = prayer_page_filename(
                    previous_prayer.slug, len(paginated[previous_prayer.slug])
                )

            if page_index < page_count:
                next_href = prayer_page_filename(prayer.slug, page_index + 1)
            elif index + 1 < len(ordered):
                next_prayer = ordered[index + 1]
                next_href = prayer_page_filename(next_prayer.slug, 1)

            nav = breviary_page_nav_html(previous_href, next_href)
            page_note = f"{prayer.title} {page_index}/{page_count}" if page_index > 1 else ""
            body_class = "breviary-page breviary-first" if page_index == 1 else "breviary-page"
            (target_dir / prayer_page_filename(prayer.slug, page_index)).write_text(
                page_shell(
                    prayer.title,
                    page_body,
                    updated,
                    "",
                    prayer.liturgical_day or liturgical_day,
                    show_metadata=page_index == 1,
                    show_title=page_index == 1,
                    page_note=page_note,
                    css_href=css_href,
                    bottom_nav=nav,
                    body_class=body_class,
                ),
                encoding="utf-8",
            )


def english_breviary_nav_html(
    previous_href: str | None,
    next_href: str | None,
    index_href: str = "index.html",
) -> str:
    previous_item = (
        f'<a class="nav-icon" href="{previous_href}">&#8249;</a>'
        if previous_href
        else '<span class="nav-icon">&#8249;</span>'
    )
    next_item = (
        f'<a class="nav-icon" href="{next_href}">&#8250;</a>'
        if next_href
        else '<span class="nav-icon">&#8250;</span>'
    )
    return (
        '<nav class="page-nav paged-nav breviary-nav">'
        f"{previous_item}{next_item}"
        f'<a class="nav-index" href="{index_href}">Index</a>'
        f"{previous_item}{next_item}"
        "</nav>"
    )


def english_date_nav_html(
    current_date: datetime,
    available_dates: list[datetime],
    from_dir: str,
) -> str:
    items: list[str] = []
    for date in available_dates:
        href = f"{date_dir_name(date)}/index.html"
        if from_dir:
            href = f"../{href}"
        cls = ' class="active"' if date.date() == current_date.date() else ""
        items.append(f'<a{cls} href="{href}">{date.day}/{date.month}</a>')
    return '<nav class="date-nav">' + "".join(items) + "</nav>"


def english_index_inner(
    site: EnglishDaySite,
    available_dates: list[datetime],
    updated: str,
    from_dir: str,
    learner_href: str | None = None,
) -> str:
    items = "".join(
        f'<li><a href="{slug}.html">{html.escape(title)}</a></li>'
        for title, slug in ENGLISH_PRAYERS
    )
    learner_mode_html = (
        f'<p class="mode-switch"><a href="{html.escape(learner_href, quote=True)}">Learner mode</a></p>'
        if learner_href
        else ""
    )
    return clean_output_html(f"""
<h1>English Breviary</h1>
<p class="updated">Updated: {html.escape(updated)}</p>
{liturgical_day_html(site.liturgical_day)}
{english_date_nav_html(site.date, available_dates, from_dir)}
<section class="home-list"><ul>{items}</ul></section>
<p class="kindle-note">For personal reading on Kindle · Source: Divine Office.</p>
{learner_mode_html}
""")


def learner_index_inner(
    site: EnglishDaySite,
    available_dates: list[datetime],
    updated: str,
    from_dir: str,
) -> str:
    items = "".join(
        f'<li><a href="{slug}.html">{html.escape(title)}</a></li>'
        for title, slug in ENGLISH_PRAYERS
    )
    reading_href = "../index.html" if not from_dir else "../../index.html"
    return clean_output_html(f"""
<h1>English Breviary</h1>
<p class="updated">Updated: {html.escape(updated)}</p>
{liturgical_day_html(site.liturgical_day)}
{english_date_nav_html(site.date, available_dates, from_dir)}
<section class="home-list"><ul>{items}</ul></section>
<p class="kindle-note">Casual British IPA for connected speech: weak forms, linking and light sound deletion · Source: Divine Office.</p>
<p class="mode-switch"><a href="{reading_href}">Reading mode</a></p>
""")


def english_prayer_inner(
    prayer: Prayer,
    liturgical_day: LiturgicalDay,
    page_body: str,
    page_index: int,
    page_count: int,
    nav: str,
    updated: str,
) -> str:
    title = f"<h1>{html.escape(prayer.title)}</h1>" if page_index == 1 else ""
    metadata = (
        f'<p class="updated">Updated: {html.escape(updated)}</p>'
        f"{liturgical_day_html(liturgical_day)}"
        if page_index == 1
        else f'<p class="updated">{html.escape(prayer.title)} {page_index}/{page_count}</p>'
    )
    return clean_output_html(f"""
{title}
{metadata}
{page_body}
{nav}
""")


def learner_prayer_inner(
    prayer: Prayer,
    liturgical_day: LiturgicalDay,
    page_body: str,
    page_index: int,
    page_count: int,
    nav: str,
    updated: str,
) -> str:
    title = f"<h1>{html.escape(prayer.title)}</h1>" if page_index == 1 else ""
    metadata = (
        f'<p class="updated">Updated: {html.escape(updated)}</p>'
        f"{liturgical_day_html(liturgical_day)}"
        if page_index == 1
        else f'<p class="updated">{html.escape(prayer.title)} {page_index}/{page_count}</p>'
    )
    return clean_output_html(f"""
{title}
{metadata}
{page_body}
{nav}
""")


def english_unlock_script(ciphertext: dict, session_key: str = ENGLISH_SESSION_KEY) -> str:
    # Kindle WebKit 534 has already proven reliable with SJCL's encoded JSON
    # string path on /debug.  Passing the decoded object takes a different
    # compatibility path inside sjcl.json.decrypt and can fail on that engine.
    payload = json.dumps(json.dumps(ciphertext, separators=(",", ":")))
    return f"""  <script>
  (function () {{
    var CIPHERTEXT = {payload};
    var SESSION_KEY = {json.dumps(session_key)};

    function status(message, isError) {{
      var node = document.getElementById('passcode-status');
      node.className = isError ? 'passcode-status passcode-error' : 'passcode-status';
      node.innerHTML = '';
      node.appendChild(document.createTextNode(message));
    }}

    function reveal(plaintext) {{
      document.getElementById('passcode-gate').style.display = 'none';
      document.getElementById('encrypted-content').innerHTML = plaintext;
    }}

    function unlock(passcode) {{
      status('Unlocking...', false);
      window.setTimeout(function () {{
        var details = {{}};
        var plaintext;
        try {{
          plaintext = window.sjcl.json.decrypt(passcode, CIPHERTEXT, {{}}, details);
        }} catch (decryptError) {{
          status('Incorrect passcode.', true);
          document.getElementById('breviary-passcode').value = '';
          document.getElementById('breviary-passcode').focus();
          return;
        }}
        try {{
          window.sessionStorage.setItem(
            SESSION_KEY,
            window.sjcl.codec.base64.fromBits(details.key)
          );
          if (!window.sessionStorage.getItem(SESSION_KEY)) {{
            throw new Error('session key was not retained');
          }}
        }} catch (storageError) {{
          reveal(plaintext);
          status('Unlocked, but this browser could not retain the session key.', true);
          return;
        }}
        try {{
          reveal(plaintext);
        }} catch (displayError) {{
          status('Unlocked, but the page could not be displayed.', true);
        }}
      }}, 10);
    }}

    window.onload = function () {{
      var encodedKey;
      try {{ encodedKey = window.sessionStorage.getItem(SESSION_KEY); }} catch (ignore) {{}}
      if (encodedKey) {{
        try {{
          reveal(window.sjcl.json.decrypt(window.sjcl.codec.base64.toBits(encodedKey), CIPHERTEXT));
          return;
        }} catch (ignore) {{
          try {{ window.sessionStorage.removeItem(SESSION_KEY); }} catch (ignoreAgain) {{}}
        }}
      }}
      document.getElementById('passcode-form').onsubmit = function () {{
        unlock(document.getElementById('breviary-passcode').value);
        return false;
      }};
      document.getElementById('breviary-passcode').focus();
    }};
  }}());
  </script>"""


def english_session_script(
    ciphertext: dict,
    unlock_href: str,
    session_key: str = ENGLISH_SESSION_KEY,
) -> str:
    payload = json.dumps(json.dumps(ciphertext, separators=(",", ":")))
    return f"""  <script>
  (function () {{
    var CIPHERTEXT = {payload};
    var SESSION_KEY = {json.dumps(session_key)};
    var UNLOCK_HREF = {json.dumps(unlock_href)};

    function locked(message) {{
      var node = document.getElementById('decrypt-status');
      node.className = 'decrypt-status passcode-error';
      node.innerHTML = '';
      node.appendChild(document.createTextNode(message + ' '));
      var link = document.createElement('a');
      link.href = UNLOCK_HREF;
      link.appendChild(document.createTextNode('Open English Breviary'));
      node.appendChild(link);
    }}

    window.onload = function () {{
      var encodedKey;
      try {{ encodedKey = window.sessionStorage.getItem(SESSION_KEY); }} catch (ignore) {{}}
      if (!encodedKey) {{
        locked('Locked.');
        return;
      }}
      try {{
        var key = window.sjcl.codec.base64.toBits(encodedKey);
        document.getElementById('decrypt-status').style.display = 'none';
        document.getElementById('encrypted-content').innerHTML =
          window.sjcl.json.decrypt(key, CIPHERTEXT);
      }} catch (error) {{
        locked('The session key is no longer valid.');
      }}
    }};
  }}());
  </script>"""


def english_encrypted_shell(
    ciphertext: dict,
    css_href: str,
    *,
    unlock_page: bool,
    unlock_href: str,
    first_page: bool = False,
    session_key: str = ENGLISH_SESSION_KEY,
    body_class: str = "",
) -> str:
    sjcl_source = SJCL_PATH.read_text(encoding="utf-8").strip()
    if unlock_page:
        gate = (
            '<section id="passcode-gate" class="passcode-gate">'
            '<div class="passcode-ornament">✠</div>'
            '<h1>English Breviary</h1>'
            '<form id="passcode-form">'
            '<label for="breviary-passcode">Passcode</label>'
            '<input id="breviary-passcode" name="passcode" type="password" '
            'inputmode="numeric" pattern="[0-9]*" autocomplete="off">'
            '<button type="submit">Unlock</button>'
            '</form><p id="passcode-status" class="passcode-status">Enter the passcode to read.</p>'
            '</section>'
        )
        behavior = english_unlock_script(ciphertext, session_key)
    else:
        gate = '<p id="decrypt-status" class="decrypt-status">Opening...</p>'
        behavior = english_session_script(ciphertext, unlock_href, session_key)
    classes = "breviary-page breviary-encrypted"
    if first_page:
        classes += " breviary-first"
    if body_class:
        classes += f" {body_class}"
    return clean_output_html(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>English Breviary</title>
  <link rel="stylesheet" href="{html.escape(css_href, quote=True)}">
  <script>{sjcl_source}</script>
{behavior}
</head>
<body class="{classes}">
  <main>
    {gate}
    <div id="encrypted-content"></div>
  </main>
</body>
</html>
""")


def encrypt_english_pages(pages: list[dict[str, str]], passcode: str) -> dict[str, dict]:
    environment = os.environ.copy()
    environment[ENGLISH_BREVIARY_PASSCODE_ENV] = passcode
    result = subprocess.run(
        ["node", str(ENCRYPT_HELPER)],
        input=json.dumps({"pages": pages}),
        text=True,
        capture_output=True,
        check=True,
        env=environment,
        cwd=ROOT,
    )
    encoded = json.loads(result.stdout)
    return {page_id: json.loads(payload) for page_id, payload in encoded.items()}


def encrypted_shell_ciphertext(path: Path) -> str:
    """Read the already encrypted payload from one learner shell.

    The shell stores an encoded SJCL JSON string in ``var CIPHERTEXT``.  This
    parser deliberately reads only that assignment rather than evaluating any
    HTML or JavaScript from the downloaded Pages artifact.
    """
    source = path.read_text(encoding="utf-8")
    marker = "var CIPHERTEXT = "
    start = source.find(marker)
    if start < 0:
        raise LearnerLanguageError(f"Encrypted learner payload is missing in {path}")
    encoded = source[start + len(marker):].lstrip()
    try:
        payload, _ = json.JSONDecoder().raw_decode(encoded)
    except json.JSONDecodeError as error:
        raise LearnerLanguageError(f"Encrypted learner payload is invalid in {path}") from error
    if not isinstance(payload, str):
        raise LearnerLanguageError(f"Encrypted learner payload has an unexpected format in {path}")
    return payload


def learner_edition_profile_matches(learner_root: Path) -> bool:
    """Tell current IPA output from an older encrypted pronunciation edition."""
    index_path = learner_root / "index.html"
    try:
        shell = index_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(
        re.search(
            rf'class="[^"]*\b{re.escape(LEARNER_PROFILE_CLASS)}\b[^"]*"',
            shell,
        )
    )


def learner_edition_covers_date(learner_root: Path, date: datetime) -> bool:
    """Avoid relabelling yesterday's cached learner pages as today's Office."""
    return (learner_root / date_dir_name(date) / "index.html").is_file()


def decrypt_english_pages(pages: list[dict[str, str]], passcode: str) -> dict[str, str]:
    """Decrypt learner fragments in memory for an immediate local re-page."""
    environment = os.environ.copy()
    environment[ENGLISH_BREVIARY_PASSCODE_ENV] = passcode
    result = subprocess.run(
        ["node", str(DECRYPT_HELPER)],
        input=json.dumps({"pages": pages}),
        text=True,
        capture_output=True,
        check=True,
        env=environment,
        cwd=ROOT,
    )
    decoded = json.loads(result.stdout)
    if not all(isinstance(value, str) for value in decoded.values()):
        raise LearnerLanguageError("Decrypted learner payload has an unexpected format")
    return decoded


def learner_page_files(learner_root: Path, slug: str) -> list[Path]:
    """Return current-day encrypted learner pages for one Office in order."""
    pattern = re.compile(rf"^{re.escape(slug)}(?:-(\d+))?\.html$")
    indexed: list[tuple[int, Path]] = []
    for path in learner_root.glob(f"{slug}*.html"):
        match = pattern.fullmatch(path.name)
        if match:
            indexed.append((int(match.group(1) or 1), path))
    indexed.sort(key=lambda item: item[0])
    if not indexed or [number for number, _ in indexed] != list(range(1, len(indexed) + 1)):
        raise LearnerLanguageError(f"Cached learner pages are incomplete for {slug}")
    return [path for _, path in indexed]


def learner_body_from_decrypted_pages(plaintext_pages: list[str]) -> str:
    """Reassemble paired learner blocks without headers or bottom navigation."""
    blocks: list[str] = []
    glossary_open = False
    for plaintext in plaintext_pages:
        wrapper = fragment_soup(plaintext).find("div")
        if wrapper is None:
            continue
        # Select only canonical learner content, but at any depth.  This also
        # repairs the already deployed one-page cache where every row sits
        # inside an accidental neutral div.
        for child in wrapper.select("h2, h3, .learner-row"):
            classes = set(child.get("class", []))
            is_row = "learner-row" in classes
            is_heading = child.name in {"h2", "h3"}
            if is_heading and normalize_key(child.get_text(" ", strip=True)) == "words in this prayer":
                if not glossary_open:
                    blocks.append('<section class="learner-glossary">')
                    glossary_open = True
            blocks.append(str(child))
    if glossary_open:
        blocks.append("</section>")
    if not blocks:
        raise LearnerLanguageError("Cached learner edition did not contain paired reading rows")
    # Keep the same top-level shape produced by ``learner_prayer_body``.
    # ``paginate_learner_html`` treats every direct child as one indivisible
    # Kindle block; an extra wrapper would therefore collapse the entire
    # Office into a single page.
    return "\n".join(blocks)


def restore_english_learner_bodies(
    learner_root: Path, passcode: str, date: datetime
) -> dict[str, dict[str, str]]:
    """Reuse the cached language work while applying the current paginator.

    The cached edition contains Gemini's pronunciation and glossary results.
    We decrypt its current-day pages only inside the build process, join their
    paired rows back into each Office, and let ``write_english_learner`` encrypt
    them again after pagination.  No plaintext is written to disk.
    """
    index_path = learner_root / "index.html"
    if not index_path.is_file():
        raise LearnerLanguageError("Cached learner unlock page is missing")
    # The first unlock page derives the session key; every later page in this
    # edition is encrypted with that key so Kindle can open it without asking
    # for the passcode again.
    page_sources: list[dict[str, str]] = [
        {"id": "learner-root-index", "ciphertext": encrypted_shell_ciphertext(index_path)}
    ]
    prayer_pages: dict[str, list[str]] = {}
    for _, slug in ENGLISH_PRAYERS:
        page_ids: list[str] = []
        for page_index, path in enumerate(learner_page_files(learner_root, slug), start=1):
            page_id = f"{slug}-{page_index}"
            page_sources.append({"id": page_id, "ciphertext": encrypted_shell_ciphertext(path)})
            page_ids.append(page_id)
        prayer_pages[slug] = page_ids
    decrypted = decrypt_english_pages(page_sources, passcode)
    restored = {
        slug: learner_body_from_decrypted_pages([decrypted[page_id] for page_id in page_ids])
        for slug, page_ids in prayer_pages.items()
    }
    logging.info("Repaginated cached English learner content without calling Gemini")
    return {date_dir_name(date): restored}


def write_english_breviary(
    day_sites: list[EnglishDaySite],
    passcode: str,
    *,
    preserve_learner: bool = False,
    include_learner_link: bool = False,
) -> None:
    target_root = SITE_DIR / "breviary" / "en"
    updated = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M Vietnam time")
    available_dates = [site.date for site in day_sites]
    today = day_sites[len(day_sites) // 2]
    paginated = {
        date_dir_name(site.date): {
            prayer.slug: paginate_html(prayer.body_html) for prayer in site.prayers
        }
        for site in day_sites
    }

    documents: list[dict[str, str]] = []
    outputs: list[dict[str, object]] = []

    def add_document(
        page_id: str,
        path: Path,
        css_href: str,
        plaintext: str,
        *,
        unlock_page: bool = False,
        unlock_href: str = "index.html",
        first_page: bool = False,
    ) -> None:
        documents.append({"id": page_id, "html": plaintext})
        outputs.append(
            {
                "id": page_id,
                "path": path,
                "css_href": css_href,
                "unlock_page": unlock_page,
                "unlock_href": unlock_href,
                "first_page": first_page,
            }
        )

    add_document(
        "root-index",
        target_root / "index.html",
        "../../breviary.css?v=3-encrypted-en",
        english_index_inner(
            today,
            available_dates,
            updated,
            "",
            "learner/index.html" if include_learner_link else None,
        ),
        unlock_page=True,
    )

    def add_site_documents(site: EnglishDaySite, target_dir: Path, prefix: str, dated: bool) -> None:
        date_name = date_dir_name(site.date)
        css_href = "../../../breviary.css?v=3-encrypted-en" if dated else "../../breviary.css?v=3-encrypted-en"
        unlock_href = "../index.html" if dated else "index.html"
        if dated:
            add_document(
                f"{date_name}-index",
                target_dir / "index.html",
                css_href,
                english_index_inner(
                    site,
                    available_dates,
                    updated,
                    date_name,
                    f"../learner/{date_name}/index.html" if include_learner_link else None,
                ),
                unlock_href=unlock_href,
            )

        prayer_by_slug = {prayer.slug: prayer for prayer in site.prayers}
        ordered = [prayer_by_slug[slug] for _, slug in ENGLISH_PRAYERS]
        for prayer_index, prayer in enumerate(ordered):
            pages = paginated[date_name][prayer.slug]
            for page_index, page_body in enumerate(pages, start=1):
                previous_href = None
                next_href = None
                if page_index > 1:
                    previous_href = prayer_page_filename(prayer.slug, page_index - 1)
                elif prayer_index > 0:
                    previous = ordered[prayer_index - 1]
                    previous_href = prayer_page_filename(
                        previous.slug, len(paginated[date_name][previous.slug])
                    )
                if page_index < len(pages):
                    next_href = prayer_page_filename(prayer.slug, page_index + 1)
                elif prayer_index + 1 < len(ordered):
                    next_href = prayer_page_filename(ordered[prayer_index + 1].slug, 1)
                nav = english_breviary_nav_html(previous_href, next_href)
                plaintext = english_prayer_inner(
                    prayer,
                    site.liturgical_day,
                    page_body,
                    page_index,
                    len(pages),
                    nav,
                    updated,
                )
                page_id = f"{prefix}{prayer.slug}-{page_index}"
                add_document(
                    page_id,
                    target_dir / prayer_page_filename(prayer.slug, page_index),
                    css_href,
                    plaintext,
                    unlock_href=unlock_href,
                    first_page=page_index == 1,
                )

    for site in day_sites:
        add_site_documents(
            site,
            target_root / date_dir_name(site.date),
            f"{date_dir_name(site.date)}-",
            True,
        )
    add_site_documents(today, target_root, "root-", False)

    ciphertexts = encrypt_english_pages(documents, passcode)
    temporary = target_root.with_name("en.new")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    for output in outputs:
        relative = Path(output["path"]).relative_to(target_root)
        destination = temporary / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            english_encrypted_shell(
                ciphertexts[str(output["id"])],
                str(output["css_href"]),
                unlock_page=bool(output["unlock_page"]),
                unlock_href=str(output["unlock_href"]),
                first_page=bool(output["first_page"]),
            ),
            encoding="utf-8",
        )
    learner_hold = target_root.with_name("learner.hold")
    if learner_hold.exists():
        shutil.rmtree(learner_hold)
    if preserve_learner and (target_root / "learner").exists():
        (target_root / "learner").rename(learner_hold)
    if target_root.exists():
        shutil.rmtree(target_root)
    temporary.rename(target_root)
    if learner_hold.exists():
        learner_hold.rename(target_root / "learner")
        refresh_preserved_learner_stylesheet(target_root / "learner")
    logging.info("Generated %d encrypted English Breviary pages", len(outputs))


def refresh_preserved_learner_stylesheet(learner_root: Path) -> None:
    """Point preserved encrypted learner shells at the current local CSS.

    The learner HTML is cached between workflow runs so ordinary CSS-only
    deploys do not call Gemini.  Its outer shell is safe to update: the prayer
    text remains encrypted and untouched.
    """
    stylesheet = f"breviary.css?v={BREVIARY_CSS_VERSION}-encrypted-learner"
    for page in learner_root.rglob("*.html"):
        original = page.read_text(encoding="utf-8")
        updated = re.sub(
            r"breviary\.css\?v=\d+-encrypted-learner",
            stylesheet,
            original,
        )
        if updated != original:
            page.write_text(updated, encoding="utf-8")


def prepare_english_learner_bodies(
    day_sites: list[EnglishDaySite], language: LearnerLanguage
) -> dict[str, dict[str, str]]:
    prepared: list[tuple[str, str, Prayer, list[tuple[str, str]], str]] = []
    for site in day_sites:
        date_name = date_dir_name(site.date)
        for prayer in site.prayers:
            units = learner_source_units(prayer.body_html)
            source_text = " ".join(value for kind, value in units if kind == "sentence")
            prepared.append((date_name, prayer.slug, prayer, units, source_text))

    source_pronunciations = language.pronunciations(
        [value for _, _, _, units, _ in prepared for kind, value in units if kind == "sentence"]
    )
    glossary_by_prayer = language.glossaries(
        [(f"{date_name}/{slug}", prayer.title, source_text) for date_name, slug, prayer, _, source_text in prepared]
    )
    glossary_lines = [
        f"{item['term']} — {item['definition']}"
        for date_name, slug, _, _, _ in prepared
        for item in glossary_by_prayer[f"{date_name}/{slug}"]
    ]
    glossary_pronunciations = language.pronunciations(glossary_lines)

    learner_bodies: dict[str, dict[str, str]] = {}
    for date_name, slug, prayer, units, _ in prepared:
        glossary = glossary_by_prayer[f"{date_name}/{slug}"]
        learner_bodies.setdefault(date_name, {})[slug] = learner_prayer_body(
            prayer,
            language,
            units=units,
            pronunciations=source_pronunciations,
            glossary=glossary,
            glossary_guides=glossary_pronunciations,
        )
    language.save()
    return learner_bodies


def write_english_learner(
    day_sites: list[EnglishDaySite],
    passcode: str,
    learner_bodies: dict[str, dict[str, str]],
) -> None:
    """Write the separate paired-column learner edition after normal English."""
    target_root = SITE_DIR / "breviary" / "en" / "learner"
    updated = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M Vietnam time")
    available_dates = [site.date for site in day_sites]
    today = day_sites[len(day_sites) // 2]

    paginated = {
        date_name: {
            slug: paginate_learner_html(body) for slug, body in prayers.items()
        }
        for date_name, prayers in learner_bodies.items()
    }

    documents: list[dict[str, str]] = []
    outputs: list[dict[str, object]] = []

    def add_document(
        page_id: str,
        path: Path,
        css_href: str,
        plaintext: str,
        *,
        unlock_page: bool = False,
        unlock_href: str = "index.html",
        first_page: bool = False,
    ) -> None:
        documents.append({"id": page_id, "html": plaintext})
        outputs.append(
            {
                "id": page_id,
                "path": path,
                "css_href": css_href,
                "unlock_page": unlock_page,
                "unlock_href": unlock_href,
                "first_page": first_page,
            }
        )

    add_document(
        "learner-root-index",
        target_root / "index.html",
        f"../../../breviary.css?v={BREVIARY_CSS_VERSION}-encrypted-learner",
        learner_index_inner(today, available_dates, updated, ""),
        unlock_page=True,
    )

    def add_site_documents(site: EnglishDaySite, target_dir: Path, prefix: str, dated: bool) -> None:
        date_name = date_dir_name(site.date)
        css_href = (
            f"../../../../breviary.css?v={BREVIARY_CSS_VERSION}-encrypted-learner"
            if dated
            else f"../../../breviary.css?v={BREVIARY_CSS_VERSION}-encrypted-learner"
        )
        unlock_href = "../index.html" if dated else "index.html"
        if dated:
            add_document(
                f"learner-{date_name}-index",
                target_dir / "index.html",
                css_href,
                learner_index_inner(site, available_dates, updated, date_name),
                unlock_href=unlock_href,
            )

        prayer_by_slug = {prayer.slug: prayer for prayer in site.prayers}
        ordered = [prayer_by_slug[slug] for _, slug in ENGLISH_PRAYERS]
        for prayer_index, prayer in enumerate(ordered):
            pages = paginated[date_name][prayer.slug]
            for page_index, page_body in enumerate(pages, start=1):
                previous_href = None
                next_href = None
                if page_index > 1:
                    previous_href = prayer_page_filename(prayer.slug, page_index - 1)
                elif prayer_index > 0:
                    previous = ordered[prayer_index - 1]
                    previous_href = prayer_page_filename(
                        previous.slug, len(paginated[date_name][previous.slug])
                    )
                if page_index < len(pages):
                    next_href = prayer_page_filename(prayer.slug, page_index + 1)
                elif prayer_index + 1 < len(ordered):
                    next_href = prayer_page_filename(ordered[prayer_index + 1].slug, 1)
                nav = english_breviary_nav_html(previous_href, next_href)
                plaintext = learner_prayer_inner(
                    prayer,
                    site.liturgical_day,
                    page_body,
                    page_index,
                    len(pages),
                    nav,
                    updated,
                )
                add_document(
                    f"learner-{prefix}{prayer.slug}-{page_index}",
                    target_dir / prayer_page_filename(prayer.slug, page_index),
                    css_href,
                    plaintext,
                    unlock_href=unlock_href,
                    first_page=page_index == 1,
                )

    for site in day_sites:
        add_site_documents(
            site,
            target_root / date_dir_name(site.date),
            f"{date_dir_name(site.date)}-",
            True,
        )
    add_site_documents(today, target_root, "root-", False)

    ciphertexts = encrypt_english_pages(documents, passcode)
    temporary = target_root.with_name("learner.new")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    for output in outputs:
        relative = Path(output["path"]).relative_to(target_root)
        destination = temporary / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            english_encrypted_shell(
                ciphertexts[str(output["id"])],
                str(output["css_href"]),
                unlock_page=bool(output["unlock_page"]),
                unlock_href=str(output["unlock_href"]),
                first_page=bool(output["first_page"]),
                session_key=ENGLISH_LEARNER_SESSION_KEY,
                body_class=f"learner-page {LEARNER_PROFILE_CLASS}",
            ),
            encoding="utf-8",
        )
    if target_root.exists():
        shutil.rmtree(target_root)
    temporary.rename(target_root)
    logging.info("Generated %d encrypted English learner pages", len(outputs))


def build_english_breviary(run_date: datetime, passcode: str) -> None:
    if not re.fullmatch(r"\d{6}", passcode):
        raise ValueError(f"{ENGLISH_BREVIARY_PASSCODE_ENV} must contain exactly six digits")
    session = requests.Session()
    sites = [
        fetch_english_day(session, date)
        for date in (run_date - timedelta(days=1), run_date, run_date + timedelta(days=1))
    ]
    learner_api_key = os.environ.get(LEARNER_GEMINI_API_KEY_ENV, "")
    learner_root = SITE_DIR / "breviary" / "en" / "learner"
    existing_learner = learner_root.is_dir()
    learner_profile_current = existing_learner and learner_edition_profile_matches(learner_root)
    profile_refresh_required = existing_learner and not learner_profile_current
    refresh_learner = (
        os.environ.get(LEARNER_REFRESH_ENV, "").strip() == "1" or profile_refresh_required
    )
    learner_bodies: dict[str, dict[str, str]] | None = None
    learner_sites = [sites[1]]
    if profile_refresh_required:
        logging.info(
            "Encrypted learner profile is stale; refreshing %s",
            LEARNER_PRONUNCIATION_PROFILE,
        )
    try:
        if refresh_learner and learner_api_key:
            language = LearnerLanguage(learner_api_key)
            # The learner edition is intentionally today-only. It keeps the
            # paired Kindle layout focused on the current Office and, with the
            # Gemini free-tier request budget, avoids generating three complete
            # days of pronunciation and glossary material on every refresh.
            learner_bodies = prepare_english_learner_bodies(learner_sites, language)
        elif (
            existing_learner
            and learner_profile_current
            and learner_edition_covers_date(learner_root, learner_sites[0].date)
        ):
            # A same-day presentation-only deploy applies new pagination without
            # calling Gemini. Never relabel a prior day's encrypted content.
            learner_bodies = restore_english_learner_bodies(
                learner_root, passcode, learner_sites[0].date
            )
        elif existing_learner and learner_profile_current:
            logging.warning(
                "The cached English learner edition does not cover %s; preserving it until the scheduled refresh",
                date_dir_name(learner_sites[0].date),
            )
        elif learner_api_key:
            language = LearnerLanguage(learner_api_key)
            learner_bodies = prepare_english_learner_bodies(learner_sites, language)
        elif existing_learner:
            logging.warning(
                "The encrypted learner edition uses an older pronunciation profile; preserving it "
                "until %s is configured",
                LEARNER_GEMINI_API_KEY_ENV,
            )
        else:
            logging.warning(
                "%s is not configured; preserving the last English learner edition",
                LEARNER_GEMINI_API_KEY_ENV,
            )
    except Exception as error:
        logging.exception(
            "English learner refresh failed; preserving the last successfully deployed learner edition"
        )
        github_actions_warning("English learner refresh degraded", str(error))
        learner_bodies = None
    write_english_breviary(
        sites,
        passcode,
        # Keep the old learner tree until its complete replacement is ready.
        # This also makes a failure in write_english_learner atomic.
        preserve_learner=existing_learner,
        include_learner_link=learner_bodies is not None or existing_learner,
    )
    if learner_bodies is not None:
        try:
            write_english_learner(learner_sites, passcode, learner_bodies)
        except Exception as error:
            logging.exception(
                "English learner write failed; preserving the last successfully deployed learner edition"
            )
            github_actions_warning("English learner publish degraded", str(error))


def update_english_breviary_optional(run_date: datetime, passcode: str) -> bool:
    """Refresh English editions without allowing them to block the Vietnamese core."""
    try:
        build_english_breviary(run_date, passcode)
    except Exception as error:
        logging.exception(
            "English Breviary update failed; preserving the last successfully deployed English edition"
        )
        github_actions_warning("English Breviary refresh degraded", str(error))
        return False
    return True


DEBUG_PROSE = (
    "Các ngài đã giải thích rõ hơn về sự kiện đó, dựa vào những lý lẽ sâu sắc "
    "để trình bày ý nghĩa và bản chất của sự kiện, nhất là cho mọi người nhận ra "
    "tình thương của Thiên Chúa vẫn luôn dẫn dắt dân Người qua mọi thử thách. "
    "Nhờ lòng tin và niềm hy vọng, chúng ta được mời gọi bước đi trong bình an, "
    "biết nâng đỡ nhau và cùng hướng lòng về quê trời vĩnh cửu."
)

DEBUG_VERSE_LINES = [
    "Xin dẫn con bước trong bình an,",
    "giữa bao thử thách của cuộc đời.",
    "Xin cho con vững lòng trông cậy,",
    "và luôn trung tín bước theo Ngài.",
]


def debug_prose(word_count: int) -> str:
    source_words = DEBUG_PROSE.split()
    words = [source_words[index % len(source_words)] for index in range(word_count)]
    text = " ".join(words)
    return text[0].upper() + text[1:] + "."


def debug_verse(line_count: int) -> str:
    lines = []
    for index in range(line_count):
        line = DEBUG_VERSE_LINES[index % len(DEBUG_VERSE_LINES)]
        lines.append(f'<span class="verse-line"><span>{html.escape(line)}</span></span>')
    return '<p class="stanza">' + "".join(lines) + "</p>"


def debug_production_verse(line_count: int) -> str:
    """Render verse blocks exactly as html_blocks() emits production pages."""
    paragraphs: list[str] = []
    for start in range(0, line_count, 2):
        block_lines = [
            DEBUG_VERSE_LINES[index % len(DEBUG_VERSE_LINES)]
            for index in range(start, min(start + 2, line_count))
        ]
        verse_body = "<br/>".join(html.escape(line) for line in block_lines)
        paragraphs.append(
            '<p><span class="verse-line"><span>' + verse_body + "</span></span></p>"
        )
    return "".join(paragraphs)


def debug_explicit_lines(line_count: int) -> str:
    lines = [f"Dòng chuẩn {index:02d} - xin ban bình an." for index in range(1, line_count + 1)]
    return '<p class="debug-line-stack">' + "<br>".join(html.escape(line) for line in lines) + "</p>"


def debug_patterns() -> list[DebugPattern]:
    patterns: list[DebugPattern] = []
    prose_word_counts = (45, 55, 65, 75, 85, 95, 105, 115, 130, 145, 160, 175, 190)
    for index, word_count in enumerate(prose_word_counts, start=1):
        patterns.append(
            DebugPattern(
                f"P{index:02d}",
                f"Văn xuôi {word_count} từ",
                "Đo khả năng chứa đoạn văn xuôi liên tục.",
                f"<p>{html.escape(debug_prose(word_count))}</p>",
            )
        )

    verse_patterns = (
        ("V01", 8),
        ("V02", 10),
        ("V03", 12),
        ("V04", 14),
        ("V07", 15),
        ("V05", 16),
        ("V06", 18),
    )
    for code, line_count in verse_patterns:
        patterns.append(
            DebugPattern(
                code,
                f"Thơ {line_count} dòng",
                (
                    "Mẫu bổ sung để xác nhận ranh giới giữa V04 và V05."
                    if code == "V07"
                    else "Đo dòng thơ dùng cấu trúc verse-line của production."
                ),
                debug_verse(line_count),
            )
        )

    for index, line_count in enumerate((12, 14, 15, 16), start=1):
        patterns.append(
            DebugPattern(
                f"R{index:02d}",
                f"Thơ production {line_count} dòng",
                "Mỗi cặp dòng nằm trong một thẻ p riêng, giống HTML sau phân trang.",
                debug_production_verse(line_count),
            )
        )

    algorithm_pages = [
        ("văn xuôi", page)
        for page in paginate_html(f'<p>{html.escape(debug_prose(420))}</p>')[:2]
    ] + [
        ("thơ production", page)
        for page in paginate_html(debug_production_verse(40))[:2]
    ]
    for index, (content_type, body) in enumerate(algorithm_pages, start=1):
        units = page_units(html_blocks(body))
        patterns.append(
            DebugPattern(
                f"A{index:02d}",
                f"Thuật toán chọn {content_type} ({units:.1f} đơn vị)",
                "Nội dung trang này được tạo trực tiếp bởi paginate_html().",
                body,
            )
        )

    mixed_bodies = [
        (
            "Điệp ca và ca vịnh ngắn",
            '<p class="antiphon"><span class="pre">ĐC:</span> '
            '<span class="body">Xin dẫn con bước trong bình an.</span></p>'
            + debug_verse(6),
        ),
        (
            "Tiêu đề, ghi chú và ca vịnh",
            '<p class="indexing">Tv 23 (24)</p>'
            '<p class="title">Chúa làm chủ trái đất cùng muôn vật muôn loài</p>'
            '<p class="note">Cửa trời rộng mở đón Chúa Ki-tô hiển trị.</p>'
            + debug_verse(6),
        ),
        (
            "Điệp ca, tiêu đề và 8 dòng",
            '<p class="antiphon"><span class="pre">ĐC:</span> '
            '<span class="body">Lạy Nữ Vương tinh khiết vẹn toàn.</span></p>'
            '<p class="indexing">Tv 45 (46)</p>'
            '<p class="title">Chúa là nơi ẩn náu và sức mạnh của người tín hữu</p>'
            + debug_verse(8),
        ),
        (
            "Heading và văn xuôi",
            '<h2>Lời Chúa</h2>'
            f'<p>{html.escape(debug_prose(70))}</p>',
        ),
        (
            "Hai đoạn văn xuôi",
            f'<p>{html.escape(debug_prose(48))}</p>'
            f'<p>{html.escape(debug_prose(58))}</p>',
        ),
        (
            "Cấu trúc hỗn hợp dài",
            '<p class="antiphon"><span class="pre">ĐC:</span> '
            '<span class="body">Xin dẫn con bước trong bình an.</span></p>'
            '<p class="indexing">Tv 23 (24)</p>'
            '<p class="title">Chúa làm chủ trái đất cùng muôn vật muôn loài</p>'
            '<p class="note">Cửa trời rộng mở đón Chúa Ki-tô hiển trị.</p>'
            + debug_verse(8),
        ),
    ]
    for index, (title, body) in enumerate(mixed_bodies, start=1):
        patterns.append(DebugPattern(f"M{index:02d}", title, "Đo margin và kiểu chữ hỗn hợp.", body))

    for index, line_count in enumerate(range(10, 18), start=1):
        patterns.append(
            DebugPattern(
                f"B{index:02d}",
                f"Ranh giới {line_count} dòng",
                "Mỗi mẫu tăng đúng một dòng ngắn để tìm ngưỡng an toàn của nav.",
                debug_explicit_lines(line_count),
            )
        )
    return patterns


def debug_metrics_script() -> str:
    return """  <script>
  window.onload = function () {
    var output = document.getElementById('debug-metrics-output');
    var main = document.getElementsByTagName('main')[0];
    var navs = document.getElementsByTagName('nav');
    var nav = navs.length ? navs[navs.length - 1] : null;
    var root = document.documentElement;
    var body = document.body;
    var lines = [];
    function add(name, value) { lines.push(name + ': ' + value); }
    add('userAgent', navigator.userAgent);
    add('screen', screen.width + ' x ' + screen.height);
    add('screen.avail', screen.availWidth + ' x ' + screen.availHeight);
    add('window.inner', window.innerWidth + ' x ' + window.innerHeight);
    add('document.client', root.clientWidth + ' x ' + root.clientHeight);
    add('document.scroll', root.scrollWidth + ' x ' + root.scrollHeight);
    add('devicePixelRatio', window.devicePixelRatio || 'không hỗ trợ');
    add('body.scroll', body.scrollWidth + ' x ' + body.scrollHeight);
    add('main.offset', main.offsetWidth + ' x ' + main.offsetHeight);
    if (nav) {
      add('nav.offsetTop', nav.offsetTop);
      add('nav.offsetHeight', nav.offsetHeight);
      if (nav.getBoundingClientRect) {
        var rect = nav.getBoundingClientRect();
        add('nav.rect', Math.round(rect.top) + ' .. ' + Math.round(rect.bottom));
        add('nav.bottomGap', Math.round((window.innerHeight || root.clientHeight) - rect.bottom));
      }
    }
    output.innerHTML = '';
    output.appendChild(document.createTextNode(lines.join('\\n')));
  };
  </script>"""


def debug_encrypted_breviary_script() -> str:
    """Return a dependency-free Web Crypto compatibility test for old Kindle browsers."""
    return """  <script>
  (function () {
    var SALT = 'Z9IDpoZ/eci4SC2KT0NvlQ==';
    var IV = '3rIF1ha90QVHgVhA';
    var CIPHERTEXT = 'CwMnvwdEkncrs9ZhSfScfsVkkv2DKnrKJYGQL/XHLmzc4dzHrqK8DwLrKrcqF9f4g95Zx362OHJljk5jRzlRYYJ85Peh2hGi5MOMSUeETGV8O7GN3PtACMaC9A6pV/JU3yjHC+du+wcCvz/Qh2wNNfXW26LavT2iYDjKlXoZl+RpKoYVG5IIutnrue6CKmVTCOM3p6rWN571ppxegFfZbsmeZ+3V/Fkp+vp3rgzrdS0KvuGgC46RR8PINz4a52gWO0xILJTdleaiTsAwunX/yb2W6QKQnIeqs5yO/+91YIzxA7n2Bt+0yKR+ZyspKIIxWIVcGvI4+jHxQq+FRHZLOk87oFDljIs8GM5gWNWopyF8Hks8Pjxv1ks4GK4oKxvM8rOJOvl9crDxvQM3eK3yuZJkNNTL8Cd0IMJc1/sXBWkkt0ToT797Cn4N/QDGT5Pytgila0TIg4sOMhnUzfMK8pMS7NjJdn/SpqDv2VPPbOUzVFK3gNWCsATMtjVtxgRcKMKv9wRJqnYXGJg5IWjtzHXxNi5ICNuUm56iNO6GUYRkSht/4Wouwc7P';
    var ITERATIONS = 50000;

    function bytesFromBase64(value) {
      var binary = window.atob(value);
      var bytes = new Uint8Array(binary.length);
      var index;
      for (index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      return bytes;
    }

    function utf8Bytes(value) {
      var encoded = unescape(encodeURIComponent(value));
      var bytes = new Uint8Array(encoded.length);
      var index;
      for (index = 0; index < encoded.length; index += 1) {
        bytes[index] = encoded.charCodeAt(index);
      }
      return bytes;
    }

    function utf8Text(buffer) {
      var bytes = new Uint8Array(buffer);
      var encoded = '';
      var index;
      for (index = 0; index < bytes.length; index += 1) {
        encoded += String.fromCharCode(bytes[index]);
      }
      return decodeURIComponent(escape(encoded));
    }

    function showStatus(message, isError) {
      var status = document.getElementById('passcode-status');
      status.className = isError ? 'passcode-status passcode-error' : 'passcode-status';
      status.innerHTML = '';
      status.appendChild(document.createTextNode(message));
    }

    function unlock(passcode) {
      var cryptoObject = window.crypto || window.msCrypto;
      var started = new Date().getTime();
      if (!cryptoObject || !cryptoObject.subtle || !window.Promise || !window.Uint8Array) {
        showStatus('UNSUPPORTED: Trình duyệt này không có Web Crypto AES-GCM.', true);
        return;
      }
      showStatus('Đang kiểm tra và giải mã...', false);
      cryptoObject.subtle.importKey(
        'raw', utf8Bytes(passcode), {name: 'PBKDF2'}, false, ['deriveKey']
      ).then(function (baseKey) {
        return cryptoObject.subtle.deriveKey(
          {name: 'PBKDF2', salt: bytesFromBase64(SALT), iterations: ITERATIONS, hash: 'SHA-256'},
          baseKey,
          {name: 'AES-GCM', length: 256},
          false,
          ['decrypt']
        );
      }).then(function (key) {
        return cryptoObject.subtle.decrypt(
          {name: 'AES-GCM', iv: bytesFromBase64(IV), tagLength: 128},
          key,
          bytesFromBase64(CIPHERTEXT)
        );
      }).then(function (plaintext) {
        var elapsed = new Date().getTime() - started;
        document.getElementById('passcode-gate').style.display = 'none';
        document.getElementById('encrypted-content').innerHTML = utf8Text(plaintext);
        document.getElementById('decrypt-result').innerHTML = '';
        document.getElementById('decrypt-result').appendChild(
          document.createTextNode('PASS - giải mã trong ' + elapsed + ' ms')
        );
      }).catch(function () {
        showStatus('Passcode không đúng hoặc trình duyệt không giải mã được.', true);
        document.getElementById('breviary-passcode').value = '';
        document.getElementById('breviary-passcode').focus();
      });
    }

    window.onload = function () {
      var form = document.getElementById('passcode-form');
      form.onsubmit = function () {
        unlock(document.getElementById('breviary-passcode').value);
        return false;
      };
      document.getElementById('breviary-passcode').focus();
    };
  }());
  </script>"""


def debug_legacy_encrypted_breviary_script() -> str:
    """Embed SJCL so the legacy Kindle test adds no runtime HTTP request."""
    sjcl_source = SJCL_PATH.read_text(encoding="utf-8").strip()
    encrypted_payload = (
        '{"iv":"6CYwGxW/D8PUepvb","v":1,"iter":2000,"ks":256,"ts":128,'
        '"mode":"ccm","adata":"","cipher":"aes",'
        '"salt":"oS2HfbDIGUXWJAqxJh1N+g==",'
        '"ct":"hOCpCYJJyt0KGilY5bF0FN709Vv/Lf8X881yue+nrGKQqqducXd3G+Mt2g+To1Qt3Vt2ceF0lBFnl9Xq6j7V358ashxK3mn7D+0Jnj5ipI1qbKDOzCTVOG4opvP3x8HKeFN5wqYxkBAo2Cr694t7c/fAHwQ6Q5u8YpfyVCdhZe3nt34Y4CVYl0NdIWHPQPhI9K/8unJv3K4nlF6EiV24PH4U4K0bX1KkmUqhwNvTKE9j4o9Fo5OlDRtdTf+gQnr17jkYVew0mycLhtLQNVyctjbT6mfUVANVj3tUvqL/v8A1AJAlmgQYMdl8IqHSlnYTOx/FHDYGjn8pMc432aJT85zcxjKIYdIsacQHyilvRk83AY+rYawLYdzdsmOzU8Yb9K74u1NlhbWrJYTe1FFbzV44AqZRCGXsJaVmYp0VwvvQdkO+X0OV8pusXgelSvW7KyaM8j6lpyiVoNCgdrmk8cvTe2d4TzYj22sFeE3WFHXLxFf2Yl5bTkhoRXNhWMDaWCbTuirJgVbRWlH9ZstUpukkD16p72Yn2W9kfUif7kd2IG8bk0nPfAZsOcqJwxnDe8A/2vynw1R3Jk9sBODsgaA="}'
    )
    return f"""  <script>
{sjcl_source}
  </script>
  <script>
  (function () {{
    var CIPHERTEXT = {json.dumps(encrypted_payload)};
    var SESSION_KEY = 'breviary-debug-key-v1';

    function showStatus(message, isError) {{
      var status = document.getElementById('passcode-status');
      status.className = isError ? 'passcode-status passcode-error' : 'passcode-status';
      status.innerHTML = '';
      status.appendChild(document.createTextNode(message));
    }}

    function unlock(passcode) {{
      var started = new Date().getTime();
      if (!window.sjcl || !window.sjcl.decrypt) {{
        showStatus('UNSUPPORTED: Không tải được bộ giải mã JavaScript cũ.', true);
        return;
      }}
      showStatus('Đang kiểm tra và giải mã...', false);
      window.setTimeout(function () {{
        var details = {{}};
        var plaintext;
        try {{
          plaintext = window.sjcl.json.decrypt(passcode, CIPHERTEXT, {{}}, details);
        }} catch (error) {{
          showStatus('Passcode không đúng hoặc Kindle không giải mã được AES-CCM.', true);
          document.getElementById('breviary-passcode').value = '';
          document.getElementById('breviary-passcode').focus();
          return;
        }}
        try {{
          if (!window.sessionStorage) {{ throw new Error('sessionStorage unavailable'); }}
          window.sessionStorage.setItem(
            SESSION_KEY,
            window.sjcl.codec.base64.fromBits(details.key)
          );
          if (!window.sessionStorage.getItem(SESSION_KEY)) {{
            throw new Error('session key was not retained');
          }}
        }} catch (storageError) {{
          showStatus('PASS AES-CCM, nhưng Kindle không lưu được khóa phiên.', true);
          return;
        }}
        var elapsed = new Date().getTime() - started;
        document.getElementById('passcode-gate').style.display = 'none';
        document.getElementById('encrypted-content').innerHTML = plaintext;
        document.getElementById('continue-link').style.display = 'block';
        document.getElementById('decrypt-result').innerHTML = '';
        document.getElementById('decrypt-result').appendChild(
          document.createTextNode('PASS LEGACY + SESSION - giải mã trong ' + elapsed + ' ms')
        );
      }}, 10);
    }}

    window.onload = function () {{
      var form = document.getElementById('passcode-form');
      form.onsubmit = function () {{
        unlock(document.getElementById('breviary-passcode').value);
        return false;
      }};
      document.getElementById('breviary-passcode').focus();
    }};
  }}());
  </script>"""


def debug_legacy_session_page_script() -> str:
    """Decrypt a second page with the derived key retained by sessionStorage."""
    sjcl_source = SJCL_PATH.read_text(encoding="utf-8").strip()
    encrypted_payload = (
        '{"iv":"N6jkPUwZzIPdZbdK","v":1,"iter":2000,"ks":256,"ts":128,'
        '"mode":"ccm","adata":"","cipher":"aes",'
        '"salt":"oS2HfbDIGUXWJAqxJh1N+g==",'
        '"ct":"9OXBzWa3jCVnRsm4qnMEiiF0e/j1CGPTg/blP6tR75uuPy98MYD645QVA5vPWrTO7bQId0NDD0en870wTA6dW7wf2tK4VrsxcYds2kljyfXHRGfDQvKHHMXfGZIusQegPQxN8lzZRs2/87DOKUMj49dx7mKwFciE/38fVr38A1ZgYyo5NWOMBtmGk3XnYtBdH8k9WoW6NIH+lSbRnH8rUYaF3KIlsZaGJAgn9ntWlNAQZvGK2G82Y32ubugvZDjItPo7+1W1xtpJB6EGQffmt4Z9TdzV8rlMLHQn51facv/QeJFPW005i5XDsUSD349MKsV4QIBfXDydF7LVUUVizBWQo7LQ1uuYAU71cC3FpyQntgwr0nW62p+jOvkY9GyOi+WnOuVVnrMD+iQ6vqRLz8FfM2PEGSb+3b9xHMaDj5GplDOMtQ=="}'
    )
    return f"""  <script>
{sjcl_source}
  </script>
  <script>
  (function () {{
    var CIPHERTEXT = {json.dumps(encrypted_payload)};
    var SESSION_KEY = 'breviary-debug-key-v1';

    function showFailure(message) {{
      var status = document.getElementById('session-status');
      status.className = 'passcode-status passcode-error';
      status.innerHTML = '';
      status.appendChild(document.createTextNode(message));
      document.getElementById('return-to-unlock').style.display = 'block';
    }}

    window.onload = function () {{
      var started = new Date().getTime();
      var encodedKey;
      try {{
        if (!window.sessionStorage) {{ throw new Error('sessionStorage unavailable'); }}
        encodedKey = window.sessionStorage.getItem(SESSION_KEY);
      }} catch (storageError) {{
        showFailure('UNSUPPORTED: Kindle không đọc được khóa phiên.');
        return;
      }}
      if (!encodedKey) {{
        showFailure('LOCKED: Chưa có khóa phiên; hãy mở khóa ở trang đầu.');
        return;
      }}
      try {{
        var key = window.sjcl.codec.base64.toBits(encodedKey);
        var plaintext = window.sjcl.json.decrypt(key, CIPHERTEXT);
        var elapsed = new Date().getTime() - started;
        document.getElementById('session-status').innerHTML = '';
        document.getElementById('session-status').appendChild(
          document.createTextNode('PASS SESSION - tự giải mã trong ' + elapsed + ' ms')
        );
        document.getElementById('encrypted-content').innerHTML = plaintext;
      }} catch (error) {{
        showFailure('FAILED: Khóa phiên có mặt nhưng không giải mã được trang thứ hai.');
      }}
    }};
  }}());
  </script>"""


def write_debug_site() -> None:
    debug_dir = SITE_DIR / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    for path in debug_dir.glob("*.html"):
        path.unlink()

    patterns = debug_patterns()
    groups = [
        ("Văn xuôi", [pattern for pattern in patterns if pattern.code.startswith("P")]),
        ("Thơ và ca vịnh", [pattern for pattern in patterns if pattern.code.startswith("V")]),
        ("Thơ đúng cấu trúc production", [pattern for pattern in patterns if pattern.code.startswith("R")]),
        ("Trang do thuật toán mới chọn", [pattern for pattern in patterns if pattern.code.startswith("A")]),
        ("Cấu trúc hỗn hợp", [pattern for pattern in patterns if pattern.code.startswith("M")]),
        ("Tìm ranh giới nav", [pattern for pattern in patterns if pattern.code.startswith("B")]),
    ]
    sections = [
        '<section class="debug-intro">'
        '<p>Mở trang thông số trước, sau đó thử các mẫu. Không cuộn trang trước khi chụp ảnh.</p>'
        '<p><a href="metrics.html">Đo thông số trình duyệt Kindle</a></p>'
        '<p><a href="encrypted-breviary.html">Thử mở Breviary bằng passcode</a></p>'
        '<p><a href="encrypted-breviary-legacy.html">Thử passcode bản Kindle cũ (AES-CCM)</a></p>'
        '</section>'
    ]
    for heading, group in groups:
        items = "".join(
            f'<li><a href="{pattern.filename}"><strong>{pattern.code}</strong> - '
            f'{html.escape(pattern.title)}</a></li>'
            for pattern in group
        )
        sections.append(f'<h2>{html.escape(heading)}</h2><section class="home-list"><ul>{items}</ul></section>')
    (debug_dir / "index.html").write_text(
        page_shell(
            "Kindle Pagination Debug",
            "\n".join(sections),
            "",
            "",
            show_metadata=False,
            css_href="../style.css?debug=2",
            bottom_nav='<nav class="page-nav"><a href="../index.html">Về site</a></nav>',
            body_class="debug-index",
        ),
        encoding="utf-8",
    )

    metrics_nav = page_nav_html(patterns[-1].filename, patterns[0].filename, 1, 1, "index.html")
    metrics_body = (
        '<h2>Thông số trình duyệt</h2>'
        '<p class="note">Chờ vài giây rồi chụp toàn bộ phần số bên dưới. Có thể cuộn để chụp đủ trang này.</p>'
        '<pre id="debug-metrics-output" class="debug-metrics-output">Đang đo...</pre>'
    )
    (debug_dir / "metrics.html").write_text(
        page_shell(
            "DEBUG METRICS",
            metrics_body,
            "",
            "",
            show_metadata=False,
            show_title=False,
            page_note="DEBUG METRICS - thông số thiết bị",
            css_href="../style.css?debug=2",
            extra_head=debug_metrics_script(),
            bottom_nav=metrics_nav,
            body_class="debug-page debug-metrics",
        ),
        encoding="utf-8",
    )

    encrypted_body = (
        '<section id="passcode-gate" class="passcode-gate">'
        '<div class="passcode-ornament">✠</div>'
        '<h1>ENGLISH BREVIARY</h1>'
        '<p class="note">AES-GCM compatibility test for Kindle Paperwhite 3</p>'
        '<form id="passcode-form">'
        '<label for="breviary-passcode">Passcode</label>'
        '<input id="breviary-passcode" name="passcode" type="password" inputmode="numeric" '
        'autocomplete="off" maxlength="32">'
        '<button type="submit">Unlock</button>'
        '</form>'
        '<p id="passcode-status" class="passcode-status">Nhập passcode để mở nội dung mẫu.</p>'
        '</section>'
        '<p id="decrypt-result" class="decrypt-result"></p>'
        '<section id="encrypted-content"></section>'
    )
    encrypted_nav = '<nav class="page-nav"><a href="index.html">Về Debug</a></nav>'
    (debug_dir / "encrypted-breviary.html").write_text(
        page_shell(
            "Encrypted English Breviary Test",
            encrypted_body,
            "",
            "",
            show_metadata=False,
            show_title=False,
            css_href="../breviary.css?v=3-debug-passcode",
            extra_head=debug_encrypted_breviary_script(),
            bottom_nav=encrypted_nav,
            body_class="breviary-page debug-passcode-page",
        ),
        encoding="utf-8",
    )

    session_body = (
        '<p id="session-status" class="decrypt-result">Đang tìm khóa phiên...</p>'
        '<section id="encrypted-content"></section>'
        '<p id="return-to-unlock" class="session-next" style="display:none">'
        '<a href="encrypted-breviary-legacy.html">‹ Trở lại trang mở khóa</a></p>'
    )
    (debug_dir / "encrypted-breviary-session-2.html").write_text(
        page_shell(
            "Encrypted Breviary Session Page Two",
            session_body,
            "",
            "",
            show_metadata=False,
            show_title=False,
            css_href="../breviary.css?v=5-debug-session",
            extra_head=debug_legacy_session_page_script(),
            bottom_nav=encrypted_nav,
            body_class="breviary-page debug-passcode-page",
        ),
        encoding="utf-8",
    )

    legacy_body = (
        '<section id="passcode-gate" class="passcode-gate">'
        '<div class="passcode-ornament">✠</div>'
        '<h1>ENGLISH BREVIARY</h1>'
        '<p class="note">Pure JavaScript AES-CCM test for legacy Kindle</p>'
        '<form id="passcode-form">'
        '<label for="breviary-passcode">Passcode</label>'
        '<input id="breviary-passcode" name="passcode" type="password" inputmode="numeric" '
        'autocomplete="off" maxlength="32">'
        '<button type="submit">Unlock</button>'
        '</form>'
        '<p id="passcode-status" class="passcode-status">Nhập passcode để mở nội dung mẫu.</p>'
        '</section>'
        '<p id="decrypt-result" class="decrypt-result"></p>'
        '<section id="encrypted-content"></section>'
        '<p id="continue-link" class="session-next" style="display:none">'
        '<a href="encrypted-breviary-session-2.html">Sang trang mã hóa thứ hai ›</a></p>'
    )
    (debug_dir / "encrypted-breviary-legacy.html").write_text(
        page_shell(
            "Legacy Encrypted English Breviary Test",
            legacy_body,
            "",
            "",
            show_metadata=False,
            show_title=False,
            css_href="../breviary.css?v=4-debug-passcode-legacy",
            extra_head=debug_legacy_encrypted_breviary_script(),
            bottom_nav=encrypted_nav,
            body_class="breviary-page debug-passcode-page",
        ),
        encoding="utf-8",
    )

    for index, pattern in enumerate(patterns):
        previous_pattern = patterns[index - 1] if index > 0 else patterns[-1]
        next_pattern = patterns[index + 1] if index + 1 < len(patterns) else patterns[0]
        nav = page_nav_html(previous_pattern.filename, next_pattern.filename, index + 1, len(patterns), "index.html")
        (debug_dir / pattern.filename).write_text(
            page_shell(
                f"DEBUG {pattern.code}",
                pattern.body_html,
                "",
                "",
                show_metadata=False,
                show_title=False,
                page_note=f"DEBUG {pattern.code} - {pattern.title}",
                css_href="../style.css?debug=2",
                bottom_nav=nav,
                body_class=f"debug-page debug-{pattern.code.lower()}",
            ),
            encoding="utf-8",
        )


def write_site(day_sites: list[DaySite]) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    write_breviary_stylesheet()
    available_date_names = {date_dir_name(site.date) for site in day_sites}
    for path in SITE_DIR.iterdir():
        if (
            path.is_dir()
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name)
            and path.name not in available_date_names
        ):
            shutil.rmtree(path)
    error_page = SITE_DIR / "error.html"
    if error_page.exists():
        error_page.unlink()
    for _, slug in PRAYERS:
        for path in SITE_DIR.glob(f"{slug}*.html"):
            path.unlink()
    for site in day_sites:
        day_dir = SITE_DIR / date_dir_name(site.date)
        if day_dir.exists():
            for path in day_dir.glob("*.html"):
                path.unlink()
    breviary_dir = SITE_DIR / "breviary"
    if breviary_dir.exists():
        for path in breviary_dir.iterdir():
            if (
                path.is_dir()
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name)
                and path.name not in available_date_names
            ):
                shutil.rmtree(path)

    updated = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M giờ Việt Nam")
    available_dates = [site.date for site in day_sites]
    today = day_sites[len(day_sites) // 2]
    paginated_by_date = {
        date_dir_name(site.date): {
            prayer.slug: paginate_html(prayer.body_html) for prayer in site.prayers
        }
        for site in day_sites
    }
    for site in day_sites:
        date_name = date_dir_name(site.date)
        write_day_site(
            SITE_DIR / date_name,
            "../style.css",
            site.prayers,
            site.liturgical_day,
            site.date,
            available_dates,
            updated,
            date_name,
            paginated_by_date[date_name],
        )
        write_breviary_day_site(
            SITE_DIR / "breviary" / date_name,
            f"../../breviary.css?v={BREVIARY_CSS_VERSION}",
            site.prayers,
            site.liturgical_day,
            site.date,
            available_dates,
            updated,
            date_name,
            paginated_by_date[date_name],
        )

    write_day_site(
        SITE_DIR,
        "style.css",
        today.prayers,
        today.liturgical_day,
        today.date,
        available_dates,
        updated,
        "",
        paginated_by_date[date_dir_name(today.date)],
    )
    write_breviary_day_site(
        SITE_DIR / "breviary",
        f"../breviary.css?v={BREVIARY_CSS_VERSION}",
        today.prayers,
        today.liturgical_day,
        today.date,
        available_dates,
        updated,
        "",
        paginated_by_date[date_dir_name(today.date)],
    )
    write_debug_site()


def breviary_snapshot_html(
    source: str,
    *,
    body_class: str,
    css_href: str,
    original_index_href: str | None = None,
) -> str:
    """Apply the Breviary shell while leaving the paginated content untouched."""
    result = re.sub(
        r'(<link rel="stylesheet" href=")[^"]+("[^>]*>)',
        rf"\g<1>{css_href}\2",
        source,
        count=1,
    )
    result = result.replace("<body>", f'<body class="{body_class}">', 1)
    result = result.replace(
        'class="page-nav paged-nav"',
        'class="page-nav paged-nav breviary-nav"',
    )
    result = result.replace("&#9664;", "&#8249;").replace("&#9654;", "&#8250;")
    if original_index_href is not None:
        result = re.sub(
            r'<p class="kindle-note">.*?</p>',
            '<p class="kindle-note">Monastic Breviary · bản tối giản dành cho Kindle.</p>',
            result,
            count=1,
            flags=re.DOTALL,
        )
        result = re.sub(
            r'<p class="mode-switch">.*?</p>',
            f'<p class="mode-switch"><a href="{original_index_href}">Trở về bản Kindle</a></p>',
            result,
            count=1,
            flags=re.DOTALL,
        )
    return result


def write_breviary_snapshot() -> None:
    """Create /breviary from committed pages without fetching or touching root."""
    write_breviary_stylesheet()
    target_root = SITE_DIR / "breviary"
    if target_root.exists():
        shutil.rmtree(target_root)

    source_roots = [SITE_DIR]
    source_roots.extend(
        sorted(
            path
            for path in SITE_DIR.iterdir()
            if path.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name)
        )
    )
    for source_root in source_roots:
        is_dated = source_root != SITE_DIR
        target_dir = target_root / source_root.name if is_dated else target_root
        target_dir.mkdir(parents=True, exist_ok=True)
        css_href = (
            f"../../breviary.css?v={BREVIARY_CSS_VERSION}"
            if is_dated
            else f"../breviary.css?v={BREVIARY_CSS_VERSION}"
        )
        original_index_href = (
            f"../../{source_root.name}/index.html" if is_dated else "../index.html"
        )

        index_source = (source_root / "index.html").read_text(encoding="utf-8")
        (target_dir / "index.html").write_text(
            breviary_snapshot_html(
                index_source,
                body_class="breviary-page breviary-index",
                css_href=css_href,
                original_index_href=original_index_href,
            ),
            encoding="utf-8",
        )

        for _, slug in PRAYERS:
            for source_path in sorted(source_root.glob(f"{slug}*.html")):
                if source_path.name.endswith("-responsive.html"):
                    continue
                page_number_match = re.search(r"-(\d+)\.html$", source_path.name)
                body_class = (
                    "breviary-page" if page_number_match else "breviary-page breviary-first"
                )
                (target_dir / source_path.name).write_text(
                    breviary_snapshot_html(
                        source_path.read_text(encoding="utf-8"),
                        body_class=body_class,
                        css_href=css_href,
                    ),
                    encoding="utf-8",
                )

    logging.info("Generated Breviary snapshot in %s", target_root.relative_to(ROOT))


def write_breviary_stylesheet() -> None:
    base_css = (SITE_DIR / "style.css").read_text(encoding="utf-8").rstrip()
    (SITE_DIR / "breviary.css").write_text(
        f"{base_css}\n\n{BREVIARY_CSS.lstrip()}",
        encoding="utf-8",
    )

def write_error_page(message: str) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    escaped = html.escape(message)
    body = f"""
<section class="error">
  <h2>Lỗi parse nội dung</h2>
  <p>{escaped}</p>
  <p>Xem log GitHub Actions và file debug <code>.cache/source.html</code> hoặc <code>build/source.html</code>.</p>
</section>
"""
    updated = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M giờ Việt Nam")
    (SITE_DIR / "error.html").write_text(
        page_shell("Lỗi cập nhật", body, updated, '<nav class="page-nav"><a href="index.html">Trang chủ</a></nav>'),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=SOURCE_URL)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--debug-only", action="store_true")
    parser.add_argument("--breviary-only", action="store_true")
    parser.add_argument("--english-only", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        if args.debug_only:
            SITE_DIR.mkdir(parents=True, exist_ok=True)
            write_breviary_stylesheet()
            write_debug_site()
            logging.info("Generated Kindle calibration pages in %s", (SITE_DIR / "debug").relative_to(ROOT))
            return 0
        if args.breviary_only:
            write_breviary_snapshot()
            return 0
        if args.english_only:
            passcode = os.environ.get(ENGLISH_BREVIARY_PASSCODE_ENV, "")
            if not passcode:
                raise ValueError(f"{ENGLISH_BREVIARY_PASSCODE_ENV} is required for --english-only")
            SITE_DIR.mkdir(parents=True, exist_ok=True)
            write_breviary_stylesheet()
            build_english_breviary(datetime.now(VN_TZ), passcode)
            return 0
        session = requests.Session()
        run_date = datetime.now(VN_TZ)
        source = fetch_source(session, args.url)
        save_debug_source(source)
        if args.url == SOURCE_URL:
            day_sites: list[DaySite] = []
            fetch_dates = [
                run_date - timedelta(days=1),
                run_date + timedelta(days=1),
                run_date,
            ]
            for fetch_date in fetch_dates:
                prayers, liturgical_day, debug_lines = build_prayers_from_api(session, source, fetch_date)
                if sorted(prayer.slug for prayer in prayers) != sorted(slug for _, slug in PRAYERS):
                    raise ValueError("Parsed prayers do not match expected fixed list")
                day_sites.append(DaySite(fetch_date, prayers, liturgical_day, debug_lines))
            day_sites.sort(key=lambda item: item.date)
        else:
            logging.warning("Non-default URL supplied; using DOM-only fallback parser")
            soup = clean_soup(source)
            root = content_root(soup)
            prayers = split_prayers(root)
            liturgical_day = None
            debug_lines = [
                f"URL fetched: {args.url}",
                f"Fetch time Asia/Ho_Chi_Minh: {run_date.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                "Main content selector used: DOM fallback content_root()",
                "WARNING: liturgical day not found in DOM fallback; tried payload selectors only on default URL",
            ]
            if sorted(prayer.slug for prayer in prayers) != sorted(slug for _, slug in PRAYERS):
                raise ValueError("Parsed prayers do not match expected fixed list")
            day_sites = [DaySite(run_date, prayers, liturgical_day, debug_lines)]
        write_site(day_sites)
        passcode = os.environ.get(ENGLISH_BREVIARY_PASSCODE_ENV, "")
        if passcode:
            update_english_breviary_optional(run_date, passcode)
        else:
            logging.warning(
                "%s is not configured; preserving the last successfully deployed English Breviary",
                ENGLISH_BREVIARY_PASSCODE_ENV,
            )
        append_debug([line for site in day_sites for line in site.debug_lines])
        logging.info("Generated %d day(s) of prayer pages in %s", len(day_sites), SITE_DIR.relative_to(ROOT))
        return 0
    except Exception as exc:
        logging.exception("Failed to generate site")
        write_error_page(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
