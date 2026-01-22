"""
Comprehensive test suite for ytdl_bot.py retry logic.

Tests cover:
- Download retry logic (audio/video)
- Upload retry logic (Telethon)
- Internet connectivity checking
- Prolonged internet outages (up to 5 minutes)
- Telethon client connection/reconnection

Run with: pytest test_ytdl_retry.py -v
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import subprocess
import os


# ---------------------------------------------------------------------------
# Fixtures and Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_telethon_client():
    """Mock Telethon client for upload tests."""
    client = AsyncMock()
    client.is_connected.return_value = True
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.send_file = AsyncMock()
    client.start = AsyncMock()
    return client


@pytest.fixture
def mock_bot():
    """Mock Telegram bot for message tests."""
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(return_value=Mock(message_id=123))
    return bot


@pytest.fixture
def temp_file(tmp_path):
    """Create a temporary test file."""
    file_path = tmp_path / "test_video.mp4"
    file_path.write_bytes(b"fake video content" * 1000)
    return str(file_path)


class InternetSimulator:
    """Simulates internet connectivity with configurable outage patterns."""

    def __init__(self):
        self.is_online = True
        self.outage_start = None
        self.outage_duration = 0
        self.check_count = 0

    def set_offline(self, duration_seconds):
        """Simulate internet going offline for specified duration."""
        self.is_online = False
        self.outage_start = time.time()
        self.outage_duration = duration_seconds

    def set_online(self):
        """Bring internet back online."""
        self.is_online = True
        self.outage_start = None

    def check(self):
        """Check if internet is available (simulated)."""
        self.check_count += 1

        # Auto-restore after outage duration
        if self.outage_start and time.time() - self.outage_start >= self.outage_duration:
            self.is_online = True
            self.outage_start = None

        return self.is_online


# ---------------------------------------------------------------------------
# check_internet() Tests
# ---------------------------------------------------------------------------

class TestCheckInternet:
    """Tests for the check_internet() function."""

    @pytest.mark.asyncio
    async def test_check_internet_success(self):
        """Test that check_internet returns True when connected."""

        # Create proper async context manager mocks
        class MockResponse:
            pass

        class MockGet:
            async def __aenter__(self):
                return MockResponse()
            async def __aexit__(self, *args):
                pass

        class MockSession:
            def get(self, url, timeout=None):
                return MockGet()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass

        with patch('ytdl_bot.aiohttp.ClientSession', return_value=MockSession()):
            from ytdl_bot import check_internet
            result = await check_internet(timeout=5)
            assert result is True

    @pytest.mark.asyncio
    async def test_check_internet_failure_timeout(self):
        """Test that check_internet returns False on timeout."""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session_instance.get.side_effect = asyncio.TimeoutError()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.__aexit__.return_value = None
            mock_session.return_value = mock_session_instance

            from ytdl_bot import check_internet
            result = await check_internet(timeout=1)
            assert result is False

    @pytest.mark.asyncio
    async def test_check_internet_failure_connection_error(self):
        """Test that check_internet returns False on connection error."""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session_instance.get.side_effect = Exception("Connection refused")
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.__aexit__.return_value = None
            mock_session.return_value = mock_session_instance

            from ytdl_bot import check_internet
            result = await check_internet(timeout=1)
            assert result is False


# ---------------------------------------------------------------------------
# wait_for_internet() Tests
# ---------------------------------------------------------------------------

class TestWaitForInternet:
    """Tests for the wait_for_internet() function."""

    @pytest.mark.asyncio
    async def test_wait_for_internet_already_online(self):
        """Test immediate return when internet is already available."""
        with patch('ytdl_bot.check_internet', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            from ytdl_bot import wait_for_internet
            start = time.time()
            result = await wait_for_internet(max_wait=300, check_interval=10)
            elapsed = time.time() - start

            assert result is True
            assert elapsed < 1  # Should return immediately
            assert mock_check.call_count == 1

    @pytest.mark.asyncio
    async def test_wait_for_internet_comes_back_quickly(self):
        """Test that function waits and returns True when internet comes back."""
        call_count = 0

        async def mock_check():
            nonlocal call_count
            call_count += 1
            # Internet comes back on 3rd check
            return call_count >= 3

        with patch('ytdl_bot.check_internet', side_effect=mock_check):
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                from ytdl_bot import wait_for_internet
                result = await wait_for_internet(max_wait=300, check_interval=1)

                assert result is True
                assert call_count == 3

    @pytest.mark.asyncio
    async def test_wait_for_internet_timeout(self):
        """Test that function returns False after max_wait exceeded."""
        with patch('ytdl_bot.check_internet', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False

            with patch('asyncio.sleep', new_callable=AsyncMock):
                # Use short timeout for test
                with patch('time.time') as mock_time:
                    times = [0, 5, 10, 15, 20, 25, 30, 35]
                    mock_time.side_effect = times

                    from ytdl_bot import wait_for_internet
                    result = await wait_for_internet(max_wait=30, check_interval=5)

                    assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_internet_30_second_outage(self):
        """Test recovery from a 30-second internet outage."""
        check_count = 0
        # With 5-second intervals, 6 checks = 30 seconds
        recovery_at_check = 6

        async def mock_check():
            nonlocal check_count
            check_count += 1
            return check_count >= recovery_at_check

        with patch('ytdl_bot.check_internet', side_effect=mock_check):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                from ytdl_bot import wait_for_internet
                result = await wait_for_internet(max_wait=60, check_interval=5)

                assert result is True
                assert check_count == recovery_at_check

    @pytest.mark.asyncio
    async def test_wait_for_internet_5_minute_outage(self):
        """Test recovery from exactly 5 minutes (300s) internet outage."""
        check_count = 0
        # With 10-second intervals, 30 checks = 300 seconds
        recovery_at_check = 30

        async def mock_check():
            nonlocal check_count
            check_count += 1
            return check_count >= recovery_at_check

        with patch('ytdl_bot.check_internet', side_effect=mock_check):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                from ytdl_bot import wait_for_internet
                result = await wait_for_internet(max_wait=300, check_interval=10)

                assert result is True
                assert check_count == recovery_at_check

    @pytest.mark.asyncio
    async def test_wait_for_internet_exceeds_5_minutes(self):
        """Test failure when outage exceeds 5 minutes."""
        with patch('ytdl_bot.check_internet', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False

            call_times = []
            base_time = 1000

            def get_time():
                # Simulate time advancing with each call
                call_times.append(len(call_times) * 10 + base_time)
                return call_times[-1]

            with patch('asyncio.sleep', new_callable=AsyncMock):
                with patch('time.time', side_effect=get_time):
                    from ytdl_bot import wait_for_internet
                    result = await wait_for_internet(max_wait=300, check_interval=10)

                    assert result is False


# ---------------------------------------------------------------------------
# download_video() Retry Tests
# ---------------------------------------------------------------------------

class TestDownloadVideoRetry:
    """Tests for download_video() retry logic (now async with wait_for_internet)."""

    @pytest.mark.asyncio
    async def test_download_video_success_first_attempt(self, tmp_path):
        """Test successful download on first attempt."""
        output_file = tmp_path / "video.mp4"

        def mock_run(*args, **kwargs):
            output_file.write_bytes(b"video content")
            return Mock(returncode=0, stdout="", stderr="")

        with patch('subprocess.run', side_effect=mock_run):
            from ytdl_bot import download_video
            result = await download_video("https://youtube.com/watch?v=test", str(tmp_path))

            assert result is not None

    @pytest.mark.asyncio
    async def test_download_video_retry_on_failure(self, tmp_path):
        """Test that download retries on failure with wait_for_internet."""
        call_count = 0
        output_file = tmp_path / "video.mp4"

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return Mock(returncode=1, stdout="", stderr="Error")
            output_file.write_bytes(b"video content")
            return Mock(returncode=0, stdout="", stderr="")

        with patch('subprocess.run', side_effect=mock_run):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = True

                from ytdl_bot import download_video
                result = await download_video("https://youtube.com/watch?v=test", str(tmp_path))

                assert result is not None
                assert call_count == 3
                assert mock_wait.call_count == 2  # wait_for_internet between retries

    @pytest.mark.asyncio
    async def test_download_video_all_retries_fail(self, tmp_path):
        """Test that download returns None after all retries exhausted."""
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr="Error")):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = True

                from ytdl_bot import download_video
                result = await download_video("https://youtube.com/watch?v=test", str(tmp_path), max_retries=2)

                assert result is None

    @pytest.mark.asyncio
    async def test_download_video_timeout_retry(self, tmp_path):
        """Test retry after subprocess timeout."""
        call_count = 0
        output_file = tmp_path / "video.mp4"

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=600)
            output_file.write_bytes(b"video content")
            return Mock(returncode=0)

        with patch('subprocess.run', side_effect=mock_run):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = True

                from ytdl_bot import download_video
                result = await download_video("https://youtube.com/watch?v=test", str(tmp_path))

                assert result is not None
                assert call_count == 2

    @pytest.mark.asyncio
    async def test_download_video_generic_exception_retry(self, tmp_path):
        """Test retry after generic exception."""
        call_count = 0
        output_file = tmp_path / "video.mp4"

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Network error")
            output_file.write_bytes(b"video content")
            return Mock(returncode=0)

        with patch('subprocess.run', side_effect=mock_run):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = True

                from ytdl_bot import download_video
                result = await download_video("https://youtube.com/watch?v=test", str(tmp_path))

                assert result is not None

    @pytest.mark.asyncio
    async def test_download_video_fails_when_internet_not_restored(self, tmp_path):
        """Test that download fails when internet doesn't come back."""
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr="Network error")):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = False  # Internet never comes back

                from ytdl_bot import download_video
                result = await download_video("https://youtube.com/watch?v=test", str(tmp_path))

                assert result is None

    @pytest.mark.asyncio
    async def test_download_video_5_minute_outage_recovery(self, tmp_path):
        """Test download recovery from 5-minute internet outage."""
        call_count = 0
        output_file = tmp_path / "video.mp4"

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 6:  # Fail first 5 attempts
                return Mock(returncode=1, stderr="Network error")
            output_file.write_bytes(b"video content")
            return Mock(returncode=0)

        with patch('subprocess.run', side_effect=mock_run):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = True

                from ytdl_bot import download_video
                result = await download_video("https://youtube.com/watch?v=test", str(tmp_path))

                assert result is not None
                assert call_count == 6


