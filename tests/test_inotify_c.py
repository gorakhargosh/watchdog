from __future__ import annotations

import pytest

from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

import ctypes
import errno
import fcntl
import logging
import os
import resource
import select
import struct
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

from watchdog.events import DirCreatedEvent, DirDeletedEvent, DirModifiedEvent
from watchdog.observers.inotify_c import (
    CallbackId,
    InotifyConstants,
    InotifyEvent,
    InotifyFD,
    Mask,
    Watch,
    WatchDescriptor,
)

if TYPE_CHECKING:
    from pathlib import Path

    from .utils import Helper, P, StartWatching, TestEventQueue

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Callback:
    overflow_count = 0
    event_count = 0

    def on_event(self, event) -> None:
        self.event_count += 1

    def on_watch_deleted(self, wd) -> None:
        pass

    def on_queue_overflow(self) -> None:
        self.overflow_count += 1


def test_inotify_fd_instances_are_independent() -> None:
    inotify_fds = []
    try:
        for _ in range(2):
            inotify_fd = InotifyFD()
            inotify_fds.append(inotify_fd)
            inotify_fd.start()

        first, second = inotify_fds
        assert first is not second
        assert first._inotify_fd != second._inotify_fd  # noqa: SLF001
        assert all(inotify_fd.is_alive() for inotify_fd in inotify_fds)
    finally:
        for inotify_fd in inotify_fds:
            inotify_fd.stop()
        for inotify_fd in inotify_fds:
            inotify_fd.join(timeout=5)
        assert all(not inotify_fd.is_alive() for inotify_fd in inotify_fds)


def test_import_with_exhausted_inotify_instances() -> None:
    code = """
import ctypes
import errno
import os
import resource
import sys

libc = ctypes.CDLL(None, use_errno=True)
inotify_init = libc.inotify_init
inotify_init.argtypes = []
inotify_init.restype = ctypes.c_int

# Keep descriptors available for imports and bound resource use on hosts with
# unusually high inotify limits.
soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
max_attempts = 16384
if soft_limit != resource.RLIM_INFINITY:
    max_attempts = min(max_attempts, max(0, soft_limit - 64))

fds = []
try:
    for _ in range(max_attempts):
        fd = inotify_init()
        if fd == -1:
            error = ctypes.get_errno()
            if error != errno.EMFILE:
                print(f"SKIP: inotify_init failed with errno {error}")
                sys.exit(77)
            break
        fds.append(fd)
    else:
        print("SKIP: could not exhaust inotify instances with descriptors reserved for imports")
        sys.exit(77)

    from watchdog.events import FileSystemEventHandler
    from watchdog.observers.polling import PollingObserver
    import watchdog.observers
    from watchdog.observers.inotify import InotifyObserver
    from watchdog.observers.inotify_c import InotifyFD

    assert watchdog.observers.Observer is InotifyObserver
    assert InotifyFD._instance is None
    assert not PollingObserver().is_alive()
    try:
        InotifyObserver().schedule(FileSystemEventHandler(), ".")
    except OSError as error:
        assert error.errno == errno.EMFILE, error
        assert "inotify instance limit reached" in str(error), error
    else:
        raise AssertionError("InotifyObserver.schedule did not raise OSError")
    print("imports succeeded; InotifyObserver.schedule raised EMFILE")
finally:
    for fd in fds:
        os.close(fd)
"""
    # Propagate pytest's source path when watchdog is not installed.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=False, timeout=30
    )
    if result.returncode == 77 and result.stdout.startswith("SKIP: "):
        pytest.skip(result.stdout.strip())
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout.strip() == "imports succeeded; InotifyObserver.schedule raised EMFILE"


