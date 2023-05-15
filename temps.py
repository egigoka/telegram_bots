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

__version__ = "0.0.6"

my_chat_id = 5328715

encrypted_telegram_token = [-15, -21, -52, -17, -57, -55, -43, 5, -13, -20, -47, -6, -46, -37, -16, 36, 49, 15, 8, 10, -3, 0, -46, 17, 10, 36, -8, -15, -14, -39, -24, 70, 35, 30, -54, 26, -62, -10, -11, 7, 33, -19, -34, -16, -8, -22]


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


def get_disks_list():
    """
    Get the list of disks in Linux.

    Returns:
    A list of strings, where each string is the output of the `hddtemp /dev/diskname` command.
    """

    # Get the list of disks.
    disks = ['/dev/' + disk for disk in Dir.list_of_entries('/dev') if disk.startswith('sd') and len(disk) == 3]

    # Get the output of the `hddtemp /dev/diskname` command for each disk.
    outputs = []
    for disk in disks:
        Print(f"getting 'hddtemp {disk}'")
        output = Console.get_output('hddtemp ' + disk)
        outputs.append(output)

    return "".join(outputs)


def _start_bot_reciever():
    @telegram_api.message_handler(content_types=["text", 'sticker'])
    def reply_all_messages_ola(message):
        telegram_api.forward_message(my_chat_id, message.chat.id, message.message_id,
                                         disable_notification=True)
        Print.rewrite()
        print(f"from {message.chat.id}: {message.text}")
    telegram_api.polling(none_stop=True)


def _start_bot_sender():
    while True:
        nowdt = datetime.datetime.now()
        sensors = Console.get_output("sensors")
        harddrives = get_disks_list()
        message_text = f"{nowdt}{newline*2}{sensors}{harddrives}"
        telegrame.send_message(telegram_api, my_chat_id, message_text)
        Time.sleep(60)


def safe_threads_run():
    # https://www.tutorialspoint.com/python/python_multithreading.htm  # you can expand current implementation

    print(f"Main thread v{__version__} started")

    threads = Threading()

    threads.add(telegrame.very_safe_start_bot, args=(_start_bot_reciever,))
    threads.add(telegrame.very_safe_start_bot, args=(_start_bot_sender,))

    threads.start(wait_for_keyboard_interrupt=True)

    Print.rewrite()
    print("Main thread quited")



if __name__ == '__main__':
    safe_threads_run()
