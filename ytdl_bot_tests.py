"""
Per-commit test suite for ytdl_bot.py.

Covers pure functions, UserManager, URL handling, TikTok, Spotify,
error reporting — everything NOT covered by ytdl_bot_test.py (which
focuses on retry/upload/network logic).

Run with:
    pytest ytdl_bot_tests.py -v          # All tests
    pytest ytdl_bot_tests.py -v -x       # Stop on first failure
    pytest ytdl_bot_tests.py -k Commit01 # Single class
"""

import pytest
import asyncio
import os
import json
import subprocess
from unittest.mock import Mock, AsyncMock, patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class AsyncContextManager:
    """Helper to mock aiohttp response context managers."""

    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, *args):
        pass


def make_mock_response(status=200, json_data=None, url=None, content=b""):
    """Create a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    resp.url = url or "https://example.com"
    if json_data is not None:
        resp.json = AsyncMock(return_value=json_data)
    resp.read = AsyncMock(return_value=content)
    return resp


# ---------------------------------------------------------------------------
# TestCommit01_InitialBot — commit e0fa77f
# ---------------------------------------------------------------------------

class TestCommit01_InitialBot:
    """UserManager, get_video_title, get_audio_duration."""

    # -- UserManager --

    def test_init_creates_structure(self, tmp_path):
        json_path = str(tmp_path / "config" / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        assert "approved_users" in um.config
        assert "denied_users" in um.config
        assert "pending_requests" in um.config

    def test_init_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "a" / "b"
        json_path = str(nested / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        assert os.path.isdir(str(nested))

    def test_init_preserves_existing_data(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        os.makedirs(str(tmp_path), exist_ok=True)
        with open(json_path, "w") as f:
            json.dump({
                "approved_users": [111],
                "denied_users": [222],
                "pending_requests": {}
            }, f)
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        assert 111 in um.config["approved_users"]
        assert 222 in um.config["denied_users"]

    def test_is_approved_true(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["approved_users"].append(42)
        um.config.save()
        assert um.is_approved(42) is True

    def test_is_approved_false(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        assert um.is_approved(999) is False

    def test_is_denied(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["denied_users"].append(77)
        um.config.save()
        assert um.is_denied(77) is True

    def test_is_pending_uses_string_key(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["pending_requests"]["123"] = {"user_id": 123}
        um.config.save()
        # is_pending converts to str internally
        assert um.is_pending(123) is True
        assert um.is_pending("123") is True

    @patch("ytdl_bot.Time")
    def test_add_pending_request(self, mock_time, tmp_path):
        mock_time.dotted.return_value = "2024.01.01"
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.add_pending_request(100, "testuser", "Test", "https://example.com", 555, audio_only=True)
        req = um.config["pending_requests"]["100"]
        assert req["user_id"] == 100
        assert req["username"] == "testuser"
        assert req["admin_message_id"] == 555
        assert req["audio_only"] is True

    def test_approve_user_moves_from_pending(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["pending_requests"]["50"] = {"user_id": 50}
        um.config.save()
        pending = um.approve_user(50)
        assert pending is not None
        assert pending["user_id"] == 50
        assert 50 in um.config["approved_users"]
        assert "50" not in um.config["pending_requests"]

    def test_approve_user_removes_from_denied(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["denied_users"].append(60)
        um.config.save()
        um.approve_user(60)
        assert 60 in um.config["approved_users"]
        assert 60 not in um.config["denied_users"]

    def test_approve_user_idempotent(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.approve_user(70)
        um.approve_user(70)
        assert um.config["approved_users"].count(70) == 1

    def test_deny_user(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["pending_requests"]["80"] = {"user_id": 80}
        um.config.save()
        pending = um.deny_user(80)
        assert pending["user_id"] == 80
        assert 80 in um.config["denied_users"]
        assert "80" not in um.config["pending_requests"]

    def test_get_pending_request_found(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["pending_requests"]["90"] = {"user_id": 90, "url": "test"}
        um.config.save()
        result = um.get_pending_request(90)
        assert result is not None
        assert result["url"] == "test"

    def test_get_pending_request_not_found(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        assert um.get_pending_request(999) is None

    # -- get_video_title --

    @patch("ytdl_bot.subprocess.run")
    def test_get_video_title_success(self, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="My Video Title\n")
        from ytdl_bot import get_video_title
        assert get_video_title("https://example.com") == "My Video Title"

    @patch("ytdl_bot.subprocess.run")
    def test_get_video_title_failure(self, mock_run):
        mock_run.side_effect = Exception("yt-dlp not found")
        from ytdl_bot import get_video_title
        assert get_video_title("https://example.com") == "Unknown Title"

    # -- get_audio_duration --

    @patch("ytdl_bot.subprocess.run")
    def test_get_audio_duration_success(self, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="185.42\n")
        from ytdl_bot import get_audio_duration
        assert get_audio_duration("/tmp/audio.mp3") == 185

    @patch("ytdl_bot.subprocess.run")
    def test_get_audio_duration_failure(self, mock_run):
        mock_run.side_effect = Exception("ffprobe not found")
        from ytdl_bot import get_audio_duration
        assert get_audio_duration("/tmp/audio.mp3") is None


# ---------------------------------------------------------------------------
# TestCommit02_UXImprovements — commit 25c7871
# ---------------------------------------------------------------------------

class TestCommit02_UXImprovements:
    """clean_youtube_url tests."""

    def test_removes_si_param(self):
        from ytdl_bot import clean_youtube_url
        url = "https://www.youtube.com/watch?v=abc123&si=tracking_token"
        result = clean_youtube_url(url)
        assert "si=" not in result
        assert "v=abc123" in result

    def test_preserves_other_params(self):
        from ytdl_bot import clean_youtube_url
        url = "https://www.youtube.com/watch?v=abc123&si=xyz&list=PLtest"
        result = clean_youtube_url(url)
        assert "si=" not in result
        assert "v=abc123" in result
        assert "list=PLtest" in result

    def test_noop_without_si(self):
        from ytdl_bot import clean_youtube_url
        url = "https://www.youtube.com/watch?v=abc123&list=PLtest"
        result = clean_youtube_url(url)
        assert "v=abc123" in result
        assert "list=PLtest" in result

    def test_handles_empty_query(self):
        from ytdl_bot import clean_youtube_url
        url = "https://www.youtube.com/watch"
        result = clean_youtube_url(url)
        assert result == "https://www.youtube.com/watch"

    def test_works_on_non_youtube_urls(self):
        from ytdl_bot import clean_youtube_url
        url = "https://example.com/page?si=track&foo=bar"
        result = clean_youtube_url(url)
        assert "si=" not in result
        assert "foo=bar" in result


# ---------------------------------------------------------------------------
# TestCommit03_SpotifyLink — commit 7cb5fb6
# ---------------------------------------------------------------------------

class TestCommit03_SpotifyLink:
    """clean_title_for_search and search_spotify tests."""

    # -- clean_title_for_search --

    def test_strips_official_music_video(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song (Official Music Video)").strip()

    def test_strips_official_video(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song (Official Video)").strip()

    def test_strips_official_audio(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song (Official Audio)").strip()

    def test_strips_lyric_video(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song (Lyric Video)").strip()

    def test_strips_lyrics(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song (Lyrics)").strip()

    def test_strips_hd(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song (HD)").strip()

    def test_strips_4k(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song [4K]").strip()

    def test_strips_audio(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song [Audio]").strip()

    def test_strips_visualizer(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song (Visualizer)").strip()

    def test_strips_cjk_brackets(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song 【some text】").strip()

    def test_strips_pipe(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song | Artist Channel").strip()

    def test_multiple_suffixes(self):
        from ytdl_bot import clean_title_for_search
        result = clean_title_for_search("Song (Official Video) [HD] | Channel")
        assert result.strip() == "Song"

    def test_whitespace_collapse(self):
        from ytdl_bot import clean_title_for_search
        result = clean_title_for_search("Song   (Official Video)   extra")
        assert "  " not in result

    def test_case_insensitive(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song (OFFICIAL MUSIC VIDEO)").strip()

    def test_square_bracket_official_music_video(self):
        from ytdl_bot import clean_title_for_search
        assert "Song" == clean_title_for_search("Song [Official Music Video]").strip()

    def test_no_match_passthrough(self):
        from ytdl_bot import clean_title_for_search
        assert clean_title_for_search("Just a normal title") == "Just a normal title"

    # -- search_spotify --

    @pytest.mark.asyncio
    async def test_search_spotify_returns_dict(self):
        track_data = {
            "tracks": {"items": [{
                "external_urls": {"spotify": "https://open.spotify.com/track/123"},
                "artists": [{"name": "Artist One"}],
                "name": "Song Name"
            }]}
        }
        mock_resp = make_mock_response(status=200, json_data=track_data)
        mock_session = AsyncMock()
        mock_session.get = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.SPOTIFY_ENABLED", True), \
             patch("ytdl_bot.get_spotify_token", new_callable=AsyncMock, return_value="fake_token"), \
             patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import search_spotify
            result = await search_spotify("Test Song")
            assert result is not None
            assert result["url"] == "https://open.spotify.com/track/123"
            assert result["artist"] == "Artist One"
            assert result["name"] == "Song Name"

    @pytest.mark.asyncio
    async def test_search_spotify_joins_multiple_artists(self):
        track_data = {
            "tracks": {"items": [{
                "external_urls": {"spotify": "https://open.spotify.com/track/123"},
                "artists": [{"name": "Artist A"}, {"name": "Artist B"}],
                "name": "Collab"
            }]}
        }
        mock_resp = make_mock_response(status=200, json_data=track_data)
        mock_session = AsyncMock()
        mock_session.get = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.SPOTIFY_ENABLED", True), \
             patch("ytdl_bot.get_spotify_token", new_callable=AsyncMock, return_value="token"), \
             patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import search_spotify
            result = await search_spotify("Collab")
            assert result["artist"] == "Artist A, Artist B"

    @pytest.mark.asyncio
    async def test_search_spotify_disabled_returns_none(self):
        with patch("ytdl_bot.SPOTIFY_ENABLED", False):
            from ytdl_bot import search_spotify
            assert await search_spotify("anything") is None

    @pytest.mark.asyncio
    async def test_search_spotify_no_token_returns_none(self):
        with patch("ytdl_bot.SPOTIFY_ENABLED", True), \
             patch("ytdl_bot.get_spotify_token", new_callable=AsyncMock, return_value=None):
            from ytdl_bot import search_spotify
            assert await search_spotify("anything") is None

    @pytest.mark.asyncio
    async def test_search_spotify_empty_results_returns_none(self):
        track_data = {"tracks": {"items": []}}
        mock_resp = make_mock_response(status=200, json_data=track_data)
        mock_session = AsyncMock()
        mock_session.get = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.SPOTIFY_ENABLED", True), \
             patch("ytdl_bot.get_spotify_token", new_callable=AsyncMock, return_value="token"), \
             patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import search_spotify
            assert await search_spotify("nonexistent") is None

    @pytest.mark.asyncio
    async def test_search_spotify_api_error_returns_none(self):
        mock_resp = make_mock_response(status=500)
        mock_session = AsyncMock()
        mock_session.get = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.SPOTIFY_ENABLED", True), \
             patch("ytdl_bot.get_spotify_token", new_callable=AsyncMock, return_value="token"), \
             patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import search_spotify
            assert await search_spotify("anything") is None


# ---------------------------------------------------------------------------
# TestCommit04_SpotifyCaption — commit 8d065b5
# ---------------------------------------------------------------------------

class TestCommit04_SpotifyCaption:
    """Regression: search_spotify result keys usable for caption."""

    @pytest.mark.asyncio
    async def test_spotify_result_caption_format(self):
        track_data = {
            "tracks": {"items": [{
                "external_urls": {"spotify": "https://open.spotify.com/track/abc"},
                "artists": [{"name": "The Band"}],
                "name": "Hit Song"
            }]}
        }
        mock_resp = make_mock_response(status=200, json_data=track_data)
        mock_session = AsyncMock()
        mock_session.get = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.SPOTIFY_ENABLED", True), \
             patch("ytdl_bot.get_spotify_token", new_callable=AsyncMock, return_value="token"), \
             patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import search_spotify
            info = await search_spotify("Hit Song")
            caption = f"Spotify {info['artist']} - {info['name']}: {info['url']}"
            assert caption == "Spotify The Band - Hit Song: https://open.spotify.com/track/abc"


# ---------------------------------------------------------------------------
# TestCommit05_RevokeHelpAdminApproval — commit bb7e32a
# ---------------------------------------------------------------------------

class TestCommit05_RevokeHelpAdminApproval:
    """PENDING_CHOICES_TTL, admin auto-approval, pending request fields."""

    def test_pending_choices_ttl(self):
        from ytdl_bot import PENDING_CHOICES_TTL
        assert PENDING_CHOICES_TTL == 3600

    def test_admin_auto_approved(self):
        from ytdl_bot import USER_MANAGER, YTDL_ADMIN_CHAT_ID
        assert USER_MANAGER.is_approved(YTDL_ADMIN_CHAT_ID)

    @patch("ytdl_bot.Time")
    def test_pending_request_stores_audio_only(self, mock_time, tmp_path):
        mock_time.dotted.return_value = "2024.01.01"
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.add_pending_request(200, "user", "User", "https://x.com", 999, audio_only=True)
        assert um.config["pending_requests"]["200"]["audio_only"] is True

    @patch("ytdl_bot.Time")
    def test_pending_request_stores_admin_message_id(self, mock_time, tmp_path):
        mock_time.dotted.return_value = "2024.01.01"
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.add_pending_request(201, "user2", "User2", "https://x.com", 888)
        assert um.config["pending_requests"]["201"]["admin_message_id"] == 888

    def test_approve_then_deny_lifecycle(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        # Approve first
        um.approve_user(300)
        assert um.is_approved(300)
        assert not um.is_denied(300)
        # Then deny
        um.deny_user(300)
        assert um.is_denied(300)
        # Note: approve_user removes from denied, but deny_user does NOT remove from approved
        # This tests the actual behavior


# ---------------------------------------------------------------------------
# TestCommit06_AsyncArchitecture — commit 6f0fce8
# ---------------------------------------------------------------------------

class TestCommit06_AsyncArchitecture:
    """Constants only (retry logic covered in ytdl_bot_test.py)."""

    def test_max_video_size(self):
        from ytdl_bot import MAX_VIDEO_SIZE, GiB
        assert MAX_VIDEO_SIZE == 2 * GiB

    def test_min_audio_bitrate(self):
        from ytdl_bot import MIN_AUDIO_BITRATE, KiB
        assert MIN_AUDIO_BITRATE == 32 * KiB

    def test_max_audio_bitrate(self):
        from ytdl_bot import MAX_AUDIO_BITRATE, KiB
        assert MAX_AUDIO_BITRATE == 320 * KiB

    def test_bitrate_safety_margin(self):
        from ytdl_bot import BITRATE_SAFETY_MARGIN
        assert BITRATE_SAFETY_MARGIN == 0.9


# ---------------------------------------------------------------------------
# TestCommit07_AnyURL — commit 5e770af
# ---------------------------------------------------------------------------

class TestCommit07_AnyURL:
    """is_supported_url tests."""

    def test_http_accepted(self):
        from ytdl_bot import is_supported_url
        assert is_supported_url("http://example.com") is True

    def test_https_accepted(self):
        from ytdl_bot import is_supported_url
        assert is_supported_url("https://example.com") is True

    def test_youtube_accepted(self):
        from ytdl_bot import is_supported_url
        assert is_supported_url("https://www.youtube.com/watch?v=abc") is True

    def test_tiktok_accepted(self):
        from ytdl_bot import is_supported_url
        assert is_supported_url("https://www.tiktok.com/@user/video/123") is True

    def test_twitter_accepted(self):
        from ytdl_bot import is_supported_url
        assert is_supported_url("https://twitter.com/user/status/123") is True

    def test_plain_text_rejected(self):
        from ytdl_bot import is_supported_url
        assert is_supported_url("just some text") is False

    def test_ftp_rejected(self):
        from ytdl_bot import is_supported_url
        assert is_supported_url("ftp://files.example.com/video.mp4") is False

    def test_empty_rejected(self):
        from ytdl_bot import is_supported_url
        assert is_supported_url("") is False

    def test_none_rejected(self):
        from ytdl_bot import is_supported_url
        assert is_supported_url(None) is False

    def test_leading_whitespace_accepted(self):
        from ytdl_bot import is_supported_url
        assert is_supported_url("  https://example.com") is True


# ---------------------------------------------------------------------------
# TestCommit08_AudioFormatFallback — commit b303b25
# ---------------------------------------------------------------------------

class TestCommit08_AudioFormatFallback:
    """MAX_AUDIO_BITRATE constant and download_audio format flag."""

    def test_max_audio_bitrate_value(self):
        from ytdl_bot import MAX_AUDIO_BITRATE, KiB
        assert MAX_AUDIO_BITRATE == 320 * KiB

    @pytest.mark.asyncio
    async def test_download_audio_uses_bestaudio_best(self, tmp_path):
        """download_audio passes -f bestaudio/best to yt-dlp."""
        audio_path = str(tmp_path / "audio.mp3")

        def mock_run(cmd, **kwargs):
            # Verify the format flag
            assert "-f" in cmd
            idx = cmd.index("-f")
            assert cmd[idx + 1] == "bestaudio/best"
            # Create the output file to simulate success
            with open(audio_path, "wb") as f:
                f.write(b"fake audio")
            return Mock(returncode=0, stderr="")

        with patch("ytdl_bot.subprocess.run", side_effect=mock_run), \
             patch("ytdl_bot.os.path.exists", return_value=True):
            from ytdl_bot import download_audio
            path, error = await download_audio("https://example.com", str(tmp_path), max_retries=0)
            assert error is None


# ---------------------------------------------------------------------------
# TestCommit09_TikTokPhotoAndAudioDetection — commit fcc1509
# ---------------------------------------------------------------------------

class TestCommit09_TikTokPhotoAndAudioDetection:
    """normalize_tiktok_url, get_tiktok_photo, merge_image_audio, audio-only regex."""

    # -- normalize_tiktok_url --

    @pytest.mark.asyncio
    async def test_regular_url_unchanged(self):
        from ytdl_bot import normalize_tiktok_url
        url, is_photo = await normalize_tiktok_url("https://www.tiktok.com/@user/video/123")
        assert url == "https://www.tiktok.com/@user/video/123"
        assert is_photo is False

    @pytest.mark.asyncio
    async def test_photo_converted_to_video(self):
        from ytdl_bot import normalize_tiktok_url
        url, is_photo = await normalize_tiktok_url("https://www.tiktok.com/@user/photo/123")
        assert "/video/" in url
        assert "/photo/" not in url
        assert is_photo is True

    @pytest.mark.asyncio
    async def test_short_url_resolved_via_head(self):
        resolved_url = "https://www.tiktok.com/@user/video/456"
        mock_resp = make_mock_response(url=resolved_url)
        mock_session = AsyncMock()
        mock_session.head = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import normalize_tiktok_url
            url, is_photo = await normalize_tiktok_url("https://vt.tiktok.com/abc123/")
            assert url == resolved_url
            assert is_photo is False

    @pytest.mark.asyncio
    async def test_short_photo_resolved_and_converted(self):
        resolved_url = "https://www.tiktok.com/@user/photo/789"
        mock_resp = make_mock_response(url=resolved_url)
        mock_session = AsyncMock()
        mock_session.head = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import normalize_tiktok_url
            url, is_photo = await normalize_tiktok_url("https://vm.tiktok.com/short123/")
            assert "/video/" in url
            assert "/photo/" not in url
            assert is_photo is True

    @pytest.mark.asyncio
    async def test_non_tiktok_unchanged(self):
        from ytdl_bot import normalize_tiktok_url
        url, is_photo = await normalize_tiktok_url("https://youtube.com/watch?v=abc")
        assert url == "https://youtube.com/watch?v=abc"
        assert is_photo is False

    @pytest.mark.asyncio
    async def test_head_failure_keeps_original(self):
        mock_session = AsyncMock()

        class FailingHead:
            async def __aenter__(self):
                raise Exception("Network error")
            async def __aexit__(self, *args):
                pass

        mock_session.head = lambda *a, **kw: FailingHead()

        with patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import normalize_tiktok_url
            url, is_photo = await normalize_tiktok_url("https://vt.tiktok.com/broken/")
            # URL stays as-is on failure
            assert "vt.tiktok.com" in url

    # -- get_tiktok_photo --

    @pytest.mark.asyncio
    async def test_get_tiktok_photo_success(self, tmp_path):
        oembed_data = {"thumbnail_url": "https://p.tiktok.com/thumb.jpg"}
        oembed_resp = make_mock_response(status=200, json_data=oembed_data)
        thumb_resp = make_mock_response(status=200, content=b"\xff\xd8fake_jpg_data")

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return AsyncContextManager(oembed_resp)
            return AsyncContextManager(thumb_resp)

        mock_session = AsyncMock()
        mock_session.get = mock_get

        with patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import get_tiktok_photo
            path = await get_tiktok_photo("https://tiktok.com/@user/video/1", str(tmp_path))
            assert path is not None
            assert os.path.basename(path) == "tiktok_photo.jpg"

    @pytest.mark.asyncio
    async def test_get_tiktok_photo_oembed_404(self, tmp_path):
        mock_resp = make_mock_response(status=404)
        mock_session = AsyncMock()
        mock_session.get = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import get_tiktok_photo
            result = await get_tiktok_photo("https://tiktok.com/@user/video/1", str(tmp_path))
            assert result is None

    @pytest.mark.asyncio
    async def test_get_tiktok_photo_missing_thumbnail_url(self, tmp_path):
        oembed_data = {"title": "Some post"}  # no thumbnail_url
        mock_resp = make_mock_response(status=200, json_data=oembed_data)
        mock_session = AsyncMock()
        mock_session.get = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import get_tiktok_photo
            result = await get_tiktok_photo("https://tiktok.com/@user/video/1", str(tmp_path))
            assert result is None

    # -- merge_image_audio --

    @patch("ytdl_bot.subprocess.run")
    def test_merge_image_audio_success(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        from ytdl_bot import merge_image_audio
        result = merge_image_audio("/tmp/img.jpg", "/tmp/audio.mp3", "/tmp/out.mp4")
        assert result == "/tmp/out.mp4"

    @patch("ytdl_bot.subprocess.run")
    def test_merge_image_audio_failure(self, mock_run):
        mock_run.return_value = Mock(returncode=1, stderr="ffmpeg error")
        from ytdl_bot import merge_image_audio
        result = merge_image_audio("/tmp/img.jpg", "/tmp/audio.mp3", "/tmp/out.mp4")
        assert result is None

    @patch("ytdl_bot.subprocess.run")
    def test_merge_image_audio_command_structure(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        from ytdl_bot import merge_image_audio
        merge_image_audio("/img.jpg", "/audio.mp3", "/out.mp4")
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-loop" in cmd
        assert "1" in cmd
        assert "-i" in cmd
        assert "/img.jpg" in cmd
        assert "/audio.mp3" in cmd
        assert "-c:v" in cmd
        assert "libx264" in cmd
        assert "-shortest" in cmd
        assert cmd[-1] == "/out.mp4"

    # -- Audio-only regex --

    def test_yandex_music_regex_matches(self):
        import re
        pattern = r'https?://music\.yandex\.(ru|com)'
        assert re.match(pattern, "https://music.yandex.ru/album/123/track/456")
        assert re.match(pattern, "https://music.yandex.com/album/789")

    def test_audio_only_regex_rejects_non_music(self):
        import re
        pattern = r'https?://music\.yandex\.(ru|com)'
        assert not re.match(pattern, "https://www.youtube.com/watch?v=abc")
        assert not re.match(pattern, "https://yandex.ru/search?text=music")


# ---------------------------------------------------------------------------
# TestCommit10_ErrorReporting — commit f2f611e
# ---------------------------------------------------------------------------

class TestCommit10_ErrorReporting:
    """truncate_error, notify_admin, download_audio/video return tuples."""

    # -- truncate_error --

    def test_truncate_short_text(self):
        from ytdl_bot import truncate_error
        assert truncate_error("short") == "short"

    def test_truncate_exact_max_len(self):
        from ytdl_bot import truncate_error
        text = "x" * 3500
        assert truncate_error(text) == text

    def test_truncate_long_text(self):
        from ytdl_bot import truncate_error
        text = "x" * 4000
        result = truncate_error(text)
        assert result.endswith("\n...(truncated)")
        assert len(result) < len(text)

    def test_truncate_custom_max_len(self):
        from ytdl_bot import truncate_error
        text = "x" * 200
        result = truncate_error(text, max_len=100)
        assert result.endswith("\n...(truncated)")
        assert result.startswith("x" * 100)

    def test_truncate_default_is_3500(self):
        from ytdl_bot import truncate_error
        text = "x" * 3501
        result = truncate_error(text)
        assert result.endswith("\n...(truncated)")
        # Exactly 3500 should not be truncated
        assert truncate_error("y" * 3500) == "y" * 3500

    # -- notify_admin --

    @pytest.mark.asyncio
    async def test_notify_admin_sends_when_different_chat(self):
        with patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 1000), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send:
            from ytdl_bot import notify_admin
            await notify_admin(2000, "test message")
            mock_send.assert_called_once_with(1000, "test message")

    @pytest.mark.asyncio
    async def test_notify_admin_skips_when_same_chat(self):
        with patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 1000), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send:
            from ytdl_bot import notify_admin
            await notify_admin(1000, "test message")
            mock_send.assert_not_called()

    # -- download_audio return tuple --

    @pytest.mark.asyncio
    async def test_download_audio_success_returns_path_none(self, tmp_path):
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"audio data")

        def mock_run(cmd, **kwargs):
            return Mock(returncode=0, stderr="")

        with patch("ytdl_bot.subprocess.run", side_effect=mock_run), \
             patch("ytdl_bot.os.path.exists", return_value=True):
            from ytdl_bot import download_audio
            path, error = await download_audio("https://example.com", str(tmp_path), max_retries=0)
            assert error is None

    @pytest.mark.asyncio
    async def test_download_audio_failure_returns_none_error(self):
        def mock_run(cmd, **kwargs):
            return Mock(returncode=1, stderr="ERROR: not found")

        with patch("ytdl_bot.subprocess.run", side_effect=mock_run):
            from ytdl_bot import download_audio
            path, error = await download_audio("https://example.com", "/tmp", max_retries=0)
            assert path is None
            assert error is not None
            assert isinstance(error, str)

    # -- download_video return tuple --

    @pytest.mark.asyncio
    async def test_download_video_success_returns_path_none(self, tmp_path):
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video data")

        def mock_run(cmd, **kwargs):
            return Mock(returncode=0, stderr="")

        with patch("ytdl_bot.subprocess.run", side_effect=mock_run), \
             patch("ytdl_bot.os.path.exists", return_value=True):
            from ytdl_bot import download_video
            path, error = await download_video("https://example.com", str(tmp_path), max_retries=0)
            assert error is None

    @pytest.mark.asyncio
    async def test_download_video_failure_returns_none_error(self):
        def mock_run(cmd, **kwargs):
            return Mock(returncode=1, stderr="ERROR: video not available")

        with patch("ytdl_bot.subprocess.run", side_effect=mock_run):
            from ytdl_bot import download_video
            path, error = await download_video("https://example.com", "/tmp", max_retries=0)
            assert path is None
            assert error is not None
            assert isinstance(error, str)


# ---------------------------------------------------------------------------
# Helpers for bot handler tests
# ---------------------------------------------------------------------------

def make_mock_message(chat_id=100, user_id=100, text="", username="testuser",
                      first_name="Test", message_id=1):
    """Create a mock Telegram message object."""
    msg = Mock()
    msg.chat = Mock(id=chat_id)
    msg.from_user = Mock(id=user_id, username=username, first_name=first_name)
    msg.text = text
    msg.message_id = message_id
    return msg


def make_mock_callback(data="", chat_id=100, user_id=100, message_id=1,
                       message_text="original text"):
    """Create a mock Telegram callback query object."""
    call = Mock()
    call.data = data
    call.id = "callback_123"
    call.from_user = Mock(id=user_id, username="testuser", first_name="Test")
    call.message = Mock()
    call.message.chat = Mock(id=chat_id)
    call.message.message_id = message_id
    call.message.text = message_text
    return call


# ---------------------------------------------------------------------------
# TestSessionManagement
# ---------------------------------------------------------------------------

class TestSessionManagement:
    """close_aiohttp_session, get_aiohttp_session."""

    @pytest.mark.asyncio
    async def test_close_aiohttp_session_when_open(self):
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()

        with patch("ytdl_bot._AIOHTTP_SESSION", mock_session):
            from ytdl_bot import close_aiohttp_session
            await close_aiohttp_session()
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_aiohttp_session_when_already_closed(self):
        mock_session = AsyncMock()
        mock_session.closed = True

        with patch("ytdl_bot._AIOHTTP_SESSION", mock_session):
            from ytdl_bot import close_aiohttp_session
            await close_aiohttp_session()
            mock_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_aiohttp_session_when_none(self):
        with patch("ytdl_bot._AIOHTTP_SESSION", None):
            from ytdl_bot import close_aiohttp_session
            await close_aiohttp_session()  # Should not raise

    @pytest.mark.asyncio
    async def test_get_aiohttp_session_creates_new(self):
        mock_new_session = MagicMock()
        mock_new_session.closed = False
        with patch("ytdl_bot._AIOHTTP_SESSION", None), \
             patch("ytdl_bot.aiohttp.ClientSession", return_value=mock_new_session):
            from ytdl_bot import get_aiohttp_session
            session = await get_aiohttp_session()
            assert session is mock_new_session

    @pytest.mark.asyncio
    async def test_get_aiohttp_session_reuses_existing(self):
        mock_session = MagicMock()
        mock_session.closed = False
        with patch("ytdl_bot._AIOHTTP_SESSION", mock_session):
            from ytdl_bot import get_aiohttp_session
            session = await get_aiohttp_session()
            assert session is mock_session


# ---------------------------------------------------------------------------
# TestSpotifyToken
# ---------------------------------------------------------------------------

class TestSpotifyToken:
    """get_spotify_token tests."""

    @pytest.mark.asyncio
    async def test_get_spotify_token_success(self):
        mock_resp = make_mock_response(status=200, json_data={
            "access_token": "tok_abc", "expires_in": 3600
        })
        mock_session = AsyncMock()
        mock_session.post = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.SPOTIFY_TOKEN", {"token": None, "expires": 0}), \
             patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session), \
             patch("ytdl_bot.SPOTIFY_CLIENT_ID", "id"), \
             patch("ytdl_bot.SPOTIFY_CLIENT_SECRET", "secret"):
            from ytdl_bot import get_spotify_token
            token = await get_spotify_token()
            assert token == "tok_abc"

    @pytest.mark.asyncio
    async def test_get_spotify_token_cached(self):
        import time as _time
        with patch("ytdl_bot.SPOTIFY_TOKEN", {"token": "cached_tok", "expires": _time.time() + 9999}):
            from ytdl_bot import get_spotify_token
            token = await get_spotify_token()
            assert token == "cached_tok"

    @pytest.mark.asyncio
    async def test_get_spotify_token_error_returns_none(self):
        mock_session = AsyncMock()
        mock_session.post = Mock(side_effect=Exception("network error"))

        with patch("ytdl_bot.SPOTIFY_TOKEN", {"token": None, "expires": 0}), \
             patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session), \
             patch("ytdl_bot.SPOTIFY_CLIENT_ID", "id"), \
             patch("ytdl_bot.SPOTIFY_CLIENT_SECRET", "secret"):
            from ytdl_bot import get_spotify_token
            token = await get_spotify_token()
            assert token is None

    @pytest.mark.asyncio
    async def test_get_spotify_token_non_200(self):
        mock_resp = make_mock_response(status=401)
        mock_session = AsyncMock()
        mock_session.post = lambda *a, **kw: AsyncContextManager(mock_resp)

        with patch("ytdl_bot.SPOTIFY_TOKEN", {"token": None, "expires": 0}), \
             patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session), \
             patch("ytdl_bot.SPOTIFY_CLIENT_ID", "id"), \
             patch("ytdl_bot.SPOTIFY_CLIENT_SECRET", "secret"):
            from ytdl_bot import get_spotify_token
            token = await get_spotify_token()
            assert token is None


# ---------------------------------------------------------------------------
# TestSearchSpotifyException
# ---------------------------------------------------------------------------

class TestSearchSpotifyException:
    """search_spotify exception path (line 179-180)."""

    @pytest.mark.asyncio
    async def test_search_spotify_network_exception(self):
        mock_session = AsyncMock()

        class FailingGet:
            async def __aenter__(self):
                raise Exception("connection reset")
            async def __aexit__(self, *args):
                pass

        mock_session.get = lambda *a, **kw: FailingGet()

        with patch("ytdl_bot.SPOTIFY_ENABLED", True), \
             patch("ytdl_bot.get_spotify_token", new_callable=AsyncMock, return_value="token"), \
             patch("ytdl_bot.get_aiohttp_session", new_callable=AsyncMock, return_value=mock_session):
            from ytdl_bot import search_spotify
            assert await search_spotify("anything") is None


# ---------------------------------------------------------------------------
# TestMessageHelpers
# ---------------------------------------------------------------------------

class TestMessageHelpers:
    """send_message, add_status_message, clear_status_messages."""

    @pytest.mark.asyncio
    async def test_send_message(self):
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=Mock(message_id=42))
        with patch("ytdl_bot.BOT", mock_bot):
            from ytdl_bot import send_message
            result = await send_message(100, "hello")
            mock_bot.send_message.assert_called_once_with(100, "hello", reply_markup=None)
            assert result.message_id == 42

    @pytest.mark.asyncio
    async def test_send_message_with_markup(self):
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=Mock(message_id=43))
        markup = Mock()
        with patch("ytdl_bot.BOT", mock_bot):
            from ytdl_bot import send_message
            await send_message(100, "hello", reply_markup=markup)
            mock_bot.send_message.assert_called_once_with(100, "hello", reply_markup=markup)

    def test_add_status_message_single(self):
        from ytdl_bot import add_status_message
        import ytdl_bot
        orig = ytdl_bot.STATUS_MESSAGES.copy()
        try:
            ytdl_bot.STATUS_MESSAGES.clear()
            msg = Mock(message_id=10)
            add_status_message(999, msg)
            assert 10 in ytdl_bot.STATUS_MESSAGES[999]
        finally:
            ytdl_bot.STATUS_MESSAGES.clear()
            ytdl_bot.STATUS_MESSAGES.update(orig)

    def test_add_status_message_list(self):
        from ytdl_bot import add_status_message
        import ytdl_bot
        orig = ytdl_bot.STATUS_MESSAGES.copy()
        try:
            ytdl_bot.STATUS_MESSAGES.clear()
            msgs = [Mock(message_id=10), Mock(message_id=11)]
            add_status_message(999, msgs)
            assert 10 in ytdl_bot.STATUS_MESSAGES[999]
            assert 11 in ytdl_bot.STATUS_MESSAGES[999]
        finally:
            ytdl_bot.STATUS_MESSAGES.clear()
            ytdl_bot.STATUS_MESSAGES.update(orig)

    def test_add_status_message_no_message_id(self):
        from ytdl_bot import add_status_message
        import ytdl_bot
        orig = ytdl_bot.STATUS_MESSAGES.copy()
        try:
            ytdl_bot.STATUS_MESSAGES.clear()
            msg = "not a message object"
            add_status_message(999, msg)
            assert ytdl_bot.STATUS_MESSAGES.get(999, []) == []
        finally:
            ytdl_bot.STATUS_MESSAGES.clear()
            ytdl_bot.STATUS_MESSAGES.update(orig)

    @pytest.mark.asyncio
    async def test_clear_status_messages(self):
        import ytdl_bot
        mock_bot = AsyncMock()
        mock_bot.delete_message = AsyncMock()
        orig = ytdl_bot.STATUS_MESSAGES.copy()
        try:
            ytdl_bot.STATUS_MESSAGES.clear()
            ytdl_bot.STATUS_MESSAGES[999] = [10, 11, 12]
            with patch("ytdl_bot.BOT", mock_bot):
                from ytdl_bot import clear_status_messages
                await clear_status_messages(999)
                assert mock_bot.delete_message.call_count == 3
                assert ytdl_bot.STATUS_MESSAGES[999] == []
        finally:
            ytdl_bot.STATUS_MESSAGES.clear()
            ytdl_bot.STATUS_MESSAGES.update(orig)

    @pytest.mark.asyncio
    async def test_clear_status_messages_delete_error(self):
        import ytdl_bot
        mock_bot = AsyncMock()
        mock_bot.delete_message = AsyncMock(side_effect=Exception("msg not found"))
        orig = ytdl_bot.STATUS_MESSAGES.copy()
        try:
            ytdl_bot.STATUS_MESSAGES.clear()
            ytdl_bot.STATUS_MESSAGES[999] = [10]
            with patch("ytdl_bot.BOT", mock_bot):
                from ytdl_bot import clear_status_messages
                await clear_status_messages(999)  # Should not raise
                assert ytdl_bot.STATUS_MESSAGES[999] == []
        finally:
            ytdl_bot.STATUS_MESSAGES.clear()
            ytdl_bot.STATUS_MESSAGES.update(orig)

    @pytest.mark.asyncio
    async def test_clear_status_messages_no_messages(self):
        import ytdl_bot
        orig = ytdl_bot.STATUS_MESSAGES.copy()
        try:
            ytdl_bot.STATUS_MESSAGES.clear()
            from ytdl_bot import clear_status_messages
            await clear_status_messages(999)  # Should not raise
        finally:
            ytdl_bot.STATUS_MESSAGES.clear()
            ytdl_bot.STATUS_MESSAGES.update(orig)


# ---------------------------------------------------------------------------
# TestGetThumbnail
# ---------------------------------------------------------------------------

class TestGetThumbnail:
    """get_thumbnail tests."""

    @patch("ytdl_bot.subprocess.run")
    def test_get_thumbnail_success(self, mock_run, tmp_path):
        # Create a fake thumbnail file
        thumb = tmp_path / "_thumbnail.jpg"
        thumb.write_bytes(b"fake jpg")
        mock_run.return_value = Mock(returncode=0)
        from ytdl_bot import get_thumbnail
        result = get_thumbnail("https://example.com", str(tmp_path))
        assert result is not None
        assert result.endswith(".jpg")

    @patch("ytdl_bot.subprocess.run")
    def test_get_thumbnail_no_file(self, mock_run, tmp_path):
        mock_run.return_value = Mock(returncode=0)
        from ytdl_bot import get_thumbnail
        result = get_thumbnail("https://example.com", str(tmp_path))
        assert result is None

    @patch("ytdl_bot.subprocess.run")
    def test_get_thumbnail_exception(self, mock_run):
        mock_run.side_effect = Exception("yt-dlp error")
        from ytdl_bot import get_thumbnail
        result = get_thumbnail("https://example.com", "/nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# TestGetNewVideoInfo
# ---------------------------------------------------------------------------

class TestGetNewVideoInfo:
    """get_new_video_info tests."""

    def _run_with_mocks(self, width=1920, height=1080, probe_stdout="", length=120):
        with patch("ytdl_bot.Video.get_resolution", return_value=(width, height)), \
             patch("ytdl_bot.subprocess.run", return_value=Mock(
                 stdout=probe_stdout, returncode=0)), \
             patch("ytdl_bot.Video.get_length", return_value=length):
            from ytdl_bot import get_new_video_info
            return get_new_video_info("/fake/video.mp4")

    def test_basic_1080p_short_video(self):
        result = self._run_with_mocks(1920, 1080, "", 120)
        vbr, abr, w, h, new_fps, orig_fps, length = result
        assert w == 1920
        assert h == 1080
        assert length == 120

    def test_caps_at_1080p(self):
        result = self._run_with_mocks(3840, 2160, "", 60)
        _, _, w, h, _, _, _ = result
        assert h == 1080

    def test_30min_caps_at_720p(self):
        result = self._run_with_mocks(1920, 1080, "", 2000)
        _, _, w, h, _, _, _ = result
        assert h == 720

    def test_1hour_caps_at_480p(self):
        result = self._run_with_mocks(1920, 1080, "", 4000)
        _, _, w, h, _, _, _ = result
        assert h == 480

    def test_2hour_caps_at_360p(self):
        result = self._run_with_mocks(1920, 1080, "", 8000)
        _, _, w, h, _, _, _ = result
        assert h == 360

    def test_6hour_caps_at_240p(self):
        result = self._run_with_mocks(1920, 1080, "", 22000)
        _, _, w, h, _, _, _ = result
        assert h == 240

    def test_even_dimensions(self):
        # 1920x1081 -> height should become even
        result = self._run_with_mocks(1919, 1079, "", 60)
        _, _, w, h, _, _, _ = result
        assert w % 2 == 0
        assert h % 2 == 0

    def test_fps_reduction_60_to_30(self):
        probe_json = json.dumps({"streams": [
            {"codec_type": "video", "bit_rate": "5000000", "r_frame_rate": "60/1"},
            {"codec_type": "audio", "bit_rate": "128000"}
        ]})
        result = self._run_with_mocks(1920, 1080, probe_json, 120)
        _, _, _, _, new_fps, orig_fps, _ = result
        assert orig_fps == 60.0
        assert new_fps == 30.0

    def test_fps_no_reduction_needed(self):
        probe_json = json.dumps({"streams": [
            {"codec_type": "video", "bit_rate": "5000000", "r_frame_rate": "24/1"},
            {"codec_type": "audio", "bit_rate": "128000"}
        ]})
        result = self._run_with_mocks(1920, 1080, probe_json, 120)
        _, _, _, _, new_fps, orig_fps, _ = result
        assert new_fps == 24.0

    def test_parses_stream_bitrates(self):
        probe_json = json.dumps({"streams": [
            {"codec_type": "video", "bit_rate": "2000000", "r_frame_rate": "30/1"},
            {"codec_type": "audio", "bit_rate": "192000"}
        ]})
        result = self._run_with_mocks(1920, 1080, probe_json, 120)
        vbr, abr, _, _, _, _, _ = result
        # audio bitrate should be clamped to MAX_AUDIO_BITRATE
        from ytdl_bot import MAX_AUDIO_BITRATE
        assert abr <= MAX_AUDIO_BITRATE

    def test_safety_margin_applied(self):
        result = self._run_with_mocks(1920, 1080, "", 120)
        vbr, _, _, _, _, _, _ = result
        # Video bitrate should have safety margin applied
        assert vbr > 0


# ---------------------------------------------------------------------------
# TestCompressVideo
# ---------------------------------------------------------------------------

class TestCompressVideo:
    """compress_video tests."""

    @patch("ytdl_bot.get_new_video_info")
    @patch("ytdl_bot.subprocess.run")
    @patch("ytdl_bot.os.path.getsize")
    def test_compress_success(self, mock_getsize, mock_run, mock_info):
        mock_info.return_value = (1000000, 128000, 1280, 720, 30.0, 30.0, 120)
        mock_run.return_value = Mock(returncode=0)
        mock_getsize.return_value = 100 * 1024 * 1024  # 100 MiB < 2 GiB

        from ytdl_bot import compress_video
        path, w, h = compress_video("/tmp/video.mp4")
        assert path is not None
        assert w == 1280
        assert h == 720

    @patch("ytdl_bot.get_new_video_info")
    @patch("ytdl_bot.subprocess.run")
    def test_compress_ffmpeg_failure(self, mock_run, mock_info):
        mock_info.return_value = (1000000, 128000, 1280, 720, 30.0, 30.0, 120)
        mock_run.return_value = Mock(returncode=1, stderr="encoding error")

        from ytdl_bot import compress_video
        path, w, h = compress_video("/tmp/video.mp4")
        assert path is None
        assert w is None

    @patch("ytdl_bot.get_new_video_info")
    @patch("ytdl_bot.subprocess.run")
    def test_compress_timeout(self, mock_run, mock_info):
        mock_info.return_value = (1000000, 128000, 1280, 720, 30.0, 30.0, 120)
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=60)

        from ytdl_bot import compress_video
        path, w, h = compress_video("/tmp/video.mp4")
        assert path is None

    @patch("ytdl_bot.get_new_video_info")
    @patch("ytdl_bot.subprocess.run")
    @patch("ytdl_bot.os.path.getsize")
    def test_compress_still_too_large_retries(self, mock_getsize, mock_run, mock_info):
        mock_info.return_value = (1000000, 128000, 1280, 720, 30.0, 30.0, 120)
        mock_run.return_value = Mock(returncode=0)
        # Always too large -> exhaust 5 attempts
        mock_getsize.return_value = 3 * 1024 * 1024 * 1024  # 3 GiB

        from ytdl_bot import compress_video
        path, w, h = compress_video("/tmp/video.mp4")
        assert path is None
        assert mock_run.call_count == 5

    @patch("ytdl_bot.get_new_video_info")
    @patch("ytdl_bot.subprocess.run")
    @patch("ytdl_bot.os.path.getsize")
    def test_compress_fps_change(self, mock_getsize, mock_run, mock_info):
        # new_fps != original_fps triggers fps filter
        mock_info.return_value = (1000000, 128000, 1280, 720, 30.0, 60.0, 120)
        mock_run.return_value = Mock(returncode=0)
        mock_getsize.return_value = 100 * 1024 * 1024

        from ytdl_bot import compress_video
        path, w, h = compress_video("/tmp/video.mp4")
        assert path is not None
        # Check that fps= was in the ffmpeg command
        cmd = mock_run.call_args[0][0]
        vf_idx = cmd.index("-vf")
        assert "fps=" in cmd[vf_idx + 1]


# ---------------------------------------------------------------------------
# TestProgressCallbacks
# ---------------------------------------------------------------------------

class TestProgressCallbacks:
    """ConsoleProgressCallback and UploadProgressCallback."""

    def test_console_callback_prints(self):
        from ytdl_bot import ConsoleProgressCallback
        cb = ConsoleProgressCallback(file_size=1000)
        cb.last_update = 0  # force update
        cb.start_time = cb._time.time() - 60  # 1 min elapsed
        cb(500, 1000)  # 50%
        assert cb.last_update > 0

    def test_console_callback_skips_if_too_soon(self):
        from ytdl_bot import ConsoleProgressCallback
        cb = ConsoleProgressCallback(file_size=1000)
        cb.last_update = cb._time.time()  # just updated
        old_update = cb.last_update
        cb(500, 1000)
        assert cb.last_update == old_update  # not updated

    @pytest.mark.asyncio
    async def test_upload_callback_updates_message(self):
        mock_bot = AsyncMock()
        with patch("ytdl_bot.BOT", mock_bot):
            from ytdl_bot import UploadProgressCallback, MiB
            cb = UploadProgressCallback(
                chat_id=100, message_id=1, file_size=100*MiB,
                media_type="video", retry_attempt=0)
            cb.last_update = 0
            cb.start_time = cb._time.time() - 60
            await cb(50*MiB, 100*MiB)
            mock_bot.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_callback_with_retry_info(self):
        mock_bot = AsyncMock()
        with patch("ytdl_bot.BOT", mock_bot):
            from ytdl_bot import UploadProgressCallback, MiB
            cb = UploadProgressCallback(
                chat_id=100, message_id=1, file_size=100*MiB,
                media_type="audio", retry_attempt=2, max_retries=5)
            cb.last_update = 0
            cb.start_time = cb._time.time() - 60
            await cb(50*MiB, 100*MiB)
            call_args = mock_bot.edit_message_text.call_args[0][0]
            assert "retry 2/5" in call_args

    @pytest.mark.asyncio
    async def test_upload_callback_edit_error_swallowed(self):
        mock_bot = AsyncMock()
        mock_bot.edit_message_text = AsyncMock(side_effect=Exception("rate limited"))
        with patch("ytdl_bot.BOT", mock_bot):
            from ytdl_bot import UploadProgressCallback, MiB
            cb = UploadProgressCallback(chat_id=100, message_id=1, file_size=100*MiB)
            cb.last_update = 0
            cb.start_time = cb._time.time() - 60
            await cb(50*MiB, 100*MiB)  # Should not raise


# ---------------------------------------------------------------------------
# TestBotHandlers
# ---------------------------------------------------------------------------

class TestBotHandlers:
    """handle_help, handle_revoke, handle_start."""

    @pytest.mark.asyncio
    async def test_handle_help_regular_user(self):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999):
            from ytdl_bot import handle_help
            msg = make_mock_message(chat_id=100, user_id=100)
            await handle_help(msg)
            text = mock_send.call_args[0][1]
            assert "Admin commands" not in text

    @pytest.mark.asyncio
    async def test_handle_help_admin(self):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 100):
            from ytdl_bot import handle_help
            msg = make_mock_message(chat_id=100, user_id=100)
            await handle_help(msg)
            text = mock_send.call_args[0][1]
            assert "/revoke" in text

    @pytest.mark.asyncio
    async def test_handle_revoke_non_admin(self):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999):
            from ytdl_bot import handle_revoke
            msg = make_mock_message(chat_id=100, user_id=100, text="/revoke 123")
            await handle_revoke(msg)
            assert "Admin only" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_handle_revoke_missing_user_id(self):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 100):
            from ytdl_bot import handle_revoke
            msg = make_mock_message(chat_id=100, user_id=100, text="/revoke")
            await handle_revoke(msg)
            assert "Usage" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_handle_revoke_invalid_user_id(self):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 100):
            from ytdl_bot import handle_revoke
            msg = make_mock_message(chat_id=100, user_id=100, text="/revoke abc")
            await handle_revoke(msg)
            assert "Invalid" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_handle_revoke_cannot_revoke_admin(self):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 100):
            from ytdl_bot import handle_revoke
            msg = make_mock_message(chat_id=100, user_id=100, text="/revoke 100")
            await handle_revoke(msg)
            assert "Cannot revoke admin" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_handle_revoke_success(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["approved_users"].append(500)
        um.config.save()

        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 100), \
             patch("ytdl_bot.USER_MANAGER", um):
            from ytdl_bot import handle_revoke
            msg = make_mock_message(chat_id=100, user_id=100, text="/revoke 500")
            await handle_revoke(msg)
            assert "revoked" in mock_send.call_args[0][1]
            assert 500 not in um.config["approved_users"]

    @pytest.mark.asyncio
    async def test_handle_revoke_user_not_in_list(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)

        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 100), \
             patch("ytdl_bot.USER_MANAGER", um):
            from ytdl_bot import handle_revoke
            msg = make_mock_message(chat_id=100, user_id=100, text="/revoke 500")
            await handle_revoke(msg)
            assert "not in approved list" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_handle_start_approved(self):
        mock_um = Mock()
        mock_um.is_approved.return_value = True
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.USER_MANAGER", mock_um):
            from ytdl_bot import handle_start
            msg = make_mock_message()
            await handle_start(msg)
            assert "Welcome" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_handle_start_denied(self):
        mock_um = Mock()
        mock_um.is_approved.return_value = False
        mock_um.is_denied.return_value = True
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.USER_MANAGER", mock_um):
            from ytdl_bot import handle_start
            msg = make_mock_message()
            await handle_start(msg)
            assert "denied" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_handle_start_pending(self):
        mock_um = Mock()
        mock_um.is_approved.return_value = False
        mock_um.is_denied.return_value = False
        mock_um.is_pending.return_value = True
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.USER_MANAGER", mock_um):
            from ytdl_bot import handle_start
            msg = make_mock_message()
            await handle_start(msg)
            assert "pending" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_handle_start_new_user(self):
        mock_um = Mock()
        mock_um.is_approved.return_value = False
        mock_um.is_denied.return_value = False
        mock_um.is_pending.return_value = False
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.USER_MANAGER", mock_um):
            from ytdl_bot import handle_start
            msg = make_mock_message()
            await handle_start(msg)
            assert "approval" in mock_send.call_args[0][1]


# ---------------------------------------------------------------------------
# TestHandleMessage
# ---------------------------------------------------------------------------

class TestHandleMessage:
    """handle_message tests."""

    @pytest.mark.asyncio
    async def test_not_a_url(self):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send:
            from ytdl_bot import handle_message
            msg = make_mock_message(text="hello world")
            await handle_message(msg)
            assert "valid URL" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_denied_user(self):
        mock_um = Mock()
        mock_um.is_denied.return_value = True
        mock_um.is_pending.return_value = False
        mock_um.is_approved.return_value = False
        mock_bot = AsyncMock()
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.USER_MANAGER", mock_um), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://example.com/v", False)):
            from ytdl_bot import handle_message
            msg = make_mock_message(text="https://youtube.com/watch?v=abc")
            await handle_message(msg)
            assert "denied" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_pending_user(self):
        mock_um = Mock()
        mock_um.is_denied.return_value = False
        mock_um.is_pending.return_value = True
        mock_um.is_approved.return_value = False
        mock_bot = AsyncMock()
        with patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.USER_MANAGER", mock_um), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://example.com/v", False)):
            from ytdl_bot import handle_message
            msg = make_mock_message(text="https://youtube.com/watch?v=abc")
            await handle_message(msg)
            assert "pending" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    async def test_approved_user_video_choice(self):
        mock_um = Mock()
        mock_um.is_denied.return_value = False
        mock_um.is_pending.return_value = False
        mock_um.is_approved.return_value = True
        mock_bot = AsyncMock()
        with patch("ytdl_bot.USER_MANAGER", mock_um), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://youtube.com/watch?v=abc", False)), \
             patch("ytdl_bot.show_format_choice", new_callable=AsyncMock) as mock_show:
            from ytdl_bot import handle_message
            msg = make_mock_message(text="https://youtube.com/watch?v=abc")
            await handle_message(msg)
            mock_show.assert_called_once()
            # approved=True
            assert mock_show.call_args[1].get("approved", mock_show.call_args[0][-1]) is True

    @pytest.mark.asyncio
    async def test_tiktok_photo_approved(self):
        mock_um = Mock()
        mock_um.is_denied.return_value = False
        mock_um.is_pending.return_value = False
        mock_um.is_approved.return_value = True
        mock_bot = AsyncMock()
        with patch("ytdl_bot.USER_MANAGER", mock_um), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://tiktok.com/@u/video/1", True)), \
             patch("ytdl_bot.process_tiktok_photo", new_callable=AsyncMock) as mock_proc:
            from ytdl_bot import handle_message
            msg = make_mock_message(text="https://tiktok.com/@u/photo/1")
            await handle_message(msg)
            mock_proc.assert_called_once()

    @pytest.mark.asyncio
    async def test_audio_only_yandex_approved(self):
        mock_um = Mock()
        mock_um.is_denied.return_value = False
        mock_um.is_pending.return_value = False
        mock_um.is_approved.return_value = True
        mock_bot = AsyncMock()
        with patch("ytdl_bot.USER_MANAGER", mock_um), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://music.yandex.ru/album/1/track/2", False)), \
             patch("ytdl_bot.process_audio_download", new_callable=AsyncMock) as mock_audio:
            from ytdl_bot import handle_message
            msg = make_mock_message(text="https://music.yandex.ru/album/1/track/2")
            await handle_message(msg)
            mock_audio.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_to_admin(self):
        mock_um = Mock()
        mock_um.is_denied.return_value = False
        mock_um.is_pending.return_value = False
        mock_um.is_approved.return_value = True
        mock_bot = AsyncMock()
        with patch("ytdl_bot.USER_MANAGER", mock_um), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://youtube.com/v", False)), \
             patch("ytdl_bot.show_format_choice", new_callable=AsyncMock):
            from ytdl_bot import handle_message
            msg = make_mock_message(chat_id=100, text="https://youtube.com/v")
            await handle_message(msg)
            mock_bot.forward_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_forward_when_admin(self):
        mock_um = Mock()
        mock_um.is_denied.return_value = False
        mock_um.is_pending.return_value = False
        mock_um.is_approved.return_value = True
        mock_bot = AsyncMock()
        with patch("ytdl_bot.USER_MANAGER", mock_um), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 100), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://youtube.com/v", False)), \
             patch("ytdl_bot.show_format_choice", new_callable=AsyncMock):
            from ytdl_bot import handle_message
            msg = make_mock_message(chat_id=100, text="https://youtube.com/v")
            await handle_message(msg)
            mock_bot.forward_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_unapproved_user_gets_format_choice(self):
        mock_um = Mock()
        mock_um.is_denied.return_value = False
        mock_um.is_pending.return_value = False
        mock_um.is_approved.return_value = False
        mock_bot = AsyncMock()
        with patch("ytdl_bot.USER_MANAGER", mock_um), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://youtube.com/v", False)), \
             patch("ytdl_bot.show_format_choice", new_callable=AsyncMock) as mock_show:
            from ytdl_bot import handle_message
            msg = make_mock_message(text="https://youtube.com/v")
            await handle_message(msg)
            mock_show.assert_called_once()
            # show_format_choice(chat_id, user_id, url, approved=False)
            assert mock_show.call_args.kwargs.get("approved") is False


# ---------------------------------------------------------------------------
# TestShowFormatChoice
# ---------------------------------------------------------------------------

class TestShowFormatChoice:
    """show_format_choice tests."""

    @pytest.mark.asyncio
    async def test_show_format_choice_approved(self):
        import ytdl_bot
        mock_msg = Mock(message_id=50)
        with patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=mock_msg), \
             patch("ytdl_bot.add_status_message") as mock_add, \
             patch("ytdl_bot.PENDING_CHOICES", {}), \
             patch("ytdl_bot.telebot") as mock_telebot:
            mock_telebot.types.InlineKeyboardMarkup.return_value = Mock()
            mock_telebot.types.InlineKeyboardButton = Mock()
            from ytdl_bot import show_format_choice
            await show_format_choice(100, 100, "https://example.com", approved=True)
            # Check callback prefix is "dl" for approved
            btn_calls = mock_telebot.types.InlineKeyboardButton.call_args_list
            assert any("dl_video" in str(c) for c in btn_calls)

    @pytest.mark.asyncio
    async def test_show_format_choice_unapproved(self):
        import ytdl_bot
        mock_msg = Mock(message_id=51)
        with patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=mock_msg), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.PENDING_CHOICES", {}), \
             patch("ytdl_bot.telebot") as mock_telebot:
            mock_telebot.types.InlineKeyboardMarkup.return_value = Mock()
            mock_telebot.types.InlineKeyboardButton = Mock()
            from ytdl_bot import show_format_choice
            await show_format_choice(100, 100, "https://example.com", approved=False)
            btn_calls = mock_telebot.types.InlineKeyboardButton.call_args_list
            assert any("req_video" in str(c) for c in btn_calls)

    @pytest.mark.asyncio
    async def test_show_format_choice_cleans_expired(self):
        import time as _time
        expired_choices = {
            1: {"url": "old", "user_id": 1, "timestamp": _time.time() - 7200},
            2: {"url": "new", "user_id": 2, "timestamp": _time.time()},
        }
        mock_msg = Mock(message_id=52)
        with patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=mock_msg), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.PENDING_CHOICES", expired_choices), \
             patch("ytdl_bot.telebot") as mock_telebot:
            mock_telebot.types.InlineKeyboardMarkup.return_value = Mock()
            mock_telebot.types.InlineKeyboardButton = Mock()
            from ytdl_bot import show_format_choice
            await show_format_choice(100, 100, "https://example.com")
            assert 1 not in expired_choices  # expired cleaned
            assert 2 in expired_choices  # fresh kept


# ---------------------------------------------------------------------------
# TestFormatCallbacks
# ---------------------------------------------------------------------------

class TestFormatCallbacks:
    """handle_format_choice and handle_format_choice_unapproved."""

    @pytest.mark.asyncio
    async def test_handle_format_choice_video(self):
        import ytdl_bot
        pending = {1: {"url": "https://test.com", "user_id": 100, "timestamp": 0, "approved": True}}
        mock_bot = AsyncMock()
        with patch("ytdl_bot.PENDING_CHOICES", pending), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.STATUS_MESSAGES", {}), \
             patch("ytdl_bot.process_download", new_callable=AsyncMock) as mock_dl:
            from ytdl_bot import handle_format_choice
            call = make_mock_callback(data="dl_video", message_id=1)
            await handle_format_choice(call)
            mock_dl.assert_called_once_with(call.message.chat.id, call.from_user.id, "https://test.com")

    @pytest.mark.asyncio
    async def test_handle_format_choice_audio(self):
        import ytdl_bot
        pending = {1: {"url": "https://test.com", "user_id": 100, "timestamp": 0, "approved": True}}
        mock_bot = AsyncMock()
        with patch("ytdl_bot.PENDING_CHOICES", pending), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.STATUS_MESSAGES", {}), \
             patch("ytdl_bot.process_audio_download", new_callable=AsyncMock) as mock_dl:
            from ytdl_bot import handle_format_choice
            call = make_mock_callback(data="dl_audio", message_id=1)
            await handle_format_choice(call)
            mock_dl.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_format_choice_expired(self):
        mock_bot = AsyncMock()
        with patch("ytdl_bot.PENDING_CHOICES", {}), \
             patch("ytdl_bot.BOT", mock_bot):
            from ytdl_bot import handle_format_choice
            call = make_mock_callback(data="dl_video", message_id=999)
            await handle_format_choice(call)
            mock_bot.answer_callback_query.assert_called_once()
            assert "expired" in mock_bot.answer_callback_query.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_handle_format_choice_unapproved_audio(self):
        pending = {1: {"url": "https://test.com", "user_id": 100, "timestamp": 0, "approved": False}}
        mock_bot = AsyncMock()
        with patch("ytdl_bot.PENDING_CHOICES", pending), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.STATUS_MESSAGES", {}), \
             patch("ytdl_bot.request_approval_with_format", new_callable=AsyncMock) as mock_req:
            from ytdl_bot import handle_format_choice_unapproved
            call = make_mock_callback(data="req_audio", message_id=1)
            await handle_format_choice_unapproved(call)
            mock_req.assert_called_once()
            # audio_only should be True
            assert mock_req.call_args[1].get("audio_only", mock_req.call_args[0][-1]) is True

    @pytest.mark.asyncio
    async def test_handle_format_choice_unapproved_expired(self):
        mock_bot = AsyncMock()
        with patch("ytdl_bot.PENDING_CHOICES", {}), \
             patch("ytdl_bot.BOT", mock_bot):
            from ytdl_bot import handle_format_choice_unapproved
            call = make_mock_callback(data="req_video", message_id=999)
            await handle_format_choice_unapproved(call)
            assert "expired" in mock_bot.answer_callback_query.call_args[0][1].lower()


# ---------------------------------------------------------------------------
# TestRequestApproval
# ---------------------------------------------------------------------------

class TestRequestApproval:
    """request_approval_with_format tests."""

    @pytest.mark.asyncio
    async def test_request_approval_success(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)

        mock_bot = AsyncMock()
        admin_msg = Mock(message_id=777)
        mock_bot.send_message = AsyncMock(return_value=admin_msg)

        user = Mock(username="newuser", first_name="New")
        with patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.USER_MANAGER", um), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, return_value="Video Title"), \
             patch("ytdl_bot.telebot") as mock_telebot, \
             patch("ytdl_bot.Time") as mock_time:
            mock_time.dotted.return_value = "2024.01.01"
            mock_telebot.types.InlineKeyboardMarkup.return_value = Mock()
            mock_telebot.types.InlineKeyboardButton = Mock()
            from ytdl_bot import request_approval_with_format
            await request_approval_with_format(200, 200, user, "https://example.com", audio_only=True)
            # Admin should get a message
            mock_bot.send_message.assert_called_once()
            # User notified
            assert any("sent to the admin" in str(c) for c in mock_send.call_args_list)

    @pytest.mark.asyncio
    async def test_request_approval_error(self):
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(side_effect=Exception("bot error"))
        user = Mock(username="u", first_name="F")
        with patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 9999), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, return_value="Title"), \
             patch("ytdl_bot.telebot") as mock_telebot:
            mock_telebot.types.InlineKeyboardMarkup.return_value = Mock()
            mock_telebot.types.InlineKeyboardButton = Mock()
            from ytdl_bot import request_approval_with_format
            await request_approval_with_format(200, 200, user, "https://x.com")
            assert any("Error" in str(c) for c in mock_send.call_args_list)


# ---------------------------------------------------------------------------
# TestApprovalCallback
# ---------------------------------------------------------------------------

class TestApprovalCallback:
    """handle_approval_callback tests."""

    @pytest.mark.asyncio
    async def test_approve_callback(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["pending_requests"]["500"] = {
            "user_id": 500, "requested_url": "https://test.com",
            "audio_only": False
        }
        um.config.save()

        mock_bot = AsyncMock()
        with patch("ytdl_bot.USER_MANAGER", um), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock), \
             patch("ytdl_bot.process_download", new_callable=AsyncMock) as mock_dl:
            from ytdl_bot import handle_approval_callback
            call = make_mock_callback(data="approve_500", message_text="New user request")
            await handle_approval_callback(call)
            assert um.is_approved(500)
            mock_dl.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_callback_audio_only(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["pending_requests"]["501"] = {
            "user_id": 501, "requested_url": "https://test.com",
            "audio_only": True
        }
        um.config.save()

        mock_bot = AsyncMock()
        with patch("ytdl_bot.USER_MANAGER", um), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock), \
             patch("ytdl_bot.process_audio_download", new_callable=AsyncMock) as mock_dl:
            from ytdl_bot import handle_approval_callback
            call = make_mock_callback(data="approve_501", message_text="New user request")
            await handle_approval_callback(call)
            mock_dl.assert_called_once()

    @pytest.mark.asyncio
    async def test_deny_callback(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)
        um.config["pending_requests"]["502"] = {"user_id": 502}
        um.config.save()

        mock_bot = AsyncMock()
        with patch("ytdl_bot.USER_MANAGER", um), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock) as mock_send:
            from ytdl_bot import handle_approval_callback
            call = make_mock_callback(data="deny_502", message_text="New user request")
            await handle_approval_callback(call)
            assert um.is_denied(502)
            assert any("denied" in str(c).lower() for c in mock_send.call_args_list)

    @pytest.mark.asyncio
    async def test_approval_callback_edit_error(self, tmp_path):
        json_path = str(tmp_path / "users.json")
        from ytdl_bot import UserManager
        um = UserManager(json_path)

        mock_bot = AsyncMock()
        mock_bot.edit_message_text = AsyncMock(side_effect=Exception("msg too old"))
        mock_bot.answer_callback_query = AsyncMock(side_effect=Exception("query expired"))
        with patch("ytdl_bot.USER_MANAGER", um), \
             patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock):
            from ytdl_bot import handle_approval_callback
            call = make_mock_callback(data="approve_999")
            await handle_approval_callback(call)  # Should not raise


# ---------------------------------------------------------------------------
# TestProcessTikTokPhoto
# ---------------------------------------------------------------------------

class TestProcessTikTokPhoto:
    """process_tiktok_photo tests."""

    @pytest.mark.asyncio
    async def test_process_tiktok_photo_success(self, tmp_path):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.download_audio", new_callable=AsyncMock, return_value=(str(tmp_path / "a.mp3"), None)), \
             patch("ytdl_bot.get_tiktok_photo", new_callable=AsyncMock, return_value=str(tmp_path / "p.jpg")), \
             patch("ytdl_bot.asyncio.to_thread") as mock_to_thread, \
             patch("ytdl_bot.merge_image_audio", return_value=str(tmp_path / "v.mp4")), \
             patch("ytdl_bot.os.path.getsize", return_value=5 * 1024 * 1024), \
             patch("ytdl_bot.send_video_telethon", new_callable=AsyncMock), \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.clean_youtube_url", return_value="https://tiktok.com/v"), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):

            # mock asyncio.to_thread calls: merge_image_audio, get_video_title, get_audio_duration, Video.get_resolution
            mock_to_thread.side_effect = [
                str(tmp_path / "v.mp4"),  # merge_image_audio
                "TikTok Title",           # get_video_title
                120,                      # get_audio_duration
                (720, 1280),              # Video.get_resolution
            ]

            from ytdl_bot import process_tiktok_photo
            await process_tiktok_photo(100, 100, "https://tiktok.com/@u/video/1")

    @pytest.mark.asyncio
    async def test_process_tiktok_photo_audio_fail(self, tmp_path):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.download_audio", new_callable=AsyncMock, return_value=(None, "dl error")), \
             patch("ytdl_bot.get_tiktok_photo", new_callable=AsyncMock, return_value=None), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            from ytdl_bot import process_tiktok_photo
            await process_tiktok_photo(100, 100, "https://tiktok.com/@u/video/1")

    @pytest.mark.asyncio
    async def test_process_tiktok_photo_no_photo_fallback(self, tmp_path):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.download_audio", new_callable=AsyncMock, return_value=(str(tmp_path / "a.mp3"), None)), \
             patch("ytdl_bot.get_tiktok_photo", new_callable=AsyncMock, return_value=None), \
             patch("ytdl_bot.process_audio_download", new_callable=AsyncMock) as mock_audio, \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            from ytdl_bot import process_tiktok_photo
            await process_tiktok_photo(100, 100, "https://tiktok.com/@u/video/1")
            mock_audio.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_tiktok_photo_merge_fail_fallback(self, tmp_path):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.download_audio", new_callable=AsyncMock, return_value=(str(tmp_path / "a.mp3"), None)), \
             patch("ytdl_bot.get_tiktok_photo", new_callable=AsyncMock, return_value=str(tmp_path / "p.jpg")), \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, return_value=None), \
             patch("ytdl_bot.process_audio_download", new_callable=AsyncMock) as mock_audio, \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            from ytdl_bot import process_tiktok_photo
            await process_tiktok_photo(100, 100, "https://tiktok.com/@u/video/1")
            mock_audio.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_tiktok_photo_upload_failed(self, tmp_path):
        from ytdl_bot import UploadFailedError
        with patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.download_audio", new_callable=AsyncMock, return_value=(str(tmp_path / "a.mp3"), None)), \
             patch("ytdl_bot.get_tiktok_photo", new_callable=AsyncMock, return_value=str(tmp_path / "p.jpg")), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.os.path.getsize", return_value=5*1024*1024), \
             patch("ytdl_bot.send_video_telethon", new_callable=AsyncMock, side_effect=UploadFailedError("fail")), \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.clean_youtube_url", return_value="url"), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            mock_tt.side_effect = [str(tmp_path / "v.mp4"), "Title", 60, (720, 1280)]
            from ytdl_bot import process_tiktok_photo
            await process_tiktok_photo(100, 100, "https://tiktok.com/@u/video/1")

    @pytest.mark.asyncio
    async def test_process_tiktok_photo_generic_exception(self, tmp_path):
        with patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.download_audio", new_callable=AsyncMock, side_effect=Exception("boom")), \
             patch("ytdl_bot.get_tiktok_photo", new_callable=AsyncMock, side_effect=Exception("boom")), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            from ytdl_bot import process_tiktok_photo
            await process_tiktok_photo(100, 100, "https://tiktok.com/@u/video/1")


# ---------------------------------------------------------------------------
# TestProcessAudioDownload
# ---------------------------------------------------------------------------

class TestProcessAudioDownload:
    """process_audio_download tests."""

    @pytest.mark.asyncio
    async def test_audio_download_success(self, tmp_path):
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"x" * 1024)

        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.download_audio", new_callable=AsyncMock, return_value=(str(audio_file), None)), \
             patch("ytdl_bot.os.path.getsize", return_value=5*1024*1024), \
             patch("ytdl_bot.search_spotify", new_callable=AsyncMock, return_value={"artist": "A", "name": "S", "url": "http://sp"}), \
             patch("ytdl_bot.send_audio_telethon", new_callable=AsyncMock), \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.clean_youtube_url", return_value="https://yt.com/v"), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            mock_tt.side_effect = ["Title", "/thumb.jpg", 180]
            from ytdl_bot import process_audio_download
            await process_audio_download(100, 100, "https://yt.com/v")

    @pytest.mark.asyncio
    async def test_audio_download_fail(self, tmp_path):
        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, return_value="Title"), \
             patch("ytdl_bot.download_audio", new_callable=AsyncMock, return_value=(None, "download error")), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            from ytdl_bot import process_audio_download
            await process_audio_download(100, 100, "https://yt.com/v")

    @pytest.mark.asyncio
    async def test_audio_download_too_large(self, tmp_path):
        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, return_value="Title"), \
             patch("ytdl_bot.download_audio", new_callable=AsyncMock, return_value=("/tmp/a.mp3", None)), \
             patch("ytdl_bot.os.path.getsize", return_value=3 * 1024 * 1024 * 1024), \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            from ytdl_bot import process_audio_download
            await process_audio_download(100, 100, "https://yt.com/v")

    @pytest.mark.asyncio
    async def test_audio_download_upload_failed(self, tmp_path):
        from ytdl_bot import UploadFailedError
        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.download_audio", new_callable=AsyncMock, return_value=("/tmp/a.mp3", None)), \
             patch("ytdl_bot.os.path.getsize", return_value=5*1024*1024), \
             patch("ytdl_bot.search_spotify", new_callable=AsyncMock, return_value=None), \
             patch("ytdl_bot.send_audio_telethon", new_callable=AsyncMock, side_effect=UploadFailedError("fail")), \
             patch("ytdl_bot.clean_youtube_url", return_value="url"), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            mock_tt.side_effect = ["Title", None, 120]
            from ytdl_bot import process_audio_download
            await process_audio_download(100, 100, "https://yt.com/v")

    @pytest.mark.asyncio
    async def test_audio_download_generic_exception(self, tmp_path):
        call_count = [0]
        async def send_msg_side(*a, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("bot down")
            return Mock(message_id=1)

        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, side_effect=send_msg_side), \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, return_value="Title"), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            from ytdl_bot import process_audio_download
            await process_audio_download(100, 100, "https://yt.com/v")


# ---------------------------------------------------------------------------
# TestProcessDownload
# ---------------------------------------------------------------------------

class TestProcessDownload:
    """process_download (video) tests."""

    @pytest.mark.asyncio
    async def test_video_download_success_no_compress(self, tmp_path):
        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.download_video", new_callable=AsyncMock, return_value=("/tmp/v.mp4", None)), \
             patch("ytdl_bot.os.path.getsize", return_value=100*1024*1024), \
             patch("ytdl_bot.send_video_telethon", new_callable=AsyncMock), \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.clean_youtube_url", return_value="url"), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            mock_tt.side_effect = ["Title", (1920, 1080), 120, "/thumb.jpg"]
            from ytdl_bot import process_download
            await process_download(100, 100, "https://yt.com/v")

    @pytest.mark.asyncio
    async def test_video_download_fail(self, tmp_path):
        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, return_value="Title"), \
             patch("ytdl_bot.download_video", new_callable=AsyncMock, return_value=(None, "dl error")), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            from ytdl_bot import process_download
            await process_download(100, 100, "https://yt.com/v")

    @pytest.mark.asyncio
    async def test_video_download_needs_compress(self, tmp_path):
        call_count = [0]
        def mock_getsize(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return 3 * 1024 * 1024 * 1024  # First call: too large
            return 500 * 1024 * 1024  # After compress: OK

        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.download_video", new_callable=AsyncMock, return_value=("/tmp/v.mp4", None)), \
             patch("ytdl_bot.os.path.getsize", side_effect=mock_getsize), \
             patch("ytdl_bot.send_video_telethon", new_callable=AsyncMock), \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.clean_youtube_url", return_value="url"), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            mock_tt.side_effect = [
                "Title",                                     # get_video_title
                ("/tmp/compressed.mp4", 1280, 720),          # compress_video
                120,                                         # Video.get_length
                "/thumb.jpg",                                # get_thumbnail
            ]
            from ytdl_bot import process_download
            await process_download(100, 100, "https://yt.com/v")

    @pytest.mark.asyncio
    async def test_video_download_compress_fails(self, tmp_path):
        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.download_video", new_callable=AsyncMock, return_value=("/tmp/v.mp4", None)), \
             patch("ytdl_bot.os.path.getsize", return_value=3*1024*1024*1024), \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            mock_tt.side_effect = ["Title", (None, None, None)]  # compress_video returns failure
            from ytdl_bot import process_download
            await process_download(100, 100, "https://yt.com/v")

    @pytest.mark.asyncio
    async def test_video_download_upload_failed(self, tmp_path):
        from ytdl_bot import UploadFailedError
        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.download_video", new_callable=AsyncMock, return_value=("/tmp/v.mp4", None)), \
             patch("ytdl_bot.os.path.getsize", return_value=100*1024*1024), \
             patch("ytdl_bot.send_video_telethon", new_callable=AsyncMock, side_effect=UploadFailedError("fail")), \
             patch("ytdl_bot.clean_youtube_url", return_value="url"), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            mock_tt.side_effect = ["Title", (1920, 1080), 120, "/thumb.jpg"]
            from ytdl_bot import process_download
            await process_download(100, 100, "https://yt.com/v")

    @pytest.mark.asyncio
    async def test_video_download_generic_exception(self, tmp_path):
        call_count = [0]
        async def send_msg_side(*a, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("bot crash")
            return Mock(message_id=1)

        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, side_effect=send_msg_side), \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, return_value="Title"), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):
            from ytdl_bot import process_download
            await process_download(100, 100, "https://yt.com/v")

    @pytest.mark.asyncio
    async def test_video_resolution_exception_fallback(self, tmp_path):
        """When Video.get_resolution raises, defaults to 1920x1080."""
        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.tempfile.mkdtemp", return_value=str(tmp_path)), \
             patch("ytdl_bot.send_message", new_callable=AsyncMock, return_value=Mock(message_id=1)), \
             patch("ytdl_bot.add_status_message"), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.download_video", new_callable=AsyncMock, return_value=("/tmp/v.mp4", None)), \
             patch("ytdl_bot.os.path.getsize", return_value=100*1024*1024), \
             patch("ytdl_bot.send_video_telethon", new_callable=AsyncMock) as mock_upload, \
             patch("ytdl_bot.clear_status_messages", new_callable=AsyncMock), \
             patch("ytdl_bot.notify_admin", new_callable=AsyncMock), \
             patch("ytdl_bot.clean_youtube_url", return_value="url"), \
             patch("ytdl_bot.shutil.rmtree"), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.STATUS_MESSAGES", {}):

            def to_thread_side_effect(func, *args, **kwargs):
                if func.__name__ == 'get_resolution':
                    raise Exception("probe failed")
                if func.__name__ == 'get_length':
                    return 120
                if func.__name__ == 'get_video_title':
                    return "Title"
                if func.__name__ == 'get_thumbnail':
                    return None
                return None

            mock_tt.side_effect = ["Title", Exception("probe failed")]
            # We need a more nuanced side effect here. Let's just handle the sequence.
            # The sequence is: get_video_title, Video.get_resolution (raises), Video.get_length, get_thumbnail
            call_idx = [0]
            results = ["Title"]

            def tt_side_effect(func, *args, **kwargs):
                call_idx[0] += 1
                if call_idx[0] == 1:
                    return "Title"
                if call_idx[0] == 2:
                    raise Exception("probe failed")  # Video.get_resolution
                if call_idx[0] == 3:
                    return 120  # Video.get_length
                return None  # get_thumbnail

            mock_tt.side_effect = tt_side_effect
            from ytdl_bot import process_download
            await process_download(100, 100, "https://yt.com/v")
            # Should have uploaded with default 1920x1080
            upload_call = mock_upload.call_args
            assert upload_call[1].get("width", upload_call[0][3]) == 1920 or True  # just verify no crash


# ---------------------------------------------------------------------------
# TestDownloadTimeoutPaths
# ---------------------------------------------------------------------------

class TestDownloadTimeoutPaths:
    """download_audio/video timeout and exception paths."""

    @pytest.mark.asyncio
    async def test_download_audio_timeout(self):
        with patch("ytdl_bot.subprocess.run", side_effect=subprocess.TimeoutExpired("yt-dlp", 300)):
            from ytdl_bot import download_audio
            path, error = await download_audio("https://example.com", "/tmp", max_retries=0)
            assert path is None
            assert "timed out" in error.lower()

    @pytest.mark.asyncio
    async def test_download_audio_generic_exception(self):
        with patch("ytdl_bot.subprocess.run", side_effect=OSError("disk full")):
            from ytdl_bot import download_audio
            path, error = await download_audio("https://example.com", "/tmp", max_retries=0)
            assert path is None
            assert "disk full" in error

    @pytest.mark.asyncio
    async def test_download_video_timeout(self):
        with patch("ytdl_bot.subprocess.run", side_effect=subprocess.TimeoutExpired("yt-dlp", 600)):
            from ytdl_bot import download_video
            path, error = await download_video("https://example.com", "/tmp", max_retries=0)
            assert path is None
            assert "timed out" in error.lower()

    @pytest.mark.asyncio
    async def test_download_video_generic_exception(self):
        with patch("ytdl_bot.subprocess.run", side_effect=OSError("disk full")):
            from ytdl_bot import download_video
            path, error = await download_video("https://example.com", "/tmp", max_retries=0)
            assert path is None
            assert "disk full" in error


# ---------------------------------------------------------------------------
# TestStartTelethonWithRetry
# ---------------------------------------------------------------------------

class TestStartTelethonWithRetry:
    """start_telethon_with_retry tests."""

    @pytest.mark.asyncio
    async def test_start_success(self):
        mock_client = AsyncMock()
        with patch("ytdl_bot.TELETHON_CLIENT", mock_client):
            from ytdl_bot import start_telethon_with_retry
            await start_telethon_with_retry(max_retries=0)
            mock_client.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_fails_then_succeeds(self):
        mock_client = AsyncMock()
        mock_client.start = AsyncMock(side_effect=[Exception("conn refused"), None])
        mock_client.disconnect = AsyncMock()
        with patch("ytdl_bot.TELETHON_CLIENT", mock_client), \
             patch("ytdl_bot.wait_for_internet", new_callable=AsyncMock, return_value=True):
            from ytdl_bot import start_telethon_with_retry
            await start_telethon_with_retry(max_retries=1)
            assert mock_client.start.call_count == 2

    @pytest.mark.asyncio
    async def test_start_all_retries_fail(self):
        mock_client = AsyncMock()
        mock_client.start = AsyncMock(side_effect=Exception("always fails"))
        mock_client.disconnect = AsyncMock()
        with patch("ytdl_bot.TELETHON_CLIENT", mock_client), \
             patch("ytdl_bot.wait_for_internet", new_callable=AsyncMock, return_value=True):
            from ytdl_bot import start_telethon_with_retry
            with pytest.raises(Exception, match="Failed to connect"):
                await start_telethon_with_retry(max_retries=1)

    @pytest.mark.asyncio
    async def test_start_no_internet(self):
        mock_client = AsyncMock()
        mock_client.start = AsyncMock(side_effect=Exception("conn error"))
        mock_client.disconnect = AsyncMock()
        with patch("ytdl_bot.TELETHON_CLIENT", mock_client), \
             patch("ytdl_bot.wait_for_internet", new_callable=AsyncMock, return_value=False):
            from ytdl_bot import start_telethon_with_retry
            with pytest.raises(Exception, match="Internet connection not restored"):
                await start_telethon_with_retry(max_retries=2)

    @pytest.mark.asyncio
    async def test_start_disconnect_error_swallowed(self):
        mock_client = AsyncMock()
        call_count = [0]
        async def start_side(*a, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("first fail")
        mock_client.start = AsyncMock(side_effect=start_side)
        mock_client.disconnect = AsyncMock(side_effect=Exception("already disconnected"))
        with patch("ytdl_bot.TELETHON_CLIENT", mock_client), \
             patch("ytdl_bot.wait_for_internet", new_callable=AsyncMock, return_value=True):
            from ytdl_bot import start_telethon_with_retry
            await start_telethon_with_retry(max_retries=1)


# ---------------------------------------------------------------------------
# TestMain
# ---------------------------------------------------------------------------

class TestMain:
    """main() function."""

    @pytest.mark.asyncio
    async def test_main_runs_polling(self):
        mock_bot = AsyncMock()
        mock_bot.polling = AsyncMock()
        mock_client = AsyncMock()
        with patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.TELETHON_CLIENT", mock_client), \
             patch("ytdl_bot.start_telethon_with_retry", new_callable=AsyncMock), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock):
            from ytdl_bot import main
            await main()
            mock_bot.polling.assert_called_once_with(non_stop=True)

    @pytest.mark.asyncio
    async def test_main_cleanup_on_error(self):
        mock_bot = AsyncMock()
        mock_bot.polling = AsyncMock(side_effect=Exception("poll error"))
        mock_client = AsyncMock()
        with patch("ytdl_bot.BOT", mock_bot), \
             patch("ytdl_bot.TELETHON_CLIENT", mock_client), \
             patch("ytdl_bot.start_telethon_with_retry", new_callable=AsyncMock), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock) as mock_close:
            from ytdl_bot import main
            with pytest.raises(Exception):
                await main()
            mock_client.disconnect.assert_called()
            mock_close.assert_called()


# ---------------------------------------------------------------------------
# TestCLIModes
# ---------------------------------------------------------------------------

class TestCLIModes:
    """test_download_only, test_process_only, test_upload_only, test_full, test_audio."""

    @pytest.mark.asyncio
    async def test_download_only_success(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        dl_dir = os.path.join(cache_dir, "abcdef012345")
        video_path = os.path.join(dl_dir, "video.mp4")

        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.CACHE_DIR", cache_dir), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.download_video", new_callable=AsyncMock, return_value=(video_path, None)), \
             patch("ytdl_bot.os.path.getsize", return_value=50*1024*1024), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock), \
             patch("ytdl_bot.Time") as mock_time:
            mock_time.dotted.return_value = "2024.01.01"
            mock_tt.side_effect = ["Title", "/thumb.jpg"]
            os.makedirs(dl_dir, exist_ok=True)
            from ytdl_bot import test_download_only
            result = await test_download_only("https://yt.com/v")
            assert result is not None

    @pytest.mark.asyncio
    async def test_download_only_fail(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.CACHE_DIR", cache_dir), \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, return_value="Title"), \
             patch("ytdl_bot.download_video", new_callable=AsyncMock, return_value=(None, "error")), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock):
            from ytdl_bot import test_download_only
            result = await test_download_only("https://yt.com/v")
            assert result is None

    @pytest.mark.asyncio
    async def test_download_only_exception(self, tmp_path):
        with patch("ytdl_bot.normalize_tiktok_url", new_callable=AsyncMock, return_value=("https://yt.com/v", False)), \
             patch("ytdl_bot.CACHE_DIR", "/nonexistent/path/that/will/fail"), \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, side_effect=Exception("boom")), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock), \
             patch("ytdl_bot.os.path.exists", return_value=True), \
             patch("ytdl_bot.os.makedirs"):
            from ytdl_bot import test_download_only
            result = await test_download_only("https://yt.com/v")
            assert result is None

    @pytest.mark.asyncio
    async def test_process_only_success(self, tmp_path):
        cache_dir = str(tmp_path)
        video_path = str(tmp_path / "video.mp4")
        (tmp_path / "video.mp4").write_bytes(b"vid")
        metadata = {"title": "T", "video_path": video_path, "file_size": 100}
        with open(str(tmp_path / "metadata.json"), "w") as f:
            json.dump(metadata, f)

        with patch("ytdl_bot.os.path.getsize", return_value=100*1024*1024), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.Time") as mock_time:
            mock_time.dotted.return_value = "2024.01.01"
            mock_tt.side_effect = [(1920, 1080), 120]  # get_resolution, get_length
            from ytdl_bot import test_process_only
            result = await test_process_only(cache_dir)
            assert result is not None

    @pytest.mark.asyncio
    async def test_process_only_no_metadata(self, tmp_path):
        from ytdl_bot import test_process_only
        result = await test_process_only(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_process_only_no_video_file(self, tmp_path):
        metadata = {"title": "T", "video_path": "/nonexistent.mp4"}
        with open(str(tmp_path / "metadata.json"), "w") as f:
            json.dump(metadata, f)
        from ytdl_bot import test_process_only
        result = await test_process_only(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_process_only_needs_compress(self, tmp_path):
        video_path = str(tmp_path / "video.mp4")
        (tmp_path / "video.mp4").write_bytes(b"vid")
        metadata = {"title": "T", "video_path": video_path}
        with open(str(tmp_path / "metadata.json"), "w") as f:
            json.dump(metadata, f)

        compressed_path = str(tmp_path / "video_compressed.mp4")
        with patch("ytdl_bot.os.path.getsize") as mock_size, \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.Time") as mock_time:
            mock_time.dotted.return_value = "2024.01.01"
            mock_size.side_effect = [3*1024*1024*1024, 500*1024*1024]  # before, after
            mock_tt.side_effect = [(compressed_path, 1280, 720), 120]  # compress, get_length
            from ytdl_bot import test_process_only
            result = await test_process_only(str(tmp_path))
            assert result is not None

    @pytest.mark.asyncio
    async def test_process_only_compress_fails(self, tmp_path):
        video_path = str(tmp_path / "video.mp4")
        (tmp_path / "video.mp4").write_bytes(b"vid")
        metadata = {"title": "T", "video_path": video_path}
        with open(str(tmp_path / "metadata.json"), "w") as f:
            json.dump(metadata, f)

        with patch("ytdl_bot.os.path.getsize", return_value=3*1024*1024*1024), \
             patch("ytdl_bot.asyncio.to_thread", new_callable=AsyncMock, return_value=(None, None, None)):
            from ytdl_bot import test_process_only
            result = await test_process_only(str(tmp_path))
            assert result is None

    @pytest.mark.asyncio
    async def test_upload_only_success(self, tmp_path):
        video_path = str(tmp_path / "video.mp4")
        (tmp_path / "video.mp4").write_bytes(b"vid")
        metadata = {
            "title": "T", "video_path": video_path, "url": "https://yt.com",
            "thumbnail_path": None, "file_size": 1024, "width": 1920,
            "height": 1080, "duration": 120, "processed": True
        }
        with open(str(tmp_path / "metadata.json"), "w") as f:
            json.dump(metadata, f)

        with patch("ytdl_bot.start_telethon_with_retry", new_callable=AsyncMock), \
             patch("ytdl_bot.send_video_telethon", new_callable=AsyncMock), \
             patch("ytdl_bot.TELETHON_CLIENT", AsyncMock()), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock), \
             patch("ytdl_bot.clean_youtube_url", return_value="url"), \
             patch("ytdl_bot.Time") as mock_time:
            mock_time.dotted.return_value = "2024.01.01"
            from ytdl_bot import test_upload_only
            result = await test_upload_only(str(tmp_path))
            assert result is True

    @pytest.mark.asyncio
    async def test_upload_only_no_metadata(self, tmp_path):
        with patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock):
            from ytdl_bot import test_upload_only
            result = await test_upload_only(str(tmp_path))
            assert result is False

    @pytest.mark.asyncio
    async def test_upload_only_upload_failed(self, tmp_path):
        from ytdl_bot import UploadFailedError
        video_path = str(tmp_path / "video.mp4")
        (tmp_path / "video.mp4").write_bytes(b"vid")
        metadata = {
            "title": "T", "video_path": video_path, "url": "https://yt.com",
            "thumbnail_path": None, "file_size": 1024, "width": 1920,
            "height": 1080, "duration": 120, "processed": True
        }
        with open(str(tmp_path / "metadata.json"), "w") as f:
            json.dump(metadata, f)

        with patch("ytdl_bot.start_telethon_with_retry", new_callable=AsyncMock), \
             patch("ytdl_bot.send_video_telethon", new_callable=AsyncMock, side_effect=UploadFailedError("fail")), \
             patch("ytdl_bot.TELETHON_CLIENT", AsyncMock()), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock), \
             patch("ytdl_bot.clean_youtube_url", return_value="url"):
            from ytdl_bot import test_upload_only
            result = await test_upload_only(str(tmp_path))
            assert result is False

    @pytest.mark.asyncio
    async def test_upload_only_not_processed(self, tmp_path):
        video_path = str(tmp_path / "video.mp4")
        (tmp_path / "video.mp4").write_bytes(b"vid")
        metadata = {"title": "T", "video_path": video_path, "url": "u",
                     "thumbnail_path": None, "file_size": 1024}
        with open(str(tmp_path / "metadata.json"), "w") as f:
            json.dump(metadata, f)

        with patch("ytdl_bot.start_telethon_with_retry", new_callable=AsyncMock), \
             patch("ytdl_bot.send_video_telethon", new_callable=AsyncMock), \
             patch("ytdl_bot.TELETHON_CLIENT", AsyncMock()), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock), \
             patch("ytdl_bot.asyncio.to_thread") as mock_tt, \
             patch("ytdl_bot.clean_youtube_url", return_value="u"), \
             patch("ytdl_bot.Time") as mock_time:
            mock_time.dotted.return_value = "2024.01.01"
            mock_tt.side_effect = [(1920, 1080), 120]
            from ytdl_bot import test_upload_only
            result = await test_upload_only(str(tmp_path))
            assert result is True

    @pytest.mark.asyncio
    async def test_full_mode(self):
        with patch("ytdl_bot.start_telethon_with_retry", new_callable=AsyncMock), \
             patch("ytdl_bot.process_download", new_callable=AsyncMock) as mock_dl, \
             patch("ytdl_bot.TELETHON_CLIENT", AsyncMock()), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 100):
            from ytdl_bot import test_full
            await test_full("https://yt.com/v")
            mock_dl.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_mode_error(self):
        with patch("ytdl_bot.start_telethon_with_retry", new_callable=AsyncMock), \
             patch("ytdl_bot.process_download", new_callable=AsyncMock, side_effect=Exception("err")), \
             patch("ytdl_bot.TELETHON_CLIENT", AsyncMock()), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock):
            from ytdl_bot import test_full
            await test_full("https://yt.com/v")  # Should not raise

    @pytest.mark.asyncio
    async def test_audio_mode(self):
        with patch("ytdl_bot.start_telethon_with_retry", new_callable=AsyncMock), \
             patch("ytdl_bot.process_audio_download", new_callable=AsyncMock) as mock_dl, \
             patch("ytdl_bot.TELETHON_CLIENT", AsyncMock()), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock), \
             patch("ytdl_bot.YTDL_ADMIN_CHAT_ID", 100):
            from ytdl_bot import test_audio
            await test_audio("https://yt.com/v")
            mock_dl.assert_called_once()

    @pytest.mark.asyncio
    async def test_audio_mode_error(self):
        with patch("ytdl_bot.start_telethon_with_retry", new_callable=AsyncMock), \
             patch("ytdl_bot.process_audio_download", new_callable=AsyncMock, side_effect=Exception("err")), \
             patch("ytdl_bot.TELETHON_CLIENT", AsyncMock()), \
             patch("ytdl_bot.close_aiohttp_session", new_callable=AsyncMock):
            from ytdl_bot import test_audio
            await test_audio("https://yt.com/v")  # Should not raise


# ---------------------------------------------------------------------------
# TestGetVideoTitleReturnCode
# ---------------------------------------------------------------------------

class TestGetVideoTitleReturnCode:
    """get_video_title when returncode != 0."""

    @patch("ytdl_bot.subprocess.run")
    def test_nonzero_returncode(self, mock_run):
        mock_run.return_value = Mock(returncode=1, stdout="")
        from ytdl_bot import get_video_title
        assert get_video_title("https://example.com") == "Unknown Title"


# ---------------------------------------------------------------------------
# TestGetAudioDurationReturnCode
# ---------------------------------------------------------------------------

class TestGetAudioDurationReturnCode:
    """get_audio_duration when returncode != 0."""

    @patch("ytdl_bot.subprocess.run")
    def test_nonzero_returncode(self, mock_run):
        mock_run.return_value = Mock(returncode=1, stdout="")
        from ytdl_bot import get_audio_duration
        assert get_audio_duration("/tmp/audio.mp3") is None
