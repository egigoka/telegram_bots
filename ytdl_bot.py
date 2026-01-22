#! python3
# -*- coding: utf-8 -*-
"""
YouTube Download Telegram Bot
Downloads YouTube videos and uploads them to Telegram with admin-controlled access.
Uses Telethon for large file uploads (up to 2GB).
"""

import os
import sys
import subprocess
import tempfile
import re
import asyncio
import time
import json
import shutil
import traceback
import urllib.parse
import base64
import hashlib

try:
    from commands import Path, Time, Video, MiB, KiB, GiB, JsonDict
except ImportError:
    os.system("pip install git+https://github.com/egigoka/commands")
    from commands import Path, Time, Video, MiB, KiB, GiB, JsonDict

try:
    import telebot
    from telebot.async_telebot import AsyncTeleBot
except ImportError:
    from commands.pip9 import Pip
    Pip.install("pytelegrambotapi")
    import telebot
    from telebot.async_telebot import AsyncTeleBot

try:
    from telethon import TelegramClient
    from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename, DocumentAttributeAudio
except ImportError:
    from commands.pip9 import Pip
    Pip.install("telethon")
    from telethon import TelegramClient
    from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename, DocumentAttributeAudio

try:
    import aiohttp
except ImportError:
    from commands.pip9 import Pip
    Pip.install("aiohttp")
    import aiohttp

try:
    from secrets import YTDL_TELEGRAM_TOKEN, MY_CHAT_ID, APP_ID, APP_API_HASH
except ImportError:
    print("Error: YTDL_TELEGRAM_TOKEN, MY_CHAT_ID, APP_ID, APP_API_HASH must be defined in secrets.py")
    sys.exit(1)

try:
    from secrets import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
    SPOTIFY_ENABLED = True
except ImportError:
    SPOTIFY_ENABLED = False
    SPOTIFY_CLIENT_ID = None
    SPOTIFY_CLIENT_SECRET = None

YTDL_ADMIN_CHAT_ID = MY_CHAT_ID

__version__ = "2.6.0"

# Shared aiohttp session (lazy initialization)
_AIOHTTP_SESSION = None


async def get_aiohttp_session():
    """Get or create shared aiohttp session."""
    global _AIOHTTP_SESSION
    if _AIOHTTP_SESSION is None or _AIOHTTP_SESSION.closed:
        _AIOHTTP_SESSION = aiohttp.ClientSession()
    return _AIOHTTP_SESSION


async def close_aiohttp_session():
    """Close shared aiohttp session."""
    global _AIOHTTP_SESSION
    if _AIOHTTP_SESSION and not _AIOHTTP_SESSION.closed:
        await _AIOHTTP_SESSION.close()
        # Allow time for graceful connection close
        await asyncio.sleep(0.25)
        _AIOHTTP_SESSION = None


# Spotify token cache
SPOTIFY_TOKEN = {"token": None, "expires": 0}


async def get_spotify_token():
    """Get Spotify access token using client credentials flow."""
    # Return cached token if still valid
    if SPOTIFY_TOKEN["token"] and time.time() < SPOTIFY_TOKEN["expires"]:
        return SPOTIFY_TOKEN["token"]

    try:
        auth_str = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()

        session = await get_aiohttp_session()
        async with session.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {auth_b64}"},
            data={"grant_type": "client_credentials"},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                data = await response.json()
                SPOTIFY_TOKEN["token"] = data["access_token"]
                SPOTIFY_TOKEN["expires"] = time.time() + data["expires_in"] - 60
                return SPOTIFY_TOKEN["token"]
    except Exception as e:
        print(f"Error getting Spotify token: {e}")
    return None


def clean_title_for_search(title):
    """Clean YouTube title for better Spotify search results."""
    # Remove common YouTube suffixes
    patterns = [
        r'\(Official\s*(Music\s*)?Video\)',
        r'\(Official\s*Audio\)',
        r'\(Lyric\s*Video\)',
        r'\(Lyrics\)',
        r'\[Official\s*(Music\s*)?Video\]',
        r'\[Official\s*Audio\]',
        r'\[Lyric\s*Video\]',
        r'\[Lyrics\]',
        r'\(HD\)',
        r'\[HD\]',
        r'\(4K\)',
        r'\[4K\]',
        r'\(Audio\)',
        r'\[Audio\]',
        r'\(Visualizer\)',
        r'\[Visualizer\]',
        r'【.*?】',
        r'\|.*$',  # Remove everything after |
    ]

    cleaned = title
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Remove extra whitespace
    cleaned = ' '.join(cleaned.split())
    return cleaned.strip()


