"""
allowlist_manager.py — Persist and query the company allowlist.

Thread-safe: the polling loop and Bolt listener share this module across threads.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

ALLOWLIST_FILE = Path("allowlist.json")

DEFAULT_COMPANIES = [
    "Google", "Meta", "Apple", "Microsoft", "Amazon", "Netflix", "Nvidia",
    "OpenAI", "Anthropic", "Stripe", "Figma", "Notion", "Linear", "Vercel",
    "Databricks", "Snowflake", "Palantir", "Ramp", "Brex", "Scale AI",
    "Anduril", "SpaceX", "Tesla", "Waymo", "DeepMind", "Salesforce", "Adobe",
    "Uber", "Lyft", "Airbnb", "Coinbase", "Robinhood", "Plaid", "Instacart",
    "DoorDash", "Intel", "Qualcomm", "AMD", "Arm", "Applied Intuition",
    "Cruise", "Aurora", "Rivian", "Asana", "Dropbox", "Twilio", "HashiCorp",
    "MongoDB", "Cloudflare", "Datadog", "Confluent", "Airtable",
]

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers (called with _lock already held)
# ---------------------------------------------------------------------------

def _load_unsafe() -> list[str]:
    if not ALLOWLIST_FILE.exists():
        _seed_unsafe()
    try:
        data = json.loads(ALLOWLIST_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array")
        return [str(x).lower() for x in data]
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse %s (%s) — falling back to defaults.", ALLOWLIST_FILE, exc)
        return [c.lower() for c in DEFAULT_COMPANIES]


def _save_unsafe(entries: list[str]) -> None:
    ALLOWLIST_FILE.write_text(
        json.dumps(sorted(entries), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _seed_unsafe() -> None:
    defaults = [c.lower() for c in DEFAULT_COMPANIES]
    _save_unsafe(defaults)
    logger.info("Seeded default allowlist with %d companies.", len(defaults))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load() -> list[str]:
    """Return the full allowlist as a sorted list of lowercase strings."""
    with _lock:
        return _load_unsafe()


def is_allowed(company: str) -> bool:
    """Return True if company matches any allowlist entry (case-insensitive)."""
    key = company.strip().lower()
    with _lock:
        return key in set(_load_unsafe())


def add_company(company: str) -> bool:
    """
    Add company to the allowlist (stored lowercase).

    Returns True if the company was newly added, False if it was already present.
    """
    key = company.strip().lower()
    with _lock:
        entries = _load_unsafe()
        if key in entries:
            return False
        entries.append(key)
        _save_unsafe(entries)
    logger.info("Added '%s' to allowlist.", company)
    return True
