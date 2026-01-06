from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from queue import Empty, Queue
from typing import Any, Protocol

from watchdog.events import FileSystemEvent
from watchdog.observers.api import EventEmitter, ObservedWatch
from watchdog.utils import platform

Emitter: type[EventEmitter]

if platform.is_linux():
    from watchdog.observers.inotify import InotifyEmitter as Emitter
    from watchdog.observers.inotify import InotifyFullEmitter
elif platform.is_darwin():
    from watchdog.observers.fsevents import FSEventsEmitter as Emitter
elif platform.is_windows():
    from watchdog.observers.read_directory_changes import WindowsApiEmitter as Emitter
elif platform.is_bsd():
    from watchdog.observers.kqueue import KqueueEmitter as Emitter


class P(Protocol):
    def __call__(self, *args: str) -> str: ...


class StartWatching(Protocol):
    def __call__(
        self,
        *,
        path: bytes | str | None = ...,
        use_full_emitter: bool = ...,
        recursive: bool = ...,
    ) -> EventEmitter: ...


class ExpectEvent(Protocol):
    def __call__(self, expected_event: FileSystemEvent, *, timeout: float = ...) -> None: ...


TestEventQueue = Queue[tuple[FileSystemEvent, ObservedWatch]]


@dataclasses.dataclass()
class Helper:
    tmp: str
    emitters: list[EventEmitter] = dataclasses.field(default_factory=list)
    event_queue: TestEventQueue = dataclasses.field(default_factory=Queue)

    def joinpath(self, *args: str) -> str:
        return os.path.join(self.tmp, *args)

    def start_watching(
        self,
        *,
        path: bytes | str | None = None,
        use_full_emitter: bool = False,
        recursive: bool = True,
    ) -> EventEmitter:
        # TODO: check if other platforms expect the trailing slash (e.g. `p('')`)
        path = self.tmp if path is None else path

        watcher = ObservedWatch(path, recursive=recursive)
        emitter_cls = InotifyFullEmitter if platform.is_linux() and use_full_emitter else Emitter
        emitter = emitter_cls(self.event_queue, watcher)

        if platform.is_darwin():
            # TODO: I think this could be better...  .suppress_history should maybe
            #       become a common attribute.
            from watchdog.observers.fsevents import FSEventsEmitter

            assert isinstance(emitter, FSEventsEmitter)
            emitter.suppress_history = True

        self.emitters.append(emitter)
        emitter.start()

        return emitter

    def events_checker(self) -> _EventsChecker:
        """Utility function to create a new event checker instance.  Use add()
        to add events to check for.  Call check_events() to check that those
        events have been emitted.
        """
        return _EventsChecker(self)

    def expect_event(self, expected_event: FileSystemEvent, timeout: float = 2) -> None:
        """Utility function to wait up to `timeout` seconds for an `event_type` for `path` to show up in the queue.

        Provides some robustness for the otherwise flaky nature of asynchronous notifications.
        """
        assert self.event_queue.get(timeout=timeout)[0] == expected_event

    def close(self) -> None:
        for emitter in self.emitters:
            emitter.stop()

        for emitter in self.emitters:
            if emitter.is_alive():
                emitter.join(5)

        alive = [emitter.is_alive() for emitter in self.emitters]
        self.emitters = []
        assert alive == [False] * len(alive)


def run_isolated_test(path):
    isolated_test_prefix = os.path.join("tests", "isolated")
    path = os.path.abspath(os.path.join(isolated_test_prefix, path))

    src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    new_env = os.environ.copy()
    new_env["PYTHONPATH"] = os.pathsep.join([*sys.path, src_dir])

    new_argv = [sys.executable, path]

    p = subprocess.Popen(
        new_argv,
        env=new_env,
    )

    # in case test goes haywire, don't let it run forever
    timeout = 10
    try:
        p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        raise

    assert p.returncode == 0


class EventsChecker(Protocol):
    def __call__(self) -> _EventsChecker: ...


@dataclasses.dataclass()
class _ExpectedEvent:
    """Specifies what kind of event we are expecting.  The `expected_class` is required,
    everything else is optional (not checked if it is None).
    """
    expected_class: type
    src_path: str | None = None
    dest_path: str | None = None


class _EventsChecker:
    # If True, output verbose debugging to stderr.
    DEBUG = False

    expected_events: list[_ExpectedEvent]

    def __init__(self, helper: Helper):
        self.tmp = helper.tmp
        self.event_queue = helper.event_queue
        self.expected_events = []

    def _debug(self, *args: Any) -> None:
        if self.DEBUG:
            print(*args, file=sys.stderr)  # noqa: T201

    def _make_path(self, path: str | None) -> str | None:
        if path is None:
            return None
        if path == "":
            # an empty path is kept as-is
            return ""
        # convert to platform specific path and normalize
        parts = path.split("/")
        path = os.path.join(self.tmp, *parts)
        return os.path.normpath(path)

    def add(self, expected_class: type, src_path: str | None = None, dest_path: str | None = None) -> None:
        """Add details for an expected event.  The `expected_class` argument
        is required, everything else is optional.  The order that events are
        received does not matter but adding the same kind of event more than
        once will require that it appears more than once.

        Note that paths are provided as relative to `tmp` and using the forward
        slash separator. They will be converted to absolute paths using `tmp`
        and normalized.  An empty path, i.e. "", is kept as-is.
        """
        self.expected_events.append(_ExpectedEvent(expected_class, src_path, dest_path))

    def check_events(self, timeout: float = 2) -> None:
        """Read events from the events queue (waiting for up to `timeout` for new events
        to appear).  Confirm that expected events, as specified by calling
        add(), appear in the sequence of events receieved.

        Note that order of events does not matter and receiving extra events is
        considered okay.
        """
        expected_events = list(self.expected_events)
        if self.DEBUG:
            self._debug("expecting events:")
            for e in expected_events:
                self._debug("  ", e.expected_class.__name__, e.src_path, self._make_path(e.src_path))

        found_events = []
        while True:
            # Read all the available events until we timeout.
            try:
                event = self.event_queue.get(timeout=timeout)[0]
            except Empty:
                self._debug("event queue timeout")
                break
            self._debug("got event", event.__class__.__name__, event.src_path)
            found_events.append(event)

        # Check that events received contain the expected events.  This is
        # an inefficient way to do it, O(n*m) but since the list of expected
        # events should be fairly short, this is okay.  Using a list allows
        # the expected events to contain the same kind of event more than
        # once.
        for event in found_events:
            for i, expected_event in enumerate(expected_events):
                if not isinstance(event, expected_event.expected_class):
                    continue  # wrong class
                src_path = self._make_path(expected_event.src_path)
                if src_path is not None and src_path != event.src_path:
                    continue  # wrong src_path
                dest_path = self._make_path(expected_event.dest_path)
                if dest_path is not None and dest_path != event.dest_path:
                    continue  # wrong dest_path
                self._debug("matched event", expected_events[i])
                del expected_events[i]
                break

        if expected_events:
            # Fail, we did not find some of the expected events.
            if self.DEBUG:
                self._debug("missing events:")
                for e in expected_events:
                    self._debug("  ", e.expected_class.__name__, e.src_path)
            assert not expected_events, "some expected events not found"