async def search_spotify(title):
    """Search Spotify for a track and return track info dict."""
    if not SPOTIFY_ENABLED:
        return None

    token = await get_spotify_token()
    if not token:
        return None

    try:
        cleaned_title = clean_title_for_search(title)
        query = urllib.parse.quote(cleaned_title)

        session = await get_aiohttp_session()
        async with session.get(
            f"https://api.spotify.com/v1/search?q={query}&type=track&limit=1",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                data = await response.json()
                tracks = data.get("tracks", {}).get("items", [])
                if tracks:
                    track = tracks[0]
                    artists = ", ".join(a["name"] for a in track["artists"])
                    return {
                        "url": track["external_urls"]["spotify"],
                        "artist": artists,
                        "name": track["name"]
                    }
    except Exception as e:
        print(f"Error searching Spotify: {e}")
    return None

# Constants
MAX_VIDEO_SIZE = 2 * GiB  # 2 GB limit with Telethon
MIN_AUDIO_BITRATE = 32 * KiB
MAX_AUDIO_BITRATE = 128 * KiB
BITRATE_SAFETY_MARGIN = 0.9

# Telegram bot instance (async)
BOT = AsyncTeleBot(YTDL_TELEGRAM_TOKEN)

# Telethon client for large uploads
TELETHON_CLIENT = TelegramClient(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ytdl_session'),
    APP_ID,
    APP_API_HASH
)

# Config paths
CONFIG_DIR = Path.combine(os.path.dirname(os.path.abspath(__file__)), "configs")
USERS_JSON_PATH = Path.combine(CONFIG_DIR, "ytdl_users.json")

# Temporary storage for pending URL choices (message_id -> {url, user_id, timestamp})
PENDING_CHOICES = {}
PENDING_CHOICES_TTL = 3600  # 1 hour

# Temporary storage for status messages to delete (chat_id -> [message_ids])
STATUS_MESSAGES = {}


class UserManager:
    """Manages user access control with JSON persistence."""

    def __init__(self, json_path):
        self.json_path = json_path
        # Ensure config directory exists
        config_dir = os.path.dirname(json_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        self.config = JsonDict(json_path)
        self._ensure_structure()

    def _ensure_structure(self):
        """Ensure required keys exist in the JSON."""
        defaults = {
            "approved_users": [],
            "denied_users": [],
            "pending_requests": {}
        }
        changed = False
        for key, default_val in defaults.items():
            if key not in self.config:
                self.config[key] = default_val
                changed = True
        if changed:
            self.config.save()

    def is_approved(self, user_id):
        """Check if user is in approved list."""
        return user_id in self.config["approved_users"]

    def is_denied(self, user_id):
        """Check if user is in denied list."""
        return user_id in self.config["denied_users"]

    def is_pending(self, user_id):
        """Check if user has a pending request."""
        return str(user_id) in self.config["pending_requests"]

    def add_pending_request(self, user_id, username, first_name, url, admin_message_id, audio_only=False):
        """Add a new pending request."""
        self.config["pending_requests"][str(user_id)] = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "requested_url": url,
            "request_time": Time.dotted(),
            "admin_message_id": admin_message_id,
            "audio_only": audio_only
        }
        self.config.save()

    def approve_user(self, user_id):
        """Move user from pending to approved."""
        user_id_str = str(user_id)
        pending = self.config["pending_requests"].pop(user_id_str, None)
        if user_id not in self.config["approved_users"]:
            self.config["approved_users"].append(user_id)
        # Remove from denied if present
        if user_id in self.config["denied_users"]:
            self.config["denied_users"].remove(user_id)
        self.config.save()
        return pending

    def deny_user(self, user_id):
        """Move user from pending to denied."""
        user_id_str = str(user_id)
        pending = self.config["pending_requests"].pop(user_id_str, None)
        if user_id not in self.config["denied_users"]:
            self.config["denied_users"].append(user_id)
        self.config.save()
        return pending

    def get_pending_request(self, user_id):
        """Get pending request data for a user."""
        return self.config["pending_requests"].get(str(user_id))


# Initialize user manager
USER_MANAGER = UserManager(USERS_JSON_PATH)

# Auto-approve admin on startup
if YTDL_ADMIN_CHAT_ID not in USER_MANAGER.config["approved_users"]:
    USER_MANAGER.config["approved_users"].append(YTDL_ADMIN_CHAT_ID)
    USER_MANAGER.config.save()


async def send_message(chat_id, text, reply_markup=None):
    """Send a message and return it."""
    print(f"[SEND] to {chat_id}: {text[:100]}{'...' if len(text) > 100 else ''}")
    return await BOT.send_message(chat_id, text, reply_markup=reply_markup)


def add_status_message(chat_id, message):
    """Track a status message for later deletion."""
    if chat_id not in STATUS_MESSAGES:
        STATUS_MESSAGES[chat_id] = []
    if hasattr(message, 'message_id'):
        STATUS_MESSAGES[chat_id].append(message.message_id)
    elif isinstance(message, list):
        for msg in message:
            if hasattr(msg, 'message_id'):
                STATUS_MESSAGES[chat_id].append(msg.message_id)


async def clear_status_messages(chat_id):
    """Delete all tracked status messages for a chat."""
    if chat_id not in STATUS_MESSAGES:
        return
    for message_id in STATUS_MESSAGES[chat_id]:
        try:
            await BOT.delete_message(chat_id, message_id)
        except Exception as e:
            print(f"Failed to delete message {message_id}: {e}")
    STATUS_MESSAGES[chat_id] = []


def clean_youtube_url(url):
    """Remove tracking parameters like 'si' from YouTube URLs."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    # Remove 'si' tracking parameter
    params.pop('si', None)
    clean_query = urllib.parse.urlencode(params, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=clean_query))


def is_youtube_url(text):
    """Check if the text is a valid YouTube URL."""
    if not text:
        return False
    youtube_patterns = [
        r'(https?://)?(www\.)?youtube\.com/watch\?v=[\w-]+',
        r'(https?://)?(www\.)?youtube\.com/shorts/[\w-]+',
        r'(https?://)?(www\.)?youtu\.be/[\w-]+',
        r'(https?://)?(www\.)?youtube\.com/live/[\w-]+',
    ]
    for pattern in youtube_patterns:
        if re.search(pattern, text):
            return True
    return False


def get_video_title(url):
    """Get video title using yt-dlp."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--get-title", url],
            text=True,
            capture_output=True,
            timeout=30
        )
        return result.stdout.strip() if result.returncode == 0 else "Unknown Title"
    except Exception as e:
        print(f"Error getting video title: {e}")
        return "Unknown Title"


