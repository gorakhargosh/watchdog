from __future__ import annotations

import os
import os.path
import stat
import struct
import threading
from queue import Empty, Queue
from time import sleep
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from watchdog.events import DirCreatedEvent, DirMovedEvent, FileAttribEvent, FileMovedEvent
from watchdog.observers.api import ObservedWatch
from watchdog.utils import platform

from .shell import mkdir, mkdtemp, mv, rm

# make pytest aware this is windows only
if not platform.is_windows():
    pytest.skip("Windows only.", allow_module_level=True)

if TYPE_CHECKING:
    from typing import Self

from watchdog.observers.read_directory_changes import WindowsApiEmitter
from watchdog.observers.winapi import (
    FILE_ACTION_CREATED,
    FILE_ACTION_DELETED,
    FILE_ACTION_DELETED_SELF,
    FILE_ACTION_MODIFIED,
    FILE_ACTION_RENAMED_NEW_NAME,
    FILE_ACTION_RENAMED_OLD_NAME,
    DirectoryChangeReader,
    WinAPINativeEvent,
    _drop_case_only_rename_deletions,
    _generate_observed_path_deleted_event,
    _parse_event_buffer,
    _parse_extended_event_buffer,
)

SLEEP_TIME = 2

# Path with non-ASCII
temp_dir = os.path.join(mkdtemp(), "Strange \N{SNOWMAN}")
os.makedirs(temp_dir)


