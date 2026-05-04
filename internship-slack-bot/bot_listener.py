"""
bot_listener.py — Slack Bolt listener for the "add <company>" command.

Runs in a daemon thread alongside the polling loop.
Requires Socket Mode: set SLACK_APP_TOKEN (xapp- token) in .env.
"""
from __future__ import annotations

import logging
import threading

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import allowlist_manager

logger = logging.getLogger(__name__)


def build_app(bot_token: str, channel_id: str) -> App:
    app = App(token=bot_token)

    @app.event("message")
    def handle_message(event, say):
        # Ignore messages from bots (including ourselves) to prevent loops
        if event.get("bot_id"):
            return

        # Only act in the configured channel
        if event.get("channel") != channel_id:
            return

        text = (event.get("text") or "").strip()
        if not text.lower().startswith("add "):
            return

        company = text[4:].strip()
        if not company:
            return

        was_added = allowlist_manager.add_company(company)
        thread_ts = event.get("ts")

        if was_added:
            say(text=f"✅ Added _{company}_ to the watchlist.", thread_ts=thread_ts)
            logger.info("Allowlist: added '%s' via Slack command.", company)
        else:
            say(text=f"_{company}_ is already on the watchlist.", thread_ts=thread_ts)
            logger.info("Allowlist: '%s' already present (duplicate add).", company)

    return app


def start_listener(bot_token: str, app_token: str, channel_id: str) -> threading.Thread:
    """Start the Bolt Socket Mode handler in a daemon thread and return it."""
    app = build_app(bot_token, channel_id)
    handler = SocketModeHandler(app, app_token)

    thread = threading.Thread(target=handler.start, daemon=True, name="bolt-listener")
    thread.start()
    logger.info("Bolt Socket Mode listener started (channel=%s).", channel_id)
    return thread
