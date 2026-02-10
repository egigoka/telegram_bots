#! python3
# -*- coding: utf-8 -*-
import os
import sys
import time
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

__version__ = "2.6.5"

my_chat_id = 5328715

class State:
    def __init__(self, chat_id):
        f = Path.safe__file__(os.path.split(__file__)[0])
        json_path = Path.combine(f, "configs", f"telegram_bot_todoist_{chat_id}.json")
        self.config_json = JsonDict(json_path)

        self.getting_project_name = False
        self.getting_item_name = False

        class JsonList(list):
            def __init__(self, list_input, category, property, json_object):
                list.__init__(self, list_input)
                self.category = category
                self.property = property
                self.json_object = json_object

            def append(self, obj):
                out = list.append(self, obj)
                self.save()
                return out

            def remove(self, obj):
                out = list.remove(self, obj)
                self.save()
                return out

            def save(self):
                self.json_object[self.category] = {}
                self.json_object[self.category][self.property] = self
                self.json_object.save()

            def purge(self):
                while self:
                    self.pop()
                self.save()

        try:
            self.excluded_projects = JsonList(self.config_json["excluded"]["projects"], "excluded", "projects", self.config_json)
        except KeyError:
            self.excluded_projects = JsonList([], "excluded", "projects", self.config_json)
        try:
            self.excluded_items = JsonList(self.config_json["excluded"]["items"], "excluded", "items", self.config_json)
        except KeyError:
            self.excluded_items = JsonList([], "excluded", "items", self.config_json)

        try:
            self.emoji = self.config_json["emoji"]
        except:
            self.config_json["emoji"] = self.emoji = False

        try:
            self.counter_for_remaining_items = self.config_json["remaining cnt"]
        except:
            self.config_json["remaining cnt"] = self.counter_for_remaining_items = True

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

        class TextEmoji:
            reset_api_key_and_password = "🚮Reset API key and password🚮"
            reset_password_for_api_key = "🖌Reset password for API key🖌"
            cancel = "✖️Cancel✖️"
            toggle_remaining_items_counter = "ℹ️Toggle remaining items counterℹ️"
            clean_excluded_list = "🆓Clean excluded list🆓"
            exclude_project = "❌Exclude project❌"
            include_project = "✅Include project✅"
            exclude_items = "❌Exclude items❌"
            include_items = "✅Include items✅"
            disable_emoji = "Disable Emoji"
            enable_emoji = "😎Enable Emoji😎"

        class TextNoEmoji:
            reset_api_key_and_password = "Reset API key and password"
            reset_password_for_api_key = "Reset password for API key"
            cancel = "Cancel"
            toggle_remaining_items_counter = "Toggle remaining items counter"
            clean_excluded_list = "Clean excluded list"
            exclude_project = "Exclude project"
            include_project = "Include project"
            exclude_items = "Exclude items"
            include_items = "Include items"
            disable_emoji = "Disable Emoji"
            enable_emoji = "😎Enable Emoji😎"

        self.TextEmoji = TextEmoji
        self.TextNoEmoji = TextNoEmoji
        if self.emoji:
            self.Text = TextEmoji
        self.Text = TextNoEmoji


class Users:
    def __init__(self):
        f = Path.safe__file__(os.path.split(__file__)[0])
        json_path = Path.combine(f, "configs", "telegram_bot_todoist_users_secrets.json")
        self.secrets = JsonDict(json_path)

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


def update_all_items_daemon(state: State, todoist_api: Todoist):
    while True:
        time.sleep(600)
        get_all_items(state=state, todoist_api=todoist_api)


def get_all_items(state: State, todoist_api: Todoist):
    timeout = 60
    if not state.all_items or Time.delta(state.last_updated_all_items, Time.stamp()) > timeout:
        state.last_updated_all_items = Time.stamp()
        state.all_items = todoist_api.all_incomplete_items_in_account()

    if not state.all_items_updating:
        state.all_items_updating = True
        auto_update_thread = MyThread(update_all_items_daemon,
                                      kwargs={"state": state, "todoist_api": todoist_api},
                                      daemon=True, quiet=False)
        auto_update_thread.start()

    return state.all_items


