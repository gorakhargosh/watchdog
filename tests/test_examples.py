from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest

from watchdog.events import (
    DirModifiedEvent,
    FileClosedEvent,
    FileClosedNoWriteEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileOpenedEvent,
    FileSystemEvent,
)

if TYPE_CHECKING:
    from types import ModuleType

EXAMPLES_DIR = Path("docs/source/examples")
EXAMPLES = [str(p) for p in sorted(EXAMPLES_DIR.glob("*.py")) if p.name != "__init__.py"]
CONFIG_EXAMPLES = [str(p) for p in sorted(EXAMPLES_DIR.glob("*tricks*")) if p.suffix in {".yaml", ".yml", ".json"}]


def run_example(script_path: str, watched_directory: Path) -> ModuleType:
    # Mock sys.argv to supply the path parameter, and time.sleep to exit the loop
    with patch("sys.argv", [script_path, str(watched_directory)]), patch("time.sleep", side_effect=KeyboardInterrupt):
        # Load and execute the module dynamically
        spec = importlib.util.spec_from_file_location("example_module", script_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)

        # This will run the script, trigger KeyboardInterrupt, and run the finally block
        with pytest.raises(KeyboardInterrupt):
            spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("script_path", EXAMPLES)
def test_example(script_path: str, tmp_path: Path) -> None:
    watched_directory = tmp_path.resolve()
    module = run_example(script_path, watched_directory)

    if Path(script_path).name == "single_file.py":
        event = FileModifiedEvent(str(watched_directory / "example.txt"))
        with patch.object(module.logger, "info") as log:
            module.event_handler.dispatch(event)
        log.assert_called_once_with(event)

    if Path(script_path).name == "validated_restart.py":
        assert module.event_handler.process is None
        assert not module.observer.is_alive()


@pytest.fixture
def validated_restart(tmp_path: Path) -> ModuleType:
    return run_example(str(EXAMPLES_DIR / "validated_restart.py"), tmp_path.resolve())


