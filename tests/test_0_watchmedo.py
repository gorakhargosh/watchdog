from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

import pytest

# Skip if import PyYAML failed. PyYAML missing possible because
# watchdog installed without watchmedo. See Installation section
# in README.rst
yaml = pytest.importorskip("yaml")

from watchdog import watchmedo  # noqa: E402
from watchdog.events import FileModifiedEvent, FileOpenedEvent  # noqa: E402
from watchdog.tricks import AutoRestartTrick, ShellCommandTrick  # noqa: E402
from watchdog.utils import WatchdogShutdownError, platform  # noqa: E402
from yaml.constructor import ConstructorError  # noqa: E402
from yaml.scanner import ScannerError  # noqa: E402


def test_load_config_valid(tmpdir):
    """Verifies the load of a valid yaml file"""

    yaml_file = os.path.join(tmpdir, "config_file.yaml")
    with open(yaml_file, "w") as f:
        f.write("one: value\ntwo:\n- value1\n- value2\n")

    config = watchmedo.load_config(yaml_file)
    assert isinstance(config, dict)
    assert "one" in config
    assert "two" in config
    assert isinstance(config["two"], list)
    assert config["one"] == "value"
    assert config["two"] == ["value1", "value2"]


def test_load_config_invalid(tmpdir):
    """Verifies if safe load avoid the execution
    of untrusted code inside yaml files"""

    critical_dir = os.path.join(tmpdir, "critical")
    yaml_file = os.path.join(tmpdir, "tricks_file.yaml")
    with open(yaml_file, "w") as f:
        content = f'one: value\nrun: !!python/object/apply:os.system ["mkdir {critical_dir}"]\n'
        f.write(content)

    # PyYAML get_single_data() raises different exceptions for Linux and Windows
    with pytest.raises((ConstructorError, ScannerError)):
        watchmedo.load_config(yaml_file)

    assert not os.path.exists(critical_dir)


def make_dummy_script(tmpdir, n=10):
    script = os.path.join(tmpdir, f"auto-test-{n}.py")
    with open(script, "w") as f:
        f.write('import time\nfor i in range(%d):\n\tprint("+++++ %%d" %% i, flush=True)\n\ttime.sleep(1)\n' % n)
    return script


def test_kill_auto_restart(tmpdir, capfd):
    script = make_dummy_script(tmpdir)
    a = AutoRestartTrick([sys.executable, script])
    a.start()
    time.sleep(3)
    a.stop()
    cap = capfd.readouterr()
    assert "+++++ 0" in cap.out
    assert "+++++ 9" not in cap.out  # we killed the subprocess before the end
    # in windows we seem to lose the subprocess stderr
    # assert 'KeyboardInterrupt' in cap.err


def test_shell_command_wait_for_completion(tmpdir, capfd):
    script = make_dummy_script(tmpdir, n=1)
    command = f"{sys.executable} {script}"
    trick = ShellCommandTrick(command, wait_for_process=True)
    assert not trick.is_process_running()
    start_time = time.monotonic()
    trick.on_any_event(FileModifiedEvent("foo/bar.baz"))
    elapsed = time.monotonic() - start_time
    assert not trick.is_process_running()
    assert elapsed >= 1


def test_shell_command_subprocess_termination_nowait(tmpdir):
    script = make_dummy_script(tmpdir, n=1)
    command = f"{sys.executable} {script}"
    trick = ShellCommandTrick(command, wait_for_process=False)
    assert not trick.is_process_running()
    trick.on_any_event(FileModifiedEvent("foo/bar.baz"))
    assert trick.is_process_running()
    time.sleep(5)
    assert not trick.is_process_running()


def test_shell_command_subprocess_termination_not_happening_on_file_opened_event(
    tmpdir,
):
    # FIXME: see issue #949, and find a way to better handle that scenario
    script = make_dummy_script(tmpdir, n=1)
    command = f"{sys.executable} {script}"
    trick = ShellCommandTrick(command, wait_for_process=False)
    assert not trick.is_process_running()
    trick.on_any_event(FileOpenedEvent("foo/bar.baz"))
    assert not trick.is_process_running()
    time.sleep(5)
    assert not trick.is_process_running()


def test_auto_restart_not_happening_on_file_opened_event(tmpdir, capfd):
    # FIXME: see issue #949, and find a way to better handle that scenario
    script = make_dummy_script(tmpdir, n=2)
    trick = AutoRestartTrick([sys.executable, script])
    trick.start()
    time.sleep(1)
    trick.on_any_event(FileOpenedEvent("foo/bar.baz"))
    trick.on_any_event(FileOpenedEvent("foo/bar2.baz"))
    trick.on_any_event(FileOpenedEvent("foo/bar3.baz"))
    time.sleep(1)
    trick.stop()
    cap = capfd.readouterr()
    assert cap.out.splitlines(keepends=False).count("+++++ 0") == 1
    assert trick.restart_count == 0


def test_auto_restart_on_file_change(tmpdir, capfd):
    """Simulate changing 3 files.

    Expect 3 restarts.
    """
    script = make_dummy_script(tmpdir, n=2)
    trick = AutoRestartTrick([sys.executable, script])
    trick.start()
    time.sleep(1)
    trick.on_any_event(FileModifiedEvent("foo/bar.baz"))
    trick.on_any_event(FileModifiedEvent("foo/bar2.baz"))
    trick.on_any_event(FileModifiedEvent("foo/bar3.baz"))
    time.sleep(1)
    trick.stop()
    cap = capfd.readouterr()
    assert cap.out.splitlines(keepends=False).count("+++++ 0") >= 2
    assert trick.restart_count == 3


