#! python3
# -*- coding: utf-8 -*-
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
    from miio import Device
    from miio.exceptions import DeviceException
except ImportError:
    import sys
    print("install python-miio")
    sys.exit(1)
try:
    from secrets import BATTERY_TELEGRAM_TOKEN, MY_CHAT_ID, VACUUM_IP, VACUUM_TOKEN
except ImportError:
    import sys
    print("create secrets.py with BATTERY_TELEGRAM_TOKEN, MY_CHAT_ID, VACUUM_IP and VACUUM_TOKEN")
    sys.exit(1)

__version__ = "0.0.2"

ONCE = "--once" in OS.args
DEBUG = "--debug" in OS.args
PREVIOUS = JsonDict("./configs/vacuum.json")
RUN_EVERY = 30
HOSTNAME = OS.hostname


STATUS_MAP = {
    1: "Idle",
    2: "Sweeping",
    3: "Paused",
    4: "Error",
    5: "Charging",
    6: "Returning",
    7: "Mopping",
}

TELEGRAM_API = telebot.TeleBot(BATTERY_TELEGRAM_TOKEN, threaded=False)

print_original = print

def print(*args, **kwargs):
    kwargs["flush"] = True
    print_original(*args, **kwargs)


def get_vacuum_struct():
    d = Device(VACUUM_IP, VACUUM_TOKEN)
    result = d.send('get_properties', [
        {'did': 'status', 'siid': 2, 'piid': 1},
        {'did': 'battery', 'siid': 3, 'piid': 1},
        {'did': 'charging', 'siid': 3, 'piid': 2},
    ])
    struct = {}
    for r in result:
        struct[r['did']] = r['value']
    return struct


def save_previous(state):
    PREVIOUS.string = state
    PREVIOUS.save()


def status_name(code):
    return STATUS_MAP.get(code, f"Unknown({code})")


def check_vacuum():
    try:
        output = get_vacuum_struct()
    except DeviceException as e:
        print(f"vacuum unreachable: {e}")
        return

    if DEBUG:
        print(output)

    now_battery = output['battery']
    now_status = output['status']

    print(f"vacuum: {now_battery}%, {status_name(now_status)}")

    if DEBUG:
        print(f"now = {now_battery}%, {status_name(now_status)}")
    if PREVIOUS:
        if DEBUG:
            print(f"previous = {PREVIOUS['battery']}%, {status_name(PREVIOUS['status'])}")
    else:
        save_previous(output)
        return

    try:
        previous_battery = int(PREVIOUS['battery'])
    except (ValueError, KeyError):
        previous_battery = 0

    diff = abs(now_battery - previous_battery)

    changed = diff > 10 \
        or PREVIOUS['status'] != now_status

    if changed:
        message = f"{HOSTNAME} vacuum: {now_battery}%, {status_name(now_status)}"
        if DEBUG:
            print(message)
        telegrame.send_message(TELEGRAM_API, MY_CHAT_ID, message)
        save_previous(output)


def _start_bot_sender():
    while True:
        check_vacuum()
        Time.sleep(RUN_EVERY)


def safe_threads_run():
    print(f"Main thread v{__version__} started")

    threads = Threading()

    threads.add(telegrame.very_safe_start_bot, args=(_start_bot_sender,))

    threads.start(wait_for_keyboard_interrupt=True)

    print("Main thread quited")


if __name__ == '__main__':
    if ONCE:
        check_vacuum()
    else:
        safe_threads_run()