def get_audio_duration(file_path):
    """Get audio duration using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return int(float(result.stdout.strip()))
    except Exception as e:
        print(f"Error getting audio duration: {e}")
    return None


def get_thumbnail(url, folder):
    """Download video thumbnail."""
    try:
        command = [
            "yt-dlp",
            "-o", os.path.join(folder, "_thumbnail.%(ext)s"),
            "--write-thumbnail",
            "--skip-download",
            "--convert-thumbnails", "jpg",
            url
        ]
        subprocess.run(command, capture_output=True, timeout=60)

        # Find thumbnail file
        for f in os.listdir(folder):
            if 'thumbnail' in f.lower() and f.endswith('.jpg'):
                return os.path.join(folder, f)
    except Exception as e:
        print(f"Error getting thumbnail: {e}")
    return None


async def download_audio(url, temp_dir, max_retries=10):
    """Download YouTube audio only using yt-dlp with robust retry logic."""
    output_path = os.path.join(temp_dir, 'audio.mp3')

    yt_dlp_command = [
        "yt-dlp",
        "-f", "bestaudio",
        "-x",  # Extract audio
        "--audio-format", "mp3",
        "--audio-quality", "0",  # Best quality
        "-o", output_path,
        url
    ]

    for attempt in range(max_retries + 1):
        try:
            print(f"[AUDIO] Download attempt {attempt + 1}/{max_retries + 1}")
            result = subprocess.run(
                yt_dlp_command,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"[AUDIO] Download successful: {output_path}")
                return output_path
            print(f"[AUDIO] Attempt {attempt + 1} failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            print(f"[AUDIO] Attempt {attempt + 1} timed out")
        except Exception as e:
            print(f"[AUDIO] Attempt {attempt + 1} error: {e}")

        if attempt >= max_retries:
            break

        # Wait for internet before retry
        print("[AUDIO] Waiting for internet connection...")
        if not await wait_for_internet(max_wait=300, check_interval=10):
            print("[AUDIO] Internet connection not restored after 5 minutes")
            return None

        print(f"[AUDIO] Retrying download (attempt {attempt + 2}/{max_retries + 1})...")

    return None


async def download_video(url, temp_dir, max_retries=10):
    """Download YouTube video using yt-dlp with robust retry logic."""
    output_path = os.path.join(temp_dir, 'video.mp4')

    yt_dlp_command = [
        "yt-dlp",
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", output_path,
        url
    ]

    for attempt in range(max_retries + 1):
        try:
            print(f"[VIDEO] Download attempt {attempt + 1}/{max_retries + 1}")
            result = subprocess.run(
                yt_dlp_command,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"[VIDEO] Download successful: {output_path}")
                return output_path
            print(f"[VIDEO] Attempt {attempt + 1} failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            print(f"[VIDEO] Attempt {attempt + 1} timed out")
        except Exception as e:
            print(f"[VIDEO] Attempt {attempt + 1} error: {e}")

        if attempt >= max_retries:
            break

        # Wait for internet before retry
        print("[VIDEO] Waiting for internet connection...")
        if not await wait_for_internet(max_wait=300, check_interval=10):
            print("[VIDEO] Internet connection not restored after 5 minutes")
            return None

        print(f"[VIDEO] Retrying download (attempt {attempt + 2}/{max_retries + 1})...")

    return None


def get_new_video_info(video_path):
    """Calculate target resolution, bitrates, and FPS based on video properties.

    Duration-based resolution scaling (same as translate bot):
    - > 30 min (1800s): max 720p
    - > 1 hour (3600s): max 480p
    - > 2 hours (7200s): max 360p
    - > 6 hours (21600s): max 240p

    FPS reduction:
    - If FPS > 32, halve it until <= 32 (e.g., 60->30, 120->30, 48->24)
    """
    video_width, video_height = Video.get_resolution(video_path)
    new_width = video_width
    new_height = video_height

    # Cap at 1080p
    if video_height > 1080:
        new_height = 1080
        new_width = int(video_width * new_height / video_height)

    # Get audio bitrate, video bitrate, and FPS in a single ffprobe call
    probe = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "stream=codec_type,bit_rate,r_frame_rate",
         "-of", "json", video_path],
        capture_output=True, text=True, timeout=60
    )
    audio_bitrate = MAX_AUDIO_BITRATE
    video_bitrate = 3000 * KiB
    video_fps = 30  # Default
    if probe.stdout:
        try:
            streams = json.loads(probe.stdout).get('streams', [])
            for stream in streams:
                codec_type = stream.get('codec_type')
                if codec_type == 'audio' and audio_bitrate == MAX_AUDIO_BITRATE:
                    # First audio stream
                    if 'bit_rate' in stream:
                        audio_bitrate = int(stream['bit_rate'])
                elif codec_type == 'video' and video_bitrate == 3000 * KiB:
                    # First video stream
                    if 'bit_rate' in stream:
                        video_bitrate = int(stream['bit_rate'])
                    if 'r_frame_rate' in stream:
                        fps_str = stream['r_frame_rate']
                        # fps_str is like "30/1" or "60000/1001"
                        num, den = map(int, fps_str.split('/'))
                        video_fps = num / den if den else 30
        except (KeyError, IndexError, ValueError, ZeroDivisionError):
            pass

    # Reduce FPS if > 32 (halve until <= 32)
    new_fps = video_fps
    while new_fps > 32:
        new_fps = new_fps / 2
    # Round to common values
    new_fps = round(new_fps, 3)

    video_length = Video.get_length(video_path)

    # Duration-based resolution scaling
    if video_length > 1800 and new_height > 720:  # > 30 min
        new_height = 720
        new_width = int(video_width * new_height / video_height)

    if video_length > 3600 and new_height > 480:  # > 1 hour
        new_height = 480
        new_width = int(video_width * new_height / video_height)

    if video_length > 7200 and new_height > 360:  # > 2 hours
        new_height = 360
        new_width = int(video_width * new_height / video_height)

    if video_length > 21600 and new_height > 240:  # > 6 hours
        new_height = 240
        new_width = int(video_width * new_height / video_height)

    # Ensure even dimensions for ffmpeg
    if new_width % 2 != 0:
        new_width += 1
    if new_height % 2 != 0:
        new_height += 1

    # Calculate target bitrates for MAX_VIDEO_SIZE
    audio_size = audio_bitrate * video_length / 8

    new_audio_bitrate = audio_bitrate
    if audio_size > MAX_VIDEO_SIZE / 4:
        new_audio_bitrate = int(MAX_VIDEO_SIZE / 4 / video_length * 8)
    new_audio_bitrate = max(MIN_AUDIO_BITRATE, min(MAX_AUDIO_BITRATE, new_audio_bitrate))

    new_audio_size = new_audio_bitrate * video_length / 8
    new_video_size = MAX_VIDEO_SIZE - new_audio_size
    new_video_bitrate = int(new_video_size / video_length * 8)
    new_video_bitrate = min(video_bitrate, new_video_bitrate)
    new_video_bitrate = int(new_video_bitrate * BITRATE_SAFETY_MARGIN)

    return new_video_bitrate, new_audio_bitrate, new_width, new_height, new_fps, video_fps, video_length


def compress_video(video_path, chat_id=None):
    """Compress video using ffmpeg with software encoding (libx264)."""
    ext = os.path.splitext(video_path)[1]
    compressed_path = video_path.replace(ext, "_compressed.mp4")

    new_video_bitrate, new_audio_bitrate, new_width, new_height, new_fps, original_fps, video_length = get_new_video_info(video_path)

    fps_info = ""
    if new_fps != original_fps:
        fps_info = f", fps: {original_fps:.1f}->{new_fps:.1f}"
    print(f"Compressing to {new_width}x{new_height}, "
          f"video: {new_video_bitrate/KiB:.0f}kbps, audio: {new_audio_bitrate/KiB:.0f}kbps{fps_info}")

    # Timeout: 10x video length (minimum 60 seconds)
    compression_timeout = max(60, int(video_length * 10))

    for attempt in range(5):
        # Build video filter (scale + optional fps reduction)
        vf_filters = [f"scale={new_width}:{new_height}"]
        if new_fps != original_fps:
            vf_filters.append(f"fps={new_fps}")
        vf_string = ",".join(vf_filters)

        command = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf_string,
            "-c:v", "libx264",
            "-preset", "fast",
            "-b:v", str(int(new_video_bitrate)),
            "-c:a", "aac",
            "-b:a", str(int(new_audio_bitrate)),
            compressed_path
        ]

        print(f"Compression attempt {attempt + 1}/5")
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=compression_timeout)
        except subprocess.TimeoutExpired:
            print(f"ffmpeg timed out after {compression_timeout}s")
            return None, None, None

        if result.returncode != 0:
            print(f"ffmpeg failed: {result.stderr}")
            return None, None, None

        compressed_size = os.path.getsize(compressed_path)
        print(f"Compressed size: {compressed_size / MiB:.1f} MiB")

        if compressed_size <= MAX_VIDEO_SIZE:
            return compressed_path, new_width, new_height

        # Reduce bitrate and retry
        print(f"Still too large, reducing bitrate by 10%")
        new_video_bitrate = int(new_video_bitrate * 0.9)

    return None, None, None


async def check_internet(timeout=5):
    """Check if internet is available by connecting to a reliable service."""
    try:
        session = await get_aiohttp_session()
        async with session.get('https://www.google.com', timeout=aiohttp.ClientTimeout(total=timeout)):
            return True
    except Exception:
        return False


async def wait_for_internet(max_wait=300, check_interval=10):
    """Wait for internet to come back, return True if restored within max_wait seconds."""
    start = time.time()
    while time.time() - start < max_wait:
        if await check_internet():
            return True
        elapsed = int(time.time() - start)
        print(f"[NET] Waiting for internet... ({elapsed}s)")
        await asyncio.sleep(check_interval)
    return False


class UploadProgressCallback:
    """Progress callback that updates Telegram message every 10 seconds."""

    def __init__(self, chat_id, message_id, file_size, media_type="video", retry_attempt=0, max_retries=10):
        self.chat_id = chat_id
        self.message_id = message_id
        self.file_size = file_size
        self.media_type = media_type
        self.retry_attempt = retry_attempt
        self.max_retries = max_retries
        self.last_update = 0
        self.update_interval = 10  # seconds
        self._time = time
        self.start_time = time.time()

    async def __call__(self, current, total):
        now = self._time.time()
        if now - self.last_update < self.update_interval:
            return

        self.last_update = now
        percent = current * 100 / total
        elapsed = now - self.start_time
        mib_per_min = (current / MiB) / (elapsed / 60) if elapsed > 0 else 0

        # Print progress update
        retry_info = f" (retry {self.retry_attempt}/{self.max_retries})" if self.retry_attempt > 0 else ""
        print(f"[UPLOAD] {percent:.1f}% ({mib_per_min:.1f} MiB/min){retry_info} - {elapsed/60:.1f} min elapsed")

        try:
            # Build message with optional retry info
            msg_text = f"Uploading {self.media_type} ({self.file_size / MiB:.0f} MiB)... {percent:.0f}%"
            if self.retry_attempt > 0:
                msg_text += f" (retry {self.retry_attempt}/{self.max_retries})"

            await BOT.edit_message_text(
                msg_text,
                self.chat_id,
                self.message_id
            )
        except Exception:
            pass


class UploadFailedError(Exception):
    """Raised when upload fails after all retries."""
    pass


class ConsoleProgressCallback:
    """Simple progress callback for console output (prints every 10 seconds)."""

    def __init__(self, file_size):
        self.file_size = file_size
        self.last_update = 0
        self.update_interval = 10  # seconds
        self._time = time
        self.start_time = time.time()

    def __call__(self, current, total):
        now = self._time.time()
        if now - self.last_update < self.update_interval:
            return

        self.last_update = now
        percent = current * 100 / total
        elapsed = now - self.start_time
        mib_per_min = (current / MiB) / (elapsed / 60) if elapsed > 0 else 0

        print(f"[UPLOAD] {percent:.1f}% ({mib_per_min:.1f} MiB/min) - {elapsed/60:.1f} min elapsed")


async def send_media_telethon(
    chat_id, file_path, caption, duration, thumbnail,
    media_type,  # "video" or "audio"
    width=None, height=None,  # video only
    title=None,  # audio only
    status_message_id=None, file_size=None, max_retries=10
):
    """Send video or audio using Telethon for large files with retry logic.

    Args:
        media_type: "video" or "audio"
        width, height: Required for video
        title: Required for audio
    """
    # Build attributes based on media type
    if media_type == "video":
        media_attributes = DocumentAttributeVideo(
            w=width,
            h=height,
            duration=duration or 0,
            supports_streaming=True
        )
    else:  # audio
        media_attributes = DocumentAttributeAudio(
            duration=duration or 0,
            title=title,
            performer=""
        )

    # For video, include filename; for audio, use title as filename
    if media_type == "video":
        file_attributes = DocumentAttributeFilename(file_name=os.path.basename(file_path))
        attributes = [media_attributes, file_attributes]
    else:
        # For audio, use title as filename (with .mp3 extension) so it displays correctly
        safe_title = (title or "audio").replace("/", "-").replace("\\", "-")
        file_attributes = DocumentAttributeFilename(file_name=f"{safe_title}.mp3")
        attributes = [media_attributes, file_attributes]

    for attempt in range(max_retries + 1):
        try:
            if not TELETHON_CLIENT.is_connected():
                await TELETHON_CLIENT.connect()

            if status_message_id and file_size:
                callback = UploadProgressCallback(chat_id, status_message_id, file_size, media_type, retry_attempt=attempt, max_retries=max_retries)
            else:
                callback = ConsoleProgressCallback(file_size or os.path.getsize(file_path))

            await TELETHON_CLIENT.send_file(
                entity=chat_id,
                file=file_path,
                attributes=attributes,
                caption=caption,
                thumb=thumbnail,
                progress_callback=callback
            )
            print()  # New line after progress
            return  # Success

        except Exception as e:
            print(f"\n[UPLOAD] Error on attempt {attempt + 1}/{max_retries + 1}: {type(e).__name__}: {e}")

            if attempt >= max_retries:
                raise UploadFailedError(f"Upload failed after {max_retries + 1} attempts: {e}")

            # Disconnect Telethon client
            print("[UPLOAD] Disconnecting Telethon...")
            try:
                await TELETHON_CLIENT.disconnect()
            except Exception:
                pass

            # Wait for internet before retry
            print("[UPLOAD] Waiting for internet connection...")
            if not await wait_for_internet(max_wait=300, check_interval=10):
                raise UploadFailedError(f"Internet connection not restored after 5 minutes")

            # Reconnect Telethon client
            print("[UPLOAD] Reconnecting Telethon...")
            try:
                await TELETHON_CLIENT.connect()
            except Exception as conn_err:
                print(f"[UPLOAD] Reconnect failed: {conn_err}, will retry on next attempt")

            print(f"[UPLOAD] Retrying upload (attempt {attempt + 2}/{max_retries + 1})...")

            # Update user message immediately with retry info
            if status_message_id and file_size:
                try:
                    await BOT.edit_message_text(
                        f"Uploading {media_type} ({file_size / MiB:.0f} MiB)... 0% (retry {attempt + 1}/{max_retries})",
                        chat_id,
                        status_message_id
                    )
                except Exception:
                    pass


async def send_video_telethon(chat_id, video_path, caption, width, height, duration, thumbnail, status_message_id=None, file_size=None, max_retries=10):
    """Send video using Telethon. Wrapper for send_media_telethon()."""
    await send_media_telethon(
        chat_id, video_path, caption, duration, thumbnail,
        media_type="video",
        width=width, height=height,
        status_message_id=status_message_id, file_size=file_size, max_retries=max_retries
    )


async def send_audio_telethon(chat_id, audio_path, caption, title, duration, thumbnail, status_message_id=None, file_size=None, max_retries=10):
    """Send audio using Telethon. Wrapper for send_media_telethon()."""
    await send_media_telethon(
        chat_id, audio_path, caption, duration, thumbnail,
        media_type="audio",
        title=title,
        status_message_id=status_message_id, file_size=file_size, max_retries=max_retries
    )


@BOT.message_handler(commands=['help'])
async def handle_help(message):
    """Handle /help command."""
    chat_id = message.chat.id
    user_id = message.from_user.id

    text = "Send a YouTube link to download video or audio."

    # Show admin commands
    if user_id == YTDL_ADMIN_CHAT_ID:
        text += "\n\nAdmin commands:\n/revoke <user_id> - revoke user access"

    await send_message(chat_id, text)


@BOT.message_handler(commands=['revoke'])
async def handle_revoke(message):
    """Handle /revoke command - admin only."""
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Admin only
    if user_id != YTDL_ADMIN_CHAT_ID:
        await send_message(chat_id, "Admin only command.")
        return

    # Parse user ID from command
    parts = message.text.split()
    if len(parts) < 2:
        await send_message(chat_id, "Usage: /revoke <user_id>")
        return

    try:
        target_user_id = int(parts[1])
    except ValueError:
        await send_message(chat_id, "Invalid user ID. Must be a number.")
        return

    # Don't allow revoking admin
    if target_user_id == YTDL_ADMIN_CHAT_ID:
        await send_message(chat_id, "Cannot revoke admin access.")
        return

    # Remove from approved list
    if target_user_id in USER_MANAGER.config["approved_users"]:
        USER_MANAGER.config["approved_users"].remove(target_user_id)
        USER_MANAGER.config.save()
        await send_message(chat_id, f"User {target_user_id} access revoked.")
    else:
        await send_message(chat_id, f"User {target_user_id} was not in approved list.")


@BOT.message_handler(commands=['start'])
async def handle_start(message):
    """Handle /start command."""
    chat_id = message.chat.id
    user_id = message.from_user.id

    if USER_MANAGER.is_approved(user_id):
        text = ("Welcome! Send me a YouTube link and I will ask whether you want video or audio.\n\n"
                "Supported formats:\n"
                "- youtube.com/watch?v=...\n"
                "- youtu.be/...\n"
                "- YouTube Shorts\n"
                "- YouTube Live (recordings)")
    elif USER_MANAGER.is_denied(user_id):
        text = "Sorry, your access request was denied."
    elif USER_MANAGER.is_pending(user_id):
        text = "Your access request is pending approval. Please wait."
    else:
        text = ("Welcome! To use this bot, send me a YouTube link.\n"
                "Your first request will be sent to the admin for approval.")

    await send_message(chat_id, text)


@BOT.message_handler(func=lambda message: True)
async def handle_message(message):
    """Handle all text messages (YouTube links)."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    print(f"[RECV] from {user_id}: {text[:100]}{'...' if len(text) > 100 else ''}")

    # Check if it's a YouTube URL
    if not is_youtube_url(text):
        await send_message(chat_id, "Please send a valid YouTube URL.")
        return

    # Forward to admin for monitoring
    if chat_id != YTDL_ADMIN_CHAT_ID:
        try:
            await BOT.forward_message(YTDL_ADMIN_CHAT_ID, chat_id, message.message_id)
        except Exception as e:
            print(f"Failed to forward message to admin: {e}")

    # Check user status
    if USER_MANAGER.is_denied(user_id):
        await send_message(chat_id, "Sorry, your access has been denied.")
        return

    if USER_MANAGER.is_pending(user_id):
        await send_message(chat_id, "Your previous request is still pending approval. Please wait.")
        return

    if USER_MANAGER.is_approved(user_id):
        # Show Video/Audio choice buttons
        await show_format_choice(chat_id, user_id, text, approved=True)
    else:
        # New user - show format choice first, then request approval
        await show_format_choice(chat_id, user_id, text, approved=False)


