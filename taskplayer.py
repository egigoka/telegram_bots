#! python3
# -*- coding: utf-8 -*-
import datetime
import sys
import traceback

try:
    from commands import *
except ImportError:
    import os

    os.system("pip install git+https://github.com/egigoka/commands")
    from commands import *
try:
    import telebot
except ImportError:
    import os
    
    os.system("pip install pytelegrambotapi")
    import telebot
import time
import telegrame
from secrets import TASKPLAYER_TELEGRAM_TOKEN

__version__ = "0.13.0"

my_chat_id = 5328715

encrypted_telegram_token_taskplayer = [-14, -18, -50, -16, -61, -56, -42, 1, -21, -13, -40, -6, -40, -27, -26, 39, -16,
                                       50, 12, 50, -21, -58, -17, 36, 29, -14, -60, 41, -27, -56, -7, 58, 41, 31, -56,
                                       33, -12, 12, -19, 48, 42, 4, 8, 47, -34]

telegram_token = TASKPLAYER_TELEGRAM_TOKEN

telegram_api = telebot.TeleBot(telegram_token, threaded=False)


class State:
    def __init__(self):
        self.state_json = JsonDict(Path.combine(".", "configs", "TaskPlayer_state.json"))
        self.task_dict = JsonDict(Path.combine('.', "configs", "TaskPlayer.json"))
        if len(self.task_dict) == 0:
            self.task_dict["Work"] = 1800
            self.task_dict["Home"] = 1800

        self.current_task_timer = Bench(verbose=False)
        self.pause_task_timer = Bench(verbose=False)
        self.current_task_id = ID()
        self.last_message_obj = None

        self.current_task_name = None
        self.current_task_time = 0
        self.pause_task_timer_time = 0
        self.pause_task_timer_started = False

        self.current_task_started = False
        self.current_task_message_id = 0
        self.previous_task_message_id = 0

        self.last_sent_mins = 0
        self.last_sent_secs = 0

        self.force_resend_message = False

        self.load_state()

    def __setitem__(self, key, value):
        if value is None:
            value = "None"
        if isinstance(value, str):
            value = '"""' + value + '"""'
        exec(f"self.{key} = {value}")

    def __getitem__(self, item):
        return eval(f"self.{item}")

    def load_state(self):
        for key, value in self.state_json.items():
            if key in ["current_task_timer.time_start",
                       "current_task_timer.time_end",
                       "pause_task_timer.time_start",
                       "pause_task_timer.time_end"]:
                try:
                    value = Time.timestamp_to_datetime(value)
                except TypeError:
                    pass
            if key == "current_task_timer.time_start":
                self.current_task_timer.time_start = value
            elif key == "current_task_timer.time_end":
                self.current_task_timer.time_end = value
            elif key == "pause_task_timer.time_start":
                self.pause_task_timer.time_start = value
            elif key == "pause_task_timer.time_end":
                self.pause_task_timer.time_end = value
            else:
                self[key] = value

    def save_state(self):
        for key in "current_task_name,current_task_time," \
                   "pause_task_timer_time,pause_task_timer_started," \
                   "current_task_started,current_task_message_id," \
                   "previous_task_message_id,last_sent_mins," \
                   "last_sent_secs,force_resend_message" \
                   "".split(","):
            self.state_json[key] = self[key]

        if self.current_task_timer.time_start is None:
            self.state_json["current_task_timer.time_start"] = None
        else:
            self.state_json["current_task_timer.time_start"] = \
                Time.datetime_to_timestamp(self.current_task_timer.time_start)
        if self.current_task_timer.time_end is None:
            self.state_json["current_task_timer.time_end"] = None
        else:
            self.state_json["current_task_timer.time_end"] = \
                Time.datetime_to_timestamp(self.current_task_timer.time_end)
        if self.pause_task_timer is None:
            self.state_json["pause_task_timer.time_start"] = None
        else:
            self.state_json["pause_task_timer.time_start"] = \
                Time.datetime_to_timestamp(self.pause_task_timer.time_start)
        if self.pause_task_timer.time_end is None:
            self.state_json["pause_task_timer.time_end"] = None
        else:
            self.state_json["pause_task_timer.time_end"] = \
                Time.datetime_to_timestamp(self.pause_task_timer.time_end)
        self.state_json.save()

    def set_task_by_int(self, integer):
        try:
            task = list(self.task_dict.items())[integer]
        except IndexError:
            return False
        self.current_task_name = task[0]
        self.current_task_time = task[1]
        self.current_task_timer.start()
        self.current_task_started = False
        self.save_state()
        return True

    def reset_timer(self):
        self.current_task_timer.start()
        self.pause_task_timer.start()
        self.save_state()

    def set_first_task(self):
        self.current_task_id.__init__()
        assert self.current_task_id.get() == 0
        self.set_task_by_int(0)
        self.pause_task_timer_started = False
        self.pause_task_timer_time = 0
        self.save_state()

    def set_next_task(self):
        next_task_int = self.current_task_id.get()
        if not self.set_task_by_int(next_task_int):
            self.set_first_task()
        self.pause_task_timer_started = False
        self.pause_task_timer_time = 0
        self.start_pause()
        self.save_state()

    def start_task(self):
        self.reset_timer()
        self.pause_task_timer_started = False
        self.save_state()

    def set_dict(self, dict_):
        self.task_dict.string = dict_
        self.task_dict.save()
        self.set_first_task()
        self.pause_task_timer_started = False
        self.save_state()

    def start_pause(self):
        self.pause_task_timer.start()
        self.pause_task_timer_started = True
        self.force_resend_message = True
        self.save_state()

    def resume_pause(self):
        self.pause_task_timer_time += self.pause_task_timer.get()
        self.pause_task_timer.start()
        self.pause_task_timer_started = False
        self.force_resend_message = True
        self.save_state()

    def get_pause_timer(self):
        if not self.pause_task_timer_started:
            return self.pause_task_timer_time
        else:
            return self.pause_task_timer_time + self.pause_task_timer.get()


