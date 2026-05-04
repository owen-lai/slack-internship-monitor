# Internship Slack Bot

Monitors the [vanshb03/Summer2026-Internships](https://github.com/vanshb03/Summer2026-Internships) GitHub repo for new internship postings and sends formatted alerts to a Slack channel via Block Kit messages.

```
New Internship Posting
──────────────────────────────────────────
Company        Acme Corp
Role           Software Engineer Intern
Location(s)    San Francisco, CA, Remote
Sponsorship    ✅ Sponsors
Date Posted    Apr 25, 2024
                                [Apply 🚀]
```

---

## Table of contents

1. [Create a Slack app](#1-create-a-slack-app)
2. [Get your bot token and channel ID](#2-get-your-bot-token-and-channel-id)
3. [Clone this repo and configure .env](#3-clone-this-repo-and-configure-env)
4. [Run locally](#4-run-locally)
5. [Run via GitHub Actions](#5-run-via-github-actions)
6. [Project structure](#6-project-structure)
7. [Running tests](#7-running-tests)

---

## 1. Create a Slack app

1. Go to <https://api.slack.com/apps> and click **Create New App → From scratch**.
2. Give it a name (e.g. `Internship Monitor`) and pick your workspace.
3. In the left sidebar, open **OAuth & Permissions**.
4. Under **Bot Token Scopes**, click **Add an OAuth Scope** and add:
   - `chat:write`
5. In the left sidebar, open **Event Subscriptions** and toggle it **On**.
   - Under **Subscribe to bot events**, add: `message.channels`
6. In the left sidebar, open **Socket Mode** and toggle it **On**.
   - Click **Generate an app-level token**, give it any name, add the `connections:write` scope, and click **Generate**. Copy the token (starts with `xapp-`). This is your `SLACK_APP_TOKEN`.
7. Back in **OAuth & Permissions**, scroll up and click **Install to Workspace**, then **Allow**.
8. Copy the **Bot User OAuth Token** (starts with `xoxb-`). This is your `SLACK_BOT_TOKEN`.

> **Invite the bot to your channel**: In Slack, open the channel you want the bot to post in and type `/invite @YourBotName`.

---

## 2. Get your bot token and channel ID

| Value | Where to find it |
|---|---|
| **Bot token** (`xoxb-…`) | Slack app → OAuth & Permissions → Bot User OAuth Token |
| **App-level token** (`xapp-…`) | Slack app → Socket Mode → app-level token you generated |
| **Channel ID** | Open the channel in Slack → right-click → **View channel details** → copy the ID at the bottom (starts with `C`) |

---

## 3. Clone this repo and configure .env

```bash
git clone https://github.com/<your-username>/internship-slack-bot.git
cd internship-slack-bot

cp .env.example .env
```

Edit `.env` and fill in your values:

```dotenv
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_CHANNEL_ID=C0123456789
SLACK_APP_TOKEN=xapp-your-app-token-here
GITHUB_REPO_URL=https://github.com/vanshb03/Summer2026-Internships
CHECK_INTERVAL_SECONDS=60
```

---

## 4. Run locally

```bash
# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the bot (loops every CHECK_INTERVAL_SECONDS)
python mainbot.py
```

On first run the bot clones the internship repo and announces every active listing it hasn't seen before, then writes `seen_ids.json` to disk. On subsequent runs it only announces truly new postings.

To do a single check and exit (useful for testing):

```bash
RUN_ONCE=true python mainbot.py
```

---

## 5. Run via GitHub Actions

The included workflow (`.github/workflows/run_bot.yml`) runs the bot on a **cron schedule every 5 minutes** (the minimum interval GitHub Actions allows) and on every push to `main`.

### Set up secrets

In your fork on GitHub, go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Value |
|---|---|
| `SLACK_BOT_TOKEN` | Your `xoxb-` token |
| `SLACK_CHANNEL_ID` | The `C…` channel ID |

The workflow uses `actions/cache` to persist `seen_ids.json` between runs so postings are never announced twice.

> **Cron lag**: GitHub Actions cron jobs can be delayed by several minutes during high-load periods. If real-time alerts are critical, run the bot locally or on a dedicated server instead.

---

## 6. Project structure

```
internship-slack-bot/
├── mainbot.py             # Entrypoint — orchestrates the check cycle
├── formatter.py           # Builds Slack Block Kit payloads
├── repo_manager.py        # git clone / pull logic
├── state_manager.py       # seen_ids.json read/write and diff logic
├── allowlist_manager.py   # allowlist.json load/save/query (thread-safe)
├── bot_listener.py        # Bolt Socket Mode listener for "add <company>"
├── test_mainbot.py        # pytest test suite (42 tests)
├── requirements.txt
├── .env.example           # Config template (copy to .env)
├── .gitignore
└── .github/
    └── workflows/
        └── run_bot.yml    # GitHub Actions CI workflow
```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | Yes | — | Bot OAuth token (`xoxb-…`) |
| `SLACK_CHANNEL_ID` | Yes | — | Slack channel to post in |
| `SLACK_APP_TOKEN` | No* | — | App-level token (`xapp-…`) for Socket Mode / "add" command |
| `GITHUB_REPO_URL` | No | `https://github.com/vanshb03/Summer2026-Internships` | Internship listings repo |
| `CHECK_INTERVAL_SECONDS` | No | `60` | Seconds between checks (local loop mode) |
| `RUN_ONCE` | No | `false` | Set `true` to run once and exit (GitHub Actions) |

\* Required to enable the `add <company>` Slack command. Without it the bot still posts listings but ignores messages.

### Company allowlist

On first run the bot creates `allowlist.json` seeded with ~50 well-known tech companies. Only postings whose company name matches an entry (case-insensitive) are announced.

**To add a company at runtime**, post in the monitored channel:
```
add Figma
```
The bot replies in-thread and immediately starts filtering for that company.

---

## 7. Running tests

```bash
pip install -r requirements.txt
pytest test_mainbot.py -v
```

The test suite covers:

- `formatter.format_message()` — Block Kit structure, fields, apply button, edge cases
- `state_manager.diff_listings()` — new vs seen, active vs inactive, hidden listings
- `state_manager` persistence — round-trip read/write, corrupt-file recovery
- `mainbot.check_cycle()` — Slack posting with mocked client, seen-ID persistence, error resilience