async def show_format_choice(chat_id, user_id, url, approved=True):
    """Show inline buttons for Video/Audio choice."""
    # Clean old pending choices
    now = time.time()
    expired = [mid for mid, data in PENDING_CHOICES.items()
               if now - data.get('timestamp', 0) > PENDING_CHOICES_TTL]
    for mid in expired:
        PENDING_CHOICES.pop(mid, None)

    # Create inline keyboard - different callback prefix for unapproved users
    markup = telebot.types.InlineKeyboardMarkup()
    prefix = "dl" if approved else "req"
    video_btn = telebot.types.InlineKeyboardButton(
        "Video", callback_data=f"{prefix}_video")
    audio_btn = telebot.types.InlineKeyboardButton(
        "Audio (MP3)", callback_data=f"{prefix}_audio")
    markup.row(video_btn, audio_btn)

    msg = await send_message(chat_id, "Choose format:", reply_markup=markup)
    add_status_message(chat_id, msg)

    # Store URL keyed by message_id (allows multiple pending URLs per user)
    PENDING_CHOICES[msg.message_id] = {
        'url': url,
        'user_id': user_id,
        'timestamp': now,
        'approved': approved
    }


@BOT.callback_query_handler(func=lambda call: call.data in ('dl_video', 'dl_audio'))
async def handle_format_choice(call):
    """Handle Video/Audio format choice for approved users."""
    format_type = call.data.split('_')[1]  # 'video' or 'audio'
    message_id = call.message.message_id
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    print(f"[CALLBACK] from {user_id}: {call.data}")

    # Get stored URL by message_id
    pending_data = PENDING_CHOICES.pop(message_id, None)
    if not pending_data:
        await BOT.answer_callback_query(call.id, "Session expired. Please send the link again.")
        return
    url = pending_data['url']

    # Delete the format choice message (it's already tracked in STATUS_MESSAGES)
    try:
        await BOT.delete_message(chat_id, call.message.message_id)
        # Remove from tracking since we deleted it manually
        if chat_id in STATUS_MESSAGES and call.message.message_id in STATUS_MESSAGES[chat_id]:
            STATUS_MESSAGES[chat_id].remove(call.message.message_id)
    except Exception as e:
        print(f"Failed to delete format choice message: {e}")

    await BOT.answer_callback_query(call.id)

    # Process download
    if format_type == 'video':
        await process_download(chat_id, user_id, url)
    else:
        await process_audio_download(chat_id, user_id, url)