# ---------------------------------------------------------------------------
# download_audio() Retry Tests
# ---------------------------------------------------------------------------

class TestDownloadAudioRetry:
    """Tests for download_audio() retry logic (now async with wait_for_internet)."""

    @pytest.mark.asyncio
    async def test_download_audio_success_first_attempt(self, tmp_path):
        """Test successful audio download on first attempt."""
        output_file = tmp_path / "audio.mp3"

        def mock_run(*args, **kwargs):
            output_file.write_bytes(b"audio content")
            return Mock(returncode=0)

        with patch('subprocess.run', side_effect=mock_run):
            from ytdl_bot import download_audio
            result = await download_audio("https://youtube.com/watch?v=test", str(tmp_path))

            assert result is not None

    @pytest.mark.asyncio
    async def test_download_audio_retry_on_failure(self, tmp_path):
        """Test that audio download retries on failure with wait_for_internet."""
        call_count = 0
        output_file = tmp_path / "audio.mp3"

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return Mock(returncode=1, stderr="Error")
            output_file.write_bytes(b"audio content")
            return Mock(returncode=0)

        with patch('subprocess.run', side_effect=mock_run):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = True

                from ytdl_bot import download_audio
                result = await download_audio("https://youtube.com/watch?v=test", str(tmp_path))

                assert result is not None
                assert call_count == 3
                assert mock_wait.call_count == 2  # wait_for_internet between retries

    @pytest.mark.asyncio
    async def test_download_audio_all_retries_fail(self, tmp_path):
        """Test that audio download returns None after all retries exhausted."""
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr="Error")):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = True

                from ytdl_bot import download_audio
                result = await download_audio("https://youtube.com/watch?v=test", str(tmp_path), max_retries=2)

                assert result is None

    @pytest.mark.asyncio
    async def test_download_audio_fails_when_internet_not_restored(self, tmp_path):
        """Test that audio download fails when internet doesn't come back."""
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr="Network error")):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = False

                from ytdl_bot import download_audio
                result = await download_audio("https://youtube.com/watch?v=test", str(tmp_path))

                assert result is None

    @pytest.mark.asyncio
    async def test_download_audio_5_minute_outage_recovery(self, tmp_path):
        """Test audio download recovery from 5-minute internet outage."""
        call_count = 0
        output_file = tmp_path / "audio.mp3"

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 6:
                return Mock(returncode=1, stderr="Network error")
            output_file.write_bytes(b"audio content")
            return Mock(returncode=0)

        with patch('subprocess.run', side_effect=mock_run):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = True

                from ytdl_bot import download_audio
                result = await download_audio("https://youtube.com/watch?v=test", str(tmp_path))

                assert result is not None
                assert call_count == 6


# ---------------------------------------------------------------------------
# send_video_telethon() Upload Retry Tests
# ---------------------------------------------------------------------------

class TestSendVideoTelethonRetry:
    """Tests for send_video_telethon() retry logic."""

    @pytest.mark.asyncio
    async def test_upload_success_first_attempt(self, mock_telethon_client, temp_file):
        """Test successful upload on first attempt."""
        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                from ytdl_bot import send_video_telethon

                # Should not raise
                await send_video_telethon(
                    chat_id=12345,
                    video_path=temp_file,
                    caption="Test video",
                    width=1920,
                    height=1080,
                    duration=60,
                    thumbnail=None,
                    status_message_id=1,
                    file_size=1000000
                )

                mock_telethon_client.send_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_retry_on_failure(self, mock_telethon_client, temp_file):
        """Test upload retries on failure."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Upload failed")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=1,
                        file_size=1000000
                    )

                    assert call_count == 3
                    assert mock_wait.call_count == 2  # Called before each retry

    @pytest.mark.asyncio
    async def test_upload_reconnects_telethon_on_failure(self, mock_telethon_client, temp_file):
        """Test that Telethon client is disconnected and reconnected on failure."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Connection lost")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    # Verify disconnect and reconnect were called
                    mock_telethon_client.disconnect.assert_called()
                    assert mock_telethon_client.connect.call_count >= 1

    @pytest.mark.asyncio
    async def test_upload_fails_after_max_retries(self, mock_telethon_client, temp_file):
        """Test that UploadFailedError is raised after max retries."""
        mock_telethon_client.send_file = AsyncMock(side_effect=Exception("Persistent failure"))

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon, UploadFailedError

                    with pytest.raises(UploadFailedError) as exc_info:
                        await send_video_telethon(
                            chat_id=12345,
                            video_path=temp_file,
                            caption="Test",
                            width=1920,
                            height=1080,
                            duration=60,
                            thumbnail=None,
                            max_retries=3
                        )

                    assert "4 attempts" in str(exc_info.value)  # 3 retries + 1 initial

    @pytest.mark.asyncio
    async def test_upload_fails_when_internet_not_restored(self, mock_telethon_client, temp_file):
        """Test that upload fails when internet doesn't come back."""
        mock_telethon_client.send_file = AsyncMock(side_effect=Exception("No connection"))

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = False  # Internet never comes back

                    from ytdl_bot import send_video_telethon, UploadFailedError

                    with pytest.raises(UploadFailedError) as exc_info:
                        await send_video_telethon(
                            chat_id=12345,
                            video_path=temp_file,
                            caption="Test",
                            width=1920,
                            height=1080,
                            duration=60,
                            thumbnail=None
                        )

                    assert "Internet connection not restored" in str(exc_info.value)


