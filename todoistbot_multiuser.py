#! python3
# -*- coding: utf-8 -*-
import os
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
from todoiste import Todoist
import telegrame

__version__ = "2.2.4"

# change version
if OS.hostname == "EGGG-HOST-2019":
    import re
    filepath = Path.safe__file__(__file__)
    content = File.read(filepath)
    lines = Str.nl(content)
    for cnt, line in enumerate(lines):
        if "__version__" in line:
            regexp = re.compile(r"(\d+)(?!.*\d)")
            last_ver = re.findall(r"(\d+)(?!.*\d)", line)
            replace = str(int(last_ver[0])+1)
            new = re.sub(r"(\d+)(?!.*\d)", replace, line)
            lines[cnt] = new
            break
    new_content = "\r\n".join(lines)
    File.write(filepath, new_content, mode="w")
# end changing version


class State:
    def __init__(self, chat_id):
        f = Path.safe__file__(os.path.split(__file__)[0])
        json_path = Path.combine(f, "configs", f"telegram_bot_todoist_{chat_id}.json")
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
                self.config_json[self.category][self.property] = self
                self.config_json.save()

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

        self.counter_for_remaining_items = True
        self.counter_for_remaining_items_int = 0

        self.counter_all_items = 0

        self.all_todo_str = ""
        self.last_todo_str = ""

        self.last_random_todo_str = "not inited"
        self.last_updated = 0

        self.all_items = []
        self.last_updated_all_items = 0
        self.all_items_updating = False

        self.todoist_api_key_password = None
        self.getting_api_key = False
        self.getting_api_key_password = False
        self.getting_api_reset_answer = False

        self.probably_last_good_password_message_id = None



class Users:
    def __init__(self):
        f = Path.safe__file__(os.path.split(__file__)[0])
        json_path = Path.combine(f, "configs", "telegram_bot_todoist_users_secrets.json")
        self.secrets = Json(json_path)

        self.todoist = {}  # place to store Todoist objects
        self.state = {}  # place to store State objects

    def get_todoist_api_key_encrypted(self, chat_id):
        try:
            return self.secrets[str(chat_id)]
        except KeyError:
            return False

    def delete_todoist_api_key_encrypted(self, chat_id):
        try:
            self.secrets.pop(str(chat_id))
        except KeyError:
            pass

    def get_todoist_api_key_password(self, chat_id):
        try:
            return int(self.secrets[f"{chat_id}_pass_message_id"])
        except (KeyError, ValueError):
            return False

    def set_todoist_api_key_password(self, chat_id, message_id):
        self.secrets[f"{chat_id}_pass_message_id"] = str(message_id)


Users = Users()


encrypted_telegram_token = [-12, -16, -48, -23, -54, -59, -41, -1, -17, -13, -40, -6, -39, -3, -17, 16, 29, 0, -39, 10,
                            -21, -29, 19, 23, -2, 16, -21, 13, -57, 9, -8, 25, -3, 48, -10, 42, -14, 0, -19, 25, 51, 9,
                            -24, 43, -26]  # production


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


def get_all_items(state: State, todoist_api: Todoist, auto_run: bool = False):
    timeout = 600 if auto_run else 60
    if not state.all_items or Time.delta(state.last_updated_all_items, Time.stamp()) > timeout:
        state.last_updated_all_items = Time.stamp()
        state.all_items = todoist_api.all_incomplete_items_in_account()

    if not auto_run and not state.all_items_updating:
        auto_update_thread = MyThread(get_all_items, args=(state, todoist_api, False), daemon=True)
        auto_update_thread.start()
        State.all_items_updating = True

    return state.all_items


