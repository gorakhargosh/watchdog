""":module: watchdog.utils.sync
:synopsis: Synchronizes filesystem state with kernel event streams for startup catch-up.
:author: Prateek Dagar (prateek-dagar)
"""

from __future__ import annotations

import contextlib
import heapq
import os
import stat
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
)
from watchdog.observers.api import SnapshotStatus
from watchdog.utils import is_ignorable_fs_error
from watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff
from watchdog.utils.statx import get_path_birthtime_ns, get_statx_birthtime_ns  # noqa: F401

if TYPE_CHECKING:
    import threading
    from collections.abc import Callable, Generator, Iterator

    from watchdog.observers.api import EventQueue, ObservedWatch


class SynchronizationComplete:
    """Marker placed into the event queue to mark completion or failure of a synchronization catch-up batch.

    :param watch: The watch for which synchronization has completed.
    :type watch: :class:`watchdog.observers.api.ObservedWatch`
    :param session_token: Optional unique session token identifying the synchronization session.
    :type session_token: object | None
    :param failed: ``True`` if catch-up terminated with an error and must tear down sync state.
    :type failed: bool
    """

    def __init__(
        self,
        watch: ObservedWatch,
        session_token: object | None = None,
        *,
        failed: bool = False,
    ) -> None:
        self.watch = watch
        self.session_token = session_token
        self.failed = failed

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SynchronizationComplete):
            return NotImplemented
        if self.failed != other.failed:
            return False
        if self.session_token is not None or other.session_token is not None:
            return self.watch == other.watch and self.session_token == other.session_token
        return self.watch == other.watch

    def __hash__(self) -> int:
        if self.session_token is not None:
            return hash((self.watch, self.session_token, self.failed))
        return hash((self.watch, self.failed))

    def __repr__(self) -> str:
        failed_str = ", failed=True" if self.failed else ""
        return f"<SynchronizationComplete: watch={self.watch!r}{failed_str}>"


def _is_cancelled(
    stop_event: threading.Event | None,
    cancel_event: threading.Event | None,
) -> bool:
    """Check both observer shutdown (stop_event) and single-watch unscheduling (cancel_event)
    to abort traversal cooperatively on large directory trees without blocking thread joins or shutdown.
    """
    return (stop_event is not None and stop_event.is_set()) or (cancel_event is not None and cancel_event.is_set())


def _passes_event_filter(event: FileSystemEvent, watch: ObservedWatch) -> bool:
    """Check if the filesystem event matches the watch's event filter."""
    return watch.event_filter is None or any(isinstance(event, cls) for cls in watch.event_filter)


def _iter_dir_children(
    dir_path: str,
    listdir_func: Callable[[str | None], Iterator[os.DirEntry]],
    effective_stat: Callable[[str], os.stat_result],
    *,
    follow_symlink: bool,
) -> Generator[tuple[str, os.stat_result, bool], None, None]:
    """Yields accessible child entries within a directory as ``(child_path, stat_result, is_dir)``.

    Scans the given directory path using ``listdir_func``, queries metadata using
    ``effective_stat``, and determines whether each entry qualifies as a traversable
    directory based on symlink traversal semantics.

    :param dir_path:
        Absolute or relative path to the directory whose immediate children should be read.
    :param listdir_func:
        Callable returning directory entries (typically :func:`os.scandir`).
    :param effective_stat:
        Callable used to inspect entry metadata (typically :func:`os.stat` when
        ``follow_symlink=True`` or :func:`os.lstat` when ``follow_symlink=False``).
    :param follow_symlink:
        ``True`` to resolve symlinks and treat symlinked directories as directories;
        ``False`` to treat symlinks as single non-traversable leaf files without resolving.
    :return:
        An iterator yielding 3-tuples of:
        - ``child_path`` (``str``): Complete filesystem path to the child entry.
        - ``st`` (:class:`os.stat_result`): Stat result obtained from ``effective_stat``.
        - ``is_dir`` (``bool``): ``True`` if the entry is a directory (or a symlink to
          a directory with ``follow_symlink=True``); ``False`` otherwise.
    :raises OSError:
        Fatal I/O errors (e.g. disk read failures, EIO) and permission denials (``PermissionError``)
        are re-raised. Transient disappearance errors (e.g. ``FileNotFoundError``, ``ENOTDIR``)
        are suppressed via :func:`~watchdog.utils.is_ignorable_fs_error`.
    """
    try:
        entries = listdir_func(dir_path)
    except OSError as e:
        if is_ignorable_fs_error(e):
            return
        raise

    # Explicitly close os.scandir handles in finally so early generator exit/cancellation never leaks descriptors.
    close_entries = getattr(entries, "close", None)
    try:
        for entry in entries:
            child_path = os.path.join(dir_path, entry.name)
            try:
                st = effective_stat(child_path)
            except OSError as e:
                if is_ignorable_fs_error(e):
                    continue
                raise
            is_dir = stat.S_ISDIR(st.st_mode) and (follow_symlink or not os.path.islink(child_path))
            yield child_path, st, is_dir
    except OSError as e:
        if is_ignorable_fs_error(e):
            return
        raise
    finally:
        if callable(close_entries):
            close_entries()


