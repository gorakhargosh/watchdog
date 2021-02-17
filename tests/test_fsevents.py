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


def start_watching(path=None, use_full_emitter=False):
    global emitter
    path = p("") if path is None else path
    emitter = FSEventsEmitter(event_queue, ObservedWatch(path, recursive=True), suppress_history=True)
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
    with pytest.raises(KeyError):
        # watch no longer exists!
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
