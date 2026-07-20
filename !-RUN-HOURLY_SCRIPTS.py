import importlib.util
import os
import sys
import time
from datetime import datetime, timedelta
from types import ModuleType
from typing import Iterable, Tuple

# List of scripts to be executed (relative to the current directory).
SCRIPTS = []


def get_current_time() -> str:
    """Return the current local time formatted as HH:MM:SS.

    Returns:
        str: Current local time in HH:MM:SS format.
    """
    return datetime.now().strftime("%H:%M:%S")


def _format_params(**params: object) -> str:
    """Build a readable key/value string for parameter logging.

    Parameters:
        **params (object): Arbitrary named values to render in logs.

    Returns:
        str: Comma-separated key=value string or 'none' when empty.
    """
    if not params:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in params.items())


def log_message(emoji: str, category: str, function_name: str, message: str) -> None:
    """Print a standardized log line with timestamp and semantic metadata.

    Parameters:
        emoji (str): Emoji indicator for the message class.
        category (str): Category token (LOG, STEP, SUCCESS, ERROR).
        function_name (str): Function or step name emitting the message.
        message (str): Human-readable detail message.

    Returns:
        None: This function only prints output.
    """
    print(f"[{get_current_time()}] {emoji} [{category}] [{function_name}] {message}")


def log_info(function_name: str, message: str) -> None:
    """Print an informational message using the required LOG format.

    Parameters:
        function_name (str): Function or step name emitting the message.
        message (str): Message details.

    Returns:
        None: This function only prints output.
    """
    log_message("ℹ️", "LOG", function_name, message)


def log_step(function_name: str, message: str) -> None:
    """Print a step/progress message using the required STEP format.

    Parameters:
        function_name (str): Function or step name emitting the message.
        message (str): Message details.

    Returns:
        None: This function only prints output.
    """
    log_message("🔹", "STEP", function_name, message)


def log_success(function_name: str, message: str) -> None:
    """Print a success message using the required SUCCESS format.

    Parameters:
        function_name (str): Function or step name emitting the message.
        message (str): Message details.

    Returns:
        None: This function only prints output.
    """
    log_message("✅", "SUCCESS", function_name, message)


def log_error(function_name: str, message: str) -> None:
    """Print an error message using the required ERROR format.

    Parameters:
        function_name (str): Function or step name emitting the message.
        message (str): Message details.

    Returns:
        None: This function only prints output.
    """
    log_message("🔴", "ERROR", function_name, message)


def build_module_name(script_name: str) -> str:
    """Create a safe Python module name from a script filename.

    Parameters:
        script_name (str): Script filename with or without special characters.

    Returns:
        str: Sanitized module name suitable for sys.modules.
    """
    return script_name.replace(".py", "").replace("!", "").replace("-", "_").replace(" ", "_")


def resolve_script_path(script_path: str) -> str:
    """Resolve a script path to an absolute path.

    Parameters:
        script_path (str): Relative or absolute script path.

    Returns:
        str: Absolute normalized script path.
    """
    return os.path.abspath(script_path)


