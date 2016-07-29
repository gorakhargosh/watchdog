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

from __future__ import unicode_literals
import os
import time
import pytest
import logging
from tests import Queue
import queue
from functools import partial
from .shell import mkdir, touch, mv, rm, mkdtemp
from watchdog.utils import platform
from watchdog.utils.unicode_paths import str_cls
from watchdog.events import *
from watchdog.observers.api import ObservedWatch

if platform.is_linux():
    from watchdog.observers.inotify import InotifyEmitter as Emitter
    from watchdog.observers.inotify import InotifyFullEmitter
elif platform.is_darwin():
    from watchdog.observers.fsevents2 import FSEventsEmitter as Emitter
elif platform.is_windows():
    from watchdog.observers.read_directory_changes import WindowsApiEmitter as Emitter

logging.basicConfig(level=logging.DEBUG)


def setup_function(function):
    global p, event_queue
    tmpdir = os.path.realpath(mkdtemp())
    p = partial(os.path.join, tmpdir)
    event_queue = Queue()


def start_watching(path=None, use_full_emitter=False):
    path = p('') if path is None else path
    global emitter
    if platform.is_linux() and use_full_emitter:
        emitter = InotifyFullEmitter(event_queue, ObservedWatch(path, recursive=True))
    else:
        emitter = Emitter(event_queue, ObservedWatch(path, recursive=True))

    if platform.is_darwin():
        # FSEvents will report old evens (like create for mkdtemp in test
        # setup. Waiting for a considerable time seems to 'flush' the events.
        time.sleep(10)
    emitter.start()
    if platform.is_windows():
        # Guess windows needs its special time
        time.sleep(1)


def teardown_function(function):
    emitter.stop()
    emitter.join(5)
    rm(p(''), recursive=True)
    assert not emitter.is_alive()

def test_create():
    start_watching()
    open(p('a'), 'a').close()

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a')
    assert isinstance(event, FileCreatedEvent)

    if not platform.is_windows():
        event = event_queue.get(timeout=5)[0]
        assert os.path.normpath(event.src_path) == os.path.normpath(p(''))
        assert isinstance(event, DirModifiedEvent)


def test_delete():
    touch(p('a'))
    start_watching()
    rm(p('a'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a')
    assert isinstance(event, FileDeletedEvent)

    if not platform.is_windows():
        event = event_queue.get(timeout=5)[0]
        assert os.path.normpath(event.src_path) == os.path.normpath(p(''))
        assert isinstance(event, DirModifiedEvent)


def test_modify():
    touch(p('a'))
    start_watching()
    touch(p('a'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a')
    assert isinstance(event, FileModifiedEvent)


def test_move():
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    start_watching()

    mv(p('dir1', 'a'), p('dir2', 'b'))

    event = event_queue.get(timeout=5)[0]

    if not platform.is_windows():
        assert event.src_path == p('dir1', 'a')
        assert event.dest_path == p('dir2', 'b')
        assert isinstance(event, FileMovedEvent)
    else:
        assert event.src_path == p('dir1', 'a')
        assert isinstance(event, FileDeletedEvent)
        event = event_queue.get(timeout=5)[0]
        assert event.src_path == p('dir2', 'b')
        assert isinstance(event, FileCreatedEvent)

    # DirModified events happen for both dirs, but in no particular order
    event = event_queue.get(timeout=5)[0]
    assert event.src_path in [p('dir2'), p('dir1')]
    assert isinstance(event, DirModifiedEvent)

    # TODO: currently windows is only emitting one DirModified
    if not platform.is_windows():
        event = event_queue.get(timeout=5)[0]
        assert event.src_path in [p('dir2'), p('dir1')]
        assert isinstance(event, DirModifiedEvent)

def test_move_to():
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    start_watching(p('dir2'))

    mv(p('dir1', 'a'), p('dir2', 'b'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileCreatedEvent)
    assert event.src_path == p('dir2', 'b')

@pytest.mark.skipif(platform.is_windows(),
                    reason="Windows doesn't use the full emitter in tests")
def test_move_to_full():
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    start_watching(p('dir2'), use_full_emitter=True)

    mv(p('dir1', 'a'), p('dir2', 'b'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileMovedEvent)
    assert event.dest_path == p('dir2', 'b')
    assert event.src_path == None #Should equal none since the path was not watched

def test_move_from():
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    start_watching(p('dir1'))

    mv(p('dir1', 'a'), p('dir2', 'b'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileDeletedEvent)
    assert event.src_path == p('dir1', 'a')

@pytest.mark.skipif(platform.is_windows(),
                    reason="Windows doesn't use the full emitter in tests")
def test_move_from_full():
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    start_watching(p('dir1'), use_full_emitter=True)
    mv(p('dir1', 'a'), p('dir2', 'b'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileMovedEvent)
    assert event.src_path == p('dir1', 'a')
    assert event.dest_path == None #Should equal None since path not watched

def test_separate_consecutive_moves():
    mkdir(p('dir1'))
    touch(p('dir1', 'a'))
    touch(p('b'))

    start_watching(p('dir1'))

    mv(p('dir1', 'a'), p('c'))
    mv(p('b'), p('dir1', 'd'))

    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileDeletedEvent)
    assert event.src_path == p('dir1', 'a')

    # Windows will not emit a DirModified Event for the root
    if not platform.is_windows():
        assert isinstance(event_queue.get(timeout=5)[0], DirModifiedEvent)

    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileCreatedEvent)
    assert event.src_path == p('dir1', 'd')

    # Windows will not emit a DirModified Event for the root
    if not platform.is_windows():
        assert isinstance(event_queue.get(timeout=5)[0], DirModifiedEvent)

def test_move_file_to_renamed_dir():
    start_watching()
    mkdir(p('dir1'))
    touch(p('a'))
    mv(p('dir1'), p('dir2'))
    mv(p('a'), p('dir2','a'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir1')
    assert isinstance(event, DirCreatedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a')
    assert isinstance(event, FileCreatedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a')
    assert isinstance(event, FileModifiedEvent)

    # TODO: fix windows event observer to not mash up the move incorrectly
    # Currently, the file move into dir2 is showing a src of dir1, but it never
    # lived there. The event_queue contains the remaining events that describe the
    # file delete from the root and the creation in dir2
    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a')
    assert event.dst_path == p('dir2', 'a')
    assert isinstance(event, FileMovedEvent)

@pytest.mark.skipif(platform.is_linux(), reason="bug. inotify will deadlock")
@pytest.mark.skipif(platform.is_windows(),
                    reason="Windows gives access denied deleting files and directories open by other applications")
def test_delete_self():
    mkdir(p('dir1'))
    start_watching(p('dir1'))
    rm(p('dir1'), True)
    event_queue.get(timeout=5)[0]


def test_passing_unicode_should_give_unicode():
    start_watching(p(''))
    touch(p('a'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event.src_path, str_cls)


@pytest.mark.skipif(platform.is_windows(),
                    reason="Windows ctypes are looking for a unicode string as the path")
def test_passing_bytes_should_give_bytes():
    start_watching(p('').encode())
    touch(p('a'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event.src_path, bytes)