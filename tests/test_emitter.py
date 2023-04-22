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

from __future__ import annotations

import logging
import os
import stat
import time
from queue import Empty

import pytest

from watchdog.events import (
    DirAttribEvent,
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileAttribEvent,
    FileClosedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileOpenedEvent,
)
from watchdog.utils import platform

from .shell import chmod, mkdir, mkfile, mv, rm, touch
from .utils import ExpectEvent, P, StartWatching, TestEventQueue

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


if platform.is_darwin():
    # enable more verbose logs
    fsevents_logger = logging.getLogger("fsevents")
    fsevents_logger.setLevel(logging.DEBUG)


def rerun_filter(exc, *args):
    time.sleep(5)
    return bool(issubclass(exc[0], Empty) and platform.is_windows())


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_create(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    start_watching()
    open(p("a"), "a").close()

    expect_event(FileCreatedEvent(p("a")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(p()))

    if platform.is_linux():
        expect_event(FileOpenedEvent(p("a")))
        expect_event(FileClosedEvent(p("a")))


@pytest.mark.xfail(reason="known to be problematic")
@pytest.mark.skipif(not platform.is_linux(), reason="FileCloseEvent only supported in GNU/Linux")
@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_close(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    f_d = open(p("a"), "a")
    start_watching()
    f_d.close()

    # After file creation/open in append mode
    expect_event(FileClosedEvent(p("a")))

    expect_event(DirModifiedEvent(os.path.normpath(p(""))))

    # After read-only, only IN_CLOSE_NOWRITE is emitted but not caught for now #747
    open(p("a"), "r").close()

    expect_event(FileOpenedEvent(p("a")))
    with pytest.raises(Empty):
        expect_event(None)


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
@pytest.mark.skipif(
    platform.is_darwin() or platform.is_windows(),
    reason="Windows and macOS enforce proper encoding",
)
def test_create_wrong_encoding(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    start_watching()
    open(p("a_\udce4"), "a").close()

    expect_event(FileCreatedEvent(p("a_\udce4")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(os.path.normpath(p(""))))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_delete(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkfile(p("a"))
    start_watching()
    rm(p("a"))

    expect_event(FileDeletedEvent(p("a")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(p()))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_modify(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkfile(p("a"))
    start_watching()

    touch(p("a"))

    if platform.is_windows():
        expect_event(FileModifiedEvent(p("a")))
    elif platform.is_linux():
        expect_event(FileOpenedEvent(p("a")))
        expect_event(FileAttribEvent(p("a")))
        expect_event(FileClosedEvent(p("a")))
    elif platform.is_bsd():
        expect_event(FileModifiedEvent(p("a")))
        expect_event(FileAttribEvent(p("a")))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_chmod(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkfile(p("a"))
    start_watching()

    # Note: We use S_IREAD here because chmod on Windows only
    # allows setting the read-only flag.
    os.chmod(p("a"), stat.S_IREAD)

    if platform.is_windows():
        expect_event(FileModifiedEvent(p("a")))
    else:
        expect_event(FileAttribEvent(p("a")))

    # Reset permissions to allow cleanup.
    os.chmod(p("a"), stat.S_IWRITE)


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_move(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "a"))
    start_watching()

    mv(p("dir1", "a"), p("dir2", "b"))

    if not platform.is_windows():
        expect_event(FileMovedEvent(p("dir1", "a"), p("dir2", "b")))
    else:
        expect_event(FileDeletedEvent(p("dir1", "a")))
        expect_event(FileCreatedEvent(p("dir2", "b")))

    expect_event(DirModifiedEvent(p("dir1")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(p("dir2")))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_case_change(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "file"))
    start_watching()

    mv(p("dir1", "file"), p("dir2", "FILE"))

    if not platform.is_windows():
        expect_event(FileMovedEvent(p("dir1", "file"), p("dir2", "FILE")))
    else:
        expect_event(FileDeletedEvent(p("dir1", "file")))
        expect_event(FileCreatedEvent(p("dir2", "FILE")))

    expect_event(DirModifiedEvent(p("dir1")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(p("dir2")))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_move_to(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "a"))
    start_watching(p("dir2"))

    mv(p("dir1", "a"), p("dir2", "b"))

    expect_event(FileCreatedEvent(p("dir2", "b")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(p("dir2")))


@pytest.mark.skipif(not platform.is_linux(), reason="InotifyFullEmitter only supported in Linux")
def test_move_to_full(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "a"))
    start_watching(p("dir2"), use_full_emitter=True)

    mv(p("dir1", "a"), p("dir2", "b"))

    # `src_path` should be blank since the path was not watched
    expect_event(FileMovedEvent("", p("dir2", "b")))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_move_from(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "a"))
    start_watching(p("dir1"))

    mv(p("dir1", "a"), p("dir2", "b"))
    expect_event(FileDeletedEvent(p("dir1", "a")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(p("dir1")))


@pytest.mark.skipif(not platform.is_linux(), reason="InotifyFullEmitter only supported in Linux")
def test_move_from_full(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "a"))
    start_watching(p("dir1"), use_full_emitter=True)

    mv(p("dir1", "a"), p("dir2", "b"))

    # `dest_path` should be blank since the path was not watched
    expect_event(FileMovedEvent(p("dir1", "a"), ""))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_separate_consecutive_moves(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkdir(p("dir1"))
    mkfile(p("dir1", "a"))
    mkfile(p("b"))
    start_watching(p("dir1"))
    mv(p("dir1", "a"), p("c"))
    mv(p("b"), p("dir1", "d"))

    dir_modif = DirModifiedEvent(p("dir1"))
    a_deleted = FileDeletedEvent(p("dir1", "a"))
    d_created = FileCreatedEvent(p("dir1", "d"))

    expected_events = [a_deleted, dir_modif, d_created, dir_modif]

    if platform.is_windows():
        expected_events = [a_deleted, d_created]

    if platform.is_bsd():
        # Due to the way kqueue works, we can't really order
        # 'Created' and 'Deleted' events in time, so creation queues first
        expected_events = [d_created, a_deleted, dir_modif, dir_modif]

    for expected_event in expected_events:
        expect_event(expected_event)


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
@pytest.mark.skipif(platform.is_bsd(), reason="BSD create another set of events for this test")
def test_delete_self(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkdir(p("dir1"))
    emitter = start_watching(p("dir1"))
    rm(p("dir1"), True)
    expect_event(DirDeletedEvent(p("dir1")))
    emitter.join(5)
    assert not emitter.is_alive()


@pytest.mark.skipif(
    platform.is_windows() or platform.is_bsd(),
    reason="Windows|BSD create another set of events for this test",
)
def test_fast_subdirectory_creation_deletion(p: P, event_queue: TestEventQueue, start_watching: StartWatching) -> None:
    root_dir = p("dir1")
    sub_dir = p("dir1", "subdir1")
    times = 30
    mkdir(root_dir)
    start_watching(root_dir)
    for _ in range(times):
        mkdir(sub_dir)
        rm(sub_dir, True)
        time.sleep(0.1)  # required for macOS emitter to catch up with us
    count = {DirCreatedEvent: 0, DirModifiedEvent: 0, DirDeletedEvent: 0}
    etype_for_dir = {
        DirCreatedEvent: sub_dir,
        DirModifiedEvent: root_dir,
        DirDeletedEvent: sub_dir,
    }
    for _ in range(times * 4):
        event = event_queue.get(timeout=5)[0]
        logger.debug(event)
        etype = type(event)
        count[etype] += 1
        assert event.src_path == etype_for_dir[etype]
        assert count[DirCreatedEvent] >= count[DirDeletedEvent]
        assert count[DirCreatedEvent] + count[DirDeletedEvent] >= count[DirModifiedEvent]
    assert count == {
        DirCreatedEvent: times,
        DirModifiedEvent: times * 2,
        DirDeletedEvent: times,
    }


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_passing_unicode_should_give_unicode(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    start_watching(str(p()))
    mkfile(p("a"))
    expect_event(FileCreatedEvent(p("a")))


@pytest.mark.skipif(
    platform.is_windows(),
    reason="Windows ReadDirectoryChangesW supports only unicode for paths.",
)
def test_passing_bytes_should_give_bytes(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    start_watching(p().encode())
    mkfile(p("a"))
    expect_event(FileCreatedEvent(p("a").encode()))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_recursive_on(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkdir(p("dir1", "dir2", "dir3"), True)
    start_watching()
    touch(p("dir1", "dir2", "dir3", "a"))

    expect_event(FileCreatedEvent(p("dir1", "dir2", "dir3", "a")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(p("dir1", "dir2", "dir3")))
        expect_event(FileOpenedEvent(p("dir1", "dir2", "dir3", "a")))
        expect_event(FileAttribEvent(p("dir1", "dir2", "dir3", "a")))
        expect_event(FileClosedEvent(p("dir1", "dir2", "dir3", "a")))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_recursive_off(
    p: P,
    event_queue: TestEventQueue,
    start_watching: StartWatching,
    expect_event: ExpectEvent,
) -> None:
    mkdir(p("dir1"))
    start_watching(recursive=False)
    touch(p("dir1", "a"))

    with pytest.raises(Empty):
        event_queue.get(timeout=5)

    mkfile(p("b"))
    expect_event(FileCreatedEvent(p("b")))
    if not platform.is_windows():
        expect_event(DirModifiedEvent(p()))

        if platform.is_linux():
            expect_event(FileOpenedEvent(p("b")))
            expect_event(FileClosedEvent(p("b")))

    # currently limiting these additional events to macOS only, see https://github.com/gorakhargosh/watchdog/pull/779
    if platform.is_darwin():
        mkdir(p("dir1", "dir2"))
        with pytest.raises(Empty):
            event_queue.get(timeout=5)
        mkfile(p("dir1", "dir2", "somefile"))
        with pytest.raises(Empty):
            event_queue.get(timeout=5)

        mkdir(p("dir3"))
        expect_event(DirModifiedEvent(p()))  # the contents of the parent directory changed

        mv(p("dir1", "dir2", "somefile"), p("somefile"))
        expect_event(FileMovedEvent(p("dir1", "dir2", "somefile"), p("somefile")))
        expect_event(DirModifiedEvent(p()))

        mv(p("dir1", "dir2"), p("dir2"))
        expect_event(DirMovedEvent(p("dir1", "dir2"), p("dir2")))
        expect_event(DirModifiedEvent(p()))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
def test_renaming_top_level_directory(
    p: P,
    event_queue: TestEventQueue,
    start_watching: StartWatching,
    expect_event: ExpectEvent,
) -> None:
    start_watching()

    mkdir(p("a"))
    expect_event(DirCreatedEvent(p("a")))
    if not platform.is_windows():
        expect_event(DirModifiedEvent(p()))

    mkdir(p("a", "b"))
    expect_event(DirCreatedEvent(p("a", "b")))
    expect_event(DirModifiedEvent(p("a")))

    mv(p("a"), p("a2"))
    expect_event(DirMovedEvent(p("a"), p("a2")))
    if not platform.is_windows():
        expect_event(DirModifiedEvent(p()))
        expect_event(DirModifiedEvent(p()))
    expect_event(DirMovedEvent(p("a", "b"), p("a2", "b"), is_synthetic=True))

    if platform.is_bsd():
        expect_event(DirModifiedEvent(p()))

    open(p("a2", "b", "c"), "a").close()

    # DirModifiedEvent may emitted, but sometimes after waiting time is out.
    events = []
    while True:
        events.append(event_queue.get(timeout=5)[0])
        if event_queue.empty():
            break

    assert all(
        isinstance(e, (FileCreatedEvent, FileMovedEvent, FileOpenedEvent, DirModifiedEvent, FileClosedEvent))
        for e in events
    )

    for event in events:
        if isinstance(event, FileCreatedEvent):
            assert event.src_path == p("a2", "b", "c")
        elif isinstance(event, FileMovedEvent):
            assert event.dest_path == p("a2", "b", "c")
            assert event.src_path == p("a", "b", "c")
        elif isinstance(event, DirModifiedEvent):
            assert event.src_path == p("a2", "b")


@pytest.mark.skipif(platform.is_windows(), reason="Windows create another set of events for this test")
def test_move_nested_subdirectories(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    mkdir(p("dir1/dir2/dir3"), parents=True)
    mkfile(p("dir1/dir2/dir3", "a"))
    start_watching()
    mv(p("dir1/dir2"), p("dir2"))

    expect_event(DirMovedEvent(p("dir1", "dir2"), p("dir2")))
    expect_event(DirModifiedEvent(p("dir1")))
    expect_event(DirModifiedEvent(p()))
    expect_event(DirMovedEvent(p("dir1", "dir2", "dir3"), p("dir2", "dir3"), is_synthetic=True))
    expect_event(FileMovedEvent(p("dir1", "dir2", "dir3", "a"), p("dir2", "dir3", "a"), is_synthetic=True))

    if platform.is_bsd():
        expect_event(DirModifiedEvent(p()))
        expect_event(DirModifiedEvent(p("dir1")))

    touch(p("dir2/dir3", "a"))

    if platform.is_linux():
        expect_event(FileOpenedEvent(p("dir2/dir3", "a")))

    if not platform.is_windows():
        expect_event(FileAttribEvent(p("dir2/dir3", "a")))

    if platform.is_linux():
        expect_event(FileClosedEvent(p("dir2/dir3/", "a")))

    expect_event(DirModifiedEvent(p("dir2/dir3")))


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
@pytest.mark.skipif(
    not platform.is_windows(),
    reason="Non-Windows create another set of events for this test",
)
def test_move_nested_subdirectories_on_windows(
    p: P,
    event_queue: TestEventQueue,
    start_watching: StartWatching,
    expect_event: ExpectEvent,
) -> None:
    mkdir(p("dir1/dir2/dir3"), parents=True)
    mkfile(p("dir1/dir2/dir3", "a"))
    start_watching(p(""))
    mv(p("dir1/dir2"), p("dir2"))

    expect_event(FileDeletedEvent(p("dir1", "dir2")))
    expect_event(DirCreatedEvent(p("dir2")))
    expect_event(DirCreatedEvent(p("dir2", "dir3")))
    expect_event(FileCreatedEvent(p("dir2", "dir3", "a")))

    touch(p("dir2/dir3", "a"))

    events = []
    while True:
        events.append(event_queue.get(timeout=5)[0])
        if event_queue.empty():
            break

    assert all(isinstance(e, (FileModifiedEvent, DirModifiedEvent)) for e in events)

    for event in events:
        if isinstance(event, FileModifiedEvent):
            assert event.src_path == p("dir2", "dir3", "a")
        elif isinstance(event, DirModifiedEvent):
            assert event.src_path in [p("dir2"), p("dir2", "dir3")]


@pytest.mark.flaky(max_runs=5, min_passes=1, rerun_filter=rerun_filter)
@pytest.mark.skipif(platform.is_bsd(), reason="BSD create another set of events for this test")
def test_file_lifecyle(p: P, start_watching: StartWatching, expect_event: ExpectEvent) -> None:
    start_watching()

    mkfile(p("a"))
    touch(p("a"))
    mv(p("a"), p("b"))
    rm(p("b"))

    expect_event(FileCreatedEvent(p("a")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(p()))

    if platform.is_linux():
        expect_event(FileOpenedEvent(p("a")))
        expect_event(FileClosedEvent(p("a")))
        expect_event(DirModifiedEvent(p()))
        expect_event(FileOpenedEvent(p("a")))

    if platform.is_windows():
        expect_event(FileModifiedEvent(p("a")))
    else:
        expect_event(FileAttribEvent(p("a")))

    if platform.is_linux():
        expect_event(FileClosedEvent(p("a")))
        expect_event(DirModifiedEvent(p()))

    expect_event(FileMovedEvent(p("a"), p("b")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(p()))
        expect_event(DirModifiedEvent(p()))

    expect_event(FileDeletedEvent(p("b")))

    if not platform.is_windows():
        expect_event(DirModifiedEvent(p()))


@pytest.mark.skipif(platform.is_windows(), reason="FileAttribEvent isn't supported in Windows")
def test_chmod_file(p: P, start_watching: StartWatching, expect_event: ExpectEvent):
    mkfile(p("newfile"))
    start_watching()

    chmod(p("newfile"), 777)
    expect_event(FileAttribEvent(p("newfile")))


@pytest.mark.skipif(platform.is_windows(), reason="DirAttribEvent isn't supported in Windows")
def test_chmod_dir(p: P, start_watching: StartWatching, expect_event: ExpectEvent):
    mkdir(p("dir1"))
    start_watching()

    chmod(p("dir1"), 777)
    expect_event(DirAttribEvent(p("dir1")))
