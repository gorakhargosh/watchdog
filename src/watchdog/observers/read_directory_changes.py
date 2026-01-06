from __future__ import annotations

import os.path
import platform
import threading
from typing import TYPE_CHECKING

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    generate_sub_created_events,
    generate_sub_moved_events,
)
from watchdog.observers.api import DEFAULT_EMITTER_TIMEOUT, DEFAULT_OBSERVER_TIMEOUT, BaseObserver, EventEmitter
from watchdog.observers.winapi import DirectoryChangeReader

if TYPE_CHECKING:
    from watchdog.events import FileSystemEvent
    from watchdog.observers.api import EventQueue, ObservedWatch


class WindowsApiEmitter(EventEmitter):
    """Windows API-based emitter that uses ReadDirectoryChangesW
    to detect file system changes for a watch.
    """

    def __init__(
        self,
        event_queue: EventQueue,
        watch: ObservedWatch,
        *,
        timeout: float = DEFAULT_EMITTER_TIMEOUT,
        event_filter: list[type[FileSystemEvent]] | None = None,
    ) -> None:
        super().__init__(event_queue, watch, timeout=timeout, event_filter=event_filter)
        self._lock = threading.RLock()
        self._reader: DirectoryChangeReader | None = None

    def on_thread_start(self) -> None:
        with self._lock:
            assert self._reader is None
            self._reader = DirectoryChangeReader(self.watch.path, recursive=self.watch.is_recursive)
        self._reader.start()

    if platform.python_implementation() == "PyPy":

        def start(self) -> None:
            """PyPy needs some time before receiving events, see #792."""
            from time import sleep

            super().start()
            sleep(0.01)

    def on_thread_stop(self) -> None:
        with self._lock:
            reader = self._reader
            self._reader = None
        if reader is not None:
            reader.stop()

    def queue_events(self, timeout: float) -> None:
        reader = self._reader
        if reader is None:
            return  # reader has been stopped
        last_renamed_src_path = ""
        should_stop = False
        for winapi_event in reader.get_events(timeout):
            src_path = os.path.join(self.watch.path, winapi_event.src_path)

            if winapi_event.is_renamed_old:
                last_renamed_src_path = src_path
            elif winapi_event.is_renamed_new:
                dest_path = src_path
                src_path = last_renamed_src_path
                if os.path.isdir(dest_path):
                    self.queue_event(DirMovedEvent(src_path, dest_path))
                    if self.watch.is_recursive:
                        for sub_moved_event in generate_sub_moved_events(src_path, dest_path):
                            self.queue_event(sub_moved_event)
                else:
                    self.queue_event(FileMovedEvent(src_path, dest_path))
            elif winapi_event.is_modified:
                self.queue_event((DirModifiedEvent if os.path.isdir(src_path) else FileModifiedEvent)(src_path))
            elif winapi_event.is_added:
                isdir = os.path.isdir(src_path)
                self.queue_event((DirCreatedEvent if isdir else FileCreatedEvent)(src_path))
                if isdir and self.watch.is_recursive:
                    for sub_created_event in generate_sub_created_events(src_path):
                        self.queue_event(sub_created_event)
            elif winapi_event.is_removed:
                self.queue_event(FileDeletedEvent(src_path))
            elif winapi_event.is_removed_self:
                self.queue_event(DirDeletedEvent(self.watch.path))
                should_stop = True
        if should_stop:
            # watched directory was deleted, stop observer threads
            self.stop()


class WindowsApiObserver(BaseObserver):
    """Observer thread that schedules watching directories and dispatches
    calls to event handlers.
    """

    def __init__(self, *, timeout: float = DEFAULT_OBSERVER_TIMEOUT) -> None:
        super().__init__(WindowsApiEmitter, timeout=timeout)
