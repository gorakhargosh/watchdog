""":module: watchdog.observers.winapi
:synopsis: Windows API-Python interface (removes dependency on ``pywin32``).
:author: theller@ctypes.org (Thomas Heller)
:author: will@willmcgugan.com (Will McGugan)
:author: ryan@rfk.id.au (Ryan Kelly)
:author: yesudeep@gmail.com (Yesudeep Mangalapilly)
:author: thomas.amland@gmail.com (Thomas Amland)
:author: Mickaël Schoentgen <contact@tiger-222.fr>
:platforms: windows
"""

from __future__ import annotations

import contextlib
import ctypes
import queue
import threading
from ctypes.wintypes import BOOL, DWORD, HANDLE, LPCWSTR, LPVOID, LPWSTR
from dataclasses import dataclass
from functools import reduce
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

# Invalid handle value.
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# File notification constants.
FILE_NOTIFY_CHANGE_FILE_NAME = 0x01
FILE_NOTIFY_CHANGE_DIR_NAME = 0x02
FILE_NOTIFY_CHANGE_ATTRIBUTES = 0x04
FILE_NOTIFY_CHANGE_SIZE = 0x08
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x010
FILE_NOTIFY_CHANGE_LAST_ACCESS = 0x020
FILE_NOTIFY_CHANGE_CREATION = 0x040
FILE_NOTIFY_CHANGE_SECURITY = 0x0100

FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OVERLAPPED = 0x40000000
FILE_LIST_DIRECTORY = 1
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
FILE_SHARE_DELETE = 0x04
OPEN_EXISTING = 3

VOLUME_NAME_NT = 0x02

# File action constants.
FILE_ACTION_CREATED = 1
FILE_ACTION_DELETED = 2
FILE_ACTION_MODIFIED = 3
FILE_ACTION_RENAMED_OLD_NAME = 4
FILE_ACTION_RENAMED_NEW_NAME = 5
FILE_ACTION_DELETED_SELF = 0xFFFE
FILE_ACTION_OVERFLOW = 0xFFFF

# Aliases
FILE_ACTION_ADDED = FILE_ACTION_CREATED
FILE_ACTION_REMOVED = FILE_ACTION_DELETED
FILE_ACTION_REMOVED_SELF = FILE_ACTION_DELETED_SELF

THREAD_TERMINATE = 0x0001

# IO waiting constants.
WAIT_ABANDONED = 0x00000080
WAIT_IO_COMPLETION = 0x000000C0
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102

# Error codes
ERROR_OPERATION_ABORTED = 995
ERROR_ELEMENT_NOT_FOUND = 1168


class OVERLAPPED(ctypes.Structure):
    _fields_ = (
        ("Internal", LPVOID),
        ("InternalHigh", LPVOID),
        ("Offset", DWORD),
        ("OffsetHigh", DWORD),
        ("Pointer", LPVOID),
        ("hEvent", HANDLE),
    )


def _errcheck_bool(value: Any | None, func: Any, args: Any) -> Any:
    if not value:
        raise ctypes.WinError()  # type: ignore[attr-defined]
    return args


def _errcheck_handle(value: Any | None, func: Any, args: Any) -> Any:
    if not value:
        raise ctypes.WinError()  # type: ignore[attr-defined]
    if value == INVALID_HANDLE_VALUE:
        raise ctypes.WinError()  # type: ignore[attr-defined]
    return args


def _errcheck_dword(value: Any | None, func: Any, args: Any) -> Any:
    if value == 0xFFFFFFFF:
        raise ctypes.WinError()  # type: ignore[attr-defined]
    return args


kernel32 = ctypes.WinDLL("kernel32")  # type: ignore[attr-defined]

ReadDirectoryChangesW = kernel32.ReadDirectoryChangesW
ReadDirectoryChangesW.restype = BOOL
ReadDirectoryChangesW.errcheck = _errcheck_bool
ReadDirectoryChangesW.argtypes = (
    HANDLE,  # hDirectory
    LPVOID,  # lpBuffer
    DWORD,  # nBufferLength
    BOOL,  # bWatchSubtree
    DWORD,  # dwNotifyFilter
    ctypes.POINTER(DWORD),  # lpBytesReturned
    ctypes.POINTER(OVERLAPPED),  # lpOverlapped
    LPVOID,  # FileIOCompletionRoutine # lpCompletionRoutine
)

