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

    Pip.install("pytelegrambotapi")
    import telebot
import telegrame
import platform
from secrets import IMALIVE_TELEGRAM_TOKEN, MY_CHAT_ID


__version__ = "0.0.1"


TELEGRAM_API = telebot.TeleBot(IMALIVE_TELEGRAM_TOKEN, threaded=False)
HOSTNAME = platform.node()


def _start_bot_receiver():
    @TELEGRAM_API.message_handler(content_types=["text", 'sticker'])
    def reply_all_messages(message):
        TELEGRAM_API.forward_message(MY_CHAT_ID, message.chat.id, message.message_id,
                                     disable_notification=True)
        Print.rewrite()
        print(f"from {message.chat.id}: {message.text}")

    TELEGRAM_API.polling(none_stop=True)



def _start_bot_sender():
    last_sent = None
    while True:
        now_dt = datetime.datetime.now()
        string = now_dt.strftime("%Y-%m-%d %H:%M")

        if string != last_sent:
            last_sent = string
            message_text = f"{string} - {HOSTNAME}"
            print(message_text)
            telegrame.send_message(TELEGRAM_API, MY_CHAT_ID, message_text)
        Time.sleep(0.9)


def safe_threads_run():
    # https://www.tutorialspoint.com/python/python_multithreading.htm  # you can expand current implementation

    print(f"Main thread v{__version__} started")
    
    threads = Threading()

    threads.add(telegrame.very_safe_start_bot, args=(_start_bot_receiver,))
    threads.add(telegrame.very_safe_start_bot, args=(_start_bot_sender,))

    threads.start(wait_for_keyboard_interrupt=True)

    Print.rewrite()
    print("Main thread quited")


if __name__ == '__main__':
    safe_threads_run()
