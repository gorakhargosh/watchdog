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
from queue import Empty, SimpleQueue
from typing import TYPE_CHECKING
from unittest.mock import patch

from watchdog.events import DirCreatedEvent, DirDeletedEvent, DirModifiedEvent, EventsLostEvent, FileCreatedEvent
from watchdog.observers.inotify import InotifyWatchGroup
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
    events_lost_count = 0
    event_count = 0

    def on_event(self, event) -> None:
        self.event_count += 1

    def on_watch_deleted(self, wd) -> None:
        pass

    def on_queue_overflow(self) -> None:
        self.overflow_count += 1

    def on_events_lost(self) -> None:
        assert self.overflow_count == 1, "the loss must be reported after the recovery"
        self.events_lost_count += 1


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
    assert callback.events_lost_count == 1
    assert callback.event_count == 0
    assert "Inotify queue overflowed" in caplog.text


@pytest.mark.timeout(10)
def test_queue_overflow_reports_events_lost_once_per_watch(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching
) -> None:
    # Watches of one observer share an inotify instance, so one overflow loses events for all of them.
    os.mkdir(p("recursive"))
    os.mkdir(p("flat"))
    with open(p("file"), "w"):
        pass
    start_watching(path=p("recursive"))
    start_watching(path=p("flat"), recursive=False)
    start_watching(path=p("file"), recursive=False)

    InotifyFD.get_instance().handle_event(InotifyEvent(WatchDescriptor(-1), InotifyConstants.IN_Q_OVERFLOW, 0, b""))

    events = sorted((event_queue.get(timeout=5)[0] for _ in range(3)), key=lambda event: event.src_path)
    assert events == [
        EventsLostEvent(p("file"), is_directory=False),
        EventsLostEvent(p("flat"), is_directory=True),
        EventsLostEvent(p("recursive"), is_directory=True),
    ]
    with pytest.raises(Empty):
        event_queue.get(timeout=1)


@pytest.mark.timeout(10)
def test_events_lost_is_reported_once_the_watches_are_repaired(
    p: P, event_queue: TestEventQueue, start_watching: StartWatching, monkeypatch: pytest.MonkeyPatch
) -> None:
    inotify_fd = InotifyFD.get_instance()
    handle_event = inotify_fd.handle_event
    on_queue_overflow = InotifyWatchGroup.on_queue_overflow

    def overflow_instead(event: InotifyEvent) -> None:
        # The kernel drops the events that do not fit in its queue and reports IN_Q_OVERFLOW instead.
        if event.is_create and event.name == b"missed":
            event = InotifyEvent(WatchDescriptor(-1), InotifyConstants.IN_Q_OVERFLOW, 0, b"")
        handle_event(event)

    def slow_recovery(self: InotifyWatchGroup) -> None:
        # Leave time for a handler to react to the event before the recovery ends, were it queued too early.
        time.sleep(0.5)
        on_queue_overflow(self)

    monkeypatch.setattr(inotify_fd, "handle_event", overflow_instead)
    monkeypatch.setattr(InotifyWatchGroup, "on_queue_overflow", slow_recovery)
    os.mkdir(p("root"))
    start_watching(path=p("root"))
    os.makedirs(p("root", "missed", "child"))

    assert event_queue.get(timeout=5)[0] == EventsLostEvent(p("root"), is_directory=True)

    # A handler rescanning now must not miss a change below the directories created while events were lost.
    new_file = p("root", "missed", "child", "new")
    with open(new_file, "w"):
        pass
    while (event := event_queue.get(timeout=5)[0]) != FileCreatedEvent(new_file):
        assert not isinstance(event, EventsLostEvent)


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


def test_raw_queue_fifo() -> None:
    inotify_fd = object.__new__(InotifyFD)
    inotify_fd._lock = threading.Lock()
    inotify_fd._closed = False
    inotify_fd._raw_queue = SimpleQueue()

    received: list[bytes] = []
    cb = Callback()
    cb.on_event = lambda ev: received.append(ev.name)  # type: ignore[method-assign]
    watch = Watch(WatchDescriptor(1), Mask(InotifyConstants.IN_CREATE), b"/tmp/fifo")
    watch.callbacks[CallbackId(1)] = cb
    inotify_fd._watch_for_wd = {WatchDescriptor(1): watch}

    expected = [f"f_{b}_{i}".encode() for b in range(5) for i in range(50)]
    for b in range(5):
        chunk = b"".join(
            struct_inotify(1, InotifyConstants.IN_CREATE, length=16, name=f"f_{b}_{i}".encode()) for i in range(50)
        )
        inotify_fd._raw_queue.put(chunk)
    inotify_fd._raw_queue.put(b"")
    inotify_fd._dispatch_raw_buffers()
    assert received == expected