def test_validated_restart_keeps_worker_until_sources_are_valid(
    validated_restart: ModuleType, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = tmp_path / "worker.py"
    source.write_text("value = 1\n")
    package = tmp_path / "package"
    package.mkdir()
    dependency = package / "dependency.py"
    dependency.write_text("value = 2\n")
    handler = validated_restart.event_handler
    old_process = Mock()
    old_process.poll.return_value = None
    new_process = Mock()

    with patch.object(validated_restart.subprocess, "Popen", side_effect=[old_process, new_process]) as start:
        handler.restart_if_valid()
        assert handler.process is old_process

        dependency.write_text("def broken(:\n")
        handler.restart_if_valid()
        assert start.call_count == 1
        assert handler.process is old_process
        old_process.terminate.assert_not_called()
        assert "restart skipped" in caplog.text
        assert "dependency.py" in caplog.text
        assert "SyntaxError" in caplog.text

        dependency.write_text("value = 3\n")
        handler.restart_if_valid()
        assert start.call_count == 2
        old_process.terminate.assert_called_once_with()
        old_process.wait.assert_called_once_with(timeout=5)
        assert handler.process is new_process
        start.assert_called_with(handler.command, cwd=tmp_path.resolve())

    assert not list(tmp_path.rglob("*.pyc"))
    handler.stop_process()


@pytest.mark.parametrize("with_helper", [False, True], ids=["no-other-sources", "valid-helper"])
@pytest.mark.parametrize("absolute_entrypoint", [False, True], ids=["relative-entrypoint", "absolute-entrypoint"])
@pytest.mark.parametrize("python", ["python", "python3.12", "python.exe", sys.executable])
def test_validated_restart_preserves_worker_until_entrypoint_is_restored(
    validated_restart: ModuleType,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    python: str,
    *,
    with_helper: bool,
    absolute_entrypoint: bool,
) -> None:
    source = tmp_path / "worker.py"
    source.write_text("value = 1\n")
    if with_helper:
        (tmp_path / "helper.py").write_text("value = 2\n")
    handler = validated_restart.event_handler
    handler.command = [python, str(source) if absolute_entrypoint else source.name, "--verbose"]
    old_process = Mock()
    old_process.poll.return_value = None
    new_process = Mock()

    with patch.object(validated_restart.subprocess, "Popen", side_effect=[old_process, new_process]) as start:
        handler.restart_if_valid()
        assert handler.process is old_process

        source.unlink()
        handler.restart_if_valid()
        assert start.call_count == 1
        assert handler.process is old_process
        old_process.terminate.assert_not_called()
        old_process.kill.assert_not_called()
        old_process.wait.assert_not_called()
        assert "restart skipped" in caplog.text
        assert "worker.py" in caplog.text
        assert caplog.records[-1].levelname == "WARNING"

        source.write_text("value = 3\n")
        handler.restart_if_valid()
        assert start.call_count == 2
        old_process.terminate.assert_called_once_with()
        old_process.wait.assert_called_once_with(timeout=5)
        assert handler.process is new_process
        start.assert_called_with(handler.command, cwd=tmp_path.resolve())

    handler.stop_process()


@pytest.mark.parametrize(
    "command",
    [
        [sys.executable, "-c", "pass", "missing.py"],
        [sys.executable, "-m", "package", "missing.py"],
        ["other-program", "missing.py"],
        ["python-tool", "missing.py"],
        ["worker.py"],
    ],
)
def test_validated_restart_allows_other_command_forms(
    validated_restart: ModuleType, command: list[str], tmp_path: Path
) -> None:
    handler = validated_restart.event_handler
    handler.command = command
    old_process = Mock()
    old_process.poll.return_value = None
    handler.process = old_process
    with patch.object(validated_restart.subprocess, "Popen") as start:
        handler.restart_if_valid()
        old_process.terminate.assert_called_once_with()
        old_process.wait.assert_called_once_with(timeout=5)
        start.assert_called_once_with(command, cwd=tmp_path.resolve())
        assert handler.process is start.return_value

    handler.stop_process()


def test_validated_restart_rejects_invalid_initial_source(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n")
    with patch("subprocess.Popen") as start:
        run_example(str(EXAMPLES_DIR / "validated_restart.py"), tmp_path.resolve())
    start.assert_not_called()
    assert "restart skipped" in caplog.text


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (FileCreatedEvent("worker.py"), True),
        (FileModifiedEvent("worker.py"), True),
        (FileModifiedEvent("package/dependency.py"), True),
        (FileDeletedEvent("worker.py"), True),
        (FileMovedEvent("worker.tmp", "worker.py"), True),
        (FileMovedEvent("worker.py", "worker.tmp"), True),
        (FileOpenedEvent("worker.py"), False),
        (FileClosedNoWriteEvent("worker.py"), False),
        (FileClosedEvent("worker.py"), False),
        (FileModifiedEvent("worker.pyc"), False),
        (FileModifiedEvent("notes.txt"), False),
        (DirModifiedEvent("source"), False),
    ],
)
def test_validated_restart_filters_events(
    validated_restart: ModuleType, tmp_path: Path, event: FileSystemEvent, *, expected: bool
) -> None:
    handler = validated_restart.event_handler
    handler.changed.clear()
    event = replace(
        event,
        src_path=str(tmp_path / os.fsdecode(event.src_path)),
        dest_path=str(tmp_path / os.fsdecode(event.dest_path)) if event.dest_path else "",
    )
    handler.dispatch(event)
    assert handler.changed.is_set() is expected


def test_validated_restart_kills_unresponsive_worker(validated_restart: ModuleType) -> None:
    handler = validated_restart.event_handler
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired(handler.command, 5), None]
    handler.process = process
    handler.stop_process()
    process.terminate.assert_called_once_with()
    process.kill.assert_called_once_with()
    assert process.wait.call_count == 2
    assert handler.process is None


@pytest.mark.parametrize("config_path", CONFIG_EXAMPLES)
def test_tricks_example(config_path: str) -> None:
    # Skip if import PyYAML failed. PyYAML missing possible because
    # watchdog installed without watchmedo. See Installation section.
    if config_path.endswith((".yaml", ".yml")):
        pytest.importorskip("yaml")

    from watchdog import watchmedo
    from watchdog.utils import WatchdogShutdownError

    args = watchmedo.cli.parse_args(["tricks-from", config_path])
    with patch("time.sleep", side_effect=WatchdogShutdownError):
        watchmedo.tricks_from(args)
