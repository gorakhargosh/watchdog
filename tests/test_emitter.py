from __future__ import annotations

import logging
import os
import stat
import time
from queue import Empty
from typing import TYPE_CHECKING

import pytest

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileClosedEvent,
    FileClosedNoWriteEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileOpenedEvent,
)
from watchdog.utils import platform

from .shell import mkdir, mkfile, mv, rm, touch

if TYPE_CHECKING:
    from .utils import EventsChecker, P, StartWatching, TestEventQueue

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


if platform.is_darwin():
    # enable more verbose logs
    fsevents_logger = logging.getLogger("fsevents")
    fsevents_logger.setLevel(logging.DEBUG)


def test_create(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    start_watching()
    open(p("a"), "a").close()

    checker = events_checker()
    checker.add(FileCreatedEvent, "a")
    if platform.is_linux():
        checker.add(FileOpenedEvent, "a")
        checker.add(FileClosedEvent, "a")

    checker.check_events()


@pytest.mark.skipif(not platform.is_linux(), reason="FileClosed*Event only supported in GNU/Linux")
def test_closed(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    with open(p("a"), "a"):
        start_watching()

    checker = events_checker()

    # After file creation/open in append mode
    checker.add(FileClosedEvent, "a")

    checker.add(DirModifiedEvent, ".")
    checker.check_events()

    # After read-only, only IN_CLOSE_NOWRITE is emitted
    open(p("a")).close()

    checker = events_checker()
    checker.add(FileOpenedEvent, "a")
    checker.add(FileClosedNoWriteEvent, "a")
    checker.check_events()


@pytest.mark.skipif(
    platform.is_darwin() or platform.is_windows(),
    reason="Windows and macOS enforce proper encoding",
)
def test_create_wrong_encoding(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    start_watching()
    open(p("a_\udce4"), "a").close()

    checker = events_checker()
    checker.add(FileCreatedEvent, "a_\udce4")
    if not platform.is_windows():
        checker.add(DirModifiedEvent, ".")
    checker.check_events()


def test_delete(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    mkfile(p("a"))

    start_watching()
    rm(p("a"))

    checker = events_checker()
    checker.add(FileDeletedEvent, "a")

    if not platform.is_windows():
        checker.add(DirModifiedEvent, ".")

    checker.check_events()


def test_modify(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    mkfile(p("a"))
    start_watching()

    touch(p("a"))

    checker = events_checker()
    checker.add(FileModifiedEvent, "a")
    if platform.is_linux():
        checker.add(FileOpenedEvent, "a")
        checker.add(FileClosedEvent, "a")
    checker.check_events()


def test_chmod(p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker) -> None:
    mkfile(p("a"))
    start_watching()

    # Note: We use S_IREAD here because chmod on Windows only
    # allows setting the read-only flag.
    os.chmod(p("a"), stat.S_IREAD)

    checker = events_checker()
    checker.add(FileModifiedEvent, "a")
    checker.check_events()

    # Reset permissions to allow cleanup.
    os.chmod(p("a"), stat.S_IWRITE)


def test_move_simple(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "a"))
    start_watching()

    mv(p("dir1", "a"), p("dir2", "b"))

    checker = events_checker()
    if not platform.is_windows():
        checker.add(FileMovedEvent, "dir1/a", dest_path="dir2/b")
    else:
        checker.add(FileDeletedEvent, "dir1/a")
        checker.add(FileCreatedEvent, "dir2/b")
    if not platform.is_windows():
        checker.add(DirModifiedEvent, "dir1")
        checker.add(DirModifiedEvent, "dir2")
    checker.check_events()


def test_case_change(
    p: P,
    event_queue: TestEventQueue,
    start_watching: StartWatching,
    events_checker: EventsChecker,
) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "file"))
    start_watching()

    mv(p("dir1", "file"), p("dir2", "FILE"))

    checker = events_checker()
    if not platform.is_windows():
        checker.add(FileMovedEvent, "dir1/file", dest_path="dir2/FILE")
    else:
        checker.add(FileDeletedEvent, "dir1/file")
        checker.add(FileCreatedEvent, "dir2/FILE")
    if not platform.is_windows():
        checker.add(DirModifiedEvent, "dir1")
        checker.add(DirModifiedEvent, "dir2")
    checker.check_events()


def test_move_to(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "a"))
    start_watching(path=p("dir2"))

    mv(p("dir1", "a"), p("dir2", "b"))

    checker = events_checker()
    checker.add(FileCreatedEvent, "dir2/b")
    if not platform.is_windows():
        checker.add(DirModifiedEvent, "dir2")
    checker.check_events()


@pytest.mark.skipif(not platform.is_linux(), reason="InotifyFullEmitter only supported in Linux")
def test_move_to_full(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "a"))
    start_watching(path=p("dir2"), use_full_emitter=True)
    mv(p("dir1", "a"), p("dir2", "b"))

    checker = events_checker()
    # The src_path should be blank since the path was not watched
    checker.add(FileMovedEvent, "", dest_path="dir2/b")
    checker.check_events()


