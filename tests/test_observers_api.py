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

import time
from pathlib import Path

import pytest

from watchdog.events import LoggingEventHandler, FileModifiedEvent
from watchdog.observers.api import (
    BaseObserver,
    EventEmitter,
    ObservedWatch,
    EventDispatcher,
    EventQueue
)


def test_observer_constructor():
    ObservedWatch(Path('/foobar'), True)


def test_observer__eq__():
    watch1 = ObservedWatch('/foobar', True)
    watch2 = ObservedWatch('/foobar', True)
    watch_ne1 = ObservedWatch('/foo', True)
    watch_ne2 = ObservedWatch('/foobar', False)

    assert watch1 == watch2
    assert watch1.__eq__(watch2)
    assert not watch1.__eq__(watch_ne1)
    assert not watch1.__eq__(watch_ne2)


def test_observer__ne__():
    watch1 = ObservedWatch('/foobar', True)
    watch2 = ObservedWatch('/foobar', True)
    watch_ne1 = ObservedWatch('/foo', True)
    watch_ne2 = ObservedWatch('/foobar', False)

    assert not watch1.__ne__(watch2)
    assert watch1.__ne__(watch_ne1)
    assert watch1.__ne__(watch_ne2)


def test_observer__repr__():
    observed_watch = ObservedWatch('/foobar', True)
    repr_str = '<ObservedWatch: path=/foobar, is_recursive=True>'
    assert observed_watch.__repr__() == repr(observed_watch)
    assert repr(observed_watch) == repr_str


def test_event_emitter():
    event_queue = EventQueue()
    watch = ObservedWatch('/foobar', True)
    event_emitter = EventEmitter(event_queue, watch, timeout=1)
    event_emitter.queue_event(FileModifiedEvent('/foobar/blah'))


def test_event_dispatcher():
    event = FileModifiedEvent('/foobar')
    watch = ObservedWatch('/path', True)

    class TestableEventDispatcher(EventDispatcher):

        def dispatch_event(self, event, watch):
            assert True

    event_dispatcher = TestableEventDispatcher()
    event_dispatcher.event_queue.put((event, watch))
    event_dispatcher.start()
    time.sleep(1)
    event_dispatcher.stop()
    event_dispatcher.join()


def test_observer_basic():
    observer = BaseObserver(EventEmitter)
    handler = LoggingEventHandler()

    watch = observer.schedule(handler, '/foobar', True)
    observer.add_handler_for_watch(handler, watch)
    observer.add_handler_for_watch(handler, watch)
    observer.remove_handler_for_watch(handler, watch)
    with pytest.raises(KeyError):
        observer.remove_handler_for_watch(handler, watch)
    observer.unschedule(watch)
    with pytest.raises(KeyError):
        observer.unschedule(watch)

    watch = observer.schedule(handler, '/foobar', True)
    observer.event_queue.put((FileModifiedEvent('/foobar'), watch))
    observer.start()
    time.sleep(1)
    observer.unschedule_all()
    observer.stop()
    observer.join()