@pytest.mark.xfail(
    condition=platform.is_darwin() or platform.is_windows() or sys.implementation.name == "pypy",
    reason="known to be problematic, see #973",
)
def test_auto_restart_on_file_change_debounce(tmpdir, capfd):
    """Simulate changing 3 files quickly and then another change later.

    Expect 2 restarts due to debouncing.
    """
    script = make_dummy_script(tmpdir, n=2)
    trick = AutoRestartTrick([sys.executable, script], debounce_interval_seconds=0.5)
    trick.start()
    time.sleep(1)
    trick.on_any_event(FileModifiedEvent("foo/bar.baz"))
    trick.on_any_event(FileModifiedEvent("foo/bar2.baz"))
    time.sleep(0.1)
    trick.on_any_event(FileModifiedEvent("foo/bar3.baz"))
    time.sleep(1)
    trick.on_any_event(FileModifiedEvent("foo/bar.baz"))
    time.sleep(1)
    trick.stop()
    cap = capfd.readouterr()
    assert cap.out.splitlines(keepends=False).count("+++++ 0") == 3
    assert trick.restart_count == 2


@pytest.mark.flaky(max_runs=5, min_passes=1)
@pytest.mark.parametrize(
    "restart_on_command_exit",
    [
        True,
        pytest.param(
            False,
            marks=pytest.mark.xfail(
                condition=platform.is_darwin() or platform.is_windows(),
                reason="known to be problematic, see #972",
            ),
        ),
    ],
)
def test_auto_restart_subprocess_termination(tmpdir, capfd, restart_on_command_exit):
    """Run auto-restart with a script that terminates in about 2 seconds.

    After 5 seconds, expect it to have been restarted at least once.
    """
    script = make_dummy_script(tmpdir, n=2)
    trick = AutoRestartTrick([sys.executable, script], restart_on_command_exit=restart_on_command_exit)
    trick.start()
    time.sleep(5)
    trick.stop()
    cap = capfd.readouterr()
    if restart_on_command_exit:
        assert cap.out.splitlines(keepends=False).count("+++++ 0") > 1
        assert trick.restart_count >= 1
    else:
        assert cap.out.splitlines(keepends=False).count("+++++ 0") == 1
        assert trick.restart_count == 0


def test_auto_restart_arg_parsing_basic():
    args = watchmedo.cli.parse_args(["auto-restart", "-d", ".", "--recursive", "--debug-force-polling", "cmd"])
    assert args.func is watchmedo.auto_restart
    assert args.command == "cmd"
    assert args.directories == ["."]
    assert args.recursive
    assert args.debug_force_polling


def test_auto_restart_arg_parsing():
    args = watchmedo.cli.parse_args(
        [
            "auto-restart",
            "-d",
            ".",
            "--kill-after",
            "12.5",
            "--debounce-interval=0.2",
            "cmd",
        ]
    )
    assert args.func is watchmedo.auto_restart
    assert args.command == "cmd"
    assert args.directories == ["."]
    assert args.kill_after == pytest.approx(12.5)
    assert args.debounce_interval == pytest.approx(0.2)


def test_shell_command_arg_parsing():
    args = watchmedo.cli.parse_args(["shell-command", "--command='cmd'"])
    assert args.command == "'cmd'"


@pytest.mark.parametrize("cmdline", [["auto-restart", "-d", ".", "cmd"], ["log", "."]])
@pytest.mark.parametrize(
    "verbosity",
    [
        ([], "WARNING"),
        (["-q"], "ERROR"),
        (["--quiet"], "ERROR"),
        (["-v"], "INFO"),
        (["--verbose"], "INFO"),
        (["-vv"], "DEBUG"),
        (["-v", "-v"], "DEBUG"),
        (["--verbose", "-v"], "DEBUG"),
    ],
)
def test_valid_verbosity(cmdline, verbosity):
    (verbosity_cmdline_args, expected_log_level) = verbosity
    cmd = [cmdline[0], *verbosity_cmdline_args, *cmdline[1:]]
    args = watchmedo.cli.parse_args(cmd)
    log_level = watchmedo._get_log_level_from_args(args)  # noqa: SLF001
    assert log_level == expected_log_level


@pytest.mark.parametrize("cmdline", [["auto-restart", "-d", ".", "cmd"], ["log", "."]])
@pytest.mark.parametrize(
    "verbosity_cmdline_args",
    [
        ["-q", "-v"],
        ["-v", "-q"],
        ["-qq"],
        ["-q", "-q"],
        ["--quiet", "--quiet"],
        ["--quiet", "-q"],
        ["-vvv"],
        ["-vvvv"],
        ["-v", "-v", "-v"],
        ["-vv", "-v"],
        ["--verbose", "-vv"],
    ],
)
def test_invalid_verbosity(cmdline, verbosity_cmdline_args):
    cmd = [cmdline[0], *verbosity_cmdline_args, *cmdline[1:]]
    with pytest.raises((watchmedo.LogLevelError, SystemExit)):  # noqa: PT012
        args = watchmedo.cli.parse_args(cmd)
        watchmedo._get_log_level_from_args(args)  # noqa: SLF001


@pytest.mark.parametrize("command", ["tricks-from", "tricks"])
def test_tricks_from_file(command, tmp_path):
    tricks_file = tmp_path / "tricks.yaml"
    tricks_file.write_text(
        """
tricks:
- watchdog.tricks.LoggerTrick:
    patterns: ["*.py", "*.js"]
"""
    )
    args = watchmedo.cli.parse_args([command, str(tricks_file)])

    checkpoint = False

    def mocked_sleep(_):
        nonlocal checkpoint
        checkpoint = True
        raise WatchdogShutdownError

    with patch("time.sleep", mocked_sleep):
        watchmedo.tricks_from(args)
    assert checkpoint
