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

    os.system("pip install pytelegrambotapi")
    import telebot
import time
import telegrame

__version__ = "0.10.18"

my_chat_id = 5328715
ola_chat_id = 550959211
tgx_chat_id = 619037205

encrypted_telegram_token_taskplayer = [-14, -18, -50, -16, -61, -56, -42, 1, -21, -13, -40, -6, -40, -27, -26, 39, -16,
                                       50, 12, 50, -21, -58, -17, 36, 29, -14, -60, 41, -27, -56, -7, 58, 41, 31, -56,
                                       33, -12, 12, -19, 48, 42, 4, 8, 47, -34]


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

telegram_token = Str.decrypt(encrypted_telegram_token_taskplayer, password)

telegram_api = telebot.TeleBot(telegram_token, threaded=False)


class State:
    def __init__(self):
        self.task_dict = JsonDict(Path.combine('.', "configs", "TaskPlayer.json"))
        if len(self.task_dict) == 0:
            self.task_dict["Work"] = 1800
            self.task_dict["Home"] = 1800
        self.current_task_name = None
        self.current_task_timer = Bench(quiet=True)
        self.current_task_time = 0

        self.pause_task_timer = Bench(quiet=True)
        self.pause_task_timer_time = 0
        self.pause_task_timer_started = False

        self.current_task_id = ID()
        self.current_task_started = False
        self.current_task_message_id = 0

        self.last_sent_mins = 0
        self.last_sent_secs = 0

        self.force_resend_message = False
        self.last_message_obj = None

    def set_task_by_int(self, integer):
        try:
            task = list(self.task_dict.items())[integer]
        except IndexError:
            return False
        self.current_task_name = task[0]
        self.current_task_time = task[1]
        self.current_task_timer.start()
        State.current_task_started = False
        return True

    def reset_timer(self):
        self.current_task_timer.start()

    def set_first_task(self):
        self.current_task_id.__init__()
        assert self.current_task_id.get() == 0
        self.set_task_by_int(0)
        self.pause_task_timer_started = False
        self.pause_task_timer_time = 0


    def set_next_task(self):
        next_task_int = self.current_task_id.get()
        if not self.set_task_by_int(next_task_int):
            self.set_first_task()
        self.pause_task_timer_started = False
        self.pause_task_timer_time = 0
        self.start_pause()

    def start_task(self):
        self.reset_timer()
        self.pause_task_timer_started = False

    def set_dict(self, dict_):
        self.task_dict.string = dict_
        self.task_dict.save()
        self.set_first_task()
        self.pause_task_timer_started = False

    def start_pause(self):
        self.pause_task_timer.start()
        self.pause_task_timer_started = True
        self.force_resend_message = True

    def resume_pause(self):
        self.pause_task_timer_time += self.pause_task_timer.get()
        self.pause_task_timer.start()
        self.pause_task_timer_started = False
        self.force_resend_message = True

    def get_pause_timer(self):
        if not self.pause_task_timer_started:
            return self.pause_task_timer_time
        else:
            return self.pause_task_timer_time + self.pause_task_timer.get()


