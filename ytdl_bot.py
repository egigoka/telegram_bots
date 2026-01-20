#! python3
# -*- coding: utf-8 -*-
"""
YouTube Download Telegram Bot
Downloads YouTube videos and uploads them to Telegram with admin-controlled access.
"""

import os
import sys
import subprocess
import tempfile
import re

try:
    from commands import File, Dir, Path, Time, Video, MiB, KiB, JsonDict
except ImportError:
    os.system("pip install git+https://github.com/egigoka/commands")
    from commands import File, Dir, Path, Time, Video, MiB, KiB, JsonDict

try:
    import telebot
except ImportError:
    from commands.pip9 import Pip
    Pip.install("pytelegrambotapi")
    import telebot

try:
    import telegrame
except ImportError:
    from commands.pip9 import Pip
    Pip.install("git+https://github.com/egigoka/telegrame")
    import telegrame

try:
    from secrets import YTDL_TELEGRAM_TOKEN, MY_CHAT_ID
except ImportError:
    print("Error: YTDL_TELEGRAM_TOKEN and MY_CHAT_ID must be defined in secrets.py")
    sys.exit(1)

YTDL_ADMIN_CHAT_ID = MY_CHAT_ID

__version__ = "1.1.0"

# Constants
MAX_VIDEO_SIZE = 50 * MiB  # 50 MiB limit for regular Telegram bot API
MIN_AUDIO_BITRATE = 32 * KiB
MAX_AUDIO_BITRATE = 128 * KiB
BITRATE_SAFETY_MARGIN = 0.9

# Telegram bot instance
TELEGRAM_API = telebot.TeleBot(YTDL_TELEGRAM_TOKEN, threaded=False)

# Config paths
CONFIG_DIR = Path.combine(os.path.dirname(os.path.abspath(__file__)), "configs")
USERS_JSON_PATH = Path.combine(CONFIG_DIR, "ytdl_users.json")

# Temporary storage for pending URL choices (user_id -> url)
PENDING_CHOICES = {}

# Temporary storage for status messages to delete (user_id -> [message_ids])
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


def clear_status_messages(chat_id):
    """Delete all tracked status messages for a chat."""
    if chat_id not in STATUS_MESSAGES:
        return
    for message_id in STATUS_MESSAGES[chat_id]:
        try:
            TELEGRAM_API.delete_message(chat_id, message_id)
        except Exception as e:
            print(f"Failed to delete message {message_id}: {e}")
    STATUS_MESSAGES[chat_id] = []


def clean_youtube_url(url):
    """Remove tracking parameters like 'si' from YouTube URLs."""
    import urllib.parse
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