@pytest.mark.parametrize("method", ["stop", "close"])
def test_shutdown(method: str) -> None:
    inotify_fd = InotifyFD()
    entered = threading.Event()
    orig_check = inotify_fd._check_inotify_fd  # noqa: SLF001

    def check_and_signal(timeout_ms: int | None = None) -> bool:
        entered.set()
        return orig_check(timeout_ms)

    inotify_fd._check_inotify_fd = check_and_signal  # type: ignore[method-assign]  # noqa: SLF001
    inotify_fd.start()
    assert entered.wait(timeout=5)
    getattr(inotify_fd, method)()
    inotify_fd.join(timeout=5)
    assert not inotify_fd.is_alive()


def test_dispatcher_error_stops_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    caught: list[BaseException] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: caught.append(args.exc_value))

    inotify_fd = InotifyFD()
    cb = Callback()
    cb.on_event = lambda _ev: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]
    inotify_fd.add_callback(os.fsencode(tmp_path), InotifyConstants.IN_CREATE, cb, CallbackId(1))
    inotify_fd.start()
    try:
        (tmp_path / "trigger.txt").touch()
        inotify_fd.join(timeout=5)
        assert not inotify_fd.is_alive()
        assert isinstance(inotify_fd._dispatch_error, RuntimeError)  # noqa: SLF001
        assert any(isinstance(e, RuntimeError) and str(e) == "boom" for e in caught)
    finally:
        if inotify_fd.is_alive():
            inotify_fd.stop()
            inotify_fd.join(timeout=5)


def test_dispatcher_start_failure_closes_fd(monkeypatch: pytest.MonkeyPatch) -> None:
    inotify_fd = InotifyFD()
    monkeypatch.setattr(threading.Thread, "start", lambda _self: (_ for _ in ()).throw(RuntimeError("cannot start")))
    with pytest.raises(RuntimeError, match="cannot start"):
        inotify_fd.run()
    assert inotify_fd._closed  # noqa: SLF001


def test_reader_enqueues_while_dispatcher_blocked(tmp_path: Path) -> None:
    inotify_fd = InotifyFD()
    blocked_in_cb = threading.Event()
    release_cb = threading.Event()
    names: list[bytes] = []

    def on_event(ev: InotifyEvent) -> None:
        names.append(ev.name)
        if ev.name == b"first.txt":
            blocked_in_cb.set()
            assert release_cb.wait(timeout=5)

    cb = Callback()
    cb.on_event = on_event  # type: ignore[method-assign]
    inotify_fd.add_callback(os.fsencode(tmp_path), InotifyConstants.IN_CREATE, cb, CallbackId(1))
    inotify_fd.start()
    try:
        (tmp_path / "first.txt").touch()
        assert blocked_in_cb.wait(timeout=5)
        (tmp_path / "second.txt").touch()
        # Reader should enqueue raw buffer for second.txt while dispatcher is still blocked on first.txt
        deadline = time.monotonic() + 2.0
        while inotify_fd._raw_queue.qsize() == 0 and time.monotonic() < deadline:  # noqa: SLF001
            time.sleep(0.01)
        assert inotify_fd._raw_queue.qsize() > 0  # noqa: SLF001
        release_cb.set()

        deadline = time.monotonic() + 2.0
        while b"second.txt" not in names and time.monotonic() < deadline:
            time.sleep(0.01)
        assert b"second.txt" in names
    finally:
        release_cb.set()
        inotify_fd.stop()
        inotify_fd.join(timeout=5)


