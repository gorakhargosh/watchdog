from __future__ import annotations

import dataclasses
import os
import sys
from queue import Empty, Queue
from typing import List, Optional, Tuple, Type, Union

from watchdog.events import FileSystemEvent
from watchdog.observers.api import EventEmitter, ObservedWatch
from watchdog.utils import Protocol

Emitter: Type[EventEmitter]

if sys.platform.startswith("linux"):
    from watchdog.observers.inotify import InotifyEmitter as Emitter
    from watchdog.observers.inotify import InotifyFullEmitter
elif sys.platform.startswith("darwin"):
    from watchdog.observers.fsevents import FSEventsEmitter as Emitter
elif sys.platform.startswith("win"):
    from watchdog.observers.read_directory_changes import WindowsApiEmitter as Emitter
elif sys.platform.startswith(("dragonfly", "freebsd", "netbsd", "openbsd", "bsd")):
    from watchdog.observers.kqueue import KqueueEmitter as Emitter


class P(Protocol):
    def __call__(self, *args: str) -> str:
        ...


class StartWatching(Protocol):
    def __call__(
        self,
        path: Optional[Union[str, bytes]] = ...,
        use_full_emitter: bool = ...,
        recursive: bool = ...,
    ) -> EventEmitter:
        ...


class ExpectEvent(Protocol):
    def __call__(self, expected_event: FileSystemEvent, timeout: float = ...) -> None:
        ...


TestEventQueue = Union["Queue[Tuple[FileSystemEvent, ObservedWatch]]"]


@dataclasses.dataclass()
class Helper:
    tmp: str
    emitters: List[EventEmitter] = dataclasses.field(default_factory=list)
    event_queue: TestEventQueue = dataclasses.field(default_factory=Queue)

    def joinpath(self, *args: str) -> str:
        return os.path.join(self.tmp, *args)

    def start_watching(
        self,
        path: Optional[Union[str, bytes]] = None,
        use_full_emitter: bool = False,
        recursive: bool = True,
    ) -> EventEmitter:
        # todo: check if other platforms expect the trailing slash (e.g. `p('')`)
        path = self.tmp if path is None else path

        emitter: EventEmitter
        if sys.platform.startswith("linux") and use_full_emitter:
            emitter = InotifyFullEmitter(
                self.event_queue, ObservedWatch(path, recursive=recursive)
            )
        else:
            emitter = Emitter(self.event_queue, ObservedWatch(path, recursive=recursive))

        self.emitters.append(emitter)

        if sys.platform.startswith("darwin"):
            # TODO: I think this could be better...  .suppress_history should maybe
            #       become a common attribute.
            from watchdog.observers.fsevents import FSEventsEmitter
            assert isinstance(emitter, FSEventsEmitter)
            emitter.suppress_history = True

        emitter.start()

        return emitter

    def expect_event(self, expected_event: FileSystemEvent, timeout: float = 2) -> None:
        """Utility function to wait up to `timeout` seconds for an `event_type` for `path` to show up in the queue.

        Provides some robustness for the otherwise flaky nature of asynchronous notifications.
        """
        try:
            event = self.event_queue.get(timeout=timeout)[0]
            assert event == expected_event
        except Empty:
            raise

    def close(self) -> None:
        for emitter in self.emitters:
            emitter.stop()

        for emitter in self.emitters:
            if emitter.is_alive():
                emitter.join(5)

        alive = [emitter.is_alive() for emitter in self.emitters]
        self.emitters = []
        assert alive == [False] * len(alive)
