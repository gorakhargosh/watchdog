from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import select
import struct
import threading
import warnings
from ctypes import c_char_p, c_int, c_uint32
from dataclasses import dataclass, field
from functools import reduce
from typing import TYPE_CHECKING, ClassVar, Callable, NewType, Protocol

from watchdog.utils import UnsupportedLibcError, BaseThread

if TYPE_CHECKING:
    from collections.abc import Generator

libc = ctypes.CDLL(None)

if not hasattr(libc, "inotify_init") or not hasattr(libc, "inotify_add_watch") or not hasattr(libc, "inotify_rm_watch"):
    error = f"Unsupported libc version found: {libc._name}"  # noqa:SLF001
    raise UnsupportedLibcError(error)


# ##############################################################################
# TODOs:
# - todo use enum.Flag for events & mask.
# - todo handle watches that do not follow move events
# - todo handle recursive watches
# - todo fire DirModifiedEvents
# - todo investigate: inotify does not generate move events for self? (e.g. watch on file F and F gets moved)
#     observation 1: watch follows the file, but no move event is generated.
# - todo handle this scenario:
#     1: crete watch for file F
#     2: move or rename F
#     3: create new watch for F at new Path
#     4: there now must be 2 Watch objects registered with the same watch id or the original Watch object must be reused
# - todo
# ##############################################################################


WatchDescriptor = NewType("WatchDescriptor", int)
Mask = NewType("Mask", int)

inotify_add_watch: Callable[[int, bytes, int], WatchDescriptor] = ctypes.CFUNCTYPE(c_int, c_int, c_char_p, c_uint32, use_errno=True)(("inotify_add_watch", libc))

inotify_rm_watch: Callable[[int, WatchDescriptor], int] = ctypes.CFUNCTYPE(c_int, c_int, c_uint32, use_errno=True)(("inotify_rm_watch", libc))

inotify_init = ctypes.CFUNCTYPE(c_int, use_errno=True)(("inotify_init", libc))


class InotifyConstants:
    # User-space events
    IN_ACCESS: ClassVar[Mask] = 0x00000001  # File was accessed.
    IN_MODIFY: ClassVar[Mask] = 0x00000002  # File was modified.
    IN_ATTRIB: ClassVar[Mask] = 0x00000004  # Meta-data changed.
    IN_CLOSE_WRITE: ClassVar[Mask] = 0x00000008  # Writable file was closed.
    IN_CLOSE_NOWRITE: ClassVar[Mask] = 0x00000010  # Unwritable file closed.
    IN_OPEN: ClassVar[Mask] = 0x00000020  # File was opened.
    IN_MOVED_FROM: ClassVar[Mask] = 0x00000040  # File was moved from X.
    IN_MOVED_TO: ClassVar[Mask] = 0x00000080  # File was moved to Y.
    IN_CREATE: ClassVar[Mask] = 0x00000100  # Subfile was created.
    IN_DELETE: ClassVar[Mask] = 0x00000200  # Subfile was deleted.
    IN_DELETE_SELF: ClassVar[Mask] = 0x00000400  # Self was deleted.
    IN_MOVE_SELF: ClassVar[Mask] = 0x00000800  # Self was moved.

    # Helper user-space events.
    IN_MOVE: ClassVar[Mask] = IN_MOVED_FROM | IN_MOVED_TO  # Moves.

    # Events sent by the kernel to a watch.
    IN_UNMOUNT: ClassVar[Mask] = 0x00002000  # Backing file system was unmounted.
    IN_Q_OVERFLOW: ClassVar[Mask] = 0x00004000  # Event queued overflowed.
    IN_IGNORED: ClassVar[Mask] = 0x00008000  # File was ignored.

    # Special flags.
    IN_ONLYDIR: ClassVar[Mask] = 0x01000000  # Only watch the path if it's a directory.
    IN_DONT_FOLLOW: ClassVar[Mask] = 0x02000000  # Do not follow a symbolic link.
    IN_EXCL_UNLINK: ClassVar[Mask] = 0x04000000  # Exclude events on unlinked objects
    IN_MASK_ADD: ClassVar[Mask] = 0x20000000  # Add to the mask of an existing watch.
    IN_ISDIR: ClassVar[Mask] = 0x40000000  # Event occurred against directory.
    IN_ONESHOT: ClassVar[Mask] = 0x80000000  # Only send event once.

    # All user-space events.
    IN_ALL_EVENTS: ClassVar[Mask] = reduce(
        lambda x, y: x | y,
        [
            IN_ACCESS,
            IN_MODIFY,
            IN_ATTRIB,
            IN_CLOSE_WRITE,
            IN_CLOSE_NOWRITE,
            IN_OPEN,
            IN_MOVED_FROM,
            IN_MOVED_TO,
            IN_DELETE,
            IN_CREATE,
            IN_DELETE_SELF,
            IN_MOVE_SELF,
        ],
    )

    # Flags for ``inotify_init1``
    IN_CLOEXEC: ClassVar[Mask] = 0x02000000
    IN_NONBLOCK: ClassVar[Mask] = 0x00004000


