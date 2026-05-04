"""
formatter.py — Build Slack Block Kit messages for internship listings.
"""
from __future__ import annotations

import datetime
import logging

logger = logging.getLogger(__name__)

SPONSORSHIP_EMOJI = {
    "sponsors": ":white_check_mark: Sponsors",
    "does not offer sponsorship": ":x: No Sponsorship",
    "does not sponsor": ":x: No Sponsorship",
    "unknown": ":grey_question: Unknown",
}


def _sponsorship_label(raw: str | None) -> str:
    if not raw:
        return ":grey_question: Unknown"
    key = raw.strip().lower()
    # Sort by length descending so more-specific patterns (e.g. "does not offer
    # sponsorship") match before shorter substrings (e.g. "sponsors").
    for k, label in sorted(SPONSORSHIP_EMOJI.items(), key=lambda x: -len(x[0])):
        if k in key:
            return label
    return f":grey_question: {raw.strip()}"


def _format_date(epoch: int | float | str | None) -> str:
    if epoch is None:
        return "Unknown"
    try:
        ts = int(epoch)
        return datetime.datetime.utcfromtimestamp(ts).strftime("%b %d, %Y")
    except (ValueError, TypeError, OSError):
        return str(epoch)


def _locations_text(locations: list | str | None) -> str:
    if not locations:
        return "Not specified"
    if isinstance(locations, str):
        return locations
    return ", ".join(str(loc) for loc in locations if loc)


def format_message(listing: dict) -> dict:
    """
    Build a Slack API `chat.postMessage` payload (blocks + text) for a single listing.

    Returns a dict with keys: ``text`` (fallback) and ``blocks`` (Block Kit).
    """
    company = listing.get("company_name") or listing.get("company") or "Unknown Company"
    title = listing.get("title") or "Software Engineer Intern"
    locations = _locations_text(listing.get("locations") or listing.get("location"))
    sponsorship = _sponsorship_label(
        listing.get("sponsorship") or listing.get("visa_sponsorship")
    )
    date_posted = _format_date(listing.get("date_posted") or listing.get("posted"))
    url = listing.get("url") or listing.get("application_url") or ""

    fallback_text = f"New internship: {title} at {company} — {locations}"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":briefcase: New Internship Posting",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Company*\n{company}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Role*\n{title}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Location(s)*\n{locations}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Sponsorship*\n{sponsorship}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Date Posted*\n{date_posted}",
                },
            ],
        },
    ]

    if url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Apply :rocket:",
                            "emoji": True,
                        },
                        "url": url,
                        "style": "primary",
                        "action_id": "apply_button",
                    }
                ],
            }
        )

    blocks.append({"type": "divider"})

    return {"text": fallback_text, "blocks": blocks}
