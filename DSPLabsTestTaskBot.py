import os
from telegrame import *
from commands import *

__version__ = "0.0.2"

encrypted_token = [-16, -14, -50, -21, -57, -55, -43, 8, -18, -13, -40, -6, -40, -52, 13, 21, -2, -18, -20, 11, 5, -9,
                   17, 55, -21, 38, -18, 48, -41, -12, -23, 58, -17, 50, -36, -20, -4, -8, 24, 72, 16, 44, 17, 50, -59]

token = Str.decrypt(encrypted_token, Str.input_pass())

bot = telebot.TeleBot(token)


def save_audio_file(chatid):
    dir = Path.combine(os.path.split(__file__)[0])
    subdir = Path.combine(dir, chatid)
    if not Dir.exist(subdir):
        Dir.create(subdir)
    raise NotImplementedError


def start():
    @bot.message_handler(content_types=["text"])
    def reply_text_messages(message):
        bot.send_message(message.chat.id, f"message '{message.text}' received")

    @bot.message_handler(content_types=['voice'])
    def reply_voice_messages(message):
        # save voice
        file_name = f"{Random.string(10)}.ogg"
        download_file(bot, token, message.voice.file_id, file_name)
        # send voice back
        bot.send_message(message.chat.id, f"Received {id} voice message from {message.chat.id}")
        voice = open(file_name, 'rb')
        sent = False
        while not sent:
            try:
                bot.send_voice(message.chat.id, voice)
                sent = True
            except requests.exceptions.ConnectionError as e:
                print(e)
                Time.sleep(5)

    bot.polling(none_stop=True)

very_safe_start_bot(start)
