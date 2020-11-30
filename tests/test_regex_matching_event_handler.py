# coding: utf-8
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc & contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from watchdog.events import (
    FileDeletedEvent,
    FileModifiedEvent,
    FileCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirCreatedEvent,
    FileMovedEvent,
    DirMovedEvent,
    RegexMatchingEventHandler,
    LoggingEventHandler,
    EVENT_TYPE_MODIFIED,
    EVENT_TYPE_CREATED,
    EVENT_TYPE_DELETED,
    EVENT_TYPE_MOVED,
)

path_1 = '/path/xyz'
path_2 = '/path/abc'
g_allowed_regexes = [r".*\.py", r".*\.txt"]
g_ignore_regexes = [r".*\.pyc"]


def test_dispatch():
    # Utilities.
    regexes = [r".*\.py", r".*\.txt"]
    ignore_regexes = [r".*\.pyc"]

    def assert_regexes(handler, event):
        if hasattr(event, 'dest_path'):
            paths = [event.src_path, event.dest_path]
        else:
            paths = [event.src_path]
        filtered_paths = set()
        for p in paths:
            if any(r.match(p) for r in handler.regexes):
                filtered_paths.add(p)
        assert filtered_paths

    dir_del_event_match = DirDeletedEvent('/path/blah.py')
    dir_del_event_not_match = DirDeletedEvent('/path/foobar')
    dir_del_event_ignored = DirDeletedEvent('/path/foobar.pyc')
    file_del_event_match = FileDeletedEvent('/path/blah.txt')
    file_del_event_not_match = FileDeletedEvent('/path/foobar')
    file_del_event_ignored = FileDeletedEvent('/path/blah.pyc')

    dir_cre_event_match = DirCreatedEvent('/path/blah.py')
    dir_cre_event_not_match = DirCreatedEvent('/path/foobar')
    dir_cre_event_ignored = DirCreatedEvent('/path/foobar.pyc')
    file_cre_event_match = FileCreatedEvent('/path/blah.txt')
    file_cre_event_not_match = FileCreatedEvent('/path/foobar')
    file_cre_event_ignored = FileCreatedEvent('/path/blah.pyc')

    dir_mod_event_match = DirModifiedEvent('/path/blah.py')
    dir_mod_event_not_match = DirModifiedEvent('/path/foobar')
    dir_mod_event_ignored = DirModifiedEvent('/path/foobar.pyc')
    file_mod_event_match = FileModifiedEvent('/path/blah.txt')
    file_mod_event_not_match = FileModifiedEvent('/path/foobar')
    file_mod_event_ignored = FileModifiedEvent('/path/blah.pyc')

    dir_mov_event_match = DirMovedEvent('/path/blah.py', '/path/blah')
    dir_mov_event_not_match = DirMovedEvent('/path/foobar', '/path/blah')
    dir_mov_event_ignored = DirMovedEvent('/path/foobar.pyc', '/path/blah')
    file_mov_event_match = FileMovedEvent('/path/blah.txt', '/path/blah')
    file_mov_event_not_match = FileMovedEvent('/path/foobar', '/path/blah')
    file_mov_event_ignored = FileMovedEvent('/path/blah.pyc', '/path/blah')

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

    class TestableEventHandler(RegexMatchingEventHandler):

        def on_any_event(self, event):
            assert_check_directory(self, event)

        def on_modified(self, event):
            assert_check_directory(self, event)
            assert event.event_type == EVENT_TYPE_MODIFIED
            assert_regexes(self, event)

        def on_deleted(self, event):
            assert_check_directory(self, event)
            assert event.event_type == EVENT_TYPE_DELETED
            assert_regexes(self, event)

        def on_moved(self, event):
            assert_check_directory(self, event)
            assert event.event_type == EVENT_TYPE_MOVED
            assert_regexes(self, event)

        def on_created(self, event):
            assert_check_directory(self, event)
            assert event.event_type == EVENT_TYPE_CREATED
            assert_regexes(self, event)

    no_dirs_handler = TestableEventHandler(regexes=regexes,
                                           ignore_regexes=ignore_regexes,
                                           ignore_directories=True)
    handler = TestableEventHandler(regexes=regexes,
                                   ignore_regexes=ignore_regexes,
                                   ignore_directories=False)

    for event in all_events:
        no_dirs_handler.dispatch(event)
    for event in all_events:

        handler.dispatch(event)


def test_handler():
    handler1 = RegexMatchingEventHandler(g_allowed_regexes,
                                         g_ignore_regexes, True)
    handler2 = RegexMatchingEventHandler(g_allowed_regexes,
                                         g_ignore_regexes, False)
    assert [r.pattern for r in handler1.regexes] == g_allowed_regexes
    assert [r.pattern for r in handler1.ignore_regexes] == g_ignore_regexes
    assert handler1.ignore_directories
    assert not handler2.ignore_directories


def test_ignore_directories():
    handler1 = RegexMatchingEventHandler(g_allowed_regexes,
                                         g_ignore_regexes, True)
    handler2 = RegexMatchingEventHandler(g_allowed_regexes,
                                         g_ignore_regexes, False)
    assert handler1.ignore_directories
    assert not handler2.ignore_directories


def test_ignore_regexes():
    handler1 = RegexMatchingEventHandler(g_allowed_regexes,
                                         g_ignore_regexes, True)
    assert [r.pattern for r in handler1.ignore_regexes] == g_ignore_regexes


def test_regexes():
    handler1 = RegexMatchingEventHandler(g_allowed_regexes,
                                         g_ignore_regexes, True)
    assert [r.pattern for r in handler1.regexes] == g_allowed_regexes


def test_logging_event_handler_dispatch():

    class _TestableEventHandler(LoggingEventHandler):

        def on_any_event(self, event):
            assert True

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

    # Utilities.
    dir_del_event = DirDeletedEvent('/path/blah.py')
    file_del_event = FileDeletedEvent('/path/blah.txt')
    dir_cre_event = DirCreatedEvent('/path/blah.py')
    file_cre_event = FileCreatedEvent('/path/blah.txt')
    dir_mod_event = DirModifiedEvent('/path/blah.py')
    file_mod_event = FileModifiedEvent('/path/blah.txt')
    dir_mov_event = DirMovedEvent('/path/blah.py', '/path/blah')
    file_mov_event = FileMovedEvent('/path/blah.txt', '/path/blah')

    all_events = [
        dir_mod_event,
        dir_del_event,
        dir_cre_event,
        dir_mov_event,
        file_mod_event,
        file_del_event,
        file_cre_event,
        file_mov_event,
    ]

    handler = _TestableEventHandler()
    for event in all_events:
        handler.dispatch(event)
