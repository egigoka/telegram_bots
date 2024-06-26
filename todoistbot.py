#! python3
# -*- coding: utf-8 -*-
import os
try:
    from commands import Path
except ImportError:
    import os
    os.system("pip install git+https://github.com/egigoka/commands")
    from commands import Path
try:
    import telebot
except ImportError:
    from commands.pip9 import Pip
    Pip.install("pytelegrambotapi")
    import telebot
from todoiste import *
import telegrame

__version__ = "1.8.1"

my_chat_id = 5328715
ola_chat_id = 550959211
tgx_chat_id = 619037205


class Arguments:
    pass


class State:
    def __init__(self):
        f = Path.safe__file__(os.path.split(__file__)[0])
        json_path = Path.combine(f, "configs", "telegram_bot_todoist.json")
        self.config_json = Json(json_path)

        self.getting_project_name = False
        self.getting_item_name = False

        class JsonList(list):
            def __init__(self, list_input, category, property):
                list.__init__(self, list_input)
                self.category = category
                self.property = property

            def append(self, obj):
                out = list.append(self, obj)
                self.save()
                return out

            def remove(self, obj):
                out = list.remove(self, obj)
                self.save()
                return out

            def save(self):
                State.config_json[self.category][self.property] = self
                State.config_json.save()

            def purge(self):
                while self:
                    self.pop()
                self.save()

        try:
            self.excluded_projects = JsonList(self.config_json["excluded"]["projects"], "excluded", "projects")
        except KeyError:
            self.excluded_projects = JsonList([], "excluded", "projects")
        try:
            self.excluded_items = JsonList(self.config_json["excluded"]["items"], "excluded", "items")
        except KeyError:
            self.excluded_items = JsonList([], "excluded", "items")

        self.counter_for_left_items = True
        self.counter_for_left_items_int = 0

        self.counter_all_items = 0

        self.all_todo_str = ""
        self.last_todo_str = ""

        self.sent_messages = 1

        self.last_radnom_todo_str = "not inited"
        self.last_updated = 0




State = State()


encrypted_telegram_token = [-15, -21, -49, -16, -63, -52, -46, 6, -20, -13, -40, -6, -39, -33, 22, 0, 1, 51, 9, -26,
                            -41, -24, 13, 4, 49, 44, -25, 18, 9, -18, -19, 72, -12, -26, -3, 3, -62, 3, 17, 4, 7, -3,
                            -33, -3, -12]

encrypted_todoist_token = [-20, -20, -50, -14, -61, -54, 2, 0, 32, 27, -51, -21, -54, -53, 4, 3, 29, -14, -51, 29, -10,
                           -6, 1, 4, 28, 29, -55, -17, -59, -9, 2, 50, -13, -14, -52, -15, -56, -59, -44, 5]

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
todoist_api_key = Str.decrypt(encrypted_todoist_token, password)


def get_random_todo(todo_api, telegram_api, chat_id):
    Print.rewrite("Getting random todo")
    bench = Bench(prefix="Get random item in", quiet=True)
    bench.start()
    incomplete_items = todo_api.all_incomplete_items_in_account()
    # Print.debug(Print.prettify(incomplete_items, quiet=True))
    bench.end()

    counter_for_left_items_int = 0
    counter_all_items = 0
    all_todo_str = ""

    for project_name, project_items in Dict.iterable(incomplete_items.copy()):  # removing excluded
        counter_all_items += len(project_items)

        if project_name.strip() in State.excluded_projects:
            incomplete_items[project_name] = []
            continue
        if project_items:
            # print(f'"{project_name}"')
            all_todo_str += project_name + newline
        for item in project_items.copy():

            if item["content"].strip() in State.excluded_items:
                incomplete_items[project_name].remove(item)
                # print(f'    "{item["content"]}" excluded')
            else:
                counter_for_left_items_int += 1
                # print(f'    "{item["content"]}"')
                all_todo_str += "    " + item["content"] + newline

    for project_name, project_items in Dict.iterable(incomplete_items.copy()):  # removing empty projects
        if not project_items:
            incomplete_items.pop(project_name)

    #  Print.debug("counter_for_left_items_int", counter_for_left_items_int,
    #              "counter_all_items", counter_all_items)
    #              "all_todo_str", all_todo_str)
    State.counter_for_left_items_int = counter_for_left_items_int
    State.counter_all_items = counter_all_items
    State.all_todo_str = all_todo_str

    try:
        random_project_name, random_project_items = Random.item(incomplete_items)
    except IndexError:
        return "All done!"
    random_item = Random.item(random_project_items)

    try:
        if not random_item["due_date_utc"].endswith("20:59:59 +0000"):
            time_string = " " + random_item["date_string"]
        else:
            time_string = ""
    except KeyError:
        time_string = ""

    if State.counter_for_left_items and telegram_api and chat_id:
        counter_for_left_items_str = f"({State.counter_for_left_items_int}/{State.counter_all_items} left)"
        telegrame.send_message(telegram_api, chat_id, f"{counter_for_left_items_str} v{__version__}")

    Print.rewrite()
    return f"{random_item['content']} <{random_project_name}>{time_string}".replace(
        ">  (", "> (")


