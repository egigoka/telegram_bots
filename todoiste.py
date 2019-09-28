#! python3
# -*- coding: utf-8 -*-
import string
import sys
import time
import datetime

__version__ = "1.0.3"

try:
    from commands import *
    from commands.id9 import ID

    id = ID()
except ImportError:
    import os

    os.system("pip install git+https://github.com/egigoka/commands")
try:
    import todoist
except ImportError:
    from commands.pip9 import Pip

    Pip.install("todoist-python")
    import todoist
try:
    import pytz
except ImportError:
    from commands.pip9 import Pip

    Pip.install("pytz")
    import pytz
try:
    import tzlocal
except ImportError:
    from commands.pip9 import Pip

    Pip.install("tzlocal")
    import tzlocal


class Arguments:
    apikey = False
    if "apikey" in sys.argv:
        apikey = True

    cleanup = False
    if "cleanup" in sys.argv:
        cleanup = True

    test = False
    if "test" in sys.argv:
        test = True

    work = False
    if "work" in sys.argv:
        work = True

    list = False
    if "list" in sys.argv:
        list = True

    listnogreen = False
    if "listnogreen" in sys.argv:
        listnogreen = True

    name = False
    if "name" in sys.argv:
        name = True

    random = False
    if "random" in sys.argv:
        random = True

    loop = False
    if "loop" in sys.argv:
        loop = True


class State:
    debug = False
    debug_not_today = False
    showed_random_items = []
    loop_input = ""
    random_bench = Bench(prefix="<task> done in", fraction_digits=0)


class Priority:
    USUAL = 1
    HIGH = 2
    VERY_HIGH = 3
    EXTREMELY = 4


