"""
mainbot.py — Entrypoint for the internship Slack bot.

Always performs a single check cycle and exits. Designed to be called
by GitHub Actions on a cron schedule. The last-processed commit SHA is
persisted between ephemeral runners via a private GitHub Gist.
"""
from __future__ import annotations

import logging
import os
import re
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

_SOURCES = [
    ("README.md", "simplify-summer"),
    ("README-Off-Season.md", "simplify-offseason"),
]


def _raw_url(repo_url: str, sha: str, filename: str) -> str | None:
    m = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?$", repo_url)
    if not m:
        return None
    return f"https://raw.githubusercontent.com/{m.group(1)}/{sha}/{filename}"


def load_all_listings(repo_path: Path) -> list[dict]:
    listings: list[dict] = []
    for filename, tag in _SOURCES:
        p = repo_path / filename
        if p.exists():
            listings.extend(markdown_parser.parse_markdown_file(p, tag))
        else:
            logger.warning("Expected file not found in cloned repo: %s", filename)
    logger.info("Total listings from local clone: %d", len(listings))
    return listings


def load_listings_at_sha(repo_url: str, sha: str) -> list[dict]:
    listings: list[dict] = []
    for filename, tag in _SOURCES:
        url = _raw_url(repo_url, sha, filename)
        if url:
            listings.extend(markdown_parser.fetch_and_parse(url, tag))
    logger.info("Total listings at commit %s: %d", sha[:8], len(listings))
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
    last_sha: str | None,
    repo_url: str,
    channel: str,
) -> str | None:
    """
    Clone/pull the repo, compare HEAD against last_sha, and post new listings.

    Returns the new HEAD SHA to persist, or None if the git operation failed.
    """
    try:
        repo_path = repo_manager.ensure_repo(repo_url, branch="dev")
        head_sha = repo_manager.get_head_sha(repo_path)
    except RuntimeError as exc:
        logger.error("Git operation failed: %s", exc)
        return None

    if last_sha is None:
        logger.info("Bootstrap: recording HEAD %s without posting.", head_sha[:8])
        return head_sha

    if head_sha == last_sha:
        logger.info("No new commits since %s — nothing to post.", last_sha[:8])
        return last_sha

    logger.info("New commits detected: %s → %s", last_sha[:8], head_sha[:8])

    current_listings = load_all_listings(repo_path)
    prev_listings = load_listings_at_sha(repo_url, last_sha)

    prev_ids = {l["id"] for l in prev_listings}
    new_listings = [
        l for l in current_listings
        if l["id"] not in prev_ids
        and l.get("active", True)
        and l.get("is_visible", True)
        and l.get("date_posted") == "0d"
    ]

    logger.info("%d new listings to post.", len(new_listings))
    for listing in new_listings:
        company = listing.get("company_name") or listing.get("company") or ""
        ping = allowlist_manager.is_allowed(company)
        post_listing(client, channel, listing, ping=ping)

    return head_sha


def main() -> None:
    slack_token: str = os.environ["SLACK_BOT_TOKEN"]
    channel: str = os.environ["SLACK_CHANNEL_ID"]
    repo_url: str = os.getenv(
        "GITHUB_REPO_URL", "https://github.com/SimplifyJobs/Summer2026-Internships"
    )
    gist_id: str = os.environ["GIST_ID"]
    github_token: str = os.environ["GHUB_TOKEN"]

    client = WebClient(token=slack_token)

    last_sha, is_bootstrap = state_manager.fetch_last_commit(gist_id, github_token)
    if is_bootstrap:
        logger.info("Bootstrap mode — no prior commit recorded.")

    new_sha = check_cycle(client, last_sha, repo_url=repo_url, channel=channel)

    if new_sha:
        state_manager.push_last_commit(gist_id, github_token, new_sha)


if __name__ == "__main__":
    main()
