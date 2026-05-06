"""
state_manager.py — GitHub Gist-backed commit-SHA persistence.

Each GitHub Actions run is ephemeral, so the last-processed commit SHA is
stored in a private Gist and fetched/pushed at the start and end of every run.
"""
from __future__ import annotations

import json
import logging

import requests

logger = logging.getLogger(__name__)

_GIST_API = "https://api.github.com/gists"
_GIST_FILENAME = "state.json"


def _gist_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def fetch_last_commit(gist_id: str, token: str) -> tuple[str | None, bool]:
    """
    Fetch the last-processed commit SHA from the Gist.

    Returns ``(sha, is_bootstrap)``.
    ``is_bootstrap=True`` means no prior SHA exists; the caller should record
    the current HEAD without posting.
    """
    url = f"{_GIST_API}/{gist_id}"
    try:
        resp = requests.get(url, headers=_gist_headers(token), timeout=15)
        resp.raise_for_status()
        file_obj = resp.json().get("files", {}).get(_GIST_FILENAME, {})
        content = (file_obj.get("content") or "").strip()
        if not content:
            logger.info("Gist has no prior state — bootstrapping.")
            return None, True
        sha = json.loads(content)
        if not isinstance(sha, str) or not sha:
            logger.warning("Gist state is not a valid SHA string — bootstrapping.")
            return None, True
        logger.info("Fetched last commit SHA from Gist: %s", sha[:8])
        return sha, False
    except Exception as exc:
        logger.error("Failed to fetch state from Gist: %s", exc)
        return None, True


def push_last_commit(gist_id: str, token: str, sha: str) -> None:
    """Write the current HEAD SHA back to the Gist. Logs and swallows errors."""
    url = f"{_GIST_API}/{gist_id}"
    payload = {
        "files": {
            _GIST_FILENAME: {"content": json.dumps(sha)}
        }
    }
    try:
        resp = requests.patch(url, headers=_gist_headers(token), json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("Pushed commit SHA %s to Gist.", sha[:8])
    except Exception as exc:
        logger.error("Failed to push state to Gist: %s", exc)
