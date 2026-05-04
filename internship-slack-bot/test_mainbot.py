"""
test_mainbot.py — Unit tests for the internship Slack bot.

Run with:  pytest test_mainbot.py -v
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
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
# state_manager persistence tests
# ---------------------------------------------------------------------------

class TestStatePersistence:
    def test_round_trip(self, tmp_path, monkeypatch):
        import state_manager
        monkeypatch.setattr(state_manager, "STATE_FILE", tmp_path / "seen_ids.json")

        original = {"id1", "id2", "id3"}
        state_manager.save_seen_ids(original)
        loaded = state_manager.load_seen_ids()
        assert loaded == original

    def test_load_missing_file_returns_empty_set(self, tmp_path, monkeypatch):
        import state_manager
        monkeypatch.setattr(
            state_manager, "STATE_FILE", tmp_path / "nonexistent.json"
        )
        result = state_manager.load_seen_ids()
        assert result == set()

    def test_load_corrupt_file_returns_empty_set(self, tmp_path, monkeypatch):
        import state_manager
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(state_manager, "STATE_FILE", bad_file)
        result = state_manager.load_seen_ids()
        assert result == set()

    def test_save_creates_valid_json_array(self, tmp_path, monkeypatch):
        import state_manager
        path = tmp_path / "seen_ids.json"
        monkeypatch.setattr(state_manager, "STATE_FILE", path)

        state_manager.save_seen_ids({"a", "b", "c"})
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert set(data) == {"a", "b", "c"}

    def test_overwrite_preserves_new_set(self, tmp_path, monkeypatch):
        import state_manager
        monkeypatch.setattr(state_manager, "STATE_FILE", tmp_path / "seen_ids.json")

        state_manager.save_seen_ids({"old1", "old2"})
        state_manager.save_seen_ids({"new1"})
        loaded = state_manager.load_seen_ids()
        assert loaded == {"new1"}


# ---------------------------------------------------------------------------
# mainbot integration tests (Slack client mocked)
# ---------------------------------------------------------------------------

class TestCheckCycle:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C123456")
        monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/test/repo")
        monkeypatch.chdir(tmp_path)

    def _make_client_mock(self):
        client = MagicMock()
        client.chat_postMessage.return_value = {"ok": True}
        return client

    def test_new_listing_triggers_slack_post(self, tmp_path):
        import mainbot, state_manager
        client = self._make_client_mock()

        with (
            patch("mainbot.repo_manager.ensure_repo", return_value=tmp_path),
            patch("mainbot.load_listings", return_value=[SAMPLE_LISTING_ACTIVE]),
        ):
            mainbot.check_cycle(client)

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args.kwargs
        assert call_kwargs["channel"] == "C123456"
        assert "blocks" in call_kwargs

    def test_seen_listing_not_reposted(self, tmp_path):
        import mainbot, state_manager
        # Pre-populate seen state
        state_manager.save_seen_ids({"abc123"})
        client = self._make_client_mock()

        with (
            patch("mainbot.repo_manager.ensure_repo", return_value=tmp_path),
            patch("mainbot.load_listings", return_value=[SAMPLE_LISTING_ACTIVE]),
        ):
            mainbot.check_cycle(client)

        client.chat_postMessage.assert_not_called()

    def test_git_failure_does_not_crash(self, tmp_path):
        import mainbot
        client = self._make_client_mock()

        with patch(
            "mainbot.repo_manager.ensure_repo",
            side_effect=RuntimeError("git pull failed"),
        ):
            # Should log the error and return cleanly
            mainbot.check_cycle(client)

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
            patch("mainbot.load_listings", return_value=[SAMPLE_LISTING_ACTIVE]),
        ):
            mainbot.check_cycle(client)

        # Error was logged; no exception propagated

    def test_seen_ids_persisted_after_cycle(self, tmp_path):
        import mainbot, state_manager
        client = self._make_client_mock()

        with (
            patch("mainbot.repo_manager.ensure_repo", return_value=tmp_path),
            patch("mainbot.load_listings", return_value=[SAMPLE_LISTING_ACTIVE]),
        ):
            mainbot.check_cycle(client)

        seen = state_manager.load_seen_ids()
        assert "abc123" in seen
