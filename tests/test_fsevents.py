from __future__ import annotations

import contextlib

import pytest

from watchdog.events import DirCreatedEvent
from watchdog.utils import platform

if not platform.is_darwin():
    pytest.skip("macOS only.", allow_module_level=True)

import gc
import logging
import os
import subprocess
import sys
import sysconfig
import threading
import time
import weakref
from os import mkdir, rmdir
from random import random
from threading import Thread
from time import sleep
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import _watchdog_fsevents as _fsevents  # type: ignore[import-not-found]

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver, EventQueue, ObservedWatch
from watchdog.observers.fsevents import FSEventsEmitter

from .shell import touch

if TYPE_CHECKING:
    from .utils import EventsChecker, ExpectEvent, P, StartWatching

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture
def observer():
    obs = Observer()
    obs.start()
    yield obs
    obs.stop()
    with contextlib.suppress(RuntimeError):
        obs.join()


@pytest.mark.parametrize(
    ("event", "expectation"),
    [
        # invalid flags
        (_fsevents.NativeEvent("", 0, 0, 0), False),
        # renamed
        (_fsevents.NativeEvent("", 0, 0x00000800, 0), False),
        # renamed, removed
        (_fsevents.NativeEvent("", 0, 0x00000800 | 0x00000200, 0), True),
        # renamed, removed, created
        (_fsevents.NativeEvent("", 0, 0x00000800 | 0x00000200 | 0x00000100, 0), True),
        # renamed, removed, created, itemfindermod
        (
            _fsevents.NativeEvent("", 0, 0x00000800 | 0x00000200 | 0x00000100 | 0x00002000, 0),
            True,
        ),
        # xattr, removed, modified, itemfindermod
        (
            _fsevents.NativeEvent("", 0, 0x00008000 | 0x00000200 | 0x00001000 | 0x00002000, 0),
            False,
        ),
    ],
)
def test_coalesced_event_check(event, expectation):
    assert event.is_coalesced == expectation


def test_native_event_owns_path() -> None:
    class Path(str):
        __slots__ = ("__weakref__",)

    path = Path("/an/event/path")
    path_ref = weakref.ref(path)
    event = _fsevents.NativeEvent(path, 123, 0, 1)
    del path
    gc.collect()
    assert path_ref() is not None
    assert event.path == "/an/event/path"
    assert '/an/event/path"' in repr(event)
    del event
    gc.collect()
    assert path_ref() is None


def test_native_event_cycles_are_collected() -> None:
    class Path(str):
        __slots__ = ("__weakref__", "event")

    path = Path("/an/event/path")
    path_ref = weakref.ref(path)
    path.event = _fsevents.NativeEvent(path, 123, 0, 1)
    del path
    gc.collect()
    assert path_ref() is None


