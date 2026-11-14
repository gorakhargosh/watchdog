""":module: watchdog.observers.inotify
:synopsis: ``inotify(7)`` based emitter implementation.
:author: Sebastien Martini <seb@dbzteam.org>
:author: Luke McCarthy <luke@iogopro.co.uk>
:author: yesudeep@google.com (Yesudeep Mangalapilly)
:author: Tim Cuthbertson <tim+github@gfxmonk.net>
:author: Mickaël Schoentgen <contact@tiger-222.fr>
:author: Joachim Coenen <joachimcoenen@icloud.com>
:author: Prateek Dagar <prateek-dagar>
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

import errno
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, cast

from watchdog.events import (
    DirAttribEvent,
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    EventsLostEvent,
    FileAttribEvent,
    FileClosedEvent,
    FileClosedNoWriteEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileOpenedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
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
    from pathlib import Path

    from watchdog.observers.api import EventQueue, ObservedWatch
    from watchdog.utils import Seconds

logger = logging.getLogger(__name__)


class FileSystemEventCtor(Protocol):
    def __call__(self, src_path: bytes | str, dest_path: bytes | str = "") -> FileSystemEvent: ...


class DirNode:
    """N-ary directory tree node for hierarchical inotify watch tracking."""

    __slots__ = ("children", "name", "parent", "wd")

    def __init__(
        self,
        name: bytes,
        wd: WatchDescriptor,
        parent: DirNode | None = None,
    ) -> None:
        self.name = name
        self.wd = wd
        self.parent = parent
        self.children: dict[bytes, DirNode] = {}


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

    _root: DirNode | None = field(default=None, init=False)
    _nodes_by_wd: dict[WatchDescriptor, DirNode] = field(default_factory=dict, init=False)

    @property
    def _active_callbacks_by_watch(self) -> dict[WatchDescriptor, bytes]:
        res: dict[WatchDescriptor, bytes] = {}
        for wd in list(self._nodes_by_wd):
            if path := self._resolve_path(wd):
                res[wd] = path
        return res

    @property
    def _active_callbacks_by_path(self) -> dict[bytes, WatchDescriptor]:
        res: dict[bytes, WatchDescriptor] = {}
        for wd in list(self._nodes_by_wd):
            if path := self._resolve_path(wd):
                res[path] = wd
        return res

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

    def on_events_lost(self) -> None:
        """Queue the overflow behind the events read so far, once :meth:`on_queue_overflow` is done."""
        with self._lock:
            if not self.is_active:
                return
            overflow = InotifyEvent(WatchDescriptor(-1), InotifyConstants.IN_Q_OVERFLOW, 0, b"")
            self._move_event_grouper.put_event(PathedInotifyEvent(overflow, self.path))

    def on_watch_deleted(self, wd: WatchDescriptor) -> None:
        """Called when a watch that this callback is registered at is removed.
        This is the case when the watched object is deleted."""
        with self._lock:
            if not self.is_active:
                return
            self._remove_watch_internally(wd)

    def on_queue_overflow(self) -> None:
        """Rebuild recursive watches after the kernel drops events."""
        with self._lock:
            if not self.is_active:
                return
            self._move_event_grouper.discard_pending_events()
            if not self.is_recursive:
                return
            logger.warning("Inotify queue overflowed; reconciling recursive watches below %r", self.path)
            self._remove_callbacks(list(self._nodes_by_wd))
            self._root = None
            try:
                self._add_all_callbacks(self.path)
            except OSError:
                logger.exception("Unable to rebuild recursive inotify watches below %r", self.path)

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
                source_was_watched = move_src_path is not None and self._move_watches(move_src_path, move_dst_path)
                if event.is_directory and self.is_recursive and not source_was_watched:
                    # The source may have been seen before its watch was registered.
                    self._add_all_callbacks(src_path)
                    if move_src_path is not None:
                        for sub_event in self._recursive_simulate(src_path):
                            sub_src_path = self._build_event_source_path(sub_event)
                            if sub_src_path is not None:
                                self._move_event_grouper.put_event(PathedInotifyEvent(sub_event, sub_src_path))
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
        # TODO: Reconcile concurrent directory discovery with real
        # inotify queue events to eliminate duplicate synthesized events and redundant add_callback calls.
        events = []
        for root, dirnames, filenames in os.walk(src_path, followlinks=self.follow_symlink):
            if not (node := self._find_node_by_path(root)):
                # Not watched: it could not be, or it appeared after the watches were added (e.g. a copy
                # still in progress) and its own queued IN_CREATE event will watch it and report its content
                continue
            wd_root = node.wd

            for dirname in dirnames:
                mask = Mask(InotifyConstants.IN_CREATE | InotifyConstants.IN_ISDIR)
                events.append(InotifyEvent(wd_root, mask, 0, dirname))

            for filename in filenames:
                mask = InotifyConstants.IN_CREATE
                events.append(InotifyEvent(wd_root, mask, 0, filename))
        return events

    def deactivate(self) -> None:
        """Removes all associated watches."""
        with self._lock:
            self._is_active = False
            self._remove_callbacks(list(self._nodes_by_wd))
            self._root = None
            self._move_event_grouper.close()

    def _activate(self) -> None:
        """Adds a watch (optionally recursively) for the given directory path
        to monitor events specified by the mask.
        """
        with self._lock:
            if self.is_active:  # maybe wwe can remove this check...
                return

            try:
                self._add_all_callbacks(self.path)
            except OSError:
                self._remove_callbacks(list(self._nodes_by_wd))
                raise
            self._is_active = True

    # Non-synchronized methods:

    def _resolve_path(self, wd: WatchDescriptor) -> bytes | None:
        # TODO: Add bounded LRU/FIFO path cache if needed for high-frequency path resolution.
        node = self._nodes_by_wd.get(wd)
        if node is None:
            return None
        return self._reconstruct_path_iterative(node)

    def _reconstruct_path_iterative(self, node: DirNode) -> bytes | None:
        if node is self._root:
            return self.path

        parts: list[bytes] = []
        curr: DirNode | None = node
        root = self._root
        while curr is not None and curr is not root:
            parts.append(curr.name)
            curr = curr.parent

        if curr is not root:
            return None

        parts.reverse()
        sep = os.path.sep.encode()
        root_path = self.path
        if root_path.endswith(sep):
            return root_path + sep.join(parts)
        return root_path + sep + sep.join(parts)

    def _find_node_by_path(self, path: bytes) -> DirNode | None:
        if self._root is None:
            return None
        norm_path = os.path.normpath(path)
        norm_root = os.path.normpath(self.path)
        if norm_path == norm_root:
            return self._root

        sep = os.path.sep.encode()
        if norm_root == sep:
            rel = norm_path[len(sep) :]
        else:
            prefix = norm_root + sep
            if not norm_path.startswith(prefix):
                return None
            rel = norm_path[len(prefix) :]

        parts = [p for p in rel.split(sep) if p]
        curr = self._root
        for part in parts:
            child = curr.children.get(part)
            if child is None:
                return None
            curr = child
        return curr

    def _insert_node(self, path: bytes, wd: WatchDescriptor) -> DirNode | None:
        norm_path = os.path.normpath(path)
        norm_root = os.path.normpath(self.path)
        if norm_path == norm_root:
            if self._root is None:
                self._root = DirNode(name=b"", wd=wd, parent=None)
            else:
                self._root.wd = wd
            self._nodes_by_wd[wd] = self._root
            return self._root

        sep = os.path.sep.encode()
        if norm_root == sep:
            rel = norm_path[len(sep) :]
        else:
            prefix = norm_root + sep
            if not norm_path.startswith(prefix):
                logger.warning("Path %r is not under watched root %r", path, self.path)
                return None
            rel = norm_path[len(prefix) :]

        parts = [p for p in rel.split(sep) if p]
        if not parts:
            return self._root

        if self._root is None:
            self._root = DirNode(name=b"", wd=WatchDescriptor(-1), parent=None)

        curr = self._root
        for part in parts[:-1]:
            child = curr.children.get(part)
            if child is None:
                child = DirNode(name=part, wd=WatchDescriptor(-1), parent=curr)
                curr.children[part] = child
            curr = child

        last_part = parts[-1]
        existing = curr.children.get(last_part)
        if existing is not None:
            existing.wd = wd
            node = existing
        else:
            node = DirNode(name=last_part, wd=wd, parent=curr)
            curr.children[last_part] = node

        # Note on descriptor cardinality:
        # In Linux inotify, inotify_add_watch returns the same WatchDescriptor for multiple paths
        # that resolve to the same underlying inode (e.g. symlinks followed into an existing directory).
        # Both upstream flat dicts and this tree map wd -> most recently registered node.
        # TODO: Consider multi-node mapping per wd if symlink alias path disambiguation is required.
        self._nodes_by_wd[wd] = node
        return node

    def _build_event_source_path(self, event: InotifyEvent) -> bytes | None:
        watched_path = self._resolve_path(event.wd)
        if watched_path is None:
            return None
        return os.path.join(watched_path, event.name) if event.name else watched_path  # avoid trailing slash

    def _prune_subtree_nodes(self, root_node: DirNode) -> None:
        stack = [root_node]
        while stack:
            curr = stack.pop()
            self._nodes_by_wd.pop(curr.wd, None)
            stack.extend(curr.children.values())
            curr.children.clear()
            curr.parent = None

    def _move_watches(self, move_src_path: bytes, move_dst_path: bytes) -> bool:
        """Move all watches in the source tree and return whether the source was watched."""
        node = self._find_node_by_path(move_src_path)
        if node is None:
            return False

        if node is self._root:
            self.path = move_dst_path
            return True

        norm_dst = os.path.normpath(move_dst_path)
        new_name = os.path.basename(norm_dst)
        new_parent_path = os.path.dirname(norm_dst)
        new_parent = self._find_node_by_path(new_parent_path)

        if new_parent is None:
            return False

        # Guard against cyclic reparenting
        curr: DirNode | None = new_parent
        while curr:
            if curr is node:
                return False
            curr = curr.parent

        if node.parent is new_parent and node.name == new_name:
            return True

        # If a child with new_name already exists in new_parent, clean it up before reparenting
        existing_child = new_parent.children.pop(new_name, None)
        if existing_child and existing_child is not node:
            self._prune_subtree_nodes(existing_child)

        # Detach from old parent
        if node.parent is not None:
            node.parent.children.pop(node.name, None)

        # Reparent with new name
        node.name = new_name
        node.parent = new_parent
        new_parent.children[new_name] = node

        return True

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
        try:
            wd = self._inotify_fd.add_callback(path, self.event_mask, self._callback, self._id)
            node = self._insert_node(path, wd)
            if node is None:
                self._inotify_fd.remove_callbacks([(wd, self._id)])
        except OSError as e:
            # Descendants may disappear or become inaccessible during recursive
            # registration, but a failure to watch the root must reach the caller.
            if path == self.path:
                raise
            # Running out of watches or instances leaves the rest of the tree unwatched.
            if e.errno in {errno.ENOSPC, errno.EMFILE}:
                if not self.is_active:
                    raise
                logger.warning("Unable to watch %r: %s", path, e)

    def _remove_callbacks(self, wds: list[WatchDescriptor]) -> None:
        """removes callbacks for the given paths.

        :param wds:
            a list of WatchDescriptors
        """
        self._inotify_fd.remove_callbacks([(wd, self._id) for wd in wds])
        for wd in wds:
            self._remove_watch_internally(wd)

    def _remove_watch_internally(self, wd: WatchDescriptor) -> None:
        """Removes a watch descriptor from internal tree."""
        node = self._nodes_by_wd.pop(wd, None)
        if node is not None:
            node.wd = WatchDescriptor(-1)
            if node is self._root and not node.children:
                self._root = None
            elif not node.children:
                self._prune_empty_ancestors(node)

    def _prune_empty_ancestors(self, node: DirNode) -> None:
        curr: DirNode | None = node
        while curr is not None and curr is not self._root:
            if curr.children or curr.wd != WatchDescriptor(-1):
                break
            parent = curr.parent
            if parent is not None:
                parent.children.pop(curr.name, None)
            curr.parent = None
            curr = parent
        if self._root is not None and not self._root.children and self._root.wd == WatchDescriptor(-1):
            self._root = None


def _select_event_type(
    dir_event: type[FileSystemEvent],
    file_event: type[FileSystemEvent],
    *,
    is_directory: bool,
) -> FileSystemEventCtor:
    """selects the correct FileSystemEvent Type based on `is_directory` and returns it."""
    return cast("FileSystemEventCtor", dir_event if is_directory else file_event)


class InotifyEmitter(EventEmitter):
    """inotify(7)-based event emitter.

    :param event_queue:
        The event queue to fill with events.
    :param watch:
        A watch object representing the directory to monitor.
    :type watch:
        :class:`watchdog.observers.api.ObservedWatch`
    :param timeout:
        Read events blocking timeout.
    :type timeout:
        ``Seconds``
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
        timeout: Seconds = DEFAULT_EMITTER_TIMEOUT,
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
        # Drop the published reference first so concurrent queue_events() calls
        # see a stopped emitter. deactivate() must not run under self._lock:
        # queue_events() may be blocked in read_event(), and deactivate() is
        # what unblocks that wait.
        inotify = self._inotify
        self._inotify = None
        if inotify is not None:
            inotify.deactivate()

    def queue_events(self, timeout: Seconds, *, full_events: bool = False) -> None:
        # If "full_events" is true, then the method will report unmatched move events as separate events
        # This behavior is by default only called by a InotifyFullEmitter
        #
        # Snapshot the watch group before the blocking read. Holding only a
        # local reference means on_thread_stop() can null self._inotify and
        # close the queue without this method raising AttributeError.
        with self._lock:
            inotify = self._inotify
        if inotify is None:
            logger.error("InotifyEmitter.queue_events() called when the thread is inactive")
            return
        event = inotify.read_event()
        if event is None:
            return
        with self._lock:
            if self._inotify is None:
                logger.error("InotifyEmitter.queue_events() called when the thread is inactive")
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
            elif event.ev.is_attrib:
                cls = _select_event_type(DirAttribEvent, FileAttribEvent, is_directory=event.ev.is_directory)
                self.queue_event(cls(src_path))
            elif event.ev.is_modify:
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
            elif event.ev.is_queue_overflow:
                self.queue_event(
                    EventsLostEvent(
                        self.watch.resolved_path if self.watch.is_file else src_path,
                        is_directory=not self.watch.is_file,
                    )
                )
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
        if self.watch.is_recursive:
            # New directories need watches even when creation events are filtered.
            event_mask = Mask(event_mask | InotifyConstants.IN_CREATE)

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

    The inotify reader is allocated on the first scheduled watch. Kernel
    resource-limit errors are therefore raised by :meth:`schedule`.
    """

    def __init__(self, *, timeout: Seconds = DEFAULT_OBSERVER_TIMEOUT, generate_full_events: bool = False) -> None:
        self._inotify_fd: InotifyFD | None = None
        cls = InotifyFullEmitter if generate_full_events else InotifyEmitter
        super().__init__(cls, timeout=timeout)

    def schedule(
        self,
        event_handler: FileSystemEventHandler,
        path: str | Path,
        *,
        recursive: bool = False,
        event_filter: list[type[FileSystemEvent]] | None = None,
        follow_symlink: bool = False,
    ) -> ObservedWatch:
        # Empty observers need neither a kernel instance nor a reader thread.
        # Allocate under the same lock as schedule/start so every emitter uses
        # exactly one independent reader, including when watches are added concurrently.
        with self._lock:
            if self._inotify_fd is None:
                inotify_fd = InotifyFD()
                inotify_fd.start()
                self._inotify_fd = inotify_fd
                self._emitter_kwargs["inotify_fd"] = inotify_fd
            return super().schedule(
                event_handler,
                path,
                recursive=recursive,
                event_filter=event_filter,
                follow_symlink=follow_symlink,
            )

    def on_thread_stop(self) -> None:
        super().on_thread_stop()
        if self._inotify_fd is not None:
            self._inotify_fd.stop()
            self._inotify_fd.join()
