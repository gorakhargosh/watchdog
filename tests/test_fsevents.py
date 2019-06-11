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

from watchdog.observers import Observer
from watchdog.observers.api import ObservedWatch
from watchdog.observers.fsevents import FSEventsEmitter

from . import Queue
from .shell import mkdtemp, rm

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def setup_function(function):
    global p, event_queue
    tmpdir = os.path.realpath(mkdtemp())
    p = partial(os.path.join, tmpdir)
    event_queue = Queue()


def teardown_function(function):
    emitter.stop()
    emitter.join(5)
    rm(p(""), recursive=True)
    assert not emitter.is_alive()


def start_watching(path=None, use_full_emitter=False):
    global emitter
    path = p("") if path is None else path
    emitter = FSEventsEmitter(event_queue, ObservedWatch(path, recursive=True))
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
    w = observer.schedule(event_queue, a, recursive=False)
    rmdir(a)
    time.sleep(0.1)
    observer.unschedule(w)
