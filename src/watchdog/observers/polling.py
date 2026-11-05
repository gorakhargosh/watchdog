""":module: watchdog.observers.polling
:synopsis: Polling emitter implementation.
:author: yesudeep@google.com (Yesudeep Mangalapilly)
:author: Mickaël Schoentgen <contact@tiger-222.fr>

Classes
-------
.. autoclass:: PollingEmitter
   :members:
   :show-inheritance:

.. autoclass:: PollingObserver
   :members:
   :show-inheritance:

.. autoclass:: PollingObserverVFS
   :members:
   :show-inheritance:
   :special-members:
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from functools import partial
from stat import S_ISREG
from typing import TYPE_CHECKING

from watchdog.events import (
    DirAttribEvent,
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileAttribEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)
from watchdog.observers.api import DEFAULT_EMITTER_TIMEOUT, DEFAULT_OBSERVER_TIMEOUT, BaseObserver, EventEmitter
from watchdog.utils import platform
from watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff, EmptyDirectorySnapshot

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from watchdog.events import FileSystemEvent
    from watchdog.observers.api import EventQueue, ObservedWatch
    from watchdog.utils import Seconds

logger = logging.getLogger(__name__)


class PollingEmitter(EventEmitter):
    """Platform-independent emitter that polls a directory to detect file
    system changes.
    """

    def __init__(
        self,
        event_queue: EventQueue,
        watch: ObservedWatch,
        *,
        timeout: Seconds = DEFAULT_EMITTER_TIMEOUT,
        event_filter: list[type[FileSystemEvent]] | None = None,
        stat: Callable[[str], os.stat_result] = os.stat,
        listdir: Callable[[str | None], Iterator[os.DirEntry]] = os.scandir,
    ) -> None:
        super().__init__(event_queue, watch, timeout=timeout, event_filter=event_filter)
        self._snapshot: DirectorySnapshot = EmptyDirectorySnapshot()
        self._lock = threading.Lock()
        self._snapshot_failing = False
        self._poll_sysfs = platform.is_linux() and stat is os.stat and listdir is os.scandir
        self._sysfs_contents: dict[bytes | str, bytes] = {}
        self._take_snapshot: Callable[[], DirectorySnapshot] = lambda: DirectorySnapshot(
            self.watch.path,
            recursive=self.watch.is_recursive,
            stat=stat,
            listdir=listdir,
        )

    def on_thread_start(self) -> None:
        """Take the first snapshot of the watched directory.

        Later snapshots are compared against this one to detect changes.
        """

        self._snapshot = self._take_snapshot()
        self._sysfs_contents = self._read_sysfs_contents(self._snapshot)

    def _read_sysfs_contents(self, snapshot: DirectorySnapshot) -> dict[bytes | str, bytes]:
        contents: dict[bytes | str, bytes] = {}
        if not self._poll_sysfs:
            return contents
        root = os.path.realpath(os.fsdecode(self.watch.path))
        if root != "/sys" and not root.startswith("/sys/"):
            return contents

        for path in snapshot.paths:
            if not S_ISREG(snapshot.mode(path)) or not os.path.realpath(os.fsdecode(path)).startswith("/sys/"):
                continue
            try:
                with open(path, "rb") as file:
                    contents[path] = hashlib.file_digest(file, "sha256").digest()
            except OSError:
                # Attributes may be unreadable or disappear between stat and
                # open. Retain the last readable value only for the same file.
                if path in self._sysfs_contents and self._snapshot.inode(path) == snapshot.inode(path):
                    contents[path] = self._sysfs_contents[path]
        return contents

    def queue_events(self, timeout: Seconds) -> None:
        """Wait ``timeout`` seconds, then queue events for any changes.

        Takes a new snapshot of the watched directory and compares it with the
        previous one. An event is queued for each file or directory that was
        created, deleted, modified or moved. Returns early if the emitter is
        stopped while waiting.

        If the watched directory no longer exists or is not a directory, a
        :class:`~watchdog.events.DirDeletedEvent` is queued and the emitter
        stops. Other :class:`OSError` exceptions are logged and retried on the
        next poll.

        :param timeout:
            Seconds to wait between successive snapshots. Polling emitters use
            this as the polling interval.
        """

        # We don't want to hit the disk continuously.
        # timeout behaves like an interval for polling emitters.
        if self.stopped_event.wait(timeout):
            return

        with self._lock:
            if not self.should_keep_running():
                return

            # Get event diff between fresh snapshot and previous snapshot.
            # Update snapshot.
            try:
                new_snapshot = self._take_snapshot()
            except (FileNotFoundError, NotADirectoryError):
                self.queue_event(DirDeletedEvent(self.watch.path))
                self.stop()
                return
            except OSError as exc:
                # Other errors (EIO, ESTALE, EHOSTDOWN, ...) are often temporary,
                # e.g. a network share that is briefly unreachable. Keep the last
                # snapshot and try again on the next poll, so that changes made
                # in the meantime are still reported.
                if not self._snapshot_failing:
                    self._snapshot_failing = True
                    logger.warning("Cannot take a snapshot of %r, will retry: %s", self.watch.path, exc)
                return

            if self._snapshot_failing:
                self._snapshot_failing = False
                logger.info("Snapshot of %r succeeded again, resuming", self.watch.path)

            events = DirectorySnapshotDiff(self._snapshot, new_snapshot)
            # sysfs attributes can change without updating their size or mtime.
            new_contents = self._read_sysfs_contents(new_snapshot)
            for path in self._sysfs_contents.keys() & new_contents.keys():
                if (
                    self._snapshot.inode(path) == new_snapshot.inode(path)
                    and self._sysfs_contents[path] != new_contents[path]
                    and path not in events.files_modified
                ):
                    events.files_modified.append(path)
            self._snapshot = new_snapshot
            self._sysfs_contents = new_contents

            # Files.
            for src_path in events.files_deleted:
                self.queue_event(FileDeletedEvent(src_path))
            for src_path in events.files_modified:
                self.queue_event(FileModifiedEvent(src_path))
            for src_path in events.files_created:
                self.queue_event(FileCreatedEvent(src_path))
            for src_path, dest_path in events.files_moved:
                self.queue_event(FileMovedEvent(src_path, dest_path))
            for src_path in events.files_attrib:
                self.queue_event(FileAttribEvent(src_path))

            # Directories.
            for src_path in events.dirs_deleted:
                self.queue_event(DirDeletedEvent(src_path))
            for src_path in events.dirs_modified:
                self.queue_event(DirModifiedEvent(src_path))
            for src_path in events.dirs_created:
                self.queue_event(DirCreatedEvent(src_path))
            for src_path, dest_path in events.dirs_moved:
                self.queue_event(DirMovedEvent(src_path, dest_path))
            for src_path in events.dirs_attrib:
                self.queue_event(DirAttribEvent(src_path))


class PollingObserver(BaseObserver):
    """Platform-independent observer that polls a directory to detect file
    system changes.

    On Linux, watches rooted at ``/sys`` or below (including symlinks resolving
    there) also compare the contents of readable regular files under ``/sys/``,
    since sysfs attributes may keep the same size and modification time when
    their values change. This reads those files on every poll; unreadable
    attributes are retried on the next poll. Other watches and custom
    filesystems use stat information only.

    If a poll fails because the watched directory no longer exists
    (``FileNotFoundError`` or ``NotADirectoryError``), a
    :class:`~watchdog.events.DirDeletedEvent` is emitted and watching stops.
    Any other ``OSError``, for instance while a network share is briefly
    unreachable, is logged once and the next poll tries again. Changes made
    in the meantime are reported once the directory can be read again. An
    outage that the OS reports as ``ENOENT`` still looks like a deletion.
    """

    def __init__(self, *, timeout: Seconds = DEFAULT_OBSERVER_TIMEOUT) -> None:
        super().__init__(PollingEmitter, timeout=timeout)


class PollingObserverVFS(BaseObserver):
    """File system independent observer that polls a directory to detect changes."""

    def __init__(
        self,
        stat: Callable[[str], os.stat_result],
        listdir: Callable[[str | None], Iterator[os.DirEntry]],
        *,
        polling_interval: Seconds = 1,
    ) -> None:
        """:param stat: stat function. See ``os.stat`` for details.
        :param listdir: listdir function. See ``os.scandir`` for details.
        :type polling_interval: Seconds
        :param polling_interval: interval between polling the file system.
        """
        emitter_cls = partial(PollingEmitter, stat=stat, listdir=listdir)
        super().__init__(emitter_cls, timeout=polling_interval)  # type: ignore[arg-type]
