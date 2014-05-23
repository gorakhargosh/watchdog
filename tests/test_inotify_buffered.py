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
import random
from tests import tmpdir, p  # pytest magic
from .shell import mkdir, touch, mv
from watchdog.observers.inotify_buffered import InotifyBuffered


def wait_for_move_event(read_event):
    while True:
        event = read_event()
        if isinstance(event, tuple) or event.is_move:
            return event


@pytest.mark.timeout(5)
def test_move_from(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))

    inotify = InotifyBuffered(p('dir1'))
    mv(p('dir1', 'a'), p('dir2', 'b'))
    event = wait_for_move_event(inotify.read_event)
    assert event.is_moved_from
    assert event.src_path == p('dir1', 'a').encode()
    inotify.close()


@pytest.mark.timeout(5)
def test_move_to(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))

    inotify = InotifyBuffered(p('dir2'))
    mv(p('dir1', 'a'), p('dir2', 'b'))
    event = wait_for_move_event(inotify.read_event)
    assert event.is_moved_to
    assert event.src_path == p('dir2', 'b').encode()
    inotify.close()


@pytest.mark.timeout(5)
def test_move_internal(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))

    inotify = InotifyBuffered(p(''), recursive=True)
    mv(p('dir1', 'a'), p('dir2', 'b'))
    frm, to = wait_for_move_event(inotify.read_event)
    assert frm.src_path.decode() == p('dir1', 'a')
    assert to.src_path.decode() == p('dir2', 'b')
    inotify.close()
    

@pytest.mark.timeout(10)
def test_move_internal_batch(p):
    n = 100
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    files = ['%d' % i for i in range(n)]
    for f in files:
        touch(p('dir1', f))

    inotify = InotifyBuffered(p(''), recursive=True)

    random.shuffle(files)
    for f in files:
        mv(p('dir1', f), p('dir2', f))

    # Check that all n events are paired
    i = 0
    while i < n:
        frm, to = wait_for_move_event(inotify.read_event)
        assert os.path.dirname(frm.src_path).endswith(b'/dir1')
        assert os.path.dirname(to.src_path).endswith(b'/dir2')
        assert frm.name == to.name
        i += 1
    inotify.close()
