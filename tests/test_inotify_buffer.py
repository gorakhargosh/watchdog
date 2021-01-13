# coding: utf-8
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

import pytest
from watchdog.utils import platform

if not platform.is_linux():  # noqa
    pytest.skip("GNU/Linux only.", allow_module_level=True)  # noqa

import os
import random

from watchdog.observers.inotify_buffer import InotifyBuffer

from .shell import mkdir, touch, mv, rm


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

    inotify = InotifyBuffer(p('dir1').encode())
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

    inotify = InotifyBuffer(p('dir2').encode())
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

    inotify = InotifyBuffer(p('').encode(), recursive=True)
    mv(p('dir1', 'a'), p('dir2', 'b'))
    frm, to = wait_for_move_event(inotify.read_event)
    assert frm.src_path == p('dir1', 'a').encode()
    assert to.src_path == p('dir2', 'b').encode()
    inotify.close()


@pytest.mark.timeout(10)
def test_move_internal_batch(p):
    n = 100
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    files = ['%d' % i for i in range(n)]
    for f in files:
        touch(p('dir1', f))

    inotify = InotifyBuffer(p('').encode(), recursive=True)

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


@pytest.mark.timeout(5)
def test_delete_watched_directory(p):
    mkdir(p('dir'))
    inotify = InotifyBuffer(p('dir').encode())
    rm(p('dir'), recursive=True)

    # Wait for the event to be picked up
    inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.close()


def test_close_should_terminate_thread(p):
    inotify = InotifyBuffer(p('').encode(), recursive=True)
    assert inotify.is_alive()
    inotify.close()
    assert not inotify.is_alive()
