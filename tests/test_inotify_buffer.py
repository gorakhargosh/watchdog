from __future__ import annotations

import pytest
from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

import os
import random
import time

from watchdog.observers.inotify_buffer import InotifyBuffer

from .shell import mkdir, mount_tmpfs, mv, rm, touch, unmount


def wait_for_move_event(read_event):
    while True:
        event = read_event()
        if isinstance(event, tuple) or event.is_move:
            return event


@pytest.mark.timeout(5)
def test_move_from(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))

    inotify = InotifyBuffer(p("dir1").encode())
    mv(p("dir1", "a"), p("dir2", "b"))
    event = wait_for_move_event(inotify.read_event)
    assert event.is_moved_from
    assert event.src_path == p("dir1", "a").encode()
    inotify.close()


@pytest.mark.timeout(5)
def test_move_to(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))

    inotify = InotifyBuffer(p("dir2").encode())
    mv(p("dir1", "a"), p("dir2", "b"))
    event = wait_for_move_event(inotify.read_event)
    assert event.is_moved_to
    assert event.src_path == p("dir2", "b").encode()
    inotify.close()


@pytest.mark.timeout(5)
def test_move_internal(p):
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    touch(p("dir1", "a"))

    inotify = InotifyBuffer(p("").encode(), recursive=True)
    mv(p("dir1", "a"), p("dir2", "b"))
    frm, to = wait_for_move_event(inotify.read_event)
    assert frm.src_path == p("dir1", "a").encode()
    assert to.src_path == p("dir2", "b").encode()
    inotify.close()


@pytest.mark.timeout(10)
def test_move_internal_batch(p):
    n = 100
    mkdir(p("dir1"))
    mkdir(p("dir2"))
    files = [str(i) for i in range(n)]
    for f in files:
        touch(p("dir1", f))

    inotify = InotifyBuffer(p("").encode(), recursive=True)

    random.shuffle(files)
    for f in files:
        mv(p("dir1", f), p("dir2", f))

    # Check that all n events are paired
    for _ in range(n):
        frm, to = wait_for_move_event(inotify.read_event)
        assert os.path.dirname(frm.src_path).endswith(b"/dir1")
        assert os.path.dirname(to.src_path).endswith(b"/dir2")
        assert frm.name == to.name
    inotify.close()


@pytest.mark.timeout(5)
def test_delete_watched_directory(p):
    mkdir(p("dir"))
    inotify = InotifyBuffer(p("dir").encode())
    rm(p("dir"), recursive=True)

    # Wait for the event to be picked up
    inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.close()


@pytest.mark.timeout(5)
@pytest.mark.skipif("GITHUB_REF" not in os.environ, reason="sudo password prompt")
def test_unmount_watched_directory_filesystem(p):
    mkdir(p("dir1"))
    mount_tmpfs(p("dir1"))
    mkdir(p("dir1/dir2"))
    inotify = InotifyBuffer(p("dir1/dir2").encode())
    unmount(p("dir1"))

    # Wait for the event to be picked up
    inotify.read_event()

    # Ensure InotifyBuffer shuts down cleanly without raising an exception
    inotify.close()
    assert not inotify.is_alive()


def delay_call(function, seconds):
    def delayed(*args, **kwargs):
        time.sleep(seconds)

        return function(*args, **kwargs)

    return delayed


class InotifyBufferDelayedRead(InotifyBuffer):
    def run(self, *args, **kwargs):
        # Introduce a delay to trigger the race condition where the file descriptor is
        # closed prior to a read being triggered.
        self._inotify.read_events = delay_call(self._inotify.read_events, 1)

        return super().run(*args, **kwargs)


@pytest.mark.parametrize(argnames="cls", argvalues=[InotifyBuffer, InotifyBufferDelayedRead])
def test_close_should_terminate_thread(p, cls):
    inotify = cls(p("").encode(), recursive=True)

    assert inotify.is_alive()
    inotify.close()
    assert not inotify.is_alive()
