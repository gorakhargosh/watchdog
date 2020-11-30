# coding: utf-8
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc & contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
from watchdog.utils import platform

if not platform.is_windows():  # noqa
    pytest.skip("Windows only.", allow_module_level=True)

import os
import os.path
from queue import Empty, Queue
from time import sleep

from watchdog.events import (
    DirCreatedEvent,
    DirMovedEvent,
)
from watchdog.observers.api import ObservedWatch
from watchdog.observers.read_directory_changes import WindowsApiEmitter

from .shell import (
    mkdir,
    mkdtemp,
    mv,
    rm
)


SLEEP_TIME = 2

# Path with non-ASCII
temp_dir = os.path.join(mkdtemp(), u"Strange \N{SNOWMAN}")
os.makedirs(temp_dir)


def p(*args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return os.path.join(temp_dir, *args)


@pytest.fixture
def event_queue():
    yield Queue()


@pytest.fixture
def emitter(event_queue):
    watch = ObservedWatch(temp_dir, True)
    em = WindowsApiEmitter(event_queue, watch, timeout=0.2)
    yield em
    em.stop()


def test___init__(event_queue, emitter):
    emitter.start()
    sleep(SLEEP_TIME)
    mkdir(p('fromdir'))

    sleep(SLEEP_TIME)
    mv(p('fromdir'), p('todir'))

    sleep(SLEEP_TIME)
    emitter.stop()

    # What we need here for the tests to pass is a collection type
    # that is:
    #   * unordered
    #   * non-unique
    # A multiset! Python's collections.Counter class seems appropriate.
    expected = {
        DirCreatedEvent(p('fromdir')),
        DirMovedEvent(p('fromdir'), p('todir')),
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
                return read_events(self._handle, self.watch.path, self.watch.is_recursive)
            File "watchdog\observers\winapi.py", line 387, in read_events
                buf, nbytes = read_directory_changes(handle, path, recursive)
            File "watchdog\observers\winapi.py", line 340, in read_directory_changes
                return _generate_observed_path_deleted_event()
            File "watchdog\observers\winapi.py", line 298, in _generate_observed_path_deleted_event
                event = FILE_NOTIFY_INFORMATION(0, FILE_ACTION_DELETED_SELF, len(path), path.value)
            TypeError: expected bytes, str found
    """

    emitter.start()
    sleep(SLEEP_TIME)

    # This should not fail
    rm(p(), recursive=True)
    sleep(SLEEP_TIME)

    # The emitter is automatically stopped, with no error
    assert not emitter.should_keep_running()