def test_move_from(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "a"))
    start_watching(path=p("dir1"))

    mv(p("dir1", "a"), p("dir2", "b"))

    checker = events_checker()
    checker.add(FileDeletedEvent, "dir1/a")
    if not platform.is_windows():
        checker.add(DirModifiedEvent, "dir1")
    checker.check_events()


@pytest.mark.skipif(not platform.is_linux(), reason="InotifyFullEmitter only supported in Linux")
def test_move_from_full(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    mkfile(p("dir1", "a"))
    start_watching(path=p("dir1"), use_full_emitter=True)
    mv(p("dir1", "a"), p("dir2", "b"))

    checker = events_checker()
    # dest_path should be blank since not watched
    checker.add(FileMovedEvent, "dir1/a", dest_path="")
    checker.check_events()


def test_separate_consecutive_moves(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    mkdir(p("dir1"))
    mkfile(p("dir1", "a"))
    mkfile(p("b"))
    start_watching(path=p("dir1"))
    mv(p("dir1", "a"), p("c"))
    mv(p("b"), p("dir1", "d"))

    checker = events_checker()
    if not platform.is_windows():
        checker.add(FileDeletedEvent, "dir1/a")
        checker.add(DirModifiedEvent, "dir1")
        checker.add(FileCreatedEvent, "dir1/d")
    else:
        checker.add(FileDeletedEvent, "dir1/a")
        checker.add(FileCreatedEvent, "dir1/d")
    checker.check_events()


@pytest.mark.skipif(platform.is_bsd(), reason="BSD create another set of events for this test")
def test_delete_self(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    mkdir(p("dir1"))
    emitter = start_watching(path=p("dir1"))
    rm(p("dir1"), recursive=True)

    checker = events_checker()
    checker.add(DirDeletedEvent, "dir1")
    checker.check_events()

    emitter.join(5)
    assert not emitter.is_alive()


@pytest.mark.skipif(
    platform.is_windows() or platform.is_bsd(),
    reason="Windows|BSD create another set of events for this test",
)
def test_fast_subdirectory_creation_deletion(
    p: P, events_checker: EventsChecker, event_queue: TestEventQueue, start_watching: StartWatching
) -> None:
    root_dir = p("dir1")
    sub_dir = p("dir1", "subdir1")
    times = 30
    mkdir(root_dir)
    start_watching(path=root_dir)
    for _ in range(times):
        mkdir(sub_dir)
        rm(sub_dir, recursive=True)
        time.sleep(0.1)  # required for macOS emitter to catch up with us

    checker = events_checker()
    for _ in range(times):
        checker.add(DirCreatedEvent, "dir1/sub_dir1")
        checker.add(DirModifiedEvent, "dir1")
        checker.add(DirDeletedEvent, "dir1/sub_dir1")
        checker.add(DirModifiedEvent, "dir1")


def test_passing_unicode_should_give_unicode(p: P, event_queue: TestEventQueue, start_watching: StartWatching) -> None:
    start_watching(path=str(p()))
    mkfile(p("a"))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event.src_path, str)


@pytest.mark.skipif(
    platform.is_windows(),
    reason="Windows ReadDirectoryChangesW supports only unicode for paths.",
)
def test_passing_bytes_should_give_bytes(p: P, event_queue: TestEventQueue, start_watching: StartWatching) -> None:
    start_watching(path=p().encode())
    mkfile(p("a"))
    event = event_queue.get(timeout=5)[0]
    assert isinstance(event.src_path, bytes)


def test_recursive_on(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    mkdir(p("dir1", "dir2", "dir3"), parents=True)
    start_watching()
    touch(p("dir1", "dir2", "dir3", "a"))

    checker = events_checker()
    checker.add(FileCreatedEvent, "dir1/dir2/dir3/a")
    if not platform.is_windows():
        checker.add(DirModifiedEvent, "dir1/dir2/dir3")

        if platform.is_linux():
            checker.add(FileOpenedEvent, "dir1/dir2/dir3/a")

        if not platform.is_bsd():
            checker.add(FileModifiedEvent, "dir1/dir2/dir3/a")

    checker.check_events()


def check_empty_queue(event_queue: TestEventQueue) -> None:
    events = []
    while True:
        try:
            _ = event_queue.get(timeout=4)
        except Empty:
            break
    assert not events, "queue was not empty"


def test_recursive_off(
    p: P,
    event_queue: TestEventQueue,
    start_watching: StartWatching,
    events_checker: EventsChecker,
) -> None:
    mkdir(p("dir1"))
    start_watching(recursive=False)
    touch(p("dir1", "a"))

    check_empty_queue(event_queue)

    mkfile(p("b"))

    checker = events_checker()
    checker.add(FileCreatedEvent, "b")
    if not platform.is_windows():
        checker.add(DirModifiedEvent, ".")
        if platform.is_linux():
            checker.add(FileOpenedEvent, "b")
            checker.add(FileClosedEvent, "b")
    checker.check_events()

    # currently limiting these additional events to macOS only, see https://github.com/gorakhargosh/watchdog/pull/779
    if platform.is_darwin():
        mkdir(p("dir1", "dir2"))
        check_empty_queue(event_queue)
        mkfile(p("dir1", "dir2", "somefile"))
        check_empty_queue(event_queue)

        mkdir(p("dir3"))
        checker = events_checker()
        checker.add(DirModifiedEvent, ".")  # the contents of the parent directory changed
        checker.check_events()

        mv(p("dir1", "dir2", "somefile"), p("somefile"))
        checker = events_checker()
        checker.add(FileMovedEvent, "dir1/dir2/somefile", dest_path="somefile")
        checker.add(DirModifiedEvent, ".")
        checker.check_events()

        mv(p("dir1", "dir2"), p("dir2"))
        checker = events_checker()
        checker.add(DirMovedEvent, "dir1/dir2", dest_path="dir2")
        checker.add(DirModifiedEvent, ".")
        checker.check_events()


def test_renaming_top_level_directory(
    p: P,
    event_queue: TestEventQueue,
    start_watching: StartWatching,
    events_checker: EventsChecker,
) -> None:
    start_watching()

    mkdir(p("a"))
    checker = events_checker()
    checker.add(DirCreatedEvent, "a")
    if not platform.is_windows():
        checker.add(DirModifiedEvent, ".")
    checker.check_events()

    mkdir(p("a", "b"))
    checker = events_checker()
    checker.add(DirCreatedEvent, "a/b")
    if not platform.is_windows():
        checker.add(DirModifiedEvent, "a")
    checker.check_events()

    mv(p("a"), p("a2"))
    checker = events_checker()
    checker.add(DirMovedEvent, "a", dest_path="a2")
    if not platform.is_windows():
        checker.add(DirModifiedEvent, ".")
    checker.add(DirMovedEvent, "a/b", dest_path="a2/b")
    checker.check_events()

    open(p("a2", "b", "c"), "a").close()

    checker = events_checker()
    checker.add(FileCreatedEvent, "a2/b/c")
    if platform.is_linux():
        checker.add(FileOpenedEvent, "a2/b/c")
        checker.add(FileClosedEvent, "a2/b/c")
    checker.check_events()


@pytest.mark.skipif(platform.is_windows(), reason="Windows create another set of events for this test")
def test_move_nested_subdirectories(
    p: P,
    event_queue: TestEventQueue,
    start_watching: StartWatching,
    events_checker: EventsChecker,
) -> None:
    mkdir(p("dir1/dir2/dir3"), parents=True)
    mkfile(p("dir1/dir2/dir3", "a"))
    start_watching()
    mv(p("dir1/dir2"), p("dir2"))

    checker = events_checker()
    checker.add(DirMovedEvent, "dir1/dir2", dest_path="dir2")
    checker.add(DirModifiedEvent, "dir1")
    checker.add(DirModifiedEvent, ".")
    checker.add(DirMovedEvent, "dir1/dir2/dir3", dest_path="dir2/dir3")
    checker.add(FileMovedEvent, "dir1/dir2/dir3/a", dest_path="dir2/dir3/a")
    checker.check_events()

    touch(p("dir2/dir3", "a"))

    checker = events_checker()
    checker.add(FileModifiedEvent, "dir2/dir3/a")
    if platform.is_linux():
        checker.add(FileOpenedEvent, "dir2/dir3/a")
    checker.check_events()


@pytest.mark.skipif(
    not platform.is_windows(),
    reason="Non-Windows create another set of events for this test",
)
def test_move_nested_subdirectories_on_windows(
    p: P,
    event_queue: TestEventQueue,
    start_watching: StartWatching,
    events_checker: EventsChecker,
) -> None:
    mkdir(p("dir1/dir2/dir3"), parents=True)
    mkfile(p("dir1/dir2/dir3", "a"))
    start_watching(path=p(""))
    mv(p("dir1/dir2"), p("dir2"))

    checker = events_checker()
    checker.add(FileDeletedEvent, "dir1/dir2")
    checker.add(DirCreatedEvent, "dir2")
    checker.add(DirCreatedEvent, "dir2/dir3")
    checker.add(FileCreatedEvent, "dir2/dir3/a")
    checker.check_events()

    touch(p("dir2/dir3", "a"))

    checker = events_checker()
    checker.add(FileModifiedEvent, "dir2/dir3/a")
    checker.check_events()


@pytest.mark.skipif(platform.is_bsd(), reason="BSD create another set of events for this test")
def test_file_lifecyle(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, events_checker: EventsChecker
) -> None:
    start_watching()

    mkfile(p("a"))
    touch(p("a"))
    mv(p("a"), p("b"))
    rm(p("b"))

    checker = events_checker()
    checker.add(FileCreatedEvent, "a")
    checker.add(FileModifiedEvent, "a")
    checker.add(FileMovedEvent, "a", dest_path="b")
    checker.add(FileDeletedEvent, "b")

    if platform.is_linux():
        checker.add(FileOpenedEvent, "a")
        checker.add(FileClosedEvent, "a")
        checker.add(FileOpenedEvent, "a")
        checker.add(FileClosedEvent, "a")

    checker.check_events()
