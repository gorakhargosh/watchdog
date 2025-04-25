from __future__ import annotations

import ctypes
import ctypes.util
import errno
import logging
import os
import select
import struct
import threading
import warnings
from ctypes import c_char_p, c_int, c_uint32
from dataclasses import dataclass, field
from functools import reduce
from typing import TYPE_CHECKING, Callable, ClassVar, NewType, Protocol, cast

from watchdog.utils import BaseThread, UnsupportedLibcError

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

logger = logging.getLogger(__name__)

libc = ctypes.CDLL(None)

if not hasattr(libc, "inotify_init") or not hasattr(libc, "inotify_add_watch") or not hasattr(libc, "inotify_rm_watch"):
    error = f"Unsupported libc version found: {libc._name}"  # noqa:SLF001
    raise UnsupportedLibcError(error)


WatchDescriptor = NewType("WatchDescriptor", int)
Mask = NewType("Mask", int)

inotify_add_watch = cast(
    Callable[[int, bytes, int], WatchDescriptor],
    ctypes.CFUNCTYPE(c_int, c_int, c_char_p, c_uint32, use_errno=True)(("inotify_add_watch", libc)),
)

inotify_rm_watch = cast(
    Callable[[int, WatchDescriptor], int],
    ctypes.CFUNCTYPE(c_int, c_int, c_uint32, use_errno=True)(("inotify_rm_watch", libc)),
)

inotify_init = cast(Callable[[], int], ctypes.CFUNCTYPE(c_int, use_errno=True)(("inotify_init", libc)))


