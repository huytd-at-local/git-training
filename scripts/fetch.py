#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from zoneinfo import ZoneInfo


SOURCE_URL = "https://ktcgkpv.org/readings/prayer"
TIMEOUT_SECONDS = 30
ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
CACHE_DIR = ROOT / ".cache"
BUILD_DIR = ROOT / "build"
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

PAGE_TARGET_UNITS = 17
FIRST_PAGE_TARGET_UNITS = 14
CHARS_PER_READING_LINE = 30
MIN_UNITS_BEFORE_HEADING_BREAK = 7
MIN_PAGE_UNITS = 12
SPLIT_PARAGRAPH_MIN_LINES = 4
SPLIT_PARAGRAPH_CHUNK_LINES = 2

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
        match = re.search(r"\S", text)
        if not match:
            continue
        index = match.start()
        initial = text[index]
        soup = BeautifulSoup("", "lxml")
        initial_tag = soup.new_tag("span")
        initial_tag["class"] = ["illuminated-initial"]
        initial_tag.string = initial
        replacement: list[NavigableString | Tag] = []
        if index:
            replacement.append(NavigableString(text[:index]))
        replacement.append(initial_tag)
        if index + 1 < len(text):
            replacement.append(NavigableString(text[index + 1 :]))
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
    root = prayer_data.get(root_key, {})
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


def extract_liturgical_day(payloads: list[dict]) -> LiturgicalDay | None:
    for payload in payloads:
        info = payload.get("date_info")
        if not isinstance(info, dict):
            continue
        main_title = str(info.get("main_title") or "").strip()
        sub_title = str(info.get("sub_title") or "").strip()
        daily_title = str(info.get("daily_title") or "").strip()
        title = sub_title or main_title or daily_title
        date_title = main_title if sub_title and main_title != sub_title else daily_title
        rank = str(info.get("rank") or info.get("type") or "").strip()
        if title or rank:
            selector = "payload.date_info.sub_title/main_title/rank" if sub_title else "payload.date_info.main_title/rank"
            return LiturgicalDay(title=title, rank=rank, selector=selector, date_title=date_title)
        feasts = payload.get("feasts")
        if isinstance(feasts, list) and feasts:
            title = str(feasts[0].get("text") or "").strip()
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
    season = payload.get("date_info", {}).get("season")
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
        prayers.append(render_dom_prayer(title, slug, source, payload, root_key, tab_id))

    night_payload = fetch_prayer_json(session, date, "nightPrayer")
    payloads.append(night_payload)
    write_payload_debug("kinh-toi", night_payload)
    prayers.append(render_night_prayer("Kinh Tối", "kinh-toi", source, night_payload, date))
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


def block_units(block_html: str) -> int:
    soup = BeautifulSoup(block_html, "lxml")
    text = soup.get_text(" ", strip=True)
    br_count = len(soup.find_all("br"))
    heading_count = len(soup.find_all(["h2", "h3"]))
    explicit_lines = br_count + 1 if text else 0
    return max(1, max(text_units(text), explicit_lines) + heading_count)


def is_heading_block(block_html: str) -> bool:
    soup = BeautifulSoup(block_html, "lxml")
    first = soup.find(["h2", "h3"])
    return bool(first and first.get_text(strip=True))


def page_units(blocks: list[str]) -> int:
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


def split_text_paragraph_to_fit(paragraph: Tag, remaining_units: int) -> tuple[str, str] | None:
    if remaining_units < 4:
        return None

    allowed_units = remaining_units + 2
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


def split_block_to_fit(block_html: str, remaining_units: int) -> tuple[str, str] | None:
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
<p class="mode-switch"><a href="index-responsive.html">Mở bản responsive</a></p>
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
                liturgical_day,
                css_href=css_href,
                bottom_nav=nav,
                body_class="responsive-page responsive-prayer",
            ),
            encoding="utf-8",
        )

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
            page_note = f"Trang {page_index}/{page_count}" if page_index > 1 else ""
            (target_dir / prayer_page_filename(prayer.slug, page_index)).write_text(
                page_shell(
                    prayer.title,
                    page_body,
                    updated,
                    "",
                    liturgical_day,
                    show_metadata=page_index == 1,
                    show_title=page_index == 1,
                    page_note=page_note,
                    css_href=css_href,
                    bottom_nav=nav,
                ),
                encoding="utf-8",
            )


def root_redirect_script(day_sites: list[DaySite]) -> str:
    entries = ",".join("'%s'" % site.date.strftime("%Y-%m-%d") for site in day_sites)
    return f"""  <script>
  (function() {{
    var days = [{entries}];
    var now = new Date();
    var vn = new Date(now.getTime() + 7 * 60 * 60 * 1000);
    var y = vn.getUTCFullYear();
    var m = vn.getUTCMonth() + 1;
    var d = vn.getUTCDate();
    var key = y + '-' + (m < 10 ? '0' + m : m) + '-' + (d < 10 ? '0' + d : d);
    var h = vn.getUTCHours();
    var slug = 'kinh-toi';
    if (h < 4) slug = 'kinh-toi';
    else if (h < 6) slug = 'kinh-sach';
    else if (h < 8) slug = 'kinh-sang';
    else if (h < 11) slug = 'kinh-trua-gio-ba';
    else if (h < 13) slug = 'kinh-trua-gio-sau';
    else if (h < 17) slug = 'kinh-trua-gio-chin';
    else if (h < 20) slug = 'kinh-chieu';
    for (var i = 0; i < days.length; i++) {{
      if (days[i] === key) {{
        window.location.replace(days[i] + '/' + slug + '.html');
        return;
      }}
    }}
  }})();
  </script>"""


def write_site(day_sites: list[DaySite]) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
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

    updated = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M giờ Việt Nam")
    available_dates = [site.date for site in day_sites]
    today = day_sites[len(day_sites) // 2]
    for site in day_sites:
        write_day_site(
            SITE_DIR / date_dir_name(site.date),
            "../style.css",
            site.prayers,
            site.liturgical_day,
            site.date,
            available_dates,
            updated,
            date_dir_name(site.date),
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
    )

    root_index = SITE_DIR / "index.html"
    root_index.write_text(
        root_index.read_text(encoding="utf-8").replace("</head>", root_redirect_script(day_sites) + "\n</head>"),
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
    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
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
        append_debug([line for site in day_sites for line in site.debug_lines])
        logging.info("Generated %d day(s) of prayer pages in %s", len(day_sites), SITE_DIR.relative_to(ROOT))
        return 0
    except Exception as exc:
        logging.exception("Failed to generate site")
        write_error_page(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
