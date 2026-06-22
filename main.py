import json
import logging
import sys
import traceback
from argparse import ArgumentParser
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from lib.logging_util import setup_logger
from lib.todo.analyzer import TodoAnalyzer
from lib.todo.exceptions import TodoAnalyzerError
from lib.todo.parser import parse_todo, TodoParserError


def init_logger(log_name="main"):
    """Initialize logger for the CLI application."""
    script_file_path = Path(__file__)
    work_dir = script_file_path.parent
    setup_logger(work_dir / "logs" / f"{log_name}.log")
    logging.getLogger()


def cmd_check(args):
    """Handle the 'check' subcommand."""
    try:
        with open(args.file, "r") as f:
            contents = f.read()
    except Exception:
        return 1

    try:
        parse_todo(contents)
        return 0
    except TodoParserError:
        return 2


def update_analyze_subparsers(subparsers):
    # Analyze get-tasks
    get_tasks_parser = subparsers.add_parser(
        "get-tasks",
        help="get all tasks for a date range"
    )
    get_tasks_parser.add_argument(
        "--from-date",
        type=str,
        default=None
    )
    get_tasks_parser.add_argument(
        "--to-date",
        type=str,
        default=None
    )

    # Analyze get-abandoned-tasks
    get_abandoned_tasks_parser = subparsers.add_parser(
        "get-abandoned-tasks",
        help="get abandoned tasks for a date range"
    )
    get_abandoned_tasks_parser.add_argument(
        "--from-date",
        type=str,
        default=None
    )
    get_abandoned_tasks_parser.add_argument(
        "--to-date",
        type=str,
        default=None
    )
    get_abandoned_tasks_parser.add_argument(
        "--min-days",
        type=int,
        default=0
    )

    # Analyze get-finished-tasks
    get_finished_tasks_parser = subparsers.add_parser(
        "get-finished-tasks",
        help="get finished tasks for a date range"
    )
    get_finished_tasks_parser.add_argument(
        "--from-date",
        type=str,
        default=None
    )
    get_finished_tasks_parser.add_argument(
        "--to-date",
        type=str,
        default=None
    )
    get_finished_tasks_parser.add_argument(
        "--min-days",
        type=int,
        default=0
    )


def cmd_analyze(args):
    """Handle the 'analyze' subcommand."""
    repo_path = Path(args.repo_path)
    if not repo_path.exists():
        logging.critical(f"repository path does not exist: {repo_path}")
        return 1

    analyzer = TodoAnalyzer(repo_path)

    if args.analyze_command == "get-tasks":
        try:
            tasks = analyzer.get_tasks(args.from_date, args.to_date)
            print(json.dumps(tasks, indent=2))
        except TodoAnalyzerError as e:
            logging.critical(f"error getting tasks: {e}")
            logging.debug(traceback.format_exc())
            return 1

    elif args.analyze_command == "get-abandoned-tasks":
        try:
            tasks = analyzer.get_abandoned_tasks(
                args.from_date,
                args.to_date,
                args.min_days
            )
            print(json.dumps(tasks, indent=2))
        except TodoAnalyzerError as e:
            logging.critical(f"error getting abandoned tasks: {e}")
            logging.debug(traceback.format_exc())
            return 1

    elif args.analyze_command == "get-finished-tasks":
        try:
            tasks = analyzer.get_finished_tasks(
                args.from_date,
                args.to_date,
                args.min_days
            )
            print(json.dumps(tasks, indent=2))
        except TodoAnalyzerError as e:
            logging.critical(f"error getting finished tasks: {e}")
            logging.debug(traceback.format_exc())
            return 1

    return 0


def cmd_mcp(args):
    """Handle the 'mcp' subcommand."""
    repo_path = Path(args.repo_path)
    if not repo_path.exists():
        logging.critical(f"repository path does not exist: {repo_path}")
        return 1

    try:
        mcp = FastMCP("todo-mcp", json_response=True)
        analyzer = TodoAnalyzer(repo_path)

        @mcp.tool()
        def get_tasks(
            from_date: str | None = None,
            to_date: str | None = None
        ) -> str:
            """
            Get all tasks for a date range.

            Args:
                from_date: Start date in YYYY-MM-DD format (optional)
                to_date: End date in YYYY-MM-DD format (optional)

            Returns:
                JSON string containing all tasks in the date range
            """
            try:
                tasks = analyzer.get_tasks(from_date, to_date)
                return json.dumps(tasks, indent=2, default=str)
            except TodoAnalyzerError as e:
                return json.dumps({"error": str(e)})

        @mcp.tool()
        def get_abandoned_tasks(
            from_date: str | None = None,
            to_date: str | None = None,
            min_days: int = 0
        ) -> str:
            """
            Get abandoned tasks for a date range.

            Args:
                from_date: Start date in YYYY-MM-DD format (optional)
                to_date: End date in YYYY-MM-DD format (optional)
                min_days: Minimum number of days a task was tracked (default: 0)

            Returns:
                JSON string containing abandoned tasks in the date range
            """
            try:
                tasks = analyzer.get_abandoned_tasks(
                    from_date,
                    to_date,
                    min_days
                )
                return json.dumps(tasks, indent=2, default=str)
            except TodoAnalyzerError as e:
                return json.dumps({"error": str(e)})

        @mcp.tool()
        def get_finished_tasks(
            from_date: str | None = None,
            to_date: str | None = None,
            min_days: int = 0
        ) -> str:
            """
            Get finished tasks for a date range.

            Args:
                from_date: Start date in YYYY-MM-DD format (optional)
                to_date: End date in YYYY-MM-DD format (optional)
                min_days: Minimum number of days a task was tracked (default: 0)

            Returns:
                JSON string containing finished tasks in the date range
            """
            try:
                tasks = analyzer.get_finished_tasks(
                    from_date,
                    to_date,
                    min_days
                )
                return json.dumps(tasks, indent=2, default=str)
            except TodoAnalyzerError as e:
                return json.dumps({"error": str(e)})

        mcp.run(transport="stdio")
        return 0
    except Exception as e:
        logging.critical(f"error initializing MCP server: {e}")
        logging.debug(traceback.format_exc())
        return 1


def main():
    """Main entry point for the unified CLI application."""
    init_logger()

    parser = ArgumentParser(
        description="Unified todo tools CLI"
    )
    subparsers = parser.add_subparsers(
        dest="command",
        help="available subcommands"
    )
    subparsers.required = True

    # Check subcommand
    check_parser = subparsers.add_parser(
        "check",
        help="check the syntax of a todo file"
    )
    check_parser.add_argument(
        "file",
        help="the todo file to check"
    )
    check_parser.set_defaults(func=cmd_check)

    # Analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="analyze todo history from a git repository"
    )
    analyze_parser.add_argument(
        "repo_path",
        type=str,
        help="path to the git repository containing todo history"
    )
    analyze_subparsers = analyze_parser.add_subparsers(
        dest="analyze_command",
        help="analyze subcommands"
    )
    analyze_subparsers.required = True
    update_analyze_subparsers(analyze_subparsers)
    analyze_parser.set_defaults(func=cmd_analyze)

    # MCP subcommand
    mcp_parser = subparsers.add_parser(
        "mcp",
        help="start the MCP server for todo analysis"
    )
    mcp_parser.add_argument(
        "repo_path",
        type=str,
        help="path to the git repository containing todo history"
    )
    mcp_parser.set_defaults(func=cmd_mcp)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