CreateFileW = kernel32.CreateFileW
CreateFileW.restype = HANDLE
CreateFileW.errcheck = _errcheck_handle
CreateFileW.argtypes = (
    LPCWSTR,  # lpFileName
    DWORD,  # dwDesiredAccess
    DWORD,  # dwShareMode
    LPVOID,  # lpSecurityAttributes
    DWORD,  # dwCreationDisposition
    DWORD,  # dwFlagsAndAttributes
    HANDLE,  # hTemplateFile
)

CloseHandle = kernel32.CloseHandle
CloseHandle.restype = BOOL
CloseHandle.argtypes = (HANDLE,)  # hObject

CancelIoEx = kernel32.CancelIoEx
CancelIoEx.restype = BOOL
CancelIoEx.errcheck = _errcheck_bool
CancelIoEx.argtypes = (
    HANDLE,  # hObject
    ctypes.POINTER(OVERLAPPED),  # lpOverlapped
)

CreateEvent = kernel32.CreateEventW
CreateEvent.restype = HANDLE
CreateEvent.errcheck = _errcheck_handle
CreateEvent.argtypes = (
    LPVOID,  # lpEventAttributes
    BOOL,  # bManualReset
    BOOL,  # bInitialState
    LPCWSTR,  # lpName
)

SetEvent = kernel32.SetEvent
SetEvent.restype = BOOL
SetEvent.errcheck = _errcheck_bool
SetEvent.argtypes = (HANDLE,)  # hEvent

WaitForSingleObjectEx = kernel32.WaitForSingleObjectEx
WaitForSingleObjectEx.restype = DWORD
WaitForSingleObjectEx.errcheck = _errcheck_dword
WaitForSingleObjectEx.argtypes = (
    HANDLE,  # hObject
    DWORD,  # dwMilliseconds
    BOOL,  # bAlertable
)

CreateIoCompletionPort = kernel32.CreateIoCompletionPort
CreateIoCompletionPort.restype = HANDLE
CreateIoCompletionPort.errcheck = _errcheck_handle
CreateIoCompletionPort.argtypes = (
    HANDLE,  # FileHandle
    HANDLE,  # ExistingCompletionPort
    LPVOID,  # CompletionKey
    DWORD,  # NumberOfConcurrentThreads
)

GetQueuedCompletionStatus = kernel32.GetQueuedCompletionStatus
GetQueuedCompletionStatus.restype = BOOL
GetQueuedCompletionStatus.errcheck = _errcheck_bool
GetQueuedCompletionStatus.argtypes = (
    HANDLE,  # CompletionPort
    LPVOID,  # lpNumberOfBytesTransferred
    LPVOID,  # lpCompletionKey
    ctypes.POINTER(OVERLAPPED),  # lpOverlapped
    DWORD,  # dwMilliseconds
)

PostQueuedCompletionStatus = kernel32.PostQueuedCompletionStatus
PostQueuedCompletionStatus.restype = BOOL
PostQueuedCompletionStatus.errcheck = _errcheck_bool
PostQueuedCompletionStatus.argtypes = (
    HANDLE,  # CompletionPort
    DWORD,  # lpNumberOfBytesTransferred
    DWORD,  # lpCompletionKey
    ctypes.POINTER(OVERLAPPED),  # lpOverlapped
)


GetFinalPathNameByHandleW = kernel32.GetFinalPathNameByHandleW
GetFinalPathNameByHandleW.restype = DWORD
GetFinalPathNameByHandleW.errcheck = _errcheck_dword
GetFinalPathNameByHandleW.argtypes = (
    HANDLE,  # hFile
    LPWSTR,  # lpszFilePath
    DWORD,  # cchFilePath
    DWORD,  # DWORD
)


class FileNotifyInformation(ctypes.Structure):
    _fields_ = (
        ("NextEntryOffset", DWORD),
        ("Action", DWORD),
        ("FileNameLength", DWORD),
        ("FileName", (ctypes.c_char * 1)),
    )


LPFNI = ctypes.POINTER(FileNotifyInformation)