def _build_synthetic_created(
    entry_path: str,
    st_res: os.stat_result,
    *,
    is_dir: bool,
    follow_symlink: bool,
    raw_btime: int | None = None,
    has_raw_btime: bool = False,
) -> FileSystemEvent:
    """Create a synthetic Created event pre-populated with scanner-captured identity."""
    ev: FileSystemEvent = (
        DirCreatedEvent(entry_path, is_synthetic=True) if is_dir else FileCreatedEvent(entry_path, is_synthetic=True)
    )
    if not has_raw_btime:
        raw_btime = get_path_birthtime_ns(entry_path, st_res, follow_symlinks=follow_symlink)
    dev = getattr(st_res, "st_dev", None)
    ino = getattr(st_res, "st_ino", None)
    file_id = (int(dev), int(ino)) if dev is not None and ino is not None else None
    # Attach scanner identity so BaseObserver records the startup ledger without re-statting.
    setattr(ev, "_sync_identity", (file_id, raw_btime))  # noqa: B010
    return ev


# TODO: Candidate flags for future emit_existing expansion:
# 1. Custom stat/listdir injection forwarded from schedule() to support virtual/mock filesystems.
# 2. Inode & device tracking (st_dev, st_ino) with an ignore_device option to handle hard links across mounts.
# 3. Early traversal optimization to skip directory event creation when DirCreatedEvent is excluded by event_filter.
def _dir_visit_key(path: str, st_res: os.stat_result) -> tuple[int, int] | str:
    """Return a cycle-detection key for a visited directory.

    Uses ``(st_dev, st_ino)`` when the filesystem reports a positive inode
    number, and falls back to the normalized canonical path when ``st_ino <= 0``
    (e.g. FAT32/SMB or virtual filesystems returning zero inodes).
    """
    if st_res.st_ino > 0:
        return (st_res.st_dev, st_res.st_ino)
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def stream_directory_events(
    path: str,
    *,
    recursive: bool = True,
    stat_func: Callable[[str], os.stat_result] | None = None,
    listdir_func: Callable[[str | None], Iterator[os.DirEntry]] = os.scandir,
    sort_by_birthtime: bool = False,
    follow_symlink: bool = False,
    stop_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
    _visited_dirs: set[tuple[int, int] | str] | None = None,
) -> Iterator[FileSystemEvent]:
    """Yields DirCreatedEvent and FileCreatedEvent lazily for all existing files and directories.

    All generated events have ``is_synthetic = True`` and are yielded in topological
    order (parent directories before child files).

    :param path:
        Root directory or file path to inspect.
    :param recursive:
        ``True`` to traverse subdirectories recursively; ``False`` otherwise.
    :param stat_func:
        Stat function used to inspect file metadata (defaults to :func:`os.stat`
        when ``follow_symlink`` is True, :func:`os.lstat` otherwise).
    :param listdir_func:
        Directory scanning function (defaults to :func:`os.scandir`).
    :param sort_by_birthtime:
        ``True`` to sort entries chronologically by file creation/birth time;
        ``False`` to yield entries immediately in filesystem traversal order (default).
    :param follow_symlink:
        ``True`` to follow directory symlinks and traverse into them; ``False``
        to treat directory symlinks as single file entries without traversal (default).
    :param stop_event:
        Optional event signaling that the observer is stopping, aborting traversal immediately.
    :param cancel_event:
        Optional event signaling that the watch was unscheduled, aborting traversal immediately.
    :param _visited_dirs:
        Internal set of ``(st_dev, st_ino)`` tuples or canonical path strings used to track visited directories
        and prevent infinite loops in recursive symlink cycles.
    :return:
        An iterator yielding synthetic :class:`~watchdog.events.FileSystemEvent` instances.
    """

    if _is_cancelled(stop_event, cancel_event):
        return

    effective_stat = stat_func or (os.stat if follow_symlink else os.lstat)

    try:
        root_st = effective_stat(path)
    except OSError as e:
        if is_ignorable_fs_error(e):
            return
        raise

    if (not follow_symlink and os.path.islink(path)) or not stat.S_ISDIR(root_st.st_mode):
        yield _build_synthetic_created(path, root_st, is_dir=False, follow_symlink=follow_symlink)
        return

    if _visited_dirs is None:
        _visited_dirs = set()
    dir_id = _dir_visit_key(path, root_st)
    if dir_id in _visited_dirs:
        return
    _visited_dirs.add(dir_id)

    if sort_by_birthtime:

        def _get_sort_and_raw_btime(entry_path: str, st_res: os.stat_result) -> tuple[int, int | None]:
            raw_btime = get_path_birthtime_ns(entry_path, st_res, follow_symlinks=follow_symlink)
            if raw_btime is not None:
                return raw_btime, raw_btime
            # Fallback to mtime when birthtime is unavailable so entries on mixed/legacy filesystems
            # don't sort before the 1970 epoch.
            mtime_ns = getattr(st_res, "st_mtime_ns", None)
            sort_btime = int(mtime_ns) if mtime_ns is not None else int(st_res.st_mtime * 1_000_000_000)
            return sort_btime, None

        # Min-heap prioritized by (birthtime_ns, mtime, path) while preserving parent-before-child ordering.
        heap: list[tuple[int, float, str, os.stat_result, bool, int | None]] = []

        def _push_children(dir_path: str) -> bool:
            with contextlib.closing(
                _iter_dir_children(dir_path, listdir_func, effective_stat, follow_symlink=follow_symlink)
            ) as children:
                for child_path, st, is_dir in children:
                    if _is_cancelled(stop_event, cancel_event):
                        return False
                    sort_btime, raw_btime = _get_sort_and_raw_btime(child_path, st)
                    heapq.heappush(heap, (sort_btime, st.st_mtime, child_path, st, is_dir, raw_btime))
            return True

        if not _push_children(path):
            return

        while heap:
            if _is_cancelled(stop_event, cancel_event):
                return
            _btime, _mtime, full_path, st, is_dir, raw_btime = heapq.heappop(heap)
            yield _build_synthetic_created(
                full_path,
                st,
                is_dir=is_dir,
                follow_symlink=follow_symlink,
                raw_btime=raw_btime,
                has_raw_btime=True,
            )
            if is_dir and recursive:
                dir_id = _dir_visit_key(full_path, st)
                if dir_id not in _visited_dirs:
                    _visited_dirs.add(dir_id)
                    if not _push_children(full_path):
                        return
        return

    subdirs: list[str] = []
    with contextlib.closing(
        _iter_dir_children(path, listdir_func, effective_stat, follow_symlink=follow_symlink)
    ) as children:
        for full_path, st, is_dir in children:
            if _is_cancelled(stop_event, cancel_event):
                return
            yield _build_synthetic_created(full_path, st, is_dir=is_dir, follow_symlink=follow_symlink)
            if is_dir and recursive:
                subdirs.append(full_path)

    if recursive:
        for subdir in subdirs:
            if _is_cancelled(stop_event, cancel_event):
                return
            yield from stream_directory_events(
                subdir,
                recursive=recursive,
                stat_func=effective_stat,
                listdir_func=listdir_func,
                sort_by_birthtime=sort_by_birthtime,
                follow_symlink=follow_symlink,
                stop_event=stop_event,
                cancel_event=cancel_event,
                _visited_dirs=_visited_dirs,
            )


