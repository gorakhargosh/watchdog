from __future__ import annotations

from watchdog.events import (
    EVENT_TYPE_CREATED,
    EVENT_TYPE_DELETED,
    EVENT_TYPE_MODIFIED,
    EVENT_TYPE_MOVED,
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    PatternMatchingEventHandler,
)
from watchdog.utils.patterns import filter_paths

path_1 = "/path/xyz"
path_2 = "/path/abc"
g_allowed_patterns = ["*.py", "*.txt"]
g_ignore_patterns = ["*.foo"]


def assert_patterns(event):
    paths = [event.src_path, event.dest_path] if hasattr(event, "dest_path") else [event.src_path]
    filtered_paths = filter_paths(
        paths,
        included_patterns=["*.py", "*.txt"],
        excluded_patterns=["*.pyc"],
        case_sensitive=False,
    )
    assert filtered_paths


def test_dispatch():
    # Utilities.
    patterns = ["*.py", "*.txt"]
    ignore_patterns = ["*.pyc"]

    dir_del_event_match = DirDeletedEvent("/path/blah.py")
    dir_del_event_not_match = DirDeletedEvent("/path/foobar")
    dir_del_event_ignored = DirDeletedEvent("/path/foobar.pyc")
    file_del_event_match = FileDeletedEvent("/path/blah.txt")
    file_del_event_not_match = FileDeletedEvent("/path/foobar")
    file_del_event_ignored = FileDeletedEvent("/path/blah.pyc")

    dir_cre_event_match = DirCreatedEvent("/path/blah.py")
    dir_cre_event_not_match = DirCreatedEvent("/path/foobar")
    dir_cre_event_ignored = DirCreatedEvent("/path/foobar.pyc")
    file_cre_event_match = FileCreatedEvent("/path/blah.txt")
    file_cre_event_not_match = FileCreatedEvent("/path/foobar")
    file_cre_event_ignored = FileCreatedEvent("/path/blah.pyc")

    dir_mod_event_match = DirModifiedEvent("/path/blah.py")
    dir_mod_event_not_match = DirModifiedEvent("/path/foobar")
    dir_mod_event_ignored = DirModifiedEvent("/path/foobar.pyc")
    file_mod_event_match = FileModifiedEvent("/path/blah.txt")
    file_mod_event_not_match = FileModifiedEvent("/path/foobar")
    file_mod_event_ignored = FileModifiedEvent("/path/blah.pyc")

    dir_mov_event_match = DirMovedEvent("/path/blah.py", "/path/blah")
    dir_mov_event_not_match = DirMovedEvent("/path/foobar", "/path/blah")
    dir_mov_event_ignored = DirMovedEvent("/path/foobar.pyc", "/path/blah")
    file_mov_event_match = FileMovedEvent("/path/blah.txt", "/path/blah")
    file_mov_event_not_match = FileMovedEvent("/path/foobar", "/path/blah")
    file_mov_event_ignored = FileMovedEvent("/path/blah.pyc", "/path/blah")

    all_dir_events = [
        dir_mod_event_match,
        dir_mod_event_not_match,
        dir_mod_event_ignored,
        dir_del_event_match,
        dir_del_event_not_match,
        dir_del_event_ignored,
        dir_cre_event_match,
        dir_cre_event_not_match,
        dir_cre_event_ignored,
        dir_mov_event_match,
        dir_mov_event_not_match,
        dir_mov_event_ignored,
    ]
    all_file_events = [
        file_mod_event_match,
        file_mod_event_not_match,
        file_mod_event_ignored,
        file_del_event_match,
        file_del_event_not_match,
        file_del_event_ignored,
        file_cre_event_match,
        file_cre_event_not_match,
        file_cre_event_ignored,
        file_mov_event_match,
        file_mov_event_not_match,
        file_mov_event_ignored,
    ]
    all_events = all_file_events + all_dir_events

    def assert_check_directory(handler, event):
        assert not (handler.ignore_directories and event.is_directory)

    class TestableEventHandler(PatternMatchingEventHandler):
        def on_any_event(self, event):
            assert_check_directory(self, event)

        def on_modified(self, event):
            assert_check_directory(self, event)
            assert event.event_type == EVENT_TYPE_MODIFIED
            assert_patterns(event)

        def on_deleted(self, event):
            assert_check_directory(self, event)
            assert event.event_type == EVENT_TYPE_DELETED
            assert_patterns(event)

        def on_moved(self, event):
            assert_check_directory(self, event)
            assert event.event_type == EVENT_TYPE_MOVED
            assert_patterns(event)

        def on_created(self, event):
            assert_check_directory(self, event)
            assert event.event_type == EVENT_TYPE_CREATED
            assert_patterns(event)

    no_dirs_handler = TestableEventHandler(patterns=patterns, ignore_patterns=ignore_patterns, ignore_directories=True)
    handler = TestableEventHandler(patterns=patterns, ignore_patterns=ignore_patterns)

    for event in all_events:
        no_dirs_handler.dispatch(event)
    for event in all_events:
        handler.dispatch(event)


def test_handler():
    handler1 = PatternMatchingEventHandler(
        patterns=g_allowed_patterns,
        ignore_patterns=g_ignore_patterns,
        ignore_directories=True,
    )
    handler2 = PatternMatchingEventHandler(patterns=g_allowed_patterns, ignore_patterns=g_ignore_patterns)
    assert handler1.patterns == g_allowed_patterns
    assert handler1.ignore_patterns == g_ignore_patterns
    assert handler1.ignore_directories
    assert not handler2.ignore_directories


def test_ignore_directories():
    handler1 = PatternMatchingEventHandler(
        patterns=g_allowed_patterns,
        ignore_patterns=g_ignore_patterns,
        ignore_directories=True,
    )
    handler2 = PatternMatchingEventHandler(patterns=g_allowed_patterns, ignore_patterns=g_ignore_patterns)
    assert handler1.ignore_directories
    assert not handler2.ignore_directories


def test_ignore_patterns():
    handler1 = PatternMatchingEventHandler(
        patterns=g_allowed_patterns,
        ignore_patterns=g_ignore_patterns,
        ignore_directories=True,
    )
    assert handler1.ignore_patterns == g_ignore_patterns


def test_patterns():
    handler1 = PatternMatchingEventHandler(
        patterns=g_allowed_patterns,
        ignore_patterns=g_ignore_patterns,
        ignore_directories=True,
    )
    assert handler1.patterns == g_allowed_patterns