INOTIFY_ALL_CONSTANTS: dict[str, Mask] = {  # todo remove once mask uses enum.Flags.
    name: getattr(InotifyConstants, name)
    for name in dir(InotifyConstants)
    if name.startswith("IN_") and name not in {"IN_ALL_EVENTS", "IN_MOVE"}
}


# Watchdog's API cares only about these events.
WATCHDOG_ALL_EVENTS: Mask = reduce(
    lambda x, y: x | y,
    [
        InotifyConstants.IN_MODIFY,
        InotifyConstants.IN_ATTRIB,
        InotifyConstants.IN_MOVED_FROM,
        InotifyConstants.IN_MOVED_TO,
        InotifyConstants.IN_CREATE,
        InotifyConstants.IN_DELETE,
        InotifyConstants.IN_DELETE_SELF,
        InotifyConstants.IN_DONT_FOLLOW,
        InotifyConstants.IN_CLOSE_WRITE,
        InotifyConstants.IN_CLOSE_NOWRITE,
        InotifyConstants.IN_OPEN,
    ],
)


def _get_mask_string(mask: int) -> str:  # todo remove once mask uses enum.Flags.
    return "|".join(
        name for name, c_val in INOTIFY_ALL_CONSTANTS.items() if mask & c_val
    )


class InotifyEventStruct(ctypes.Structure):
    """Structure representation of the inotify_event structure
    (used in buffer size calculations)::

        struct inotify_event {
            __s32 wd;            /* watch descriptor */
            __u32 mask;          /* watch mask */
            __u32 cookie;        /* cookie to synchronize two events */
            __u32 len;           /* length (including nulls) of name */
            char  name[0];       /* stub for possible name */
        };
    """

    _fields_ = (
        ("wd", c_int),
        ("mask", c_uint32),
        ("cookie", c_uint32),
        ("len", c_uint32),
        ("name", c_char_p),
    )


EVENT_SIZE = ctypes.sizeof(InotifyEventStruct)
DEFAULT_NUM_EVENTS = 2048
DEFAULT_EVENT_BUFFER_SIZE = DEFAULT_NUM_EVENTS * (EVENT_SIZE + 16)


class WatchCallback(Protocol):
    def on_event(self, event: InotifyEvent, watch_path: bytes) -> None:
        """called for every event for each watch this callback is registered at."""
        ...

    def on_watch_deleted(self, wd: WatchDescriptor) -> None:
        """Called when a watch that ths callback is registered at is removed. This is the case when the watched object is deleted."""
        ...


@dataclass(slots=True)
class Watch:
    """Represents an inotify watch"""
    wd: WatchDescriptor
    """the inotify watch descriptor"""
    path: bytes
    """the (original) path being watched"""
    mask: Mask
    """the mask used"""
    callbacks: dict[int, WatchCallback] = field(default_factory=dict, init=False, compare=False)
    """callbacks to be called when an event for this watch is fired. dict[<some form of id>, Callback]"""

    @property
    def is_used(self) -> bool:
        return bool(self.callbacks)

    def short_str(self) -> str:
        contents = ", ".join([
            f"wd={self.wd}",
            f"path={self.path!r}",
            f"mask={_get_mask_string(self.mask)}",
        ])
        return f"<{type(self).__name__}: {contents}>"