def download_audio(url, temp_dir):
    """Download YouTube audio only using yt-dlp."""
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

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            print(f"Audio download attempt {attempt + 1}/{max_attempts}")
            result = subprocess.run(
                yt_dlp_command,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"Audio download successful: {output_path}")
                return output_path
            print(f"Attempt {attempt + 1} failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            print(f"Attempt {attempt + 1} timed out")
        except Exception as e:
            print(f"Attempt {attempt + 1} error: {e}")
        Time.sleep(5)

    return None


def download_video(url, temp_dir):
    """Download YouTube video using yt-dlp."""
    output_path = os.path.join(temp_dir, 'video.mp4')

    yt_dlp_command = [
        "yt-dlp",
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", output_path,
        url
    ]

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            print(f"Download attempt {attempt + 1}/{max_attempts}")
            result = subprocess.run(
                yt_dlp_command,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"Download successful: {output_path}")
                return output_path
            print(f"Attempt {attempt + 1} failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            print(f"Attempt {attempt + 1} timed out")
        except Exception as e:
            print(f"Attempt {attempt + 1} error: {e}")
        Time.sleep(5)

    return None


def get_compression_params(video_path):
    """Calculate compression parameters to fit 50 MiB limit."""
    try:
        video_width, video_height = Video.get_resolution(video_path)
    except Exception:
        video_width, video_height = 1920, 1080

    try:
        video_length = Video.get_length(video_path)
    except Exception:
        video_length = 60  # Assume 1 minute if can't determine

    # Get current bitrates
    try:
        audio_bitrate = Video.get_audio_bitrate(video_path)
        audio_bitrate = max(MIN_AUDIO_BITRATE, min(MAX_AUDIO_BITRATE, audio_bitrate))
    except Exception:
        audio_bitrate = 96 * KiB

    new_width = video_width
    new_height = video_height

    # Scale down resolution based on video length (more aggressive for 50 MiB)
    if video_length > 60 and video_height > 720:  # > 1 min
        new_height = 720
        new_width = int(video_width * new_height / video_height)

    if video_length > 180 and video_height > 480:  # > 3 min
        new_height = 480
        new_width = int(video_width * new_height / video_height)

    if video_length > 600 and video_height > 360:  # > 10 min
        new_height = 360
        new_width = int(video_width * new_height / video_height)

    if video_length > 1200 and video_height > 240:  # > 20 min
        new_height = 240
        new_width = int(video_width * new_height / video_height)

    # Ensure even dimensions for video encoding
    if new_width % 2 != 0:
        new_width += 1
    if new_height % 2 != 0:
        new_height += 1

    # Calculate bitrates for 50 MiB limit
    target_size_bytes = MAX_VIDEO_SIZE
    target_size_bits = target_size_bytes * 8

    # Audio budget (fixed based on length)
    new_audio_bitrate = min(MAX_AUDIO_BITRATE, max(MIN_AUDIO_BITRATE,
                            int((target_size_bits * 0.1) / video_length)))

    # Video gets the rest
    audio_size_bits = new_audio_bitrate * video_length
    video_budget_bits = target_size_bits - audio_size_bits
    new_video_bitrate = int(video_budget_bits / video_length)

    # Apply safety margin
    new_video_bitrate = int(new_video_bitrate * BITRATE_SAFETY_MARGIN)

    # Minimum video bitrate to maintain quality
    new_video_bitrate = max(100 * KiB, new_video_bitrate)

    return new_video_bitrate, new_audio_bitrate, new_width, new_height


def compress_video(video_path, temp_dir):
    """Compress video to fit 50 MiB limit using ffmpeg with software encoding."""
    compressed_path = os.path.join(temp_dir, 'video_compressed.mp4')

    new_video_bitrate, new_audio_bitrate, new_width, new_height = get_compression_params(video_path)

    for iteration in range(5):
        print(f"Compression iteration {iteration + 1}, "
              f"video bitrate: {new_video_bitrate / KiB:.0f} kbps, "
              f"audio bitrate: {new_audio_bitrate / KiB:.0f} kbps, "
              f"resolution: {new_width}x{new_height}")

        command = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"scale={new_width}:{new_height}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-b:v", str(int(new_video_bitrate)),
            "-c:a", "aac",
            "-b:a", str(int(new_audio_bitrate)),
            compressed_path
        ]

        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=1800)  # 30 min timeout

            if result.returncode != 0:
                print(f"FFmpeg error: {result.stderr}")
                continue

            if os.path.exists(compressed_path):
                file_size = os.path.getsize(compressed_path)
                print(f"Compressed size: {file_size / MiB:.1f} MiB")

                if file_size <= MAX_VIDEO_SIZE:
                    return compressed_path, new_width, new_height
                else:
                    # Reduce bitrates further
                    new_video_bitrate = int(new_video_bitrate * 0.75)
                    new_audio_bitrate = max(MIN_AUDIO_BITRATE, int(new_audio_bitrate * 0.9))
                    print(f"File too large, reducing bitrates...")
        except subprocess.TimeoutExpired:
            print("FFmpeg compression timed out")
        except Exception as e:
            print(f"Compression error: {e}")

    return None, None, None


@TELEGRAM_API.message_handler(commands=['start'])
def handle_start(message):
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

    telegrame.send_message(TELEGRAM_API, chat_id, text)


