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
from functools import partial
from . import Queue, Empty
from .shell import mkdir, touch, mv, rm
from watchdog.utils import platform
from watchdog.utils.unicode_paths import str_cls
from watchdog.events import (
    FileDeletedEvent,
    FileModifiedEvent,
    FileCreatedEvent,
    FileMovedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirCreatedEvent,
    DirMovedEvent
)
from watchdog.observers.api import ObservedWatch

if platform.is_linux():
    from watchdog.observers.inotify import (
        InotifyEmitter as Emitter,
        InotifyFullEmitter,
    )
elif platform.is_darwin():
    pytestmark = pytest.mark.skip("FIXME: issue #546.")
    from watchdog.observers.fsevents import FSEventsEmitter as Emitter
elif platform.is_windows():
    from watchdog.observers.read_directory_changes import (
        WindowsApiEmitter as Emitter
    )
elif platform.is_bsd():
    from watchdog.observers.kqueue import (
        KqueueEmitter as Emitter
    )

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def setup_teardown(tmpdir):
    global p, emitter, event_queue
    p = partial(os.path.join, tmpdir)
    event_queue = Queue()

    yield

    emitter.stop()
    emitter.join(5)
    assert not emitter.is_alive()


def start_watching(path=None, use_full_emitter=False, recursive=True):
    path = p('') if path is None else path
    global emitter
    if platform.is_linux() and use_full_emitter:
        emitter = InotifyFullEmitter(event_queue, ObservedWatch(path, recursive=recursive))
    else:
        emitter = Emitter(event_queue, ObservedWatch(path, recursive=recursive))

    if platform.is_darwin():
        # FSEvents will report old events (like create for mkdtemp in test
        # setup. Waiting for a considerable time seems to 'flush' the events.
        time.sleep(10)
    emitter.start()


