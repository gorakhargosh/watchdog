from __future__ import annotations

import pytest
from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

import ctypes
import errno
import logging
import os
import struct
from typing import TYPE_CHECKING
from unittest.mock import patch

from watchdog.events import DirCreatedEvent, DirDeletedEvent, DirModifiedEvent
from watchdog.observers.inotify_c import Inotify, InotifyConstants, InotifyEvent

if TYPE_CHECKING:
    from .utils import Helper, P, StartWatching, TestEventQueue

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def struct_inotify(wd, mask, cookie=0, length=0, name=b""):
    assert len(name) <= length
    struct_format = (
        "="  # (native endianness, standard sizes)
        "i"  # int      wd
        "i"  # uint32_t mask
        "i"  # uint32_t cookie
        "i"  # uint32_t len
        f"{length}s"  # char[] name
    )
    return struct.pack(struct_format, wd, mask, cookie, length, name)


def test_late_double_deletion(helper: Helper, p: P, event_queue: TestEventQueue, start_watching: StartWatching) -> None:
    inotify_fd = type("FD", (object,), {})()
    inotify_fd.last = 0
    inotify_fd.wds = []

    const = InotifyConstants()

    # CREATE DELETE CREATE DELETE DELETE_SELF IGNORE DELETE_SELF IGNORE
    inotify_fd.buf = (
        struct_inotify(wd=1, mask=const.IN_CREATE | const.IN_ISDIR, length=16, name=b"subdir1")
        + struct_inotify(wd=1, mask=const.IN_DELETE | const.IN_ISDIR, length=16, name=b"subdir1")
    ) * 2 + (
        struct_inotify(wd=2, mask=const.IN_DELETE_SELF)
        + struct_inotify(wd=2, mask=const.IN_IGNORED)
        + struct_inotify(wd=3, mask=const.IN_DELETE_SELF)
        + struct_inotify(wd=3, mask=const.IN_IGNORED)
    )

    os_read_bkp = os.read

    def fakeread(fd, length):
        if fd is inotify_fd:
            result, fd.buf = fd.buf[:length], fd.buf[length:]
            return result
        return os_read_bkp(fd, length)

    os_close_bkp = os.close

    def fakeclose(fd):
        if fd is not inotify_fd:
            os_close_bkp(fd)

    def inotify_init():
        return inotify_fd

    def inotify_add_watch(fd, path, mask):
        fd.last += 1
        logger.debug("New wd = %d", fd.last)
        fd.wds.append(fd.last)
        return fd.last

    def inotify_rm_watch(fd, wd):
        logger.debug("Removing wd = %d", wd)
        fd.wds.remove(wd)
        return 0

    # Mocks the API!
    from watchdog.observers import inotify_c

    mock1 = patch.object(os, "read", new=fakeread)
    mock2 = patch.object(os, "close", new=fakeclose)
    mock3 = patch.object(inotify_c, "inotify_init", new=inotify_init)
    mock4 = patch.object(inotify_c, "inotify_add_watch", new=inotify_add_watch)
    mock5 = patch.object(inotify_c, "inotify_rm_watch", new=inotify_rm_watch)

    with mock1, mock2, mock3, mock4, mock5:
        start_watching(path=p(""))
        # Watchdog Events
        for evt_cls in [DirCreatedEvent, DirDeletedEvent] * 2:
            event = event_queue.get(timeout=5)[0]
            assert isinstance(event, evt_cls)
            assert event.src_path == p("subdir1")
            event = event_queue.get(timeout=5)[0]
            assert isinstance(event, DirModifiedEvent)
            assert event.src_path == p("").rstrip(os.path.sep)
        helper.close()

    assert inotify_fd.last == 3  # Number of directories
    assert inotify_fd.buf == b""  # Didn't miss any event
    assert inotify_fd.wds == [2, 3]  # Only 1 is removed explicitly


@pytest.mark.parametrize(
    ("error", "pattern"),
    [
        (errno.ENOSPC, "inotify watch limit reached"),
        (errno.EMFILE, "inotify instance limit reached"),
        (errno.ENOENT, "No such file or directory"),
        (-1, "error"),
    ],
)
def test_raise_error(error, pattern):
    with patch.object(ctypes, "get_errno", new=lambda: error), pytest.raises(OSError, match=pattern) as exc:
        Inotify._raise_error()  # noqa: SLF001
    assert exc.value.errno == error


def test_non_ascii_path(p: P, event_queue: TestEventQueue, start_watching: StartWatching) -> None:
    """
    Inotify can construct an event for a path containing non-ASCII.
    """
    path = p("\N{SNOWMAN}")
    start_watching(path=p(""))
    os.mkdir(path)
    event, _ = event_queue.get(timeout=5)
    assert isinstance(event.src_path, str)
    assert event.src_path == path
    # Just make sure it doesn't raise an exception.
    assert repr(event)


def test_watch_file(p: P, event_queue: TestEventQueue, start_watching: StartWatching) -> None:
    path = p("this_is_a_file")
    with open(path, "a"):
        pass
    start_watching(path=path)
    os.remove(path)
    event, _ = event_queue.get(timeout=5)
    assert repr(event)


def test_event_equality(p: P) -> None:
    wd_parent_dir = 42
    filename = "file.ext"
    full_path = p(filename)
    event1 = InotifyEvent(wd_parent_dir, InotifyConstants.IN_CREATE, 0, filename, full_path)
    event2 = InotifyEvent(wd_parent_dir, InotifyConstants.IN_CREATE, 0, filename, full_path)
    event3 = InotifyEvent(wd_parent_dir, InotifyConstants.IN_ACCESS, 0, filename, full_path)
    assert event1 == event2
    assert event1 != event3
    assert event2 != event3