def diff_snapshot_events(
    old_snapshot: DirectorySnapshot,
    new_snapshot: DirectorySnapshot,
) -> Iterator[FileSystemEvent]:
    """Diffs two DirectorySnapshots and yields synthetic FileSystemEvents representing
    changes that occurred between them (for Supervisor downtime gap recovery).

    :param old_snapshot:
        The directory snapshot taken prior to interruption.
    :param new_snapshot:
        The new directory snapshot taken after revival.
    :return:
        An iterator yielding synthetic :class:`~watchdog.events.FileSystemEvent` instances.
    """
    diff = DirectorySnapshotDiff(old_snapshot, new_snapshot)
    # Note: attrib buckets (files_attrib/dirs_attrib) are omitted; only created entries are sorted
    # (snapshots lack portable attrib/delete timestamps and retain only latest mtime for modified).

    def _creation_sort_key(p: bytes | str) -> tuple[int, float, str]:
        btime = new_snapshot.birthtime(p)
        mtime = new_snapshot.mtime(p) or 0.0
        # Fall back to mtime when birthtime is unavailable so entries maintain relative
        # chronological order instead of sorting to Unix epoch 0.
        effective_btime = btime if btime is not None else int(mtime * 1_000_000_000)
        return (effective_btime, mtime, os.fsdecode(p) if isinstance(p, bytes) else p)

    # 1. Directories created (sorted chronologically by birth time)
    for d in sorted(diff.dirs_created, key=_creation_sort_key):
        yield DirCreatedEvent(d, is_synthetic=True)

    # 2. Files created (sorted chronologically by birth time)
    for f in sorted(diff.files_created, key=_creation_sort_key):
        yield FileCreatedEvent(f, is_synthetic=True)

    # 3. Directories moved
    for src, dest in diff.dirs_moved:
        yield DirMovedEvent(src, dest, is_synthetic=True)

    # 4. Files moved
    for src, dest in diff.files_moved:
        yield FileMovedEvent(src, dest, is_synthetic=True)

    # 5. Files modified
    for f in diff.files_modified:
        yield FileModifiedEvent(f, is_synthetic=True)

    # 6. Directories modified
    for d in diff.dirs_modified:
        yield DirModifiedEvent(d, is_synthetic=True)

    # 7. Files deleted
    for f in diff.files_deleted:
        yield FileDeletedEvent(f, is_synthetic=True)

    # 8. Directories deleted
    for d in diff.dirs_deleted:
        yield DirDeletedEvent(d, is_synthetic=True)


