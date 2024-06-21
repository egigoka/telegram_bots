#! python3
# -*- coding: utf-8 -*-
import os
import sys
try:
    from commands import Path, Str, Dir, File, Random, Dict, GIV, newline
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
from secrets import SERIES_TELEGRAM_TOKEN, MY_CHAT_ID

__version__ = "0.4.1"

my_chat_id = MY_CHAT_ID


class Arguments:
    pass


class State:
    series_path = "/mnt/btr/Phones Sync/later"
    search_mode = False
    removing_mode = False

def send_main_message(message):
    main_markup = telebot.types.ReplyKeyboardMarkup()
    get_random_button = telebot.types.KeyboardButton('Random')
    get_all = telebot.types.KeyboardButton('All')
    search_button = telebot.types.KeyboardButton('Search')
    remove_keyboard_button = telebot.types.KeyboardButton('Remove')
    main_markup.row(get_random_button, get_all)
    main_markup.row(search_button, remove_keyboard_button)

    telegrame.send_message(telegram_api, chat_id=message.chat.id,
                           text="Hello, darling", reply_markup=main_markup)


def get_series():
    return Dir.list_of_files(State.series_path)

telegram_token = SERIES_TELEGRAM_TOKEN

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
        elif message.text.lower() in ["search", "find"]:
            State.search_mode = True
            telegrame.send_message(telegram_api, message.chat.id, "Enter search query")
        elif message.text.lower() == "all":
            series = get_series()
            series.sort()
            telegrame.send_message(telegram_api, message.chat.id, newline.join(series))
        elif State.search_mode:
            State.search_mode = False
            series = get_series()
            search_result = []
            for s in series:
                if message.text.lower() in s.lower():
                    search_result.append(s)
            search_result.sort()
            telegrame.send_message(telegram_api, message.chat.id, "\n".join(search_result))
        elif message.text.lower() in ["remove", "delete"]:
            State.removing_mode = True
            telegrame.send_message(telegram_api, message.chat.id, "Enter name to remove")
        elif State.removing_mode:
            State.removing_mode = False
            filename = message.text.lower()
            filename = filename.replace("<space>", " ")
            filename += ".mp4"
            path = Path.combine(State.series_path, filename)
            if File.exist(path):
                File.delete(path)
                message_send = f"Series '{filename}' removed"
            else:
                message_send = f"Series '{filename}' not found"
            telegrame.send_message(telegram_api, message.chat.id, message_send)
        elif message.text == "/start":
            send_main_message(message)
        else:
            for line in Str.nl(message.text):
                if line.strip() == "":
                    continue
                filename = line.lower() + ".mp4"
                try:
                    File.create(Path.combine(State.series_path, filename))
                    message_send = f"Series '{filename}' added"
                except FileExistsError:
                    message_send = f"Series '{filename}' already exists"
                telegrame.send_message(telegram_api, message.chat.id, message_send)

    telegram_api.polling(none_stop=True)
    # https://github.com/eternnoir/pyTelegramBotAPI/issues/273


def main():
    telegrame.very_safe_start_bot(start_todoist_bot)


if __name__ == '__main__':
    main()
