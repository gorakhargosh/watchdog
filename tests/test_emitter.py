# -*- coding: utf-8 -*-
#
# Copyright 2014 Thomas Amland <thomas.amland@gmail.com>
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

import os
import time
import pytest
import logging
from tests import Queue
from tests import tmpdir, p  # pytest magic
from .shell import mkdir, touch, mv, rm
from watchdog.utils import platform
from watchdog.events import *
from watchdog.observers.api import ObservedWatch

pytestmark = pytest.mark.skipif(not platform.is_linux() and not platform.is_darwin(), reason="")
if platform.is_linux():
    from watchdog.observers.inotify import InotifyEmitter as Emitter
elif platform.is_darwin():
    from watchdog.observers.fsevents2 import FSEventsEmitter as Emitter

logging.basicConfig(level=logging.DEBUG)


def _setup_emitter(path):
    event_queue = Queue()

    if platform.is_darwin():
        # FSEvents will report old evens (like create for mkdtemp in test
        # setup. Waiting for a considerable time seems to 'flush' the events.
        time.sleep(10)

    emitter = Emitter(event_queue, ObservedWatch(path, recursive=True))
    emitter.start()
    return event_queue, emitter


def test_create(p):
    event_queue, emitter = _setup_emitter(p(''))
    open(p('a'), 'a').close()

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a').encode()
    assert isinstance(event, FileCreatedEvent)

    event = event_queue.get(timeout=5)[0]
    assert os.path.normpath(event.src_path) == os.path.normpath(p('').encode())
    assert isinstance(event, DirModifiedEvent)

    emitter.stop()


def test_delete(p):
    touch(p('a'))
    event_queue, emitter = _setup_emitter(p(''))
    rm(p('a'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a').encode()
    assert isinstance(event, FileDeletedEvent)

    event = event_queue.get(timeout=5)[0]
    assert os.path.normpath(event.src_path) == os.path.normpath(p('').encode())
    assert isinstance(event, DirModifiedEvent)

    emitter.stop()


def test_modify(p):
    touch(p('a'))
    event_queue, emitter = _setup_emitter(p(''))
    touch(p('a'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a').encode()
    assert isinstance(event, FileModifiedEvent)

    emitter.stop()


def test_move(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    event_queue, emitter = _setup_emitter(p(''))

    mv(p('dir1', 'a'), p('dir2', 'b'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir1', 'a').encode()
    assert event.dest_path == p('dir2', 'b').encode()
    assert isinstance(event, FileMovedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir1').encode()
    assert isinstance(event, DirModifiedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir2').encode()
    assert isinstance(event, DirModifiedEvent)

    emitter.stop()


def test_move_to(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    event_queue, emitter = _setup_emitter(p('dir2'))

    mv(p('dir1', 'a'), p('dir2', 'b'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileCreatedEvent)
    assert event.src_path == p('dir2', 'b').encode()

    emitter.stop()


def test_move_from(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    event_queue, emitter = _setup_emitter(p('dir1'))

    mv(p('dir1', 'a'), p('dir2', 'b'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileDeletedEvent)
    assert event.src_path == p('dir1', 'a').encode()

    emitter.stop()


def test_separate_consecutive_moves(p):
    mkdir(p('dir1'))
    touch(p('dir1', 'a'))
    touch(p('b'))

    event_queue, emitter = _setup_emitter(p('dir1'))

    mv(p('dir1', 'a'), p('c'))
    mv(p('b'), p('dir1', 'd'))

    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileDeletedEvent)
    assert event.src_path == p('dir1', 'a').encode()

    assert isinstance(event_queue.get(timeout=5)[0], DirModifiedEvent)

    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileCreatedEvent)
    assert event.src_path == p('dir1', 'd').encode()

    assert isinstance(event_queue.get(timeout=5)[0], DirModifiedEvent)

    emitter.stop()


@pytest.mark.skipif(platform.is_linux(), reason="bug. inotify will deadlock")
def test_delete_self(p):
    mkdir(p('dir1'))
    event_queue, emitter = _setup_emitter(p('dir1'))
    rm(p('dir1'), True)
    event_queue.get(timeout=5)[0]
    emitter.stop()


#TODO
@pytest.mark.xfail # when fixed, remove all encode/decode calls from above tests
def test_passing_unicode_should_give_unicode(p):
    from watchdog.utils.unicode_paths import str_cls
    path = str_cls(p(''))
    assert isinstance(p(''), str_cls)

    event_queue = Queue()
    emitter = Emitter(event_queue, ObservedWatch(path, recursive=True))
    emitter.start()
    touch(p('a'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event.src_path, str_cls)


#TODO
@pytest.mark.xfail # when fixed, remove all encode/decode calls from above tests
def test_passing_bytes_should_give_bytes(p):
    from watchdog.utils.unicode_paths import bytes_cls
    path = bytes_cls(p(''), 'ascii')
    assert isinstance(p(''), bytes_cls)

    event_queue = Queue()
    emitter = Emitter(event_queue, ObservedWatch(path, recursive=True))
    emitter.start()
    touch(p('a'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event.src_path, bytes_cls)