@TELEGRAM_API.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle all text messages (YouTube links)."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""

    # Check if it's a YouTube URL
    if not is_youtube_url(text):
        telegrame.send_message(TELEGRAM_API, chat_id,
                               "Please send a valid YouTube URL.")
        return

    # Forward to admin for monitoring
    if chat_id != YTDL_ADMIN_CHAT_ID:
        try:
            TELEGRAM_API.forward_message(YTDL_ADMIN_CHAT_ID, chat_id, message.message_id)
        except Exception as e:
            print(f"Failed to forward message to admin: {e}")

    # Check user status
    if USER_MANAGER.is_denied(user_id):
        telegrame.send_message(TELEGRAM_API, chat_id,
                               "Sorry, your access has been denied.")
        return

    if USER_MANAGER.is_pending(user_id):
        telegrame.send_message(TELEGRAM_API, chat_id,
                               "Your previous request is still pending approval. Please wait.")
        return

    if USER_MANAGER.is_approved(user_id):
        # Show Video/Audio choice buttons
        show_format_choice(chat_id, user_id, text)
    else:
        # New user - request approval
        request_approval(message, text)


def show_format_choice(chat_id, user_id, url):
    """Show inline buttons for Video/Audio choice."""
    # Store URL for later
    PENDING_CHOICES[user_id] = url

    # Create inline keyboard
    markup = telebot.types.InlineKeyboardMarkup()
    video_btn = telebot.types.InlineKeyboardButton(
        "Video", callback_data=f"dl_video_{user_id}")
    audio_btn = telebot.types.InlineKeyboardButton(
        "Audio (MP3)", callback_data=f"dl_audio_{user_id}")
    markup.row(video_btn, audio_btn)

    msg = telegrame.send_message(TELEGRAM_API, chat_id,
                                 "Choose format:",
                                 reply_markup=markup)
    add_status_message(chat_id, msg)


@TELEGRAM_API.callback_query_handler(func=lambda call: call.data.startswith(('dl_video_', 'dl_audio_')))
def handle_format_choice(call):
    """Handle Video/Audio format choice."""
    parts = call.data.split('_')
    format_type = parts[1]  # 'video' or 'audio'
    user_id = int(parts[2])
    chat_id = call.message.chat.id

    # Get stored URL
    url = PENDING_CHOICES.pop(user_id, None)
    if not url:
        TELEGRAM_API.answer_callback_query(call.id, "Session expired. Please send the link again.")
        return

    # Delete the format choice message (it's already tracked in STATUS_MESSAGES)
    try:
        TELEGRAM_API.delete_message(chat_id, call.message.message_id)
        # Remove from tracking since we deleted it manually
        if chat_id in STATUS_MESSAGES and call.message.message_id in STATUS_MESSAGES[chat_id]:
            STATUS_MESSAGES[chat_id].remove(call.message.message_id)
    except Exception as e:
        print(f"Failed to delete format choice message: {e}")

    TELEGRAM_API.answer_callback_query(call.id)

    # Process download
    if format_type == 'video':
        process_download(chat_id, user_id, url)
    else:
        process_audio_download(chat_id, user_id, url)


def request_approval(message, url, audio_only=False):
    """Request admin approval for a new user."""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    first_name = message.from_user.first_name or "N/A"
    chat_id = message.chat.id

    # Create inline keyboard with Approve/Deny buttons
    markup = telebot.types.InlineKeyboardMarkup()
    approve_btn = telebot.types.InlineKeyboardButton(
        "Approve", callback_data=f"approve_{user_id}")
    deny_btn = telebot.types.InlineKeyboardButton(
        "Deny", callback_data=f"deny_{user_id}")
    markup.row(approve_btn, deny_btn)

    # Get video title for context
    title = get_video_title(url)

    admin_text = (f"New user request:\n\n"
                  f"User ID: {user_id}\n"
                  f"Username: @{username}\n"
                  f"Name: {first_name}\n"
                  f"Video: {title}\n"
                  f"URL: {url}")

    try:
        admin_msg = TELEGRAM_API.send_message(
            YTDL_ADMIN_CHAT_ID, admin_text, reply_markup=markup)

        # Store pending request
        USER_MANAGER.add_pending_request(
            user_id, username, first_name, url, admin_msg.message_id, audio_only)

        # Notify user
        telegrame.send_message(TELEGRAM_API, chat_id,
                               "Your request has been sent to the admin for approval. "
                               "You will be notified once approved.")
    except Exception as e:
        print(f"Error sending approval request: {e}")
        telegrame.send_message(TELEGRAM_API, chat_id,
                               "Error processing your request. Please try again later.")