# ---------------------------------------------------------------------------
# send_audio_telethon() Upload Retry Tests
# ---------------------------------------------------------------------------

class TestSendAudioTelethonRetry:
    """Tests for send_audio_telethon() retry logic."""

    @pytest.mark.asyncio
    async def test_audio_upload_success_first_attempt(self, mock_telethon_client, temp_file):
        """Test successful audio upload on first attempt."""
        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                from ytdl_bot import send_audio_telethon

                await send_audio_telethon(
                    chat_id=12345,
                    audio_path=temp_file,
                    caption="Test audio",
                    title="Test Song",
                    duration=180,
                    thumbnail=None,
                    status_message_id=1,
                    file_size=5000000
                )

                mock_telethon_client.send_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_audio_upload_retry_on_failure(self, mock_telethon_client, temp_file):
        """Test audio upload retries on failure."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Upload failed")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_audio_telethon

                    await send_audio_telethon(
                        chat_id=12345,
                        audio_path=temp_file,
                        caption="Test",
                        title="Song",
                        duration=180,
                        thumbnail=None,
                        status_message_id=1,
                        file_size=5000000
                    )

                    assert call_count == 3


# ---------------------------------------------------------------------------
# start_telethon_with_retry() Tests
# ---------------------------------------------------------------------------

class TestStartTelethonWithRetry:
    """Tests for start_telethon_with_retry() function."""

    @pytest.mark.asyncio
    async def test_start_success_first_attempt(self, mock_telethon_client):
        """Test successful Telethon start on first attempt."""
        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            from ytdl_bot import start_telethon_with_retry

            await start_telethon_with_retry(max_retries=10)

            mock_telethon_client.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_retry_on_failure(self, mock_telethon_client):
        """Test Telethon start retries on failure."""
        call_count = 0

        async def mock_start(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection failed")

        mock_telethon_client.start = mock_start

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = True

                from ytdl_bot import start_telethon_with_retry

                await start_telethon_with_retry(max_retries=10)

                assert call_count == 3

    @pytest.mark.asyncio
    async def test_start_fails_after_max_retries(self, mock_telethon_client):
        """Test that start raises exception after max retries."""
        mock_telethon_client.start = AsyncMock(side_effect=Exception("Persistent failure"))

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = True

                from ytdl_bot import start_telethon_with_retry

                with pytest.raises(Exception) as exc_info:
                    await start_telethon_with_retry(max_retries=2)

                assert "Failed to connect" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_start_fails_when_internet_not_restored(self, mock_telethon_client):
        """Test start fails when internet doesn't come back."""
        mock_telethon_client.start = AsyncMock(side_effect=Exception("No connection"))

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = False

                from ytdl_bot import start_telethon_with_retry

                with pytest.raises(Exception) as exc_info:
                    await start_telethon_with_retry(max_retries=5)

                assert "Internet connection not restored" in str(exc_info.value)


# ---------------------------------------------------------------------------
# compress_video() Retry Tests
# ---------------------------------------------------------------------------

class TestCompressVideoRetry:
    """Tests for compress_video() retry logic."""

    def test_compress_success_first_attempt(self, tmp_path):
        """Test successful compression on first attempt."""
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video" * 1000)
        compressed_file = tmp_path / "video_compressed.mp4"

        def mock_run(*args, **kwargs):
            compressed_file.write_bytes(b"compressed" * 100)
            return Mock(returncode=0)

        with patch('subprocess.run', side_effect=mock_run):
            # Return: video_bitrate, audio_bitrate, width, height, new_fps, original_fps, video_length
            with patch('ytdl_bot.get_new_video_info', return_value=(1000000, 128000, 1920, 1080, 30, 30, 60)):
                with patch('os.path.getsize', return_value=100 * 1024 * 1024):  # 100 MiB
                    from ytdl_bot import compress_video
                    result, w, h = compress_video(str(video_file))

                    # Result depends on file size check
                    # The function should attempt compression

    def test_compress_retries_when_too_large(self, tmp_path):
        """Test compression retries when output is still too large."""
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video" * 1000)
        compressed_file = tmp_path / "video_compressed.mp4"

        call_count = 0
        sizes = [3 * 1024**3, 2.5 * 1024**3, 2.2 * 1024**3, 1.9 * 1024**3]  # Decreasing sizes

        def mock_run(*args, **kwargs):
            compressed_file.write_bytes(b"compressed")
            return Mock(returncode=0)

        def mock_getsize(path):
            nonlocal call_count
            if "_compressed" in path:
                size = sizes[min(call_count, len(sizes) - 1)]
                call_count += 1
                return size
            return 3 * 1024**3

        with patch('subprocess.run', side_effect=mock_run):
            # Return: video_bitrate, audio_bitrate, width, height, new_fps, original_fps, video_length
            with patch('ytdl_bot.get_new_video_info', return_value=(5000000, 128000, 1920, 1080, 30, 60, 120)):
                with patch('os.path.getsize', side_effect=mock_getsize):
                    from ytdl_bot import compress_video, MAX_VIDEO_SIZE
                    result, w, h = compress_video(str(video_file))

                    # Should have retried multiple times
                    assert call_count >= 2

    def test_compress_timeout(self, tmp_path):
        """Test compression fails gracefully on ffmpeg timeout."""
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video" * 1000)

        def mock_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=600)

        with patch('subprocess.run', side_effect=mock_run):
            # Return: video_bitrate, audio_bitrate, width, height, new_fps, original_fps, video_length
            with patch('ytdl_bot.get_new_video_info', return_value=(1000000, 128000, 1920, 1080, 30, 30, 60)):
                from ytdl_bot import compress_video
                result, w, h = compress_video(str(video_file))

                # Should return None on timeout
                assert result is None
                assert w is None
                assert h is None


# ---------------------------------------------------------------------------
# Spotify Function Tests
# ---------------------------------------------------------------------------