def struct_inotify(wd, mask, cookie=0, length=0, name=b"") -> bytes:
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
    inotify_fd.buf = b""

    const = InotifyConstants()

    # CREATE DELETE CREATE DELETE DELETE_SELF IGNORE DELETE_SELF IGNORE
    inotify_fd_buf = (
        struct_inotify(wd=1, mask=const.IN_CREATE | const.IN_ISDIR, length=16, name=b"subdir1")
        + struct_inotify(wd=1, mask=const.IN_DELETE | const.IN_ISDIR, length=16, name=b"subdir1")
    ) * 2 + (
        struct_inotify(wd=2, mask=const.IN_DELETE_SELF)
        + struct_inotify(wd=2, mask=const.IN_IGNORED)
        + struct_inotify(wd=3, mask=const.IN_DELETE_SELF)
        + struct_inotify(wd=3, mask=const.IN_IGNORED)
    )

    select_bkp = select.select

    def fakeselect(read_list, *args, **kwargs):
        if inotify_fd in read_list:
            return [inotify_fd], [], []
        return select_bkp(read_list, *args, **kwargs)

    poll_bkp = select.poll
    buf_lock = threading.Lock()

    class Fakepoll:
        def __init__(self):
            self._orig = poll_bkp()
            self._fake = False

        def register(self, fd, *args, **kwargs):
            if fd == inotify_fd:
                self._fake = True
                return None
            return self._orig.register(fd, *args, **kwargs)

        def poll(self, *args, **kwargs):
            if self._fake:
                # Only claim readability when synthetic events are queued.
                # An empty-buffer POLLIN makes InotifyFD spin in os.read and
                # race with the test thread assigning ``inotify_fd.buf``.
                with buf_lock:
                    if inotify_fd.buf:
                        return [(inotify_fd, select.POLLIN)]
                return []
            return self._orig.poll(*args, **kwargs)

    os_read_bkp = os.read

    def fakeread(fd, length):
        if fd is inotify_fd:
            # Keep buffer injection and consumption atomic so
            # ``result, fd.buf = fd.buf[:n], fd.buf[n:]`` on an empty buf
            # cannot overwrite events the test just injected.
            with buf_lock:
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
    mock6 = patch.object(select, "select", new=fakeselect)
    mock7 = patch.object(select, "poll", new=Fakepoll)
    mock8 = patch.object(inotify_c.InotifyFD, "_instance", new=None)

    with mock1, mock2, mock3, mock4, mock5, mock6, mock7, mock8:
        try:
            try:
                start_watching(path=p(""))
                with buf_lock:
                    inotify_fd.buf = inotify_fd_buf
                # Watchdog Events
                for evt_cls in [DirCreatedEvent, DirDeletedEvent] * 2:
                    event = event_queue.get(timeout=5)[0]
                    assert isinstance(event, evt_cls)
                    assert event.src_path == p("subdir1")
                    event = event_queue.get(timeout=5)[0]
                    assert isinstance(event, DirModifiedEvent)
                    assert event.src_path == p("").rstrip(os.path.sep)

                # Give InotifyFD time to process the remaining synthetic events before close
                time.sleep(0.05)
            finally:
                helper.close()
        finally:
            # reset InotifyFD singleton
            inotify_fd_instance = inotify_c.InotifyFD._instance  # noqa: SLF001
            if inotify_fd_instance.is_alive():
                inotify_fd_instance.stop()
                inotify_fd_instance.join()
            elif not inotify_fd_instance._closed:  # noqa: SLF001
                inotify_fd_instance.close()

    assert inotify_fd.last == 3  # Number of directories
    assert inotify_fd.buf == b""  # Didn't miss any event
    assert 1 not in inotify_fd.wds  # Only 1 is removed explicitly
    assert set(inotify_fd.wds) <= {2, 3}


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
        InotifyFD._raise_error()  # noqa: SLF001
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
    wd_parent_dir = WatchDescriptor(42)
    filename = b"file.ext"
    event1 = InotifyEvent(wd_parent_dir, InotifyConstants.IN_CREATE, 0, filename)
    event2 = InotifyEvent(wd_parent_dir, InotifyConstants.IN_CREATE, 0, filename)
    event3 = InotifyEvent(wd_parent_dir, InotifyConstants.IN_ACCESS, 0, filename)
    assert event1 == event2
    assert event1 != event3
    assert event2 != event3