@BOT.callback_query_handler(func=lambda call: call.data in ('req_video', 'req_audio'))
async def handle_format_choice_unapproved(call):
    """Handle Video/Audio format choice for unapproved users - sends approval request."""
    format_type = call.data.split('_')[1]  # 'video' or 'audio'
    message_id = call.message.message_id
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    # Get stored URL by message_id
    pending_data = PENDING_CHOICES.pop(message_id, None)
    if not pending_data:
        await BOT.answer_callback_query(call.id, "Session expired. Please send the link again.")
        return
    url = pending_data['url']
    audio_only = (format_type == 'audio')

    # Delete the format choice message
    try:
        await BOT.delete_message(chat_id, call.message.message_id)
        if chat_id in STATUS_MESSAGES and call.message.message_id in STATUS_MESSAGES[chat_id]:
            STATUS_MESSAGES[chat_id].remove(call.message.message_id)
    except Exception as e:
        print(f"Failed to delete format choice message: {e}")

    await BOT.answer_callback_query(call.id)

    # Now request approval with the format choice
    await request_approval_with_format(chat_id, user_id, call.from_user, url, audio_only)


async def request_approval_with_format(chat_id, user_id, user, url, audio_only=False):
    """Request admin approval for a new user with format choice."""
    username = user.username or "N/A"
    first_name = user.first_name or "N/A"

    # Create inline keyboard with Approve/Deny buttons
    markup = telebot.types.InlineKeyboardMarkup()
    approve_btn = telebot.types.InlineKeyboardButton(
        "Approve", callback_data=f"approve_{user_id}")
    deny_btn = telebot.types.InlineKeyboardButton(
        "Deny", callback_data=f"deny_{user_id}")
    markup.row(approve_btn, deny_btn)

    # Get video title for context
    title = await asyncio.to_thread(get_video_title, url)
    format_str = "Audio" if audio_only else "Video"

    admin_text = (f"New user request:\n\n"
                  f"User ID: {user_id}\n"
                  f"Username: @{username}\n"
                  f"Name: {first_name}\n"
                  f"Format: {format_str}\n"
                  f"Video: {title}\n"
                  f"URL: {url}")

    try:
        admin_msg = await BOT.send_message(
            YTDL_ADMIN_CHAT_ID, admin_text, reply_markup=markup)

        # Store pending request
        USER_MANAGER.add_pending_request(
            user_id, username, first_name, url, admin_msg.message_id, audio_only)

        # Notify user
        await send_message(chat_id,
                           "Your request has been sent to the admin for approval. "
                           "You will be notified once approved.")
    except Exception as e:
        print(f"Error sending approval request: {e}")
        await send_message(chat_id,
                           "Error processing your request. Please try again later.")


