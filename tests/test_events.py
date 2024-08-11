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

from __future__ import annotations

from watchdog.events import (
    EVENT_TYPE_ATTRIB,
    EVENT_TYPE_CLOSED,
    EVENT_TYPE_CREATED,
    EVENT_TYPE_DELETED,
    EVENT_TYPE_MODIFIED,
    EVENT_TYPE_MOVED,
    EVENT_TYPE_OPENED,
    DirAttribEvent,
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileAttribEvent,
    FileClosedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileOpenedEvent,
    FileSystemEventHandler,
)

path_1 = "/path/xyz"
path_2 = "/path/abc"


def test_file_deleted_event():
    event = FileDeletedEvent(path_1)
    assert path_1 == event.src_path
    assert EVENT_TYPE_DELETED == event.event_type
    assert not event.is_directory
    assert not event.is_synthetic


def test_file_delete_event_is_directory():
    # Inherited properties.
    event = FileDeletedEvent(path_1)
    assert not event.is_directory
    assert not event.is_synthetic


def test_file_modified_event():
    event = FileModifiedEvent(path_1)
    assert path_1 == event.src_path
    assert EVENT_TYPE_MODIFIED == event.event_type
    assert not event.is_directory
    assert not event.is_synthetic


def test_file_modified_event_is_directory():
    # Inherited Properties
    event = FileModifiedEvent(path_1)
    assert not event.is_directory
    assert not event.is_synthetic


def test_file_created_event():
    event = FileCreatedEvent(path_1)
    assert path_1 == event.src_path
    assert EVENT_TYPE_CREATED == event.event_type
    assert not event.is_directory
    assert not event.is_synthetic


def test_file_moved_event():
    event = FileMovedEvent(path_1, path_2)
    assert path_1 == event.src_path
    assert path_2 == event.dest_path
    assert EVENT_TYPE_MOVED == event.event_type
    assert not event.is_directory
    assert not event.is_synthetic


def test_file_closed_event():
    event = FileClosedEvent(path_1)
    assert path_1 == event.src_path
    assert EVENT_TYPE_CLOSED == event.event_type
    assert not event.is_directory
    assert not event.is_synthetic


def test_file_attrib_event():
    event = FileAttribEvent(path_1)
    assert path_1 == event.src_path
    assert EVENT_TYPE_ATTRIB == event.event_type


def test_file_opened_event():
    event = FileOpenedEvent(path_1)
    assert path_1 == event.src_path
    assert EVENT_TYPE_OPENED == event.event_type
    assert not event.is_directory
    assert not event.is_synthetic


def test_dir_deleted_event():
    event = DirDeletedEvent(path_1)
    assert path_1 == event.src_path
    assert EVENT_TYPE_DELETED == event.event_type
    assert event.is_directory
    assert not event.is_synthetic


def test_dir_modified_event():
    event = DirModifiedEvent(path_1)
    assert path_1 == event.src_path
    assert EVENT_TYPE_MODIFIED == event.event_type
    assert event.is_directory
    assert not event.is_synthetic


def test_dir_created_event():
    event = DirCreatedEvent(path_1)
    assert path_1 == event.src_path
    assert EVENT_TYPE_CREATED == event.event_type
    assert event.is_directory
    assert not event.is_synthetic


def test_dir_attrib_event():
    event = DirAttribEvent(path_1)
    assert path_1 == event.src_path
    assert EVENT_TYPE_ATTRIB == event.event_type
    assert event.is_directory
    assert not event.is_synthetic


def test_file_system_event_handler_dispatch():
    dir_del_event = DirDeletedEvent("/path/blah.py")
    file_del_event = FileDeletedEvent("/path/blah.txt")
    dir_cre_event = DirCreatedEvent("/path/blah.py")
    file_cre_event = FileCreatedEvent("/path/blah.txt")
    file_cls_event = FileClosedEvent("/path/blah.txt")
    file_opened_event = FileOpenedEvent("/path/blah.txt")
    dir_mod_event = DirModifiedEvent("/path/blah.py")
    file_mod_event = FileModifiedEvent("/path/blah.txt")
    dir_mov_event = DirMovedEvent("/path/blah.py", "/path/blah")
    file_mov_event = FileMovedEvent("/path/blah.txt", "/path/blah")
    file_attr_event = FileAttribEvent('/path/blah.py')
    dir_attr_event = DirAttribEvent('/path/dir')

    all_events = [
        dir_mod_event,
        dir_del_event,
        dir_cre_event,
        dir_mov_event,
        file_mod_event,
        file_del_event,
        file_cre_event,
        file_mov_event,
        file_cls_event,
        file_attr_event,
        dir_attr_event,
        file_opened_event,
    ]

    class TestableEventHandler(FileSystemEventHandler):
        def on_any_event(self, event):
            pass

        def on_modified(self, event):
            assert event.event_type == EVENT_TYPE_MODIFIED

        def on_deleted(self, event):
            assert event.event_type == EVENT_TYPE_DELETED

        def on_moved(self, event):
            assert event.event_type == EVENT_TYPE_MOVED

        def on_created(self, event):
            assert event.event_type == EVENT_TYPE_CREATED

        def on_closed(self, event):
            assert event.event_type == EVENT_TYPE_CLOSED

        def on_attrib(self, event):
            assert event.event_type == EVENT_TYPE_ATTRIB

        def on_opened(self, event):
            assert event.event_type == EVENT_TYPE_OPENED

    handler = TestableEventHandler()

    for event in all_events:
        assert not event.is_synthetic
        handler.dispatch(event)


def test_event_comparison():
    creation1 = FileCreatedEvent("foo")
    creation2 = FileCreatedEvent("foo")
    creation3 = FileCreatedEvent("bar")
    assert creation1 == creation2
    assert creation1 != creation3
    assert creation2 != creation3

    move1 = FileMovedEvent("a", "b")
    move2 = FileMovedEvent("a", "b")
    move3 = FileMovedEvent("a", "c")
    move4 = FileMovedEvent("b", "a")
    assert creation1 != move1  # type: ignore[comparison-overlap]
    assert move1 == move2
    assert move1 != move3
    assert move1 != move4
    assert move2 != move3
    assert move2 != move4
    assert move3 != move4
