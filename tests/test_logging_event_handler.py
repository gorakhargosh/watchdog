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
    LoggingEventHandler,
    EVENT_TYPE_MODIFIED,
    EVENT_TYPE_CREATED,
    EVENT_TYPE_DELETED,
    EVENT_TYPE_MOVED,
)

path_1 = '/path/xyz'
path_2 = '/path/abc'


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


def test_logging_event_handler_dispatch():
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