@BOT.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'deny_')))
async def handle_approval_callback(call):
    """Handle admin approval/denial callbacks."""
    action, user_id_str = call.data.split('_', 1)
    user_id = int(user_id_str)

    if action == "approve":
        pending = USER_MANAGER.approve_user(user_id)
        result_text = f"User {user_id} has been APPROVED."

        if pending:
            # Notify user and process their queued request with chosen format
            try:
                await send_message(user_id,
                                   "Your access has been approved! Processing your request...")
                # Process with the format they chose
                if pending.get("audio_only", False):
                    await process_audio_download(user_id, user_id, pending["requested_url"])
                else:
                    await process_download(user_id, user_id, pending["requested_url"])
            except Exception as e:
                print(f"Error processing approved user request: {e}")
    else:
        pending = USER_MANAGER.deny_user(user_id)
        result_text = f"User {user_id} has been DENIED."

        if pending:
            try:
                await send_message(user_id,
                                   "Sorry, your access request has been denied.")
            except Exception as e:
                print(f"Error notifying denied user: {e}")

    # Update admin message
    try:
        await BOT.edit_message_text(
            f"{call.message.text}\n\n{result_text}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None
        )
        await BOT.answer_callback_query(call.id, result_text)
    except Exception as e:
        print(f"Error updating admin message: {e}")


async def process_audio_download(chat_id, user_id, url):
    """Download and send audio only."""
    print(f"[AUDIO] Starting download for user {user_id}")
    temp_dir = tempfile.mkdtemp(prefix="ytdl_")

    try:
        print("[AUDIO] Getting title...")
        title = await asyncio.to_thread(get_video_title, url)
        print(f"[AUDIO] Title: {title}")
        msg = await send_message(chat_id, f"Downloading audio: {title}\nPlease wait...")
        add_status_message(chat_id, msg)

        # Download audio
        print("[AUDIO] Starting yt-dlp download...")
        audio_path = await download_audio(url, temp_dir)
        if not audio_path:
            await send_message(chat_id, "Failed to download audio. Please try again later.")
            await clear_status_messages(chat_id)
            return
        print("[AUDIO] Download complete")

        file_size = os.path.getsize(audio_path)
        print(f"[AUDIO] Downloaded size: {file_size / MiB:.1f} MiB")

        if file_size > MAX_VIDEO_SIZE:
            await send_message(chat_id,
                               f"Audio file is too large ({file_size / MiB:.1f} MiB). "
                               f"Maximum is {MAX_VIDEO_SIZE / GiB:.0f} GB.")
            await clear_status_messages(chat_id)
            return

        # Processing
        msg = await send_message(chat_id, "Processing audio...")
        add_status_message(chat_id, msg)

        # Get thumbnail
        print("[AUDIO] Getting thumbnail...")
        thumbnail_path = await asyncio.to_thread(get_thumbnail, url, temp_dir)
        print(f"[AUDIO] Thumbnail: {thumbnail_path}")

        # Get audio duration
        print("[AUDIO] Getting duration...")
        duration = await asyncio.to_thread(get_audio_duration, audio_path)
        print(f"[AUDIO] Duration: {duration}s")

        # Search for Spotify link
        print("[AUDIO] Searching Spotify...")
        spotify_info = await search_spotify(title)
        print(f"[AUDIO] Spotify: {spotify_info}")

        # Upload to Telegram
        print("[AUDIO] Starting upload...")
        msg = await send_message(chat_id, f"Uploading audio ({file_size / MiB:.0f} MiB)...")
        add_status_message(chat_id, msg)

        # Build caption
        caption = f"Source: {clean_youtube_url(url)}"
        if spotify_info:
            caption += f"\n\nSpotify {spotify_info['artist']} - {spotify_info['name']}: {spotify_info['url']}"

        # Use Telethon for upload
        await send_audio_telethon(
            chat_id,
            audio_path,
            caption,
            title,
            duration,
            thumbnail_path,
            status_message_id=msg.message_id,
            file_size=file_size
        )
        print("[AUDIO] Upload complete")

        # Clear status messages on success
        await clear_status_messages(chat_id)
        print(f"[AUDIO] Done for user {user_id}")

        # Notify admin
        if chat_id != YTDL_ADMIN_CHAT_ID:
            await send_message(YTDL_ADMIN_CHAT_ID, f"Audio sent to user {user_id}: {title}")

    except UploadFailedError as e:
        error_msg = f"Upload failed: {str(e)}"
        print(error_msg)

        await send_message(chat_id,
                           f"Upload failed after multiple retries. Please try again later.\n\nError: {e}")
        await send_message(YTDL_ADMIN_CHAT_ID,
                           f"Upload failed for user {user_id}:\n{url}\n\n{error_msg}")

    except Exception as e:
        error_msg = f"Error processing audio: {str(e)}"
        print(error_msg)
        traceback.print_exc()

        await send_message(chat_id,
                           "An error occurred while processing your audio. Please try again.")
        await send_message(YTDL_ADMIN_CHAT_ID,
                           f"Error for user {user_id}:\n{url}\n\n{error_msg}")

    finally:
        STATUS_MESSAGES.pop(chat_id, None)
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Error cleaning up temp dir: {e}")