State = State()


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
                    reply += "To start next task enter '/start'" + newline
                    telegram_api.delete_message(my_chat_id, message.id)
                elif message.text.lower().startswith("dict "):
                    message.text = message.text[5:]
                    temp_dict = {}
                    try:
                        temp_dict = eval(message.text)
                    except (SyntaxError, TypeError, ValueError) as e:
                        print(e)
                        reply = f"Cannot change dict: {str(e)}"
                        telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                    if temp_dict:
                        if not Dict.isinstance_keys(temp_dict, str):
                            temp_dict = Dict.all_keys_lambda(temp_dict, str)
                        State.set_dict(temp_dict)
                    else:
                        reply = f"Cannot set empty {temp_dict} list, return to {State.task_dict}"
                        telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                elif message.text.lower() == "skip" \
                        or message.text.lower() == "/skip":
                    State.set_next_task()
                    telegram_api.delete_message(my_chat_id, message.id)
                elif message.text.lower() == "start" \
                        or message.text.lower() == "/start":
                    State.start_task()
                elif message.text.lower() == "pause" \
                        or message.text.lower() == "/pause":
                    State.start_pause()
                    telegram_api.delete_message(my_chat_id, message.id)
                elif message.text.lower() == "resume" \
                        or message.text.lower():
                    State.resume_pause()
                    telegram_api.delete_message(my_chat_id, message.id)
                else:
                    reply = "Unknown command, enter '/help'"
                    telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                    telegram_api.delete_message(my_chat_id, message.id)
            else:
                reply = "Stickers doesn't supported"
                telegrame.send_message(telegram_api, message.chat.id, reply, disable_notification=True)
                telegram_api.delete_message(my_chat_id, message.id)

        else:
            telegram_api.forward_message(my_chat_id, message.chat.id, message.message_id,
                                         disable_notification=True)
            Print.rewrite()
            print(f"from {message.chat.id}: {message.text}")

    telegram_api.polling(none_stop=True)


def _start_taskplayer_bot_sender():
    while True:
        time.sleep(0.5)

        time_passed = State.current_task_timer.get()
        time_paused = State.get_pause_timer()
        time_passed -= time_paused
        Print(f"{time_passed=:.2f} {time_paused=:.2f} {State.pause_task_timer_started=}")
        seconds_passed = int(time_passed / 1)
        minutes_passed = int(time_passed / 60)
        seconds_all = int(State.current_task_time / 1)
        minutes_all = int(State.current_task_time / 60)
        seconds_left = seconds_all - seconds_passed
        minutes_left = minutes_all - minutes_passed

        if time_passed > State.current_task_time:
            State.set_next_task()
            if State.current_task_message_id:
                telegram_api.delete_message(my_chat_id, State.current_task_message_id)
            State.current_task_started = False
            continue
        if State.current_task_time >= 60:  # minutes mode
            if not State.current_task_started:
                message_text = f"Task {State.current_task_name} started - {minutes_left} minutes"
                message_obj = send_message_with_saving(telegram_api, my_chat_id, message_text)[0]
                State.current_task_message_id = message_obj.message_id
                State.current_task_started = True
                State.last_sent_mins = minutes_passed
            elif minutes_passed != State.last_sent_mins:
                message_text = f"Current task is {State.current_task_name} {minutes_left} minutes left"
                telegram_api.edit_message_text(chat_id=my_chat_id, message_id=State.current_task_message_id,
                                               text=message_text)
                State.last_message_obj.text = message_text
                State.last_sent_mins = minutes_passed

        else:  # seconds mode
            if not State.current_task_started:
                message_text = f"Task {State.current_task_name} started - {seconds_left} seconds"
                message_obj = telegrame.send_message(telegram_api, my_chat_id, message_text)[0]
                State.current_task_message_id = message_obj.message_id
                State.current_task_started = True
                State.last_sent_secs = seconds_passed
            if seconds_passed != State.last_sent_secs:
                message_text = f"Current task is {State.current_task_name} {seconds_left} seconds left"
                telegram_api.edit_message_text(chat_id=my_chat_id, message_id=State.current_task_message_id,
                                               text=message_text)
                State.last_sent_secs = seconds_passed

        print(f"{State.force_resend_message=}")
        if State.force_resend_message:
            # message_obj = telegram_api.copy_message(my_chat_id, my_chat_id, State.current_task_message_id)
            print(f"{State.current_task_message_id=}")
            if State.current_task_message_id != 0:
                telegram_api.delete_message(my_chat_id, State.current_task_message_id)
            # print(f"{State.last_message_obj.text}")
            message_obj = telegrame.send_message(telegram_api, my_chat_id, State.last_message_obj.text
                                                 + (" - paused"
                                                    if State.pause_task_timer_started
                                                    else ""))[0]
            State.current_task_message_id = message_obj.message_id
            State.force_resend_message = False


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
