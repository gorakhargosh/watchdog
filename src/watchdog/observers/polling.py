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

import logging
import os
import threading
import time
from functools import partial
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
from watchdog.observers.api import (
    DEFAULT_EMITTER_TIMEOUT,
    DEFAULT_OBSERVER_TIMEOUT,
    BaseObserver,
    EventEmitter,
    SnapshotStatus,
)
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

    supports_sync_barrier: bool = True

    def __init__(
        self,
        event_queue: EventQueue,
        watch: ObservedWatch,
        *,
        timeout: Seconds = DEFAULT_EMITTER_TIMEOUT,
        event_filter: list[type[FileSystemEvent]] | None = None,
        stat: Callable[[str], os.stat_result] | None = None,
        listdir: Callable[[str | None], Iterator[os.DirEntry]] = os.scandir,
    ) -> None:
        super().__init__(event_queue, watch, timeout=timeout, event_filter=event_filter)
        self._snapshot: DirectorySnapshot = EmptyDirectorySnapshot()
        self._lock = threading.Lock()
        self._snapshot_failing = False
        # Distinguishes fatal self-stop (missing/non-dir root) from external stop() so waiters report FAILED.
        self._stopped_on_failure = False
        stat_func = stat if stat is not None else (os.stat if getattr(watch, "follow_symlink", False) else os.lstat)
        self._take_snapshot: Callable[[], DirectorySnapshot] = lambda: DirectorySnapshot(
            self.watch.path,
            recursive=self.watch.is_recursive,
            stat=stat_func,
            listdir=listdir,
        )
        self._wake_event = threading.Event()
        self._snapshot_cond = threading.Condition(threading.Lock())
        self._snapshot_started_seq = 0
        self._snapshot_completed_seq = 0
        self._snapshot_status: SnapshotStatus = SnapshotStatus.IDLE
        self._snapshot_seq_status: dict[int, SnapshotStatus] = {}
        # Tracks completed snapshot sequence numbers that failed with a recoverable OSError
        # (e.g. EIO, ESTALE) rather than fatal root loss, allowing wait_for_snapshot() to retry
        # across polling intervals up to retry_timeout and report CANCELLED on clean stop();
        # pruned alongside _snapshot_seq_status.
        self._snapshot_transient_error_seqs: set[int] = set()
        # Tracks active waiter counts per snapshot sequence number. Prevents queue_events()
        # from purging sequence results while one or more workers are still awaiting them.
        self._snapshot_waiting_seqs: dict[int, int] = {}

    def _register_next_wait_target(self) -> int:
        """Register a waiter on the next unstarted snapshot sequence and return it.

        Caller must hold ``self._snapshot_cond``.
        """
        target_seq = self._snapshot_started_seq + 1
        self._snapshot_waiting_seqs[target_seq] = self._snapshot_waiting_seqs.get(target_seq, 0) + 1
        return target_seq

    def _release_wait_target(self, target_seq: int) -> None:
        """Decrement active waiter count for ``target_seq``, pruning if zero.

        Caller must hold ``self._snapshot_cond``.
        """
        remaining = self._snapshot_waiting_seqs.get(target_seq, 1) - 1
        if remaining <= 0:
            self._snapshot_waiting_seqs.pop(target_seq, None)
        else:
            self._snapshot_waiting_seqs[target_seq] = remaining

    def _is_retryable_transient_failure(self, target_seq: int) -> bool:
        """Return whether ``target_seq`` hit a recoverable error while emitter stays healthy.

        Caller must hold ``self._snapshot_cond``.
        """
        return (
            target_seq in self._snapshot_transient_error_seqs
            and not self._stopped_on_failure
            and self.should_keep_running()
        )

    def on_thread_stop(self) -> None:
        self._wake_event.set()
        with self._snapshot_cond:
            self._snapshot_cond.notify_all()

    def on_thread_start(self) -> None:
        """Take the first snapshot of the watched directory.

        Later snapshots are compared against this one to detect changes.
        """

        self._snapshot = self._take_snapshot()

    def _terminal_wait_status(
        self,
        cancel_event: threading.Event | None,
        target_seq: int,
    ) -> SnapshotStatus | None:
        """Resolve terminal wait status for ``target_seq``, or return None to continue waiting.

        Caller must hold ``self._snapshot_cond``. Explicit cancellation takes precedence over
        fatal snapshot failures, which in turn take precedence over clean emitter shutdown.
        """
        if cancel_event is not None and cancel_event.is_set():
            return SnapshotStatus.CANCELLED
        if self._snapshot_completed_seq >= target_seq:
            seq_status = self._snapshot_seq_status.get(target_seq, self._snapshot_status)
            if seq_status is SnapshotStatus.FAILED:
                if target_seq in self._snapshot_transient_error_seqs and not self._stopped_on_failure:
                    return SnapshotStatus.FAILED if self.should_keep_running() else SnapshotStatus.CANCELLED
                return SnapshotStatus.FAILED
            if not self.should_keep_running():
                return SnapshotStatus.FAILED if self._stopped_on_failure else SnapshotStatus.CANCELLED
            return seq_status
        if not self.should_keep_running():
            return SnapshotStatus.FAILED if self._stopped_on_failure else SnapshotStatus.CANCELLED
        return None

    def wait_for_snapshot(
        self,
        *,
        cancel_event: threading.Event | None = None,
        snapshot_timeout: float | None = None,
        retry_timeout: float | None = None,
    ) -> SnapshotStatus:
        """Trigger an immediate snapshot and wait for its completion.

        Coordinates with the polling worker using monotonic sequence numbers,
        guaranteeing that SUCCESS is only returned for a snapshot that began
        *after* this wait request was registered. Transient ``OSError`` failures
        while the emitter remains healthy are retried across normal polling intervals
        until a bounded monotonic retry deadline elapses.

        :param cancel_event:
            Optional event signaled if the watch is unscheduled.
        :param snapshot_timeout:
            Optional maximum seconds to wait for snapshot completion (default
            ``None`` waits until completion, fatal failure, or cancellation).
        :param retry_timeout:
            Optional maximum seconds to retry after the first recoverable
            ``OSError`` (defaults to ``max(2.0, timeout * 3.0)``).

        :returns:
            :class:`~watchdog.observers.api.SnapshotStatus`:
            SUCCESS if the snapshot diff completed cleanly,
            FAILED if a fatal snapshot error occurred or stopped the emitter,
            CANCELLED if cancelled or stopped cleanly, or
            TIMEOUT if ``snapshot_timeout`` or the transient-error retry deadline elapsed.
        """
        # TODO: Evaluate exposing snapshot_timeout / retry_timeout via schedule()/PollingObserver.
        with self._snapshot_cond:
            # We must wait for a snapshot whose execution began AFTER this wait request
            # was registered. This prevents an in-flight snapshot that started before
            # the catch-up scan from prematurely acknowledging completion.
            target_seq = self._register_next_wait_target()
            self._wake_event.set()

            overall_deadline = None if snapshot_timeout is None else time.monotonic() + snapshot_timeout
            retry_deadline: float | None = None
            try:
                while (result := self._terminal_wait_status(cancel_event, target_seq)) is None or (
                    result is SnapshotStatus.FAILED and self._is_retryable_transient_failure(target_seq)
                ):
                    if result is not None:
                        now = time.monotonic()
                        if retry_deadline is None:
                            effective_retry = (
                                max(2.0, float(self._timeout) * 3.0)
                                if retry_timeout is None
                                else max(0.0, retry_timeout)
                            )
                            retry_deadline = now + effective_retry
                        if retry_deadline <= now or (overall_deadline is not None and overall_deadline <= now):
                            return SnapshotStatus.TIMEOUT
                        # Release finished failed seq and await the next scheduled poll without spin-waking.
                        self._release_wait_target(target_seq)
                        target_seq = self._register_next_wait_target()
                        continue

                    deadline = retry_deadline
                    if overall_deadline is not None:
                        deadline = overall_deadline if deadline is None else min(overall_deadline, deadline)
                    if deadline is None:
                        self._snapshot_cond.wait(timeout=0.05)
                        continue
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return SnapshotStatus.TIMEOUT
                    self._snapshot_cond.wait(timeout=min(0.05, remaining))
                return result
            finally:
                self._release_wait_target(target_seq)

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
        if self.stopped_event.is_set():
            return

        self._wake_event.wait(timeout)

        if self.stopped_event.is_set():
            return

        with self._lock:
            if not self.should_keep_running():
                return

            with self._snapshot_cond:
                # Increment started sequence to mark the beginning of a fresh snapshot and clear wake signal atomically
                self._snapshot_started_seq += 1
                current_seq = self._snapshot_started_seq
                self._wake_event.clear()

            status = SnapshotStatus.FAILED
            is_transient_error = False
            # Get event diff between fresh snapshot and previous snapshot.
            # Update snapshot.
            try:
                new_snapshot = self._take_snapshot()
                if self._snapshot_failing:
                    self._snapshot_failing = False
                    logger.info("Snapshot of %r succeeded again, resuming", self.watch.path)

                # TODO: Optional timestamp sorting within DirectorySnapshotDiff for created (birthtime/mtime)
                # and modified (mtime) entries; attrib/deleted events lack snapshot timestamps to sort reliably.
                events = DirectorySnapshotDiff(self._snapshot, new_snapshot)
                self._snapshot = new_snapshot

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

                status = SnapshotStatus.SUCCESS
            except (FileNotFoundError, NotADirectoryError):
                self.queue_event(DirDeletedEvent(self.watch.path))
                # Record fatal self-stop under _snapshot_cond before stop() flips should_keep_running()
                # so concurrent/subsequent wait_for_snapshot() callers report FAILED, not CANCELLED.
                with self._snapshot_cond:
                    self._stopped_on_failure = True
                self.stop()
            except OSError as exc:
                # Other errors (EIO, ESTALE, EHOSTDOWN, ...) are often temporary,
                # e.g. a network share that is briefly unreachable. Keep the last
                # snapshot and try again on the next poll, so that changes made
                # in the meantime are still reported.
                # TODO: Revisit library-wide permission/error handling in a dedicated
                # cleanup so permanent permission errors (EACCES/EPERM) can be
                # distinguished from transient I/O errors without breaking existing
                # PollingEmitter retry contracts.
                is_transient_error = True
                if not self._snapshot_failing:
                    self._snapshot_failing = True
                    logger.warning("Cannot take a snapshot of %r, will retry: %s", self.watch.path, exc)
            finally:
                # Always advance completed sequence and wake waiters, even on failure/error
                with self._snapshot_cond:
                    if is_transient_error:
                        self._snapshot_transient_error_seqs.add(current_seq)
                    self._snapshot_completed_seq = current_seq
                    self._snapshot_status = status
                    self._snapshot_seq_status[current_seq] = status
                    # Retain the most recent 10 sequence statuses for history, but never
                    # purge sequences with active waiting threads (retained in _snapshot_waiting_seqs).
                    for old_seq in list(self._snapshot_seq_status):
                        if old_seq < current_seq - 10 and old_seq not in self._snapshot_waiting_seqs:
                            del self._snapshot_seq_status[old_seq]
                            self._snapshot_transient_error_seqs.discard(old_seq)
                    self._snapshot_cond.notify_all()


class PollingObserver(BaseObserver):
    """Platform-independent observer that polls a directory to detect file
    system changes.

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
