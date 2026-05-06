"""
test_mainbot.py — Unit tests for the internship Slack bot.

Run with:  pytest test_mainbot.py -v
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

import pytest

# ---------------------------------------------------------------------------
# Shared sample data
# ---------------------------------------------------------------------------

SAMPLE_LISTING_ACTIVE = {
    "id": "abc123",
    "company_name": "Acme Corp",
    "title": "Software Engineer Intern",
    "locations": ["San Francisco, CA", "Remote"],
    "url": "https://example.com/apply",
    "date_posted": 1714000000,
    "active": True,
    "is_visible": True,
    "sponsorship": "Sponsors",
}

SAMPLE_LISTING_INACTIVE = {
    "id": "dead456",
    "company_name": "Closed Co",
    "title": "Backend Intern",
    "locations": ["New York, NY"],
    "url": "https://example.com/apply2",
    "date_posted": 1714000001,
    "active": False,
    "is_visible": True,
    "sponsorship": "Does Not Offer Sponsorship",
}

SAMPLE_LISTING_HIDDEN = {
    "id": "hidden789",
    "company_name": "Secret Inc",
    "title": "Data Intern",
    "locations": ["Austin, TX"],
    "url": "https://example.com/apply3",
    "date_posted": 1714000002,
    "active": True,
    "is_visible": False,
    "sponsorship": "Unknown",
}


# ---------------------------------------------------------------------------
# formatter tests
# ---------------------------------------------------------------------------

class TestFormatMessage:
    def test_returns_text_and_blocks(self):
        import formatter
        payload = formatter.format_message(SAMPLE_LISTING_ACTIVE)
        assert "text" in payload
        assert "blocks" in payload
        assert isinstance(payload["blocks"], list)

    def test_fallback_text_contains_company_and_title(self):
        import formatter
        payload = formatter.format_message(SAMPLE_LISTING_ACTIVE)
        assert "Acme Corp" in payload["text"]
        assert "Software Engineer Intern" in payload["text"]

    def test_header_block_present(self):
        import formatter
        payload = formatter.format_message(SAMPLE_LISTING_ACTIVE)
        header_blocks = [b for b in payload["blocks"] if b.get("type") == "header"]
        assert len(header_blocks) == 1

    def test_section_block_contains_company_field(self):
        import formatter
        payload = formatter.format_message(SAMPLE_LISTING_ACTIVE)
        section_blocks = [b for b in payload["blocks"] if b.get("type") == "section"]
        assert len(section_blocks) >= 1
        fields_text = " ".join(f["text"] for f in section_blocks[0]["fields"])
        assert "Acme Corp" in fields_text

    def test_apply_button_present_when_url_given(self):
        import formatter
        payload = formatter.format_message(SAMPLE_LISTING_ACTIVE)
        action_blocks = [b for b in payload["blocks"] if b.get("type") == "actions"]
        assert len(action_blocks) == 1
        button = action_blocks[0]["elements"][0]
        assert button["type"] == "button"
        assert button["url"] == "https://example.com/apply"

    def test_no_apply_button_when_no_url(self):
        import formatter
        listing = {**SAMPLE_LISTING_ACTIVE, "url": ""}
        payload = formatter.format_message(listing)
        action_blocks = [b for b in payload["blocks"] if b.get("type") == "actions"]
        assert len(action_blocks) == 0

    def test_locations_joined_with_comma(self):
        import formatter
        payload = formatter.format_message(SAMPLE_LISTING_ACTIVE)
        section_blocks = [b for b in payload["blocks"] if b.get("type") == "section"]
        fields_text = " ".join(f["text"] for f in section_blocks[0]["fields"])
        assert "San Francisco, CA" in fields_text
        assert "Remote" in fields_text

    def test_sponsorship_sponsors_label(self):
        import formatter
        payload = formatter.format_message(SAMPLE_LISTING_ACTIVE)
        section_blocks = [b for b in payload["blocks"] if b.get("type") == "section"]
        fields_text = " ".join(f["text"] for f in section_blocks[0]["fields"])
        assert "Sponsors" in fields_text

    def test_sponsorship_no_sponsorship_label(self):
        import formatter
        payload = formatter.format_message(SAMPLE_LISTING_INACTIVE)
        section_blocks = [b for b in payload["blocks"] if b.get("type") == "section"]
        fields_text = " ".join(f["text"] for f in section_blocks[0]["fields"])
        assert "No Sponsorship" in fields_text

    def test_date_posted_formatted(self):
        import formatter
        payload = formatter.format_message(SAMPLE_LISTING_ACTIVE)
        section_blocks = [b for b in payload["blocks"] if b.get("type") == "section"]
        fields_text = " ".join(f["text"] for f in section_blocks[0]["fields"])
        # epoch 1714000000 → Apr 25, 2024
        assert "2024" in fields_text

    def test_missing_fields_dont_crash(self):
        import formatter
        payload = formatter.format_message({"id": "x"})
        assert "text" in payload
        assert "blocks" in payload

    def test_divider_is_last_block(self):
        import formatter
        payload = formatter.format_message(SAMPLE_LISTING_ACTIVE)
        assert payload["blocks"][-1]["type"] == "divider"


# ---------------------------------------------------------------------------
# state_manager.diff_listings tests
# ---------------------------------------------------------------------------

class TestDiffListings:
    def test_new_active_listing_returned(self):
        from state_manager import diff_listings
        result = diff_listings([SAMPLE_LISTING_ACTIVE], seen_ids=set())
        assert len(result) == 1
        assert result[0]["id"] == "abc123"

    def test_already_seen_listing_excluded(self):
        from state_manager import diff_listings
        result = diff_listings([SAMPLE_LISTING_ACTIVE], seen_ids={"abc123"})
        assert result == []

    def test_inactive_listing_excluded(self):
        from state_manager import diff_listings
        result = diff_listings([SAMPLE_LISTING_INACTIVE], seen_ids=set())
        assert result == []

    def test_hidden_listing_excluded(self):
        from state_manager import diff_listings
        result = diff_listings([SAMPLE_LISTING_HIDDEN], seen_ids=set())
        assert result == []

    def test_inactive_listing_added_to_seen(self):
        from state_manager import diff_listings
        seen = set()
        diff_listings([SAMPLE_LISTING_INACTIVE], seen_ids=seen)
        assert "dead456" in seen

    def test_hidden_listing_added_to_seen(self):
        from state_manager import diff_listings
        seen = set()
        diff_listings([SAMPLE_LISTING_HIDDEN], seen_ids=seen)
        assert "hidden789" in seen

    def test_mixed_listings_only_new_active_returned(self):
        from state_manager import diff_listings
        listings = [
            SAMPLE_LISTING_ACTIVE,
            SAMPLE_LISTING_INACTIVE,
            SAMPLE_LISTING_HIDDEN,
            {**SAMPLE_LISTING_ACTIVE, "id": "already_seen"},
        ]
        result = diff_listings(listings, seen_ids={"already_seen"})
        assert len(result) == 1
        assert result[0]["id"] == "abc123"

    def test_listing_without_id_skipped(self):
        from state_manager import diff_listings
        listing_no_id = {"company_name": "No ID Co", "active": True, "is_visible": True}
        result = diff_listings([listing_no_id], seen_ids=set())
        assert result == []

    def test_defaults_active_true_when_key_missing(self):
        from state_manager import diff_listings
        listing = {
            "id": "noflag999",
            "company_name": "Flags Missing",
            "title": "Intern",
            "url": "https://example.com",
        }
        result = diff_listings([listing], seen_ids=set())
        assert len(result) == 1

    def test_multiple_new_listings_all_returned(self):
        from state_manager import diff_listings
        l2 = {**SAMPLE_LISTING_ACTIVE, "id": "second"}
        result = diff_listings([SAMPLE_LISTING_ACTIVE, l2], seen_ids=set())
        ids = {r["id"] for r in result}
        assert ids == {"abc123", "second"}


# ---------------------------------------------------------------------------
# state_manager Gist I/O tests
# ---------------------------------------------------------------------------

class TestGistState:
    GIST_ID = "abc123gist"
    TOKEN = "ghp-fake-token"

    def _make_gist_response(self, content: str) -> Mock:
        resp = Mock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "files": {
                "seen_ids.json": {"content": content}
            }
        }
        return resp

    def test_fetch_populates_seen_ids(self):
        from state_manager import fetch_seen_ids
        ids_json = json.dumps(["id1", "id2", "id3"])
        mock_resp = self._make_gist_response(ids_json)

        with patch("state_manager.requests.get", return_value=mock_resp) as mock_get:
            seen, is_bootstrap = fetch_seen_ids(self.GIST_ID, self.TOKEN)

        assert seen == {"id1", "id2", "id3"}
        assert is_bootstrap is False
        mock_get.assert_called_once()

    def test_fetch_sends_auth_header(self):
        from state_manager import fetch_seen_ids
        mock_resp = self._make_gist_response(json.dumps(["x"]))

        with patch("state_manager.requests.get", return_value=mock_resp) as mock_get:
            fetch_seen_ids(self.GIST_ID, self.TOKEN)

        _, kwargs = mock_get.call_args
        assert f"Bearer {self.TOKEN}" in kwargs["headers"]["Authorization"]

    def test_fetch_returns_bootstrap_on_network_error(self):
        from state_manager import fetch_seen_ids
        with patch("state_manager.requests.get", side_effect=ConnectionError("timeout")):
            seen, is_bootstrap = fetch_seen_ids(self.GIST_ID, self.TOKEN)
        assert seen == set()
        assert is_bootstrap is True

    def test_fetch_returns_bootstrap_on_http_error(self):
        import requests as req
        from state_manager import fetch_seen_ids
        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("500")

        with patch("state_manager.requests.get", return_value=mock_resp):
            seen, is_bootstrap = fetch_seen_ids(self.GIST_ID, self.TOKEN)

        assert is_bootstrap is True

    def test_fetch_returns_bootstrap_on_empty_content(self):
        from state_manager import fetch_seen_ids
        mock_resp = self._make_gist_response("")

        with patch("state_manager.requests.get", return_value=mock_resp):
            seen, is_bootstrap = fetch_seen_ids(self.GIST_ID, self.TOKEN)

        assert is_bootstrap is True

    def test_fetch_returns_bootstrap_on_initial_empty_gist(self):
        from state_manager import fetch_seen_ids
        mock_resp = self._make_gist_response("{}")

        with patch("state_manager.requests.get", return_value=mock_resp):
            seen, is_bootstrap = fetch_seen_ids(self.GIST_ID, self.TOKEN)

        assert is_bootstrap is True

    def test_fetch_returns_bootstrap_on_bad_json(self):
        from state_manager import fetch_seen_ids
        mock_resp = self._make_gist_response("{not valid json")

        with patch("state_manager.requests.get", return_value=mock_resp):
            seen, is_bootstrap = fetch_seen_ids(self.GIST_ID, self.TOKEN)

        assert is_bootstrap is True

    def test_fetch_returns_bootstrap_when_content_is_object_not_array(self):
        from state_manager import fetch_seen_ids
        mock_resp = self._make_gist_response('{"id1": true}')

        with patch("state_manager.requests.get", return_value=mock_resp):
            seen, is_bootstrap = fetch_seen_ids(self.GIST_ID, self.TOKEN)

        assert is_bootstrap is True

    def test_push_writes_updated_state(self):
        from state_manager import push_seen_ids
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None

        with patch("state_manager.requests.patch", return_value=mock_resp) as mock_patch:
            push_seen_ids(self.GIST_ID, self.TOKEN, {"id1", "id2"})

        mock_patch.assert_called_once()
        _, kwargs = mock_patch.call_args
        content = kwargs["json"]["files"]["seen_ids.json"]["content"]
        stored = json.loads(content)
        assert set(stored) == {"id1", "id2"}

    def test_push_sends_auth_header(self):
        from state_manager import push_seen_ids
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None

        with patch("state_manager.requests.patch", return_value=mock_resp) as mock_patch:
            push_seen_ids(self.GIST_ID, self.TOKEN, {"x"})

        _, kwargs = mock_patch.call_args
        assert f"Bearer {self.TOKEN}" in kwargs["headers"]["Authorization"]

    def test_push_logs_on_failure_without_crash(self):
        from state_manager import push_seen_ids
        with patch("state_manager.requests.patch", side_effect=ConnectionError("down")):
            # Must not raise
            push_seen_ids(self.GIST_ID, self.TOKEN, {"id1"})


# ---------------------------------------------------------------------------
# allowlist_manager tests
# ---------------------------------------------------------------------------

class TestAllowlistManager:
    @pytest.fixture(autouse=True)
    def _tmp(self, tmp_path, monkeypatch):
        import allowlist_manager
        monkeypatch.setattr(allowlist_manager, "ALLOWLIST_FILE", tmp_path / "allowlist.json")

    def test_is_allowed_case_insensitive(self):
        import allowlist_manager
        allowlist_manager._save_unsafe(["google"])
        assert allowlist_manager.is_allowed("Google") is True
        assert allowlist_manager.is_allowed("GOOGLE") is True
        assert allowlist_manager.is_allowed("  google  ") is True

    def test_is_allowed_returns_false_for_unknown(self):
        import allowlist_manager
        allowlist_manager._save_unsafe(["google"])
        assert allowlist_manager.is_allowed("Unknown Corp") is False

    def test_seeds_defaults_on_first_run(self):
        import allowlist_manager
        entries = allowlist_manager.load()
        assert "google" in entries
        assert "anthropic" in entries
        assert allowlist_manager.ALLOWLIST_FILE.exists()

    def test_load_corrupt_file_returns_defaults(self):
        import allowlist_manager
        allowlist_manager.ALLOWLIST_FILE.write_text("{bad json", encoding="utf-8")
        entries = allowlist_manager.load()
        assert "google" in entries

    def test_original_casing_lowercased_on_load(self):
        import allowlist_manager
        allowlist_manager._save_unsafe(["Google", "Meta"])
        entries = allowlist_manager.load()
        assert "google" in entries
        assert "meta" in entries
        assert "Google" not in entries


# ---------------------------------------------------------------------------
# mainbot integration tests (Slack client + Gist mocked)
# ---------------------------------------------------------------------------

class TestCheckCycle:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch, tmp_path):
        import allowlist_manager
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C123456")
        monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/test/repo")
        monkeypatch.setenv("GIST_ID", "fake-gist-id")
        monkeypatch.setenv("GHUB_TOKEN", "ghp-fake")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(allowlist_manager, "ALLOWLIST_FILE", tmp_path / "allowlist.json")
        allowlist_manager._save_unsafe(["acme corp"])

    def _make_client_mock(self):
        client = MagicMock()
        client.chat_postMessage.return_value = {"ok": True}
        return client

    def test_new_listing_triggers_slack_post(self, tmp_path):
        import mainbot
        client = self._make_client_mock()

        with (
            patch("mainbot.repo_manager.ensure_repo", return_value=tmp_path),
            patch("mainbot.load_all_listings", return_value=[SAMPLE_LISTING_ACTIVE]),
        ):
            mainbot.check_cycle(
                client, seen_ids=set(), repo_url="https://github.com/test/repo",
                channel="C123456",
            )

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args.kwargs
        assert call_kwargs["channel"] == "C123456"
        assert "blocks" in call_kwargs

    def test_seen_listing_not_reposted(self, tmp_path):
        import mainbot
        client = self._make_client_mock()

        with (
            patch("mainbot.repo_manager.ensure_repo", return_value=tmp_path),
            patch("mainbot.load_all_listings", return_value=[SAMPLE_LISTING_ACTIVE]),
        ):
            mainbot.check_cycle(
                client, seen_ids={"abc123"}, repo_url="https://github.com/test/repo",
                channel="C123456",
            )

        client.chat_postMessage.assert_not_called()

    def test_git_failure_does_not_crash(self, tmp_path):
        import mainbot
        client = self._make_client_mock()

        with patch("mainbot.repo_manager.ensure_repo", side_effect=RuntimeError("git pull failed")):
            mainbot.check_cycle(
                client, seen_ids=set(), repo_url="https://github.com/test/repo",
                channel="C123456",
            )

        client.chat_postMessage.assert_not_called()

    def test_slack_api_error_does_not_crash(self, tmp_path):
        from slack_sdk.errors import SlackApiError
        import mainbot
        client = self._make_client_mock()
        client.chat_postMessage.side_effect = SlackApiError(
            "channel_not_found", {"error": "channel_not_found", "ok": False}
        )

        with (
            patch("mainbot.repo_manager.ensure_repo", return_value=tmp_path),
            patch("mainbot.load_all_listings", return_value=[SAMPLE_LISTING_ACTIVE]),
        ):
            mainbot.check_cycle(
                client, seen_ids=set(), repo_url="https://github.com/test/repo",
                channel="C123456",
            )
        # Error was logged; no exception propagated

    def test_seen_ids_returned_after_cycle(self, tmp_path):
        import mainbot
        client = self._make_client_mock()

        with (
            patch("mainbot.repo_manager.ensure_repo", return_value=tmp_path),
            patch("mainbot.load_all_listings", return_value=[SAMPLE_LISTING_ACTIVE]),
        ):
            updated = mainbot.check_cycle(
                client, seen_ids=set(), repo_url="https://github.com/test/repo",
                channel="C123456",
            )

        assert "abc123" in updated

    def test_non_allowlisted_company_is_posted_without_ping(self, tmp_path):
        import allowlist_manager, mainbot
        allowlist_manager._save_unsafe(["google"])
        client = self._make_client_mock()
        unlisted_listing = {**SAMPLE_LISTING_ACTIVE, "id": "xyz", "company_name": "Acme Corp"}

        with (
            patch("mainbot.repo_manager.ensure_repo", return_value=tmp_path),
            patch("mainbot.load_all_listings", return_value=[unlisted_listing]),
        ):
            mainbot.check_cycle(
                client, seen_ids=set(), repo_url="https://github.com/test/repo",
                channel="C123456",
            )

        client.chat_postMessage.assert_called_once()
        text = client.chat_postMessage.call_args.kwargs["text"]
        assert "<!here>" not in text

    def test_allowlisted_company_is_posted_with_ping(self, tmp_path):
        import allowlist_manager, mainbot
        allowlist_manager._save_unsafe(["google"])
        client = self._make_client_mock()
        google_listing = {**SAMPLE_LISTING_ACTIVE, "id": "goog1", "company_name": "Google"}

        with (
            patch("mainbot.repo_manager.ensure_repo", return_value=tmp_path),
            patch("mainbot.load_all_listings", return_value=[google_listing]),
        ):
            mainbot.check_cycle(
                client, seen_ids=set(), repo_url="https://github.com/test/repo",
                channel="C123456",
            )

        client.chat_postMessage.assert_called_once()
        text = client.chat_postMessage.call_args.kwargs["text"]
        assert "<!here>" in text

    def test_bootstrap_mode_skips_posting(self, tmp_path):
        import mainbot
        client = self._make_client_mock()

        with (
            patch("mainbot.repo_manager.ensure_repo", return_value=tmp_path),
            patch("mainbot.load_all_listings", return_value=[SAMPLE_LISTING_ACTIVE]),
        ):
            updated = mainbot.check_cycle(
                client, seen_ids=set(), repo_url="https://github.com/test/repo",
                channel="C123456", post_enabled=False,
            )

        client.chat_postMessage.assert_not_called()
        # ID still recorded so it won't fire on the next (non-bootstrap) run
        assert "abc123" in updated

    def test_gist_fetch_and_push_called_in_main(self, tmp_path):
        import mainbot
        client_mock = self._make_client_mock()

        with (
            patch("mainbot.WebClient", return_value=client_mock),
            patch("mainbot.state_manager.fetch_seen_ids", return_value=(set(), False)) as mock_fetch,
            patch("mainbot.state_manager.push_seen_ids") as mock_push,
            patch("mainbot.check_cycle", return_value={"some-id"}) as mock_cycle,
        ):
            mainbot.main()

        mock_fetch.assert_called_once_with("fake-gist-id", "ghp-fake")
        mock_push.assert_called_once_with("fake-gist-id", "ghp-fake", {"some-id"})
        mock_cycle.assert_called_once()

    def test_bootstrap_flag_propagated_from_gist_failure(self, tmp_path):
        import mainbot
        client_mock = self._make_client_mock()

        with (
            patch("mainbot.WebClient", return_value=client_mock),
            patch("mainbot.state_manager.fetch_seen_ids", return_value=(set(), True)),
            patch("mainbot.state_manager.push_seen_ids"),
            patch("mainbot.check_cycle", return_value=set()) as mock_cycle,
        ):
            mainbot.main()

        _, kwargs = mock_cycle.call_args
        assert kwargs.get("post_enabled") is False
