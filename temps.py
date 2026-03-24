#! python3
# -*- coding: utf-8 -*-
import datetime
import os
import time as time_module
from collections import defaultdict

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

__version__ = "0.2.5"

IGNORED_SENSORS = []
IGNORED_HARD_DRIVES_TEMPERATURE = []
IGNORED_SYSTEMD_SERVICES = []
OUTPUT_ALL_SENSORS = False
RUN_EVERY = 300

CPU_REPORT_SAMPLES = 100
CPU_REPORT_DELAY = 0.5
CPU_REPORT_THRESHOLD = 10.0
_last_cpu_report_date = None

TELEGRAM_API = telebot.TeleBot(TEMPS_TELEGRAM_TOKEN, threaded=False)

print_original = print

def print(*args, **kwargs):
    kwargs["flush"] = True
    print_original(*args, **kwargs)


def get_list_of_disks():
    return ['/dev/' + disk for disk in Dir.list_of_entries('/dev') if disk.startswith('sd') and len(disk) == 3]


def get_drive_temps(disks):
    """
    Get drive temperatures using smartctl.

    Returns:
    A string with one line per disk in the format:
    /dev/sdX: Model Name: 42°C
    """
    import subprocess
    outputs = []
    for disk in disks:
        try:
            result = subprocess.run(
                ["smartctl", "-A", "-i", disk],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout
            # Get model name
            model = "Unknown"
            for line in output.splitlines():
                if "Device Model" in line or "Product" in line:
                    model = line.split(":", 1)[1].strip()
                    break
            # Get temperature
            temp = None
            for line in output.splitlines():
                if "Temperature_Celsius" in line or "Airflow_Temp" in line:
                    parts = line.split()
                    temp = parts[9] if len(parts) >= 10 else None
                    break
            if temp is None:
                for line in output.splitlines():
                    if "Current Drive Temperature" in line:
                        temp_parts = line.split()
                        for i, p in enumerate(temp_parts):
                            if p == "C" and i > 0:
                                temp = temp_parts[i - 1]
                                break
            if temp is not None and temp != "0":
                outputs.append(f"{disk}: {model}: {temp}°C")
        except Exception:
            pass

    return "\n".join(outputs)


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
    if unit == "mW":
        return value / 1000, "W"
    if unit == "W":
        return value, unit
    raise ValueError(f"Unknown unit: {unit}")


def parse_sensor_line(line):
    parts = line.split(':')
    if len(parts) < 2:
        return None  # Skip lines that don't contain a colon

    if line.startswith("ERROR: Can't get value of subfeature"):
        return None

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
    # Format: /dev/sdX: Model Name: 42°C
    parts = line.split(':')
    disk_device = parts[0].strip()
    disk_name = parts[1].strip() if len(parts) > 1 else "Unknown"
    disk_info = parts[2].strip() if len(parts) > 2 else "0°C"

    # Initialize min and max
    min_val = 5
    max_val = 55
    status = 'OK'

    # Extract the temperature value
    temp_value = Str.get_integers(disk_info)[0]

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
    if not hard_drives.strip():
        return newline.join(results)
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


def get_systemctl_properties(status):
    active = ""
    triggered_by = None
    since = ""
    since_time = ""
    since_delta = None
    
    for line in Str.nl(status):
        if "Active: " in line:
            active = Str.substring(line, "Active: ", " ", safe = True)
            since = Str.substring(line, "since ", ";", safe = True) + "00"
        elif "TriggeredBy: " in line:
            triggered_by = Str.substring(line, "TriggeredBy: ", safe = True)
        elif line.strip() == "":
            break

    try:
        since_time = datetime.datetime.strptime(since, "%a %Y-%m-%d %H:%M:%S %z")
        since_delta = datetime.datetime.now(since_time.tzinfo) - since_time                                   
    except ValueError:
        pass

    return active, triggered_by, since, since_time, since_delta


def should_skip_service(active, triggered_by, since_delta, run_every):
    """
    Determine if a service should be skipped (not reported as problematic).

    Args:
        active: The active state of the service (e.g., "active", "inactive", "activating", "failed")
        triggered_by: The trigger unit if any (or None)
        since_delta: timedelta since the service entered current state (or None)
        run_every: The check interval in seconds

    Returns:
        True if the service should be skipped, False if it should be reported
    """
    # If active, skip - service is running fine
    if active == "active":
        return True

    # If it has a trigger and is inactive, skip - it's waiting for its trigger
    if triggered_by is not None and active == "inactive":
        return True

    # If it's activating for less than the loop time, skip - give it time to start
    if active == "activating" and since_delta is not None:
        if since_delta.total_seconds() <= run_every:
            return True

    return False


def failed_systemd_services(ignore_services=None):

    # plain failed
    services = Console.get_output("systemctl", "list-units", "--state=failed", "--no-legend", "--plain").strip()
    services += newline
    # auto restarting or stuck
    services += Console.get_output("systemctl", "list-units", "--state=activating", "--no-legend", "--plain").strip()
    # in /etc/systemd/system
    to_check = Dir.list_of_files("/etc/systemd/system")

    outputs = []

    for service in Str.nl(services):
        try:
            service_name = service.split()[0]
        except IndexError:
            continue
        if ignore_services is None or service_name not in ignore_services:
            to_check.append(service_name)

    for file in to_check:
        status = Console.get_output("systemctl", "status", "-l", file)
        
        active, triggered_by, since, since_time, since_delta = get_systemctl_properties(status)

        if should_skip_service(active, triggered_by, since_delta, RUN_EVERY):
            continue

        # debug
        output = f"{file=} {active=} {triggered_by=} {since_time=} {since_delta=}"

        output += newline
        output += status
        outputs.append(output)
    return outputs


def _cpu_get_cwd(pid):
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return "?"


def _cpu_sample_processes():
    import subprocess
    result = subprocess.run(
        ["ps", "-eo", "pid,%cpu,comm,args", "--no-headers"],
        capture_output=True, text=True
    )
    procs = []
    for line in result.stdout.strip().splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, cpu, name, cmd = parts[0], float(parts[1]), parts[2], parts[3]
        cwd = _cpu_get_cwd(pid)
        procs.append((pid, cpu, name, cmd, cwd))
    return procs


def get_cpu_report():
    global _last_cpu_report_date
    today = datetime.date.today()
    if _last_cpu_report_date == today:
        return None
    _last_cpu_report_date = today

    by_name = defaultdict(lambda: {"samples": 0, "total_cpu": 0.0, "max_cpu": 0.0, "pids": set()})
    by_cmd = defaultdict(lambda: {"samples": 0, "total_cpu": 0.0, "max_cpu": 0.0, "pids": set(), "cwds": set()})

    for i in range(CPU_REPORT_SAMPLES):
        for pid, cpu, name, cmd, cwd in _cpu_sample_processes():
            if cpu < CPU_REPORT_THRESHOLD:
                continue
            e = by_name[name]
            e["samples"] += 1
            e["total_cpu"] += cpu
            e["max_cpu"] = max(e["max_cpu"], cpu)
            e["pids"].add(pid)

            e = by_cmd[cmd]
            e["samples"] += 1
            e["total_cpu"] += cpu
            e["max_cpu"] = max(e["max_cpu"], cpu)
            e["pids"].add(pid)
            e["cwds"].add(cwd)
        time_module.sleep(CPU_REPORT_DELAY)

    report = []
    report.append(f"CPU Report — {CPU_REPORT_SAMPLES} samples, {CPU_REPORT_DELAY}s interval, threshold >= {CPU_REPORT_THRESHOLD}%")
    report.append("=" * 60)

    report.append("\nBy process name:\n")
    report.append(f"{'Name':<25} {'Seen':>5} {'Avg%':>6} {'Max%':>6} {'PIDs':>5}")
    report.append("-" * 55)
    for name, d in sorted(by_name.items(), key=lambda x: x[1]["total_cpu"], reverse=True):
        avg = d["total_cpu"] / d["samples"]
        report.append(f"{name:<25} {d['samples']:>5} {avg:>5.1f}% {d['max_cpu']:>5.1f}% {len(d['pids']):>5}")

    report.append("\nBy full command:\n")
    report.append(f"{'Seen':>5} {'Avg%':>6} {'Max%':>6} {'PIDs':>5}  Command")
    report.append("-" * 60)
    for cmd, d in sorted(by_cmd.items(), key=lambda x: x[1]["total_cpu"], reverse=True):
        avg = d["total_cpu"] / d["samples"]
        cmd_short = cmd if len(cmd) <= 120 else cmd[:117] + "..."
        cwds = ", ".join(sorted(d["cwds"]))
        report.append(f"{d['samples']:>5} {avg:>5.1f}% {d['max_cpu']:>5.1f}% {len(d['pids']):>5}  {cmd_short}")
        report.append(f"       cwd: {cwds}")

    return "\n".join(report)


def check_everything():
    hostname = OS.hostname
    now_dt = datetime.datetime.now()

    sensors = get_sensors_data(OUTPUT_ALL_SENSORS, IGNORED_SENSORS)

    disks = get_list_of_disks()
    hard_drives_temps = get_drive_temps(disks)
    hard_drives_info = analyse_hard_drives(hard_drives_temps, OUTPUT_ALL_SENSORS, IGNORED_HARD_DRIVES_TEMPERATURE)

    failed_systemd = failed_systemd_services(IGNORED_SYSTEMD_SERVICES)

    cpu_report = get_cpu_report()

    #failed_systemd = newline + failed_systemd if failed_systemd else ""
    #hard_drives_info = newline + hard_drives_info if hard_drives_info else ""
    #sensors = newline + sensors if sensors else ""

    if sensors or hard_drives_info or failed_systemd or cpu_report:
        outputs = [sensors, hard_drives_info] + failed_systemd + ([cpu_report] if cpu_report else [])

        for output in outputs:
            if not output.strip():
                continue
            message_text = f"{now_dt}\t{hostname}\n\n{output}"
            print(message_text)
            send_message(TELEGRAM_API, MY_CHAT_ID, message_text)
        #message_text = f"{now_dt}\n{sensors}{hard_drives_info}{failed_systemd}"
        #print(message_text)
        #send_message(TELEGRAM_API, MY_CHAT_ID, message_text)
    else:
        print(str(datetime.datetime.now()) + " nothing abnormal.")


def _start_bot_receiver():
    @TELEGRAM_API.message_handler(content_types=["text", 'sticker'])
    def reply_all_messages(message):
        TELEGRAM_API.forward_message(MY_CHAT_ID, message.chat.id, message.message_id,
                                     disable_notification=True)
        # Print.rewrite()
        print(f"from {message.chat.id}: {message.text}")

    TELEGRAM_API.polling(none_stop=True)


def _start_bot_sender():
    while True:
        check_everything()
        Time.sleep(RUN_EVERY)


def safe_threads_run():
    # https://www.tutorialspoint.com/python/python_multithreading.htm  # you can expand current implementation

    print(f"Main thread v{__version__} started")
    
    threads = Threading()

    if "--no-receive" not in OS.args:
        threads.add(telegrame.very_safe_start_bot, args=(_start_bot_receiver,))
    threads.add(telegrame.very_safe_start_bot, args=(_start_bot_sender,))

    threads.start(wait_for_keyboard_interrupt=True)

    # Print.rewrite()
    print("Main thread quited")


if __name__ == '__main__':
    if "--once" in OS.args:
        check_everything()
    else:
        safe_threads_run()
    
