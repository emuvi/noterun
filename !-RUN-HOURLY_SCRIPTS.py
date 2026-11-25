import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass



def print_error(message: str) -> None:
    """Prints an error message to stderr."""
    print(message, file=sys.stderr)


# List of scripts to be executed (relative to the current directory or this script's directory).
SCRIPTS: List[str] = []

# Directory containing !-RUN-HOURLY_SCRIPTS.py and !-RUN-HOURLY_SCRIPTS.bat.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ERROR_LOG_PREFIX = "!-RUN-HOURLY_SCRIPTS-errors_"
ERROR_LOG_EXTENSION = ".log"


def get_current_time() -> str:
    """Return the current local time formatted as HH:MM:SS.

    Returns:
        str: Current local time in HH:MM:SS format.
    """
    return datetime.now().strftime("%H:%M:%S")


def get_timestamp_for_filename() -> str:
    """Return a filename-safe local timestamp formatted as YYYY-MM-DD_HH-MM-SS.

    Returns:
        str: Timestamp suitable for error log filenames.
    """
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def build_error_log_path(timestamp: Optional[str] = None, log_dir: str = BASE_DIR) -> str:
    """Build a unique path for the hourly scripts error log file.

    Parameters:
        timestamp (Optional[str]): Precomputed filename-safe timestamp. Defaults to now.
        log_dir (str): Directory where the error log will be saved. Defaults to BASE_DIR.

    Returns:
        str: Unique absolute path matching !-RUN-HOURLY_SCRIPTS-errors_${timestamp}.log.
    """
    ts = timestamp or get_timestamp_for_filename()
    base_name = f"{ERROR_LOG_PREFIX}{ts}"
    candidate = os.path.join(log_dir, f"{base_name}{ERROR_LOG_EXTENSION}")
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(log_dir, f"{base_name}_{counter}{ERROR_LOG_EXTENSION}")
        counter += 1
    return candidate


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
    stream = sys.stderr if category == "ERROR" else sys.stdout
    print(f"[{get_current_time()}] {emoji} [{category}] [{function_name}] {message}", file=stream)


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