class InotifyConstants:
    # User-space events
    IN_ACCESS: ClassVar[Mask] = Mask(0x00000001)  # File was accessed.
    IN_MODIFY: ClassVar[Mask] = Mask(0x00000002)  # File was modified.
    IN_ATTRIB: ClassVar[Mask] = Mask(0x00000004)  # Meta-data changed.
    IN_CLOSE_WRITE: ClassVar[Mask] = Mask(0x00000008)  # Writable file was closed.
    IN_CLOSE_NOWRITE: ClassVar[Mask] = Mask(0x00000010)  # Unwritable file closed.
    IN_OPEN: ClassVar[Mask] = Mask(0x00000020)  # File was opened.
    IN_MOVED_FROM: ClassVar[Mask] = Mask(0x00000040)  # File was moved from X.
    IN_MOVED_TO: ClassVar[Mask] = Mask(0x00000080)  # File was moved to Y.
    IN_CREATE: ClassVar[Mask] = Mask(0x00000100)  # Subfile was created.
    IN_DELETE: ClassVar[Mask] = Mask(0x00000200)  # Subfile was deleted.
    IN_DELETE_SELF: ClassVar[Mask] = Mask(0x00000400)  # Self was deleted.
    IN_MOVE_SELF: ClassVar[Mask] = Mask(0x00000800)  # Self was moved.

    # Helper user-space events.
    IN_MOVE: ClassVar[Mask] = Mask(IN_MOVED_FROM | IN_MOVED_TO)  # Moves.

    # Events sent by the kernel to a watch.
    IN_UNMOUNT: ClassVar[Mask] = Mask(0x00002000)  # Backing file system was unmounted.
    IN_Q_OVERFLOW: ClassVar[Mask] = Mask(0x00004000)  # Event queued overflowed.
    IN_IGNORED: ClassVar[Mask] = Mask(0x00008000)  # File was ignored.

    # Special flags.
    IN_ONLYDIR: ClassVar[Mask] = Mask(0x01000000)  # Only watch the path if it's a directory.
    IN_DONT_FOLLOW: ClassVar[Mask] = Mask(0x02000000)  # Do not follow a symbolic link.
    IN_EXCL_UNLINK: ClassVar[Mask] = Mask(0x04000000)  # Exclude events on unlinked objects
    IN_MASK_ADD: ClassVar[Mask] = Mask(0x20000000)  # Add to the mask of an existing watch.
    IN_ISDIR: ClassVar[Mask] = Mask(0x40000000)  # Event occurred against directory.
    IN_ONESHOT: ClassVar[Mask] = Mask(0x80000000)  # Only send event once.

    # All user-space events.
    IN_ALL_EVENTS: ClassVar[Mask] = reduce(
        lambda x, y: Mask(x | y),
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
    IN_CLOEXEC: ClassVar[Mask] = Mask(0x02000000)
    IN_NONBLOCK: ClassVar[Mask] = Mask(0x00004000)


INOTIFY_ALL_CONSTANTS: dict[str, Mask] = {
    name: getattr(InotifyConstants, name)
    for name in dir(InotifyConstants)
    if name.startswith("IN_") and name not in {"IN_ALL_EVENTS", "IN_MOVE"}
}


# Watchdog's API cares only about these events.
WATCHDOG_ALL_EVENTS: Mask = reduce(
    lambda x, y: Mask(x | y),
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


def _get_mask_string(mask: int) -> str:
    return "|".join(name for name, c_val in INOTIFY_ALL_CONSTANTS.items() if mask & c_val)


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


CallbackId = NewType("CallbackId", int)


class WatchCallback(Protocol):
    def on_event(self, event: InotifyEvent) -> None:
        """called for every event for each watch this callback is registered at."""
        ...

    def on_watch_deleted(self, wd: WatchDescriptor) -> None:
        """Called when a watch that ths callback is registered at is removed.
        This is the case when the watched object is deleted."""
        ...


@dataclass
class Watch:
    """Represents an inotify watch"""

    wd: WatchDescriptor
    """the inotify watch descriptor"""
    mask: Mask
    """the mask used"""
    _initial_creation_path: bytes
    """the original(!) path being watched.
    .. NOTE:: Do **NOT** use when creating or interpreting events, finding watches
    or similar. This is purely meant to help debugging.

    If a watched file/folder gets moved and we create a new watch for the
    file/folder at the new path, inotify will give us the same watch descriptor,
    which is still remembered undr the old path.
    """
    callbacks: dict[CallbackId, WatchCallback] = field(default_factory=dict, init=False, compare=False)
    """callbacks to be called when an event for this watch is fired. dict[<some form of id>, Callback]"""

    @property
    def is_used(self) -> bool:
        return bool(self.callbacks)

    def short_str(self) -> str:
        contents = ", ".join(
            [
                f"wd={self.wd}",
                f"mask={_get_mask_string(self.mask)}",
                f"_initial_creation_path={self._initial_creation_path!r}",
            ]
        )
        return f"<{type(self).__name__}: {contents}>"


class InotifyFD(BaseThread):
    """Linux inotify(7) API wrapper class.
    Allows adding and removing callbacks to specific inotify watches, keeps
    track of them, and automatically calls the appropriate callbacks for each
    event.

    Watches are created and removed as needed.
    """

    # InotifyFD is a singleton for now.
    _instance: ClassVar[InotifyFD | None] = None
    _global_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        super().__init__()
        if hasattr(self, "is_initialized"):
            return  # do not initialize the singleton twice.
        self.is_initialized = True

        # The file descriptor associated with the inotify instance.
        self._inotify_fd: int = self._create_inotify_fd()

        self._lock = threading.Lock()
        self._closed = False
        self._is_reading = True
        self._kill_r, self._kill_w = os.pipe()

        # used by _check_inotify_fd to tell if we can read _inotify_fd without blocking
        if hasattr(select, "poll"):
            self._poller: select.poll | None = select.poll()
            self._poller.register(self._inotify_fd, select.POLLIN)
            self._poller.register(self._kill_r, select.POLLIN)
        else:
            self._poller = None

        # Stores the callbacks for a given watch descriptor.
        self._watch_for_wd: dict[WatchDescriptor, Watch] = {}

    @classmethod
    def _create_inotify_fd(cls) -> int:
        inotify_fd = inotify_init()
        if inotify_fd == -1:
            InotifyFD._raise_error()
        return inotify_fd

    @classmethod
    def get_instance(cls) -> InotifyFD:
        """Use this class method to get a running InotifyFD instance."""
        with cls._global_lock:
            # enforce that InotifyFD is a singleton.
            if cls._instance is None:
                cls._instance = InotifyFD()
                cls._instance.start()
            return cls._instance

    def add_callback(self, path: bytes, mask: Mask, callback: WatchCallback, id_: CallbackId) -> WatchDescriptor:
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
            return self._add_callback(path, mask, callback, id_)

    def remove_callbacks(self, callbacks: list[tuple[WatchDescriptor, CallbackId]]) -> None:
        """Removes callbacks from WatchDescriptors. If a callback was the last
        callback on a watch, the watch is removed. Otherwise, just the callback
        is removed from the watch.

        If no watch for a given WatchDescriptor exists or no callback with the
        given id_ for the watch exists, a warning is generated.

        Implementation Note:
        This does not use the path to identify a watch, because the _actual_
        path of a watch can change if the watched file/folder is moved.

        :param callbacks:
            a list of (WatchDescriptor, callback id)-tuples for each of which
            the callback will be removed from the WatchDescriptor.
        """
        with self._lock:
            for wd, id_ in callbacks:
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
        delete_callbacks = []
        with self._lock:
            if not self._closed:
                self._closed = True
                for wd in self._watch_for_wd.copy():
                    inotify_rm_watch(self._inotify_fd, wd)
                    delete_callbacks.append((wd, self._remove_watch(wd)))
                self._watch_for_wd.clear()

                if self._is_reading:
                    # inotify_rm_watch() should write data to _inotify_fd and wake
                    # the thread, but writing to the kill channel will guarantee this
                    os.write(self._kill_w, b"!")
                else:
                    self._close_resources()

        # execute callbacks outside of lock, as they might attempt to register / unregister watches:
        for wd, callbacks in delete_callbacks:
            for callback in callbacks:
                callback.on_watch_deleted(wd)

    def handle_event(self, event: InotifyEvent) -> None:
        with self._lock:
            if event.is_ignored:
                # Clean up book-keeping for deleted watches.
                delete_callbacks: Sequence[WatchCallback] = self._remove_watch(event.wd)
                callbacks: Sequence[WatchCallback] = ()
            else:
                delete_callbacks = ()
                watch = self._watch_for_wd.get(event.wd)

                # watch might have been removed already. Also copy, because
                # watch.callbacks might change during later iteration
                callbacks = list(watch.callbacks.values()) if watch is not None else ()

        # execute callbacks outside of lock, as they might need to register / unregister watches:
        for callback in callbacks:
            callback.on_event(event)
        for callback in delete_callbacks:
            callback.on_watch_deleted(event.wd)

    def read_events(self, *, event_buffer_size: int = DEFAULT_EVENT_BUFFER_SIZE) -> list[InotifyEvent]:
        """
        Reads events from inotify and yields them.
        All appropriate exiting watches are automatically moved when a move event occurs.
        """
        event_buffer = self._read_event_buffer(event_buffer_size)
        return [
            InotifyEvent(wd, mask, cookie, name)
            for wd, mask, cookie, name in InotifyFD._parse_event_buffer(event_buffer)
            if wd != -1
        ]

    # Non-synchronized methods.

    def _check_inotify_fd(self) -> bool:
        """return true if we can read _inotify_fd without blocking"""
        if self._poller is not None:
            return any(fd == self._inotify_fd for fd, _ in self._poller.poll())

        result = select.select([self._inotify_fd, self._kill_r], [], [])
        return self._inotify_fd in result[0]

    def _read_event_buffer(self, event_buffer_size: int) -> bytes:
        """
        Reads from inotify and returns what was read.
        If inotify got closed or if an errno.EBADF occurred during reading, None is returned.
        """
        event_buffer = b""
        while True:
            try:
                with self._lock:
                    if self._closed:
                        return b""

                    self._is_reading = True

                if self._check_inotify_fd():
                    event_buffer = os.read(self._inotify_fd, event_buffer_size)

                with self._lock:
                    self._is_reading = False

                    if self._closed:
                        self._close_resources()
                        return b""
            except OSError as e:
                if e.errno == errno.EINTR:
                    continue

                if e.errno == errno.EBADF:
                    return b""

                raise
            break
        return event_buffer

    def _close_resources(self) -> None:
        os.close(self._inotify_fd)
        os.close(self._kill_r)
        os.close(self._kill_w)

    def _add_callback(self, path: bytes, mask: Mask, callback: WatchCallback, id_: CallbackId) -> WatchDescriptor:
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
        watch = self._get_or_create_watch(path, mask)

        if id_ in watch.callbacks:
            msg = f"Callback with id '{id_}' already exists for watch {watch.short_str}. It will be Overwritten."
            warnings.warn(msg, RuntimeWarning, stacklevel=3)
        watch.callbacks[id_] = callback
        return watch.wd

    def _get_or_create_watch(self, path: bytes, mask: Mask) -> Watch:
        """Creates a watch for the given path to monitor events specified by the
        mask.

        :param path:
            Path to monitor
        :param mask:
            Event bit mask.
        """
        # returns an existing watch descriptor, if one already exists for path:
        wd = inotify_add_watch(self._inotify_fd, path, mask)
        if wd == -1:
            InotifyFD._raise_error()
        watch = self._watch_for_wd.get(wd)
        if watch is None:
            watch = Watch(wd, mask, path)
            self._watch_for_wd[wd] = watch
        return watch

    def _remove_callback(self, wd: WatchDescriptor, id_: CallbackId) -> None:
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
            msg = "Trying to remove callback from a watch that does not exist. WatchDescriptor: %s, callback id: '%s'."
            logger.debug(msg, wd, id_)
            return

        if watch.callbacks.pop(id_, None) is None:
            msg = f"Callback with id '{id_}' does not exist for watch {watch.short_str} and therefore cannot be removed"
            warnings.warn(msg, RuntimeWarning, stacklevel=3)

        if not watch.is_used:
            delete_callbacks = self._remove_watch(watch.wd)
            if inotify_rm_watch(self._inotify_fd, watch.wd) == -1:
                InotifyFD._raise_error(ignore_invalid_argument=True)  # ignore if a watch doesn't exist anymore
            assert not delete_callbacks, f"delete_callbacks should be empty, but was: {delete_callbacks}"

    def _remove_watch(self, wd: WatchDescriptor) -> Sequence[WatchCallback]:
        """Notifies all necessary objects of deleted watches and cleans up book-keeping.
        This does NOT call inotify_rm_watch."""
        watch = self._watch_for_wd.pop(wd, None)
        return list(watch.callbacks.values()) if watch is not None else []

    @staticmethod
    def _raise_error(*, ignore_invalid_argument: bool = False) -> None:
        """Raises errors for inotify failures."""
        err = ctypes.get_errno()

        if err == errno.ENOSPC:
            raise OSError(errno.ENOSPC, "inotify watch limit reached")

        if err == errno.EMFILE:
            raise OSError(errno.EMFILE, "inotify instance limit reached")

        if ignore_invalid_argument and err == errno.EINVAL:
            return  # ignore

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
            name = event_buffer[i + 16 : i + 16 + length].rstrip(b"\0")
            i += 16 + length
            yield wd, mask, cookie, name


# creates global InotifyFD instance NOW, (only necessary for unit tests) todo find better solution
InotifyFD.get_instance()


@dataclass(unsafe_hash=True, frozen=True)
class InotifyEvent:
    """Inotify event struct wrapper."""

    wd: WatchDescriptor
    """Watch descriptor"""
    mask: Mask
    """Event mask"""
    cookie: int
    """Event cookie"""
    name: bytes
    """Base name of the event source path. might be empty"""
    # src_path: bytes; We cannot set the src_path.
    # See 'Challenges With inotify' section in the description of inotify.py

    @property
    def is_modify(self) -> bool:
        return self.mask & InotifyConstants.IN_MODIFY > 0

    @property
    def is_close_write(self) -> bool:
        return self.mask & InotifyConstants.IN_CLOSE_WRITE > 0

    @property
    def is_close_nowrite(self) -> bool:
        return self.mask & InotifyConstants.IN_CLOSE_NOWRITE > 0

    @property
    def is_open(self) -> bool:
        return self.mask & InotifyConstants.IN_OPEN > 0

    @property
    def is_access(self) -> bool:
        return self.mask & InotifyConstants.IN_ACCESS > 0

    @property
    def is_delete(self) -> bool:
        return self.mask & InotifyConstants.IN_DELETE > 0

    @property
    def is_delete_self(self) -> bool:
        return self.mask & InotifyConstants.IN_DELETE_SELF > 0

    @property
    def is_create(self) -> bool:
        return self.mask & InotifyConstants.IN_CREATE > 0

    @property
    def is_moved_from(self) -> bool:
        return self.mask & InotifyConstants.IN_MOVED_FROM > 0

    @property
    def is_moved_to(self) -> bool:
        return self.mask & InotifyConstants.IN_MOVED_TO > 0

    @property
    def is_move(self) -> bool:
        return self.mask & InotifyConstants.IN_MOVE > 0

    @property
    def is_move_self(self) -> bool:
        return self.mask & InotifyConstants.IN_MOVE_SELF > 0

    @property
    def is_attrib(self) -> bool:
        return self.mask & InotifyConstants.IN_ATTRIB > 0

    @property
    def is_ignored(self) -> bool:
        return self.mask & InotifyConstants.IN_IGNORED > 0

    @property
    def is_directory(self) -> bool:
        # It looks like the kernel does not provide this information for
        # IN_DELETE_SELF and IN_MOVE_SELF. In this case, assume it's a dir.
        # See also: https://github.com/seb-m/pyinotify/blob/2c7e8f8/python2/pyinotify.py#L897
        return self.is_delete_self or self.is_move_self or self.mask & InotifyConstants.IN_ISDIR > 0

    def __repr__(self) -> str:
        contents = ", ".join(
            [
                f"wd={self.wd}",
                f"mask={_get_mask_string(self.mask)}",
                f"cookie={self.cookie}",
                f"name={os.fsdecode(self.name)!r}",
            ]
        )
        return f"<{type(self).__name__}: {contents}>"