class Todoist:

    def __init__(self, api_key):
        Print.rewrite("Loading cache...")
        self.api = todoist.TodoistAPI(api_key)
        Print.rewrite("Syncing...")
        try:
            self.api.sync()
        except OSError:
            pass
        Print.rewrite("Synced")

    def is_synced(self):
        return bool(self.api.user.get('email'))  # get this method from todoist.api.__repr__

    def projects_all_names(self):
        names = {}
        for project in self.api.projects.all():
            names[project["name"]] = project["id"]
        return names

    def project_exists(self, name):
        all_projects = self.projects_all_names()
        if name in all_projects:
            return all_projects[name]
        return False

    def get_temp_project(self, prefix="Temp"):
        project_name = None
        cnt = 0
        while not project_name:
            cnt += 1
            temp_name = f"{prefix}_{cnt}"
            if not self.project_exists(temp_name):
                project_name = temp_name
        new_project = self.api.projects.add(project_name)
        return new_project

    def project_raw_items(self, name):
        project_id = self.project_exists(name)
        if not project_id:
            raise KeyError(f"Project {name} doesn't exist!")
        project_data = self.api.projects.get_data(project_id)
        try:
            items = project_data["items"]
        except TypeError:  # why? wtf?
            items = project_data
        if items:
            return items
        return []


    def project_items_names(self, name):
        raw = self.project_raw_items(name)
        items = {}
        for item in raw:
            items[item["content"]] = item["id"]
        return items

    def project_cnt_items(self, project_name):
        cnt_all_tasks = 0
        items = self.project_raw_items(project_name)
        for item in items:
            cnt_all_tasks += 1
        return cnt_all_tasks

    def cnt_all_items_in_account(self):
        cnt_all_tasks = 0
        for project_name, project_id in Dict.iterable(self.projects_all_names()):
            cnt_all_tasks += self.project_cnt_items(project_name)
        return cnt_all_tasks

    def project_cnt_incomplete_items(self, project_name):
        cnt_incomplete_tasks = 0
        items = self.project_raw_items(project_name)
        for item in items:
            status = self.item_status(item)
            if status in ["today", "overdue"]:
                cnt_incomplete_tasks += 1
        return cnt_incomplete_tasks

    def cnt_incompleted_items_in_account(self):
        cnt_incomplete_tasks = 0
        for project_name, project_id in Dict.iterable(self.projects_all_names()):
            cnt_incomplete_tasks += self.project_cnt_incomplete_items(project_name)
        return cnt_incomplete_tasks

    def project_raw_incomplete_items(self, project_name):
        items = self.project_raw_items(project_name)
        incomplete_items = []
        for item in items:
            status = self.item_status(item)
            if status in ["today", "overdue"]:
                incomplete_items.append(item)
        return incomplete_items

    def all_incomplete_items_in_account(self):
        incomplete_items = {}
        for project_name, project_id in Dict.iterable(self.projects_all_names()):
            incomplete_items[project_name] = self.project_raw_incomplete_items(project_name)
        return incomplete_items

    def create_project(self, name):
        project_id = self.project_exists(name)
        if not project_id:
            print(f"Creating project {name}")
            project = self.api.projects.add(name)
            self.api.commit()
            self.api.sync()
            project_id = self.project_exists(name)
        return project_id

    def add_item(self, name, project_name, item_order, day_order, priority=Priority.USUAL, date_string=None,
                 due_date_utc=None, auto_create_project=False):
        project_id = self.project_exists(project_name)
        if auto_create_project:
            project_id = self.create_project(project_name)
        else:
            raise KeyError(f"Project {project_name} doesn't exist")
        if date_string and due_date_utc:
            raise KeyError(f"only date_string {date_string} or due_date_utc {due_date_utc}")
        elif date_string:
            item = self.api.items.add(name, project_id, item_order=item_order, date_string=date_string,
                                      day_order=day_order, priority=priority)
        elif due_date_utc:
            item = self.api.items.add(name, project_id, item_order=item_order, due_date_utc=due_date_utc,
                                      day_order=day_order, priority=priority)
        else:
            item = self.api.items.add(name, project_id, item_order=item_order, day_order=day_order, priority=priority)
        return item

    def date_string_today(self):
        return datetime.datetime.now().strftime("%d %b %Y")

    def try_todoist_time_to_datetime_datetime(self, time_string, format):
        try:
            return datetime.datetime.strptime(time_string, format)
        except ValueError:
            return

    def todoist_time_to_datetime_datetime(self, time_string):
        formats = ["%a %d %b %Y %H:%M:%S +0000", "%d %b %Y %H:%M:%S +0000", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
                   "%Y-%m-%dT%H:%M:%SZ"]
        formats_today = ["T%H:%M:%SZ", "T%H:%M:%S", "%H:%M:%S", "%H:%M:%S +0000", " %H:%M:%S +0000"]
        for format in formats:
            out = self.try_todoist_time_to_datetime_datetime(time_string, format)
            if out:
                return out

        for format in formats_today:
            time_string_today = datetime.datetime.now().strftime("%Y-%m-%d")+time_string
            format = "%Y-%m-%d"+format
            out = self.try_todoist_time_to_datetime_datetime(time_string_today, format)
            if out:
                return out

        raise ValueError(f"Time string '{time_string}' not known for formats {formats} and today formats {formats_today}")

    def item_status(self, item_obj):
        # Print.prettify(item_obj)
        try:
            if item_obj["is_archived"]:
                if State.debug:
                    print(item_obj["content"], item_obj["due"], "deleted")
                return "deleted"
        except KeyError:
            pass
        if item_obj['is_deleted']:
            if State.debug:
                print(item_obj["content"], item_obj["due"], "deleted")
            return "deleted"
        elif item_obj['checked']:
            if State.debug:
                print(item_obj["content"], item_obj["due"], "deleted")
            return "deleted"
        else:
            now = datetime.datetime.now()
            try:
                # if item_obj['due_date_utc']:
                todo_time = self.todoist_time_to_datetime_datetime(item_obj['due']['date'])
            except KeyError as e:
                Print.prettify(item_obj)
                Print.colored("try to 'pip install --upgrade todoist-python'")
                raise KeyError(e)
            except TypeError:
                # Print.prettify(item_obj)
                # print(id.get())
                if State.debug:
                    print(item_obj["content"], item_obj["due"], "no date")
                return "no date"
            local_timezone = tzlocal.get_localzone()
            utc_timezone = pytz.timezone("utc")
            end_of_today = datetime.datetime(now.year,
                                             now.month,
                                             now.day,
                                             23, 59, 59)  # not used
            now = datetime.datetime.now()

            # end_of_today_aware = local_timezone.localize(now)

            # todo_time_aware = utc_timezone.localize(todo_time)
            # todo: update it to new api due item_obj["date"]["timezone"]
            # dirty hack:
            todo_time_aware = todo_time
            end_of_today_aware = end_of_today

            if end_of_today_aware > todo_time_aware:
                if State.debug:
                    print(item_obj["content"], item_obj["due"], "overdue")
                return "overdue"
            elif end_of_today_aware == todo_time_aware:
                if State.debug:
                    print(item_obj["content"], item_obj["due"], "today")
                return "today"
            elif end_of_today_aware < todo_time_aware:
                if State.debug or State.debug_not_today:
                    print(item_obj["content"], item_obj["due"], "not today")
                return "not today"


