from __future__ import annotations

import dataclasses
import os
from queue import Queue
from typing import Protocol

from watchdog.events import FileSystemEvent
from watchdog.observers.api import EventEmitter, ObservedWatch
from watchdog.utils import platform

Emitter: type[EventEmitter]

if platform.is_linux():
    from watchdog.observers.inotify import InotifyEmitter as Emitter
    from watchdog.observers.inotify import InotifyFullEmitter
elif platform.is_darwin():
    from watchdog.observers.fsevents import FSEventsEmitter as Emitter
elif platform.is_windows():
    from watchdog.observers.read_directory_changes import WindowsApiEmitter as Emitter
elif platform.is_bsd():
    from watchdog.observers.kqueue import KqueueEmitter as Emitter


class P(Protocol):
    def __call__(self, *args: str) -> str: ...


class StartWatching(Protocol):
    def __call__(
        self,
        *,
        path: bytes | str | None = ...,
        use_full_emitter: bool = ...,
        recursive: bool = ...,
    ) -> EventEmitter: ...


class ExpectEvent(Protocol):
    def __call__(self, expected_event: FileSystemEvent, *, timeout: float = ...) -> None: ...


TestEventQueue = Queue[tuple[FileSystemEvent, ObservedWatch]]


@dataclasses.dataclass()
class Helper:
    tmp: str
    emitters: list[EventEmitter] = dataclasses.field(default_factory=list)
    event_queue: TestEventQueue = dataclasses.field(default_factory=Queue)

    def joinpath(self, *args: str) -> str:
        return os.path.join(self.tmp, *args)

    def start_watching(
        self,
        *,
        path: bytes | str | None = None,
        use_full_emitter: bool = False,
        recursive: bool = True,
    ) -> EventEmitter:
        # TODO: check if other platforms expect the trailing slash (e.g. `p('')`)
        path = self.tmp if path is None else path

        watcher = ObservedWatch(path, recursive=recursive)
        emitter_cls = InotifyFullEmitter if platform.is_linux() and use_full_emitter else Emitter
        emitter = emitter_cls(self.event_queue, watcher)

        if platform.is_darwin():
            # TODO: I think this could be better...  .suppress_history should maybe
            #       become a common attribute.
            from watchdog.observers.fsevents import FSEventsEmitter

            assert isinstance(emitter, FSEventsEmitter)
            emitter.suppress_history = True

        self.emitters.append(emitter)
        emitter.start()

        return emitter

    def expect_event(self, expected_event: FileSystemEvent, timeout: float = 2) -> None:
        """Utility function to wait up to `timeout` seconds for an `event_type` for `path` to show up in the queue.

        Provides some robustness for the otherwise flaky nature of asynchronous notifications.
        """
        assert self.event_queue.get(timeout=timeout)[0] == expected_event

    def close(self) -> None:
        for emitter in self.emitters:
            emitter.stop()

        for emitter in self.emitters:
            if emitter.is_alive():
                emitter.join(5)

        alive = [emitter.is_alive() for emitter in self.emitters]
        self.emitters = []
        assert alive == [False] * len(alive)