def test_read_events_preserves_queue_overflow() -> None:
    inotify_fd = object.__new__(InotifyFD)
    inotify_fd._read_event_buffer = lambda _size: (  # type: ignore[method-assign]
        struct_inotify(-1, Mask(0)) + struct_inotify(-1, InotifyConstants.IN_Q_OVERFLOW)
    )

    events = inotify_fd.read_events()

    assert events == [InotifyEvent(WatchDescriptor(-1), InotifyConstants.IN_Q_OVERFLOW, 0, b"")]


def test_queue_overflow_notifies_each_callback_once(caplog) -> None:
    callback = Callback()
    watch_a = Watch(WatchDescriptor(1), Mask(0), b"a")
    watch_b = Watch(WatchDescriptor(2), Mask(0), b"b")
    watch_a.callbacks[CallbackId(1)] = callback
    watch_b.callbacks[CallbackId(2)] = callback
    inotify_fd = object.__new__(InotifyFD)
    inotify_fd._lock = threading.Lock()
    inotify_fd._watch_for_wd = {watch_a.wd: watch_a, watch_b.wd: watch_b}

    inotify_fd.handle_event(InotifyEvent(WatchDescriptor(-1), InotifyConstants.IN_Q_OVERFLOW, 0, b""))

    assert callback.overflow_count == 1
    assert callback.event_count == 0
    assert "Inotify queue overflowed" in caplog.text


def test_select_fd(helper: Helper, p: P, event_queue: TestEventQueue, start_watching: StartWatching) -> None:
    soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft_limit != resource.RLIM_INFINITY and soft_limit <= 1024:
        pytest.skip("A file descriptor above select()'s limit requires RLIMIT_NOFILE > 1024")

    create_inotify_fd = InotifyFD._create_inotify_fd  # noqa: SLF001

    def create_high_fd() -> int:
        fd = create_inotify_fd()
        try:
            # Exercise a real descriptor outside select()'s range without
            # opening thousands of unrelated files.
            high_fd = fcntl.fcntl(fd, fcntl.F_DUPFD, 1024)
            fcntl.fcntl(high_fd, fcntl.F_SETFD, fcntl.FD_CLOEXEC)
            return high_fd
        finally:
            os.close(fd)

    # Isolate the high descriptor from the shared singleton used by other tests.
    with (
        patch.object(InotifyFD, "_create_inotify_fd", side_effect=create_high_fd) as create_fd,
        patch.object(InotifyFD, "_instance", new=None),
    ):
        inotify_fd = InotifyFD.get_instance()
        try:
            create_fd.assert_called_once()
            # Watch this file, then trigger an event by deleting it.
            path = p("this_is_a_file")
            with open(path, "a"):
                pass
            start_watching(path=path)
            os.remove(path)
            event, _ = event_queue.get(timeout=5)
            assert event.src_path == path
        finally:
            try:
                helper.close()
            finally:
                inotify_fd.stop()
                inotify_fd.join(5)
                assert not inotify_fd.is_alive()


def test_add_callback_warn_on_duplicate(tmp_path: Path) -> None:
    path = os.fsencode(tmp_path)
    inotify_fd = InotifyFD()
    args = (path, InotifyConstants.IN_ACCESS, Callback(), CallbackId(1))

    # First call is OK
    inotify_fd.add_callback(*args)

    # The second must fire a warning
    error = (
        f"Callback with id '{args[-1]}' already exists for watch <Watch: wd={args[-1]}, mask=IN_ACCESS,"
        f" _initial_creation_path={args[0]}>, it will be overwritten."
    )
    with pytest.warns(RuntimeWarning, match=error):
        inotify_fd.add_callback(*args)