# We don't need to recalculate these flags every time a call is made to
# the win32 API functions.
WATCHDOG_FILE_FLAGS = FILE_FLAG_BACKUP_SEMANTICS
WATCHDOG_FILE_SHARE_FLAGS = reduce(
    lambda x, y: x | y,
    [
        FILE_SHARE_READ,
        FILE_SHARE_WRITE,
        FILE_SHARE_DELETE,
    ],
)
WATCHDOG_FILE_NOTIFY_FLAGS = reduce(
    lambda x, y: x | y,
    [
        FILE_NOTIFY_CHANGE_FILE_NAME,
        FILE_NOTIFY_CHANGE_DIR_NAME,
        FILE_NOTIFY_CHANGE_ATTRIBUTES,
        FILE_NOTIFY_CHANGE_SIZE,
        FILE_NOTIFY_CHANGE_LAST_WRITE,
        FILE_NOTIFY_CHANGE_SECURITY,
        FILE_NOTIFY_CHANGE_LAST_ACCESS,
        FILE_NOTIFY_CHANGE_CREATION,
    ],
)

# ReadDirectoryChangesW buffer length.
# To handle cases with lot of changes, this seems the highest safest value we can use.
# Note: it will fail with ERROR_INVALID_PARAMETER when it is greater than 64 KB and
#       the application is monitoring a directory over the network.
#       This is due to a packet size limitation with the underlying file sharing protocols.
#       https://docs.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-readdirectorychangesw#remarks
BUFFER_SIZE = 64000

# Buffer length for path-related stuff.
# Introduced to keep the old behavior when we bumped BUFFER_SIZE from 2048 to 64000 in v1.0.0.
PATH_BUFFER_SIZE = 2048


def _parse_event_buffer(read_buffer: bytes) -> list[tuple[int, str]]:
    n_bytes = len(read_buffer)
    results = []
    while n_bytes > 0:
        fni = ctypes.cast(read_buffer, LPFNI)[0]  # type: ignore[arg-type]
        ptr = ctypes.addressof(fni) + FileNotifyInformation.FileName.offset
        filename = ctypes.string_at(ptr, fni.FileNameLength)
        results.append((fni.Action, filename.decode("utf-16")))
        num_to_skip = fni.NextEntryOffset
        if num_to_skip <= 0:
            break
        read_buffer = read_buffer[num_to_skip:]
        n_bytes -= num_to_skip  # num_to_skip is long. n_bytes should be long too.
    return results


def _is_observed_path_deleted(handle: HANDLE, path: str) -> bool:
    # Comparison of observed path and actual path, returned by
    # GetFinalPathNameByHandleW. If directory moved to the trash bin, or
    # deleted, actual path will not be equal to observed path.
    buff = ctypes.create_unicode_buffer(PATH_BUFFER_SIZE)
    GetFinalPathNameByHandleW(handle, buff, PATH_BUFFER_SIZE, VOLUME_NAME_NT)
    return buff.value != path


def _generate_observed_path_deleted_event() -> bytes:
    # Create synthetic event for notify that observed directory is deleted
    path = ctypes.create_unicode_buffer(".")
    event = FileNotifyInformation(0, FILE_ACTION_DELETED_SELF, len(path), path.value.encode("utf-8"))
    event_size = ctypes.sizeof(event)
    buff = ctypes.create_string_buffer(PATH_BUFFER_SIZE)
    ctypes.memmove(buff, ctypes.addressof(event), event_size)
    return buff.raw[:event_size]


def _get_directory_handle(path: str) -> HANDLE:
    """Returns a Windows handle to the specified directory path."""
    return CreateFileW(
        path,
        FILE_LIST_DIRECTORY,
        WATCHDOG_FILE_SHARE_FLAGS,
        None,
        OPEN_EXISTING,
        WATCHDOG_FILE_FLAGS,
        None,
    )


def _cancel_handle_io(handle: HANDLE) -> None:
    try:
        CancelIoEx(handle, None)
    except OSError as e:
        if e.winerror == ERROR_ELEMENT_NOT_FOUND:  # type: ignore[attr-defined]
            # Happens when the directory has been deleted, ignore.
            return
        raise


def _close_directory_handle(handle: HANDLE) -> None:
    with contextlib.suppress(OSError):
        CloseHandle(handle)


@dataclass(unsafe_hash=True)
class WinAPINativeEvent:
    action: int
    src_path: str

    @property
    def is_added(self) -> bool:
        return self.action == FILE_ACTION_ADDED

    @property
    def is_removed(self) -> bool:
        return self.action == FILE_ACTION_REMOVED

    @property
    def is_modified(self) -> bool:
        return self.action == FILE_ACTION_MODIFIED

    @property
    def is_renamed_old(self) -> bool:
        return self.action == FILE_ACTION_RENAMED_OLD_NAME

    @property
    def is_renamed_new(self) -> bool:
        return self.action == FILE_ACTION_RENAMED_NEW_NAME

    @property
    def is_removed_self(self) -> bool:
        return self.action == FILE_ACTION_REMOVED_SELF