class InotifyFD(BaseThread):
    """Linux inotify(7) API wrapper class. Allows adding and removing callbacks
    to specific inotify watches, keeps track of them and automatically calls the
    appropriate callbacks for each event.

    Watches are created and removed as needed.
    """

    # InotifyFD is a singleton for now.
    _instance: ClassVar[InotifyFD | None] = None
    _global_lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls) -> InotifyFD:
        # enforce that InotifyFD is a singleton.
        with cls._global_lock:
            if cls._instance is None:
                cls._instance = super(InotifyFD, cls).__new__(cls)
                cls._instance.__init__()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()
        if hasattr(self, "is_initialized"):
            return  # do not initialize the singleton twice.
        else:
            self.is_initialized = True

        # The file descriptor associated with the inotify instance.
        self._inotify_fd = self._create_inotify_fd()
        self._lock = threading.Lock()
        self._closed = False
        self._is_reading = True
        self._kill_r, self._kill_w = os.pipe()

        # used by _check_inotify_fd to tell if we can read _inotify_fd without blocking
        if hasattr(select, "poll"):
            self._poller = select.poll()
            self._poller.register(self._inotify_fd, select.POLLIN)
            self._poller.register(self._kill_r, select.POLLIN)
        else:
            self._poller = None

        # Stores the watch descriptor for a given path.
        self._watch_for_path: dict[bytes, Watch] = {}
        self._watch_for_wd: dict[WatchDescriptor, Watch] = {}

        self.start()

    @classmethod
    def _create_inotify_fd(cls) -> int:
        inotify_fd = inotify_init()
        if inotify_fd == -1:
            InotifyFD._raise_error()
        return inotify_fd

    @classmethod
    def get_instance(cls) -> InotifyFD:
        return InotifyFD()

    @property
    def fd(self) -> int:
        """The file descriptor associated with the inotify instance."""
        return self._inotify_fd

    def add_callback(self, path: bytes, mask: Mask, callback: WatchCallback, id_: int) -> WatchDescriptor:
        """Adds a callback for the given path to monitor events specified by the
        mask. If a watch already exists for the given path, it is reused.
        If a callback with the given id_ already exists for this watch, it is overwritten and a warning is generated.

        :param path:
            Path to begin monitoring.
        :param mask:
            Event bit mask.
        :param callback:
            Function to be called when an event for this watch is fired
        :param id_:
            Some form of id usd to identify the callback (for example to remove it later on...).
            The id must be unique only within a given watch.
        """
        with self._lock:
            return self._add_callback(path, mask, callback, id_).wd

    def remove_callback(self, wd: WatchDescriptor, id_: int) -> None:
        """Removes a callback for the given WatchDescriptor. If it was the last callback on
        the watch, the watch is removed. Otherwise, just the callback is removed
        from the watch.
        If no watch for the given WatchDescriptor exists or no callback with the given id_ for the watch exists, a
        warning is generated.

        Implementation Note:
        This does not use the path to identify a watch, because the _actual_
        path of a watch can change if the watched fil/folder is moved.

        :param wd:
            WatchDescriptor for which the callback will be removed.
        :param id_:
            Some form of id usd to identify the callback.
        """
        with self._lock:
            self._remove_callback(wd, id_)

    def on_thread_stop(self) -> None:
        self.close()

    def run(self) -> None:
        """Read events from `inotify` and handle them."""
        while self.should_keep_running():
            inotify_events = self.read_events()
            for event in inotify_events:
                self.handle_event(event)

    def close(self) -> None:
        """Closes the inotify instance and removes all associated watches."""
        with self._lock:
            if not self._closed:
                self._closed = True
                # todo notify callbacks
                for watch in self._watch_for_path.values():
                    inotify_rm_watch(self._inotify_fd, watch.wd)
                self._watch_for_wd.clear()
                self._watch_for_path.clear()

                if self._is_reading:
                    # inotify_rm_watch() should write data to _inotify_fd and wake
                    # the thread, but writing to the kill channel will guarantee this
                    os.write(self._kill_w, b"!")
                else:
                    self._close_resources()

    def handle_event(self, event: InotifyEvent):
        if event.is_ignored:
            # Clean up book-keeping for deleted watches.
            self._remove_watch(event.wd)
        else:
            watch = self._watch_for_wd[event.wd]
            for callback in watch.callbacks.values():
                callback.on_event(event, watch.path)

    def read_events(self, *, event_buffer_size: int = DEFAULT_EVENT_BUFFER_SIZE) -> list[InotifyEvent]:
        """
        Reads events from inotify and yields them.
        All appropriate exiting watches are automatically moved when a move event occurs.
        """

        event_buffer = self._read_event_buffer(event_buffer_size)
        if event_buffer is None:
            return []

        with self._lock:
            event_list = []
            for wd, mask, cookie, name in InotifyFD._parse_event_buffer(event_buffer):
                if wd == -1:
                    continue

                watch = self._watch_for_wd.get(wd)
                if watch is not None:  # watch might have been removed already
                    src_path = os.path.join(watch.path, name) if name else watch.path  # avoid trailing slash
                    event_list.append(InotifyEvent(wd, mask, cookie, name, src_path))

        return event_list

    # Non-synchronized methods.

    def _check_inotify_fd(self) -> bool:
        """return true if we can read _inotify_fd without blocking"""
        if self._poller is not None:
            return any(fd == self._inotify_fd for fd, _ in self._poller.poll())
        else:
            result = select.select([self._inotify_fd, self._kill_r], [], [])
            return self._inotify_fd in result[0]

    def _read_event_buffer(self, event_buffer_size: int) -> bytes | None:
        """
        Reads from inotify and returns what was read.
        If inotify got closed or if an errno.EBADF occurred during reading, None is returned.
        """
        event_buffer = b""
        while True:
            try:
                with self._lock:
                    if self._closed:
                        return None

                    self._is_reading = True

                if self._check_inotify_fd():
                    event_buffer = os.read(self._inotify_fd, event_buffer_size)

                with self._lock:
                    self._is_reading = False

                    if self._closed:
                        self._close_resources()
                        return None
            except OSError as e:
                if e.errno == errno.EINTR:
                    continue

                if e.errno == errno.EBADF:
                    return None

                raise
            break
        return event_buffer

    def _close_resources(self) -> None:
        os.close(self._inotify_fd)
        os.close(self._kill_r)
        os.close(self._kill_w)

    def _add_callback(self, path: bytes, mask: Mask, callback: WatchCallback, id_: int) -> Watch:
        """Adds a callback for the given path to monitor events specified by the
        mask. If a watch already exists for the given path, it is reused.
        If a callback with the given id_ already exists for this watch, it is overwritten and a warning is generated.

        :param path:
            Path to begin monitoring.
        :param mask:
            Event bit mask.
        :param callback:
            Function to be called when an event for this watch is fired
        :param id_:
            Some form of id usd to identify the callback (for example to remove it later on...).
            The id must be unique only within a given watch.
        """
        watch = self._watch_for_path.get(path)
        if watch is None:
            watch = self._create_watch(path, mask)

        if id_ in watch.callbacks:
            warnings.warn(f"Callback with id '{id_}' already exists for watch {watch.short_str}. It will be Overwritten.", RuntimeWarning, 3)
        watch.callbacks[id_] = callback

        return watch

    def _create_watch(self, path: bytes, mask: Mask) -> Watch:
        """Creates a watch for the given path to monitor events specified by the
        mask.

        :param path:
            Path to monitor
        :param mask:
            Event bit mask.
        """
        wd = inotify_add_watch(self._inotify_fd, path, mask)
        if wd == -1:
            InotifyFD._raise_error()
        watch = Watch(wd, path, mask)
        self._watch_for_wd[wd] = watch
        self._watch_for_path[path] = watch
        return watch

    def _remove_callback(self, wd: WatchDescriptor, id_: int) -> None:
        """Removes a callback for the given WatchDescriptor. If it was the last callback on
        the watch, the watch is removed. Otherwise, just the callback is removed
        from the watch.
        If no watch for the given WatchDescriptor exists or no callback with the given id_ for the watch exists, a
        warning is generated.

        :param wd:
            WatchDescriptor for which the callback will be removed.
        :param id_:
            Some form of id usd to identify the callback.
        """
        watch = self._watch_for_wd.get(wd)
        if watch is None:
            warnings.warn(f"Trying to remove callback from a watch that does not exist. WatchDescriptor: {wd}, callback id: '{id_}'.", RuntimeWarning, 3)
            return

        if watch.callbacks.pop(id_, None) is None:
            warnings.warn(f"Callback with id '{id_}' does not exist for watch {watch.short_str} and therefore cannot be removed.", RuntimeWarning, 3)

        if not watch.is_used:
            self._remove_watch(watch.wd)
            if inotify_rm_watch(self._inotify_fd, watch.wd) == -1:
                InotifyFD._raise_error()

    def _remove_watch(self, wd: WatchDescriptor):
        """Notifies all necessary objects of deleted watches and cleans up book-keeping.
        This does NOT call inotify_rm_watch."""
        watch = self._watch_for_wd.pop(wd)
        if self._watch_for_path[watch.path].wd == wd:  # why the extra check only here?
            del self._watch_for_path[watch.path]
            for callback in watch.callbacks.values():
                callback.on_watch_deleted(watch.wd)

    @staticmethod
    def _raise_error() -> None:
        """Raises errors for inotify failures."""
        err = ctypes.get_errno()

        if err == errno.ENOSPC:
            raise OSError(errno.ENOSPC, "inotify watch limit reached")

        if err == errno.EMFILE:
            raise OSError(errno.EMFILE, "inotify instance limit reached")

        if err != errno.EACCES:
            raise OSError(err, os.strerror(err))

    @staticmethod
    def _parse_event_buffer(event_buffer: bytes) -> Generator[tuple[WatchDescriptor, Mask, int, bytes]]:
        """Parses an event buffer of ``inotify_event`` structs returned by
        inotify::

            struct inotify_event {
                __s32 wd;            /* watch descriptor */
                __u32 mask;          /* watch mask */
                __u32 cookie;        /* cookie to synchronize two events */
                __u32 len;           /* length (including nulls) of name */
                char  name[0];       /* stub for possible name */
            };

        The ``cookie`` member of this struct is used to pair two related
        events, for example, it pairs an IN_MOVED_FROM event with an
        IN_MOVED_TO event.
        """
        i = 0
        while i + 16 <= len(event_buffer):
            wd, mask, cookie, length = struct.unpack_from("iIII", event_buffer, i)
            name = event_buffer[i + 16: i + 16 + length].rstrip(b"\0")
            i += 16 + length
            yield wd, mask, cookie, name


