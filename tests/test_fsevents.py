# coding: utf-8

import pytest
from watchdog.utils import platform

if not platform.is_darwin():  # noqa
    pytest.skip("macOS only.", allow_module_level=True)

import logging
import os
import time
from functools import partial
from os import mkdir, rmdir
from queue import Queue
from random import random
from threading import Thread
from time import sleep
from unittest.mock import patch

import _watchdog_fsevents as _fsevents
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import ObservedWatch
from watchdog.observers.fsevents import FSEventsEmitter

from .shell import mkdtemp, rm, touch

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def setup_function(function):
    global p, event_queue
    tmpdir = os.path.realpath(mkdtemp())
    p = partial(os.path.join, tmpdir)
    event_queue = Queue()


def teardown_function(function):
    try:
        emitter.stop()
        emitter.join(5)
        assert not emitter.is_alive()
    except NameError:
        pass  # `name 'emitter' is not defined` unless we call `start_watching`
    rm(p(""), recursive=True)


def start_watching(path=None, recursive=True, use_full_emitter=False):
    global emitter
    path = p("") if path is None else path
    emitter = FSEventsEmitter(event_queue, ObservedWatch(path, recursive=recursive), suppress_history=True)
    emitter.start()


@pytest.fixture
def observer():
    obs = Observer()
    obs.start()
    yield obs
    obs.stop()
    try:
        obs.join()
    except RuntimeError:
        pass


@pytest.mark.parametrize('event,expectation', [
    # invalid flags
    (_fsevents.NativeEvent('', 0, 0, 0), False),
    # renamed
    (_fsevents.NativeEvent('', 0, 0x00000800, 0), False),
    # renamed, removed
    (_fsevents.NativeEvent('', 0, 0x00000800 | 0x00000200, 0), True),
    # renamed, removed, created
    (_fsevents.NativeEvent('', 0, 0x00000800 | 0x00000200 | 0x00000100, 0), True),
    # renamed, removed, created, itemfindermod
    (_fsevents.NativeEvent('', 0, 0x00000800 | 0x00000200 | 0x00000100 | 0x00002000, 0), True),
    # xattr, removed, modified, itemfindermod
    (_fsevents.NativeEvent('', 0, 0x00008000 | 0x00000200 | 0x00001000 | 0x00002000, 0), False),
])
def test_coalesced_event_check(event, expectation):
    assert event.is_coalesced == expectation


def test_add_watch_twice(observer):
    """ Adding the same watch twice used to result in a null pointer return without an exception.

    See https://github.com/gorakhargosh/watchdog/issues/765
    """

    a = p("a")
    mkdir(a)
    h = FileSystemEventHandler()
    w = ObservedWatch(a, recursive=False)

    def callback(path, inodes, flags, ids):
        pass

    _fsevents.add_watch(h, w, callback, [w.path])
    with pytest.raises(RuntimeError):
        _fsevents.add_watch(h, w, callback, [w.path])
    _fsevents.remove_watch(w)
    rmdir(a)


def test_watcher_deletion_while_receiving_events_1(caplog, observer):
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

    def cb(*args):
        FSEventsEmitter.stop(emitter)
        orig(*args)

    with caplog.at_level(logging.ERROR), patch.object(FSEventsEmitter, "events_callback", new=cb):
        start_watching(tmpdir)
        # Less than 100 is not enough events to trigger the error
        for n in range(100):
            touch(p("{}.txt".format(n)))
        emitter.stop()
        assert not caplog.records


def test_watcher_deletion_while_receiving_events_2(caplog):
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
        start_watching(tmpdir)

        def create_files():
            # Less than 2000 is not enough events to trigger the error
            for n in range(2000):
                touch(p(str(n) + ".txt"))

        def stop(em):
            sleep(random())
            em.stop()

        th1 = Thread(target=create_files)
        th2 = Thread(target=stop, args=(emitter,))

        try:
            with caplog.at_level(logging.ERROR):
                th1.start()
                th2.start()
                th1.join()
                th2.join()
                assert not caplog.records
        finally:
            emitter.stop()

    # 20 attempts to make the random failure happen
    for _ in range(20):
        try_to_fail()
        sleep(random())


def test_remove_watch_twice():
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
    start_watching()
    # This one must work
    emitter.stop()
    # This is allowed to call several times .stop()
    emitter.stop()


def test_unschedule_removed_folder(observer):
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


def test_converting_cfstring_to_pyunicode():
    """See https://github.com/gorakhargosh/watchdog/issues/762
    """

    tmpdir = p()
    start_watching(tmpdir)

    dirname = "TéstClass"

    try:
        mkdir(p(dirname))
        event, _ = event_queue.get()
        assert event.src_path.endswith(dirname)
    finally:
        emitter.stop()


def test_recursive_check_accepts_relative_paths():
    """See https://github.com/gorakhargosh/watchdog/issues/797

    The test code provided in the defect observes the current working directory
    using ".". Since the watch path wasn't normalized then that failed.
    This test emulates the scenario.
    """
    from watchdog.events import (
        PatternMatchingEventHandler,
        FileCreatedEvent,
        FileModifiedEvent
    )

    class TestEventHandler(PatternMatchingEventHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # the TestEventHandler instance is set to ignore_directories,
            # as such we won't get a DirModifiedEvent(p()) here.
            self.expected_events = [
                FileCreatedEvent(p('foo.json')),
                FileModifiedEvent(p('foo.json'))
            ]
            self.observed_events = set()

        def on_any_event(self, event):
            self.expected_events.remove(event)
            self.observed_events.add(event)

        def done(self):
            return not self.expected_events

    cwd = os.getcwd()
    os.chdir(p())
    event_handler = TestEventHandler(patterns=["*.json"], ignore_patterns=[], ignore_directories=True)
    observer = Observer()
    observer.schedule(event_handler, ".")
    observer.start()
    time.sleep(0.1)

    try:
        touch(p('foo.json'))
        timeout_at = time.time() + 5
        while not event_handler.done() and time.time() < timeout_at:
            time.sleep(0.1)

        assert event_handler.done()
    finally:
        os.chdir(cwd)
        observer.stop()
        observer.join()


def test_watchdog_recursive():
    """ See https://github.com/gorakhargosh/watchdog/issues/706
    """
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import os.path

    class Handler(FileSystemEventHandler):
        def __init__(self):
            FileSystemEventHandler.__init__(self)
            self.changes = []

        def on_any_event(self, event):
            self.changes.append(os.path.basename(event.src_path))

    handler = Handler()
    observer = Observer()

    watches = []
    watches.append(observer.schedule(handler, str(p('')), recursive=True))

    try:
        observer.start()
        time.sleep(0.1)

        touch(p('my0.txt'))
        mkdir(p('dir_rec'))
        touch(p('dir_rec', 'my1.txt'))

        expected = {"dir_rec", "my0.txt", "my1.txt"}
        timeout_at = time.time() + 5
        while not expected.issubset(handler.changes) and time.time() < timeout_at:
            time.sleep(0.2)

        assert expected.issubset(handler.changes), "Did not find expected changes. Found: {}".format(handler.changes)
    finally:
        for watch in watches:
            observer.unschedule(watch)
        observer.stop()
        observer.join(1)
