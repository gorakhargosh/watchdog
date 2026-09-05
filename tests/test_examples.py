from __future__ import annotations

import importlib.util
import logging
import runpy
from pathlib import Path
from queue import Queue
from unittest.mock import call, patch

import pytest

from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEvent
from watchdog.observers import Observer

EXAMPLES_DIR = Path("docs/source/examples")
EXAMPLES = [str(p) for p in sorted(EXAMPLES_DIR.glob("*.py")) if p.name != "__init__.py"]


@pytest.mark.parametrize("script_path", EXAMPLES)
def test_example(script_path: str) -> None:
    # Mock sys.argv to supply the path parameter, and time.sleep to exit the loop
    with patch("sys.argv", [script_path, "."]), patch("time.sleep", side_effect=KeyboardInterrupt):
        # Load and execute the module dynamically
        spec = importlib.util.spec_from_file_location("example_module", script_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)

        # This will run the script, trigger KeyboardInterrupt, and run the finally block
        with pytest.raises(KeyboardInterrupt):
            spec.loader.exec_module(module)


def test_multiple_directories_schedules_both_watches() -> None:
    script = str(EXAMPLES_DIR / "multiple_directories.py")
    paths = ["input one", "input two"]
    with (
        patch("sys.argv", [script, *paths]),
        patch("watchdog.observers.Observer") as observer_class,
        patch("time.sleep", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        runpy.run_path(script)

    observer_class.assert_called_once_with()
    observer = observer_class.return_value
    schedules = observer.schedule.call_args_list
    assert len(schedules) == 2
    handlers = [scheduled.args[0] for scheduled in schedules]
    assert handlers[0] is not handlers[1]
    assert observer.mock_calls == [
        call.schedule(handlers[0], paths[0], recursive=True),
        call.schedule(handlers[1], paths[1], recursive=True),
        call.start(),
        call.stop(),
        call.join(),
    ]


@pytest.mark.parametrize("paths", [[], ["input one"]])
def test_multiple_directories_accepts_default_or_single_path(paths: list[str]) -> None:
    script = str(EXAMPLES_DIR / "multiple_directories.py")
    with (
        patch("sys.argv", [script, *paths]),
        patch("watchdog.observers.Observer") as observer_class,
        patch("time.sleep", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        runpy.run_path(script)
    scheduled = observer_class.return_value.schedule.call_args_list
    assert len(scheduled) == 1
    assert scheduled[0].args[1] == (paths or ["."])[0]
    assert scheduled[0].kwargs == {"recursive": True}


def test_multiple_directories_labels_events(caplog: pytest.LogCaptureFixture) -> None:
    script = str(EXAMPLES_DIR / "multiple_directories.py")
    paths = ["input one", "input two"]
    with (
        patch("sys.argv", [script, *paths]),
        patch("watchdog.observers.Observer") as observer_class,
        patch("time.sleep", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        runpy.run_path(script)

    handlers = [scheduled.args[0] for scheduled in observer_class.return_value.schedule.call_args_list]
    caplog.set_level(logging.INFO)
    events = [FileCreatedEvent("same.txt"), FileMovedEvent("same.txt", "renamed.txt")]
    for handler in handlers:
        for event in events:
            handler.dispatch(event)
    assert caplog.messages == [f"[{path}] {event}" for path in paths for event in events]


def test_multiple_directories_cleans_up_on_loop_error() -> None:
    script = str(EXAMPLES_DIR / "multiple_directories.py")
    error = RuntimeError("monitoring failed")
    with (
        patch("sys.argv", [script, "input one", "input two"]),
        patch("watchdog.observers.Observer") as observer_class,
        patch("time.sleep", side_effect=error),
        pytest.raises(RuntimeError) as caught,
    ):
        runpy.run_path(script)
    assert caught.value is error
    assert observer_class.return_value.mock_calls[-2:] == [call.stop(), call.join()]


@pytest.mark.parametrize("method", ["schedule", "start"])
def test_multiple_directories_cleans_up_on_setup_error(method: str) -> None:
    script = str(EXAMPLES_DIR / "multiple_directories.py")
    error = OSError("watch setup failed")
    with patch("sys.argv", [script, "input one", "input two"]), patch("watchdog.observers.Observer") as observer_class:
        observer = observer_class.return_value
        getattr(observer, method).side_effect = error
        with pytest.raises(OSError, match="watch setup failed") as caught:
            runpy.run_path(script)
    assert caught.value is error
    observer.stop.assert_called_once_with()
    observer.join.assert_not_called()  # Thread.join cannot be called before a successful start.


def test_multiple_directories_receives_native_events(tmp_path: Path) -> None:
    script = str(EXAMPLES_DIR / "multiple_directories.py")
    paths = [tmp_path / "input one", tmp_path / "input two"]
    for path in paths:
        path.mkdir()
    observer = Observer()
    received: Queue[tuple[str, FileSystemEvent]] = Queue()
    emitters = []

    def record_event(_format: str, label: str, event: FileSystemEvent) -> None:
        received.put((label, event))

    def create_files_and_wait(_seconds: float) -> None:
        assert observer.is_alive()
        emitters.extend(observer.emitters)
        for path in paths:
            (path / "same.txt").write_text("test event", encoding="utf-8")
        pending = {str(path) for path in paths}
        while pending:
            label, event = received.get(timeout=5)
            if isinstance(event, FileCreatedEvent) and Path(event.src_path).name == "same.txt":
                pending.discard(label)
        raise KeyboardInterrupt

    try:
        with (
            patch("sys.argv", [script, *(str(path) for path in paths)]),
            patch("watchdog.observers.Observer", return_value=observer),
            patch("logging.info", side_effect=record_event),
            patch("time.sleep", side_effect=create_files_and_wait),
            pytest.raises(KeyboardInterrupt),
        ):
            runpy.run_path(script)
        assert not observer.is_alive()
        assert len(emitters) == 2
        assert all(not emitter.is_alive() for emitter in emitters)
    finally:
        observer.stop()
        if observer.is_alive():
            observer.join(timeout=5)


def test_multiple_directories_stops_a_partially_started_observer(tmp_path: Path) -> None:
    script = str(EXAMPLES_DIR / "multiple_directories.py")
    observer = Observer()
    started = []
    error = OSError("second watch could not start")

    def partial_start() -> None:
        emitter = next(iter(observer.emitters))
        emitter.start()
        started.append(emitter)
        assert emitter.is_alive()
        raise error

    try:
        with (
            patch("sys.argv", [script, str(tmp_path)]),
            patch("watchdog.observers.Observer", return_value=observer),
            patch.object(observer, "start", side_effect=partial_start),
            pytest.raises(OSError, match="second watch could not start") as caught,
        ):
            runpy.run_path(script)
        assert caught.value is error
        assert len(started) == 1
        assert not started[0].is_alive()
        assert not observer.is_alive()
    finally:
        observer.stop()
