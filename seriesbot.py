#! python3
# -*- coding: utf-8 -*-
import os
import sys
try:
    from commands import Path, Str, Dir, File, Random, Dict, GIV
except ImportError:
    import os
    os.system("pip install git+https://github.com/egigoka/commands")
    from commands import Path, Str, Dir, File, Random, Dict, GIV
try:
    import telebot
except ImportError:
    from commands.pip9 import Pip
    Pip.install("pytelegrambotapi")
    import telebot
import telegrame

__version__ = "0.0.3"

my_chat_id = 5328715


class Arguments:
    pass


class State:
    series_path = "/mnt/btr/Phones Sync/later"
    search_mode = False


def reset_password():
    global password
    password = Str.input_pass()
    GIV["api_password"] = password
    return password


def send_main_message(message):
    main_markup = telebot.types.ReplyKeyboardMarkup()
    get_random_button = telebot.types.KeyboardButton('Random')
    search_button = telebot.types.KeyboardButton('Search')
    main_markup.row(get_random_button)
    main_markup.row(search_button)

    telegrame.send_message(telegram_api, chat_id=message.chat.id,
                           text="Hello, darling", reply_markup=main_markup)


encrypted_telegram_token = [-14, -23, -48, -15, -60, -50, -48, 5, -15, -14, -47, -6, -46, -37, 24, 30, -3, -14, -35, 11,
                            -56, -24, 5, -1, 13, 13, 0, -3, -25, -30, -15, 41, 41, 32, -60, 0, -7, 11, -26, 57, 35, 30,
                            13, 43, -16, -42]

try:
    password = GIV["api_password"]
    if "reset" in sys.argv:
        password = reset_password()
except (NameError, KeyError) as e:
    password = reset_password()

telegram_token = Str.decrypt(encrypted_telegram_token, password)

telegram_api = telebot.TeleBot(telegram_token, threaded=False)


def start_todoist_bot():
    telegram_api = telebot.TeleBot(telegram_token, threaded=False)

    @telegram_api.message_handler(content_types=["text"])
    def reply_all_messages(message):
        if message.chat.id != my_chat_id:
            telegrame.send_message(telegram_api, message.chat.id, "ACCESS DENIED")
            return

        elif message.text.lower() == "random":
            series = Dir.list_of_files(State.series_path)
            random_series = Random.item(series)
            telegrame.send_message(telegram_api, message.chat.id, random_series.replace(".mp4", ""))
        elif message.text.lower() == "search":
            State.search_mode = True
            telegrame.send_message(telegram_api, message.chat.id, "Enter search query")
        elif State.search_mode:
            State.search_mode = False
            series = Dir.list_of_files(State.series_path)
            search_result = []
            for s in series:
                if message.text.lower() in s.lower():
                    search_result.append(s)
            telegrame.send_message(telegram_api, message.chat.id, "\n".join(search_result))
        elif message.text == "/start":
            send_main_message(message)
        else:
            File.wipe(Path.combine(State.series_path, message.text.lower() + ".mp4"))

    telegram_api.polling(none_stop=True)
    # https://github.com/eternnoir/pyTelegramBotAPI/issues/273


def main():
    telegrame.very_safe_start_bot(start_todoist_bot)


if __name__ == '__main__':
    main()