def test_parse_event_buffer_large_burst_with_varied_names() -> None:
    events_bytes: list[bytes] = []
    expected_names: list[bytes] = []
    for i in range(500):
        name = f"file_{i}_{'x' * (i % 25)}.txt".encode()
        padded_len = ((len(name) + 1 + 15) // 16) * 16
        events_bytes.append(struct_inotify(1, InotifyConstants.IN_CREATE, length=padded_len, name=name))
        expected_names.append(name)
    events_bytes.append(struct_inotify(-1, InotifyConstants.IN_Q_OVERFLOW))

    parsed = list(InotifyFD._parse_event_buffer(b"".join(events_bytes)))  # noqa: SLF001
    assert len(parsed) == 501
    assert [p[3] for p in parsed[:500]] == expected_names
    assert parsed[-1][0] == -1
    assert parsed[-1][1] & InotifyConstants.IN_Q_OVERFLOW


def test_concurrent_callback_mutation_during_handle_event() -> None:
    inotify_fd = InotifyFD.__new__(InotifyFD)
    inotify_fd._lock = threading.RLock()  # noqa: SLF001
    watch = Watch(WatchDescriptor(1), Mask(InotifyConstants.IN_CREATE), b"/tmp/mut")
    cb1 = Callback()
    cb1.on_event = lambda _ev: None  # type: ignore[method-assign]
    watch.callbacks[CallbackId(1)] = cb1
    inotify_fd._watch_for_wd = {WatchDescriptor(1): watch}  # noqa: SLF001

    mutator_started = threading.Event()
    stop_mutator = threading.Event()
    mutations = 0
    errors: list[BaseException] = []

    def mutator() -> None:
        nonlocal mutations
        try:
            idx = 2
            while not stop_mutator.is_set():
                cid = CallbackId(idx)
                cb = Callback()
                cb.on_event = lambda _ev: None  # type: ignore[method-assign]
                with inotify_fd._lock:  # noqa: SLF001
                    watch.callbacks[cid] = cb
                    watch.callbacks.pop(cid, None)
                mutations += 1
                mutator_started.set()
                idx += 1
        except BaseException as exc:
            errors.append(exc)

    t = threading.Thread(target=mutator, daemon=True)
    t.start()
    try:
        assert mutator_started.wait(timeout=2)
        ev = InotifyEvent(1, InotifyConstants.IN_CREATE, 0, b"a.txt")
        for _ in range(200):
            inotify_fd.handle_event(ev)
    finally:
        stop_mutator.set()
        t.join(timeout=2)
    assert not t.is_alive()
    assert not errors
    assert mutations > 0


def test_close_while_coalescing() -> None:
    inotify_fd = InotifyFD()
    entered_coalesce = threading.Event()
    allow_check_to_finish = threading.Event()
    orig_check = inotify_fd._check_inotify_fd  # noqa: SLF001

    def instrumented_check(timeout_ms: int | None = None) -> bool:
        if timeout_ms is not None:
            entered_coalesce.set()
            allow_check_to_finish.wait(timeout=5)
        return orig_check(timeout_ms)

    inotify_fd._check_inotify_fd = instrumented_check  # type: ignore[method-assign]  # noqa: SLF001
    first_chunk = struct_inotify(1, InotifyConstants.IN_CREATE, length=16, name=b"burst")
    coalesce_result: list[bytes] = []

    def coalesce_worker() -> None:
        res = inotify_fd._coalesce_event_buffer(first_chunk, time.perf_counter() + 10.0)  # noqa: SLF001
        coalesce_result.append(res)

    t = threading.Thread(target=coalesce_worker)
    t.start()
    try:
        assert entered_coalesce.wait(timeout=5)
        inotify_fd.close()
        allow_check_to_finish.set()
        t.join(timeout=5)
        assert not t.is_alive()
        assert coalesce_result == [first_chunk]
        assert inotify_fd._closed  # noqa: SLF001
    finally:
        allow_check_to_finish.set()
        if t.is_alive():
            inotify_fd.close()
            t.join(timeout=5)


def test_stop_while_buffers_queued() -> None:
    inotify_fd = InotifyFD()
    events_dispatched: list[InotifyEvent] = []
    inotify_fd.handle_event = events_dispatched.append  # type: ignore[method-assign]
    # Enqueue buffers into raw_queue without starting reader thread
    for i in range(10):
        chunk = struct_inotify(1, InotifyConstants.IN_CREATE, length=16, name=f"f_{i}".encode())
        inotify_fd._raw_queue.put(chunk)  # noqa: SLF001
    inotify_fd.close()
    # Draining after close should not hang and must complete cleanly
    inotify_fd._raw_queue.put(b"")  # noqa: SLF001
    inotify_fd._dispatch_raw_buffers()  # noqa: SLF001
    assert len(events_dispatched) == 0