@TELEGRAM_API.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'deny_')))
def handle_approval_callback(call):
    """Handle admin approval/denial callbacks."""
    action, user_id_str = call.data.split('_', 1)
    user_id = int(user_id_str)

    if action == "approve":
        pending = USER_MANAGER.approve_user(user_id)
        result_text = f"User {user_id} has been APPROVED."

        if pending:
            # Notify user - they need to send the link again and choose format
            try:
                telegrame.send_message(TELEGRAM_API, user_id,
                                       "Your access has been approved! Please send your YouTube link again.")
            except Exception as e:
                print(f"Error notifying approved user: {e}")
    else:
        pending = USER_MANAGER.deny_user(user_id)
        result_text = f"User {user_id} has been DENIED."

        if pending:
            try:
                telegrame.send_message(TELEGRAM_API, user_id,
                                       "Sorry, your access request has been denied.")
            except Exception as e:
                print(f"Error notifying denied user: {e}")

    # Update admin message
    try:
        TELEGRAM_API.edit_message_text(
            f"{call.message.text}\n\n{result_text}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None
        )
        TELEGRAM_API.answer_callback_query(call.id, result_text)
    except Exception as e:
        print(f"Error updating admin message: {e}")


def process_audio_download(chat_id, user_id, url):
    """Download and send audio only."""
    temp_dir = tempfile.mkdtemp(prefix="ytdl_")

    try:
        title = get_video_title(url)
        msg = telegrame.send_message(TELEGRAM_API, chat_id,
                                     f"Downloading audio: {title}\nPlease wait...")
        add_status_message(chat_id, msg)

        # Download audio
        audio_path = download_audio(url, temp_dir)
        if not audio_path:
            telegrame.send_message(TELEGRAM_API, chat_id,
                                   "Failed to download audio. Please try again later.")
            clear_status_messages(chat_id)
            return

        file_size = os.path.getsize(audio_path)
        print(f"Audio file size: {file_size / MiB:.1f} MiB")

        if file_size > MAX_VIDEO_SIZE:
            telegrame.send_message(TELEGRAM_API, chat_id,
                                   f"Audio file is too large ({file_size / MiB:.1f} MiB). "
                                   f"Maximum is {MAX_VIDEO_SIZE / MiB:.0f} MiB.")
            clear_status_messages(chat_id)
            return

        # Get thumbnail
        thumbnail_path = get_thumbnail(url, temp_dir)

        # Get audio duration
        duration = get_audio_duration(audio_path)

        # Upload to Telegram
        msg = telegrame.send_message(TELEGRAM_API, chat_id, "Uploading audio...")
        add_status_message(chat_id, msg)

        with open(audio_path, 'rb') as audio_file:
            thumb_file = None
            try:
                if thumbnail_path and os.path.exists(thumbnail_path):
                    thumb_file = open(thumbnail_path, 'rb')

                TELEGRAM_API.send_audio(
                    chat_id,
                    audio_file,
                    caption=f"Source: {clean_youtube_url(url)}",
                    title=title,
                    duration=duration,
                    thumb=thumb_file,
                    timeout=300
                )
            finally:
                if thumb_file:
                    thumb_file.close()

        # Clear status messages on success
        clear_status_messages(chat_id)

        # Notify admin
        if chat_id != YTDL_ADMIN_CHAT_ID:
            telegrame.send_message(TELEGRAM_API, YTDL_ADMIN_CHAT_ID,
                                   f"Audio sent to user {user_id}: {title}")

    except Exception as e:
        error_msg = f"Error processing audio: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()

        telegrame.send_message(TELEGRAM_API, chat_id,
                               "An error occurred while processing your audio. Please try again.")
        telegrame.send_message(TELEGRAM_API, YTDL_ADMIN_CHAT_ID,
                               f"Error for user {user_id}:\n{url}\n\n{error_msg}")

    finally:
        try:
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Error cleaning up temp dir: {e}")


