from __future__ import annotations

import contextlib
import logging
import os
import queue
import threading
from collections import defaultdict, deque
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any

from watchdog.events import (
    EVENT_TYPE_CREATED,
    EVENT_TYPE_DELETED,
    EVENT_TYPE_MOVED,
    DirCreatedEvent,
    DirDeletedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileSystemMovedEvent,
)
from watchdog.utils import BaseThread
from watchdog.utils.bricks import SkipRepeatsQueue
from watchdog.utils.statx import get_path_birthtime_ns

if TYPE_CHECKING:
    import types
    from collections.abc import Iterable
    from typing import Self

    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.utils import Seconds

logger = logging.getLogger(__name__)

DEFAULT_EMITTER_TIMEOUT: Seconds = 1.0
DEFAULT_OBSERVER_TIMEOUT: Seconds = 1.0

_STRUCTURAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        EVENT_TYPE_CREATED,
        EVENT_TYPE_DELETED,
        EVENT_TYPE_MOVED,
    }
)


class _QueueEntry(tuple):
    """Internal envelope for queued (event, watch) pairs.

    Subclasses tuple so that item unpacking (event, watch = entry) works seamlessly
    everywhere. Extends equality to compare session_token attributes, preventing
    SkipRepeatsQueue from dropping consecutive equal events across distinct
    synchronization sessions.
    """

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        eq = super().__eq__(other)
        if eq is NotImplemented or not eq:
            return False
        # Compare session_token and watch_token so SkipRepeatsQueue differentiates consecutive
        # identical events across distinct synchronization sessions or watch generations.
        if isinstance(other, tuple) and len(self) >= 2 and len(other) >= 2:
            if getattr(self[0], "session_token", None) != getattr(other[0], "session_token", None):
                return False
            return getattr(self[0], "watch_token", None) == getattr(other[0], "watch_token", None)
        return True

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


class EventQueue(SkipRepeatsQueue):
    """Thread-safe event queue based on a special queue that skips adding
    the same event (:class:`watchdog.events.FileSystemEvent`) multiple times
    consecutively. Thus avoiding dispatching multiple event handling
    calls when multiple identical events are produced quicker than an observer
    can consume them.

    :param maxsize:
        Maximum number of items allowed in the queue. If <= 0, the queue size is infinite.
    :type maxsize:
        ``int``
    """

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:  # noqa: FBT001,FBT002
        if isinstance(item, tuple) and len(item) == 2 and not isinstance(item, _QueueEntry):
            item = _QueueEntry(item)
        super().put(item, block, timeout)


class ObservedWatch:
    """An scheduled watch.

    :param path:
        Path string.
    :type path:
        ``str`` or :class:`pathlib.Path`
    :param recursive:
        ``True`` if watch should include subdirectories; ``False`` otherwise.
    :type recursive:
        ``bool``
    :param event_filter:
        Optional collection of :class:`watchdog.events.FileSystemEvent` to watch.
    :type event_filter:
        Iterable[:class:`watchdog.events.FileSystemEvent`] | None
    :param follow_symlink:
        ``True`` if symlinks are followed; ``False`` otherwise.
    :type follow_symlink:
        ``bool``
    :param emit_existing:
        ``True`` if created events should be emitted for existing files and
        directories upon startup; ``False`` otherwise (default).
        When watching a directory, synthetic ``DirCreatedEvent`` and ``FileCreatedEvent``
        instances are emitted for all existing contents. When watching a single file,
        a single synthetic ``FileCreatedEvent`` is emitted for that file alone.
    :type emit_existing:
        ``bool``
    :param ordered_startup:
        ``True`` to buffer overlapping live events during startup catch-up so
        synthetic creations are dispatched before subsequent live events, and
        suppress delayed duplicate live ``Created`` events matching discovered
        startup file identities; ``False`` otherwise (default).
        On :class:`~watchdog.observers.polling.PollingEmitter`, completion waits
        for a synchronous snapshot diff barrier; on asynchronous OS emitters
        (FSEvents, inotify, kqueue, Windows), delayed duplicate creations are
        reconciled against the startup identity ledger. Without a native backend
        barrier, strict causal ordering across delayed multi-step pre-scan
        histories (e.g. Created then Moved before scan completion) is not
        guaranteed. Delayed duplicate suppression fails open when filesystem
        inode numbers are non-positive (such as FAT32 or SMB).
        Only takes effect when ``emit_existing=True``; ignored if ``emit_existing=False``.
        On Linux, chronological birthtime ordering utilizes ``statx(2)`` (Linux >= 4.11
        on ext4/Btrfs/XFS); on older kernels or filesystems without birthtime support,
        ordering falls back gracefully to modification time (``mtime``).
    :type ordered_startup:
        ``bool``
    """

    def __init__(
        self,
        path: str | Path,
        *,
        recursive: bool,
        event_filter: list[type[FileSystemEvent]] | None = None,
        follow_symlink: bool = False,
        emit_existing: bool = False,
        ordered_startup: bool = False,
    ):
        raw_path = str(path) if isinstance(path, Path) else path
        self.raw_path = raw_path
        self.normalized_path = os.path.normcase(os.path.abspath(os.path.normpath(raw_path)))
        self.follow_symlink = follow_symlink
        self.event_filter = frozenset(event_filter) if event_filter is not None else None
        self.emit_existing = emit_existing
        # ordered_startup is a reconciliation modifier for startup catch-up;
        # if emit_existing is False, ordered_startup has no effect and is disabled.
        self.ordered_startup = ordered_startup if emit_existing else False
        self.watch_token: object = object()

        self.is_file = os.path.isfile(raw_path)
        self.resolved_path = (
            os.path.realpath(os.path.abspath(raw_path)) if follow_symlink else os.path.abspath(raw_path)
        )

        if self.is_file:
            self.path = os.path.dirname(self.resolved_path)
            self.is_recursive = False
        else:
            self.path = raw_path
            self.is_recursive = recursive

    @property
    def key(self) -> tuple[str, str, bool, frozenset[type[FileSystemEvent]] | None, bool, bool, bool]:
        """A tuple key identifying the watch
        (resolved_path, normalized_path, recursive, event_filter, follow_symlink, emit_existing, ordered_startup).
        """
        return (
            self.resolved_path,
            self.normalized_path,
            self.is_recursive,
            self.event_filter,
            self.follow_symlink,
            self.emit_existing,
            self.ordered_startup,
        )

    def __eq__(self, watch: object) -> bool:
        if not isinstance(watch, ObservedWatch):
            return NotImplemented
        return self.key == watch.key

    def __ne__(self, watch: object) -> bool:
        if not isinstance(watch, ObservedWatch):
            return NotImplemented
        return self.key != watch.key

    def __hash__(self) -> int:
        return hash(self.key)

    def __repr__(self) -> str:
        if self.event_filter is not None:
            event_filter_str = "|".join(sorted(_cls.__name__ for _cls in self.event_filter))
            event_filter_str = f", event_filter={event_filter_str}"
        else:
            event_filter_str = ""
        emit_existing_str = ", emit_existing=True" if self.emit_existing else ""
        ordered_str = ", ordered_startup=True" if self.ordered_startup else ""
        return (
            f"<{type(self).__name__}: path={self.path!r}, is_recursive={self.is_recursive}"
            f"{event_filter_str}{emit_existing_str}{ordered_str}>"
        )


class SnapshotStatus(Enum):
    """Status result of waiting for an emitter snapshot during startup catch-up.

    - IDLE: No snapshot has been requested or taken yet.
    - SUCCESS: A snapshot that started after the request was registered has completed successfully.
    - FAILED: Snapshot encountered an unrecoverable OSError or filesystem error.
    - CANCELLED: The watch was unscheduled or the observer was stopped while waiting.
    - TIMEOUT: The specified wait timeout elapsed before a snapshot completed.
    """

    IDLE = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()
    TIMEOUT = auto()


