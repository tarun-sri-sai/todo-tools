import git
import logging
import traceback
from datetime import datetime
from sortedcontainers import SortedDict
from .parser import parse_todo
from .exceptions import TodoAnalyzerError, TodoParserError

logging.getLogger()


class TodoAnalyzer:
    def __init__(self, repo_path):
        self._DATE_FMT = "%Y-%m-%d"
        self._TODO_FILE = "to-do.txt"

        self._todo_repo = git.Repo(repo_path)
        self._history = SortedDict()

        self._cache_history()

    def _try_parse_date(self, date_str):
        try:
            return datetime.strptime(date_str, self._DATE_FMT)
        except ValueError:
            raise TodoAnalyzerError(
                f"invalid date format: {date_str}, expected {self._DATE_FMT}"
            )

    def _cache_history(self):
        for commit in self._todo_repo.iter_commits():
            sha = commit.hexsha
            message = commit.message.strip()

            try:
                self._history[self._try_parse_date(message)] = commit.hexsha
            except TodoAnalyzerError:
                logging.debug(
                    f"commit {sha} - invalid date format: {message}"
                )

    def _get_date_range(self, from_date_str=None, to_date_str=None):
        from_date = (
            self._history.peekitem(0)[0]
            if from_date_str is None
            else self._try_parse_date(from_date_str)
        )
        to_date = (
            self._history.peekitem(-1)[0]
            if to_date_str is None
            else self._try_parse_date(to_date_str)
        )

        if from_date > to_date:
            raise TodoAnalyzerError(
                "'start date' must be less than or equal to 'end date'"
            )

        ceiling = self._history.bisect_left(from_date)
        if ceiling == len(self._history):
            raise TodoAnalyzerError(
                f"no todos found for 'start date' {from_date_str}"
            )
        history_start_date = self._history.items()[ceiling][0]

        floor = self._history.bisect_right(to_date) - 1
        if floor == -1:
            raise TodoAnalyzerError(
                f"no todos found for 'end date' {to_date_str}"
            )
        history_end_date = self._history.items()[floor][0]

        return history_start_date, history_end_date

    def _get_stats(self, tasks, end_date):
        if not tasks:
            return {
                "total_tasks": 0,
                "longest_task_id": "",
                "average_task_duration": 0,
                "median_task_duration": 0,
                "most_active_task_id": "",
                "most_active_category": ""
            }

        task_data = []
        for task_id, task in tasks.items():
            task_end_date = (
                self._try_parse_date(task["end_date"])
                if "end_date" in task
                else end_date
            )
            task_start_date = self._try_parse_date(task["start_date"])

            task_data.append({
                "task_id": task_id,
                "duration": (task_end_date - task_start_date).days,
                "updates": task["updates"],
                "category": task["category"],
            })

        category_updates = {}
        for task in task_data:
            category = task["category"]
            category_updates[category] = (
                category_updates.get(category, 0) +
                len(task["updates"])
            )

        def duration_key(x): return x["duration"]
        def updates_key(x): return x["updates"]
        half_len = len(task_data) // 2

        total_tasks = len(task_data)

        longest_task = max(task_data, key=duration_key)

        average_task_duration = (
            sum(task["duration"] for task in task_data) /
            max(len(task_data), 1)
        )

        median_task = sorted(task_data, key=duration_key)[half_len]

        most_active_task = max(task_data, key=updates_key)

        most_active_category = max(category_updates, key=category_updates.get)

        return {
            "total_tasks": total_tasks,
            "longest_task_id": longest_task["task_id"],
            "average_task_duration": average_task_duration,
            "median_task_duration": median_task["duration"],
            "most_active_task_id": most_active_task["task_id"],
            "most_active_category": most_active_category
        }

    def _get_tasks_by_date(self, from_date_str=None, to_date_str=None):
        history_start_date, history_end_date = self._get_date_range(
            from_date_str,
            to_date_str
        )
        history_dates = self._history.irange(
            history_start_date,
            history_end_date
        )

        tasks = {}
        for commit in (self._history[date] for date in history_dates):
            commit_obj = self._todo_repo.commit(commit)
            try:
                todo_file = commit_obj.tree / self._TODO_FILE
                todo_contents = todo_file.data_stream.read().decode("utf-8")
                task_map = parse_todo(todo_contents)

                curr_tasks = set(task_map.keys())

                for task_id, task in task_map.items():
                    if task_id not in tasks:
                        tasks[task_id] = {
                            **task,
                            "start_date": commit_obj.message.strip()
                        }

                    tasks[task_id]["updates"] = task["updates"]
                    tasks[task_id]["category"] = task.get("category", "")
                    tasks[task_id]["parentTasks"] = task["parentTasks"]

                    if (
                        task.get("finished", False)
                        and "end_date" not in tasks[task_id]
                    ):
                        tasks[task_id]["finished"] = True
                        tasks[task_id]["end_date"] = commit_obj.message.strip()

                for task_id, task in tasks.items():
                    if (
                        task_id not in curr_tasks
                        and not task.get("finished", False)
                        and "end_date" not in task
                    ):
                        task["abandoned"] = True
                        task["end_date"] = commit_obj.message.strip()
            except TodoParserError:
                logging.debug(
                    f"commit {commit} - failed to parse {self._TODO_FILE}"
                )
                logging.debug(traceback.format_exc())
            except Exception as e:
                logging.debug(
                    f"commit {commit} - error parsing {self._TODO_FILE}: {e}"
                )
                logging.debug(traceback.format_exc())
        
        return tasks

    def get_tasks(self, from_date_str=None, to_date_str=None):
        _, history_end_date = self._get_date_range(from_date_str, to_date_str)
        tasks = self._get_tasks_by_date(from_date_str, to_date_str)

        return {
            "tasks": tasks,
            "stats": self._get_stats(tasks, history_end_date)
        }

    def _get_tasks_by_min_days(self, tasks, min_days=0):
        return {
            task_id: task
            for task_id, task in tasks.items()
            if (
                self._try_parse_date(task["end_date"])
                - self._try_parse_date(task["start_date"])
            ).days >= min_days
        }

    def get_abandoned_tasks(
        self, from_date_str=None, to_date_str=None, min_days=0
    ):
        _, history_end_date = self._get_date_range(from_date_str, to_date_str)
        tasks = self._get_tasks_by_date(from_date_str, to_date_str)

        abandoned_tasks = self._get_tasks_by_min_days({
            task_id: task
            for task_id, task in tasks.items()
            if task.get("abandoned", False)
        }, min_days)

        return {
            "stats": self._get_stats(abandoned_tasks, history_end_date),
            "tasks": abandoned_tasks
        }

    def get_finished_tasks(
        self, from_date_str=None, to_date_str=None, min_days=0
    ):
        _, history_end_date = self._get_date_range(from_date_str, to_date_str)
        tasks = self._get_tasks_by_date(from_date_str, to_date_str)

        finished_tasks = self._get_tasks_by_min_days({
            task_id: task
            for task_id, task in tasks.items()
            if task.get("finished", False)
        }, min_days)

        return {
            "stats": self._get_stats(finished_tasks, history_end_date),
            "tasks": finished_tasks
        }