def rerun_filter(exc, *args):
    time.sleep(5)
    return issubclass(exc[0], Empty) and platform.is_windows()


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
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


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
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


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_modify():
    touch(p('a'))
    start_watching()
    touch(p('a'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a')
    assert isinstance(event, FileModifiedEvent)


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_move():
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    start_watching()
    mv(p('dir1', 'a'), p('dir2', 'b'))

    if not platform.is_windows():
        event = event_queue.get(timeout=5)[0]
        assert event.src_path == p('dir1', 'a')
        assert event.dest_path == p('dir2', 'b')
        assert isinstance(event, FileMovedEvent)
    else:
        event = event_queue.get(timeout=5)[0]
        assert event.src_path == p('dir1', 'a')
        assert isinstance(event, FileDeletedEvent)
        event = event_queue.get(timeout=5)[0]
        assert event.src_path == p('dir2', 'b')
        assert isinstance(event, FileCreatedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path in [p('dir1'), p('dir2')]
    assert isinstance(event, DirModifiedEvent)

    if not platform.is_windows():
        event = event_queue.get(timeout=5)[0]
        assert event.src_path in [p('dir1'), p('dir2')]
        assert isinstance(event, DirModifiedEvent)


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_move_to():
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    start_watching(p('dir2'))
    mv(p('dir1', 'a'), p('dir2', 'b'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir2', 'b')
    assert isinstance(event, FileCreatedEvent)

    if not platform.is_windows():
        event = event_queue.get(timeout=5)[0]
        assert event.src_path == p('dir2')
        assert isinstance(event, DirModifiedEvent)


@pytest.mark.skipif(not platform.is_linux(), reason="InotifyFullEmitter only supported in Linux")
def test_move_to_full():
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    start_watching(p('dir2'), use_full_emitter=True)
    mv(p('dir1', 'a'), p('dir2', 'b'))

    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileMovedEvent)
    assert event.dest_path == p('dir2', 'b')
    assert event.src_path is None  # Should equal None since the path was not watched


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_move_from():
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    start_watching(p('dir1'))
    mv(p('dir1', 'a'), p('dir2', 'b'))

    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileDeletedEvent)
    assert event.src_path == p('dir1', 'a')

    if not platform.is_windows():
        event = event_queue.get(timeout=5)[0]
        assert event.src_path == p('dir1')
        assert isinstance(event, DirModifiedEvent)


@pytest.mark.skipif(not platform.is_linux(), reason="InotifyFullEmitter only supported in Linux")
def test_move_from_full():
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    start_watching(p('dir1'), use_full_emitter=True)
    mv(p('dir1', 'a'), p('dir2', 'b'))

    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, FileMovedEvent)
    assert event.src_path == p('dir1', 'a')
    assert event.dest_path is None  # Should equal None since path not watched


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_separate_consecutive_moves():
    mkdir(p('dir1'))
    touch(p('dir1', 'a'))
    touch(p('b'))
    start_watching(p('dir1'))
    mv(p('dir1', 'a'), p('c'))
    mv(p('b'), p('dir1', 'd'))

    dir_modif = (DirModifiedEvent, p('dir1'))
    a_deleted = (FileDeletedEvent, p('dir1', 'a'))
    d_created = (FileCreatedEvent, p('dir1', 'd'))

    expected = [a_deleted, dir_modif, d_created, dir_modif]

    if platform.is_windows():
        expected = [a_deleted, d_created]

    if platform.is_bsd():
        # Due to the way kqueue works, we can't really order
        # 'Created' and 'Deleted' events in time, so creation queues first
        expected = [d_created, a_deleted, dir_modif, dir_modif]

    def _step(expected_step):
        event = event_queue.get(timeout=5)[0]
        assert event.src_path == expected_step[1]
        assert isinstance(event, expected_step[0])

    for expected_step in expected:
        _step(expected_step)


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_delete_self():
    mkdir(p('dir1'))
    start_watching(p('dir1'))
    rm(p('dir1'), True)

    if platform.is_darwin():
        event = event_queue.get(timeout=5)[0]
        assert event.src_path == p('dir1')
        assert isinstance(event, FileDeletedEvent)


@pytest.mark.skipif(platform.is_windows() or platform.is_bsd(),
                    reason="Windows|BSD create another set of events for this test")
def test_fast_subdirectory_creation_deletion():
    root_dir = p('dir1')
    sub_dir = p('dir1', 'subdir1')
    times = 30
    mkdir(root_dir)
    start_watching(root_dir)
    for _ in range(times):
        mkdir(sub_dir)
        rm(sub_dir, True)
    count = {DirCreatedEvent: 0,
             DirModifiedEvent: 0,
             DirDeletedEvent: 0}
    etype_for_dir = {DirCreatedEvent: sub_dir,
                     DirModifiedEvent: root_dir,
                     DirDeletedEvent: sub_dir}
    for _ in range(times * 4):
        event = event_queue.get(timeout=5)[0]
        logger.debug(event)
        etype = type(event)
        count[etype] += 1
        assert event.src_path == etype_for_dir[etype]
        assert count[DirCreatedEvent] >= count[DirDeletedEvent]
        assert count[DirCreatedEvent] + count[DirDeletedEvent] >= count[DirModifiedEvent]
    assert count == {DirCreatedEvent: times,
                     DirModifiedEvent: times * 2,
                     DirDeletedEvent: times}


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_passing_unicode_should_give_unicode():
    start_watching(str_cls(p("")))
    touch(p('a'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event.src_path, str_cls)


@pytest.mark.skipif(platform.is_windows(),
                    reason="Windows ReadDirectoryChangesW supports only"
                           " unicode for paths.")
def test_passing_bytes_should_give_bytes():
    start_watching(p('').encode())
    touch(p('a'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event.src_path, bytes)


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_recursive_on():
    mkdir(p('dir1', 'dir2', 'dir3'), True)
    start_watching()
    touch(p('dir1', 'dir2', 'dir3', 'a'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir1', 'dir2', 'dir3', 'a')
    assert isinstance(event, FileCreatedEvent)

    if not platform.is_windows():
        event = event_queue.get(timeout=5)[0]
        assert event.src_path == p('dir1', 'dir2', 'dir3')
        assert isinstance(event, DirModifiedEvent)

        if not platform.is_bsd():
            event = event_queue.get(timeout=5)[0]
            assert event.src_path == p('dir1', 'dir2', 'dir3', 'a')
            assert isinstance(event, FileModifiedEvent)


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_recursive_off():
    mkdir(p('dir1'))
    start_watching(recursive=False)
    touch(p('dir1', 'a'))

    with pytest.raises(Empty):
        event_queue.get(timeout=5)


@pytest.mark.skipif(platform.is_windows(),
                    reason="Windows create another set of events for this test")
def test_renaming_top_level_directory():
    start_watching()

    mkdir(p('a'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirCreatedEvent)
    assert event.src_path == p('a')
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirModifiedEvent)
    assert event.src_path == p()

    mkdir(p('a', 'b'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirCreatedEvent)
    assert event.src_path == p('a', 'b')
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirModifiedEvent)
    assert event.src_path == p('a')

    mv(p('a'), p('a2'))
    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('a')
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirModifiedEvent)
    assert event.src_path == p()
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirModifiedEvent)
    assert event.src_path == p()

    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirMovedEvent)
    assert event.src_path == p('a', 'b')

    if platform.is_bsd():
        event = event_queue.get(timeout=5)[0]
        assert isinstance(event, DirModifiedEvent)
        assert event.src_path == p()

    open(p('a2', 'b', 'c'), 'a').close()

    # DirModifiedEvent may emitted, but sometimes after waiting time is out.
    events = []
    while True:
        events.append(event_queue.get(timeout=5)[0])
        if event_queue.empty():
            break

    assert all([isinstance(e, (FileCreatedEvent, FileMovedEvent, DirModifiedEvent)) for e in events])

    for event in events:
        if isinstance(event, FileCreatedEvent):
            assert event.src_path == p('a2', 'b', 'c')
        elif isinstance(event, FileMovedEvent):
            assert event.dest_path == p('a2', 'b', 'c')
            assert event.src_path == p('a', 'b', 'c')
        elif isinstance(event, DirModifiedEvent):
            assert event.src_path == p('a2', 'b')


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
@pytest.mark.skipif(not platform.is_windows(),
                    reason="Non-Windows create another set of events for this test")
def test_renaming_top_level_directory_on_windows():
    start_watching()

    mkdir(p('a'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirCreatedEvent)
    assert event.src_path == p('a')

    mkdir(p('a', 'b'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirCreatedEvent)
    assert event.src_path == p('a', 'b')

    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirCreatedEvent)
    assert event.src_path == p('a', 'b')

    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirModifiedEvent)
    assert event.src_path == p('a')

    mv(p('a'), p('a2'))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event, DirMovedEvent)
    assert event.src_path == p('a', 'b')

    open(p('a2', 'b', 'c'), 'a').close()

    events = []
    while True:
        events.append(event_queue.get(timeout=5)[0])
        if event_queue.empty():
            break

    assert all([isinstance(e, (FileCreatedEvent, FileMovedEvent, DirMovedEvent, DirModifiedEvent)) for e in events])

    for event in events:
        if isinstance(event, FileCreatedEvent):
            assert event.src_path == p('a2', 'b', 'c')
        elif isinstance(event, FileMovedEvent):
            assert event.dest_path == p('a2', 'b', 'c')
            assert event.src_path == p('a', 'b', 'c')
        elif isinstance(event, DirMovedEvent):
            assert event.dest_path == p('a2')
            assert event.src_path == p('a')
        elif isinstance(event, DirModifiedEvent):
            assert event.src_path == p('a2', 'b')


@pytest.mark.skipif(platform.is_windows(),
                    reason="Windows create another set of events for this test")
def test_move_nested_subdirectories():
    mkdir(p('dir1/dir2/dir3'), parents=True)
    touch(p('dir1/dir2/dir3', 'a'))
    start_watching(p(''))
    mv(p('dir1/dir2'), p('dir2'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir1', 'dir2')
    assert isinstance(event, DirMovedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir1')
    assert isinstance(event, DirModifiedEvent)

    event = event_queue.get(timeout=5)[0]
    assert p(event.src_path, '') == p('')
    assert isinstance(event, DirModifiedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir1/dir2/dir3')
    assert isinstance(event, DirMovedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir1/dir2/dir3', 'a')
    assert isinstance(event, FileMovedEvent)

    if platform.is_bsd():
        event = event_queue.get(timeout=5)[0]
        assert p(event.src_path) == p()
        assert isinstance(event, DirModifiedEvent)

        event = event_queue.get(timeout=5)[0]
        assert p(event.src_path) == p('dir1')
        assert isinstance(event, DirModifiedEvent)

    touch(p('dir2/dir3', 'a'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir2/dir3', 'a')
    assert isinstance(event, FileModifiedEvent)


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
@pytest.mark.skipif(not platform.is_windows(),
                    reason="Non-Windows create another set of events for this test")
def test_move_nested_subdirectories_on_windows():
    mkdir(p('dir1/dir2/dir3'), parents=True)
    touch(p('dir1/dir2/dir3', 'a'))
    start_watching(p(''))
    mv(p('dir1/dir2'), p('dir2'))

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir1', 'dir2')
    assert isinstance(event, FileDeletedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir2')
    assert isinstance(event, DirCreatedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir2', 'dir3')
    assert isinstance(event, DirCreatedEvent)

    event = event_queue.get(timeout=5)[0]
    assert event.src_path == p('dir2', 'dir3', 'a')
    assert isinstance(event, FileCreatedEvent)

    touch(p('dir2/dir3', 'a'))

    events = []
    while True:
        events.append(event_queue.get(timeout=5)[0])
        if event_queue.empty():
            break

    assert all([isinstance(e, (FileModifiedEvent, DirModifiedEvent)) for e in events])

    for event in events:
        if isinstance(event, FileModifiedEvent):
            assert event.src_path == p('dir2', 'dir3', 'a')
        elif isinstance(event, DirModifiedEvent):
            assert event.src_path in [p('dir2'), p('dir2', 'dir3')]
