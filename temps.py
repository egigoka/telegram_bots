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
from secrets import TEMPS_TELEGRAM_TOKEN, MY_CHAT_ID

__version__ = "0.1.0"

IGNORED_SENSORS = ["CHASSIS1 FAN Speed"]
IGNORED_HARD_DRIVES_TEMPERATURE = ["M4-CT128M4SSD2"]
IGNORED_SYSTEMD_SERVICES = ["gmail-cli-ai.service"]
OUTPUT_ALL_SENSORS = False

TELEGRAM_API = telebot.TeleBot(TEMPS_TELEGRAM_TOKEN, threaded=False)


def get_list_of_disks():
    return ['/dev/' + disk for disk in Dir.list_of_entries('/dev') if disk.startswith('sd') and len(disk) == 3]


def get_drive_temps(disks):
    """
    Get the list of disks in Linux.

    Returns:
    A list of strings, where each string is the output of the `hddtemp /dev/disk_name` command.
    """
    # Get the output of the `hddtemp /dev/disk_name` command for each disk.
    outputs = []
    for disk in disks:
        output = Console.get_output('hddtemp', disk)
        outputs.append(output)

    return "".join(outputs)


def remove_useless_parts(input_strings):
    while "min" in input_strings:
        input_strings.remove("min")
    while "max" in input_strings:
        input_strings.remove("max")
    while "high" in input_strings:
        input_strings.remove("high")
    while "crit" in input_strings:
        input_strings.remove("crit")
    while "=" in input_strings:
        input_strings.remove("=")
    return input_strings


def get_value_and_unit(value_info):
    value_parts = value_info.split()
    value_parts = remove_useless_parts(value_parts)
    value_float = Str.get_integers(value_parts[0])[0]

    value_str = str(round(value_float, 2))

    unit = Str.substring(value_parts[0], "+", safe=True)
    unit = Str.substring(unit, value_str, "")

    value = float(value_str)
    unit = value_parts[1] if len(value_parts) > 1 else unit

    return value, unit


def convert_units(value, unit):
    if unit is None and value is None:
        return None, None
    if unit == 'mV':
        return value / 1000, 'V'
    if unit == 'RPM':
        return value, unit
    if unit == '°C':
        return value, unit
    if unit == 'V':
        return value, unit
    raise ValueError(f"Unknown unit: {unit}")


def parse_sensor_line(line):
    parts = line.split(':')
    if len(parts) < 2:
        return None  # Skip lines that don't contain a colon

    sensor_name = parts[0].strip()
    value_section = parts[1].strip()
    details = value_section.split('(')
    value_info = details[0].strip()
    range_info = details[1] if len(details) > 1 else None

    if sensor_name.lower() == "adapter":
        return None

    # Extract value and units
    value, unit = get_value_and_unit(value_info)

    # Initialize min and max
    min_val = None
    min_unit = None
    max_val = None
    max_unit = None
    crit_val = None
    crit_unit = None
    status = 'OK'

    # Extract range values if available
    if range_info:
        range_parts = range_info.replace(')', '').split(',')
        for part in range_parts:
            if 'min' in part:
                min_val, min_unit = get_value_and_unit(part)
            if 'max' in part or 'high' in part:
                max_val, max_unit = get_value_and_unit(part)
            if 'crit' in part:
                crit_val, crit_unit = get_value_and_unit(part)

        if unit != min_unit or unit != max_unit or unit != crit_unit:
            value, unit = convert_units(value, unit)
            min_val, min_unit = convert_units(min_val, min_unit)
            max_val, max_unit = convert_units(max_val, max_unit)
            crit_val, crit_unit = convert_units(crit_val, crit_unit)

        if min_val is None:
            min_val = 0  # default for mb and cpu

        if min_val and value < min_val:
            status = 'Too low'
        if max_val and value > max_val:
            status = 'Too high'
        if crit_val and value > crit_val:
            status = 'Critical!'

    return {
        'sensor': sensor_name,
        'value': value,
        'unit': unit,
        'min': min_val,
        'max': max_val,
        'crit': crit_val,
        'status': status
    }


def process_sensors_output(output, ignore_devices=None):
    results = []
    for line in output.split('\n'):
        parsed_line = parse_sensor_line(line)
        if parsed_line is None:
            continue
        if ignore_devices is None or parsed_line['sensor'] not in ignore_devices:
            results.append(parsed_line)
    return results


