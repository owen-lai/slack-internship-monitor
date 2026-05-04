# Internship Slack Bot

Monitors the [vanshb03/Summer2026-Internships](https://github.com/vanshb03/Summer2026-Internships) GitHub repo for new internship postings and sends formatted alerts to a Slack channel via Block Kit messages.

Runs as a GitHub Actions cron job every 5 minutes. Seen-post state is persisted across ephemeral runners in a private GitHub Gist.

```
New Internship Posting
──────────────────────────────────────────
Company        Google
Role           Software Engineer Intern
Location(s)    San Francisco, CA, Remote
Sponsorship    ✅ Sponsors
Date Posted    Apr 25, 2024
                                [Apply 🚀]
```

---

## Table of contents

1. [Create a Slack app](#1-create-a-slack-app)
2. [Create a private GitHub Gist for state](#2-create-a-private-github-gist-for-state)
3. [Create a GitHub personal access token](#3-create-a-github-personal-access-token)
4. [Clone this repo and configure .env](#4-clone-this-repo-and-configure-env)
5. [Run via GitHub Actions](#5-run-via-github-actions)
6. [Run locally](#6-run-locally)
7. [Project structure](#7-project-structure)
8. [Running tests](#8-running-tests)

---

## 1. Create a Slack app

1. Go to <https://api.slack.com/apps> and click **Create New App → From scratch**.
2. Give it a name (e.g. `Internship Monitor`) and pick your workspace.
3. In the left sidebar, open **OAuth & Permissions**.
4. Under **Bot Token Scopes**, click **Add an OAuth Scope** and add:
   - `chat:write`
5. Scroll up and click **Install to Workspace**, then **Allow**.
6. Copy the **Bot User OAuth Token** (starts with `xoxb-`). This is your `SLACK_BOT_TOKEN`.

> **Invite the bot to your channel**: In Slack, open the channel and type `/invite @YourBotName`.

| Value | Where to find it |
|---|---|
| **Bot token** (`xoxb-…`) | Slack app → OAuth & Permissions → Bot User OAuth Token |
| **Channel ID** | Open the channel → right-click → **View channel details** → copy the ID at the bottom (starts with `C`) |

---

## 2. Create a private GitHub Gist for state

Because each GitHub Actions runner is ephemeral, seen-post state is stored in a private Gist.

1. Go to <https://gist.github.com> and create a **secret** (private) Gist.
2. Set the filename to `seen_ids.json` and the content to `{}`.
3. Click **Create secret gist**.
4. Copy the Gist ID from the URL: `https://gist.github.com/<username>/<GIST_ID>`.

---

## 3. Create a GitHub personal access token

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**.
2. Click **Generate new token (classic)**.
3. Give it a descriptive name (e.g. `internship-bot-gist`), set an expiry, and check only the **`gist`** scope.
4. Copy the token (starts with `ghp-`). This is your `GHUB_TOKEN`.

---

## 4. Clone this repo and configure .env

```bash
git clone https://github.com/<your-username>/internship-slack-bot.git
cd internship-slack-bot

cp .env.example .env
```

Edit `.env`:

```dotenv
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_CHANNEL_ID=C0123456789
GITHUB_REPO_URL=https://github.com/vanshb03/Summer2026-Internships
GHUB_TOKEN=ghp-your-personal-access-token-here
GIST_ID=your-gist-id-here
```

---

## 5. Run via GitHub Actions

The included workflow (`.github/workflows/run_bot.yml`) runs every **5 minutes** and on every push to `main`.

### Set up repository secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Value |
|---|---|
| `SLACK_BOT_TOKEN` | Your `xoxb-` bot token |
| `SLACK_CHANNEL_ID` | The `C…` channel ID |
| `GHUB_TOKEN` | Your PAT with `gist` scope (`ghp-…`) |
| `GIST_ID` | The ID of your private Gist |

On the first run the bot bootstraps: it records all current listings as seen without posting anything. Every subsequent run posts only new listings.

> **Cron lag**: GitHub Actions cron jobs can be delayed by a few minutes during high load. This is expected.

---

## 6. Run locally

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python mainbot.py
```

The bot performs one check cycle and exits, same as in CI.

---

## 7. Project structure

```
internship-slack-bot/
├── mainbot.py            # Entrypoint — always runs once and exits
├── formatter.py          # Builds Slack Block Kit payloads
├── repo_manager.py       # git clone / pull logic
├── state_manager.py      # GitHub Gist-backed seen-ID persistence + diff logic
├── allowlist_manager.py  # allowlist.json load and query
├── allowlist.json        # Committed company allowlist — edit via PR to add companies
├── test_mainbot.py       # pytest test suite (48 tests)
├── requirements.txt
├── .env.example          # Config template (copy to .env)
├── .gitignore
└── .github/
    └── workflows/
        └── run_bot.yml   # GitHub Actions CI/cron workflow
```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | Yes | — | Bot OAuth token (`xoxb-…`) |
| `SLACK_CHANNEL_ID` | Yes | — | Slack channel to post in |
| `GHUB_TOKEN` | Yes | — | PAT with `gist` scope for state persistence |
| `GIST_ID` | Yes | — | ID of the private Gist storing `seen_ids.json` |
| `GITHUB_REPO_URL` | No | `https://github.com/vanshb03/Summer2026-Internships` | Internship listings repo |

### Company allowlist

`allowlist.json` is committed to the repo and seeded with ~50 well-known tech companies. Only postings whose company name matches an entry (case-insensitive) are announced.

**To add a company**: edit `allowlist.json` and open a PR. Once merged, the next cron run picks it up automatically.

---

## 8. Running tests

```bash
pip install -r requirements.txt
pytest test_mainbot.py -v
```

The test suite (48 tests) covers:

- `formatter.format_message()` — Block Kit structure, fields, apply button, edge cases
- `state_manager.diff_listings()` — new vs seen, active vs inactive, hidden listings
- `state_manager` Gist I/O — successful fetch, network errors, HTTP errors, bad JSON, empty Gist, push payload and auth header
- `allowlist_manager` — case-insensitive matching, default seeding, corrupt-file recovery
- `mainbot.check_cycle()` — posting, dedup, allowlist filtering, bootstrap mode, error resilience
- `mainbot.main()` — Gist fetch/push wired correctly, bootstrap flag propagated
