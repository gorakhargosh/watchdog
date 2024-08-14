from __future__ import annotations

import os
import os.path
from queue import Empty, Queue
from time import sleep

import pytest
from watchdog.events import DirCreatedEvent, DirMovedEvent
from watchdog.observers.api import ObservedWatch
from watchdog.utils import platform

from .shell import mkdir, mkdtemp, mv, rm

# make pytest aware this is windows only
if not platform.is_windows():
    pytest.skip("Windows only.", allow_module_level=True)

from watchdog.observers.read_directory_changes import WindowsApiEmitter

SLEEP_TIME = 2

# Path with non-ASCII
temp_dir = os.path.join(mkdtemp(), "Strange \N{SNOWMAN}")
os.makedirs(temp_dir)


def p(*args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return os.path.join(temp_dir, *args)


@pytest.fixture()
def event_queue():
    return Queue()


@pytest.fixture()
def emitter(event_queue):
    watch = ObservedWatch(temp_dir, recursive=True)
    em = WindowsApiEmitter(event_queue, watch, timeout=0.2)
    yield em
    em.stop()


def test___init__(event_queue, emitter):
    emitter.start()
    sleep(SLEEP_TIME)
    mkdir(p("fromdir"))

    sleep(SLEEP_TIME)
    mv(p("fromdir"), p("todir"))

    sleep(SLEEP_TIME)
    emitter.stop()

    # What we need here for the tests to pass is a collection type
    # that is:
    #   * unordered
    #   * non-unique
    # A multiset! Python's collections.Counter class seems appropriate.
    expected = {
        DirCreatedEvent(p("fromdir")),
        DirMovedEvent(p("fromdir"), p("todir")),
    }

    got = set()

    while True:
        try:
            event, _ = event_queue.get_nowait()
        except Empty:
            break
        else:
            got.add(event)

    assert expected == got


def test_root_deleted(event_queue, emitter):
    r"""Test the event got when removing the watched folder.
    The regression to prevent is:

        Exception in thread Thread-1:
        Traceback (most recent call last):
        File "watchdog\observers\winapi.py", line 333, in read_directory_changes
            ctypes.byref(nbytes), None, None)
        File "watchdog\observers\winapi.py", line 105, in _errcheck_bool
            raise ctypes.WinError()
        PermissionError: [WinError 5] Access refused.

        During handling of the above exception, another exception occurred:

        Traceback (most recent call last):
        File "C:\Python37-32\lib\threading.py", line 926, in _bootstrap_inner
            self.run()
        File "watchdog\observers\api.py", line 145, in run
            self.queue_events(self.timeout)
        File "watchdog\observers\read_directory_changes.py", line 76, in queue_events
            winapi_events = self._read_events()
        File "watchdog\observers\read_directory_changes.py", line 73, in _read_events
            return read_events(self._whandle, self.watch.path, recursive=self.watch.is_recursive)
        File "watchdog\observers\winapi.py", line 387, in read_events
            buf, nbytes = read_directory_changes(handle, path, recursive=recursive)
        File "watchdog\observers\winapi.py", line 340, in read_directory_changes
            return _generate_observed_path_deleted_event()
        File "watchdog\observers\winapi.py", line 298, in _generate_observed_path_deleted_event
            event = FileNotifyInformation(0, FILE_ACTION_DELETED_SELF, len(path), path.value)
        TypeError: expected bytes, str found
    """

    emitter.start()
    sleep(SLEEP_TIME)

    # This should not fail
    rm(p(), recursive=True)
    sleep(SLEEP_TIME)

    # The emitter is automatically stopped, with no error
    assert not emitter.should_keep_running()
