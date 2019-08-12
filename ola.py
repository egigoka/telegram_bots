#! python3
# -*- coding: utf-8 -*-
import datetime
import sys
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

__version__ = "1.7.1"

my_chat_id = 5328715
ola_chat_id = 550959211
tgx_chat_id = 619037205

encrypted_telegram_token = [-14, -22, -51, -21, -57, -55, -42, 6, -20, -13, -40, -6, -42, -3, 1, 20, -3, -15,
                            -16, 47, -45, 0, -24, 62, 7, -17, -55, -14, -39, 2, -15, 58, 16, -17, -16, 46,
                            -11, -31, -47, 49, 46, 45, -60, 30, -26]


def reset_password():
    password = Str.input_pass()
    GIV["api_password"] = password
    return password

try:
    password = GIV["api_password"]
    if "reset" in sys.argv:
        password = reset_password()
except (NameError, KeyError):
    password = reset_password()

telegram_token = Str.decrypt(encrypted_telegram_token, password)
# telegram_token = Str.decrypt(encrypted, Str.input_pass("Enter password:"))

telegram_api = telebot.TeleBot(telegram_token, threaded=False)

class State:
    last_sent = ""


def _start_ola_bot_reciever():
    @telegram_api.message_handler(content_types=["text", 'sticker'])
    def reply_all_messages_ola(message):
        if message.chat.id == my_chat_id:
            if message.text:
                if message.text.startswith("help"):
                    reply = "Commands not implemented now :("
                else:
                    telegram_api.forward_message(ola_chat_id, message.chat.id, message.message_id,
                                                 disable_notification=True)
                    reply = f"Forwarded to Ola: {message.text}"
            else:
                telegram_api.forward_message(ola_chat_id, message.chat.id, message.message_id,
                                             disable_notification=True)
                reply = f"Forwarded to Ola: [sticker]"
            Print.rewrite()
            print(reply)
            telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
        else:
            telegram_api.forward_message(my_chat_id, message.chat.id, message.message_id,
                                         disable_notification=True)
            Print.rewrite()
            print(f"from {message.chat.id}: {message.text}")
    telegram_api.polling(none_stop=True)


def _start_ola_bot_sender():
    while True:
        nowdt = datetime.datetime.now()
        now = nowdt.strftime("%H:%M")
        Time.sleep(20)
        if now == "08:00" and State.last_sent != now:
            State.last_sent = now
            message_text = "Завтрак это важно и полезно, мне мама так говор... ой, у меня же нет мамы, я программка :("
            telegrame.send_message(telegram_api, ola_chat_id, message_text)
            telegrame.send_message(telegram_api, my_chat_id, message_text)
        elif now == "14:00" and State.last_sent != now:
            State.last_sent = now
            message_text = f"Ну давай, поешь, ну чего ты? Nani the fucc???"
            telegrame.send_message(telegram_api, ola_chat_id, message_text)
            telegrame.send_message(telegram_api, my_chat_id, message_text)
        elif now == "20:00" and State.last_sent != now:
            State.last_sent = now
            message_text = "Девять из десяти диетологов рекомендуют есть после шести."
            telegrame.send_message(telegram_api, ola_chat_id, message_text)
            telegrame.send_message(telegram_api, my_chat_id, message_text)


def _start_ola_bot_sender_mine():
    while True:
        nowdt = datetime.datetime.now()
        now = nowdt.strftime("%H:%M")
        weekday = int(nowdt.strftime("%w"))
        Time.sleep(20)
        if now in ["11:05", "17:05"] and State.last_sent != now and weekday in Int.from_to(1, 5):
            State.last_sent = now
            message_text = "Егор, на кухне печеньки!"
            if weekday == 3:
                message_text = "Егор, зохавай фруктиков!"
            telegrame.send_message(telegram_api, my_chat_id, message_text)
        elif now == "16:00" and State.last_sent != now:
            State.last_sent = now
            message_text = "Сходи, покушой, зоебал сидеть!"
            telegrame.send_message(telegram_api, my_chat_id, message_text)


def safe_threads_run():
    # https://www.tutorialspoint.com/python/python_multithreading.htm  # you can expand current implementation

    print(f"Main thread v{__version__} started")

    threads = Threading()

    threads.add(telegrame.very_safe_start_bot, args=(_start_ola_bot_reciever,))
    threads.add(telegrame.very_safe_start_bot, args=(_start_ola_bot_sender,))
    threads.add(telegrame.very_safe_start_bot, args=(_start_ola_bot_sender_mine,))

    threads.start(wait_for_keyboard_interrupt=True)

    Print.rewrite()
    print("Main thread quited")



if __name__ == '__main__':
    safe_threads_run()