def test_native_event_allocations_are_released() -> None:
    code = """
import gc
import tracemalloc
import _watchdog_fsevents as f

tracemalloc.start()
for _ in range(1000):
    f.NativeEvent('/event/path', 123, 0, 1)
gc.collect()
before = tracemalloc.get_traced_memory()[0]
for _ in range(10000):
    f.NativeEvent('/event/path', 123, 0, 1)
gc.collect()
retained = tracemalloc.get_traced_memory()[0] - before
assert retained < 100_000, retained
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=30)


def test_native_event_requires_arguments() -> None:
    with pytest.raises(TypeError):
        _fsevents.NativeEvent()


def test_native_event_unsigned_id() -> None:
    event = _fsevents.NativeEvent("/event/path", 123, 0, 2**64 - 1)
    assert event.event_id == 2**64 - 1


def test_stream_does_not_retain_paths_list(p: P) -> None:
    class Paths(list):
        pass

    paths = Paths([p()])
    paths_ref = weakref.ref(paths)
    stream = _fsevents.Stream(paths)
    paths.append(stream)
    del paths
    gc.collect()
    assert paths_ref() is None
    stream.stop()


def test_stream_copies_paths(p: P) -> None:
    original = p("original")
    replacement = p("replacement")
    mkdir(original)
    mkdir(replacement)
    paths = [original]
    stream = _fsevents.Stream(paths)
    paths[:] = [replacement]
    started = threading.Event()
    received = threading.Event()
    target = os.path.realpath(os.path.join(original, "file"))

    def callback(event_paths, *args):
        if target in event_paths:
            received.set()

    thread = Thread(target=stream.run, args=(callback, started.set))
    thread.start()
    try:
        assert started.wait(5)
        touch(target)
        assert received.wait(5)
    finally:
        stream.stop()
        thread.join(5)
    assert not thread.is_alive()


@pytest.mark.parametrize("already_running", [False, True])
def test_observer_propagates_stream_startup_failure(p: P, *, already_running: bool) -> None:
    observer = Observer()
    stream = Mock()
    stream.run.side_effect = OSError("native startup failed")
    try:
        if already_running:
            observer.start()
        with patch.object(_fsevents, "Stream", return_value=stream):
            if already_running:
                with pytest.raises(OSError, match="native startup failed"):
                    observer.schedule(FileSystemEventHandler(), p())
            else:
                observer.schedule(FileSystemEventHandler(), p())
                with pytest.raises(OSError, match="native startup failed"):
                    observer.start()
        assert not observer.emitters
    finally:
        observer.stop()
        if observer.is_alive():
            observer.join(5)
    assert not observer.is_alive()


def test_stream_stop_before_run(p: P) -> None:
    stream = _fsevents.Stream([p("")])
    stream.stop()
    stream.run(lambda *args: None)


def test_stream_can_retry_after_startup_callback_failure(p: P) -> None:
    stream = _fsevents.Stream([p()])

    def fail() -> None:
        message = "startup callback failed"
        raise ValueError(message)

    with pytest.raises(ValueError, match="startup callback failed"):
        stream.run(lambda *args: None, fail)

    # Cleanup must release the running state before another run can start.
    stream.run(lambda *args: None, stream.stop)


def test_emitter_start_waits_for_stream(p: P) -> None:
    """Thread startup must not be mistaken for native stream readiness."""
    entered_run = threading.Event()
    allow_run = threading.Event()
    start_returned = threading.Event()

    class PausedEmitter(FSEventsEmitter):
        def run(self) -> None:
            entered_run.set()
            assert allow_run.wait(5)
            super().run()

    emitter = PausedEmitter(EventQueue(), ObservedWatch(p(), recursive=True))

    def start() -> None:
        emitter.start()
        start_returned.set()

    thread = Thread(target=start)
    thread.start()
    try:
        assert entered_run.wait(5)
        assert not start_returned.wait(0.1)
        allow_run.set()
        assert start_returned.wait(5)
    finally:
        allow_run.set()
        thread.join(5)
        emitter.stop()
        emitter.join(5)

    assert not thread.is_alive()
    assert not emitter.is_alive()


def test_stopping_unstarted_observer_releases_emitter(p: P) -> None:
    observer = Observer()
    observer.schedule(FileSystemEventHandler(), p())
    emitter_ref = weakref.ref(next(iter(observer.emitters)))
    observer.stop()
    del observer
    gc.collect()
    assert emitter_ref() is None


def test_stream_stop_racing_run(p: P) -> None:
    for _ in range(100):
        stream = _fsevents.Stream([p("")])
        thread = Thread(target=stream.run, args=(lambda *args: None,))
        thread.start()
        sleep(random() * 0.001)
        stream.stop()
        thread.join(5)
        assert not thread.is_alive()


def test_two_streams_same_path(p: P) -> None:
    streams = [_fsevents.Stream([p("")]) for _ in range(2)]
    threads = [Thread(target=stream.run, args=(lambda *args: None,)) for stream in streams]
    for thread in threads:
        thread.start()
    sleep(0.1)
    for stream in streams:
        stream.stop()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()


def test_observer_stop_racing_start(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    thread_count = threading.active_count()
    for _ in range(50):
        observer = Observer()
        observer.schedule(FileSystemEventHandler(), p(""))
        thread = Thread(target=observer.start)
        thread.start()
        observer.stop()
        thread.join()
        observer.join(5)
        assert not observer.is_alive()
    deadline = time.monotonic() + 5
    while threading.active_count() > thread_count and time.monotonic() < deadline:
        sleep(0.01)
    # the path must still be watchable afterwards
    start_watching(path=p(""))
    mkdir(p("dir"))
    expect_event(DirCreatedEvent(p("dir")))


def test_rapid_observer_start_stop(p: P) -> None:
    for _ in range(20):
        observer = Observer()
        observer.schedule(FileSystemEventHandler(), p(""))
        observer.start()
        observer.stop()
        observer.join(5)
        assert not observer.is_alive()


def test_module_keeps_gil_disabled() -> None:
    if not sysconfig.get_config_var("Py_GIL_DISABLED"):
        pytest.skip("free-threaded build only")
    env = {key: value for key, value in os.environ.items() if key != "PYTHON_GIL"}
    code = "import sys, _watchdog_fsevents; sys.exit(sys._is_gil_enabled())"
    subprocess.run([sys.executable, "-W", "error", "-c", code], check=True, env=env)


def test_watcher_deletion_while_receiving_events_1(
    caplog: pytest.LogCaptureFixture,
    p: P,
    start_watching: StartWatching,
) -> None:
    """
    When the watcher is stopped while there are events, such exception could happen:

        Traceback (most recent call last):
            File "observers/fsevents.py", line 327, in events_callback
            self.queue_events(self.timeout, events)
            File "observers/fsevents.py", line 187, in queue_events
            src_path = self._encode_path(event.path)
            File "observers/fsevents.py", line 352, in _encode_path
            if isinstance(self.watch.path, bytes):
        AttributeError: 'NoneType' object has no attribute 'path'
    """
    tmpdir = p()

    orig = FSEventsEmitter.events_callback

    def cb(emitter: FSEventsEmitter, *args):
        emitter.stop()
        orig(emitter, *args)

    with caplog.at_level(logging.ERROR), patch.object(FSEventsEmitter, "events_callback", new=cb):
        emitter = start_watching(path=tmpdir)
        # Less than 100 is not enough events to trigger the error
        for n in range(100):
            touch(p(f"{n}.txt"))
        emitter.stop()
        assert not caplog.records


def test_watcher_deletion_while_receiving_events_2(
    caplog: pytest.LogCaptureFixture,
    p: P,
    start_watching: StartWatching,
) -> None:
    """Note: that test takes about 20 seconds to complete.

    Quite similar test to prevent another issue
    when the watcher is stopped while there are events, such exception could happen:

        Traceback (most recent call last):
            File "observers/fsevents.py", line 327, in events_callback
              self.queue_events(self.timeout, events)
            File "observers/fsevents.py", line 235, in queue_events
              self._queue_created_event(event, src_path, src_dirname)
            File "observers/fsevents.py", line 132, in _queue_created_event
              self.queue_event(cls(src_path))
            File "observers/fsevents.py", line 104, in queue_event
              if self._watch.is_recursive:
        AttributeError: 'NoneType' object has no attribute 'is_recursive'
    """

    def try_to_fail():
        tmpdir = p()
        emitter = start_watching(path=tmpdir)

        def create_files():
            # Less than 2000 is not enough events to trigger the error
            for n in range(2000):
                touch(p(f"{n}.txt"))

        def stop(em):
            sleep(random())
            em.stop()

        th1 = Thread(target=create_files)
        th2 = Thread(target=stop, args=(emitter,))

        try:
            th1.start()
            th2.start()
            th1.join()
            th2.join()
        finally:
            emitter.stop()

    # 20 attempts to make the random failure happen
    with caplog.at_level(logging.ERROR):
        for _ in range(20):
            try_to_fail()
            sleep(random())

        assert not caplog.records


def test_remove_watch_twice(start_watching: StartWatching) -> None:
    """
    ValueError: PyCapsule_GetPointer called with invalid PyCapsule object
    The above exception was the direct cause of the following exception:

    src/watchdog/utils/__init__.py:92: in stop
        self.on_thread_stop()

    src/watchdog/observers/fsevents.py:73: SystemError
        def on_thread_stop(self):
    >       _fsevents.remove_watch(self.watch)
    E       SystemError: <built-in function remove_watch> returned a result with an error set

    (FSEvents.framework) FSEventStreamStop(): failed assertion 'streamRef != NULL'
    (FSEvents.framework) FSEventStreamInvalidate(): failed assertion 'streamRef != NULL'
    (FSEvents.framework) FSEventStreamRelease(): failed assertion 'streamRef != NULL'
    """
    emitter = start_watching()
    # This one must work
    emitter.stop()
    # This is allowed to call several times .stop()
    emitter.stop()


def test_unschedule_removed_folder(observer: BaseObserver, p: P) -> None:
    """
    TypeError: PyCObject_AsVoidPtr called with null pointer
    The above exception was the direct cause of the following exception:

    def on_thread_stop(self):
        if self.watch:
            _fsevents.remove_watch(self.watch)
    E       SystemError: <built-in function stop> returned a result with an error set

    (FSEvents.framework) FSEventStreamStop(): failed assertion 'streamRef != NULL'
    (FSEvents.framework) FSEventStreamInvalidate(): failed assertion 'streamRef != NULL'
    (FSEvents.framework) FSEventStreamRelease(): failed assertion 'streamRef != NULL'
    """
    a = p("a")
    mkdir(a)
    w = observer.schedule(FileSystemEventHandler(), a, recursive=False)
    rmdir(a)
    time.sleep(0.1)
    observer.unschedule(w)


def test_converting_cfstring_to_pyunicode(p: P, start_watching: StartWatching, events_checker: EventsChecker) -> None:
    """See https://github.com/gorakhargosh/watchdog/issues/762"""

    tmpdir = p()
    emitter = start_watching(path=tmpdir)

    dirname = "TéstClass"

    try:
        mkdir(p(dirname))
        with events_checker() as ec:
            ec.add(DirCreatedEvent, dirname)
    finally:
        emitter.stop()