State = State()

main_markup = telebot.types.ReplyKeyboardMarkup()
main_button = telebot.types.KeyboardButton('Resume')
settings_button = telebot.types.KeyboardButton('Pause')
list_button = telebot.types.KeyboardButton('Help')
skip_button = telebot.types.KeyboardButton('Skip')
main_markup.row(main_button)
main_markup.row(settings_button, list_button, skip_button)
main_markup.row()


def send_message_with_saving(*args, **kwargs):
    message_obj = telegrame.send_message(*args, **kwargs)
    State.last_message_obj = message_obj[0]
    return message_obj


def _start_task_player_bot_receiver():
    @telegram_api.message_handler(content_types=["text", 'sticker'])
    def reply_all_messages(message):

        if message.chat.id == my_chat_id:
            if message.text:
                print(fr"input: {message.text}")
                if message.text.lower().startswith("help") \
                        or message.text.lower().startswith("/help"):
                    reply = "To set todos enter python dict with format like 'dict {'task1': 1800, 'task2': 3600}'" \
                            + newline
                    reply += "To skip task, enter '/skip'" + newline
                    reply += "To start task enter '/resume'" + newline
                    reply += "To pause task enter '/pause'" + newline
                    buttons = ["", "", "", ""]
                    try:
                        telegram_api.delete_message(my_chat_id, message.id)
                        print(f"1 deleted received {my_chat_id=} {message.id} {message.text}")
                    except Exception:
                        pass
                    telegrame.send_message(telegram_api, my_chat_id, reply, reply_markup=main_markup)
                    print(f"2 sent {my_chat_id=} {reply=} {main_markup=}")
                elif message.text.lower().startswith("dict "):
                    message.text = message.text[5:]
                    temp_dict = {}
                    try:
                        temp_dict = eval(message.text)
                    except (SyntaxError, TypeError, ValueError) as e:
                        print(e)
                        stacktrace = traceback.format_exc()
                        reply = f"Cannot change dict: {str(e)}{newline}{str(stacktrace)}"
                        telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                        print(f"3 sent {message.chat.id=} {reply=} {True}")
                    if temp_dict:
                        if not Dict.isinstance_keys(temp_dict, str):
                            temp_dict = Dict.all_keys_lambda(temp_dict, str)
                        State.set_dict(temp_dict)
                    else:
                        reply = f"Cannot set empty {temp_dict} list, return to {State.task_dict}"
                        telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                        print(f"4 sent {message.chat.id=} reply={reply} {True}")
                elif message.text.lower() == "skip" \
                        or message.text.lower() == "/skip":
                    State.set_next_task()
                    try:
                        telegram_api.delete_message(my_chat_id, message.id)
                        print(f"5 deleted {my_chat_id=} {message.id=} {message.text=}")
                    except Exception:
                        pass
                elif message.text.lower() == "/start":
                    State.start_task()
                elif message.text.lower() == "pause" \
                        or message.text.lower() == "/pause":
                    State.start_pause()
                    try:
                        telegram_api.delete_message(my_chat_id, message.id)
                        print(f"6 deleted {my_chat_id=} {message.id=} {message.text=}")
                    except Exception:
                        pass
                elif message.text.lower() == "resume" \
                        or message.text.lower() == "/resume":
                    State.resume_pause()
                    try:
                        telegram_api.delete_message(my_chat_id, message.id)
                        print(f"7 deleted {my_chat_id=} {message.id=} {message.text=}")
                    except Exception:
                        pass
                else:
                    reply = "Unknown command, enter '/help'"
                    telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                    print(f"8 sent {message.chat.id} {reply=} {True=}")
                    try:
                        telegram_api.delete_message(my_chat_id, message.id)
                        print(f"9 deleted {my_chat_id} {message.id} {message.text}")
                    except Exception:
                        pass
            else:
                reply = "Stickers doesn't supported"
                telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                print(f"10 sent {message.chat.id=} {reply=} {True=}")
                try:
                    telegram_api.delete_message(my_chat_id, message.id)
                    print(f"11 deleted {my_chat_id=} {message.id=} {message.text=}")
                except Exception:
                    pass

        else:
            telegram_api.forward_message(my_chat_id, message.chat.id, message.message_id,
                                         disable_notification=True)
            print(f"12 forwarded {my_chat_id=} {message.chat.id=} {message.message_id=} {True=}")
            Print.rewrite()
            print(f"from {message.chat.id}: {message.text}")

    telegram_api.polling(none_stop=True)