def send_message(telegram_api, chat_id, message_text):
    telegrame.send_message(telegram_api, chat_id, message_text)


def get_sensors_data(output_all, ignore_devices=None):
    sensor_data = Console.get_output("sensors")
    results = process_sensors_output(sensor_data, ignore_devices)

    output = []

    for result in results:
        message = (f"{result['sensor']}: "
                   f"{result['value']}{result['unit']} "
                   f"(Min: {result['min']}, "
                   f"Max: {result['max']}) "
                   f"- {result['status']}")
        if output_all or not result['status'].lower() == "ok":
            output.append(message)
        else:
            pass

    return newline.join(output)


def parse_hard_drive_line(line):
    parts = line.split(':')
    disk_device = parts[0].strip()
    disk_name = parts[1].strip()
    disk_info = parts[2].strip()

    # Extract the temperature value
    temp_value = Str.get_integers(disk_info)[0]

    # Initialize min and max
    min_val = 5
    max_val = 55
    status = 'OK'

    # Check if the current value is within the range
    if (temp_value < min_val) or (temp_value > max_val):
        status = 'Out of range'

    return {"disk_name": disk_name,
            "disk_device": disk_device,
            "temp_value": temp_value,
            "min_val": min_val,
            "max_val": max_val,
            "status": status}


def analyse_hard_drives(hard_drives, output_all=False, ignore_devices=None):
    """
    Analyse the output of the `hddtemp /dev/disk_name` command for each disk.

    Returns:
    A list of strings, where each string is the analysis of the output of the `hddtemp /dev/disk_name` command.
    """
    results = []
    for hard_drive in Str.nl(hard_drives.strip()):
        disk_info = parse_hard_drive_line(hard_drive)

        disk_name = disk_info["disk_name"]
        disk_device = disk_info["disk_device"]
        temp_value = disk_info["temp_value"]
        min_val = disk_info["min_val"]
        max_val = disk_info["max_val"]
        status = disk_info["status"]

        # Check if the current value is within the range
        if temp_value < min_val:
            status = 'Too low'
        if temp_value > max_val:
            status = 'Too high'

        if output_all or not status.lower() == "ok" and (ignore_devices is None or disk_name not in ignore_devices):
            results.append(f"{disk_name} ({disk_device}): {temp_value}°C (Min: {min_val}, Max: {max_val}) - {status}")
        else:
            pass

    return newline.join(results)


def failed_systemd_services(ignore_services=None):
    services = Console.get_output("systemctl", "list-units", "--state=failed", "--no-legend", "--plain").strip()
    output = ""
    for service in Str.nl(services):
        service_name = service.split()[0]
        if ignore_services is None or service_name not in ignore_services:
            output += f"{service}\n"
    return output


def _start_bot_receiver():
    @TELEGRAM_API.message_handler(content_types=["text", 'sticker'])
    def reply_all_messages(message):
        TELEGRAM_API.forward_message(MY_CHAT_ID, message.chat.id, message.message_id,
                                     disable_notification=True)
        Print.rewrite()
        print(f"from {message.chat.id}: {message.text}")

    TELEGRAM_API.polling(none_stop=True)


def _start_bot_sender():
    while True:
        now_dt = datetime.datetime.now()

        sensors = get_sensors_data(OUTPUT_ALL_SENSORS, IGNORED_SENSORS)

        disks = get_list_of_disks()
        hard_drives_temps = get_drive_temps(disks)
        hard_drives_info = analyse_hard_drives(hard_drives_temps, OUTPUT_ALL_SENSORS, IGNORED_HARD_DRIVES_TEMPERATURE)

        failed_systemd = failed_systemd_services(IGNORED_SYSTEMD_SERVICES)

        failed_systemd = newline + failed_systemd if failed_systemd else ""
        hard_drives_info = newline + hard_drives_info if hard_drives_info else ""
        sensors = newline + sensors if sensors else ""

        if sensors or hard_drives_info or failed_systemd:
            message_text = f"{now_dt}\n{sensors}{hard_drives_info}{failed_systemd}"
            print(message_text)
            send_message(TELEGRAM_API, MY_CHAT_ID, message_text)
        else:
            print(str(datetime.datetime.now()) + " nothing abnormal.")
        Time.sleep(300)


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
