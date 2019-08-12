#! python3
# -*- coding: utf-8 -*-
import datetime
try:
    from commands import *
except ImportError:
    import os
    os.system("pip install git+https://github.com/egigoka/commands")
    from commands import *
try:
    import telebot
except ImportError:
    from commands.pip9 import Pip
    Pip.install("pytelegrambotapi")  # https://github.com/eternnoir/pyTelegramBotAPI
    import telebot
import time
import telegrame

__version__ = "0.0.1"

my_chat_id = 5328715
ola_chat_id = 550959211
tgx_chat_id = 619037205

encrypted_telegram_token = [-13, -19, -49, -21, -61, -51, -40, 5, -21, -13, -40, -6, -41, 7, 8, 32, -1, 50,
                            -8, 28, -32, -34, -10, 3, -14, 46, -25, -14, -42, -26, 9, 59, 28, 49, -32, 8,
                            -34, -9, -7, 41, 48, 46, 1, 38, -26]


telegram_token = Str.decrypt(encrypted_telegram_token, Str.input_pass())

telegram_api = telebot.TeleBot(telegram_token, threaded=False)


class State:
    def __init__(self):
        self.saved = []


State = State()


def _start_bot_reciever():
    @telegram_api.message_handler(content_types=["text", 'sticker'])
    def reply_all_messages(message):

        if message.chat.id == my_chat_id:
            if message.text:
                print(fr"input: {message.text}")
                if message.text.lower().startswith("help"):
                    reply = "no help in here"
                    message_obj = telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                elif message.text.lower() == "привет!":
                    reply = "Ну что там у тебя?"
                    message_obj = telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                elif message.text.lower() == "пока":
                    reply = "Ну бывай"
                    message_obj = telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                elif message.text.lower() == "как твои?":
                    for obj in State.saved:
                        if File.exist(obj):
                            photo = open(obj, 'rb')
                            telegram_api.send_photo(message.chat.id, photo)
                        reply = "Ну бывай"
                        message_obj = telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                else:
                    reply = "Unknown command, enter 'help'"
                    message_obj = telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
            else:
                reply = "Stickers doesn't supported"
                message_obj = telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)

        else:
            telegram_api.forward_message(my_chat_id, message.chat.id, message.message_id,
                                         disable_notification=True)
            Print.rewrite()
            print(f"from {message.chat.id}: {message.text}")
    telegram_api.polling(none_stop=True)


def _start_bot_sender():
    while True:
        time.sleep(0.2)
        pass


def safe_threads_run():
    # https://www.tutorialspoint.com/python/python_multithreading.htm  # you can expand current implementation

    print(f"Main thread v{__version__} started")

    threads = Threading()

    threads.add(telegrame.very_safe_start_bot, args=(_start_bot_reciever,), name="Reciever")
    # threads.add(telegrame.very_safe_start_bot, args=(_start_bot_sender,), name="Sender")

    threads.start(wait_for_keyboard_interrupt=True)

    Print.rewrite()
    print("Main thread quited")


if __name__ == '__main__':
    safe_threads_run()