def process_download(chat_id, user_id, url):
    """Main video download and processing function."""
    temp_dir = tempfile.mkdtemp(prefix="ytdl_")

    try:
        title = get_video_title(url)
        msg = telegrame.send_message(TELEGRAM_API, chat_id,
                                     f"Downloading video: {title}\nPlease wait...")
        add_status_message(chat_id, msg)

        # Download video
        video_path = download_video(url, temp_dir)
        if not video_path:
            telegrame.send_message(TELEGRAM_API, chat_id,
                                   "Failed to download video. Please try again later.")
            clear_status_messages(chat_id)
            return

        # Check file size
        file_size = os.path.getsize(video_path)
        print(f"Downloaded video size: {file_size / MiB:.1f} MiB")

        # Get video dimensions
        try:
            width, height = Video.get_resolution(video_path)
        except Exception:
            width, height = 1920, 1080

        # Compress if needed
        if file_size > MAX_VIDEO_SIZE:
            msg = telegrame.send_message(TELEGRAM_API, chat_id,
                                         f"Video is {file_size / MiB:.1f} MiB. "
                                         f"Compressing to fit 50 MiB limit...")
            add_status_message(chat_id, msg)

            video_path, width, height = compress_video(video_path, temp_dir)

            if not video_path:
                telegrame.send_message(TELEGRAM_API, chat_id,
                                       "Failed to compress video. "
                                       "It may be too long for the 50 MiB limit.")
                clear_status_messages(chat_id)
                return

            file_size = os.path.getsize(video_path)
            print(f"Compressed video size: {file_size / MiB:.1f} MiB")

        # Get thumbnail
        thumbnail_path = get_thumbnail(url, temp_dir)

        # Upload to Telegram
        msg = telegrame.send_message(TELEGRAM_API, chat_id, "Uploading video...")
        add_status_message(chat_id, msg)

        with open(video_path, 'rb') as video_file:
            thumb_file = None
            try:
                if thumbnail_path and os.path.exists(thumbnail_path):
                    thumb_file = open(thumbnail_path, 'rb')

                TELEGRAM_API.send_video(
                    chat_id,
                    video_file,
                    caption=f"{title}\n\nSource: {clean_youtube_url(url)}",
                    supports_streaming=True,
                    width=width,
                    height=height,
                    thumb=thumb_file,
                    timeout=300
                )
            finally:
                if thumb_file:
                    thumb_file.close()

        # Clear status messages on success
        clear_status_messages(chat_id)

        # Notify admin
        if chat_id != YTDL_ADMIN_CHAT_ID:
            telegrame.send_message(TELEGRAM_API, YTDL_ADMIN_CHAT_ID,
                                   f"Video sent to user {user_id}: {title}")

    except Exception as e:
        error_msg = f"Error processing video: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()

        telegrame.send_message(TELEGRAM_API, chat_id,
                               "An error occurred while processing your video. Please try again.")
        telegrame.send_message(TELEGRAM_API, YTDL_ADMIN_CHAT_ID,
                               f"Error for user {user_id}:\n{url}\n\n{error_msg}")

    finally:
        try:
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Error cleaning up temp dir: {e}")


def _start_bot():
    """Start the Telegram bot polling."""
    TELEGRAM_API.polling(none_stop=True)


def main():
    print(f"YouTube Download Bot v{__version__} starting...")
    print(f"Admin chat ID: {YTDL_ADMIN_CHAT_ID}")
    print(f"Max video size: {MAX_VIDEO_SIZE / MiB:.0f} MiB")
    telegrame.very_safe_start_bot(_start_bot)


if __name__ == '__main__':
    main()
