from __future__ import annotations

from typing import Callable

import pytest

from watchdog.observers.inotify import InotifyWatch
from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

import os
import random

from watchdog.observers.inotify_buffer import GroupedInotifyEvent, PathedInotifyEvent
from watchdog.observers.inotify_c import InotifyConstants, InotifyFD, WATCHDOG_ALL_EVENTS

from .shell import mkdir, mount_tmpfs, mv, rm, symlink, touch, unmount


def wait_for_move_event(read_event: Callable[[], GroupedInotifyEvent]) -> GroupedInotifyEvent:
    while True:
        event = read_event()
        if not isinstance(event, PathedInotifyEvent) or event.ev.is_move:
            return event


def create_inotify_watch(path: bytes, *, recursive: bool = False, follow_symlink: bool = False) -> InotifyWatch:
    return InotifyWatch(
        InotifyFD.get_instance(),
        path,
        is_recursive=recursive,
        follow_symlink=follow_symlink,
        event_mask=WATCHDOG_ALL_EVENTS
    )


@pytest.mark.timeout(5)
def test_move_from(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))

    inotify = create_inotify_watch(p("dir1").encode())
    mv(p("dir1", "a"), p("dir2", "b"))
    event = wait_for_move_event(inotify.read_event)
    assert event.ev.is_moved_from
    assert event.path == p("dir1", "a").encode()
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_move_to(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))

    inotify = create_inotify_watch(p("dir2").encode())
    mv(p("dir1", "a"), p("dir2", "b"))
    event = wait_for_move_event(inotify.read_event)
    assert event.ev.is_moved_to
    assert event.path == p("dir2", "b").encode()
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_move_internal(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))

    inotify = create_inotify_watch(p("").encode(), recursive=True)
    mv(p("dir1", "a"), p("dir2", "b"))
    frm, to = wait_for_move_event(inotify.read_event)
    assert frm.path == p("dir1", "a").encode()
    assert to.path == p("dir2", "b").encode()
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_move_internal_symlink_followed(p):
    mkdir(p("dir", "dir1"), parents=True)
    mkdir(p("dir", "dir2"))
    touch(p("dir", "dir1", "a"))
    symlink(p("dir"), p("symdir"), target_is_directory=True)

    inotify = create_inotify_watch(p("symdir").encode(), recursive=True, follow_symlink=True)
    mv(p("dir", "dir1", "a"), p("dir", "dir2", "b"))
    frm, to = wait_for_move_event(inotify.read_event)
    assert frm.path == p("symdir", "dir1", "a").encode()
    assert to.path == p("symdir", "dir2", "b").encode()
    inotify.deactivate()


@pytest.mark.timeout(10)
def test_move_internal_batch(p):
    n = 100
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    files = [str(i) for i in range(n)]
    for f in files:
        touch(p("dir1", f))

    inotify = create_inotify_watch(p("").encode(), recursive=True)

    random.shuffle(files)
    for f in files:
        mv(p("dir1", f), p("dir2", f))

    # Check that all n events are paired
    for _ in range(n):
        frm, to = wait_for_move_event(inotify.read_event)
        assert os.path.dirname(frm.path).endswith(b"/dir1")
        assert os.path.dirname(to.path).endswith(b"/dir2")
        assert frm.ev.name == to.ev.name
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_delete_watched_directory(p):
    mkdir(p("dir"))
    inotify = create_inotify_watch(p("dir").encode())
    rm(p("dir"), recursive=True)

    # Wait for the event to be picked up
    inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_delete_watched_directory_symlink_followed(p):
    mkdir(p("dir", "dir2"), parents=True)
    symlink(p("dir"), p("symdir"), target_is_directory=True)

    inotify = create_inotify_watch(p("symdir").encode(), follow_symlink=True)
    rm(p("dir", "dir2"), recursive=True)

    # Wait for the event to be picked up
    event = inotify.read_event()
    while not isinstance(event, PathedInotifyEvent) or (
        event.ev.mask != (InotifyConstants.IN_DELETE | InotifyConstants.IN_ISDIR)
    ):
        event = inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.deactivate()


@pytest.mark.timeout(5)
def test_delete_watched_directory_symlink_followed_recursive(p):
    mkdir(p("dir"), parents=True)
    mkdir(p("dir2", "dir3", "dir4"), parents=True)
    symlink(p("dir2"), p("dir", "symdir"), target_is_directory=True)

    inotify = create_inotify_watch(p("dir").encode(), follow_symlink=True, recursive=True)
    rm(p("dir2", "dir3", "dir4"), recursive=True)

    # Wait for the event to be picked up
    event = inotify.read_event()
    while not isinstance(event, PathedInotifyEvent) or (
        event.ev.mask != (InotifyConstants.IN_DELETE | InotifyConstants.IN_ISDIR)
    ):
        event = inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.deactivate()


@pytest.mark.timeout(5)
@pytest.mark.skipif("GITHUB_REF" not in os.environ, reason="sudo password prompt")
def test_unmount_watched_directory_filesystem(p):
    mkdir(p("dir1"))
    mount_tmpfs(p("dir1"))
    mkdir(p("dir1/dir2"))
    inotify = create_inotify_watch(p("dir1/dir2").encode())
    unmount(p("dir1"))

    # Wait for the event to be picked up
    inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.deactivate()
    assert not inotify.is_active
    assert not inotify._active_callbacks_by_watch
    assert not inotify._active_callbacks_by_watch