# creates global InotifyFD instance NOW, (only necessary for unit tests) todo find better solution
InotifyFD.get_instance()


class InotifyEvent:
    """Inotify event struct wrapper.

    :param wd:
        Watch descriptor
    :param mask:
        Event mask
    :param cookie:
        Event cookie
    :param name:
        Base name of the event source path.
    :param src_path:
        Full event source path.
    """

    def __init__(self, wd: int, mask: int, cookie: int, name: bytes, src_path: bytes) -> None:
        self._wd = wd
        self._mask = mask
        self._cookie = cookie
        self._name = name
        self._src_path = src_path

    @property
    def src_path(self) -> bytes:
        return self._src_path

    @property
    def wd(self) -> int:
        return self._wd

    @property
    def mask(self) -> int:
        return self._mask

    @property
    def cookie(self) -> int:
        return self._cookie

    @property
    def name(self) -> bytes:
        return self._name

    @property
    def is_modify(self) -> bool:
        return self._mask & InotifyConstants.IN_MODIFY > 0

    @property
    def is_close_write(self) -> bool:
        return self._mask & InotifyConstants.IN_CLOSE_WRITE > 0

    @property
    def is_close_nowrite(self) -> bool:
        return self._mask & InotifyConstants.IN_CLOSE_NOWRITE > 0

    @property
    def is_open(self) -> bool:
        return self._mask & InotifyConstants.IN_OPEN > 0

    @property
    def is_access(self) -> bool:
        return self._mask & InotifyConstants.IN_ACCESS > 0

    @property
    def is_delete(self) -> bool:
        return self._mask & InotifyConstants.IN_DELETE > 0

    @property
    def is_delete_self(self) -> bool:
        return self._mask & InotifyConstants.IN_DELETE_SELF > 0

    @property
    def is_create(self) -> bool:
        return self._mask & InotifyConstants.IN_CREATE > 0

    @property
    def is_moved_from(self) -> bool:
        return self._mask & InotifyConstants.IN_MOVED_FROM > 0

    @property
    def is_moved_to(self) -> bool:
        return self._mask & InotifyConstants.IN_MOVED_TO > 0

    @property
    def is_move(self) -> bool:
        return self._mask & InotifyConstants.IN_MOVE > 0

    @property
    def is_move_self(self) -> bool:
        return self._mask & InotifyConstants.IN_MOVE_SELF > 0

    @property
    def is_attrib(self) -> bool:
        return self._mask & InotifyConstants.IN_ATTRIB > 0

    @property
    def is_ignored(self) -> bool:
        return self._mask & InotifyConstants.IN_IGNORED > 0

    @property
    def is_directory(self) -> bool:
        # It looks like the kernel does not provide this information for
        # IN_DELETE_SELF and IN_MOVE_SELF. In this case, assume it's a dir.
        # See also: https://github.com/seb-m/pyinotify/blob/2c7e8f8/python2/pyinotify.py#L897
        return self.is_delete_self or self.is_move_self or self._mask & InotifyConstants.IN_ISDIR > 0

    @property
    def key(self) -> tuple[bytes, int, int, int, bytes]:
        return self._src_path, self._wd, self._mask, self._cookie, self._name

    def __eq__(self, inotify_event: object) -> bool:
        if not isinstance(inotify_event, InotifyEvent):
            return NotImplemented
        return self.key == inotify_event.key

    def __ne__(self, inotify_event: object) -> bool:
        if not isinstance(inotify_event, InotifyEvent):
            return NotImplemented
        return self.key != inotify_event.key

    def __hash__(self) -> int:
        return hash(self.key)

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__}: src_path={self.src_path!r}, wd={self.wd},"
            f" mask={_get_mask_string(self.mask)}, cookie={self.cookie},"
            f" name={os.fsdecode(self.name)!r}>"
        )
