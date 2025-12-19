#! python3
# -*- coding: utf-8 -*-
import datetime

try:
    from commands import *
except ImportError:
    import sys
    print("install https://github.com/egigoka/commands")
    sys.exit(1)
try:
    import telebot
except ImportError:
    import sys
    print("install pytelegrambotapi")
    sys.exit(1)
try:
    import telegrame
except ImportError:
    import sys
    print("install https://github.com/egigoka/telegrame")
    sys.exit(1)
try:
    from secrets import BATTERY_TELEGRAM_TOKEN, MY_CHAT_ID
except ImportError:
    import sys
    print("create secrets.py with BATTERY_TELEGRAM_TOKEN and MY_CHAT_ID")
    sys.exit(1)

__version__ = "0.0.3"

BATTERY = OS.args[1]
ONCE = "--once" in OS.args
DEBUG = "--debug" in OS.args
PREVIOUS = JsonDict("./configs/battery.json")
RUN_EVERY = 300
HOSTNAME = OS.hostname

TELEGRAM_API = telebot.TeleBot(BATTERY_TELEGRAM_TOKEN, threaded=False)

print_original = print

def print(*args, **kwargs):
    kwargs["flush"] = True
    print_original(*args, **kwargs)

def get_battery_struct():
    out = Console.get_output(["upower", "-i", BATTERY])
    struct = {}
    for line in Str.nl(out):
        if not line:
            continue
        words = line.split(":")
        key = words[0].strip()
        value = " ".join(words[1:]).strip()
        if not value:
            continue
        struct[key] = value
    return struct


def save_previous(state):
    PREVIOUS.string = state
    PREVIOUS.save()


def get_time_to(state):
    time_to_completion = "time to empty"
    if time_to_completion not in state.keys():
        time_to_completion = "time to full"
    if time_to_completion not in state.keys():
        return None  # none found
    return state[time_to_completion]


def check_battery():
    output = get_battery_struct()

    if DEBUG:
        print(output)
    
    if DEBUG:
        print(f"now = {output['percentage']} {get_time_to(output)} {output['state']}")
    if PREVIOUS:
        if DEBUG:
            print(f"previous = {PREVIOUS['percentage']} {get_time_to(PREVIOUS)} {output['state']}")
    else:
        save_previous(output)

    now_percentage = int(output["percentage"][:-1])
    try:
        previous_percentage = int(PREVIOUS["percentage"][:-1])
    except ValueError:
        previous_percentage = 0

    diff = abs(now_percentage - previous_percentage)
    
    changed = diff > 10 \
        or PREVIOUS['state'] != output['state']

    if changed:
        time_to = get_time_to(output)
        if time_to is None:
            time_to = ""
        else:
            time_to = f", {time_to} left"
        message = f"{HOSTNAME}: {output['percentage']}{time_to}, {output['state']}"
        if DEBUG:
            print(message)
        telegrame.send_message(TELEGRAM_API, MY_CHAT_ID, message)
        save_previous(output)


def _start_bot_sender():
    while True:
        check_battery()
        Time.sleep(RUN_EVERY)


def safe_threads_run():
    # https://www.tutorialspoint.com/python/python_multithreading.htm  # you can expand current implementation

    print(f"Main thread v{__version__} started")
    
    threads = Threading()

    threads.add(telegrame.very_safe_start_bot, args=(_start_bot_sender,))

    threads.start(wait_for_keyboard_interrupt=True)

    # Print.rewrite()
    print("Main thread quited")


if __name__ == '__main__':
    if ONCE:
        check_battery()
    else:
        safe_threads_run()
    
