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

from watchdog.utils import platform
import pytest
pytestmark = pytest.mark.skipif(not platform.is_linux(), reason="")

import os
from tests import Queue
from tests import tmpdir, p  # pytest magic
from .shell import mkdir, touch, mv
from watchdog.observers.api import ObservedWatch
from watchdog.observers.inotify import InotifyEmitter


def test_create(p):
    event_queue = Queue()
    emitter = InotifyEmitter(event_queue, ObservedWatch(p(''), recursive=True))
    emitter.start()
    touch(p('a'))

    event = event_queue.get(timeout=5)[0]
    assert event.event_type == 'created'
    assert not event.is_directory
    assert event.src_path == p('a').encode()

    event = event_queue.get(timeout=5)[0]
    assert event.event_type == 'modified'
    assert event.is_directory
    assert os.path.normpath(event.src_path) == os.path.normpath(p('').encode())


def test_move(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    event_queue = Queue()
    emitter = InotifyEmitter(event_queue, ObservedWatch(p(''), recursive=True))
    emitter.start()

    mv(p('dir1', 'a'), p('dir2', 'b'))
    event = event_queue.get(timeout=5)[0]
    assert event.event_type == 'moved'
    assert not event.is_directory
    assert event.src_path == p('dir1', 'a').encode()
    assert event.dest_path == p('dir2', 'b').encode()

    event = event_queue.get(timeout=5)[0]
    assert event.event_type == 'modified'
    assert event.is_directory
    assert event.src_path == p('dir1').encode()

    event = event_queue.get(timeout=5)[0]
    assert event.event_type == 'modified'
    assert event.is_directory
    assert event.src_path == p('dir2').encode()


@pytest.mark.xfail # when fixed, remove all encode/decode calls from above tests
def test_passing_unicode_should_give_unicode(p):
    from watchdog.utils.unicode_paths import str_cls
    path = str_cls(p(''))
    assert isinstance(p(''), str_cls)

    event_queue = Queue()
    emitter = InotifyEmitter(event_queue, ObservedWatch(path, recursive=True))
    emitter.start()
    touch(p('a'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event.src_path, str_cls)


@pytest.mark.xfail # when fixed, remove all encode/decode calls from above tests
def test_passing_bytes_should_give_bytes(p):
    from watchdog.utils.unicode_paths import bytes_cls
    path = bytes_cls(p(''), 'ascii')
    assert isinstance(p(''), bytes_cls)

    event_queue = Queue()
    emitter = InotifyEmitter(event_queue, ObservedWatch(path, recursive=True))
    emitter.start()
    touch(p('a'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event.src_path, bytes_cls)
