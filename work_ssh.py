#! python3
# -*- coding: utf-8 -*-
import sys
import os

__version = "0.2.1"

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

my_chat_id = 5328715


class Arguments:
    pass


class State:
    timeout = 10


State = State()


encrypted_telegram_token = [-14, -15, -57, -17, -62, -55, -40, 5, -14, -13, -40, -6, -42, -21, 7, 32, -15, 48, -53, 39,
                            4, -41, -15, 52, -12, 42, -52, 50, -3, 2, -28, 49, 50, -4, -23, -14, -31, -22, 17, 62, -3,
                            -16, 7, -15, -4]


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


def start_ssh_bot():
    telegram_api = telebot.TeleBot(telegram_token, threaded=False)

    @telegram_api.message_handler(content_types=["text"])
    def reply_all_messages(message):
        if message.chat.id == my_chat_id:
            if message.text.lower().startswith("t "):
                try:
                    State.timeout = Str.get_integers(message.text)[0]
                    telegrame.send_message(telegram_api, my_chat_id, f"set timeout to {State.timeout}")
                except IndexError:
                    telegrame.send_message(telegram_api, my_chat_id, f"Failed change timeout {State.timeout}")
            elif message.text.lower().startswith("cd"):
                try:
                    os.chdir(message.text[3:])
                    telegrame.send_message(telegram_api, my_chat_id, f"Dir changed to {Path.working()}")
                except Exception as e:
                    telegrame.send_message(telegram_api, my_chat_id, str(e))
            else:
                print(f"running {message.text}")
                telegrame.send_message(telegram_api, my_chat_id, f"running {message.text}")
                # output, err = Console.get_output("ping 8.8.8.8", pureshell=True, return_merged=False, timeout=2,
                # decoding="cp866", print_std=True)
                try:
                    output, err = Console.get_output(message.text, return_merged=False, timeout=State.timeout,
                                                     print_std=True)
                    if not output and not err:
                        output = "Done!"
                except FileNotFoundError:
                    try:
                        output, err = Console.get_output(message.text, return_merged=False, timeout=State.timeout,
                                                         print_std=True, pureshell=True)
                        if not output and not err:
                            output = "Done!"
                    except Exception as e:
                        telegrame.send_message(telegram_api, my_chat_id, str(e))
                        output, err = "", ""
                except Exception as e:
                    telegrame.send_message(telegram_api, my_chat_id, str(e))
                    output, err = "", ""
                if err:
                    output += newline + "ERROR:" + newline + err
                message_chunks = Str.split_every(output.replace(newline, "{newline}").replace(newline2, "{newline}"),
                                                 4096)
                for chunk in message_chunks:
                    chunk = chunk.replace("{newline}", newline)
                    if not chunk:
                        chunk = "__nil__"
                    telegrame.send_message(telegram_api, my_chat_id, chunk)
        else:
            telegrame.send_message(telegram_api, message.chat.id, "ACCESS DENIED")

    telegram_api.polling()


def main():
    telegrame.very_safe_start_bot(start_ssh_bot)


if __name__ == '__main__':
    main()
