"""
state_manager.py — Persist and load the set of already-seen listing IDs.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILE = Path("seen_ids.json")


def load_seen_ids() -> set[str]:
    """Return the set of listing IDs that have already been announced."""
    if not STATE_FILE.exists():
        logger.info("No state file found at %s — starting fresh.", STATE_FILE)
        return set()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array of ID strings.")
        ids = set(str(x) for x in data)
        logger.info("Loaded %d seen IDs from %s", len(ids), STATE_FILE)
        return ids
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse %s (%s) — starting with empty state.", STATE_FILE, exc)
        return set()


def save_seen_ids(seen_ids: set[str]) -> None:
    """Persist the full set of seen IDs to disk."""
    STATE_FILE.write_text(
        json.dumps(sorted(seen_ids), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.debug("Saved %d seen IDs to %s", len(seen_ids), STATE_FILE)


def diff_listings(
    listings: list[dict],
    seen_ids: set[str],
) -> list[dict]:
    """
    Return listings that are:
      - not in seen_ids (genuinely new), AND
      - active / visible (not closed or hidden).
    """
    new_postings = []
    for listing in listings:
        lid = str(listing.get("id", ""))
        if not lid:
            logger.debug("Skipping listing with no id: %s", listing)
            continue
        if lid in seen_ids:
            continue

        # Filter out closed / hidden roles
        if not listing.get("active", True):
            logger.debug("Skipping inactive listing id=%s", lid)
            seen_ids.add(lid)  # mark so we don't process it again later
            continue
        if not listing.get("is_visible", True):
            logger.debug("Skipping hidden listing id=%s", lid)
            seen_ids.add(lid)
            continue

        new_postings.append(listing)

    return new_postings
