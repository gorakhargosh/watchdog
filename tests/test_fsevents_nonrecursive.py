from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from watchdog.utils import platform

if not platform.is_darwin():
    pytest.skip("macOS only.", allow_module_level=True)

from watchdog.events import (
    DirAttribEvent,
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileSystemEvent,
)
from watchdog.observers.api import EventQueue, ObservedWatch
from watchdog.observers.fsevents import FSEventsEmitter

if TYPE_CHECKING:
    from .utils import EventsChecker, P, StartWatching


@pytest.mark.parametrize("operation", ["create", "delete", "move"])
def test_nonrecursive_directory_entries(
    p: P, start_watching: StartWatching, events_checker: EventsChecker, operation: str
) -> None:
    os.mkdir(p("nested"))
    if operation != "create":
        os.mkdir(p("child"))
    start_watching(recursive=False)

    if operation == "create":
        os.mkdir(p("child"))
        expected = DirCreatedEvent
    elif operation == "delete":
        os.rmdir(p("child"))
        expected = DirDeletedEvent
    else:
        os.rename(p("child"), p("nested", "child"))
        expected = DirMovedEvent

    with events_checker() as ec:
        ec.add(expected, "child", dest_path="nested/child" if operation == "move" else None)
        ec.add(DirModifiedEvent, ".")


@pytest.mark.parametrize(
    "event_type", [DirCreatedEvent, DirDeletedEvent, DirMovedEvent, DirModifiedEvent, DirAttribEvent]
)
@pytest.mark.parametrize("relative_path", [".", "child", "nested/child"])
@pytest.mark.parametrize("recursive", [False, True])
def test_directory_entry_filter(
    p: P, event_type: type[FileSystemEvent], relative_path: str, *, recursive: bool
) -> None:
    queue = EventQueue()
    watch = ObservedWatch(p(), recursive=recursive)
    emitter = FSEventsEmitter(queue, watch)
    root = os.path.realpath(p())
    event = event_type(os.path.normpath(os.path.join(root, relative_path)))
    if event_type is DirMovedEvent:
        event = event_type(event.src_path, os.path.join(root, "nested", "renamed"))
    emitter.queue_event(event)
    expected = (
        recursive
        or relative_path == "."
        or (relative_path == "child" and event_type in (DirCreatedEvent, DirDeletedEvent, DirMovedEvent))
    )
    if expected:
        assert queue.get_nowait() == (event, watch)
    assert queue.empty()