def _start_taskplayer_bot_sender():
    while True:
        # print(f"{State.current_task_message_id=}")
        # print(f"{State.previous_task_message_id=}")

        time.sleep(0.5)

        time_passed = State.current_task_timer.get()
        time_paused = State.get_pause_timer()
        time_passed -= time_paused
        # Print(f"{time_passed=:.2f} {time_paused=:.2f} {State.pause_task_timer_started=}")
        seconds_passed = int(time_passed / 1)
        minutes_passed = int(time_passed / 60)
        seconds_all = int(State.current_task_time / 1)
        minutes_all = int(State.current_task_time / 60)
        seconds_left = seconds_all - seconds_passed
        minutes_left = minutes_all - minutes_passed

        if time_passed > State.current_task_time:
            State.set_next_task()
            if State.current_task_message_id:
                try:
                    telegram_api.delete_message(my_chat_id, State.current_task_message_id)
                    print(f"13 deleted {my_chat_id=} {State.current_task_message_id=}")
                except Exception:
                    pass
                State.current_task_started = 0
            if State.previous_task_message_id:
                try:
                    telegram_api.delete_message(my_chat_id, State.previous_task_message_id)
                    print(f"14 deleted {my_chat_id=} {State.current_task_message_id=}")
                except Exception:
                    pass
                State.previous_task_message_id = 0
            State.current_task_started = False
            continue
        if State.current_task_time >= 60:  # minutes mode
            if not State.current_task_started:
                message_text = f"Task {State.current_task_name} started - {minutes_left} minutes"
                message_obj = send_message_with_saving(telegram_api, my_chat_id, message_text)[0]
                print(f"15 sent {my_chat_id=} {message_text=}")
                State.current_task_message_id = message_obj.message_id
                State.current_task_started = True
                State.last_sent_mins = minutes_passed
            elif minutes_passed != State.last_sent_mins:
                message_text = f"Current task is {State.current_task_name} {minutes_left} minutes left"
                try:
                    telegram_api.edit_message_text(chat_id=my_chat_id, message_id=State.current_task_message_id,
                                                   text=message_text)
                    print(f"16 edited {my_chat_id=} {State.current_task_message_id=} {message_text=}")
                except Exception:
                    pass
                try:
                    State.last_message_obj.text = message_text
                except Exception:
                    pass
                State.last_sent_mins = minutes_passed

        else:  # seconds mode
            if not State.current_task_started:
                message_text = f"Task {State.current_task_name} started - {seconds_left} seconds"
                message_obj = send_message_with_saving(telegram_api, my_chat_id, message_text)[0]
                print(f"17 sent {my_chat_id=} {message_text=}")
                State.current_task_message_id = message_obj.message_id
                State.current_task_started = True
                State.last_sent_secs = seconds_passed
            if seconds_passed != State.last_sent_secs:
                message_text = f"Current task is {State.current_task_name} {seconds_left} seconds left"
                try:
                    telegram_api.edit_message_text(chat_id=my_chat_id, message_id=State.current_task_message_id,
                                                   text=message_text)
                    print(f"18 modified {my_chat_id=}{State.current_task_message_id=}{message_text=}")
                except Exception:
                    pass
                State.last_sent_secs = seconds_passed

        # print(f"{State.force_resend_message=}")
        if State.force_resend_message:
            # message_obj = telegram_api.copy_message(my_chat_id, my_chat_id, State.current_task_message_id)
            # print(f"{State.current_task_message_id=}")
            if State.current_task_message_id != 0:
                try:
                    telegram_api.delete_message(my_chat_id, State.current_task_message_id)
                    print(f"19 deleted {my_chat_id=} {State.current_task_message_id=}")
                except Exception:
                    pass
                State.current_task_message_id = 0
            if State.previous_task_message_id != 0:
                try:
                    telegram_api.delete_message(my_chat_id, State.previous_task_message_id)
                    print(f"20 deleted {my_chat_id=} {State.previous_task_message_id=}")
                except Exception:
                    pass
                State.previous_task_message_id = 0
            # print(f"{State.last_message_obj.text}")
            # if State.last_message_obj is not None:
            last_message_text = State.last_message_obj.text if State.last_message_obj is not None else ""
            print(f"{State.last_message_obj=}")
            message_text = last_message_text + (" - paused"
                                                if State.pause_task_timer_started
                                                else "")
            message_obj = telegrame.send_message(telegram_api, my_chat_id, message_text)[0]
            print(f"21 sent {my_chat_id=} {message_text=}")
            # State.previous_task_message_id = State.current_task_message_id
            State.current_task_message_id = message_obj.message_id
            State.force_resend_message = False
        State.save_state()
        # print()


def safe_threads_run():
    # https://www.tutorialspoint.com/python/python_multithreading.htm  # you can expand current implementation

    print(f"Main thread v{__version__} started")

    threads = Threading()

    debug = False
    if debug:
        threads.add(_start_taskplayer_bot_sender, name="Sender")
        threads.add(_start_task_player_bot_receiver, name="Receiver")
    else:
        threads.add(telegrame.very_safe_start_bot, args=(_start_task_player_bot_receiver,), name="Receiver")
        threads.add(telegrame.very_safe_start_bot, args=(_start_taskplayer_bot_sender,), name="Sender")

    threads.start(wait_for_keyboard_interrupt=True)

    Print.rewrite()
    print("Main thread quited")


if __name__ == '__main__':
    safe_threads_run()