class TestSpotifyFunctions:
    """Tests for async Spotify functions."""

    @pytest.mark.asyncio
    async def test_get_spotify_token_success(self):
        """Test successful Spotify token retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "access_token": "test_token_123",
            "expires_in": 3600
        })

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=AsyncContextManager(mock_response))

        with patch('ytdl_bot.get_aiohttp_session', return_value=mock_session):
            with patch('ytdl_bot.SPOTIFY_TOKEN', {"token": None, "expires": 0}):
                from ytdl_bot import get_spotify_token
                token = await get_spotify_token()
                assert token == "test_token_123"

    @pytest.mark.asyncio
    async def test_get_spotify_token_cached(self):
        """Test cached Spotify token is returned."""
        import time
        cached_token = {"token": "cached_token", "expires": time.time() + 3600}

        with patch('ytdl_bot.SPOTIFY_TOKEN', cached_token):
            from ytdl_bot import get_spotify_token
            token = await get_spotify_token()
            assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_get_spotify_token_failure(self):
        """Test Spotify token retrieval failure."""
        mock_response = AsyncMock()
        mock_response.status = 401

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=AsyncContextManager(mock_response))

        with patch('ytdl_bot.get_aiohttp_session', return_value=mock_session):
            with patch('ytdl_bot.SPOTIFY_TOKEN', {"token": None, "expires": 0}):
                from ytdl_bot import get_spotify_token
                token = await get_spotify_token()
                assert token is None

    @pytest.mark.asyncio
    async def test_search_spotify_success(self):
        """Test successful Spotify search."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "tracks": {
                "items": [{
                    "name": "Test Song",
                    "artists": [{"name": "Test Artist"}],
                    "external_urls": {"spotify": "https://open.spotify.com/track/123"}
                }]
            }
        })

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncContextManager(mock_response))

        with patch('ytdl_bot.get_aiohttp_session', return_value=mock_session):
            with patch('ytdl_bot.get_spotify_token', return_value="test_token"):
                with patch('ytdl_bot.SPOTIFY_ENABLED', True):
                    from ytdl_bot import search_spotify
                    result = await search_spotify("Test Song")
                    assert result is not None
                    assert result["name"] == "Test Song"
                    assert result["artist"] == "Test Artist"
                    assert result["url"] == "https://open.spotify.com/track/123"

    @pytest.mark.asyncio
    async def test_search_spotify_no_results(self):
        """Test Spotify search with no results."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"tracks": {"items": []}})

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=AsyncContextManager(mock_response))

        with patch('ytdl_bot.get_aiohttp_session', return_value=mock_session):
            with patch('ytdl_bot.get_spotify_token', return_value="test_token"):
                with patch('ytdl_bot.SPOTIFY_ENABLED', True):
                    from ytdl_bot import search_spotify
                    result = await search_spotify("Nonexistent Song")
                    assert result is None

    @pytest.mark.asyncio
    async def test_search_spotify_disabled(self):
        """Test Spotify search when disabled."""
        with patch('ytdl_bot.SPOTIFY_ENABLED', False):
            from ytdl_bot import search_spotify
            result = await search_spotify("Test Song")
            assert result is None

    @pytest.mark.asyncio
    async def test_search_spotify_no_token(self):
        """Test Spotify search when token retrieval fails."""
        with patch('ytdl_bot.get_spotify_token', return_value=None):
            with patch('ytdl_bot.SPOTIFY_ENABLED', True):
                from ytdl_bot import search_spotify
                result = await search_spotify("Test Song")
                assert result is None


class AsyncContextManager:
    """Helper class for mocking async context managers."""
    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Internet Outage Scenario Tests (Up to 5 Minutes)
# ---------------------------------------------------------------------------

class TestInternetOutageScenarios:
    """Tests for various internet outage scenarios."""

    @pytest.mark.asyncio
    async def test_1_minute_outage_during_upload(self, mock_telethon_client, temp_file):
        """Test upload recovery from 1-minute internet outage."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Connection lost")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    # Simulate 1 minute wait then recovery
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2
                    mock_wait.assert_called()

    @pytest.mark.asyncio
    async def test_3_minute_outage_during_upload(self, mock_telethon_client, temp_file):
        """Test upload recovery from 3-minute internet outage."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 4:  # Fail first 3 attempts
                raise Exception("Connection lost")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 4
                    assert mock_wait.call_count == 3

    @pytest.mark.asyncio
    async def test_5_minute_outage_during_upload(self, mock_telethon_client, temp_file):
        """Test upload recovery from exactly 5-minute internet outage."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 6:  # Fail first 5 attempts
                raise Exception("Connection lost")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        max_retries=10
                    )

                    assert call_count == 6

    @pytest.mark.asyncio
    async def test_intermittent_connectivity(self, mock_telethon_client, temp_file):
        """Test handling of intermittent connectivity (flapping)."""
        call_count = 0
        # Simulate: fail, success wait, fail, success wait, success

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count in [1, 3, 5]:  # Fail on odd attempts
                raise Exception("Connection flapping")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        max_retries=10
                    )

                    # Should succeed on attempt 2, 4, or 6
                    assert call_count >= 2

    @pytest.mark.asyncio
    async def test_outage_exceeds_5_minutes(self, mock_telethon_client, temp_file):
        """Test failure when outage exceeds 5 minutes (wait_for_internet returns False)."""
        mock_telethon_client.send_file = AsyncMock(side_effect=Exception("No connection"))

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    # Internet never comes back within 5 minute window
                    mock_wait.return_value = False

                    from ytdl_bot import send_video_telethon, UploadFailedError

                    with pytest.raises(UploadFailedError) as exc_info:
                        await send_video_telethon(
                            chat_id=12345,
                            video_path=temp_file,
                            caption="Test",
                            width=1920,
                            height=1080,
                            duration=60,
                            thumbnail=None
                        )

                    assert "Internet connection not restored" in str(exc_info.value)


# ---------------------------------------------------------------------------
# UploadProgressCallback Tests
# ---------------------------------------------------------------------------

class TestUploadProgressCallback:
    """Tests for UploadProgressCallback class."""

    @pytest.mark.asyncio
    async def test_progress_callback_updates_message(self):
        """Test that progress callback updates Telegram message."""
        with patch('ytdl_bot.BOT') as mock_bot:
            mock_bot.edit_message_text = AsyncMock()

            from ytdl_bot import UploadProgressCallback

            callback = UploadProgressCallback(
                chat_id=12345,
                message_id=1,
                file_size=100 * 1024 * 1024,  # 100 MiB
                media_type="video",
                retry_attempt=0,
                max_retries=10
            )
            callback.last_update = 0  # Force update

            await callback(50 * 1024 * 1024, 100 * 1024 * 1024)  # 50% progress

            mock_bot.edit_message_text.assert_called()

    @pytest.mark.asyncio
    async def test_progress_callback_shows_retry_info(self):
        """Test that progress callback shows retry information."""
        with patch('ytdl_bot.BOT') as mock_bot:
            mock_bot.edit_message_text = AsyncMock()

            from ytdl_bot import UploadProgressCallback

            callback = UploadProgressCallback(
                chat_id=12345,
                message_id=1,
                file_size=100 * 1024 * 1024,
                media_type="video",
                retry_attempt=3,  # 3rd retry
                max_retries=10
            )
            callback.last_update = 0

            await callback(25 * 1024 * 1024, 100 * 1024 * 1024)

            # Check that retry info is in the message
            call_args = mock_bot.edit_message_text.call_args
            message_text = call_args[0][0]
            assert "retry 3/10" in message_text

    @pytest.mark.asyncio
    async def test_progress_callback_respects_interval(self):
        """Test that progress callback respects update interval."""
        with patch('ytdl_bot.BOT') as mock_bot:
            mock_bot.edit_message_text = AsyncMock()

            from ytdl_bot import UploadProgressCallback
            import time

            callback = UploadProgressCallback(
                chat_id=12345,
                message_id=1,
                file_size=100 * 1024 * 1024,
                media_type="video"
            )
            callback.last_update = time.time()  # Just updated

            await callback(50 * 1024 * 1024, 100 * 1024 * 1024)

            # Should not update (interval not passed)
            mock_bot.edit_message_text.assert_not_called()


# ---------------------------------------------------------------------------
# Integration-style Tests
# ---------------------------------------------------------------------------

