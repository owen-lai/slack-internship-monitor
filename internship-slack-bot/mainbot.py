"""
mainbot.py — Entrypoint for the internship Slack bot.

Behaviour
---------
* Default: loops forever on CHECK_INTERVAL_SECONDS (default 60).
* RUN_ONCE=true: runs a single check cycle then exits (used by GitHub Actions).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import allowlist_manager
import bot_listener
import formatter
import repo_manager
import state_manager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

load_dotenv()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def load_listings(repo_path: Path) -> list[dict]:
    """Read and parse the listings JSON file from the cloned repo."""
    listings_path = repo_manager.find_listings_file(repo_path)
    text = listings_path.read_text(encoding="utf-8")
    data = json.loads(text)
    if isinstance(data, dict):
        # Some repos wrap the array in a top-level object
        for key in ("postings", "listings", "jobs", "data"):
            if key in data and isinstance(data[key], list):
                logger.debug("Unwrapping top-level key '%s'", key)
                return data[key]
        raise ValueError(f"Unexpected JSON structure: top-level keys are {list(data.keys())}")
    if isinstance(data, list):
        return data
    raise ValueError(f"Unexpected JSON type: {type(data)}")


def post_listing(client: WebClient, channel: str, listing: dict) -> None:
    """Send a single listing to Slack. Logs and swallows API errors."""
    payload = formatter.format_message(listing)
    try:
        client.chat_postMessage(
            channel=channel,
            text=payload["text"],
            blocks=payload["blocks"],
        )
        logger.info(
            "Posted: %s @ %s",
            listing.get("title", "?"),
            listing.get("company_name") or listing.get("company", "?"),
        )
    except SlackApiError as exc:
        logger.error(
            "Slack API error posting listing id=%s: %s",
            listing.get("id"),
            exc.response["error"],
        )


def check_cycle(client: WebClient, repo_url: str | None = None, channel: str | None = None) -> None:
    """One full check-and-notify cycle."""
    if repo_url is None:
        repo_url = os.getenv("GITHUB_REPO_URL", "https://github.com/vanshb03/Summer2026-Internships")
    if channel is None:
        channel = os.environ["SLACK_CHANNEL_ID"]

    try:
        repo_path = repo_manager.ensure_repo(repo_url)
    except RuntimeError as exc:
        logger.error("Git operation failed: %s", exc)
        return

    try:
        listings = load_listings(repo_path)
    except (json.JSONDecodeError, ValueError, FileNotFoundError, OSError) as exc:
        logger.error("Failed to load listings: %s", exc)
        return

    logger.info("Loaded %d total listings", len(listings))

    seen_ids = state_manager.load_seen_ids()
    new_listings = state_manager.diff_listings(listings, seen_ids)
    logger.info("%d new active listings to announce", len(new_listings))

    for listing in new_listings:
        company = listing.get("company_name") or listing.get("company") or ""
        if not allowlist_manager.is_allowed(company):
            logger.debug("Skipping non-allowlisted company: %s", company)
            seen_ids.add(str(listing["id"]))
            continue
        post_listing(client, channel, listing)
        seen_ids.add(str(listing["id"]))

    # Always persist seen IDs — diff_listings may have added inactive ones too
    state_manager.save_seen_ids(seen_ids)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    slack_token: str = os.environ["SLACK_BOT_TOKEN"]
    channel: str = os.environ["SLACK_CHANNEL_ID"]
    repo_url: str = os.getenv(
        "GITHUB_REPO_URL", "https://github.com/vanshb03/Summer2026-Internships"
    )
    check_interval: int = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
    run_once: bool = os.getenv("RUN_ONCE", "false").lower() in {"1", "true", "yes"}

    client = WebClient(token=slack_token)

    if run_once:
        logger.info("RUN_ONCE mode — performing a single check cycle.")
        check_cycle(client, repo_url=repo_url, channel=channel)
        return

    # Start the Bolt Socket Mode listener for Slack commands (non-blocking daemon thread)
    app_token: str | None = os.getenv("SLACK_APP_TOKEN")
    if app_token:
        bot_listener.start_listener(slack_token, app_token, channel)
    else:
        logger.warning("SLACK_APP_TOKEN not set — 'add <company>' command listener is disabled.")

    logger.info(
        "Starting internship monitor (interval=%ds, channel=%s)",
        check_interval,
        channel,
    )
    while True:
        logger.info("--- Check cycle starting ---")
        check_cycle(client, repo_url=repo_url, channel=channel)
        logger.info("--- Check cycle complete, sleeping %ds ---", check_interval)
        time.sleep(check_interval)


if __name__ == "__main__":
    main()
