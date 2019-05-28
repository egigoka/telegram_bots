import os
from telegrame import *
from commands import *

__version__ = "0.3.15"

print(f"DSPLabsTestTaskBot v{__version__}")

script_dir = os.path.split(__file__)[0]
voices_dir = Path.combine(script_dir, "voices")
my_chat_id = 5328715
encrypted_token = [-16, -14, -50, -21, -57, -55, -43, 8, -18, -13, -40, -6, -40, -52, 13, 21, -2, -18, -20, 11, 5, -9,
                   17, 55, -21, 38, -18, 48, -41, -12, -23, 58, -17, 50, -36, -20, -4, -8, 24, 72, 16, 44, 17, 50, -59]

token = Str.decrypt(encrypted_token, Str.input_pass())

bot = telebot.TeleBot(token)


def count_voices(chat_id):
    directory = voices_dir
    subdir = Path.combine(directory, chat_id)
    return len(Dir.list_of_files(subdir))


def get_voice_path(chat_id, voice_id, create_dir=False):
    directory = voices_dir
    subdir = Path.combine(directory, chat_id)
    if not Dir.exist(subdir) and create_dir:
        Dir.create(subdir)
    path = Path.combine(subdir, f"audio_{voice_id}.ogg")
    return path


def mark_as_deleted(path):
    try:
        File.create(path + "_del")
    except FileExistsError:
        pass


def is_mark_as_deleted(path):
    return File.exist(path + "_del")


def save_audio_file(message):
    file_path = None
    file_id = ID()
    while not file_path:
        check_file_path = get_voice_path(message.chat.id, file_id.get(), create_dir=True)
        if not File.exist(check_file_path):
            file_path = check_file_path
    download_file(bot, token, message.voice.file_id, file_path)
    return file_path


def send_voice(message, chat_id, voice_id):
    voice = open(get_voice_path(chat_id, voice_id), 'rb')
    sent = False
    while not sent:
        try:
            bot.send_voice(message.chat.id, voice)
            sent = True
        except requests.exceptions.ConnectionError as e:
            print(e)
            Time.sleep(5)


def start():
    @bot.message_handler(commands=['help', 'start'])
    def send_help(message, error_message=None):
        if message.text.lower().startswith("/start"):
            bot.send_message(message.chat.id, f"Hello, human #{message.chat.id}")
        if error_message:
            bot.send_message(message.chat.id, f"ERROR:{error_message}")
        bot.send_message(message.chat.id,
                         f"All sended voice messages collected in filesystem.{newline}"
                         f"You can send your voice message to store it on my server.{newline}"
                         f"Of cource, you also can request saved voice messages.{newline}"
                         f"You can send chat id like this: 5328715{newline}"
                         f"Or if you need specific message, send chat id and voice id: 5328715 0{newline}"
                         f"And yes, this is real mine chat id, so you can listen my message :){newline}"
                         f"If you just want to get your chat id, send command '/chatid'.{newline}"
                         f"For deletion send 'delete <chat id>' for delete all messages {newline}"
                         f"or 'delete <chat id> <voice id>'.{newline}"
                         f"For get list of all saved voice mails, type /list")

    @bot.message_handler(commands=['chatid', 'chat_id'])
    def chatid(message):
        bot.send_message(message.chat.id, f"Your chat id is '{message.chat.id}'")

    @bot.message_handler(commands=["del", "delete", "rem", "remove"])
    def delete(message):
        ints = Str.get_integers(message.text)
        if len(ints) == 1:
            chat_id = ints[0]
            deleting = True
            voice_id = 0
            cnt_deleted = 0
            while deleting:
                voice_path = get_voice_path(chat_id, voice_id)
                if File.exist(voice_path):
                    if is_mark_as_deleted(voice_path):
                        pass  # not send any info
                    else:
                        mark_as_deleted(get_voice_path(chat_id, voice_id))
                        cnt_deleted += 1
                    voice_id += 1
                else:
                    bot.send_message(message.chat.id, f"Deleted all {cnt_deleted} voice messages from {chat_id}")
                    deleting = False
        elif len(ints) == 2:
            chat_id = ints[0]
            voice_id = ints[1]
            mark_as_deleted(get_voice_path(chat_id, voice_id))
            bot.send_message(message.chat.id, f"Deleted voice {chat_id} {voice_id}")
        else:
            send_help(message, f"not deleted {message.text}")

    @bot.message_handler(commands=["list"])
    def send_list(message):
        output_text = ""
        for directory in Dir.list_of_dirs(voices_dir):
            dir_path = Path.combine(voices_dir, directory)
            output_files = []
            for file in Dir.list_of_files(dir_path):
                file_path = Path.combine(dir_path, file)
                if file.endswith(".ogg") and not is_mark_as_deleted(file_path):
                    output_files.append(file)
            if output_files:
                output_text += f"{directory}{newline}"
                for file in output_files:
                    output_text += f"    {Str.get_integers(file)[0]}{newline}"
                    # output_text += f"    {file}{newline}"
        bot.send_message(message.chat.id, output_text)

    @bot.message_handler(content_types=["text"])
    def reply_text_messages(message):
        # some telemetry :D
        if message.chat.id != my_chat_id:
            bot.forward_message(my_chat_id, message.chat.id, message.message_id, disable_notification=True)
        # workarond if commands was send wihtout /
        if message.text.lower() in ["help"]:
            send_help(message)
            return
        if message.text.lower() in ["list"]:
            send_list(message)
            return
        if message.text.lower().startswith("del") or message.text.lower().startswith("rem"):
            delete(message)
            return
        if message.text.lower() in ["chat id", "chatid", "chat_id"]:
            chatid(message)
            return
        # send audio messages
        words = Str.get_words(message.text)
        if len(words) == 1:
            try:
                chat_id = int(words[0])
            except ValueError:
                bot.send_message(message.chat.id, f"message '{message.text}' cannot be interpreted as chat id")
                return
            sending = True
            voice_id = 0
            cnt_sended = 0
            while sending:
                voice_path = get_voice_path(chat_id, voice_id)
                if File.exist(voice_path):
                    if is_mark_as_deleted(voice_path):
                        pass  # not send any info
                    else:
                        send_voice(message, chat_id, voice_id)
                        cnt_sended += 1
                    voice_id += 1
                else:
                    if cnt_sended == 0:
                        bot.send_message(message.chat.id, f"No messages from {chat_id} saved")
                    sending = False
        elif len(words) == 2:
            try:
                chat_id = int(words[0])
                voice_id = int(words[1])
            except ValueError:
                bot.send_message(message.chat.id, f"message '{message.text}'"
                f" cannot be interpreted as chat id and voice id")
                return
            voice_path = get_voice_path(chat_id, voice_id)
            if File.exist(voice_path) and not is_mark_as_deleted(voice_path):
                send_voice(message, chat_id, voice_id)
            else:
                bot.send_message(message.chat.id, f"Voice recording with chat id '{chat_id}' "
                f"and voice id '{voice_id}' not found")
        else:
            send_help(message, f"Not found command '{message.text}'")

    @bot.message_handler(content_types=['voice'])
    def reply_voice_messages(message):
        bot.send_message(message.chat.id, f"Received {count_voices(message.chat.id) - 1} "
        f"voice message from {message.chat.id}")
        save_audio_file(message)

    bot.polling(none_stop=True)


very_safe_start_bot(start)