class SynchronizationEngine:
    """Orchestrates filesystem state synchronization against the observer's event queue.

    :param event_queue:
        The event queue to populate with generated synchronization events.
    :type event_queue:
        :class:`watchdog.observers.api.EventQueue`
    """

    def __init__(self, event_queue: EventQueue) -> None:
        self._event_queue = event_queue

    def stream_startup_catchup(
        self,
        watch: ObservedWatch,
        *,
        stop_event: threading.Event | None = None,
        cancel_event: threading.Event | None = None,
        session_token: object | None = None,
        emitter: Any | None = None,
    ) -> None:
        """Streams existing files into the queue, terminated by a SynchronizationComplete marker.

        :param watch: The watch to catch up.
        :param stop_event: Optional event signaling observer shutdown to abort synchronization early.
        :param cancel_event: Optional event signaling this watch was unscheduled to abort early.
        :param session_token: Unique identity token isolating this synchronization session.
        :param emitter: Optional emitter associated with this watch to coordinate initial snapshot completion.
        """
        # TODO: Mid-traversal live directory moves: when a directory is renamed on the live filesystem
        # after being queued into the traversal heap/subdirs but before scandir descent, the scanner
        # encounters a transient FileNotFoundError and skips the subtree. Future enhancement: provide
        # an adaptive rescan mechanism or bidirectional communication with the observer's sync state.
        scan_path = watch.resolved_path if getattr(watch, "is_file", False) else watch.path
        scan_recursive = False if getattr(watch, "is_file", False) else watch.is_recursive
        for event in stream_directory_events(
            scan_path,
            recursive=scan_recursive,
            sort_by_birthtime=getattr(watch, "ordered_startup", False),
            follow_symlink=watch.follow_symlink,
            stop_event=stop_event,
            cancel_event=cancel_event,
        ):
            if _is_cancelled(stop_event, cancel_event):
                return
            event.watch_path = watch.path
            if session_token is not None:
                # Tag synthetic event so dispatch_events() drops it if this session is unscheduled/replaced.
                setattr(event, "session_token", session_token)  # noqa: B010
            if _passes_event_filter(event, watch):
                self._event_queue.put((event, watch))

        if _is_cancelled(stop_event, cancel_event):
            return

        if emitter is not None and hasattr(emitter, "wait_for_snapshot"):
            status = emitter.wait_for_snapshot(cancel_event=cancel_event)
            # Terminate silently without emitting completion if cancelled while waiting for baseline snapshot.
            if status is SnapshotStatus.CANCELLED or _is_cancelled(stop_event, cancel_event):
                return
            # Raise on snapshot failure/timeout so _sync_worker aborts ordered staging and flushes live events.
            if status is not SnapshotStatus.SUCCESS:
                raise RuntimeError(f"Snapshot synchronization failed: {status.name}")

        if not _is_cancelled(stop_event, cancel_event):
            self._event_queue.put((SynchronizationComplete(watch, session_token=session_token), watch))