class CycleErrorLogger:
    """Lazily creates and appends to a timestamped error log file for a scheduler cycle."""

    def __init__(self, log_dir: str = BASE_DIR, timestamp: Optional[str] = None) -> None:
        self.log_dir = os.path.abspath(log_dir)
        self.started_at = datetime.now()
        self.timestamp = timestamp or self.started_at.strftime("%Y-%m-%d_%H-%M-%S")
        self.log_path: Optional[str] = None
        self.has_errors = False

    def record_error(
        self,
        script_path: str,
        error_text: str,
        exit_code: Optional[int] = None,
    ) -> Optional[str]:
        """Append an error section for a script execution to the cycle error log file.

        Parameters:
            script_path (str): Absolute or relative path of the failing script.
            error_text (str): Captured stderr output or error description.
            exit_code (Optional[int]): Process exit code if available.

        Returns:
            Optional[str]: Path to the error log file if written successfully, else None.
        """
        script_name = os.path.basename(script_path) or script_path
        event_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        exit_code_str = str(exit_code) if exit_code is not None else "N/A"
        normalized_error = (error_text or "").rstrip()
        if not normalized_error:
            normalized_error = "(no stderr output captured)"

        try:
            os.makedirs(self.log_dir, exist_ok=True)
            is_new_file = self.log_path is None
            if is_new_file:
                self.log_path = build_error_log_path(timestamp=self.timestamp, log_dir=self.log_dir)

            assert self.log_path is not None
            with open(self.log_path, "a", encoding="utf-8") as log_file:
                if is_new_file:
                    log_file.write("=" * 80 + "\n")
                    log_file.write("!-RUN-HOURLY_SCRIPTS ERROR LOG\n")
                    log_file.write(f"Cycle Started: {self.started_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    log_file.write("=" * 80 + "\n")

                log_file.write("\n" + "-" * 80 + "\n")
                log_file.write(f"Timestamp: {event_time}\n")
                log_file.write(f"Script:    {script_name}\n")
                log_file.write(f"Path:      {script_path}\n")
                log_file.write(f"Exit Code: {exit_code_str}\n")
                log_file.write("-" * 80 + "\n")
                log_file.write(normalized_error + "\n")

            self.has_errors = True
            return self.log_path
        except OSError as io_err:
            log_error(
                "CycleErrorLogger.record_error",
                f"Failed to write error log in '{self.log_dir}': {io_err}",
            )
            return None


def resolve_script_path(script_path: str) -> str:
    """Resolve a script path to an absolute path.

    Checks the current working directory first for relative paths, falling back to
    BASE_DIR (the directory containing !-RUN-HOURLY_SCRIPTS.bat/.py).

    Parameters:
        script_path (str): Relative or absolute script path.

    Returns:
        str: Absolute normalized script path.
    """
    if os.path.isabs(script_path):
        return os.path.abspath(script_path)

    cwd_candidate = os.path.abspath(script_path)
    if os.path.exists(cwd_candidate):
        return cwd_candidate

    base_candidate = os.path.abspath(os.path.join(BASE_DIR, script_path))
    if os.path.exists(base_candidate):
        return base_candidate

    return cwd_candidate


def build_script_command(absolute_script_path: str) -> List[str]:
    """Build the command-line arguments used to execute a target script.

    Parameters:
        absolute_script_path (str): Absolute path to the target script.

    Returns:
        List[str]: Command list passed to subprocess.Popen.
    """
    if absolute_script_path.lower().endswith((".bat", ".cmd")):
        return ["cmd", "/c", absolute_script_path]
    return [sys.executable, absolute_script_path]


def execute_script_subprocess(absolute_script_path: str, script_dir: str) -> Tuple[int, str]:
    """Execute a target script in a child process and capture its stderr.

    Parameters:
        absolute_script_path (str): Absolute path to the script to execute.
        script_dir (str): Working directory for the child process.

    Returns:
        Tuple[int, str]: (return_code, captured_stderr_output).
    """
    cmd = build_script_command(absolute_script_path)
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONUNBUFFERED"] = "1"

    sys.stdout.flush()
    sys.stderr.flush()

    process = subprocess.Popen(
        cmd,
        cwd=script_dir,
        stdin=subprocess.DEVNULL,
        stdout=None,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env,
    )

    stderr_chunks: List[str] = []
    try:
        if process.stderr is not None:
            for line in process.stderr:
                stderr_chunks.append(line)
                sys.stderr.write(line)
                sys.stderr.flush()
        return_code = process.wait()
    except KeyboardInterrupt:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        raise
    finally:
        if process.stderr is not None:
            try:
                process.stderr.close()
            except Exception:
                pass

    return return_code, "".join(stderr_chunks)


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


def run_script(
    script_path: str,
    item_index: int,
    total_items: int,
    error_logger: Optional[CycleErrorLogger] = None,
) -> bool:
    """Execute one script in an isolated subprocess, capturing stderr to the error log.

    Parameters:
        script_path (str): Relative or absolute path to the script.
        item_index (int): Current 1-based index in the cycle.
        total_items (int): Total scripts to process in the cycle.
        error_logger (Optional[CycleErrorLogger]): Cycle error logger for saving script errors.

    Returns:
        bool: True when script execution succeeds without stderr errors; otherwise False.
    """
    function_name = "run_script"
    active_logger = error_logger if error_logger is not None else CycleErrorLogger()

    log_step(
        function_name,
        f"Starting | params: {_format_params(script_path=script_path, item_index=item_index, total_items=total_items)}",
    )

    absolute_script_path = resolve_script_path(script_path)
    script_name = os.path.basename(absolute_script_path)
    script_dir = os.path.dirname(absolute_script_path)

    try:
        if not os.path.isfile(absolute_script_path):
            error_message = (
                f"Script not found: {absolute_script_path}. "
                "How to fix: verify SCRIPTS entry, confirm file exists, and check read permissions."
            )
            log_error(function_name, error_message)
            active_logger.record_error(
                script_path=absolute_script_path,
                error_text=error_message,
            )
            return False

        log_step("run_cycle", f"Processing item {item_index} of {total_items}")
        log_info("run_cycle", f"Processing: {script_name} with absolute_path={absolute_script_path}")

        log_step(
            "execute_script_subprocess",
            f"Starting | params: {_format_params(script_name=script_name, working_dir=script_dir)}",
        )
        return_code, stderr_output = execute_script_subprocess(absolute_script_path, script_dir)

        has_stderr = bool(stderr_output.strip())
        if return_code != 0 or has_stderr:
            error_detail = (
                stderr_output.strip()
                if has_stderr
                else f"Script exited with non-zero exit code {return_code} without writing to stderr."
            )
            saved_log = active_logger.record_error(
                script_path=absolute_script_path,
                error_text=error_detail,
                exit_code=return_code,
            )
            log_suffix = f" Saved to: {saved_log}" if saved_log else ""
            log_error(
                function_name,
                (
                    f"Execution reported errors for {script_name} "
                    f"(exit_code={return_code}, stderr_captured={has_stderr}).{log_suffix}"
                ),
            )
            return False

        log_success("execute_script_subprocess", f"Completed | executed {script_name} (exit_code=0)")
        log_success(function_name, f"Completed | result=success, script={script_name}")
        return True

    except KeyboardInterrupt:
        raise
    except Exception as exc:
        error_detail = (
            f"Execution failed for {script_name}: {exc}\n"
            f"{traceback.format_exc()}"
        )
        log_error(
            function_name,
            (
                f"Execution failed for {script_name}: {exc}. "
                "How to fix: validate script path, Python interpreter, and runtime permissions."
            ),
        )
        active_logger.record_error(
            script_path=absolute_script_path,
            error_text=error_detail,
        )
        return False


def run_all_scripts(
    scripts: Iterable[str],
    error_log_dir: str = BASE_DIR,
) -> Tuple[int, int, int]:
    """Run each configured script and return cycle totals.

    Parameters:
        scripts (Iterable[str]): Script path collection for this cycle.
        error_log_dir (str): Directory where error logs are written when failures occur.

    Returns:
        Tuple[int, int, int]: (total_processed, successes, failures).
    """
    function_name = "run_all_scripts"
    scripts_list = list(scripts)
    total_items = len(scripts_list)
    successes = 0
    failures = 0
    error_logger = CycleErrorLogger(log_dir=error_log_dir)

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
        succeeded = run_script(
            script_path=script_path,
            item_index=item_index,
            total_items=total_items,
            error_logger=error_logger,
        )

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
    if error_logger.has_errors and error_logger.log_path:
        log_info(function_name, f"Errors saved to: {error_logger.log_path}")
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

    try:
        total, successes, failures = run_all_scripts(SCRIPTS)
        log_info(
            function_name,
            f"Initial cycle completed | total_processed={total}, successes={successes}, failures={failures}",
        )

        while True:
            try:
                wait_for_next_cycle(hours=1)
                total, successes, failures = run_all_scripts(SCRIPTS)
                log_info(
                    function_name,
                    f"Cycle completed | total_processed={total}, successes={successes}, failures={failures}",
                )
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                log_error(function_name, f"Unexpected error during scheduler cycle: {exc}. Retrying in 60s...")
                CycleErrorLogger(log_dir=BASE_DIR).record_error(
                    script_path=os.path.abspath(__file__),
                    error_text=f"Unexpected error during scheduler cycle: {exc}\n{traceback.format_exc()}",
                )
                time.sleep(60)
    except KeyboardInterrupt:
        log_info(function_name, "Scheduler stopped by user.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScheduler stopped by user.")
        sys.exit(0)
    except Exception as exc:
        log_error("main", f"Fatal scheduler error: {exc}")
        CycleErrorLogger(log_dir=BASE_DIR).record_error(
            script_path=os.path.abspath(__file__),
            error_text=f"Fatal scheduler error: {exc}\n{traceback.format_exc()}",
            exit_code=1,
        )
        sys.exit(1)