def get_random_todo(state: State, todoist_api: Todoist, telegram_api: (telebot.TeleBot, None), chat_id: int, cnt: bool):
    Print.rewrite("Getting random todo")
    bench = Bench(prefix="Get random item in", quiet=True)
    bench.start()
    incomplete_items = get_all_items(state=state, todoist_api=todoist_api)
    # Print.debug(Print.prettify(incomplete_items, quiet=True))
    bench.end()

    counter_for_remaining_items_int = 0
    counter_all_items = 0
    all_todo_str = ""

    for project_name, project_items in Dict.iterable(incomplete_items.copy()):  # removing excluded
        counter_all_items += len(project_items)

        if project_name.strip() in state.excluded_projects:
            incomplete_items[project_name] = []
            continue
        if project_items:
            # print(f'"{project_name}"')
            all_todo_str += project_name + newline
        for item in project_items.copy():

            if item["content"].strip() in state.excluded_items:
                incomplete_items[project_name].remove(item)
                # print(f'    "{item["content"]}" excluded')
            else:
                counter_for_remaining_items_int += 1
                # print(f'    "{item["content"]}"')
                all_todo_str += "    " + item["content"] + newline

    for project_name, project_items in Dict.iterable(incomplete_items.copy()):  # removing empty projects
        if not project_items:
            incomplete_items.pop(project_name)

    #  Print.debug("counter_for_remaining_items_int", counter_for_remaining_items_int,
    #              "counter_all_items", counter_all_items)
    #              "all_todo_str", all_todo_str)
    state.counter_for_remaining_items_int = counter_for_remaining_items_int
    state.counter_all_items = counter_all_items
    state.all_todo_str = all_todo_str

    try:
        random_project_name, random_project_items = Random.item(incomplete_items)
    except IndexError:
        return "All done!"
    random_item = Random.item(random_project_items)

    time_string = ""
    try:
        if not random_item["due_date_utc"].endswith("20:59:59 +0000"):
            time_string = " " + random_item["date_string"]
    except KeyError:
        pass

    if state.counter_for_remaining_items and cnt:
        counter_for_remaining_items_str = f"({state.counter_for_remaining_items_int}/{state.counter_all_items} remaining)"
        telegrame.send_message(telegram_api, chat_id, f"{counter_for_remaining_items_str} v{__version__}")

    Print.rewrite()
    return f"{random_item['content']} <{random_project_name}>{time_string}".replace(
        ">  (", "> (")


def todo_updater(state: State, todoist_api: Todoist, telegram_api: telebot.TeleBot, chat_id, force: bool = True, cnt: bool = True):
    # if Time.delta(state.last_updated, Time.stamp()) < 3 and not force:
    #     Print("skip updating, thread already running")
    #     return
    state.last_random_todo_str = get_random_todo(state=state, todoist_api=todoist_api, telegram_api=telegram_api, chat_id=chat_id, cnt = cnt)
    state.last_updated = Time.stamp()
    if state.probably_last_good_password_message_id and state.probably_last_good_password_message_id != Users.get_todoist_api_key_password(chat_id):
        Users.set_todoist_api_key_password(chat_id, state.probably_last_good_password_message_id)


def main_message(state: State, telegram_api: telebot.TeleBot, todoist_api: (Todoist,None), chat_id):
    first_run = state.last_random_todo_str == "not inited"

    main_markup = telebot.types.ReplyKeyboardMarkup()
    main_button = telebot.types.KeyboardButton('MOAR!')
    settings_button = telebot.types.KeyboardButton('Settings')
    list_button = telebot.types.KeyboardButton('List')
    main_markup.row(main_button)
    main_markup.row(settings_button, list_button)
    main_markup.row()

    if state.excluded_projects:
        excluded_str = f"Excluded projects: {state.excluded_projects}."
    else:
        excluded_str = "No excluded projects."
    if state.excluded_items:
        excluded_str += f"{newline}Excluded items: {state.excluded_items}."
    else:
        excluded_str += f"{newline}No excluded items."

    if first_run:
        messages = telegrame.send_message(telegram_api, chat_id=chat_id, text="Please, wait...")
        todo_updater(state=state, todoist_api=todoist_api, telegram_api=telegram_api, chat_id=chat_id, cnt=False)
        for message in messages:
            telegrame.delete_message(telegram_api, chat_id, message.message_id)

    current_todo = state.last_random_todo_str
    telegrame.send_message(telegram_api, chat_id=chat_id,
                           #  text=f"{excluded_str}{newline}{current_todo}")  # , reply_markup=main_markup)
                           text=current_todo, reply_markup=main_markup)

    state.last_todo_str = Str.substring(current_todo, "", "<", safe=True).strip()
    todo_updater_thread = MyThread(todo_updater, args=(state, todoist_api, telegram_api, chat_id, first_run),
                                   daemon=True, quiet=False)
    todo_updater_thread.start()


def check_connection_verbose(todoist_api: Todoist, telegram_api: telebot.TeleBot, chat_id):
    try:
        if todoist_api.is_synced():
            return todoist_api
    except AttributeError:
        pass
    markup = telebot.types.ReplyKeyboardMarkup()
    key_button = telebot.types.KeyboardButton('Reset API key and password')
    password_button = telebot.types.KeyboardButton('Reset password for API key')
    markup.row(key_button)
    markup.row(password_button)

    telegram_api.send_message(chat_id, f"Cannot sync with Todoist.\n"
                                       f"Do you want to change Todoist API key or password?", reply_markup=markup)