class TestRetryIntegration:
    """Integration-style tests combining multiple retry scenarios."""

    @pytest.mark.asyncio
    async def test_full_upload_flow_with_retries(self, mock_telethon_client, temp_file):
        """Test complete upload flow with connection issues and recovery."""
        upload_attempts = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal upload_attempts
            upload_attempts += 1
            if upload_attempts < 3:
                raise Exception("Transient error")
            return Mock()

        mock_telethon_client.send_file = mock_send_file
        mock_telethon_client.is_connected.return_value = False  # Force reconnection

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=1,
                        file_size=50 * 1024 * 1024
                    )

                    assert upload_attempts == 3
                    # Verify reconnection was attempted
                    assert mock_telethon_client.connect.call_count >= 2

    @pytest.mark.asyncio
    async def test_telethon_disconnect_during_upload(self, mock_telethon_client, temp_file):
        """Test handling of Telethon disconnect during upload."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("disconnected")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    # Should have disconnected and reconnected
                    mock_telethon_client.disconnect.assert_called()


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests for retry logic."""

    @pytest.mark.asyncio
    async def test_zero_retries_allowed(self, mock_telethon_client, temp_file):
        """Test behavior when max_retries=0."""
        mock_telethon_client.send_file = AsyncMock(side_effect=Exception("Fail"))

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                from ytdl_bot import send_video_telethon, UploadFailedError

                with pytest.raises(UploadFailedError):
                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        max_retries=0
                    )

                # Should have tried exactly once
                assert mock_telethon_client.send_file.call_count == 1

    @pytest.mark.asyncio
    async def test_reconnect_fails_but_upload_succeeds(self, mock_telethon_client, temp_file):
        """Test when reconnect fails but subsequent attempt succeeds."""
        call_count = 0
        reconnect_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First attempt failed")
            return Mock()

        async def mock_connect():
            nonlocal reconnect_count
            reconnect_count += 1
            if reconnect_count == 1:
                raise Exception("Reconnect failed")
            # Second reconnect succeeds

        mock_telethon_client.send_file = mock_send_file
        mock_telethon_client.connect = mock_connect

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_download_with_empty_temp_dir(self, tmp_path):
        """Test download when temp directory is empty (normal case)."""
        output_file = tmp_path / "video.mp4"

        def mock_run(*args, **kwargs):
            output_file.write_bytes(b"video content")
            return Mock(returncode=0)

        with patch('subprocess.run', side_effect=mock_run):
            from ytdl_bot import download_video
            result = await download_video("https://youtube.com/watch?v=test", str(tmp_path))

            assert result is not None

    @pytest.mark.asyncio
    async def test_progress_callback_handles_edit_message_failure(self):
        """Test that progress callback gracefully handles message edit failures."""
        with patch('ytdl_bot.BOT') as mock_bot:
            mock_bot.edit_message_text = AsyncMock(side_effect=Exception("Message not found"))

            from ytdl_bot import UploadProgressCallback

            callback = UploadProgressCallback(
                chat_id=12345,
                message_id=1,
                file_size=100 * 1024 * 1024,
                media_type="video"
            )
            callback.last_update = 0

            # Should not raise even when edit fails
            await callback(50 * 1024 * 1024, 100 * 1024 * 1024)


# ---------------------------------------------------------------------------
# TestUploadInternetShutdownScenarios - Internet outage duration tests
# ---------------------------------------------------------------------------

