import os
from telegrame import *
from commands import *

__version__ = "0.1.2"

encrypted_token = [-16, -14, -50, -21, -57, -55, -43, 8, -18, -13, -40, -6, -40, -52, 13, 21, -2, -18, -20, 11, 5, -9,
                   17, 55, -21, 38, -18, 48, -41, -12, -23, 58, -17, 50, -36, -20, -4, -8, 24, 72, 16, 44, 17, 50, -59]

token = Str.decrypt(encrypted_token, Str.input_pass())

bot = telebot.TeleBot(token)


def count_voices(chat_id):
    dir = Path.combine(os.path.split(__file__)[0])
    subdir = Path.combine(dir, chat_id)
    return len(Dir.list_of_files(subdir))


def get_voice_path(chat_id, voice_id):
    dir = Path.combine(os.path.split(__file__)[0])
    subdir = Path.combine(dir, chat_id)
    if not Dir.exist(subdir):
        Dir.create(subdir)
    path = Path.combine(subdir, f"audio_{voice_id}.ogg")
    return path


def save_audio_file(message):
    file_path = None
    file_id = ID()
    while not file_path:
        check_file_path = get_voice_path(message.chat.id, file_id.get())
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
    @bot.message_handler(content_types=["text"])
    def reply_text_messages(message):
        words = Str.get_words(message.text)
        if len(words) == 1:
            try:
                chat_id = int(words[0])
            except ValueError:
                bot.send_message(message.chat.id, f"message '{message.text}' cannot be interpreted as chat id")
                return
            sending = True
            voice_id = 0
            while sending:
                if File.exist(get_voice_path(chat_id, voice_id)):
                    send_voice(message, chat_id, voice_id)
                    voice_id += 1
                else:
                    bot.send_message(message.chat.id, f"I've sent all {voice_id} voice messages from {chat_id}")
                    sending = False
        if len(words) == 2:
            try:
                chat_id = int(words[0])
                voice_id = int(words[1])
            except ValueError:
                bot.send_message(message.chat.id, f"message '{message.text}' cannot be interpreted as chat id and voice id")
                return
            if File.exist(get_voice_path(chat_id, voice_id)):
                send_voice(message, chat_id, voice_id)
            else:
                bot.send_message(message.chat.id, f"Voice recording with chat id '{chat_id}' and voice id '{voice_id}' not found")

    @bot.message_handler(content_types=['voice'])
    def reply_voice_messages(message):
        bot.send_message(message.chat.id, f"Received {count_voices(message.chat.id)} voice message from {message.chat.id}")
        # save voice
        file_name = save_audio_file(message)
        bot.send_message(message.chat.id, f"Saved as {file_name}")
        # send voice back


    bot.polling(none_stop=True)

very_safe_start_bot(start)
