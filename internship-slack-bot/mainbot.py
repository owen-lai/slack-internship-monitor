"""
mainbot.py — Entrypoint for the internship Slack bot.

Always performs a single check cycle and exits. Designed to be called
by GitHub Actions on a cron schedule. Seen state is persisted between
ephemeral runners via a private GitHub Gist.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import allowlist_manager
import formatter
import markdown_parser
import repo_manager
import state_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

load_dotenv()


def load_all_listings(repo_path: Path) -> list[dict]:
    """
    Load listings from the cloned SimplifyJobs repo.

    Sources:
      1. README.md          — summer 2026 listings
      2. README-Off-Season.md — fall/spring 2026 listings
    """
    listings: list[dict] = []
    for filename, tag in [
        ("README.md", "simplify-summer"),
        ("README-Off-Season.md", "simplify-offseason"),
    ]:
        p = repo_path / filename
        if p.exists():
            listings.extend(markdown_parser.parse_markdown_file(p, tag))
        else:
            logger.warning("Expected file not found in cloned repo: %s", filename)

    logger.info("Total listings across all sources: %d", len(listings))
    return listings


def post_listing(client: WebClient, channel: str, listing: dict, ping: bool = False) -> None:
    """Send a single listing to Slack. Logs and swallows API errors."""
    payload = formatter.format_message(listing, ping=ping)
    try:
        client.chat_postMessage(
            channel=channel,
            text=payload["text"],
            blocks=payload["blocks"],
        )
        logger.info(
            "Posted%s: %s @ %s",
            " [PING]" if ping else "",
            listing.get("title", "?"),
            listing.get("company_name") or listing.get("company", "?"),
        )
    except SlackApiError as exc:
        logger.error(
            "Slack API error posting listing id=%s: %s",
            listing.get("id"),
            exc.response["error"],
        )


def check_cycle(
    client: WebClient,
    seen_ids: set[str],
    repo_url: str,
    channel: str,
    post_enabled: bool = True,
) -> set[str]:
    """
    Fetch the latest listings, diff against seen_ids, and post new ones.

    post_enabled=False skips Slack messages (bootstrap mode: record state
    without flooding the channel on first run or after a Gist failure).

    Returns the updated seen_ids set.
    """
    try:
        repo_path = repo_manager.ensure_repo(repo_url, branch="main")
    except RuntimeError as exc:
        logger.error("Git operation failed: %s", exc)
        return seen_ids

    listings = load_all_listings(repo_path)
    if not listings:
        logger.error("No listings loaded from any source — skipping cycle.")
        return seen_ids

    logger.info("Loaded %d total listings", len(listings))

    new_listings = state_manager.diff_listings(listings, seen_ids)
    logger.info(
        "%d new active listings found%s",
        len(new_listings),
        " (bootstrap: not posting)" if not post_enabled else "",
    )

    for listing in new_listings:
        seen_ids.add(str(listing["id"]))
        if not post_enabled:
            continue
        company = listing.get("company_name") or listing.get("company") or ""
        ping = allowlist_manager.is_allowed(company)
        post_listing(client, channel, listing, ping=ping)

    return seen_ids


def main() -> None:
    slack_token: str = os.environ["SLACK_BOT_TOKEN"]
    channel: str = os.environ["SLACK_CHANNEL_ID"]
    repo_url: str = os.getenv(
        "GITHUB_REPO_URL", "https://github.com/SimplifyJobs/Summer2026-Internships"
    )
    gist_id: str = os.environ["GIST_ID"]
    github_token: str = os.environ["GHUB_TOKEN"]

    client = WebClient(token=slack_token)

    seen_ids, is_bootstrap = state_manager.fetch_seen_ids(gist_id, github_token)
    if is_bootstrap:
        logger.info("Bootstrap mode — recording current state without posting.")

    updated_ids = check_cycle(
        client,
        seen_ids,
        repo_url=repo_url,
        channel=channel,
        post_enabled=not is_bootstrap,
    )

    state_manager.push_seen_ids(gist_id, github_token, updated_ids)


if __name__ == "__main__":
    main()