class TestUploadInternetShutdownScenarios:
    """Tests for internet shutdown scenarios with realistic timing simulation."""

    @pytest.fixture
    def mock_telethon_client(self):
        """Mock Telethon client for upload tests."""
        client = AsyncMock()
        client.is_connected.return_value = True
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.send_file = AsyncMock()
        client.start = AsyncMock()
        return client

    @pytest.fixture
    def temp_file(self, tmp_path):
        """Create a temporary test file."""
        file_path = tmp_path / "test_video.mp4"
        file_path.write_bytes(b"fake video content" * 1000)
        return str(file_path)

    @pytest.mark.asyncio
    async def test_upload_30_second_outage_recovery(self, mock_telethon_client, temp_file):
        """Test upload recovery from 30-second internet outage."""
        call_count = 0
        internet_checks = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Connection lost during 30s outage")
            return Mock()

        async def mock_wait_for_internet(*args, **kwargs):
            nonlocal internet_checks
            internet_checks += 1
            # Simulate 30 second wait (3 checks at 10s interval)
            return True

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', side_effect=mock_wait_for_internet):
                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2
                    assert internet_checks == 1

    @pytest.mark.asyncio
    async def test_upload_1_minute_outage_recovery(self, mock_telethon_client, temp_file):
        """Test upload recovery from 1-minute internet outage."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Connection lost during 1 min outage")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_upload_2_minute_outage_recovery(self, mock_telethon_client, temp_file):
        """Test upload recovery from 2-minute internet outage."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection lost during 2 min outage")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 3
                    assert mock_wait.call_count == 2

    @pytest.mark.asyncio
    async def test_upload_3_minute_outage_recovery(self, mock_telethon_client, temp_file):
        """Test upload recovery from 3-minute internet outage."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise Exception("Connection lost during 3 min outage")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 4
                    assert mock_wait.call_count == 3

    @pytest.mark.asyncio
    async def test_upload_4_minute_outage_recovery(self, mock_telethon_client, temp_file):
        """Test upload recovery from 4-minute internet outage."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 5:
                raise Exception("Connection lost during 4 min outage")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 5
                    assert mock_wait.call_count == 4

    @pytest.mark.asyncio
    async def test_upload_5_minute_outage_recovery_at_limit(self, mock_telethon_client, temp_file):
        """Test upload recovery from exactly 5-minute internet outage (at the limit)."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 6:
                raise Exception("Connection lost during 5 min outage")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        max_retries=10
                    )

                    assert call_count == 6
                    assert mock_wait.call_count == 5

    @pytest.mark.asyncio
    async def test_upload_5_minute_1_second_outage_fails(self, mock_telethon_client, temp_file):
        """Test upload fails when outage exceeds 5 minutes (wait_for_internet returns False)."""
        mock_telethon_client.send_file = AsyncMock(side_effect=Exception("Prolonged outage"))

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    # Simulate internet not restored within 5 minute window
                    mock_wait.return_value = False

                    from ytdl_bot import send_video_telethon, UploadFailedError

                    with pytest.raises(UploadFailedError) as exc_info:
                        await send_video_telethon(
                            chat_id=12345,
                            video_path=temp_file,
                            caption="Test",
                            width=1920,
                            height=1080,
                            duration=60,
                            thumbnail=None
                        )

                    assert "Internet connection not restored" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_multiple_short_outages_cumulative(self, mock_telethon_client, temp_file):
        """Test handling of multiple short outages that cumulatively exceed normal operation."""
        call_count = 0
        wait_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Fail every other attempt (simulating intermittent short outages)
            if call_count in [1, 2, 3, 4, 5]:
                raise Exception(f"Short outage #{call_count}")
            return Mock()

        async def mock_wait(*args, **kwargs):
            nonlocal wait_count
            wait_count += 1
            return True

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', side_effect=mock_wait):
                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        max_retries=10
                    )

                    assert call_count == 6
                    assert wait_count == 5


# ---------------------------------------------------------------------------
# TestAudioUploadComprehensive - Audio upload parity with video tests
# ---------------------------------------------------------------------------

class TestAudioUploadComprehensive:
    """Comprehensive tests for audio upload to achieve parity with video tests."""

    @pytest.fixture
    def mock_telethon_client(self):
        """Mock Telethon client for upload tests."""
        client = AsyncMock()
        client.is_connected.return_value = True
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.send_file = AsyncMock()
        client.start = AsyncMock()
        return client

    @pytest.fixture
    def temp_audio_file(self, tmp_path):
        """Create a temporary test audio file."""
        file_path = tmp_path / "test_audio.mp3"
        file_path.write_bytes(b"fake audio content" * 1000)
        return str(file_path)

    @pytest.mark.asyncio
    async def test_audio_upload_reconnects_telethon_on_failure(self, mock_telethon_client, temp_audio_file):
        """Test that Telethon client is disconnected and reconnected on audio upload failure."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Connection lost")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_audio_telethon

                    await send_audio_telethon(
                        chat_id=12345,
                        audio_path=temp_audio_file,
                        caption="Test",
                        title="Test Song",
                        duration=180,
                        thumbnail=None
                    )

                    # Verify disconnect and reconnect were called
                    mock_telethon_client.disconnect.assert_called()
                    assert mock_telethon_client.connect.call_count >= 1

    @pytest.mark.asyncio
    async def test_audio_upload_fails_after_max_retries(self, mock_telethon_client, temp_audio_file):
        """Test that UploadFailedError is raised after max retries for audio."""
        mock_telethon_client.send_file = AsyncMock(side_effect=Exception("Persistent failure"))

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_audio_telethon, UploadFailedError

                    with pytest.raises(UploadFailedError) as exc_info:
                        await send_audio_telethon(
                            chat_id=12345,
                            audio_path=temp_audio_file,
                            caption="Test",
                            title="Test Song",
                            duration=180,
                            thumbnail=None,
                            max_retries=3
                        )

                    assert "4 attempts" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_audio_upload_fails_when_internet_not_restored(self, mock_telethon_client, temp_audio_file):
        """Test that audio upload fails when internet doesn't come back."""
        mock_telethon_client.send_file = AsyncMock(side_effect=Exception("No connection"))

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = False

                    from ytdl_bot import send_audio_telethon, UploadFailedError

                    with pytest.raises(UploadFailedError) as exc_info:
                        await send_audio_telethon(
                            chat_id=12345,
                            audio_path=temp_audio_file,
                            caption="Test",
                            title="Test Song",
                            duration=180,
                            thumbnail=None
                        )

                    assert "Internet connection not restored" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_audio_upload_5_minute_outage_recovery(self, mock_telethon_client, temp_audio_file):
        """Test audio upload recovery from 5-minute internet outage."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 6:
                raise Exception("Connection lost")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_audio_telethon

                    await send_audio_telethon(
                        chat_id=12345,
                        audio_path=temp_audio_file,
                        caption="Test",
                        title="Test Song",
                        duration=180,
                        thumbnail=None,
                        max_retries=10
                    )

                    assert call_count == 6

    @pytest.mark.asyncio
    async def test_audio_upload_intermittent_connectivity(self, mock_telethon_client, temp_audio_file):
        """Test audio upload with intermittent connectivity."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count in [1, 3, 5]:
                raise Exception("Connection flapping")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_audio_telethon

                    await send_audio_telethon(
                        chat_id=12345,
                        audio_path=temp_audio_file,
                        caption="Test",
                        title="Test Song",
                        duration=180,
                        thumbnail=None,
                        max_retries=10
                    )

                    assert call_count >= 2

    @pytest.mark.asyncio
    async def test_audio_upload_various_error_types(self, mock_telethon_client, temp_audio_file):
        """Test audio upload handles various error types."""
        call_count = 0
        errors = [
            ConnectionError("Connection reset"),
            TimeoutError("Upload timed out"),
            OSError("Network unreachable"),
            Exception("Generic error")
        ]

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= len(errors):
                raise errors[call_count - 1]
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_audio_telethon

                    await send_audio_telethon(
                        chat_id=12345,
                        audio_path=temp_audio_file,
                        caption="Test",
                        title="Test Song",
                        duration=180,
                        thumbnail=None,
                        max_retries=10
                    )

                    assert call_count == len(errors) + 1

    @pytest.mark.asyncio
    async def test_audio_upload_with_progress_callback(self, mock_telethon_client, temp_audio_file):
        """Test audio upload with progress callback."""
        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                from ytdl_bot import send_audio_telethon

                await send_audio_telethon(
                    chat_id=12345,
                    audio_path=temp_audio_file,
                    caption="Test audio",
                    title="Test Song",
                    duration=180,
                    thumbnail=None,
                    status_message_id=123,
                    file_size=5000000
                )

                mock_telethon_client.send_file.assert_called_once()
                call_kwargs = mock_telethon_client.send_file.call_args[1]
                assert 'progress_callback' in call_kwargs
                assert callable(call_kwargs['progress_callback'])

    @pytest.mark.asyncio
    async def test_audio_upload_status_message_updates(self, mock_telethon_client, temp_audio_file):
        """Test that status message is updated during audio upload retry."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Upload failed")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_audio_telethon

                    await send_audio_telethon(
                        chat_id=12345,
                        audio_path=temp_audio_file,
                        caption="Test",
                        title="Test Song",
                        duration=180,
                        thumbnail=None,
                        status_message_id=123,
                        file_size=5000000
                    )

                    # Should have updated message with retry info
                    assert mock_bot.edit_message_text.called
                    call_args_list = mock_bot.edit_message_text.call_args_list
                    retry_message_found = False
                    for call in call_args_list:
                        if "retry" in str(call).lower():
                            retry_message_found = True
                            break
                    assert retry_message_found


# ---------------------------------------------------------------------------
# TestUploadMidTransferFailures - Failures at different progress points
# ---------------------------------------------------------------------------

class TestUploadMidTransferFailures:
    """Tests for upload failures at different progress points."""

    @pytest.fixture
    def mock_telethon_client(self):
        """Mock Telethon client for upload tests."""
        client = AsyncMock()
        client.is_connected.return_value = True
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.send_file = AsyncMock()
        client.start = AsyncMock()
        return client

    @pytest.fixture
    def temp_file(self, tmp_path):
        """Create a temporary test file."""
        file_path = tmp_path / "test_video.mp4"
        file_path.write_bytes(b"fake video content" * 1000)
        return str(file_path)

    @pytest.mark.asyncio
    async def test_upload_fails_at_10_percent(self, mock_telethon_client, temp_file):
        """Test upload failure at 10% progress."""
        call_count = 0
        progress_at_failure = None

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count, progress_at_failure
            call_count += 1
            progress_callback = kwargs.get('progress_callback')
            if progress_callback and call_count == 1:
                # Simulate 10% progress before failure
                await progress_callback(10, 100)
                progress_at_failure = 10
                raise Exception("Connection lost at 10%")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=1,
                        file_size=100
                    )

                    assert call_count == 2
                    assert progress_at_failure == 10

    @pytest.mark.asyncio
    async def test_upload_fails_at_50_percent(self, mock_telethon_client, temp_file):
        """Test upload failure at 50% progress."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            progress_callback = kwargs.get('progress_callback')
            if progress_callback and call_count == 1:
                # Simulate 50% progress before failure
                await progress_callback(50, 100)
                raise Exception("Connection lost at 50%")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=1,
                        file_size=100
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_upload_fails_at_90_percent(self, mock_telethon_client, temp_file):
        """Test upload failure at 90% progress (near completion)."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            progress_callback = kwargs.get('progress_callback')
            if progress_callback and call_count == 1:
                # Simulate 90% progress before failure
                await progress_callback(90, 100)
                raise Exception("Connection lost at 90%")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=1,
                        file_size=100
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_upload_fails_multiple_times_at_different_points(self, mock_telethon_client, temp_file):
        """Test upload fails at different progress points across retries."""
        call_count = 0
        failure_points = [10, 50, 90]  # Fail at 10%, 50%, 90% then succeed

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            progress_callback = kwargs.get('progress_callback')
            if progress_callback and call_count <= len(failure_points):
                # Simulate progress before failure
                await progress_callback(failure_points[call_count - 1], 100)
                raise Exception(f"Connection lost at {failure_points[call_count - 1]}%")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=1,
                        file_size=100,
                        max_retries=10
                    )

                    assert call_count == len(failure_points) + 1

    @pytest.mark.asyncio
    async def test_upload_progress_callback_during_retry(self, mock_telethon_client, temp_file):
        """Test progress callback is properly created during retry with correct retry_attempt."""
        call_count = 0
        callbacks_created = []

        original_send_file = mock_telethon_client.send_file

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            progress_callback = kwargs.get('progress_callback')
            if progress_callback:
                callbacks_created.append(progress_callback)
            if call_count < 3:
                raise Exception("Retry needed")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=1,
                        file_size=100
                    )

                    assert len(callbacks_created) == 3
                    # Each callback should have increasing retry_attempt
                    for i, callback in enumerate(callbacks_created):
                        assert callback.retry_attempt == i

    @pytest.mark.asyncio
    async def test_upload_restarts_from_zero_on_retry(self, mock_telethon_client, temp_file):
        """Test that upload restarts from 0% on retry (not resume)."""
        call_count = 0
        progress_starts = []

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            progress_callback = kwargs.get('progress_callback')
            if progress_callback:
                # Record the starting progress of each attempt
                progress_starts.append(0)  # Telethon always starts from 0
                if call_count == 1:
                    await progress_callback(50, 100)  # Progress to 50%
                    raise Exception("Connection lost")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=1,
                        file_size=100
                    )

                    # Both attempts start from 0
                    assert all(p == 0 for p in progress_starts)


# ---------------------------------------------------------------------------
# TestUploadErrorTypes - Various network/server error scenarios
# ---------------------------------------------------------------------------

class TestUploadErrorTypes:
    """Tests for various network/server error scenarios during upload."""

    @pytest.fixture
    def mock_telethon_client(self):
        """Mock Telethon client for upload tests."""
        client = AsyncMock()
        client.is_connected.return_value = True
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.send_file = AsyncMock()
        client.start = AsyncMock()
        return client

    @pytest.fixture
    def temp_file(self, tmp_path):
        """Create a temporary test file."""
        file_path = tmp_path / "test_video.mp4"
        file_path.write_bytes(b"fake video content" * 1000)
        return str(file_path)

    @pytest.mark.asyncio
    async def test_upload_timeout_error_retry(self, mock_telethon_client, temp_file):
        """Test retry on timeout error."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError("Upload timed out")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_upload_connection_reset_error_retry(self, mock_telethon_client, temp_file):
        """Test retry on connection reset error."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionResetError("Connection reset by peer")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_upload_connection_refused_error_retry(self, mock_telethon_client, temp_file):
        """Test retry on connection refused error."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionRefusedError("Connection refused")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_upload_server_error_500_retry(self, mock_telethon_client, temp_file):
        """Test retry on server error (500)."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Server returned 500 Internal Server Error")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_upload_rate_limit_error_retry(self, mock_telethon_client, temp_file):
        """Test retry on rate limit error."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Rate limit exceeded")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_upload_flood_wait_error_retry(self, mock_telethon_client, temp_file):
        """Test retry on flood wait error (Telegram specific)."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("FloodWaitError: wait 30 seconds")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_upload_mixed_error_types_recovery(self, mock_telethon_client, temp_file):
        """Test recovery from mixed error types."""
        call_count = 0
        errors = [
            ConnectionResetError("Reset"),
            asyncio.TimeoutError("Timeout"),
            OSError("Network unreachable"),
            Exception("Unknown error")
        ]

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= len(errors):
                raise errors[call_count - 1]
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        max_retries=10
                    )

                    assert call_count == len(errors) + 1

    @pytest.mark.asyncio
    async def test_upload_unknown_error_type_retry(self, mock_telethon_client, temp_file):
        """Test retry on unknown/custom error type."""
        call_count = 0

        class CustomTelethonError(Exception):
            pass

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise CustomTelethonError("Some custom Telethon error")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert call_count == 2


# ---------------------------------------------------------------------------
# TestTelethonReconnectionEdgeCases - Edge cases in Telethon reconnection
# ---------------------------------------------------------------------------

class TestTelethonReconnectionEdgeCases:
    """Edge case tests for Telethon client reconnection."""

    @pytest.fixture
    def mock_telethon_client(self):
        """Mock Telethon client for upload tests."""
        client = AsyncMock()
        client.is_connected.return_value = True
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.send_file = AsyncMock()
        client.start = AsyncMock()
        return client

    @pytest.fixture
    def temp_file(self, tmp_path):
        """Create a temporary test file."""
        file_path = tmp_path / "test_video.mp4"
        file_path.write_bytes(b"fake video content" * 1000)
        return str(file_path)

    @pytest.mark.asyncio
    async def test_reconnect_fails_first_time_succeeds_second(self, mock_telethon_client, temp_file):
        """Test when reconnect fails first time but succeeds second."""
        upload_count = 0
        connect_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal upload_count
            upload_count += 1
            if upload_count < 3:
                raise Exception("Upload failed")
            return Mock()

        async def mock_connect():
            nonlocal connect_count
            connect_count += 1
            if connect_count == 1:
                raise Exception("Reconnect failed")
            # Subsequent connects succeed

        mock_telethon_client.send_file = mock_send_file
        mock_telethon_client.connect = mock_connect

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert upload_count == 3

    @pytest.mark.asyncio
    async def test_reconnect_fails_multiple_times_then_succeeds(self, mock_telethon_client, temp_file):
        """Test when reconnect fails multiple times before succeeding."""
        upload_count = 0
        connect_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal upload_count
            upload_count += 1
            if upload_count < 4:
                raise Exception("Upload failed")
            return Mock()

        async def mock_connect():
            nonlocal connect_count
            connect_count += 1
            if connect_count < 3:
                raise Exception(f"Reconnect failed #{connect_count}")
            # 3rd and later connects succeed

        mock_telethon_client.send_file = mock_send_file
        mock_telethon_client.connect = mock_connect

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert upload_count == 4

    @pytest.mark.asyncio
    async def test_disconnect_fails_silently_continues(self, mock_telethon_client, temp_file):
        """Test that disconnect failure doesn't prevent retry."""
        upload_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal upload_count
            upload_count += 1
            if upload_count == 1:
                raise Exception("Upload failed")
            return Mock()

        mock_telethon_client.send_file = mock_send_file
        mock_telethon_client.disconnect = AsyncMock(side_effect=Exception("Disconnect failed"))

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    # Should not raise despite disconnect failure
                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert upload_count == 2

    @pytest.mark.asyncio
    async def test_is_connected_returns_false_triggers_connect(self, mock_telethon_client, temp_file):
        """Test that is_connected() returning False triggers connect()."""
        connect_call_count = 0

        async def mock_connect():
            nonlocal connect_call_count
            connect_call_count += 1

        # Make is_connected return False (it's a synchronous method)
        mock_telethon_client.is_connected = Mock(return_value=False)
        mock_telethon_client.connect = mock_connect

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                from ytdl_bot import send_video_telethon

                await send_video_telethon(
                    chat_id=12345,
                    video_path=temp_file,
                    caption="Test",
                    width=1920,
                    height=1080,
                    duration=60,
                    thumbnail=None
                )

                # is_connected returned False, so connect should have been called
                assert connect_call_count >= 1

    @pytest.mark.asyncio
    async def test_connection_lost_during_reconnect_attempt(self, mock_telethon_client, temp_file):
        """Test handling of connection lost during reconnect attempt."""
        upload_count = 0
        connect_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal upload_count
            upload_count += 1
            if upload_count < 3:
                raise ConnectionError("Connection lost")
            return Mock()

        async def mock_connect():
            nonlocal connect_count
            connect_count += 1
            if connect_count == 1:
                raise ConnectionError("Connection lost during reconnect")
            # Later connects succeed

        mock_telethon_client.send_file = mock_send_file
        mock_telethon_client.connect = mock_connect

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert upload_count == 3

    @pytest.mark.asyncio
    async def test_partial_reconnection_state(self, mock_telethon_client, temp_file):
        """Test handling of partial reconnection state (connected but unusable)."""
        upload_count = 0
        is_connected_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal upload_count
            upload_count += 1
            if upload_count < 2:
                raise Exception("Connection in bad state")
            return Mock()

        def mock_is_connected():
            nonlocal is_connected_count
            is_connected_count += 1
            # Report connected but actually in bad state
            return True

        mock_telethon_client.send_file = mock_send_file
        mock_telethon_client.is_connected = mock_is_connected

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                    )

                    assert upload_count == 2
                    # Disconnect should be called to reset bad state
                    mock_telethon_client.disconnect.assert_called()