def test_recursive_check_accepts_relative_paths(p: P) -> None:
    """See https://github.com/gorakhargosh/watchdog/issues/797

    The test code provided in the defect observes the current working directory
    using ".". Since the watch path wasn't normalized then that failed.
    This test emulates the scenario.
    """
    from watchdog.events import FileCreatedEvent, FileModifiedEvent, PatternMatchingEventHandler

    class TestEventHandler(PatternMatchingEventHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # the TestEventHandler instance is set to ignore_directories,
            # as such we won't get a DirModifiedEvent(p()) here.
            self.expected_events = [
                FileCreatedEvent(p("foo.json")),
                FileModifiedEvent(p("foo.json")),
            ]
            self.observed_events = set()

        def on_any_event(self, event):
            self.expected_events.remove(event)
            self.observed_events.add(event)

        def done(self):
            return not self.expected_events

    cwd = os.getcwd()
    os.chdir(p())
    event_handler = TestEventHandler(patterns=["**/*.json"], ignore_patterns=[], ignore_directories=True)
    observer = Observer()
    observer.schedule(event_handler, ".")
    observer.start()
    time.sleep(0.1)

    try:
        touch(p("foo.json"))
        timeout_at = time.time() + 5
        while not event_handler.done() and time.time() < timeout_at:
            time.sleep(0.1)

        assert event_handler.done()
    finally:
        os.chdir(cwd)
        observer.stop()
        observer.join()


def test_watchdog_recursive(p: P) -> None:
    """See https://github.com/gorakhargosh/watchdog/issues/706"""
    import os.path

    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class Handler(FileSystemEventHandler):
        def __init__(self):
            super().__init__()
            self.changes = []

        def on_any_event(self, event):
            self.changes.append(os.path.basename(event.src_path))

    handler = Handler()
    observer = Observer()

    watches = [observer.schedule(handler, str(p("")), recursive=True)]
    try:
        observer.start()
        time.sleep(0.1)

        touch(p("my0.txt"))
        mkdir(p("dir_rec"))
        touch(p("dir_rec", "my1.txt"))

        expected = {"dir_rec", "my0.txt", "my1.txt"}
        timeout_at = time.time() + 5
        while not expected.issubset(handler.changes) and time.time() < timeout_at:
            time.sleep(0.2)

        assert expected.issubset(handler.changes), f"Did not find expected changes. Found: {handler.changes}"
    finally:
        for watch in watches:
            observer.unschedule(watch)
        observer.stop()
        observer.join(1)