def todo_updater(todo_api, telegram_api, chat_id):
    if Time.delta(State.last_updated, Time.stamp()) < 3:
        Print("skip updating, thread already running")
        return
    State.last_radnom_todo_str = get_random_todo(todo_api=todo_api, telegram_api=telegram_api, chat_id=chat_id)
    State.last_updated = Time.stamp()


def start_todoist_bot():
    todoist_api = Todoist(todoist_api_key)
    telegram_api = telebot.TeleBot(telegram_token, threaded=False)

    todo_updater(todoist_api, None, None)  # initing for fist message, no chat_id

    @telegram_api.message_handler(content_types=["text"])
    def reply_all_messages(message):

        def main_message():
            State.sent_messages = 1

            main_markup = telebot.types.ReplyKeyboardMarkup()
            main_button = telebot.types.KeyboardButton('MOAR!')
            settings_button = telebot.types.KeyboardButton('Settings')
            list_button = telebot.types.KeyboardButton('List')
            main_markup.row(main_button)
            main_markup.row(settings_button, list_button)

            if State.excluded_projects:
                excluded_str = f"Excluded projects: {State.excluded_projects}."
            else:
                excluded_str = "No excluded projects."
            if State.excluded_items:
                excluded_str += f"{newline}Excluded items: {State.excluded_items}."
            else:
                excluded_str += f"{newline}No excluded items."

            current_todo = State.last_radnom_todo_str
            telegrame.send_message(telegram_api, chat_id=message.chat.id,
                                   #  text=f"{excluded_str}{newline}{current_todo}")  # , reply_markup=main_markup)
                                   text=current_todo, reply_markup=main_markup)

            State.last_todo_str = Str.substring(current_todo, "", "<").strip()
            todo_updater_thread = MyThread(todo_updater, args=(todoist_api, telegram_api, message.chat.id), daemon=True, quiet=False)
            todo_updater_thread.start()

        if message.chat.id != my_chat_id:
            telegrame.send_message(telegram_api, message.chat.id, "ACCESS DENY!")
            return

        if State.getting_project_name:
            if message.text == "Cancel":
                pass
            else:
                message_text = message.text.strip()
                if message_text in State.excluded_projects:
                    State.excluded_projects.remove(message_text)
                else:
                    State.excluded_projects.append(message_text)
            State.getting_project_name = False
            main_message()

        elif State.getting_item_name:
            if message.text == "Cancel":
                pass
            else:
                message_text = message.text.strip()
                if message_text in State.excluded_items:
                    State.excluded_items.remove(message_text)
                else:
                    State.excluded_items.append(message_text)
            State.getting_item_name = False
            State._message = True
            main_message()

        elif message.text == "MOAR!":  # MAIN MESSAGE
            main_message()

        elif message.text == "List":
            if not State.all_todo_str:
                get_random_todo(todoist_api, None, None)
            if State.all_todo_str:
                telegrame.send_message(telegram_api, message.chat.id, State.all_todo_str)
            else:
                telegrame.send_message(telegram_api, message.chat.id, "Todo list for today is empty!")

        elif message.text == "Settings":
            markup = telebot.types.ReplyKeyboardMarkup()
            project_exclude_button = telebot.types.KeyboardButton("Exclude project")
            project_include_button = telebot.types.KeyboardButton("Include project")

            items_exclude_button = telebot.types.KeyboardButton("Exclude items")
            items_include_button = telebot.types.KeyboardButton("Include items")

            clean_black_list_button = telebot.types.KeyboardButton("Clean black list")
            counter_for_left_items_button = telebot.types.KeyboardButton("Toggle left items counter")

            markup.row(project_exclude_button, project_include_button)
            markup.row(items_exclude_button, items_include_button)
            markup.row(clean_black_list_button)
            markup.row(counter_for_left_items_button)

            telegrame.send_message(telegram_api, message.chat.id, "Settings:", reply_markup=markup)

        elif message.text == "Exclude project":
            markup = telebot.types.ReplyKeyboardMarkup()
            for project_name, project_id in Dict.iterable(todoist_api.projects_all_names()):
                if project_name not in State.excluded_projects:
                    project_button = telebot.types.KeyboardButton(project_name)
                    markup.row(project_button)

            cancel_button = telebot.types.KeyboardButton("Cancel")
            markup.row(cancel_button)

            telegrame.send_message(telegram_api, message.chat.id, "Send me project name to exclude:", reply_markup=markup)

            State.getting_project_name = True

        elif message.text == "Include project":
            if State.excluded_projects:
                markup = telebot.types.ReplyKeyboardMarkup()
                for project_name in State.excluded_projects:
                    project_button = telebot.types.KeyboardButton(project_name)
                    markup.row(project_button)

                cancel_button = telebot.types.KeyboardButton("Cancel")
                markup.row(cancel_button)

                telegrame.send_message(telegram_api, message.chat.id, "Send me project name to include:", reply_markup=markup)

                State.getting_project_name = True
            else:
                telegrame.send_message(telegram_api, message.chat.id, "No excluded projects, skip...")
                main_message()

        elif message.text == "Exclude items":
            # main_markup = telebot.types.ForceReply(selective=False) it doesn't show up default keyboard :(

            markup = telebot.types.ReplyKeyboardMarkup()
            default_items = False
            default_items_list = [r"Vacuum/sweep", "Wash the floor"]
            if State.last_todo_str:
                default_items_list.append(State.last_todo_str)
            for item_name in default_items_list:
                if item_name not in State.excluded_items:
                    project_button = telebot.types.KeyboardButton(item_name)
                    markup.row(project_button)
                    default_items = True

            if not default_items:
                project_button = telebot.types.KeyboardButton("Enter item manually")
                markup.row(project_button)

            cancel_button = telebot.types.KeyboardButton("Cancel")
            markup.row(cancel_button)

            telegrame.send_message(telegram_api, message.chat.id, "Send me item name:", reply_markup=markup)

            State.getting_item_name = True

        elif message.text == "Include items":
            if State.excluded_items:
                markup = telebot.types.ReplyKeyboardMarkup()
                for item_name in State.excluded_items:
                    project_button = telebot.types.KeyboardButton(item_name)
                    markup.row(project_button)

                cancel_button = telebot.types.KeyboardButton("Cancel")
                markup.row(cancel_button)

                telegrame.send_message(telegram_api, message.chat.id, "Send me item name:", reply_markup=markup)

                State.getting_item_name = True
            else:
                telegrame.send_message(telegram_api, message.chat.id, "No excluded items, skip...")
                main_message()

        elif message.text == "Clean black list":
            State.excluded_items.purge()
            State.excluded_projects.purge()
            main_message()

        elif message.text == "Toggle left items counter":
            if State.counter_for_left_items:
                State.counter_for_left_items = False
            else:
                State.counter_for_left_items = True
            main_message()

        else:
            telegrame.send_message(telegram_api, message.chat.id, f"ERROR! <{message.text}>")
            State.sent_messages += 1
            main_message()

    telegram_api.polling(none_stop=True)
    # https://github.com/eternnoir/pyTelegramBotAPI/issues/273


def main():
    telegrame.very_safe_start_bot(start_todoist_bot)


if __name__ == '__main__':
    main()
