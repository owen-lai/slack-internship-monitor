"""
allowlist_manager.py — Load and query the committed company allowlist.

allowlist.json is committed to the repo and updated via PR; there is no
runtime editing, so no locking is needed.
"""
from __future__ import annotations

import json
import logging
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


def _load_unsafe() -> list[str]:
    """Read the allowlist file and return lowercase entries. Seeds defaults if absent."""
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
    """Write the default allowlist (original casing for readability)."""
    ALLOWLIST_FILE.write_text(
        json.dumps(DEFAULT_COMPANIES, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Seeded default allowlist with %d companies.", len(DEFAULT_COMPANIES))


def load() -> list[str]:
    """Return the full allowlist as a sorted list of lowercase strings."""
    return _load_unsafe()


def is_allowed(company: str) -> bool:
    """Return True if company matches any allowlist entry (case-insensitive)."""
    key = company.strip().lower()
    return key in set(_load_unsafe())
