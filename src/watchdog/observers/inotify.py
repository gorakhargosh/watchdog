""":module: watchdog.observers.inotify
:synopsis: ``inotify(7)`` based emitter implementation.
:author: Sebastien Martini <seb@dbzteam.org>
:author: Luke McCarthy <luke@iogopro.co.uk>
:author: yesudeep@google.com (Yesudeep Mangalapilly)
:author: Tim Cuthbertson <tim+github@gfxmonk.net>
:author: Mickaël Schoentgen <contact@tiger-222.fr>
:author: Joachim Coenen <joachimcoenen@icloud.com>
:platforms: Linux 2.6.13+.

.. ADMONITION:: About system requirements

    Recommended minimum kernel version: 2.6.25.

    Quote from the inotify(7) man page:

        "Inotify was merged into the 2.6.13 Linux kernel. The required library
        interfaces were added to glibc in version 2.4. (IN_DONT_FOLLOW,
        IN_MASK_ADD, and IN_ONLYDIR were only added in version 2.5.)"

    Therefore, you must ensure the system is running at least these versions
    appropriate libraries and the kernel.

.. ADMONITION:: About recursiveness, event order, and event coalescing

    Quote from the inotify(7) man page:

        If successive output inotify events produced on the inotify file
        descriptor are identical (same wd, mask, cookie, and name) then they
        are coalesced into a single event if the older event has not yet been
        read (but see BUGS).

        The events returned by reading from an inotify file descriptor form
        an ordered queue. Thus, for example, it is guaranteed that when
        renaming from one directory to another, events will be produced in
        the correct order on the inotify file descriptor.

        ...

        Inotify monitoring of directories is not recursive: to monitor
        subdirectories under a directory, additional watches must be created.

    This emitter implementation therefore automatically adds watches for
    sub-directories if running in recursive mode.

.. ADMONITION:: Challenges with the inotify API:
    inotify has some limitations:

    - A watch on a file/folder is not informed when the file/folder itself or any containing (outer) folders  is moved.
    - When a file is moved from a watched directory to a different directory, there will only be an IN_MOVE_FROM event
      for the watch on that directory.
    - When a file is moved from an unwatched directory to a watched directory, there will only be an IN_MOVE_TO event
      for the watch on that directory.

    If we were to keep track of the path of watches in InotifyFD, an
    InotifyWatchGroup would get different events depending on whether there are
    other InotifyWatchGroups for exactly the right set of paths or not. The same
    goes for coalescing move events.

    Therefore, both things are handled by the InotifyWatchGroups themselves.

Some extremely useful articles and documentation:

.. _inotify FAQ: http://inotify.aiken.cz/?section=inotify&page=faq&lang=en
.. _intro to inotify: http://www.linuxjournal.com/article/8478

"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, cast

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
    FileSystemEvent,
    generate_sub_created_events,
    generate_sub_moved_events,
)
from watchdog.observers.api import DEFAULT_EMITTER_TIMEOUT, DEFAULT_OBSERVER_TIMEOUT, BaseObserver, EventEmitter
from watchdog.observers.inotify_c import (
    WATCHDOG_ALL_EVENTS,
    CallbackId,
    InotifyConstants,
    InotifyEvent,
    InotifyFD,
    Mask,
    WatchCallback,
    WatchDescriptor,
)
from watchdog.observers.inotify_move_event_grouper import (
    GroupedInotifyEvent,
    InotifyMoveEventGrouper,
    PathedInotifyEvent,
)

if TYPE_CHECKING:
    from watchdog.observers.api import EventQueue, ObservedWatch

logger = logging.getLogger(__name__)


class FileSystemEventCtor(Protocol):
    def __call__(self, src_path: bytes | str, dest_path: bytes | str = "") -> FileSystemEvent: ...


@dataclass
class InotifyWatchGroup(WatchCallback):
    """Linux inotify(7) API wrapper class.

    Bundles everything needed to watch a file or (possibly recursive) directory.
    Manages the watches needed and coalesces IN_MOVE_FROM and IN_MOVE_TO events.

    In order to preserve consistency the behavior of one InotifyWatchGroup must
    be independent of the existence of any other InotifyWatchGroup.
    Therefore, an InotifyWatchGroup is itself responsible for:

    - keeping track of the actual path a watch watches (including tracking moves, if possible)
    - coalescing move events.

    :param path:
        The directory path for which we want an inotify object.
    :type path:
        :class:`bytes`
    :param is_recursive:
        ``True`` if subdirectories should be monitored; ``False`` otherwise.
    """

    _inotify_fd: InotifyFD
    """The inotify instance to use"""
    path: bytes
    """Whether we are watching directories recursively."""
    event_mask: Mask = field(default=Mask(0))
    """The path associated with the inotify instance."""
    is_recursive: bool = False
    """The event mask for this inotify instance."""
    follow_symlink: bool = False

    _move_event_grouper: InotifyMoveEventGrouper = field(default_factory=InotifyMoveEventGrouper, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _id: CallbackId = field(init=False)

    _is_active: bool = field(default=False, init=False)

    _active_callbacks_by_watch: dict[WatchDescriptor, bytes] = field(default_factory=dict, init=False)
    _active_callbacks_by_path: dict[bytes, WatchDescriptor] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.event_mask = InotifyWatchGroup.build_event_mask(self.event_mask, follow_symlink=self.follow_symlink)
        self._id = CallbackId(id(self))
        self._activate()

    @staticmethod
    def build_event_mask(event_mask: Mask, *, follow_symlink: bool) -> Mask:
        if follow_symlink:
            event_mask = Mask(event_mask & ~InotifyConstants.IN_DONT_FOLLOW)
        else:
            event_mask = Mask(event_mask | InotifyConstants.IN_DONT_FOLLOW)
        return event_mask

    @property
    def is_active(self) -> bool:
        """Returns True if there are any callbacks active"""
        return self._is_active

    def _source_for_move(self, cookie: int) -> bytes | None:
        """The source path corresponding to the given MOVED_TO event.

        If the source path is outside the monitored directories, None
        is returned instead.
        """
        src_event = self._move_event_grouper.get_queued_moved_from_event(cookie)
        if src_event is not None:
            return src_event.path
        return None

    @property
    def _callback(self) -> WatchCallback:
        return self

    def read_event(self) -> GroupedInotifyEvent | None:
        """Returns a single event or a tuple of from/to events in case of a
        paired move event. If this buffer has been closed, raise the Closed
        exception.
        """
        return self._move_event_grouper.read_event()

    def on_watch_deleted(self, wd: WatchDescriptor) -> None:
        """Called when a watch that ths callback is registered at is removed.
        This is the case when the watched object is deleted."""
        with self._lock:
            if not self.is_active:
                return
            self._remove_watch_internally(wd)

    def on_event(self, event: InotifyEvent) -> None:
        """called for every event for each watch this callback is registered at."""
        with self._lock:
            if not self.is_active:
                return
            src_path = self._build_event_source_path(event)
            if src_path is None:
                return

            # todo look into desired behavior for IN_MOVE_SELF events
            #  (keep watching?, stop watching?, are they even possible?)
            if event.is_moved_from:
                # TODO: When a directory from a watched directory
                #  is moved into another part of the filesystem, this
                #  will not generate DELETE events for the directory tree.
                #  We need to coalesce IN_MOVED_FROM events and those
                #  IN_MOVED_FROM events which don't pair up with
                #  IN_MOVED_TO events should be marked IN_DELETE (maybe?)
                #  instead relative to this directory. And the respective
                #  callbacks for the directory and sub directory must be removed.
                #
                #  also: hold back all other events for this directory and its
                #  subdirectories, until we know whether it is still watched
                pass
            elif event.is_moved_to:
                move_src_path = self._source_for_move(event.cookie)
                move_dst_path = src_path
                if move_src_path is not None:
                    self._move_watches(move_src_path, move_dst_path)
                # TODO: When a directory from another part of the
                #  filesystem is moved into a watched directory, this
                #  will not generate events for the directory tree.
                #  We need to coalesce IN_MOVED_TO events and those
                #  IN_MOVED_TO events which don't pair up with
                #  IN_MOVED_FROM events should be marked IN_CREATE
                #  instead relative to this directory.
            elif event.is_create and event.is_directory and self.is_recursive:
                self._add_all_callbacks(src_path)

            self._move_event_grouper.put_event(PathedInotifyEvent(event, src_path))

            if event.is_create and event.is_directory and self.is_recursive:
                for sub_event in self._recursive_simulate(src_path):
                    sub_src_path = self._build_event_source_path(sub_event)
                    if sub_src_path is not None:
                        self._move_event_grouper.put_event(PathedInotifyEvent(sub_event, sub_src_path))

    def _recursive_simulate(self, src_path: bytes) -> list[InotifyEvent]:
        # HACK: We need to traverse the directory path recursively and simulate
        # events for newly  created subdirectories/files.
        # This will handle: mkdir -p foobar/blah/bar; touch foobar/afile
        events = []
        for root, dirnames, filenames in os.walk(src_path, followlinks=self.follow_symlink):
            for dirname in dirnames:
                full_path = os.path.join(root, dirname)
                wd_dir = self._active_callbacks_by_path[os.path.dirname(full_path)]
                mask = Mask(InotifyConstants.IN_CREATE | InotifyConstants.IN_ISDIR)
                events.append(InotifyEvent(wd_dir, mask, 0, dirname))

            for filename in filenames:
                full_path = os.path.join(root, filename)
                wd_parent_dir = self._active_callbacks_by_path[os.path.dirname(full_path)]
                mask = InotifyConstants.IN_CREATE
                events.append(InotifyEvent(wd_parent_dir, mask, 0, filename))
        return events

    def deactivate(self) -> None:
        """Removes all associated watches."""
        with self._lock:
            self._is_active = False
            self._remove_callbacks(list(self._active_callbacks_by_watch))
            self._move_event_grouper.close()

    def _activate(self) -> None:
        """Adds a watch (optionally recursively) for the given directory path
        to monitor events specified by the mask.
        """
        with self._lock:
            if self.is_active:  # maybe wwe can remove this check...
                return

            self._add_all_callbacks(self.path)
            self._is_active = True

    # Non-synchronized methods:

    def _build_event_source_path(self, event: InotifyEvent) -> bytes | None:
        watched_path = self._active_callbacks_by_watch.get(event.wd)
        if watched_path is None:
            # investigate: can we *actually* get events for a WatchDescriptor that has already been removed?
            return None
        return os.path.join(watched_path, event.name) if event.name else watched_path  # avoid trailing slash

    def _move_watches(self, move_src_path: bytes, move_dst_path: bytes) -> None:
        """moves all watches that are inside the directory move_src_path to move_dst_path"""
        moved_watch = self._active_callbacks_by_path.pop(move_src_path, None)
        if moved_watch is not None:
            self._active_callbacks_by_watch[moved_watch] = move_dst_path
            self._active_callbacks_by_path[move_dst_path] = moved_watch

            # move all watches within this directory
            move_src_prefix = move_src_path + os.path.sep.encode()
            for path, wd in self._active_callbacks_by_path.copy().items():
                if path.startswith(move_src_prefix):
                    del self._active_callbacks_by_path[path]
                    path = path.replace(move_src_path, move_dst_path, 1)
                    self._active_callbacks_by_watch[wd] = path
                    self._active_callbacks_by_path[path] = wd

    def _add_all_callbacks(self, path: bytes) -> None:
        """Adds a watch (optionally recursively) for the given directory path
        to monitor events specified by the mask.

        :param path:
            Path to monitor
        """
        is_dir = os.path.isdir(path)
        self._add_callback(path)
        if is_dir and self.is_recursive:
            for root, dirnames, _ in os.walk(path, followlinks=self.follow_symlink):
                for dirname in dirnames:
                    full_path = os.path.join(root, dirname)
                    if not self.follow_symlink and os.path.islink(full_path):
                        continue
                    self._add_callback(full_path)

    def _add_callback(self, path: bytes) -> None:
        """Adds a callback for the given path to monitor events specified by the
        mask.

        :param path:
            Path to monitor
        """
        with contextlib.suppress(OSError):
            wd = self._inotify_fd.add_callback(path, self.event_mask, self._callback, self._id)
            self._active_callbacks_by_path[path] = wd
            self._active_callbacks_by_watch[wd] = path

    def _remove_callbacks(self, wds: list[WatchDescriptor]) -> None:
        """removes callbacks for the given paths.

        :param wds:
            a list of WatchDescriptors
        """
        self._inotify_fd.remove_callbacks([(wd, self._id) for wd in wds])
        for wd in wds:
            self._remove_watch_internally(wd)

    def _remove_watch_internally(self, wd: WatchDescriptor) -> None:
        """Removes a watch descriptor from internal dicts."""
        path = self._active_callbacks_by_watch.pop(wd)
        wd2 = self._active_callbacks_by_path.pop(path)
        if wd2 != wd:
            # Oops. The path already belongs to a different wd. Put it back.
            # This can happen, when events are sent slightly out of order.
            self._active_callbacks_by_path[path] = wd2


def _select_event_type(
    dir_event: type[FileSystemEvent],
    file_event: type[FileSystemEvent],
    *,
    is_directory: bool,
) -> FileSystemEventCtor:
    """selects the correct FileSystemEvent Type based on `is_directory` and returns it."""
    return cast(FileSystemEventCtor, dir_event if is_directory else file_event)


class InotifyEmitter(EventEmitter):
    """inotify(7)-based event emitter.

    :param event_queue:
        The event queue to fill with events.
    :param watch:
        A watch object representing the directory to monitor.
    :type watch:
        :class:`watchdog.observers.api.ObservedWatch`
    :param timeout:
        Read events blocking timeout (in seconds).
    :type timeout:
        ``float``
    :param event_filter:
        Collection of event types to emit, or None for no filtering (default).
    :type event_filter:
        Iterable[:class:`watchdog.events.FileSystemEvent`] | None
    """

    def __init__(
        self,
        event_queue: EventQueue,
        watch: ObservedWatch,
        *,
        timeout: float = DEFAULT_EMITTER_TIMEOUT,
        event_filter: list[type[FileSystemEvent]] | None = None,
        inotify_fd: InotifyFD | None = None,
    ) -> None:
        super().__init__(event_queue, watch, timeout=timeout, event_filter=event_filter)
        self._lock: threading.Lock = threading.Lock()
        self._inotify_fd: InotifyFD = inotify_fd if inotify_fd is not None else InotifyFD.get_instance()
        self._inotify: InotifyWatchGroup | None = None

    def on_thread_start(self) -> None:
        path = os.fsencode(self.watch.path)
        event_mask = self.get_event_mask_from_filter()
        self._inotify = InotifyWatchGroup(
            self._inotify_fd,
            path,
            is_recursive=self.watch.is_recursive,
            event_mask=event_mask,
            follow_symlink=self.watch.follow_symlink,
        )

    def on_thread_stop(self) -> None:
        if self._inotify is not None:
            self._inotify.deactivate()
            self._inotify = None

    def queue_events(self, timeout: float, *, full_events: bool = False) -> None:
        # If "full_events" is true, then the method will report unmatched move events as separate events
        # This behavior is by default only called by a InotifyFullEmitter
        if self._inotify is None:
            logger.error("InotifyEmitter.queue_events() called when the thread is inactive")
            return
        with self._lock:
            if self._inotify is None:
                logger.error("InotifyEmitter.queue_events() called when the thread is inactive")
                return
            event = self._inotify.read_event()
            if event is None:
                return
            self.build_and_queue_event(event)

    def build_and_queue_event(self, event: GroupedInotifyEvent, *, full_events: bool = False) -> None:
        """called for every event for each watch this callback is registered at."""
        cls: FileSystemEventCtor
        if not isinstance(event, PathedInotifyEvent):
            # we got a move event tuple
            move_from, move_to = event
            src_path = self._decode_path(move_from.path)
            dest_path = self._decode_path(move_to.path)
            cls = _select_event_type(DirMovedEvent, FileMovedEvent, is_directory=move_from.ev.is_directory)
            self.queue_event(cls(src_path, dest_path))
            self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
            self.queue_event(DirModifiedEvent(os.path.dirname(dest_path)))
            if move_from.ev.is_directory and self.watch.is_recursive:
                for sub_moved_event in generate_sub_moved_events(src_path, dest_path):
                    self.queue_event(sub_moved_event)
        else:
            src_path = self._decode_path(event.path)
            if event.ev.is_moved_to:
                if full_events:
                    cls = _select_event_type(DirMovedEvent, FileMovedEvent, is_directory=event.ev.is_directory)
                    self.queue_event(cls("", src_path))
                else:
                    cls = _select_event_type(DirCreatedEvent, FileCreatedEvent, is_directory=event.ev.is_directory)
                    self.queue_event(cls(src_path))
                self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
                if event.ev.is_directory and self.watch.is_recursive:
                    for sub_created_event in generate_sub_created_events(src_path):
                        self.queue_event(sub_created_event)
            elif event.ev.is_attrib or event.ev.is_modify:
                cls = _select_event_type(DirModifiedEvent, FileModifiedEvent, is_directory=event.ev.is_directory)
                self.queue_event(cls(src_path))
            elif event.ev.is_delete or (event.ev.is_moved_from and not full_events):
                cls = _select_event_type(DirDeletedEvent, FileDeletedEvent, is_directory=event.ev.is_directory)
                self.queue_event(cls(src_path))
                self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
            elif event.ev.is_moved_from and full_events:
                cls = _select_event_type(DirMovedEvent, FileMovedEvent, is_directory=event.ev.is_directory)
                self.queue_event(cls(src_path, ""))
                self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
            elif event.ev.is_create:
                cls = _select_event_type(DirCreatedEvent, FileCreatedEvent, is_directory=event.ev.is_directory)
                self.queue_event(cls(src_path))
                self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
            elif event.ev.is_delete_self and src_path == self.watch.path:
                cls = _select_event_type(DirDeletedEvent, FileDeletedEvent, is_directory=event.ev.is_directory)
                self.queue_event(cls(src_path))
                self.stop()
            elif not event.ev.is_directory:
                if event.ev.is_open:
                    self.queue_event(FileOpenedEvent(src_path))
                elif event.ev.is_close_write:
                    self.queue_event(FileClosedEvent(src_path))
                    self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
                elif event.ev.is_close_nowrite:
                    self.queue_event(FileClosedNoWriteEvent(src_path))

    def _decode_path(self, path: bytes) -> bytes | str:
        """Decode path only if unicode string was passed to this emitter."""
        return path if isinstance(self.watch.path, bytes) else os.fsdecode(path)

    def get_event_mask_from_filter(self) -> Mask:
        """Optimization: Only include events we are filtering in inotify call."""
        if self._event_filter is None:
            return WATCHDOG_ALL_EVENTS

        # Always listen to delete self
        event_mask = InotifyConstants.IN_DELETE_SELF

        for cls in self._event_filter:
            if cls in {DirMovedEvent, FileMovedEvent}:
                event_mask = Mask(event_mask | InotifyConstants.IN_MOVE)
            elif cls in {DirCreatedEvent, FileCreatedEvent}:
                event_mask = Mask(event_mask | InotifyConstants.IN_MOVE | InotifyConstants.IN_CREATE)
            elif cls is DirModifiedEvent:
                event_mask = Mask(
                    event_mask
                    | (
                        InotifyConstants.IN_MOVE
                        | InotifyConstants.IN_ATTRIB
                        | InotifyConstants.IN_MODIFY
                        | InotifyConstants.IN_CREATE
                        | InotifyConstants.IN_CLOSE_WRITE
                    )
                )
            elif cls is FileModifiedEvent:
                event_mask = Mask(event_mask | InotifyConstants.IN_ATTRIB | InotifyConstants.IN_MODIFY)
            elif cls in {DirDeletedEvent, FileDeletedEvent}:
                event_mask = Mask(event_mask | InotifyConstants.IN_DELETE)
            elif cls is FileClosedEvent:
                event_mask = Mask(event_mask | InotifyConstants.IN_CLOSE_WRITE)
            elif cls is FileClosedNoWriteEvent:
                event_mask = Mask(event_mask | InotifyConstants.IN_CLOSE_NOWRITE)
            elif cls is FileOpenedEvent:
                event_mask = Mask(event_mask | InotifyConstants.IN_OPEN)

        return event_mask


class InotifyFullEmitter(InotifyEmitter):
    """inotify(7)-based event emitter. By default, this class produces move events even if they are not matched
    Such move events will have a ``None`` value for the unmatched part.
    """

    def build_and_queue_event(self, event: GroupedInotifyEvent, *, full_events: bool = True) -> None:
        super().build_and_queue_event(event, full_events=full_events)


class InotifyObserver(BaseObserver):
    """Observer thread that schedules watching directories and dispatches
    calls to event handlers.
    """

    def __init__(self, *, timeout: float = DEFAULT_OBSERVER_TIMEOUT, generate_full_events: bool = False) -> None:
        cls = InotifyFullEmitter if generate_full_events else InotifyEmitter
        super().__init__(cls, timeout=timeout)