def start_todoist_bot(none_stop=True):
    telegram_api = telebot.TeleBot(telegram_token, threaded=False)

    @telegram_api.message_handler(content_types=["text"])
    def reply_all_messages(message):
        # init vars
        chat_id = message.chat.id
        message_id = message.message_id

        # check State object
        if chat_id not in Users.state:
            Users.state[chat_id] = State(chat_id)
        CurrentState = Users.state[chat_id]

        if message.text == "Reset API key and password":
            print("yeah")
            # reset state
            CurrentState.__init__(chat_id)
            # delete api key
            Users.delete_todoist_api_key_encrypted(chat_id)
            # delete todoist obj
            Users.todoist.pop(chat_id, None)
            # get new todoist api key and password
            telegram_api.send_message(chat_id, "API key and password reset, send new Todoist API password")
            CurrentState.getting_api_key_password = True
            return
        elif message.text == "Reset password for API key":
            # reset password
            CurrentState.__init__(chat_id)
            # delete todoist obj
            Users.todoist.pop(chat_id, None)
            # get new api password
            telegram_api.send_message(chat_id, "API password key reset, send new password")
            CurrentState.getting_api_key_password = True
            return

        # getting init input
        if CurrentState.getting_api_key_password:
            CurrentState.todoist_api_key_password = message.text
            CurrentState.getting_api_key_password = False
            CurrentState.probably_last_good_password_message_id = message_id

        if CurrentState.getting_api_key:
            api_key_encrypted = Str.encrypt(message.text.strip(), CurrentState.todoist_api_key_password)
            Users.secrets[chat_id] = api_key_encrypted
            CurrentState.getting_api_key = False

        if CurrentState.getting_api_reset_answer:
            if message.text == "Yes":
                Users.secrets.pop(chat_id, None)
                Users.todoist.pop(chat_id, None)
            CurrentState.getting_api_key_password = False

        # check Todoist object
        if chat_id not in Users.todoist:
            if not CurrentState.todoist_api_key_password:
                telegram_api.send_message(chat_id, "Please, enter password to encrypt Todoist API Key.\n"
                                                   "For security reasons, I will not write it to disk, "
                                                   "so after each update you need to re-send it.")
                if Users.get_todoist_api_key_password(chat_id):
                    try:
                        telegram_api.forward_message(chat_id, chat_id, Users.get_todoist_api_key_password(chat_id))
                    except Exception as e:
                        print(e)
                CurrentState.getting_api_key_password = True
                return
            if not Users.get_todoist_api_key_encrypted(chat_id):
                telegram_api.send_message(chat_id, "Please, enter API key for Todoist. It will be encrypted.")
                CurrentState.getting_api_key = True
                return
            try:
                decrypted_api_key = Str.decrypt(Users.get_todoist_api_key_encrypted(chat_id), CurrentState.todoist_api_key_password)
            except ValueError:
                telegram_api.send_message(chat_id, "Wrong password. Password reset.\n"
                                                   "Enter password:")
                CurrentState.todoist_api_key_password = None
                Users.todoist.pop(chat_id, None)
                CurrentState.getting_api_key_password = True
                return
            Users.todoist[chat_id] = CurrentTodoistApi = check_connection_verbose(Todoist(decrypted_api_key), telegram_api, chat_id)
            if CurrentTodoistApi:
                main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
            return

        # check Todoist connection
        CurrentTodoistApi = check_connection_verbose(Users.todoist[chat_id], telegram_api, chat_id)
        if not CurrentTodoistApi:
            return

        # main
        if CurrentState.getting_project_name:
            if message.text == "Cancel":
                pass
            else:
                message_text = message.text.strip()
                if message_text in CurrentState.excluded_projects:
                    CurrentState.excluded_projects.remove(message_text)
                else:
                    CurrentState.excluded_projects.append(message_text)
            CurrentState.getting_project_name = False
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif CurrentState.getting_item_name:
            if message.text == "Cancel":
                pass
            else:
                message_text = message.text.strip()
                if message_text in CurrentState.excluded_items:
                    CurrentState.excluded_items.remove(message_text)
                else:
                    CurrentState.excluded_items.append(message_text)
            CurrentState.getting_item_name = False
            CurrentState._message = True
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)

        elif message.text == "MOAR!":  # MAIN MESSAGE
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == "List":
            if not CurrentState.all_todo_str:
                get_random_todo(state=CurrentState, todoist_api=CurrentTodoistApi, telegram_api=None, chat_id=None)
            if CurrentState.all_todo_str:
                telegrame.send_message(telegram_api, message.chat.id, CurrentState.all_todo_str)
            else:
                telegrame.send_message(telegram_api, message.chat.id, "Todo list for today is empty!")
        elif message.text == "Settings":
            markup = telebot.types.ReplyKeyboardMarkup()
            project_exclude_button = telebot.types.KeyboardButton("Exclude project")
            project_include_button = telebot.types.KeyboardButton("Include project")

            items_exclude_button = telebot.types.KeyboardButton("Exclude items")
            items_include_button = telebot.types.KeyboardButton("Include items")

            clean_excluded_list_button = telebot.types.KeyboardButton("Clean excluded list")
            counter_for_remaining_items_button = telebot.types.KeyboardButton("Toggle remaining items counter")

            reset_api_key_button = telebot.types.KeyboardButton("Reset API key and password")
            reset_api_key_password_button = telebot.types.KeyboardButton("Reset password for API key")

            markup.row(project_exclude_button, project_include_button)
            markup.row(items_exclude_button, items_include_button)
            markup.row(clean_excluded_list_button)
            markup.row(counter_for_remaining_items_button)
            markup.row(reset_api_key_button, reset_api_key_password_button)

            telegrame.send_message(telegram_api, message.chat.id, "Settings:", reply_markup=markup)
        elif message.text == "Exclude project":
            markup = telebot.types.ReplyKeyboardMarkup()
            for project_name, project_id in Dict.iterable(CurrentTodoistApi.projects_all_names()):
                if project_name not in CurrentState.excluded_projects:
                    project_button = telebot.types.KeyboardButton(project_name)
                    markup.row(project_button)

            cancel_button = telebot.types.KeyboardButton("Cancel")
            markup.row(cancel_button)

            telegrame.send_message(telegram_api, message.chat.id, "Send me project name to exclude:", reply_markup=markup)

            CurrentState.getting_project_name = True
        elif message.text == "Include project":
            if CurrentState.excluded_projects:
                markup = telebot.types.ReplyKeyboardMarkup()
                for project_name in CurrentState.excluded_projects:
                    project_button = telebot.types.KeyboardButton(project_name)
                    markup.row(project_button)

                cancel_button = telebot.types.KeyboardButton("Cancel")
                markup.row(cancel_button)

                telegrame.send_message(telegram_api, message.chat.id, "Send me project name to include:", reply_markup=markup)

                CurrentState.getting_project_name = True
            else:
                telegrame.send_message(telegram_api, message.chat.id, "No excluded projects, skip...")
                main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == "Exclude items":
            # main_markup = telebot.types.ForceReply(selective=False) it doesn't show up default keyboard :(

            markup = telebot.types.ReplyKeyboardMarkup()
            default_items = False
            default_items_list = [r"Vacuum/sweep", "Wash the floor"]
            if CurrentState.last_todo_str:
                default_items_list.append(CurrentState.last_todo_str)
            for item_name in default_items_list:
                if item_name not in CurrentState.excluded_items:
                    project_button = telebot.types.KeyboardButton(item_name)
                    markup.row(project_button)
                    default_items = True

            if not default_items:
                project_button = telebot.types.KeyboardButton("Enter item manually")
                markup.row(project_button)

            cancel_button = telebot.types.KeyboardButton("Cancel")
            markup.row(cancel_button)

            telegrame.send_message(telegram_api, message.chat.id, "Send me item name:", reply_markup=markup)

            CurrentState.getting_item_name = True
        elif message.text == "Include items":
            if CurrentState.excluded_items:
                markup = telebot.types.ReplyKeyboardMarkup()
                for item_name in CurrentState.excluded_items:
                    project_button = telebot.types.KeyboardButton(item_name)
                    markup.row(project_button)

                cancel_button = telebot.types.KeyboardButton("Cancel")
                markup.row(cancel_button)

                telegrame.send_message(telegram_api, message.chat.id, "Send me item name:", reply_markup=markup)

                CurrentState.getting_item_name = True
            else:
                telegrame.send_message(telegram_api, message.chat.id, "No excluded items, skip...")
                main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == "Clean excluded list":
            CurrentState.excluded_items.purge()
            CurrentState.excluded_projects.purge()
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == "Toggle remaining items counter":
            CurrentState.counter_for_remaining_items = not CurrentState.counter_for_remaining_items
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        else:
            telegrame.send_message(telegram_api, message.chat.id, f"Unknown command '{message.text}'.\n"
            f"Please, enter one of commands: \n"
            f"'MOAR!' - next random command\n"
            f"'List' - list of all tasks\n"
            f"'Settings' - for change settings\n"
            f"'Include\Exclude project\items' to include or exclude tasks\n"
            f"'Clean excluded list' to include all tasks\n"
            f"'Toggle remaining items counter' to enable or disable sending counter of remaining items\n"
            f"'Reset API key and password' - change bot API key and password for it for Todoist"
            f"'Reset password for API key' - change password to decrypt API key for Todoist (API key stays encrypted, change only if you entered wrong password)")
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)

    telegram_api.polling(none_stop=none_stop)
    # https://github.com/eternnoir/pyTelegramBotAPI/issues/273


def main():
    start_todoist_bot(none_stop=False)
    telegrame.very_safe_start_bot(start_todoist_bot)


if __name__ == '__main__':
    main()