def get_random_todo(state: State, todoist_api: Todoist, telegram_api: (telebot.TeleBot, None), chat_id: int, cnt: bool):
    Print.rewrite("Getting random todo")
    bench = Bench(prefix="Get random item in", verbose=False)
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
    telegrame.send_message(telegram_api, chat_id=chat_id, disable_web_page_preview=True,
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
        try:
            print(chat_id, message_id, message.text)
        except:
            print(chat_id, message_id)


        # check State object
        if chat_id not in Users.state:
            Users.state[chat_id] = State(chat_id)
        CurrentState = Users.state[chat_id]

        if message.text == CurrentState.Text.reset_api_key_and_password:
            # reset state
            CurrentState.__init__(chat_id)
            # delete api key
            Users.delete_todoist_api_key_encrypted(chat_id)
            # delete todoist obj
            Users.todoist.pop(chat_id, None)
            # get new todoist api key and password
            telegram_api.send_message(chat_id, "API key and password reset, send new Todoist API password:")
            CurrentState.getting_api_key_password = True
            return
        elif message.text == CurrentState.Text.reset_password_for_api_key:
            # reset password
            CurrentState.__init__(chat_id)
            # delete todoist obj
            Users.todoist.pop(chat_id, None)
            # get new api password
            telegram_api.send_message(chat_id, "API password key reset, send correct password:")
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
                                                   "For security reasons, I will not write it to disk.")
                if Users.get_todoist_api_key_password(chat_id):
                    try:
                        telegram_api.send_message(chat_id, "Probably, message with last correct password:")
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
        if message.text.startswith("[to all]") and chat_id == my_chat_id:
            f = Path.safe__file__(__file__)
            workdir = Path.combine(os.path.split(f)[0], "configs")
            for file in Dir.list_of_files(workdir):
                if file.startswith("telegram_bot_todoist_"):
                    try:
                        to_chat_id = Str.get_integers(file)[0]
                        telegram_api.forward_message(to_chat_id, chat_id, message_id)
                    except IndexError:
                        pass
        elif CurrentState.getting_project_name:
            if message.text == CurrentState.Text.cancel:
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
            if message.text == CurrentState.Text.cancel:
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
                telegrame.send_message(telegram_api, message.chat.id, CurrentState.all_todo_str, disable_web_page_preview=True)
            else:
                telegrame.send_message(telegram_api, message.chat.id, "Todo list for today is empty!")
        elif message.text == "Settings":
            markup = telebot.types.ReplyKeyboardMarkup()
            project_exclude_button = telebot.types.KeyboardButton(CurrentState.Text.exclude_project)
            project_include_button = telebot.types.KeyboardButton(CurrentState.Text.include_project)

            items_exclude_button = telebot.types.KeyboardButton(CurrentState.Text.exclude_items)
            items_include_button = telebot.types.KeyboardButton(CurrentState.Text.include_items)

            clean_excluded_list_button = telebot.types.KeyboardButton(CurrentState.Text.clean_excluded_list)
            counter_for_remaining_items_button = telebot.types.KeyboardButton(CurrentState.Text.toggle_remaining_items_counter)

            cancel_button = telebot.types.KeyboardButton(CurrentState.Text.cancel)

            reset_api_key_button = telebot.types.KeyboardButton(CurrentState.Text.reset_api_key_and_password)
            reset_api_key_password_button = telebot.types.KeyboardButton(CurrentState.Text.reset_password_for_api_key)

            disable_emoji_button = telebot.types.KeyboardButton(CurrentState.Text.disable_emoji)
            enable_emoji_button = telebot.types.KeyboardButton(CurrentState.Text.enable_emoji)

            markup.row(project_exclude_button, project_include_button)
            markup.row(items_exclude_button, items_include_button)
            markup.row(clean_excluded_list_button, counter_for_remaining_items_button)
            markup.row(cancel_button)
            markup.row(reset_api_key_button, reset_api_key_password_button)
            markup.row(disable_emoji_button, enable_emoji_button)

            telegrame.send_message(telegram_api, message.chat.id, "Settings:", reply_markup=markup)
        elif message.text == CurrentState.Text.exclude_project:
            markup = telebot.types.ReplyKeyboardMarkup()
            for project_name, project_id in Dict.iterable(CurrentTodoistApi.projects_all_names()):
                if project_name not in CurrentState.excluded_projects:
                    project_button = telebot.types.KeyboardButton(project_name)
                    markup.row(project_button)

            cancel_button = telebot.types.KeyboardButton(CurrentState.Text.cancel)
            markup.row(cancel_button)

            telegrame.send_message(telegram_api, message.chat.id, "Send me project name to exclude:", reply_markup=markup)

            CurrentState.getting_project_name = True
        elif message.text == CurrentState.Text.include_project:
            if CurrentState.excluded_projects:
                markup = telebot.types.ReplyKeyboardMarkup()
                for project_name in CurrentState.excluded_projects:
                    project_button = telebot.types.KeyboardButton(project_name)
                    markup.row(project_button)

                cancel_button = telebot.types.KeyboardButton(CurrentState.Text.cancel)
                markup.row(cancel_button)

                telegrame.send_message(telegram_api, message.chat.id, "Send me project name to include:", reply_markup=markup)

                CurrentState.getting_project_name = True
            else:
                telegrame.send_message(telegram_api, message.chat.id, "No excluded projects, skip...")
                main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == CurrentState.Text.exclude_items:
            # main_markup = telebot.types.ForceReply(selective=False) it doesn't show up default keyboard :(

            markup = telebot.types.ReplyKeyboardMarkup()
            default_items = False
            default_items_list = [r"Vacuum/sweep", "Wash the floor"]
            if CurrentState.last_todo_str and CurrentState.last_todo_str not in default_items_list:
                default_items_list.append(CurrentState.last_todo_str)
            for item_name in default_items_list:
                if item_name not in CurrentState.excluded_items:
                    project_button = telebot.types.KeyboardButton(item_name)
                    markup.row(project_button)
                    default_items = True

            if not default_items:
                project_button = telebot.types.KeyboardButton("Enter item manually")
                markup.row(project_button)

            cancel_button = telebot.types.KeyboardButton(CurrentState.Text.cancel)
            markup.row(cancel_button)

            telegrame.send_message(telegram_api, message.chat.id, "Send me item name:", reply_markup=markup)

            CurrentState.getting_item_name = True
        elif message.text == CurrentState.Text.include_items:
            if CurrentState.excluded_items:
                markup = telebot.types.ReplyKeyboardMarkup()
                for item_name in CurrentState.excluded_items:
                    project_button = telebot.types.KeyboardButton(item_name)
                    markup.row(project_button)

                cancel_button = telebot.types.KeyboardButton(CurrentState.Text.cancel)
                markup.row(cancel_button)

                telegrame.send_message(telegram_api, message.chat.id, "Send me item name:", reply_markup=markup)

                CurrentState.getting_item_name = True
            else:
                telegrame.send_message(telegram_api, message.chat.id, "No excluded items, skip...")
                main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == CurrentState.Text.clean_excluded_list:
            CurrentState.excluded_items.purge()
            CurrentState.excluded_projects.purge()
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == CurrentState.Text.toggle_remaining_items_counter:
            CurrentState.counter_for_remaining_items = not CurrentState.counter_for_remaining_items
            CurrentState.config_json["remaining_cnt"] = CurrentState.counter_for_remaining_items
            CurrentState.config_json.save()
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == CurrentState.Text.cancel:
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == CurrentState.Text.enable_emoji:
            CurrentState.Text = CurrentState.TextEmoji
            CurrentState.config_json["emoji"] = True
            CurrentState.config_json.save()
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == CurrentState.Text.disable_emoji:
            CurrentState.Text = CurrentState.TextNoEmoji
            CurrentState.config_json["emoji"] = False
            CurrentState.config_json.save()
            main_message(state=CurrentState, telegram_api=telegram_api, todoist_api=CurrentTodoistApi, chat_id=chat_id)
        elif message.text == "69":
            gifs = ['https://media3.giphy.com/media/VTnKWKVuExtYc/giphy.gif',
                    'https://media1.tenor.com/images/87433eeab910a8467cb23253fbed51ac/tenor.gif?itemid=4571547',
                    'https://i.makeagif.com/media/2-22-2015/3wrPKL.gif',
                    'https://thumbs.gfycat.com/ComplexUnsteadyChinesecrocodilelizard-size_restricted.gif',
                    'https://i.kym-cdn.com/photos/images/original/000/967/326/252.gif',
                    'https://thumbs.gfycat.com/GratefulBriefIberianbarbel-size_restricted.gif',
                    'https://media1.tenor.com/images/3738b88b7d2883f046c7f7cf1cf44d12/tenor.gif?itemid=5963604',
                    'http://www.gifimagesdownload.com/wp-content/uploads/2016/02/free-noice-gif-666-1.gif',
                    'https://media.giphy.com/media/3oEdv6KUnfOnIDmUcU/giphy.gif',
                    'https://i.makeagif.com/media/3-17-2015/h1Qm8Z.gif',
                    'http://www.gifimagesdownload.com/wp-content/uploads/2016/02/cool-noice-gif-484-1.gif',
                    'https://thumbs.gfycat.com/TemptingGaseousGarpike-size_restricted.gif',
                    'https://i.imgflip.com/k8p3a.gif',
                    'http://i.cubeupload.com/2lXIYI.gif',
                    'https://i.kym-cdn.com/photos/images/list/000/922/397/e39.gif',
                    'http://68.media.tumblr.com/18c85a433e657241db5e6fe44f16aac9/tumblr_inline_njzowqhntg1sqilv2.gif',
                    'https://media.giphy.com/media/yJFeycRK2DB4c/giphy.gif',
                    'https://thumbs.gfycat.com/AnimatedPoorDuckbillcat-max-1mb.gif',
                    'https://memebomb.net/wp-content/uploads/2019/03/nice-memes-sandboarding-.gif',
                    'https://thumbs.gfycat.com/BareRealLarva-small.gif',
                    'https://i.gifer.com/Es2m.gif',
                    'https://media3.giphy.com/media/gRRy5PkDTK4OQ/giphy.gif',
                    'https://i.ytimg.com/vi/a8c5wmeOL9o/maxresdefault.jpg',
                    'https://orig00.deviantart.net/d03f/f/2015/349/e/6/noice__model__michael_rosen_edition__by_doctoroctoroc-d9k8m6z.gif',
                    'http://33.media.tumblr.com/9550a2974ba353be964add2a6ce66504/tumblr_inline_njzoy7yiKJ1sqilv2.gif',
                    'https://cdn.dopl3r.com/memes_files/noice-intensifies-M6GmQ.jpg',
                    'https://gifimage.net/wp-content/uploads/2017/10/michael-rosen-nice-gif-8.gif',
                    'https://media.tenor.com/images/d8a67b9408c210c7e93923c5e5baca05/tenor.gif'
                    ]
            random_gif = Random.item(gifs)
            texts = ["Nice!", "Noice!", "It's time to stop!", "Catch them all!1", "Do you find _that_ one?",
                     "Yeah!", "Nice", "NiCe!", "Nooice", "Pluck!", "Noiice"]
            random_text = Random.item(texts)
            try:
                if random_gif.endswith(".jpg"):
                    telegram_api.send_photo(chat_id, random_gif, caption=random_text)
                else:
                    telegram_api.send_video(chat_id, random_gif, caption=random_text)
            except Exception as e:
                print(e)
                telegram_api.send_message(chat_id, "No gif for you! (just kidding, try again)")
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
    telegrame.very_safe_start_bot(start_todoist_bot)


if __name__ == '__main__':
    main()
