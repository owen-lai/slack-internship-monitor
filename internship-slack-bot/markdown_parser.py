"""
markdown_parser.py — Parse internship markdown/HTML tables into listing dicts.

Handles two source formats:
  - vanshb03 (pipe tables): Company | Role | Location | Application/Link | Date Posted
  - SimplifyJobs (HTML tables): Company | Role | Location | Terms | Application | Age

Closed listings (🔒) and inactive <details> blocks are silently skipped.
Continuation rows starting with ↳ inherit the last seen company name.
IDs are stable SHA-1 hashes of (company, role, url).
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_TABLE_START = "TABLE_START"
_CLOSED_EMOJI = "\U0001f512"  # 🔒


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _extract_url(cell: str) -> str:
    m = re.search(r'href="([^"]+)"', cell)
    return m.group(1) if m else ""


def _clean_cell(cell: str) -> str:
    text = re.sub(r"<[^>]+>", "", cell)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return text.strip()


def _clean_location(cell: str) -> str:
    details = re.search(
        r"<details>.*?<summary>([^<]+)</summary>(.*?)</details>", cell, re.DOTALL
    )
    if details:
        inner = details.group(2)
        inner = re.sub(r"<br\s*/?>", ", ", inner, flags=re.IGNORECASE)
        return _clean_cell(inner)
    loc = re.sub(r"</?br\s*/?>", ", ", cell, flags=re.IGNORECASE)
    return _clean_cell(loc)


def _clean_role(raw: str) -> str:
    text = _clean_cell(raw)
    return re.sub(r"[\U0001f6c2\U0001f1fa\U0001f393\U0001f525\U0001f512]+", "", text).strip()


def _make_id(company: str, role: str, url: str) -> str:
    raw = f"{company.lower()}|{role.lower()}|{url}"
    return "md_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Pipe-table parser (vanshb03 format)
# ---------------------------------------------------------------------------

def _parse_pipe_rows(content: str, source_tag: str) -> list[dict]:
    lines = content.splitlines()

    start_idx = None
    for i, line in enumerate(lines):
        if _TABLE_START in line:
            start_idx = i
            break

    if start_idx is None:
        logger.warning("No TABLE_START marker in %s", source_tag)
        return []

    listings: list[dict] = []
    last_company = ""
    header_seen = separator_seen = False

    for line in lines[start_idx + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue

        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if not cells:
            continue

        if not header_seen:
            header_seen = True
            continue
        if not separator_seen:
            separator_seen = True
            continue
        if _CLOSED_EMOJI in stripped:
            continue

        n = len(cells)
        company_raw = cells[0] if n > 0 else ""
        role_raw = cells[1] if n > 1 else ""
        location_raw = cells[2] if n > 2 else ""
        app_raw = cells[3] if n > 3 else ""
        date_posted = _clean_cell(cells[4]) if n > 4 else ""

        company = _clean_cell(company_raw)
        if company == "↳":
            company = last_company
        else:
            last_company = company

        entry: dict = {
            "id": _make_id(company, _clean_role(role_raw), _extract_url(app_raw)),
            "company_name": company,
            "title": _clean_role(role_raw),
            "location": _clean_location(location_raw),
            "url": _extract_url(app_raw),
            "date_posted": date_posted,
            "active": True,
            "source": source_tag,
        }
        listings.append(entry)

    return listings


# ---------------------------------------------------------------------------
# HTML-table parser (SimplifyJobs format)
# ---------------------------------------------------------------------------

def _parse_html_rows(content: str, source_tag: str) -> list[dict]:
    start_pos = content.find(_TABLE_START)
    if start_pos == -1:
        logger.warning("No TABLE_START marker in %s", source_tag)
        return []

    # Drop everything before TABLE_START and strip inactive <details> blocks
    body = content[start_pos:]
    body = re.sub(r"<details>.*?</details>", "", body, flags=re.DOTALL)

    listings: list[dict] = []
    last_company = ""

    for tr_match in re.finditer(r"<tr>(.*?)</tr>", body, re.DOTALL):
        tr = tr_match.group(1)
        cells = re.findall(r"<td>(.*?)</td>", tr, re.DOTALL)
        if len(cells) < 5:
            continue  # header rows use <th>, not <td>
        if _CLOSED_EMOJI in tr:
            continue

        company_raw = cells[0].strip()
        role_raw = cells[1].strip()
        location_raw = cells[2].strip()
        # 5-col format: Company|Role|Location|Application|Age (no Terms)
        # 6-col format: Company|Role|Location|Terms|Application|Age
        if len(cells) >= 6:
            terms = _clean_cell(cells[3])
            app_raw = cells[4].strip()
            age_raw = cells[5].strip()
        else:
            terms = ""
            app_raw = cells[3].strip()
            age_raw = cells[4].strip() if len(cells) > 4 else ""

        # Company cell: <strong><a ...>Name</a></strong>  OR  ↳
        company_link = re.search(
            r"<strong>.*?<a[^>]*>([^<]+)</a>.*?</strong>", company_raw, re.DOTALL
        )
        if company_link:
            company = company_link.group(1).strip()
            last_company = company
        elif company_raw.strip() == "↳":
            company = last_company
        else:
            company = _clean_cell(company_raw)
            last_company = company

        role = _clean_role(role_raw)
        location = re.sub(r"<br\s*/?>", ", ", location_raw, flags=re.IGNORECASE)
        location = _clean_cell(location)
        url = _extract_url(app_raw)
        date_posted = _clean_cell(age_raw)

        entry: dict = {
            "id": _make_id(company, role, url),
            "company_name": company,
            "title": role,
            "location": location,
            "url": url,
            "date_posted": date_posted,
            "active": True,
            "source": source_tag,
        }
        if terms:
            entry["terms"] = terms

        listings.append(entry)

    return listings


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def _detect_and_parse(content: str, source_tag: str) -> list[dict]:
    """Dispatch to the right parser based on whether the source uses HTML tables."""
    start_pos = content.find(_TABLE_START)
    if start_pos != -1 and "<table>" in content[start_pos:]:
        return _parse_html_rows(content, source_tag)
    return _parse_pipe_rows(content, source_tag)


def parse_markdown_file(path: Path, source_tag: str = "local") -> list[dict]:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return []
    listings = _detect_and_parse(content, source_tag)
    logger.info("Parsed %d active listings from %s", len(listings), path.name)
    return listings


def fetch_and_parse(raw_url: str, source_tag: str) -> list[dict]:
    try:
        resp = requests.get(raw_url, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Failed to fetch %s: %s", source_tag, exc)
        return []
    listings = _detect_and_parse(resp.text, source_tag)
    logger.info("Parsed %d active listings from %s", len(listings), source_tag)
    return listings