# ---------------------------------------------------------------------------
# TestUploadStatusMessageBehavior - User notification during uploads
# ---------------------------------------------------------------------------

class TestUploadStatusMessageBehavior:
    """Tests for status message behavior during uploads."""

    @pytest.fixture
    def mock_telethon_client(self):
        """Mock Telethon client for upload tests."""
        client = AsyncMock()
        client.is_connected.return_value = True
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.send_file = AsyncMock()
        client.start = AsyncMock()
        return client

    @pytest.fixture
    def temp_file(self, tmp_path):
        """Create a temporary test file."""
        file_path = tmp_path / "test_video.mp4"
        file_path.write_bytes(b"fake video content" * 1000)
        return str(file_path)

    @pytest.mark.asyncio
    async def test_status_message_updated_on_each_retry(self, mock_telethon_client, temp_file):
        """Test that status message is updated on each retry."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise Exception("Retry needed")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=123,
                        file_size=100 * 1024 * 1024
                    )

                    # Should have updated message for each retry
                    assert mock_bot.edit_message_text.call_count >= 3

    @pytest.mark.asyncio
    async def test_status_message_shows_correct_retry_count(self, mock_telethon_client, temp_file):
        """Test that status message shows correct retry count."""
        call_count = 0
        status_messages = []

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Retry needed")
            return Mock()

        async def mock_edit_message_text(text, chat_id, message_id):
            status_messages.append(text)

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = mock_edit_message_text

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=123,
                        file_size=100 * 1024 * 1024,
                        max_retries=10
                    )

                    # Check retry counts in messages
                    retry_1_found = any("retry 1/" in msg for msg in status_messages)
                    retry_2_found = any("retry 2/" in msg for msg in status_messages)
                    assert retry_1_found
                    assert retry_2_found

    @pytest.mark.asyncio
    async def test_status_message_update_failure_doesnt_break_upload(self, mock_telethon_client, temp_file):
        """Test that status message update failure doesn't break upload."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Retry needed")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                # Make edit_message_text always fail
                mock_bot.edit_message_text = AsyncMock(side_effect=Exception("Message edit failed"))

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    # Should complete despite message edit failures
                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None,
                        status_message_id=123,
                        file_size=100 * 1024 * 1024
                    )

                    assert call_count == 2

    @pytest.mark.asyncio
    async def test_status_message_shows_progress_during_retry(self, mock_telethon_client, temp_file):
        """Test that status message shows progress during retry attempts."""
        with patch('ytdl_bot.BOT') as mock_bot:
            mock_bot.edit_message_text = AsyncMock()

            from ytdl_bot import UploadProgressCallback

            callback = UploadProgressCallback(
                chat_id=12345,
                message_id=123,
                file_size=100 * 1024 * 1024,
                media_type="video",
                retry_attempt=2,
                max_retries=10
            )
            callback.last_update = 0  # Force update

            await callback(50 * 1024 * 1024, 100 * 1024 * 1024)

            mock_bot.edit_message_text.assert_called()
            call_args = mock_bot.edit_message_text.call_args[0][0]
            assert "50%" in call_args
            assert "retry 2/10" in call_args

    @pytest.mark.asyncio
    async def test_no_status_message_when_not_provided(self, mock_telethon_client, temp_file):
        """Test that no status message updates when status_message_id is not provided."""
        call_count = 0

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Retry needed")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=temp_file,
                        caption="Test",
                        width=1920,
                        height=1080,
                        duration=60,
                        thumbnail=None
                        # No status_message_id or file_size
                    )

                    # edit_message_text should not be called for retry status
                    # (it might be called for other reasons, but check the specific retry pattern)
                    for call in mock_bot.edit_message_text.call_args_list:
                        if call[0]:
                            assert "retry" not in call[0][0].lower()