def load_script_module(script_path: str, module_name: str) -> ModuleType:
    """Load and execute a Python module from a file location.

    Parameters:
        script_path (str): Absolute path to the script file.
        module_name (str): Safe name used for module registration.

    Returns:
        ModuleType: Loaded Python module object.

    Raises:
        ImportError: If a module spec/loader cannot be created.
        Exception: Any execution exception raised by module import.
    """
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if not spec or not spec.loader:
        raise ImportError(
            "Could not load script specification. Verify readability and syntax of the target file."
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_module_main(module: ModuleType, script_name: str) -> None:
    """Execute the main() entry point from a dynamically loaded module.

    Parameters:
        module (ModuleType): Imported module object.
        script_name (str): Script name used for contextual errors.

    Returns:
        None: Executes module main() and does not return data.

    Raises:
        AttributeError: If main() is missing or not callable.
        Exception: Any runtime exception raised by the called main().
    """
    main_func = getattr(module, "main", None)
    if not callable(main_func):
        raise AttributeError(
            f"No callable main() in {script_name}. Add 'def main()' as an entry point."
        )
    main_func()


def print_summary_box(total_processed: int, successes: int, failures: int, box_width: int = 50) -> None:
    """Print a fixed-width visual summary box with cycle totals.

    Parameters:
        total_processed (int): Number of processed scripts.
        successes (int): Number of successful script executions.
        failures (int): Number of failed script executions.
        box_width (int): Total box width including borders. Default is 50.

    Returns:
        None: This function only prints output.
    """
    inner_width = box_width - 2
    title = "Processing Summary"

    def row(content: str) -> str:
        return f"║{content.ljust(inner_width)}║"

    print("╔" + "═" * inner_width + "╗")
    print(row(title.center(inner_width)))
    print("╠" + "═" * inner_width + "╣")
    print(row(f" Total Processed: {total_processed}"))
    print(row(f" Successes:       {successes}"))
    print(row(f" Failures:        {failures}"))
    print("╚" + "═" * inner_width + "╝")


def run_script(script_path: str, item_index: int, total_items: int) -> bool:
    """Execute one script and report whether execution succeeded.

    Parameters:
        script_path (str): Relative or absolute path to the script.
        item_index (int): Current 1-based index in the cycle.
        total_items (int): Total scripts to process in the cycle.

    Returns:
        bool: True when script execution succeeds; otherwise False.
    """
    function_name = "run_script"
    log_step(
        function_name,
        f"Starting | params: {_format_params(script_path=script_path, item_index=item_index, total_items=total_items)}",
    )

    original_cwd = os.getcwd()
    absolute_script_path = resolve_script_path(script_path)
    script_name = os.path.basename(absolute_script_path)
    script_dir = os.path.dirname(absolute_script_path)

    try:
        if not os.path.exists(absolute_script_path):
            log_error(
                function_name,
                (
                    f"Script not found: {absolute_script_path}. "
                    "How to fix: verify SCRIPTS entry, confirm file exists, and check read permissions."
                ),
            )
            return False

        log_step("run_cycle", f"Processing item {item_index} of {total_items}")
        log_info("run_cycle", f"Processing: {script_name} with absolute_path={absolute_script_path}")

        module_name = build_module_name(script_name)
        log_step("load_script_module", f"Starting | params: {_format_params(module_name=module_name)}")
        module = load_script_module(absolute_script_path, module_name)
        log_success("load_script_module", f"Completed | module={module_name}")

        log_step("change_working_directory", f"Starting | params: {_format_params(script_dir=script_dir)}")
        os.chdir(script_dir)
        log_success("change_working_directory", f"Completed | active_directory={script_dir}")

        log_step("run_module_main", f"Starting | params: {_format_params(script_name=script_name)}")
        run_module_main(module, script_name)
        log_success("run_module_main", f"Completed | executed main() in {script_name}")

        log_success(function_name, f"Completed | result=success, script={script_name}")
        return True

    except Exception as exc:
        log_error(
            function_name,
            (
                f"Execution failed for {script_name}: {exc}. "
                "How to fix: validate script syntax, dependencies, and runtime assumptions in its main() function."
            ),
        )
        return False

    finally:
        log_step("restore_working_directory", f"Starting | params: {_format_params(original_cwd=original_cwd)}")
        os.chdir(original_cwd)
        log_success("restore_working_directory", f"Completed | active_directory={original_cwd}")


def run_all_scripts(scripts: Iterable[str]) -> Tuple[int, int, int]:
    """Run each configured script and return cycle totals.

    Parameters:
        scripts (Iterable[str]): Script path collection for this cycle.

    Returns:
        Tuple[int, int, int]: (total_processed, successes, failures).
    """
    function_name = "run_all_scripts"
    scripts_list = list(scripts)
    total_items = len(scripts_list)
    successes = 0
    failures = 0

    log_step(
        function_name,
        f"Starting | params: {_format_params(total_items=total_items, scripts=scripts_list)}",
    )

    if total_items == 0:
        log_info(function_name, "No scripts configured in SCRIPTS. Add entries to start processing.")
        print_summary_box(total_processed=0, successes=0, failures=0, box_width=50)
        log_success(function_name, "Completed | result=no-op")
        return 0, 0, 0

    for item_index, script_path in enumerate(scripts_list, start=1):
        log_step("run_cycle", f"Processing item {item_index} of {total_items}")
        succeeded = run_script(script_path=script_path, item_index=item_index, total_items=total_items)

        if succeeded:
            successes += 1
            log_success("run_cycle", f"Completed | result=success, script={script_path}")
        else:
            failures += 1
            log_error("run_cycle", f"Script failed | script={script_path}")

    log_info(
        function_name,
        f"Cycle summary | total_processed={total_items}, successes={successes}, failures={failures}",
    )
    print_summary_box(total_processed=total_items, successes=successes, failures=failures, box_width=50)
    log_success(function_name, "Completed | cycle finished")
    return total_items, successes, failures


def wait_for_next_cycle(hours: int = 1) -> None:
    """Sleep until the next scheduler cycle.

    Parameters:
        hours (int): Number of hours to wait before next run.

    Returns:
        None: This function logs and blocks for the wait duration.
    """
    function_name = "wait_for_next_cycle"
    log_step(function_name, f"Starting | params: {_format_params(hours=hours)}")

    next_run = datetime.now() + timedelta(hours=hours)
    log_info(function_name, f"Waiting for {hours} hour(s). Next execution at {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
    time.sleep(hours * 3600)

    log_success(function_name, "Completed | wait interval elapsed")


def main() -> None:
    """Run the scheduler loop that executes scripts every hour.

    Parameters:
        None: This entry point does not take arguments.

    Returns:
        None: This function runs continuously until interrupted.
    """
    function_name = "main"
    log_step(function_name, f"Starting | params: {_format_params(scripts_count=len(SCRIPTS), interval_hours=1)}")
    log_info(function_name, "Scheduler started. Scripts will run every hour.")

    total, successes, failures = run_all_scripts(SCRIPTS)
    log_info(
        function_name,
        f"Initial cycle completed | total_processed={total}, successes={successes}, failures={failures}",
    )

    while True:
        wait_for_next_cycle(hours=1)
        total, successes, failures = run_all_scripts(SCRIPTS)
        log_info(
            function_name,
            f"Cycle completed | total_processed={total}, successes={successes}, failures={failures}",
        )


if __name__ == "__main__":
    main()
