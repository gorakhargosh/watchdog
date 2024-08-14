from __future__ import annotations

from watchdog.events import (
    EVENT_TYPE_CLOSED,
    EVENT_TYPE_CLOSED_NO_WRITE,
    EVENT_TYPE_CREATED,
    EVENT_TYPE_DELETED,
    EVENT_TYPE_MODIFIED,
    EVENT_TYPE_MOVED,
    EVENT_TYPE_OPENED,
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
    LoggingEventHandler,
)

path_1 = "/path/xyz"
path_2 = "/path/abc"


class _TestableEventHandler(LoggingEventHandler):
    def on_any_event(self, event):
        assert isinstance(event, FileSystemEvent)

    def on_modified(self, event):
        super().on_modified(event)
        assert event.event_type == EVENT_TYPE_MODIFIED

    def on_deleted(self, event):
        super().on_deleted(event)
        assert event.event_type == EVENT_TYPE_DELETED

    def on_moved(self, event):
        super().on_moved(event)
        assert event.event_type == EVENT_TYPE_MOVED

    def on_created(self, event):
        super().on_created(event)
        assert event.event_type == EVENT_TYPE_CREATED

    def on_closed(self, event):
        super().on_closed(event)
        assert event.event_type == EVENT_TYPE_CLOSED

    def on_closed_no_write(self, event):
        super().on_closed_no_write(event)
        assert event.event_type == EVENT_TYPE_CLOSED_NO_WRITE

    def on_opened(self, event):
        super().on_opened(event)
        assert event.event_type == EVENT_TYPE_OPENED


def test_logging_event_handler_dispatch():
    dir_del_event = DirDeletedEvent("/path/blah.py")
    file_del_event = FileDeletedEvent("/path/blah.txt")
    dir_cre_event = DirCreatedEvent("/path/blah.py")
    file_cre_event = FileCreatedEvent("/path/blah.txt")
    dir_mod_event = DirModifiedEvent("/path/blah.py")
    file_mod_event = FileModifiedEvent("/path/blah.txt")
    dir_mov_event = DirMovedEvent("/path/blah.py", "/path/blah")
    file_mov_event = FileMovedEvent("/path/blah.txt", "/path/blah")
    file_ope_event = FileOpenedEvent("/path/blah.txt")
    file_clo_event = FileClosedEvent("/path/blah.txt")
    file_clo_nw_event = FileClosedNoWriteEvent("/path/blah.txt")

    all_events = [
        dir_mod_event,
        dir_del_event,
        dir_cre_event,
        dir_mov_event,
        file_mod_event,
        file_del_event,
        file_cre_event,
        file_mov_event,
        file_ope_event,
        file_clo_event,
        file_clo_nw_event,
    ]

    handler = _TestableEventHandler()
    for event in all_events:
        handler.dispatch(event)