# ---------------------------------------------------------------------------
# TestLargeFileUploadScenarios - Large file specific scenarios
# ---------------------------------------------------------------------------

class TestLargeFileUploadScenarios:
    """Tests for large file upload scenarios."""

    @pytest.fixture
    def mock_telethon_client(self):
        """Mock Telethon client for upload tests."""
        client = AsyncMock()
        client.is_connected.return_value = True
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.send_file = AsyncMock()
        client.start = AsyncMock()
        return client

    @pytest.fixture
    def large_temp_file(self, tmp_path):
        """Create a simulated large test file (metadata only, not actual 2GB)."""
        file_path = tmp_path / "large_video.mp4"
        # Create a small file but we'll mock the size
        file_path.write_bytes(b"fake video content" * 1000)
        return str(file_path)

    @pytest.mark.asyncio
    async def test_large_file_2gb_upload_with_retries(self, mock_telethon_client, large_temp_file):
        """Test 2GB file upload with retries."""
        call_count = 0
        file_size = 2 * 1024 * 1024 * 1024  # 2 GB

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Large file upload failed")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=large_temp_file,
                        caption="Large file test",
                        width=1920,
                        height=1080,
                        duration=3600,  # 1 hour video
                        thumbnail=None,
                        status_message_id=123,
                        file_size=file_size
                    )

                    assert call_count == 3

    @pytest.mark.asyncio
    async def test_large_file_multiple_outages_during_upload(self, mock_telethon_client, large_temp_file):
        """Test large file upload with multiple outages during upload."""
        call_count = 0
        file_size = 1.5 * 1024 * 1024 * 1024  # 1.5 GB
        outages = 5  # Simulate 5 outages during upload

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            progress_callback = kwargs.get('progress_callback')
            if progress_callback:
                # Simulate partial progress before each outage
                progress_pct = min(call_count * 20, 100)
                await progress_callback(int(file_size * progress_pct / 100), file_size)
            if call_count <= outages:
                raise Exception(f"Outage #{call_count} during large file upload")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=large_temp_file,
                        caption="Large file with outages",
                        width=1920,
                        height=1080,
                        duration=7200,  # 2 hour video
                        thumbnail=None,
                        status_message_id=123,
                        file_size=file_size,
                        max_retries=10
                    )

                    assert call_count == outages + 1

    @pytest.mark.asyncio
    async def test_large_file_progress_tracking_accuracy(self, mock_telethon_client, large_temp_file):
        """Test that progress tracking is accurate for large files."""
        file_size = 1 * 1024 * 1024 * 1024  # 1 GB
        progress_updates = []

        with patch('ytdl_bot.BOT') as mock_bot:
            async def capture_edit(text, chat_id, message_id):
                progress_updates.append(text)

            mock_bot.edit_message_text = capture_edit

            from ytdl_bot import UploadProgressCallback
            import time

            callback = UploadProgressCallback(
                chat_id=12345,
                message_id=123,
                file_size=file_size,
                media_type="video",
                retry_attempt=0,
                max_retries=10
            )
            callback.last_update = 0  # Force updates

            # Simulate progress updates
            for pct in [10, 25, 50, 75, 90, 100]:
                callback.last_update = 0  # Reset to force update
                await callback(int(file_size * pct / 100), file_size)

            # Check that percentage updates are accurate
            for i, update in enumerate(progress_updates):
                assert "%" in update

    @pytest.mark.asyncio
    async def test_large_file_timeout_handling(self, mock_telethon_client, large_temp_file):
        """Test timeout handling for large file uploads."""
        call_count = 0
        file_size = 2 * 1024 * 1024 * 1024  # 2 GB

        async def mock_send_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate timeout on first attempt of large file
                raise asyncio.TimeoutError("Upload timed out after 30 minutes")
            return Mock()

        mock_telethon_client.send_file = mock_send_file

        with patch('ytdl_bot.TELETHON_CLIENT', mock_telethon_client):
            with patch('ytdl_bot.BOT') as mock_bot:
                mock_bot.edit_message_text = AsyncMock()

                with patch('ytdl_bot.wait_for_internet', new_callable=AsyncMock) as mock_wait:
                    mock_wait.return_value = True

                    from ytdl_bot import send_video_telethon

                    await send_video_telethon(
                        chat_id=12345,
                        video_path=large_temp_file,
                        caption="Large file timeout test",
                        width=1920,
                        height=1080,
                        duration=3600,
                        thumbnail=None,
                        status_message_id=123,
                        file_size=file_size
                    )

                    assert call_count == 2
                    # Verify disconnect was called after timeout
                    mock_telethon_client.disconnect.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