def p(*args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return os.path.join(temp_dir, *args)


@pytest.fixture
def event_queue():
    return Queue()


@pytest.fixture
def emitter(event_queue):
    watch = ObservedWatch(temp_dir, recursive=True)
    em = WindowsApiEmitter(event_queue, watch, timeout=0.2)
    yield em
    em.stop()


def test___init__(event_queue, emitter):
    emitter.start()
    sleep(SLEEP_TIME)
    mkdir(p("fromdir"))

    sleep(SLEEP_TIME)
    mv(p("fromdir"), p("todir"))

    sleep(SLEEP_TIME)
    emitter.stop()
    sleep(SLEEP_TIME)  # time for background thread to exit

    # What we need here for the tests to pass is a collection type
    # that is:
    #   * unordered
    #   * non-unique
    # A multiset! Python's collections.Counter class seems appropriate.
    expected = {
        DirCreatedEvent(p("fromdir")),
        DirMovedEvent(p("fromdir"), p("todir")),
    }

    got = set()

    while True:
        try:
            event, _ = event_queue.get_nowait()
        except Empty:
            break
        else:
            if event.event_type == "modified":
                # On Windows can get one or two modified events.  Ignore
                # them to make test more deterministic.
                continue
            got.add(event)

    assert expected == got


def test_windows_api_emitter_attrib_event(event_queue, emitter):
    file_path = p("attr_file.txt")
    with open(file_path, "w") as f:
        f.write("initial")

    emitter.start()
    sleep(SLEEP_TIME)

    os.chmod(file_path, stat.S_IREAD)
    sleep(SLEEP_TIME)

    emitter.stop()
    sleep(SLEEP_TIME)

    os.chmod(file_path, stat.S_IWRITE)

    got = []
    while True:
        try:
            event, _ = event_queue.get_nowait()
        except Empty:
            break
        else:
            got.append(event)

    assert any(isinstance(ev, FileAttribEvent) and ev.src_path == file_path for ev in got)


def test_root_deleted(event_queue, emitter):
    r"""Test the event got when removing the watched folder.
    The regression to prevent is:

        Exception in thread Thread-1:
        Traceback (most recent call last):
        File "watchdog\observers\winapi.py", line 333, in read_directory_changes
            ctypes.byref(nbytes), None, None)
        File "watchdog\observers\winapi.py", line 105, in _errcheck_bool
            raise ctypes.WinError()
        PermissionError: [WinError 5] Access refused.

        During handling of the above exception, another exception occurred:

        Traceback (most recent call last):
        File "C:\Python37-32\lib\threading.py", line 926, in _bootstrap_inner
            self.run()
        File "watchdog\observers\api.py", line 145, in run
            self.queue_events(self.timeout)
        File "watchdog\observers\read_directory_changes.py", line 76, in queue_events
            winapi_events = self._read_events()
        File "watchdog\observers\read_directory_changes.py", line 73, in _read_events
            return read_events(self._whandle, self.watch.path, recursive=self.watch.is_recursive)
        File "watchdog\observers\winapi.py", line 387, in read_events
            buf, nbytes = read_directory_changes(handle, path, recursive=recursive)
        File "watchdog\observers\winapi.py", line 340, in read_directory_changes
            return _generate_observed_path_deleted_event()
        File "watchdog\observers\winapi.py", line 298, in _generate_observed_path_deleted_event
            event = FileNotifyInformation(0, FILE_ACTION_DELETED_SELF, len(path), path.value)
        TypeError: expected bytes, str found
    """

    emitter.start()
    sleep(SLEEP_TIME)

    # This should not fail
    rm(p(), recursive=True)
    sleep(SLEEP_TIME)

    # The emitter is automatically stopped, with no error
    assert not emitter.should_keep_running()


def test_queue_events_locks_reader_access():
    """Regression test for #1170.

    on_thread_stop() clears _reader while holding self._lock, so queue_events()
    must read _reader under the same lock. Otherwise a concurrent stop could
    leave queue_events() processing events from a reader that is being stopped.
    """

    emitter = WindowsApiEmitter(Queue(), ObservedWatch(temp_dir, recursive=True), timeout=0.05)

    class DummyReader:
        def get_events(self, timeout: float) -> list:
            return []

        def stop(self) -> None:
            pass

    emitter._reader = DummyReader()  # noqa: SLF001

    locked = threading.Event()

    class TrackingLock:
        def __init__(self) -> None:
            self._lock = threading.RLock()

        def __enter__(self) -> Self:
            locked.set()
            self._lock.acquire()
            return self

        def __exit__(self, *exc_info: object) -> None:
            self._lock.release()

    emitter._lock = TrackingLock()  # noqa: SLF001

    emitter.queue_events(0)

    assert locked.is_set()


def test_drop_case_only_rename_deletions():
    """A case-only rename is reported with an extra deletion of the old name."""
    events = [
        WinAPINativeEvent(FILE_ACTION_DELETED, "file"),
        WinAPINativeEvent(FILE_ACTION_RENAMED_OLD_NAME, "file"),
        WinAPINativeEvent(FILE_ACTION_RENAMED_NEW_NAME, "FILE"),
    ]

    assert _drop_case_only_rename_deletions(events) == events[1:]


@pytest.mark.parametrize(
    "events",
    [
        # A deletion is only spurious when the very next record renames that same
        # path, so a path deleted, recreated and only then renamed is left alone.
        [
            WinAPINativeEvent(FILE_ACTION_DELETED, "file"),
            WinAPINativeEvent(FILE_ACTION_CREATED, "file"),
            WinAPINativeEvent(FILE_ACTION_RENAMED_OLD_NAME, "file"),
            WinAPINativeEvent(FILE_ACTION_RENAMED_NEW_NAME, "other"),
        ],
        # A deletion followed by the rename of a different path.
        [
            WinAPINativeEvent(FILE_ACTION_DELETED, "file"),
            WinAPINativeEvent(FILE_ACTION_RENAMED_OLD_NAME, "other"),
            WinAPINativeEvent(FILE_ACTION_RENAMED_NEW_NAME, "OTHER"),
        ],
        # A deletion closing the batch, which is how a plain deletion is reported.
        [WinAPINativeEvent(FILE_ACTION_DELETED, "file")],
    ],
)
def test_drop_case_only_rename_deletions_keeps_real_deletions(events):
    assert _drop_case_only_rename_deletions(events) == events


@pytest.mark.parametrize(
    "file_name",
    [
        "plain.txt",
        # U+FEFF is a legal file name character that "utf-16" eats as a byte-order
        # mark, silently reporting the event against a different, possibly existing,
        # file. U+FFFE flips the byte order the rest of the name is decoded with.
        "\ufeffhello.txt",
        "\ufffehello.txt",
    ],
)
def test_parse_event_buffer_reads_the_whole_file_name(file_name):
    """ReadDirectoryChangesW writes UTF-16LE without a byte-order mark."""
    name = file_name.encode("utf-16-le")
    buffer = struct.pack("<III", 0, FILE_ACTION_CREATED, len(name)) + name

    assert _parse_event_buffer(buffer) == [(FILE_ACTION_CREATED, file_name)]


def test_on_thread_stop_is_idempotent():
    """A second ``on_thread_stop()`` must not stop the reader again.

    ``BaseThread.stop()`` calls ``on_thread_stop()`` unconditionally, and an
    emitter is routinely stopped more than once: ``unschedule_all()`` stops
    every emitter, and the caller may still hold a reference of its own.
    See #1132.

    This builds its own directory instead of using the ``emitter`` fixture,
    because ``test_root_deleted`` removes ``temp_dir``.
    """
    watched = os.path.join(mkdtemp(), "idempotent")
    os.makedirs(watched)
    emitter = WindowsApiEmitter(Queue(), ObservedWatch(watched, recursive=True), timeout=0.2)
    emitter.start()
    sleep(SLEEP_TIME)

    calls = []
    real_stop = DirectoryChangeReader.stop

    def counting_stop(self, *args, **kwargs):
        calls.append(self)
        return real_stop(self, *args, **kwargs)

    try:
        with patch.object(DirectoryChangeReader, "stop", counting_stop):
            emitter.on_thread_stop()
            assert emitter._reader is None  # noqa: SLF001
            assert len(calls) == 1

            emitter.on_thread_stop()
            assert len(calls) == 1
    finally:
        emitter.stop()
        sleep(SLEEP_TIME)  # time for background thread to exit


def test_rename_split_across_two_batches_keeps_the_source_path(event_queue, emitter):
    """A rename keeps its source path when its two halves arrive in different batches.

    ``DirectoryChangeReader`` queues one buffer per ``ReadDirectoryChangesW()``
    completion and ``get_events()`` returns whatever has arrived, so the
    ``FILE_ACTION_RENAMED_OLD_NAME`` and ``FILE_ACTION_RENAMED_NEW_NAME`` records for
    one rename are not guaranteed to reach a single ``queue_events()`` call. Pairing
    state scoped to the call turned the second half into a move event whose
    ``src_path`` was the empty string.
    """

    class SplitReader:
        def __init__(self):
            self.batches = [
                [WinAPINativeEvent(FILE_ACTION_RENAMED_OLD_NAME, "old_name")],
                [WinAPINativeEvent(FILE_ACTION_RENAMED_NEW_NAME, "new_name")],
            ]

        def get_events(self, timeout):
            return self.batches.pop(0) if self.batches else []

        def stop(self):
            pass

    emitter._reader = SplitReader()  # noqa: SLF001

    emitter.queue_events(emitter.timeout)
    assert event_queue.empty()

    emitter.queue_events(emitter.timeout)
    event, _ = event_queue.get_nowait()

    assert event == FileMovedEvent(p("old_name"), p("new_name"))


@pytest.mark.parametrize(
    ("last_change_time", "last_mod_time", "expected_attrib"),
    [
        (200, 100, True),
        (100, 100, False),
        (50, 100, False),
    ],
)
def test_parse_extended_event_buffer_modified(last_change_time, last_mod_time, expected_attrib):
    name = "test.txt".encode("utf-16-le")
    buffer = (
        struct.pack(
            "<IIqqqqqqIIqqI",
            0,
            FILE_ACTION_MODIFIED,
            0,
            last_mod_time,
            last_change_time,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            len(name),
        )
        + name
    )
    events = _parse_extended_event_buffer(buffer)
    assert events == [(FILE_ACTION_MODIFIED, "test.txt", expected_attrib)]


def test_winapi_native_event_is_attrib():
    attrib_event = WinAPINativeEvent(FILE_ACTION_MODIFIED, "test.txt", is_attrib=True)
    assert attrib_event.is_attrib
    assert not attrib_event.is_modified

    modified_event = WinAPINativeEvent(FILE_ACTION_MODIFIED, "test.txt", is_attrib=False)
    assert not modified_event.is_attrib
    assert modified_event.is_modified


def test_generate_observed_path_deleted_event():
    buf_extended = _generate_observed_path_deleted_event(extended=True)
    events_extended = _parse_extended_event_buffer(buf_extended)
    assert events_extended == [(FILE_ACTION_DELETED_SELF, ".", False)]

    buf_standard = _generate_observed_path_deleted_event(extended=False)
    events_standard = _parse_event_buffer(buf_standard)
    assert events_standard == [(FILE_ACTION_DELETED_SELF, ".")]
