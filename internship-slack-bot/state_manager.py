"""
state_manager.py — GitHub Gist-backed seen-ID persistence and listing diff logic.

Each GitHub Actions run is ephemeral, so seen state is stored in a private
Gist and fetched/pushed at the start and end of every run.
"""
from __future__ import annotations

import json
import logging

import requests

logger = logging.getLogger(__name__)

_GIST_API = "https://api.github.com/gists"
_GIST_FILENAME = "seen_ids.json"


def _gist_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def fetch_seen_ids(gist_id: str, token: str) -> tuple[set[str], bool]:
    """
    Fetch seen IDs from a GitHub Gist.

    Returns ``(ids, is_bootstrap)``.
    ``is_bootstrap=True`` means the fetch failed or the file was empty/invalid;
    the caller should mark all current listings as seen without posting any.
    """
    url = f"{_GIST_API}/{gist_id}"
    try:
        resp = requests.get(url, headers=_gist_headers(token), timeout=15)
        resp.raise_for_status()
        file_obj = resp.json().get("files", {}).get(_GIST_FILENAME, {})
        content = (file_obj.get("content") or "").strip()
        if not content or content == "{}":
            logger.info("Gist '%s' has no prior state — bootstrapping.", gist_id)
            return set(), True
        data = json.loads(content)
        if not isinstance(data, list):
            logger.warning("Gist content is not a JSON array — bootstrapping.")
            return set(), True
        ids = {str(x) for x in data}
        logger.info("Fetched %d seen IDs from Gist.", len(ids))
        return ids, False
    except Exception as exc:
        logger.error("Failed to fetch seen IDs from Gist: %s", exc)
        return set(), True


def push_seen_ids(gist_id: str, token: str, seen_ids: set[str]) -> None:
    """Write the updated seen-ID set back to the Gist. Logs and swallows errors."""
    url = f"{_GIST_API}/{gist_id}"
    payload = {
        "files": {
            _GIST_FILENAME: {
                "content": json.dumps(sorted(seen_ids), indent=2, ensure_ascii=False)
            }
        }
    }
    try:
        resp = requests.patch(url, headers=_gist_headers(token), json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("Pushed %d seen IDs to Gist.", len(seen_ids))
    except Exception as exc:
        logger.error("Failed to push seen IDs to Gist: %s", exc)


def diff_listings(
    listings: list[dict],
    seen_ids: set[str],
) -> list[dict]:
    """
    Return listings that are:
      - not in seen_ids (genuinely new), AND
      - active / visible (not closed or hidden).

    Inactive and hidden listings are added to seen_ids in-place so they are
    never re-evaluated on subsequent runs.
    """
    new_postings = []
    for listing in listings:
        lid = str(listing.get("id", ""))
        if not lid:
            logger.debug("Skipping listing with no id: %s", listing)
            continue
        if lid in seen_ids:
            continue

        if not listing.get("active", True):
            logger.debug("Skipping inactive listing id=%s", lid)
            seen_ids.add(lid)
            continue
        if not listing.get("is_visible", True):
            logger.debug("Skipping hidden listing id=%s", lid)
            seen_ids.add(lid)
            continue

        new_postings.append(listing)

    return new_postings
