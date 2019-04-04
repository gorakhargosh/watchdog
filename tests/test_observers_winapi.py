#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc.
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

if not platform.is_windows():
    pytest.skip("Windows only.", allow_module_level=True)

import os.path
from time import sleep

from watchdog.events import (
    DirCreatedEvent,
    DirMovedEvent,
)
from watchdog.observers.api import ObservedWatch
from watchdog.observers.read_directory_changes import WindowsApiEmitter

from . import Empty, Queue
from .shell import (
    mkdir,
    mkdtemp,
    mv
)


temp_dir = mkdtemp()


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
    SLEEP_TIME = 2

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