# Observer classes
class EventEmitter(BaseThread):
    """Producer thread base class subclassed by event emitters
    that generate events and populate a queue with them.

    :param event_queue:
        The event queue to populate with generated events.
    :type event_queue:
        :class:`EventQueue`
    :param watch:
        The watch to observe and produce events for.
    :type watch:
        :class:`ObservedWatch`
    :param timeout:
        Timeout between successive attempts at reading events.
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
    ) -> None:
        super().__init__()
        # bool subclasses int; timeout=True would silently become 1.0s
        if isinstance(timeout, bool):
            error = f"timeout must be a float, not bool (got {timeout!r})"
            raise TypeError(error)
        self._event_queue = event_queue
        self._watch = watch
        self._timeout = timeout
        self._event_filter = frozenset(event_filter) if event_filter is not None else None

    @property
    def timeout(self) -> Seconds:
        """Blocking timeout for reading events."""
        return self._timeout

    @property
    def watch(self) -> ObservedWatch:
        """The watch associated with this emitter."""
        return self._watch

    def queue_event(self, event: FileSystemEvent) -> None:
        """Queues a single event.

        :param event:
            Event to be queued.
        :type event:
            An instance of :class:`watchdog.events.FileSystemEvent`
            or a subclass.
        """
        event.watch_path = self.watch.path
        if getattr(event, "watch_token", None) is None:
            setattr(event, "watch_token", getattr(self.watch, "watch_token", None))  # noqa: B010
        passes_filter = self._event_filter is None or any(isinstance(event, cls) for cls in self._event_filter)
        is_structural_sync = self.watch.emit_existing and (
            event.is_directory or isinstance(event, (FileSystemMovedEvent, FileDeletedEvent))
        )
        if passes_filter or is_structural_sync:
            self._event_queue.put((event, self.watch))

    def queue_events(self, timeout: Seconds) -> None:
        """Override this method to populate the event queue with events
        per interval period.

        :param timeout:
            Timeout between successive attempts at
            reading events.
        :type timeout:
            ``Seconds``
        """

    supports_sync_barrier: bool = False
    """Whether ``wait_for_snapshot()`` establishes a strict pre-completion backend barrier.

    Emitters with ``supports_sync_barrier = True`` (such as
    :class:`~watchdog.observers.polling.PollingEmitter`) allow
    :class:`~watchdog.observers.api.BaseObserver` to discard its startup identity ledger
    immediately upon ``SynchronizationComplete`` because all prior backend state has
    been drained.
    """

    def wait_for_snapshot(self, *, cancel_event: threading.Event | None = None) -> SnapshotStatus:
        """Wait for emitter to complete in-flight snapshot or event queueing.

        Without a native backend barrier (``supports_sync_barrier=False``),
        ordered startup catch-up suppresses delayed duplicate ``Created`` events
        using the startup identity ledger rather than guaranteeing strict OS stream
        causal ordering across delayed multi-step pre-scan histories.
        """
        # TODO: Implement native synchronization barriers for asynchronous OS backends in
        # follow-up work:
        # - FSEvents: synchronous stream flush (FSEventStreamFlushSync) + cycle fence.
        # - Inotify: shared reader notification drain plus InotifyMoveEventGrouper /
        #   DelayedQueue coordination without destabilizing active inotify fixes.
        # - Kqueue: wake-pipe drain of pending kevent batches.
        # - Windows: ReadDirectoryChangesW overlapped/buffer drain.
        return SnapshotStatus.SUCCESS

    def run(self) -> None:
        while self.should_keep_running():
            self.queue_events(self.timeout)


class EventDispatcher(BaseThread):
    """Consumer thread base class subclassed by event observer threads
    that dispatch events from an event queue to appropriate event handlers.

    :param timeout:
        Timeout value passed to emitters
        constructions in the child class BaseObserver.
    :type timeout:
        ``Seconds``
    """

    stop_event = object()
    """Event inserted into the queue to signal a requested stop."""

    def __init__(self, *, timeout: Seconds = DEFAULT_OBSERVER_TIMEOUT) -> None:
        super().__init__()
        # bool subclasses int; timeout=True would silently become 1.0s
        if isinstance(timeout, bool):
            error = f"timeout must be a float, not bool (got {timeout!r})"
            raise TypeError(error)
        self._event_queue = EventQueue()
        self._timeout = timeout

    @property
    def timeout(self) -> Seconds:
        """Timeout value to construct emitters with."""
        return self._timeout

    def stop(self) -> None:
        BaseThread.stop(self)
        with contextlib.suppress(queue.Full):
            self.event_queue.put_nowait(EventDispatcher.stop_event)

    @property
    def event_queue(self) -> EventQueue:
        """The event queue which is populated with file system events
        by emitters and from which events are dispatched by a dispatcher
        thread.
        """
        return self._event_queue

    def dispatch_events(self, event_queue: EventQueue) -> None:
        """Override this method to consume events from an event queue, blocking
        on the queue for the specified timeout before raising :class:`queue.Empty`.

        :param event_queue:
            Event queue to populate with one set of events.
        :type event_queue:
            :class:`EventQueue`
        :raises:
            :class:`queue.Empty`
        """

    def run(self) -> None:
        while self.should_keep_running():
            try:
                self.dispatch_events(self.event_queue)
            except queue.Empty:
                continue


def _is_same_or_descendant(path: str, prefix: str) -> bool:
    """Return True when normalized ``path`` equals ``prefix`` or lies underneath it."""
    if path == prefix:
        return True
    if not prefix:
        return False
    if prefix.endswith(os.sep) or (os.altsep and prefix.endswith(os.altsep)):
        return path.startswith(prefix)
    return path.startswith(prefix + os.sep) or bool(os.altsep and path.startswith(prefix + os.altsep))


def _replace_path_prefix(path: str, old_prefix: str, new_prefix: str) -> str:
    """Translate ``path`` from ``old_prefix`` to ``new_prefix``."""
    if path == old_prefix:
        return new_prefix
    return new_prefix + path[len(old_prefix) :]


class _WatchSyncState:
    """Internal state tracked per watch during startup synchronization catch-up.

    Tracks files discovered during initial filesystem traversal to deduplicate
    them against overlapping live kernel events, stages live events when
    ``ordered_startup`` is enabled, and retains the startup identity ledger on
    asynchronous backends so delayed buffered ``Created`` duplicates can be
    suppressed safely after synchronization completes.

    :param ordered_startup:
        Whether live events arriving during catch-up should be staged and flushed
        in arrival order once catch-up completes.
    :param session_token:
        Unique object token identifying the synchronization session.
    :param follow_symlink:
        Whether symbolic links are dereferenced during sync normalization.
    :param root_norm:
        Optional normalized watch root path used to bound parent-tree links.
    """

    def __init__(
        self,
        *,
        ordered_startup: bool = False,
        session_token: object | None = None,
        follow_symlink: bool = False,
        root_norm: str | None = None,
    ) -> None:
        self.ordered_startup = ordered_startup
        self.follow_symlink = follow_symlink
        self.root_norm = root_norm
        # Unique session token identifying the specific watch synchronization lifetime.
        # Used by the dispatcher and queue deduplication to isolate events across
        # unschedule and reschedule cycles on the same path.
        self.session_token = session_token if session_token is not None else object()
        self.cancel_event = threading.Event()
        """Signaled when the watch is unscheduled to cancel the background sync worker."""
        self.seen_created: set[bytes | str] = set()
        """Set of normalized paths for which creation events have already been dispatched."""
        self.deleted_during_sync: set[bytes | str] = set()
        """Set of normalized paths deleted live during sync, used to suppress stale synthetic creations."""
        self.deleted_dirs: set[str] = set()
        """Set of normalized directory paths deleted or retired live during sync, tombstoning descendants."""
        self.recreated_dirs: set[str] = set()
        """Set of normalized directory paths deleted and recreated live during sync."""
        self.staged_live_events: list[FileSystemEvent] = []
        """Buffer holding staged live event records that arrived while the startup scan was running."""
        self.staged_created_paths: set[str] = set()
        """Index of normalized paths with staged live Created events enabling O(1) pruning checks."""
        self.staged_moves_by_dest: dict[
            str,
            tuple[str, list[FileSystemEvent], int | None, tuple[int, int] | None, bool, set[str]],
        ] = {}
        """Mapping of destination normalized path to
        (move_root, move_events, dest_btime, dest_file_id, move_src_seen, move_sources)
        used to reconcile staged live moves against startup catch-up discoveries in O(1) time
        without lock-held disk I/O. Guards against duplicate/contradictory events and inode recycling (#992)."""
        self.startup_entities: dict[str, tuple[tuple[int, int] | None, int | None]] = {}
        """Ledger of normalized startup entity paths mapped to ``(file_id, btime_ns)``."""
        self.children_by_parent: dict[str, set[str]] = defaultdict(set)
        """Parent-to-child normalized path index enabling O(subtree) move/delete reconciliation."""
        self.moved_dir_dest_to_src: dict[str, str] = {}
        """Mapping from live destination directory to its handler-visible root before staged move dispatch."""
        self.moved_dir_src_to_dest: dict[str, str] = {}
        """Mapping from previous source directory aliases to their current live destination directory."""
        self.is_sync_complete: bool = False
        """Whether the startup catch-up scan for this watch has completed."""
        self.sync_started: bool = False
        """Whether the background sync worker thread has been launched."""

    def has_startup_ledger(self) -> bool:
        """Return True if any startup entity identities remain tracked for late dedup."""
        return bool(self.startup_entities)

    def _link_path_tree(self, norm_path: str) -> None:
        """Link ``norm_path`` and any unlinked ancestor directories up to ``root_norm``."""
        curr = norm_path
        while True:
            if self.root_norm is not None and curr == self.root_norm:
                break
            parent = os.path.dirname(curr)
            if not parent or parent == curr:
                break
            siblings = self.children_by_parent[parent]
            parent_existed = len(siblings) > 0
            siblings.add(curr)
            if parent_existed:
                break
            curr = parent

    def _unlink_from_parent(self, norm_path: str) -> None:
        """Detach ``norm_path`` from its parent index and prune now-empty container entries."""
        curr = norm_path
        while True:
            parent = os.path.dirname(curr)
            if not parent or parent == curr:
                break
            siblings = self.children_by_parent.get(parent)
            if siblings is None:
                break
            siblings.discard(curr)
            if siblings:
                break
            del self.children_by_parent[parent]
            if (
                parent in self.startup_entities
                or parent in self.seen_created
                or (self.root_norm is not None and parent == self.root_norm)
            ):
                break
            curr = parent

    def _pop_subtree_paths(self, root_path: str) -> list[str]:
        """Collect and detach ``root_path`` and all indexed descendants in O(subtree) time."""
        paths: list[str] = []
        queue_nodes: deque[str] = deque([root_path])
        visited: set[str] = set()
        while queue_nodes:
            node = queue_nodes.popleft()
            if node in visited:
                continue
            visited.add(node)
            paths.append(node)
            children = self.children_by_parent.pop(node, None)
            if children:
                queue_nodes.extend(children)
        self._unlink_from_parent(root_path)
        return paths

    def mark_seen(self, norm_path: str) -> None:
        """Record ``norm_path`` in ``seen_created`` and ensure it is indexed for subtree ops."""
        self.seen_created.add(norm_path)
        self._link_path_tree(norm_path)

    def record_startup_entity(
        self,
        norm_path: str,
        identity: tuple[tuple[int, int] | None, int | None],
    ) -> None:
        """Record a startup-dispatched entity identity in the ledger."""
        self.startup_entities[norm_path] = identity
        self._link_path_tree(norm_path)

    def remove_startup_entity(self, norm_path: str) -> None:
        """Remove a single path from the startup ledger and prune empty parent sets if unused."""
        if (
            self.startup_entities.pop(norm_path, None) is not None
            and not self.children_by_parent.get(norm_path)
            and norm_path not in self.seen_created
        ):
            self._unlink_from_parent(norm_path)

    def invalidate_subtree(self, norm_path: str, *, include_staged_moves: bool = False) -> set[str]:
        """Invalidate ``norm_path`` and all indexed descendants from ledger and active sync state."""
        subtree = self._pop_subtree_paths(norm_path)
        removed = set(subtree)
        for p in subtree:
            self.startup_entities.pop(p, None)
            self.seen_created.discard(p)
        if not self.is_sync_complete:
            self.deleted_during_sync.update(removed)
            self.deleted_during_sync.add(norm_path)
            if include_staged_moves:
                for dest in list(self.staged_moves_by_dest):
                    if _is_same_or_descendant(dest, norm_path):
                        self.staged_moves_by_dest.pop(dest, None)
                for d in list(self.moved_dir_dest_to_src):
                    if _is_same_or_descendant(d, norm_path):
                        self.moved_dir_dest_to_src.pop(d, None)
        return removed

    def translate_subtree(
        self,
        src_norm: str,
        dest_norm: str,
        *,
        include_root_in_seen: bool = True,
    ) -> None:
        """Translate ``src_norm`` and all indexed descendants to ``dest_norm`` in O(subtree) time."""
        if src_norm == dest_norm:
            return
        # Drop any stale ledger/seen entries under destination being overwritten or replaced.
        self.invalidate_subtree(dest_norm)
        subtree = self._pop_subtree_paths(src_norm)

        for old_path in subtree:
            new_path = _replace_path_prefix(old_path, src_norm, dest_norm)
            if (ident := self.startup_entities.pop(old_path, None)) is not None:
                self.startup_entities[new_path] = ident
                self._link_path_tree(new_path)
            if old_path in self.seen_created:
                self.seen_created.discard(old_path)
                if old_path != src_norm or include_root_in_seen:
                    self.seen_created.add(new_path)
                    self._link_path_tree(new_path)
            if not self.is_sync_complete:
                self.deleted_during_sync.add(old_path)
                self.deleted_during_sync.discard(new_path)

        if not self.is_sync_complete:
            self.deleted_during_sync.add(src_norm)
            self.deleted_during_sync.discard(dest_norm)
            if self.staged_moves_by_dest:
                for old_dest in list(self.staged_moves_by_dest):
                    if old_dest != src_norm and _is_same_or_descendant(old_dest, src_norm):
                        new_dest = _replace_path_prefix(old_dest, src_norm, dest_norm)
                        self.staged_moves_by_dest[new_dest] = self.staged_moves_by_dest.pop(old_dest)

    def _longest_ancestor_match(self, norm_path: str, lookup: Any) -> str | None:
        """Return ``norm_path`` or its deepest ancestor present in ``lookup``, bounded by ``root_norm``."""
        curr = norm_path
        while True:
            if curr in lookup:
                return curr
            if self.root_norm is not None and curr == self.root_norm:
                return None
            parent = os.path.dirname(curr)
            if not parent or parent == curr:
                return None
            curr = parent

    def resolve_live_path(self, path: str) -> tuple[str, str | None]:
        """Resolve a path through chained and nested directory move aliases to its live location."""
        curr = path
        first_src: str | None = None
        visited: set[str] = set()
        while True:
            src = self._longest_ancestor_match(curr, self.moved_dir_src_to_dest)
            if src is None or src in visited:
                break
            visited.add(src)
            if first_src is None:
                first_src = src
            dest = self.moved_dir_src_to_dest[src]
            curr = _replace_path_prefix(curr, src, dest)
        return curr, first_src

    def resolve_handler_path(self, live_path: str) -> str:
        """Resolve a live path through staged destination-to-source mappings to its handler-visible path."""
        curr = live_path
        visited: set[str] = set()
        while True:
            dest_match = self._longest_ancestor_match(curr, self.moved_dir_dest_to_src)
            if not dest_match or dest_match in visited:
                break
            visited.add(dest_match)
            curr = _replace_path_prefix(curr, dest_match, self.moved_dir_dest_to_src[dest_match])
        return curr

    def has_recreated_ancestor(self, norm_path: str) -> bool:
        """Check whether ``norm_path`` or an ancestor was deleted and recreated during sync."""
        return bool(self.recreated_dirs and self._longest_ancestor_match(norm_path, self.recreated_dirs))

    def is_recreated_path(self, norm_path: str) -> bool:
        """Check whether ``norm_path`` or its resolved live destination is in a recreated directory."""
        if not self.recreated_dirs:
            return False
        live_path, _ = self.resolve_live_path(norm_path)
        return self.has_recreated_ancestor(norm_path) or self.has_recreated_ancestor(live_path)

    def _tombstone_dir(self, path: str) -> None:
        """Tombstone a directory path and prune any existing descendant tombstones."""
        self.deleted_dirs.add(path)
        self.recreated_dirs.discard(path)
        for d in list(self.deleted_dirs):
            if d != path and _is_same_or_descendant(d, path):
                self.deleted_dirs.discard(d)
        for d in list(self.recreated_dirs):
            if _is_same_or_descendant(d, path):
                self.recreated_dirs.discard(d)

    def record_dir_delete(self, norm_path: str) -> None:
        """Record live directory deletion, tombstoning descendants and retiring moved targets."""
        self._tombstone_dir(norm_path)

        # Before retiring aliases, find subtrees that moved OUT of norm_path and rebase all historical source keys
        # so original paths continue to resolve to dest.
        rebased_out: dict[str, str] = {}
        parents_by_dest: dict[str, list[str]] = {}
        for parent_src, parent_dest in self.moved_dir_src_to_dest.items():
            if not _is_same_or_descendant(parent_src, norm_path):
                parents_by_dest.setdefault(parent_dest, []).append(parent_src)

        for src, dest in self.moved_dir_src_to_dest.items():
            if _is_same_or_descendant(src, norm_path) and not _is_same_or_descendant(dest, norm_path):
                matched_any = False
                for parent_dest, parent_sources in parents_by_dest.items():
                    if _is_same_or_descendant(src, parent_dest):
                        for parent_src in parent_sources:
                            orig_key = _replace_path_prefix(src, parent_dest, parent_src)
                            rebased_out[orig_key] = dest
                            matched_any = True
                if not matched_any:
                    dest_match = self._longest_ancestor_match(src, self.moved_dir_dest_to_src)
                    if dest_match:
                        orig_key = _replace_path_prefix(src, dest_match, self.moved_dir_dest_to_src[dest_match])
                        rebased_out[orig_key] = dest
                    else:
                        rebased_out[src] = dest

        for d in list(self.moved_dir_dest_to_src):
            if _is_same_or_descendant(d, norm_path):
                self.moved_dir_dest_to_src.pop(d, None)

        for src, dest in list(self.moved_dir_src_to_dest.items()):
            if _is_same_or_descendant(src, norm_path):
                self.moved_dir_src_to_dest.pop(src, None)
            elif _is_same_or_descendant(dest, norm_path):
                self.moved_dir_src_to_dest.pop(src, None)
                self._tombstone_dir(src)
            elif _is_same_or_descendant(norm_path, dest):
                self._tombstone_dir(_replace_path_prefix(norm_path, dest, src))

        self.moved_dir_src_to_dest.update(rebased_out)

    def record_dir_create(self, norm_path: str) -> None:
        """Handle live directory creation, clearing tombstones and tracking recreation."""
        if norm_path in self.deleted_dirs:
            self.deleted_dirs.discard(norm_path)
            self.recreated_dirs.add(norm_path)
        for d in list(self.deleted_dirs):
            if _is_same_or_descendant(d, norm_path):
                self.deleted_dirs.discard(d)
                self.recreated_dirs.add(d)
        for src, dest in list(self.moved_dir_src_to_dest.items()):
            if _is_same_or_descendant(src, norm_path) or _is_same_or_descendant(dest, norm_path):
                self.moved_dir_src_to_dest.pop(src, None)

    def record_dir_move(self, src_norm: str, dest_norm: str, *, is_staged: bool) -> None:
        """Record live directory move, maintaining handler vs live roots and chained aliases."""
        if src_norm == dest_norm:
            return
        was_deleted = dest_norm in self.deleted_dirs or bool(self._longest_ancestor_match(dest_norm, self.deleted_dirs))
        self.deleted_dirs.discard(dest_norm)
        self.recreated_dirs.discard(dest_norm)
        for d in list(self.deleted_dirs):
            if _is_same_or_descendant(d, dest_norm):
                self.deleted_dirs.discard(d)
        if was_deleted:
            self.recreated_dirs.add(dest_norm)

        dest_match = self._longest_ancestor_match(src_norm, self.moved_dir_dest_to_src)
        if dest_match:
            handler_root = _replace_path_prefix(src_norm, dest_match, self.moved_dir_dest_to_src[dest_match])
        else:
            handler_root = src_norm if is_staged else dest_norm

        if handler_root == dest_norm:
            self.moved_dir_dest_to_src.pop(dest_norm, None)
        else:
            self.moved_dir_dest_to_src[dest_norm] = handler_root

        # Rebase any existing nested source aliases whose keys or targets lie within src_norm's subtree
        for k, v in list(self.moved_dir_src_to_dest.items()):
            k_new = (
                _replace_path_prefix(k, src_norm, dest_norm)
                if (k != src_norm and _is_same_or_descendant(k, src_norm))
                else k
            )
            v_new = (
                _replace_path_prefix(v, src_norm, dest_norm)
                if (v != src_norm and _is_same_or_descendant(v, src_norm))
                else v
            )
            if k_new != k or v_new != v:
                self.moved_dir_src_to_dest.pop(k, None)
                self.moved_dir_src_to_dest[k_new] = v_new

        # Update and collapse source aliases to avoid cycles (e.g. A -> B -> A)
        self.moved_dir_src_to_dest.pop(dest_norm, None)
        self.moved_dir_src_to_dest[src_norm] = dest_norm
        for k, v in list(self.moved_dir_src_to_dest.items()):
            if v == src_norm:
                if k == dest_norm:
                    self.moved_dir_src_to_dest.pop(k, None)
                else:
                    self.moved_dir_src_to_dest[k] = dest_norm

        for d in list(self.deleted_dirs):
            if d != src_norm and _is_same_or_descendant(d, src_norm):
                self.deleted_dirs.discard(d)
                self.deleted_dirs.add(_replace_path_prefix(d, src_norm, dest_norm))

        for d in list(self.recreated_dirs):
            if _is_same_or_descendant(d, src_norm):
                self.recreated_dirs.discard(d)
                self.recreated_dirs.add(_replace_path_prefix(d, src_norm, dest_norm))

    def mark_dir_move_folded(self, dest_norm: str) -> None:
        """Update directory move tracking after a staged move into ``dest_norm`` is folded."""
        self.moved_dir_dest_to_src.pop(dest_norm, None)

    def resolve_startup_path(self, norm_path: str) -> tuple[str, str, bool]:
        """Resolve a synthetic startup candidate to ``(live_path, handler_path, should_suppress)``.

        Coordinates directory moves and deletions that occur during active scans:
        - If ``norm_path`` or an ancestor was deleted, suppression is requested.
        - If an ancestor moved, ``norm_path`` is translated to its ``live_path`` on disk.
        - If the live destination is staged (handler has not received the move event yet),
          the event is delivered using ``handler_path`` so handlers observe a consistent tree.
        """
        del_match = self._longest_ancestor_match(norm_path, self.deleted_dirs)
        live_path, src_match = self.resolve_live_path(norm_path)
        if del_match and (not src_match or len(del_match) >= len(src_match)):
            return (norm_path, norm_path, True)

        if src_match:
            if self._longest_ancestor_match(live_path, self.deleted_dirs):
                return (live_path, live_path, True)
            if norm_path == src_match and (
                live_path in self.seen_created or bool((m := self.staged_moves_by_dest.get(live_path)) and m[4])
            ):
                return (live_path, live_path, True)

        recreated = self.has_recreated_ancestor(norm_path) or self.has_recreated_ancestor(live_path)
        if (norm_path in self.deleted_during_sync or live_path in self.deleted_during_sync) and not recreated:
            return (live_path, live_path, True)

        handler_path = self.resolve_handler_path(live_path)
        return (live_path, handler_path, False)

    def stage_event(
        self,
        event: FileSystemEvent,
        norm_path: str,
        dest_norm: str | None = None,
    ) -> FileSystemEvent:
        """Record a staged live event together with its normalized sync path."""
        setattr(event, "_norm_path", norm_path)  # noqa: B010
        self.staged_live_events.append(event)
        if event.event_type == EVENT_TYPE_CREATED:
            self.staged_created_paths.add(norm_path)
        return event

    def rebuild_staged_created_paths(self) -> None:
        """Rebuild the staged live created paths index from current staged events."""
        self.staged_created_paths = {
            getattr(ev, "_norm_path", "") for ev in self.staged_live_events if ev.event_type == EVENT_TYPE_CREATED
        }

    def unstage_events(self, items: Iterable[FileSystemEvent]) -> None:
        """Remove multiple staged live events in a single O(N) pass, rebuilding index once."""
        item_set = {id(ev) for ev in items}
        if not item_set:
            return
        had_created = False
        kept: list[FileSystemEvent] = []
        for ev in self.staged_live_events:
            if id(ev) in item_set:
                if ev.event_type == EVENT_TYPE_CREATED:
                    had_created = True
            else:
                kept.append(ev)
        self.staged_live_events = kept
        if had_created:
            self.rebuild_staged_created_paths()

    def unstage_event(self, item: FileSystemEvent) -> None:
        """Remove a staged live event record if present, ignoring if already absent."""
        self.unstage_events((item,))

    def finish(self, *, clear_ledger: bool = True) -> list[FileSystemEvent]:
        """Complete startup catch-up tracking and extract any staged live events.

        When ``clear_ledger`` is False (for emitters without a pre-completion backend
        barrier), ``startup_entities`` and ``children_by_parent`` are retained for the
        watch lifetime (until invalidated by deletes/moves) so delayed duplicate
        ``Created`` events can still be suppressed after synchronization completes.
        """
        self.ordered_startup = False
        self.is_sync_complete = True
        self.deleted_during_sync.clear()
        self.deleted_dirs.clear()
        self.recreated_dirs.clear()
        self.seen_created.clear()
        self.staged_moves_by_dest.clear()
        self.moved_dir_dest_to_src.clear()
        self.moved_dir_src_to_dest.clear()
        self.staged_created_paths.clear()
        staged = list(self.staged_live_events)
        self.staged_live_events.clear()
        if clear_ledger or not self.startup_entities:
            self.startup_entities.clear()
            self.children_by_parent.clear()
        else:
            self.children_by_parent.clear()
            for p in self.startup_entities:
                self._link_path_tree(p)
        return staged

    def cancel(self) -> None:
        """Signal cancellation to terminate background sync worker and purge sync state."""
        self.cancel_event.set()
        self.staged_live_events.clear()
        self.staged_created_paths.clear()
        self.staged_moves_by_dest.clear()
        self.moved_dir_dest_to_src.clear()
        self.moved_dir_src_to_dest.clear()
        self.deleted_dirs.clear()
        self.recreated_dirs.clear()
        self.deleted_during_sync.clear()
        self.seen_created.clear()
        self.startup_entities.clear()
        self.children_by_parent.clear()


class BaseObserver(EventDispatcher):
    """Base observer.

    :param emitter_class:
        The class of the emitter to use (e.g., a subclass of :class:`EventEmitter`).
    :type emitter_class:
        ``type[EventEmitter]``
    :param timeout:
        The timeout for the observer to wait on events.
    :type timeout:
        ``Seconds``
    :param kwargs:
        Extra keyword arguments forwarded to every emitter this observer
        constructs, for platform-specific emitter options.
    """

    def __init__(
        self,
        emitter_class: type[EventEmitter],
        *,
        timeout: Seconds = DEFAULT_OBSERVER_TIMEOUT,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self._emitter_class = emitter_class
        self._emitter_kwargs = kwargs
        self._lock = threading.RLock()
        self._watches: set[ObservedWatch] = set()
        self._handlers: defaultdict[ObservedWatch, set[FileSystemEventHandler]] = defaultdict(set)
        self._emitters: set[EventEmitter] = set()
        self._emitter_for_watch: dict[ObservedWatch, EventEmitter] = {}
        self._sync_state: dict[ObservedWatch, _WatchSyncState] = {}
        self._sync_threads: set[threading.Thread] = set()

    def _init_sync_state(self, watch: ObservedWatch, *, root_norm: str | None = None) -> _WatchSyncState:
        """Initializes and registers a new synchronization session state for the watch under lock."""
        with self._lock:
            # Unique identity token isolating this session so stale synthetic events cannot
            # leak into a rescheduled watch at the same path.
            sync_state = _WatchSyncState(
                ordered_startup=watch.ordered_startup,
                session_token=object(),
                follow_symlink=watch.follow_symlink,
                root_norm=root_norm,
            )
            self._sync_state[watch] = sync_state
            return sync_state

    def _complete_sync_state(
        self,
        watch: ObservedWatch,
        *,
        session_token: object | None = None,
        strict_token: bool = False,
        clear_ledger_override: bool | None = None,
    ) -> tuple[list[FileSystemEvent], list[FileSystemEventHandler], object | None]:
        """Mark catch-up tracking complete and extract staged events + active handlers under lock."""
        with self._lock:
            sync_state = self._sync_state.get(watch)
            # strict_token=True requires matching session ownership even if session_token were None;
            # otherwise tokenless SynchronizationComplete markers still complete the active watch.
            if sync_state is None or (
                (strict_token or session_token is not None) and sync_state.session_token is not session_token
            ):
                return ([], [], None)
            if clear_ledger_override is not None:
                clear_ledger = clear_ledger_override
            else:
                emitter = self._emitter_for_watch.get(watch)
                clear_ledger = bool(emitter is not None and getattr(emitter, "supports_sync_barrier", False))
            staged = sync_state.finish(clear_ledger=clear_ledger)
            handlers = list(self._handlers.get(watch, ())) if staged else []
            return (staged, handlers, sync_state.session_token)

    def _start_sync(self, watch: ObservedWatch) -> None:
        """Starts a background thread to stream existing directory contents for startup catch-up."""
        with self._lock:
            sync_state = self._sync_state.get(watch)
            if sync_state is None:
                sync_state = self._init_sync_state(watch)
            elif sync_state.sync_started:
                # schedule() pre-registers state with sync_started=False before start(),
                # so avoid launching a duplicate worker once started.
                return
            sync_state.sync_started = True
            session_token = sync_state.session_token
            emitter = self._emitter_for_watch.get(watch)

            thread = threading.Thread(
                target=self._sync_worker,
                args=(watch, sync_state, session_token, emitter),
                name=f"watchdog.sync.{watch.path}",
                daemon=True,
            )
            self._sync_threads.add(thread)
            thread.start()

    def _sync_worker(
        self,
        watch: ObservedWatch,
        sync_state: _WatchSyncState,
        session_token: object,
        emitter: EventEmitter | None = None,
    ) -> None:
        """Background worker executing startup catch-up streaming and serialized failure reporting."""
        from watchdog.utils.sync import SynchronizationComplete, SynchronizationEngine

        engine = SynchronizationEngine(self.event_queue)
        cancel_event = sync_state.cancel_event
        try:
            engine.stream_startup_catchup(
                watch,
                stop_event=self.stopped_event,
                cancel_event=cancel_event,
                session_token=session_token,
                emitter=emitter,
            )
        except Exception:
            # Discard staged events on cancellation/shutdown; on unexpected failure, enqueue
            # a failure completion marker so the dispatcher flushes staged events and tears
            # down sync state strictly on the dispatcher thread.
            if cancel_event.is_set() or self.stopped_event.is_set():
                return

            # TODO: Revisit startup catch-up exception handling architecture:
            # consider surfacing sync errors to registered error handlers or emitting
            # a synthetic ErrorEvent, rather than only flushing staged events and logging.
            logger.exception("Error during startup catch-up for %s", watch.path)
            if not (cancel_event.is_set() or self.stopped_event.is_set()):
                self.event_queue.put((SynchronizationComplete(watch, session_token=session_token, failed=True), watch))
        finally:
            with self._lock:
                curr_t = threading.current_thread()
                self._sync_threads.discard(curr_t)

    def _add_emitter(self, emitter: EventEmitter) -> None:
        self._emitter_for_watch[emitter.watch] = emitter
        self._emitters.add(emitter)

    def _remove_emitter(self, emitter: EventEmitter) -> None:
        del self._emitter_for_watch[emitter.watch]
        self._emitters.remove(emitter)
        emitter.stop()
        with contextlib.suppress(RuntimeError):
            emitter.join()

    def _clear_emitters(self) -> None:
        for emitter in self._emitters:
            emitter.stop()
        for emitter in self._emitters:
            with contextlib.suppress(RuntimeError):
                emitter.join()
        self._emitters.clear()
        self._emitter_for_watch.clear()

    def _add_handler_for_watch(self, event_handler: FileSystemEventHandler, watch: ObservedWatch) -> None:
        self._handlers[watch].add(event_handler)

    def _remove_handlers_for_watch(self, watch: ObservedWatch) -> None:
        del self._handlers[watch]

    @property
    def emitters(self) -> set[EventEmitter]:
        """Returns event emitter created by this observer."""
        return self._emitters

    def start(self) -> None:
        """Starts the observer thread and all scheduled emitters under synchronization lock.

        Overrides :meth:`watchdog.utils.BaseThread.start` to guarantee atomicity between
        observer startup and concurrent :meth:`schedule` invocations (prevents #1044).
        """
        with self._lock:
            super().start()

    def on_thread_start(self) -> None:
        """Start all scheduled emitters and synchronization threads before dispatching begins."""
        with self._lock:
            for emitter in self._emitters.copy():
                try:
                    emitter.start()
                except Exception:
                    self._remove_emitter(emitter)
                    raise
            for watch in self._watches.copy():
                if watch.emit_existing:
                    self._start_sync(watch)

    def __enter__(self) -> Self:
        """Context manager entry. Starts the observer if not already running."""
        if not self.is_alive():
            self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Context manager exit. Stops the observer and waits for it to finish."""
        if self.is_alive():
            self.stop()
            self.join()

    def schedule(
        self,
        event_handler: FileSystemEventHandler,
        path: str | Path,
        *,
        recursive: bool = False,
        event_filter: list[type[FileSystemEvent]] | None = None,
        follow_symlink: bool = False,
        emit_existing: bool = False,
        ordered_startup: bool = False,
    ) -> ObservedWatch:
        """Schedules watching a path and calls appropriate methods specified
        in the given event handler in response to file system events.

        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param path:
            Directory or file path that will be monitored.
        :type path:
            ``str`` or :class:`pathlib.Path`
        :param recursive:
            ``True`` if events will be emitted for sub-directories
            traversed recursively; ``False`` otherwise.
        :type recursive:
            ``bool``
        :param event_filter:
            Collection of event types to emit, or None for no filtering (default).
        :type event_filter:
            Iterable[:class:`watchdog.events.FileSystemEvent`] | None
        :param follow_symlink:
            ``True`` if symlinks should be followed; ``False`` otherwise.
        :type follow_symlink:
            ``bool``
        :param emit_existing:
            ``True`` if created events should be emitted for existing files
            and directories upon startup; ``False`` otherwise (default).
            When watching a directory, synthetic ``DirCreatedEvent`` and ``FileCreatedEvent``
            instances are emitted for all existing contents. When watching a single file,
            a single synthetic ``FileCreatedEvent`` is emitted for that file alone.
        :type emit_existing:
            ``bool``
        :param ordered_startup:
            ``True`` to buffer overlapping live events during startup catch-up so
            synthetic creations are dispatched before subsequent live events, and
            suppress delayed duplicate live ``Created`` events matching discovered
            startup file identities; ``False`` otherwise (default).
            On :class:`~watchdog.observers.polling.PollingEmitter`, completion waits
            for a synchronous snapshot diff barrier; on asynchronous OS emitters
            (FSEvents, inotify, kqueue, Windows), delayed duplicate creations are
            reconciled against the startup identity ledger. Without a native backend
            barrier, strict causal ordering across delayed multi-step pre-scan
            histories (e.g. Created then Moved before scan completion) is not
            guaranteed. Delayed duplicate suppression fails open when filesystem
            inode numbers are non-positive (such as FAT32 or SMB).
            Only takes effect when ``emit_existing=True``; ignored if ``emit_existing=False``.
            On Linux, chronological birthtime ordering utilizes ``statx(2)`` (Linux >= 4.11
            on ext4/Btrfs/XFS); on older kernels or filesystems without birthtime support,
            ordering falls back gracefully to modification time (``mtime``).
        :type ordered_startup:
            ``bool``
        :return:
            An :class:`ObservedWatch` object instance representing
            a watch.
        """
        # TODO: Candidate flags for future emit_existing expansion:
        # - Custom stat/listdir injection from schedule() for mock/virtual filesystems.
        # - Inode/device tracking (ignore_device) for hard-link and cross-mount deduplication.
        # - Early traversal pruning when DirCreatedEvent is excluded by event_filter.
        with self._lock:
            watch = ObservedWatch(
                path,
                recursive=recursive,
                event_filter=event_filter,
                follow_symlink=follow_symlink,
                emit_existing=emit_existing,
                ordered_startup=ordered_startup,
            )

            if emit_existing and watch not in self._sync_state:
                # Register sync state before starting the emitter so early live events enter staging.
                self._init_sync_state(watch)

            # If we don't have an emitter for this watch already, create it.
            if watch not in self._emitter_for_watch:
                emitter = self._emitter_class(
                    self.event_queue,
                    watch,
                    timeout=self.timeout,
                    event_filter=event_filter,
                    **self._emitter_kwargs,
                )
                if self.is_alive():
                    emitter.start()
                self._add_emitter(emitter)
            if emit_existing and self.is_alive():
                self._start_sync(watch)
            self._add_handler_for_watch(event_handler, watch)
            self._watches.add(watch)
        return watch

    def add_handler_for_watch(self, event_handler: FileSystemEventHandler, watch: ObservedWatch) -> None:
        """Adds a handler for the given watch.

        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param watch:
            The watch to add a handler for.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """
        with self._lock:
            self._add_handler_for_watch(event_handler, watch)

    def remove_handler_for_watch(self, event_handler: FileSystemEventHandler, watch: ObservedWatch) -> None:
        """Removes a handler for the given watch.

        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param watch:
            The watch to remove a handler for.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """
        with self._lock:
            # Use .get() rather than indexing: _handlers is a defaultdict, so
            # indexing it here would resurrect a watch that unschedule() already
            # removed, leaving a permanent empty-set entry behind.
            self._handlers.get(watch, set()).remove(event_handler)

    def unschedule(self, watch: ObservedWatch) -> None:
        """Unschedules a watch.

        :param watch:
            The watch to unschedule.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """
        with self._lock:
            if (sync_state := self._sync_state.pop(watch, None)) is not None:
                # Signal cancellation to terminate background sync worker and discard staged live events
                sync_state.cancel()
            emitter = self._emitter_for_watch[watch]
            del self._handlers[watch]
            self._remove_emitter(emitter)
            self._watches.remove(watch)

    def unschedule_all(self) -> None:
        """Unschedules all watches and detaches all associated event handlers."""
        with self._lock:
            for sync_state in self._sync_state.values():
                # Signal cancellation and purge staged live events for all active sessions
                sync_state.cancel()
            self._sync_state.clear()
            self._handlers.clear()
            self._clear_emitters()
            self._watches.clear()

    def on_thread_stop(self) -> None:
        self.unschedule_all()
        with self._lock:
            sync_threads = list(self._sync_threads)
        for t in sync_threads:
            with contextlib.suppress(RuntimeError):
                t.join(timeout=self.timeout)

    def _process_sync_complete(self, watch: ObservedWatch, complete_event: Any | None = None) -> None:
        """Processes a startup catch-up completion or failure marker cleanly on the dispatcher thread."""
        complete_token = getattr(complete_event, "session_token", None) if complete_event is not None else None
        is_failed = bool(getattr(complete_event, "failed", False)) if complete_event is not None else False
        staged, handlers, session_token = self._complete_sync_state(
            watch,
            session_token=complete_token,
            strict_token=is_failed,
            clear_ledger_override=True if is_failed else None,
        )
        try:
            for staged_event in staged:
                if hasattr(staged_event, "_norm_path"):
                    with contextlib.suppress(AttributeError):
                        delattr(staged_event, "_norm_path")
                self._dispatch_event(staged_event, watch, handlers=handlers, session_token=session_token)
        finally:
            if is_failed and session_token is not None:
                # Tear down failed session state only after staged events flush, preserving
                # session_token validation during dispatch against concurrent reschedules.
                with self._lock:
                    st = self._sync_state.get(watch)
                    if st is not None and st.session_token is session_token:
                        st.cancel_event.set()
                        self._sync_state.pop(watch, None)

    @staticmethod
    def _normalize_sync_path(path: bytes | str, *, follow_symlink: bool) -> str:
        """Normalizes a filesystem path for consistent event deduplication during synchronization.

        Handles platform-specific differences so that events from OS kernel notification
        backends (e.g. FSEvents, inotify) can be compared reliably against paths discovered
        by the startup catch-up scanner:

        - Decodes ``bytes`` to ``str`` using :func:`os.fsdecode`.
        - When ``follow_symlink`` is ``True``, resolves all symlinks via :func:`os.path.realpath`.
        - When ``follow_symlink`` is ``False``, resolves the parent directory (resolving system
          alias links such as macOS ``/var`` -> ``/private/var``) while preserving the symlink
          status of the leaf basename itself.
        - Normalizes filesystem case sensitivity and slash formatting via :func:`os.path.normcase`
          (e.g., Windows case-insensitivity and backslashes).

        :param path: The filesystem path string or bytes to normalize.
        :param follow_symlink: Whether symlinks should be fully resolved.
        :return: Canonical normalized path string suitable for set membership checks.
        """
        decoded = os.fsdecode(path) if isinstance(path, bytes) else path
        if follow_symlink:
            return os.path.normcase(os.path.realpath(decoded))
        abs_path = os.path.abspath(decoded)
        dirname, basename = os.path.split(abs_path)
        if basename:
            return os.path.normcase(os.path.join(os.path.realpath(dirname), basename))
        return os.path.normcase(os.path.realpath(abs_path))

    @staticmethod
    def _get_path_file_id(path: bytes | str, *, follow_symlink: bool) -> tuple[int, int] | None:
        """Returns (st_dev, st_ino) identifying the underlying filesystem entity, or None if unavailable."""
        decoded = os.fsdecode(path) if isinstance(path, bytes) else path
        try:
            st = os.stat(decoded) if follow_symlink else os.lstat(decoded)
            return (int(st.st_dev), int(st.st_ino))
        except OSError:
            return None

    @staticmethod
    def _is_same_move_target(
        dest_btime: int | None,
        dest_file_id: tuple[int, int] | None,
        current_btime: int | None,
        current_file_id: tuple[int, int] | None,
    ) -> bool:
        """Return True when current metadata matches or cannot be distinguished from the staged move destination (#992).

        Ignores non-positive ``st_ino`` values (e.g., FAT32/SMB placeholder inodes) and compares valid
        inodes or birthtimes. Returns True when neither metadata source was queried (e.g., mocked paths).
        """
        valid_inodes = (
            dest_file_id is not None and current_file_id is not None and dest_file_id[1] > 0 and current_file_id[1] > 0
        )
        has_birthtimes = dest_btime is not None and current_btime is not None
        diff_identity = (valid_inodes and dest_file_id != current_file_id) or (
            has_birthtimes and dest_btime != current_btime
        )
        if diff_identity:
            return False
        if valid_inodes or has_birthtimes:
            return True
        return all(v is None for v in (dest_file_id, current_file_id, dest_btime, current_btime))

    @staticmethod
    def _is_same_startup_entity(
        recorded_identity: tuple[tuple[int, int] | None, int | None],
        live_file_id: tuple[int, int] | None,
        live_btime: int | None,
    ) -> bool:
        """Return True only when live metadata affirmatively matches a startup entity identity.

        Fails open (returns False) if the file is absent on disk, lacks positive
        inode numbers (e.g. FAT32/SMB placeholder inodes), or differs in file ID
        or birthtime, so legitimate new creations are never suppressed.
        """
        rec_file_id, rec_btime = recorded_identity
        valid_inodes = (
            rec_file_id is not None and live_file_id is not None and rec_file_id[1] > 0 and live_file_id[1] > 0
        )
        if not valid_inodes or rec_file_id != live_file_id:
            return False
        return not (rec_btime is not None and live_btime is not None and rec_btime != live_btime)

    @staticmethod
    def _fold_superseded_move(
        sync_state: _WatchSyncState,
        norm_path: str,
        move_events: list[FileSystemEvent],
    ) -> bool:
        """Fold staged move chain targeting ``norm_path`` into synthetic ``Created(norm_path)``.

        Returns False (preserving the move chain) if a live move-out from ``norm_path``
        preceded ``move_events[-1]``, since dropping the incoming move would leave
        ``norm_path`` absent after the move-out. When folding, also removes earlier
        staged deletes/creates for ``norm_path`` superseded by the incoming move.
        """
        staged = sync_state.staged_live_events
        last_move = move_events[-1]
        last_move_idx = next((idx for idx, ev in enumerate(staged) if ev is last_move), -1)
        # Keep the move chain if norm_path was moved out before this incoming move landed on it.
        if last_move_idx >= 0 and any(
            ev.event_type == EVENT_TYPE_MOVED and getattr(ev, "_norm_path", None) == norm_path
            for ev in staged[:last_move_idx]
        ):
            return False

        move_ids = {id(m) for m in move_events}
        kept: list[FileSystemEvent] = []
        for idx, ev in enumerate(staged):
            if id(ev) in move_ids:
                continue
            # Drop pre-move deletes/creates at norm_path (e.g. Delete(A) -> Move(B, A)) now
            # superseded by synthetic Created(A), while preserving any post-move events.
            if (
                last_move_idx >= 0
                and idx < last_move_idx
                and getattr(ev, "_norm_path", None) == norm_path
                and ev.event_type in (EVENT_TYPE_DELETED, EVENT_TYPE_CREATED)
            ):
                continue
            kept.append(ev)
        sync_state.staged_live_events = kept
        sync_state.rebuild_staged_created_paths()
        return True

    @staticmethod
    def _prune_pre_removal_created(sync_state: _WatchSyncState, drop_created: set[str]) -> None:
        """Drop staged live Created events before each path's first removal (Deleted or Moved-out).

        Once a path is deleted or moved away, later staged Created events represent a new
        post-removal creation (recreation) and must be preserved.
        """
        if not (sync_state.staged_created_paths and (drop_created & sync_state.staged_created_paths)):
            return
        removed_paths: set[str] = set()
        kept: list[FileSystemEvent] = []
        for ev in sync_state.staged_live_events:
            ev_norm = getattr(ev, "_norm_path", None)
            if not ev_norm:
                kept.append(ev)
                continue
            if ev.event_type in (EVENT_TYPE_DELETED, EVENT_TYPE_MOVED):
                for p in drop_created:
                    if _is_same_or_descendant(p, ev_norm):
                        removed_paths.add(p)
            elif ev.event_type == EVENT_TYPE_CREATED and ev_norm in drop_created and ev_norm not in removed_paths:
                continue
            kept.append(ev)
        sync_state.staged_live_events = kept
        sync_state.rebuild_staged_created_paths()

    @staticmethod
    def _rewrite_synthetic_created(
        event: FileSystemEvent,
        *,
        watch_path: bytes | str | None,
        root_norm: str | None,
        handler_path: str,
    ) -> FileSystemEvent:
        """Reconstruct a synthetic Created event using the handler's active view of the path prefix."""
        rewritten_src: bytes | str
        if watch_path is not None and root_norm is not None and _is_same_or_descendant(handler_path, root_norm):
            if handler_path == root_norm:
                rewritten_src = watch_path
            else:
                rel = os.path.relpath(handler_path, root_norm)
                if isinstance(watch_path, bytes):
                    rewritten_src = os.path.join(watch_path, os.fsencode(rel))
                else:
                    rewritten_src = os.path.join(watch_path, rel)
        elif isinstance(watch_path, bytes):
            rewritten_src = os.fsencode(handler_path)
        else:
            rewritten_src = handler_path

        ev_cls = DirCreatedEvent if event.is_directory else FileCreatedEvent
        rewritten = ev_cls(rewritten_src, is_synthetic=True)
        if (tok := getattr(event, "session_token", None)) is not None:
            object.__setattr__(rewritten, "session_token", tok)
        if (wt := getattr(event, "watch_token", None)) is not None:
            object.__setattr__(rewritten, "watch_token", wt)
        return rewritten

    def _should_dispatch_startup_event(
        self,
        event: FileSystemEvent,
        sync_state: _WatchSyncState,
        norm_path: str,
        *,
        watch_path: bytes | str | None = None,
        current_btime: int | None = None,
        current_file_id: tuple[int, int] | None = None,
    ) -> FileSystemEvent | None:
        """Handles synthetic events emitted by the startup catch-up worker.

        Returns the (possibly rewritten) synthetic event to dispatch, or ``None``
        if suppressed (e.g. duplicate, deleted during sync, or handled via staged move).
        """
        if event.event_type != EVENT_TYPE_CREATED:
            return event

        live_path, handler_path, should_suppress = sync_state.resolve_startup_path(norm_path)
        if should_suppress or live_path in sync_state.seen_created:
            return None

        # When a directory was deleted and recreated during sync, descendants that no longer exist
        # on disk (e.g. belonged to the retired directory incarnation) are suppressed. If identity
        # cannot be established (e.g. disk unlinked or stat OSError), safely drop the stale synthetic candidate.
        if current_file_id is None and sync_state.is_recreated_path(norm_path):
            return None

        if sync_state.ordered_startup:
            if (
                live_path != norm_path
                and norm_path in sync_state.moved_dir_src_to_dest
                and live_path in sync_state.staged_moves_by_dest
                and current_file_id is None
            ):
                return None

            drop_created = {norm_path, live_path, handler_path}
            for src_alias, target_live in sync_state.moved_dir_src_to_dest.items():
                if live_path != target_live and _is_same_or_descendant(live_path, target_live):
                    drop_created.add(_replace_path_prefix(live_path, target_live, src_alias))

            move_info = sync_state.staged_moves_by_dest.get(live_path)
            if move_info is not None:
                move_root, move_events, dest_btime, dest_file_id, src_seen, staged_sources = move_info
                if self._is_same_move_target(dest_btime, dest_file_id, current_btime, current_file_id):
                    if src_seen or move_root in sync_state.seen_created:
                        # Scanner already visited src; preserve staged move and suppress Created(dest).
                        sync_state.mark_seen(live_path)
                        sync_state.staged_moves_by_dest.pop(live_path, None)
                        return None
                    # Moved before scanner reached src; emit Created(dest) and fold redundant staged moves/creates.
                    sync_state.staged_moves_by_dest.pop(live_path, None)
                    if self._fold_superseded_move(sync_state, live_path, move_events):
                        drop_created |= staged_sources
                        if move_events[-1].is_directory:
                            sync_state.mark_dir_move_folded(live_path)
                            if handler_path != live_path:
                                handler_path = live_path

            # Drop staged live creations at this discovered path (or superseded move sources) before first removal.
            self._prune_pre_removal_created(sync_state, drop_created)

        sync_state.mark_seen(live_path)
        sync_state.record_startup_entity(live_path, (current_file_id, current_btime))
        if handler_path != norm_path:
            return self._rewrite_synthetic_created(
                event,
                watch_path=watch_path,
                root_norm=sync_state.root_norm,
                handler_path=handler_path,
            )
        return event

    def _should_dispatch_live_event(
        self,
        event: FileSystemEvent,
        sync_state: _WatchSyncState,
        norm_path: str,
        *,
        current_btime: int | None = None,
        current_file_id: tuple[int, int] | None = None,
        dest_norm: str | None = None,
        dest_btime: int | None = None,
        dest_file_id: tuple[int, int] | None = None,
        follow_symlink: bool,
    ) -> bool:
        """Handles live kernel events arriving from emitter threads while startup sync is active."""
        ev_type = event.event_type
        if ev_type == EVENT_TYPE_CREATED:
            if (rec_ident := sync_state.startup_entities.get(norm_path)) is not None:
                if self._is_same_startup_entity(rec_ident, current_file_id, current_btime):
                    return False
                sync_state.seen_created.discard(norm_path)
                sync_state.remove_startup_entity(norm_path)
            if event.is_directory:
                sync_state.record_dir_create(norm_path)
                if norm_path not in sync_state.deleted_dirs:
                    sync_state.deleted_during_sync.discard(norm_path)
            else:
                sync_state.deleted_during_sync.discard(norm_path)
            if not sync_state.ordered_startup:
                if norm_path in sync_state.seen_created:
                    return False
                sync_state.mark_seen(norm_path)
                return True
        elif ev_type == EVENT_TYPE_DELETED:
            # Record deletions for both the deleted path and any indexed subtree descendants so late
            # partial scanner discoveries skip them and ledger identities are invalidated immediately.
            sync_state.invalidate_subtree(norm_path, include_staged_moves=sync_state.ordered_startup)
            if event.is_directory:
                sync_state.record_dir_delete(norm_path)
        elif ev_type == EVENT_TYPE_MOVED:
            src_seen = norm_path in sync_state.seen_created
            sync_state.seen_created.discard(norm_path)
            if dest_norm is None and event.dest_path:
                dest_norm = self._normalize_sync_path(event.dest_path, follow_symlink=follow_symlink)

            if not sync_state.ordered_startup:
                # Under unordered startup (emit_existing=True, ordered_startup=False):
                # The move is dispatched immediately. Translate subtree paths/identities and mark
                # source paths deleted so late scanner discovery does not duplicate Created events.
                if dest_norm:
                    sync_state.translate_subtree(norm_path, dest_norm, include_root_in_seen=True)
                    if event.is_directory:
                        sync_state.record_dir_move(norm_path, dest_norm, is_staged=False)
                    sync_state.mark_seen(dest_norm)
                else:
                    sync_state.invalidate_subtree(norm_path)
                    if event.is_directory:
                        sync_state.record_dir_delete(norm_path)
                return True

            # Under ordered startup (ordered_startup=True):
            if dest_norm:
                sync_state.deleted_during_sync.discard(dest_norm)

                # 1. Check if an earlier staged move targeted this exact destination path (Overwrite/Replacement):
                if (overwritten_move := sync_state.staged_moves_by_dest.pop(dest_norm, None)) is not None:
                    orig_src, overwritten_events, _btime, _fid, prev_src_was_seen = overwritten_move[:5]
                    # The prior file at this destination was unlinked/overwritten by the incoming move.
                    if not prev_src_was_seen and orig_src not in sync_state.seen_created:
                        # If the prior move's source was never announced to handlers (neither staged-seen nor
                        # dispatched by startup catch-up), the move is obsolete and can be discarded.
                        sync_state.unstage_events(overwritten_events)
                    else:
                        # If the prior source was announced (e.g. Created(A) was dispatched), preserve the move
                        # history (Moved(A, B)) and record destination replacement (Deleted(B)).
                        # Also mark src_seen=True: handlers already know about files leading into destination B,
                        # so the startup scanner must not emit a duplicate synthetic Created(B) later.
                        src_seen = True
                        del_cls = DirDeletedEvent if event.is_directory else FileDeletedEvent
                        sync_state.stage_event(del_cls(event.dest_path), dest_norm)

                # 2. Check if this move continues a staged move chain (e.g. A -> B -> C):
                chain_move = sync_state.staged_moves_by_dest.pop(norm_path, None)
                if chain_move is not None:
                    orig_src, prev_events, _, _, orig_src_seen, prev_sources = chain_move
                    if orig_src == dest_norm and not orig_src_seen:
                        # Ping-pong rename (A -> B -> A) before scanner visited it: drop intermediate moves
                        sync_state.unstage_events(prev_events)
                        sync_state.translate_subtree(norm_path, dest_norm, include_root_in_seen=False)
                        if event.is_directory:
                            sync_state.moved_dir_dest_to_src.pop(norm_path, None)
                            sync_state.moved_dir_src_to_dest.pop(dest_norm, None)
                            sync_state.deleted_dirs.discard(dest_norm)
                        return False
                    move_root = orig_src
                    move_events = [*prev_events, event]
                    move_src_seen = src_seen or orig_src_seen
                    move_sources = prev_sources | {norm_path}
                else:
                    move_root = norm_path
                    move_events = [event]
                    move_src_seen = src_seen
                    move_sources = {norm_path}

                # Translate any already-scanned/indexed descendant paths (and ledger identities)
                # from src subtree to dest subtree while preserving staged_moves_by_dest ownership of dest_norm.
                sync_state.translate_subtree(norm_path, dest_norm, include_root_in_seen=False)
                if event.is_directory:
                    sync_state.record_dir_move(norm_path, dest_norm, is_staged=True)

                src_str = os.fsdecode(event.src_path) if isinstance(event.src_path, bytes) else event.src_path
                raw_src = os.path.normcase(os.path.abspath(src_str))
                # Record move reconciliation state for this destination:
                # - move_root: initial origin path in chains (A in A -> B -> C) to detect ping-pong renames.
                # - move_src_seen: True if handlers saw Created at the source/root/overwritten dest,
                #   causing startup catch-up to suppress duplicate Created(dest).
                # - move_sources | {raw_src}: normalized (norm_path) and abspath-normalized (raw_src) source paths
                #   whose pre-removal staged creations can be pruned if the destination is discovered first.
                sync_state.staged_moves_by_dest[dest_norm] = (
                    move_root,
                    move_events,
                    dest_btime,
                    dest_file_id,
                    move_src_seen,
                    move_sources | {raw_src},
                )
            else:
                sync_state.invalidate_subtree(norm_path, include_staged_moves=True)
                if event.is_directory:
                    sync_state.record_dir_delete(norm_path)

        if sync_state.ordered_startup:
            sync_state.stage_event(event, norm_path, dest_norm)
            return False

        return True

    def _reconcile_post_sync_event(
        self,
        event: FileSystemEvent,
        sync_state: _WatchSyncState,
        norm_path: str,
        *,
        dest_norm: str | None = None,
        current_btime: int | None = None,
        current_file_id: tuple[int, int] | None = None,
    ) -> bool:
        """Reconcile post-sync live events against retained startup entity ledger entries."""
        if getattr(event, "is_synthetic", False) and getattr(event, "session_token", None) is not None:
            return False
        if not sync_state.has_startup_ledger():
            return True

        ev_type = event.event_type
        if ev_type == EVENT_TYPE_CREATED:
            if (rec_ident := sync_state.startup_entities.get(norm_path)) is not None:
                if self._is_same_startup_entity(rec_ident, current_file_id, current_btime):
                    return False
                sync_state.seen_created.discard(norm_path)
                sync_state.remove_startup_entity(norm_path)
        elif ev_type == EVENT_TYPE_DELETED:
            sync_state.invalidate_subtree(norm_path)
        elif ev_type == EVENT_TYPE_MOVED:
            if dest_norm:
                sync_state.translate_subtree(norm_path, dest_norm)
            else:
                sync_state.invalidate_subtree(norm_path)
        return True

    def _resolve_sync_event(
        self,
        event: FileSystemEvent,
        sync_state: _WatchSyncState,
        *,
        watch_path: bytes | str | None = None,
        norm_path: str | None = None,
        dest_norm: str | None = None,
        current_btime: int | None = None,
        current_file_id: tuple[int, int] | None = None,
        dest_btime: int | None = None,
        dest_file_id: tuple[int, int] | None = None,
    ) -> FileSystemEvent | None:
        """Filters, deduplicates, and stages events arriving during startup catch-up.

        Returns the :class:`FileSystemEvent` to dispatch (possibly path-rewritten),
        or ``None`` if the event was suppressed (duplicate/stale) or staged.
        """
        follow_symlink = sync_state.follow_symlink
        if sync_state.is_sync_complete:
            if getattr(event, "is_synthetic", False) and getattr(event, "session_token", None) is not None:
                return None
            if not sync_state.has_startup_ledger() or event.event_type not in _STRUCTURAL_EVENT_TYPES:
                return event
            if norm_path is None:
                norm_path = self._normalize_sync_path(event.src_path, follow_symlink=follow_symlink)
            if dest_norm is None and getattr(event, "dest_path", None):
                dest_norm = self._normalize_sync_path(event.dest_path, follow_symlink=follow_symlink)
            should_dispatch = self._reconcile_post_sync_event(
                event,
                sync_state,
                norm_path,
                dest_norm=dest_norm,
                current_btime=current_btime,
                current_file_id=current_file_id,
            )
            return event if should_dispatch else None

        # Stale synthetic event from a different or cancelled session
        if getattr(event, "is_synthetic", False):
            event_token = getattr(event, "session_token", None)
            if event_token is not None and event_token is not sync_state.session_token:
                return None

        if norm_path is None:
            norm_path = self._normalize_sync_path(event.src_path, follow_symlink=follow_symlink)
        is_startup_sync = getattr(event, "session_token", None) is sync_state.session_token

        if is_startup_sync:
            return self._should_dispatch_startup_event(
                event,
                sync_state,
                norm_path,
                watch_path=watch_path,
                current_btime=current_btime,
                current_file_id=current_file_id,
            )
        should_dispatch = self._should_dispatch_live_event(
            event,
            sync_state,
            norm_path,
            current_btime=current_btime,
            current_file_id=current_file_id,
            dest_norm=dest_norm,
            dest_btime=dest_btime,
            dest_file_id=dest_file_id,
            follow_symlink=follow_symlink,
        )
        return event if should_dispatch else None

    def _should_dispatch_sync_event(
        self,
        event: FileSystemEvent,
        sync_state: _WatchSyncState,
        *,
        norm_path: str | None = None,
        dest_norm: str | None = None,
        current_btime: int | None = None,
        current_file_id: tuple[int, int] | None = None,
        dest_btime: int | None = None,
        dest_file_id: tuple[int, int] | None = None,
    ) -> bool:
        """Filters, deduplicates, and stages events arriving during startup catch-up.

        Returns ``True`` if the event should be dispatched immediately; ``False``
        if it was suppressed (duplicate/stale) or staged.
        """
        return (
            self._resolve_sync_event(
                event,
                sync_state,
                norm_path=norm_path,
                dest_norm=dest_norm,
                current_btime=current_btime,
                current_file_id=current_file_id,
                dest_btime=dest_btime,
                dest_file_id=dest_file_id,
            )
            is not None
        )

    def dispatch_events(self, event_queue: EventQueue) -> None:
        entry = event_queue.get(block=True)
        if entry is EventDispatcher.stop_event:
            event_queue.task_done()
            return

        event, watch = entry

        # Handle completion marker for startup catch-up / sync batches
        from watchdog.utils.sync import SynchronizationComplete

        if isinstance(event, SynchronizationComplete):
            self._process_sync_complete(watch, event)
            event_queue.task_done()
            return

        # Step 1: Quick initial check under self._lock to inspect session state.
        # Normal live events when emit_existing=False (sync_state is None), non-structural events
        # post-sync, and post-sync events with an empty ledger take the lock-free direct fast path.
        with self._lock:
            active_emitter = self._emitter_for_watch.get(watch)
            if active_emitter is not None:
                expected_watch_token = getattr(active_emitter.watch, "watch_token", None)
                if getattr(watch, "watch_token", None) != expected_watch_token:
                    event_queue.task_done()
                    return
                ev_watch_token = getattr(event, "watch_token", None)
                if ev_watch_token is not None and ev_watch_token != expected_watch_token:
                    event_queue.task_done()
                    return

            sync_state = self._sync_state.get(watch)
            ev_session_token = getattr(event, "session_token", None)
            is_synthetic = getattr(event, "is_synthetic", False)

            if sync_state is None:
                if is_synthetic and ev_session_token is not None:
                    event_queue.task_done()
                    return
                handlers = list(self._handlers.get(watch, ()))
                should_dispatch_direct = True
            elif sync_state.is_sync_complete:
                if is_synthetic and ev_session_token is not None:
                    event_queue.task_done()
                    return
                if not sync_state.has_startup_ledger() or event.event_type not in _STRUCTURAL_EVENT_TYPES:
                    handlers = list(self._handlers.get(watch, ()))
                    should_dispatch_direct = True
                else:
                    should_dispatch_direct = False
                    follow_symlink = sync_state.follow_symlink
                    ordered_startup = False
                    session_token = sync_state.session_token
                    need_root_norm = sync_state.root_norm is None
                    has_recreated = False
            else:
                if is_synthetic and ev_session_token is not None and ev_session_token is not sync_state.session_token:
                    event_queue.task_done()
                    return
                should_dispatch_direct = False
                # Capture synchronization attributes needed for disk I/O while holding the lock.
                follow_symlink = sync_state.follow_symlink
                ordered_startup = sync_state.ordered_startup
                session_token = sync_state.session_token
                need_root_norm = sync_state.root_norm is None
                has_recreated = bool(sync_state.recreated_dirs)

        if should_dispatch_direct:
            # Dispatch event handlers outside self._lock to avoid blocking concurrent schedule()/unschedule()
            self._dispatch_event(event, watch, handlers=handlers, session_token=None)
            event_queue.task_done()
            return

        # Step 2: Perform all filesystem metadata queries (I/O) OUTSIDE self._lock.
        # Resolving realpaths, stat, and birthtime / statx calls can incur blocking disk
        # or network filesystem latency. Running them lock-free prevents blocking concurrent
        # calls to schedule(), unschedule(), or stop().
        root_norm = self._normalize_sync_path(watch.path, follow_symlink=follow_symlink) if need_root_norm else None
        norm_src = self._normalize_sync_path(event.src_path, follow_symlink=follow_symlink)
        norm_dest = (
            self._normalize_sync_path(event.dest_path, follow_symlink=follow_symlink)
            if getattr(event, "dest_path", None)
            else None
        )
        is_startup = ev_session_token is session_token
        ev_type = event.event_type
        current_btime = None
        current_file_id = None
        dest_btime = None
        dest_file_id = None

        if is_startup and ev_type == EVENT_TYPE_CREATED:
            needs_disk_verify = False
            stat_path: str | bytes = event.src_path
            with self._lock:
                curr = self._sync_state.get(watch)
                if curr is not None and curr.session_token is session_token:
                    if has_recreated:
                        needs_disk_verify = curr.is_recreated_path(norm_src)
                    live_norm, _ = curr.resolve_live_path(norm_src)
                    if live_norm != norm_src:
                        stat_path = os.fsencode(live_norm) if isinstance(event.src_path, bytes) else live_norm

            # Reuse scanner-captured identity when attached and not in a recreated directory.
            cached_ident = getattr(event, "_sync_identity", None)
            if cached_ident is not None and not needs_disk_verify:
                current_file_id, current_btime = cached_ident
            else:
                current_btime = get_path_birthtime_ns(stat_path, follow_symlinks=follow_symlink)
                current_file_id = self._get_path_file_id(stat_path, follow_symlink=follow_symlink)
        elif not is_startup:
            if ordered_startup and ev_type == EVENT_TYPE_MOVED and event.dest_path:
                dest_btime = get_path_birthtime_ns(event.dest_path, follow_symlinks=follow_symlink)
                dest_file_id = self._get_path_file_id(event.dest_path, follow_symlink=follow_symlink)
            elif ev_type == EVENT_TYPE_CREATED:
                # Only stat live Created events when norm_src actually matches a startup ledger entry.
                with self._lock:
                    curr = self._sync_state.get(watch)
                    needs_identity = (
                        curr is not None and curr.session_token is session_token and norm_src in curr.startup_entities
                    )
                if needs_identity:
                    current_btime = get_path_birthtime_ns(event.src_path, follow_symlinks=follow_symlink)
                    current_file_id = self._get_path_file_id(event.src_path, follow_symlink=follow_symlink)

        # Step 3: Re-acquire self._lock for O(1)/O(subtree) in-memory transition and handler snapshot.
        # We must re-verify that the watch and session token did not expire or change (e.g., via
        # unschedule or stop) while disk I/O was performed outside the lock.
        with self._lock:
            sync_state = self._sync_state.get(watch)
            if sync_state is None or sync_state.session_token is not session_token:
                # Watch was unscheduled, stopped, or restarted while I/O ran outside the lock; safely drop.
                event_queue.task_done()
                return
            if sync_state.root_norm is None and root_norm is not None:
                sync_state.root_norm = root_norm

            # Evaluate reconciliation rules (pure in-memory filtering / staging).
            resolved_event = self._resolve_sync_event(
                event,
                sync_state,
                watch_path=watch.path,
                norm_path=norm_src,
                dest_norm=norm_dest,
                current_btime=current_btime,
                current_file_id=current_file_id,
                dest_btime=dest_btime,
                dest_file_id=dest_file_id,
            )
            if resolved_event is None:
                event_queue.task_done()
                return

            # Snapshot active handlers under lock before dispatching outside the lock.
            handlers = list(self._handlers.get(watch, ()))
            event_token = session_token if getattr(resolved_event, "is_synthetic", False) else None

        # Step 4: Dispatch event to handlers OUTSIDE self._lock.
        # Handlers execute user code and may call schedule(), unschedule(), or stop(), so they
        # must never be invoked while holding self._lock to prevent deadlocks.
        self._dispatch_event(resolved_event, watch, handlers=handlers, session_token=event_token)
        event_queue.task_done()

    def _dispatch_event(
        self,
        event: FileSystemEvent,
        watch: ObservedWatch,
        handlers: list[FileSystemEventHandler] | None = None,
        session_token: object | None = None,
    ) -> None:
        """Dispatches an event to the handlers registered for a watch.

        :param event: The filesystem event to dispatch.
        :param watch: The watch context associated with the event.
        :param handlers: Optional pre-captured snapshot of handlers active when
            the event was dequeued or un-staged. If omitted, active handlers are
            queried dynamically under ``self._lock``.
        :param session_token: Optional originating session token. If provided,
            dispatch validates that the originating session is still current,
            preventing stale events from reaching a reused handler instance after
            an unschedule/reschedule cycle.
        """
        if watch.event_filter is not None and not any(isinstance(event, cls) for cls in watch.event_filter):
            return

        if watch.is_file:
            target = watch.resolved_path
            src_path = (
                os.path.realpath(os.path.abspath(event.src_path))
                if watch.follow_symlink
                else os.path.abspath(event.src_path)
            )
            dest_path = None
            if isinstance(event, FileSystemMovedEvent) and event.dest_path:
                dest_path = (
                    os.path.realpath(os.path.abspath(event.dest_path))
                    if watch.follow_symlink
                    else os.path.abspath(event.dest_path)
                )
            if src_path != target and dest_path != target:
                return

        # To allow unschedule/stop and safe removal of event handlers
        # within event handlers itself, check if the handler is still
        # registered before dispatching.
        # Use .get() rather than indexing: _handlers is a defaultdict, so
        # indexing it here would resurrect a watch that unschedule() removed
        # but whose events were already queued.
        # Handlers are dispatched without holding self._lock to avoid blocking
        # concurrent calls to schedule(), unschedule(), or stop().
        if handlers is None:
            with self._lock:
                handlers = list(self._handlers.get(watch, ()))

        for handler in handlers:
            with self._lock:
                if session_token is not None:
                    curr_sync = self._sync_state.get(watch)
                    # If this watch's session was cancelled, unscheduled, or replaced,
                    # drop the event so it never reaches the handler in a new session.
                    if curr_sync is None or curr_sync.session_token is not session_token:
                        continue
                active_emitter = self._emitter_for_watch.get(watch)
                if active_emitter is not None:
                    expected_watch_token = getattr(active_emitter.watch, "watch_token", None)
                    if getattr(watch, "watch_token", None) != expected_watch_token:
                        continue
                    ev_watch_token = getattr(event, "watch_token", None)
                    if ev_watch_token is not None and ev_watch_token != expected_watch_token:
                        continue
                is_active = handler in self._handlers.get(watch, ())
            if is_active:
                event.watch_path = watch.path
                handler.dispatch(event)