class DirectoryChangeReader:
    """Uses ReadDirectoryChangesW() to detect file system changes.  A separate
    thread is used to make that call in order to reduce the time window
    in that events may be lost.  The processing of data receieved from
    ReadDirectoryChangesW() is queued and processed by another thread.
    """

    def __init__(self, path: str, *, recursive: bool) -> None:
        self._path = path
        self._recursive = recursive
        self._reader_thread: threading.Thread | None = None
        self._handle: HANDLE | None = None
        self._should_stop = False
        self._buf_queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()

    def _run_inner(self, handle: HANDLE, event_buffer: ctypes.Array[ctypes.c_char], nbytes: DWORD) -> None:
        # This runs in its own thread and it makes a single call to
        # ReadDirectoryChangesW().  This blocks until at least some events are
        # available (or there is an error).  We will re-use the _event_buffer
        # and so we copy the data into a second buffer (double-buffering
        # technique) and queue it for another thread to process.  This reduces
        # the time window in which we could miss events.
        try:
            ReadDirectoryChangesW(
                handle,
                ctypes.byref(event_buffer),
                len(event_buffer),
                self._recursive,
                WATCHDOG_FILE_NOTIFY_FLAGS,
                ctypes.byref(nbytes),
                None,
                None,
            )
            buf = event_buffer.raw[: nbytes.value]
        except OSError as e:
            if e.winerror == ERROR_OPERATION_ABORTED:  # type: ignore[attr-defined]
                return
            if _is_observed_path_deleted(handle, self._path):
                # Handle the case when the root path is deleted
                with self._lock:
                    # Additional calls to ReadDirectoryChangesW() will fail so stop.
                    self._should_stop = True
                # Create synthetic event for deletion
                buf = _generate_observed_path_deleted_event()
            else:
                raise
        self._buf_queue.put(buf)

    def _run(self) -> None:
        with self._lock:
            assert self._handle is None
            handle = self._handle = _get_directory_handle(self._path)
        # To improve performance and reduce the window in which events can be
        # missed, we re-use these for each call to _run_inner().
        event_buffer = ctypes.create_string_buffer(BUFFER_SIZE)
        nbytes = DWORD()
        self._buf_queue.put(b'')  # indicates that this thread has started
        try:
            while not self._should_stop:
                self._run_inner(handle, event_buffer, nbytes)
        finally:
            # Note that a HANDLE value can be re-used by the OS once we close
            # it.  So we need to be careful not to hang on to the value after
            # we close it.
            with self._lock:
                self._handle = None
            _close_directory_handle(handle)

    def start(self) -> None:
        with self._lock:
            assert self._reader_thread is None
            if self._should_stop:
                return  # stop already called, do not start
            self._reader_thread = threading.Thread(target=self._run)
        self._reader_thread.start()
        # Wait for empty bytes object, indicating reader thread has started.
        # This reduces the time window between this method returning and the
        # actual ReadDirectoryChangesW() call, which reduces the time that
        # events could be missed.
        _ = self._buf_queue.get(timeout=2)

    def stop(self) -> None:
        with self._lock:
            if self._should_stop:
                return  # already stopping
            self._should_stop = True
            reader_thread = self._reader_thread
            if reader_thread is None:
                return  # never started
            self._reader_thread = None
            if self._handle is not None:
                # Note that we don't close the handle here but let the reader
                # thread do that.  The _should_stop flag will tell it to exit the
                # _run loop, cleanup and exit.  Since it might be blocked inside
                # ReadDirectoryChangesW, we call CancelIoEx to wake it. This
                # cancel call is done while holding self._lock so that the run
                # thread cannot race with us and close the handle before we
                # make this call.
                _cancel_handle_io(self._handle)
        reader_thread.join()

    def get_events(self, timeout: float) -> list[WinAPINativeEvent]:
        events = []
        while True:
            try:
                buf = self._buf_queue.get(timeout=timeout)
            except queue.Empty:
                break
            events.extend(_parse_event_buffer(buf))
        return [WinAPINativeEvent(action, src_path) for action, src_path in events]