async def process_download(chat_id, user_id, url):
    """Main video download and processing function."""
    print(f"[VIDEO] Starting download for user {user_id}")
    temp_dir = tempfile.mkdtemp(prefix="ytdl_")

    try:
        print("[VIDEO] Getting title...")
        title = await asyncio.to_thread(get_video_title, url)
        print(f"[VIDEO] Title: {title}")
        msg = await send_message(chat_id, f"Downloading video: {title}\nPlease wait...")
        add_status_message(chat_id, msg)

        # Download video
        print("[VIDEO] Starting yt-dlp download...")
        video_path = await download_video(url, temp_dir)
        if not video_path:
            await send_message(chat_id, "Failed to download video. Please try again later.")
            await clear_status_messages(chat_id)
            return
        print("[VIDEO] Download complete")

        # Check file size and compress if needed
        file_size = os.path.getsize(video_path)
        print(f"[VIDEO] Downloaded size: {file_size / MiB:.1f} MiB")

        if file_size > MAX_VIDEO_SIZE:
            msg = await send_message(chat_id,
                f"Video is too large ({file_size / GiB:.1f} GB). Compressing...")
            add_status_message(chat_id, msg)

            print("[VIDEO] Starting compression...")
            compressed_path, new_width, new_height = await asyncio.to_thread(compress_video, video_path)
            if not compressed_path:
                await send_message(chat_id,
                    "Failed to compress video. It may be too long.")
                await clear_status_messages(chat_id)
                return

            video_path = compressed_path
            width, height = new_width, new_height
            file_size = os.path.getsize(video_path)
            print(f"[VIDEO] Compression complete: {file_size / MiB:.1f} MiB")
        else:
            # Get video dimensions
            msg = await send_message(chat_id, "Processing video...")
            add_status_message(chat_id, msg)
            print("[VIDEO] Getting resolution...")
            try:
                width, height = await asyncio.to_thread(Video.get_resolution, video_path)
            except Exception:
                width, height = 1920, 1080
            print(f"[VIDEO] Resolution: {width}x{height}")

        # Get video duration
        print("[VIDEO] Getting duration...")
        try:
            duration = int(await asyncio.to_thread(Video.get_length, video_path))
        except Exception:
            duration = None
        print(f"[VIDEO] Duration: {duration}s")

        # Get thumbnail
        print("[VIDEO] Getting thumbnail...")
        thumbnail_path = await asyncio.to_thread(get_thumbnail, url, temp_dir)
        print(f"[VIDEO] Thumbnail: {thumbnail_path}")

        # Upload to Telegram
        print("[VIDEO] Starting upload...")
        msg = await send_message(chat_id, f"Uploading video ({file_size / MiB:.0f} MiB)...")
        add_status_message(chat_id, msg)

        caption = f"{title}\n\nSource: {clean_youtube_url(url)}"

        # Use Telethon for upload
        await send_video_telethon(
            chat_id,
            video_path,
            caption,
            width,
            height,
            duration,
            thumbnail_path,
            status_message_id=msg.message_id,
            file_size=file_size
        )
        print("[VIDEO] Upload complete")

        # Clear status messages on success
        await clear_status_messages(chat_id)
        print(f"[VIDEO] Done for user {user_id}")

        # Notify admin
        if chat_id != YTDL_ADMIN_CHAT_ID:
            await send_message(YTDL_ADMIN_CHAT_ID, f"Video sent to user {user_id}: {title}")

    except UploadFailedError as e:
        error_msg = f"Upload failed: {str(e)}"
        print(error_msg)

        await send_message(chat_id,
                           f"Upload failed after multiple retries. Please try again later.\n\nError: {e}")
        await send_message(YTDL_ADMIN_CHAT_ID,
                           f"Upload failed for user {user_id}:\n{url}\n\n{error_msg}")

    except Exception as e:
        error_msg = f"Error processing video: {str(e)}"
        print(error_msg)
        traceback.print_exc()

        await send_message(chat_id,
                           "An error occurred while processing your video. Please try again.")
        await send_message(YTDL_ADMIN_CHAT_ID,
                           f"Error for user {user_id}:\n{url}\n\n{error_msg}")

    finally:
        STATUS_MESSAGES.pop(chat_id, None)
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Error cleaning up temp dir: {e}")


async def start_telethon_with_retry(max_retries=10):
    """Start Telethon client with retry logic on connection failure."""
    for attempt in range(max_retries + 1):
        try:
            await TELETHON_CLIENT.start(bot_token=YTDL_TELEGRAM_TOKEN)
            print("Telethon client started")
            return
        except Exception as e:
            print(f"[TELETHON] Connection failed on attempt {attempt + 1}/{max_retries + 1}: {type(e).__name__}: {e}")

            if attempt >= max_retries:
                raise Exception(f"Failed to connect to Telegram after {max_retries + 1} attempts")

            # Disconnect if partially connected
            try:
                await TELETHON_CLIENT.disconnect()
            except Exception:
                pass

            print("[TELETHON] Waiting for internet...")
            if not await wait_for_internet(max_wait=300, check_interval=10):
                raise Exception("Internet connection not restored after 5 minutes")

            print(f"[TELETHON] Retrying connection (attempt {attempt + 2}/{max_retries + 1})...")


async def main():
    print(f"YouTube Download Bot v{__version__} starting...")
    print(f"Admin chat ID: {YTDL_ADMIN_CHAT_ID}")
    print(f"Max video size: {MAX_VIDEO_SIZE / GiB:.0f} GB")

    # Start Telethon client with bot token
    await start_telethon_with_retry()
    print("Telethon client ready")

    # Start bot polling
    try:
        await BOT.polling(non_stop=True)
    finally:
        await TELETHON_CLIENT.disconnect()
        await close_aiohttp_session()


# Cache directory for test modes
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "download_cache")


async def test_download_only(url):
    """Download-only mode: download video and metadata, keep files for later processing."""
    print(f"YouTube Download Bot v{__version__} DOWNLOAD-ONLY MODE")
    print(f"URL: {url}")

    try:
        # Create cache directory if needed
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

        # Create unique folder for this download
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        download_dir = os.path.join(CACHE_DIR, url_hash)
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        print(f"[DOWNLOAD] Cache directory: {download_dir}")

        # Get title
        print("[DOWNLOAD] Getting title...")
        title = await asyncio.to_thread(get_video_title, url)
        print(f"[DOWNLOAD] Title: {title}")

        # Download video
        print("[DOWNLOAD] Starting yt-dlp download...")
        video_path = await download_video(url, download_dir)
        if not video_path:
            print("[DOWNLOAD] FAILED to download video")
            return None

        file_size = os.path.getsize(video_path)
        print(f"[DOWNLOAD] Downloaded: {file_size / MiB:.1f} MiB")

        # Get thumbnail
        print("[DOWNLOAD] Getting thumbnail...")
        thumbnail_path = await asyncio.to_thread(get_thumbnail, url, download_dir)
        print(f"[DOWNLOAD] Thumbnail: {thumbnail_path}")

        # Save metadata
        metadata = {
            "url": url,
            "title": title,
            "video_path": video_path,
            "thumbnail_path": thumbnail_path,
            "file_size": file_size,
            "downloaded_at": Time.dotted()
        }
        metadata_path = os.path.join(download_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        print(f"\n[DOWNLOAD] Complete! Files saved to: {download_dir}")
        print(f"[DOWNLOAD] Metadata: {metadata_path}")
        print(f"\n[DOWNLOAD] To process: python3 ytdl_bot.py --test-process {download_dir}")
        print(f"[DOWNLOAD] To upload:  python3 ytdl_bot.py --test-upload {download_dir}")

        return download_dir

    except Exception as e:
        print(f"[DOWNLOAD] ERROR: {e}")
        return None
    finally:
        # Cleanup aiohttp session (used by wait_for_internet if retries occurred)
        await close_aiohttp_session()


async def test_process_only(cache_dir):
    """Process-only mode: process/compress video from cache directory."""
    print(f"YouTube Download Bot v{__version__} PROCESS-ONLY MODE")
    print(f"Cache dir: {cache_dir}")

    # Load metadata
    metadata_path = os.path.join(cache_dir, "metadata.json")
    if not os.path.exists(metadata_path):
        print(f"[PROCESS] ERROR: metadata.json not found in {cache_dir}")
        return None

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    video_path = metadata.get("video_path")
    if not video_path or not os.path.exists(video_path):
        print(f"[PROCESS] ERROR: Video file not found: {video_path}")
        return None

    print(f"[PROCESS] Title: {metadata.get('title')}")
    print(f"[PROCESS] Video: {video_path}")

    file_size = os.path.getsize(video_path)
    print(f"[PROCESS] Current size: {file_size / MiB:.1f} MiB")

    # Check if compression needed
    if file_size > MAX_VIDEO_SIZE:
        print(f"[PROCESS] Video is too large ({file_size / GiB:.1f} GB). Compressing...")
        compressed_path, new_width, new_height = await asyncio.to_thread(compress_video, video_path)
        if not compressed_path:
            print("[PROCESS] ERROR: Compression failed")
            return None

        video_path = compressed_path
        file_size = os.path.getsize(video_path)
        print(f"[PROCESS] Compressed to: {file_size / MiB:.1f} MiB ({new_width}x{new_height})")

        # Update metadata
        metadata["video_path"] = video_path
        metadata["width"] = new_width
        metadata["height"] = new_height
        metadata["compressed"] = True
    else:
        print("[PROCESS] No compression needed")
        # Get video dimensions
        print("[PROCESS] Getting resolution...")
        try:
            width, height = await asyncio.to_thread(Video.get_resolution, video_path)
        except Exception:
            width, height = 1920, 1080
        metadata["width"] = width
        metadata["height"] = height
        print(f"[PROCESS] Resolution: {width}x{height}")

    # Get video duration
    print("[PROCESS] Getting duration...")
    try:
        duration = int(await asyncio.to_thread(Video.get_length, video_path))
    except Exception:
        duration = None
    metadata["duration"] = duration
    print(f"[PROCESS] Duration: {duration}s")

    # Update metadata
    metadata["file_size"] = file_size
    metadata["processed"] = True
    metadata["processed_at"] = Time.dotted()

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"\n[PROCESS] Complete! Updated metadata: {metadata_path}")
    print(f"\n[PROCESS] To upload: python3 ytdl_bot.py --test-upload {cache_dir}")

    return cache_dir


async def test_upload_only(cache_dir):
    """Upload-only mode: upload processed video from cache directory."""
    print(f"YouTube Download Bot v{__version__} UPLOAD-ONLY MODE")
    print(f"Cache dir: {cache_dir}")

    telethon_started = False
    try:
        # Load metadata
        metadata_path = os.path.join(cache_dir, "metadata.json")
        if not os.path.exists(metadata_path):
            print(f"[UPLOAD] ERROR: metadata.json not found in {cache_dir}")
            return False

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        video_path = metadata.get("video_path")
        if not video_path or not os.path.exists(video_path):
            print(f"[UPLOAD] ERROR: Video file not found: {video_path}")
            return False

        title = metadata.get("title", "Unknown")
        url = metadata.get("url", "")
        thumbnail_path = metadata.get("thumbnail_path")
        file_size = metadata.get("file_size") or os.path.getsize(video_path)
        width = metadata.get("width", 1920)
        height = metadata.get("height", 1080)
        duration = metadata.get("duration")

        print(f"[UPLOAD] Title: {title}")
        print(f"[UPLOAD] Size: {file_size / MiB:.1f} MiB")
        print(f"[UPLOAD] Resolution: {width}x{height}")
        print(f"[UPLOAD] Duration: {duration}s")

        # Check if video was processed
        if not metadata.get("processed"):
            print("[UPLOAD] WARNING: Video was not processed. Run --test-process first for best results.")
            # Get dimensions if not in metadata
            if not metadata.get("width"):
                try:
                    width, height = await asyncio.to_thread(Video.get_resolution, video_path)
                except Exception:
                    width, height = 1920, 1080
            if not metadata.get("duration"):
                try:
                    duration = int(await asyncio.to_thread(Video.get_length, video_path))
                except Exception:
                    duration = None

        # Start Telethon
        print("[UPLOAD] Starting Telethon client...")
        await start_telethon_with_retry()
        telethon_started = True

        caption = f"{title}\n\nSource: {clean_youtube_url(url)}" if url else title

        print("[UPLOAD] Uploading to Telegram...")
        await send_video_telethon(
            chat_id=YTDL_ADMIN_CHAT_ID,
            video_path=video_path,
            caption=caption,
            width=width,
            height=height,
            duration=duration,
            thumbnail=thumbnail_path,
            file_size=file_size
        )

        print("\n[UPLOAD] Complete! Video sent to admin chat.")

        # Update metadata
        metadata["uploaded"] = True
        metadata["uploaded_at"] = Time.dotted()
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return True

    except UploadFailedError as e:
        print(f"\n[UPLOAD] FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n[UPLOAD] ERROR: {e}")
        return False
    finally:
        if telethon_started:
            await TELETHON_CLIENT.disconnect()
        await close_aiohttp_session()


async def test_full(url):
    """Full test mode: download, process, and upload video in one shot."""
    print(f"YouTube Download Bot v{__version__} FULL TEST MODE (VIDEO)")
    print(f"Testing URL: {url}")

    telethon_started = False
    try:
        # Start Telethon client with bot token
        await start_telethon_with_retry()
        telethon_started = True

        await process_download(YTDL_ADMIN_CHAT_ID, YTDL_ADMIN_CHAT_ID, url)
        print("[TEST] Complete")
    except Exception as e:
        print(f"[TEST] ERROR: {e}")
    finally:
        if telethon_started:
            await TELETHON_CLIENT.disconnect()
        await close_aiohttp_session()


async def test_audio(url):
    """Full test mode: download, process, and upload audio in one shot."""
    print(f"YouTube Download Bot v{__version__} FULL TEST MODE (AUDIO)")
    print(f"Testing URL: {url}")

    telethon_started = False
    try:
        # Start Telethon client with bot token
        await start_telethon_with_retry()
        telethon_started = True

        await process_audio_download(YTDL_ADMIN_CHAT_ID, YTDL_ADMIN_CHAT_ID, url)
        print("[TEST] Complete")
    except Exception as e:
        print(f"[TEST] ERROR: {e}")
    finally:
        if telethon_started:
            await TELETHON_CLIENT.disconnect()
        await close_aiohttp_session()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='YouTube Download Telegram Bot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test mode examples:
  Full pipeline (download + process + upload):
    python3 ytdl_bot.py --test-video URL   # Video
    python3 ytdl_bot.py --test-audio URL   # Audio (MP3)

  Split pipeline (useful for debugging uploads):
    python3 ytdl_bot.py --test-download URL      # Step 1: Download only
    python3 ytdl_bot.py --test-process PATH      # Step 2: Process video
    python3 ytdl_bot.py --test-upload PATH       # Step 3: Upload to Telegram

  The split pipeline keeps files in download_cache/ so you can retry
  uploads without re-downloading from YouTube.
        """
    )
    parser.add_argument('--test-video', metavar='URL',
                        help='Full test: download, process, and upload video')
    parser.add_argument('--test-audio', metavar='URL',
                        help='Full test: download, process, and upload audio (MP3)')
    parser.add_argument('--test-download', metavar='URL',
                        help='Download only: save video and metadata to cache')
    parser.add_argument('--test-process', metavar='PATH',
                        help='Process only: compress video if needed (PATH is cache dir)')
    parser.add_argument('--test-upload', metavar='PATH',
                        help='Upload only: upload cached video to Telegram (PATH is cache dir)')
    args = parser.parse_args()

    if args.test_audio:
        asyncio.run(test_audio(args.test_audio))
    elif args.test_download:
        asyncio.run(test_download_only(args.test_download))
    elif args.test_process:
        asyncio.run(test_process_only(args.test_process))
    elif args.test_upload:
        asyncio.run(test_upload_only(args.test_upload))
    elif args.test_video:
        asyncio.run(test_full(args.test_video))
    else:
        asyncio.run(main())
