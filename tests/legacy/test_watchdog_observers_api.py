#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc.
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
from tests import unittest

from watchdog.observers.api import (
    BaseObserver,
    EventEmitter,
    ObservedWatch,
    EventDispatcher,
    EventQueue
)

from watchdog.events import LoggingEventHandler, FileModifiedEvent


class TestObservedWatch(unittest.TestCase):

    def test___eq__(self):
        watch1 = ObservedWatch('/foobar', True)
        watch2 = ObservedWatch('/foobar', True)
        watch_ne1 = ObservedWatch('/foo', True)
        watch_ne2 = ObservedWatch('/foobar', False)

        self.assertTrue(watch1.__eq__(watch2))
        self.assertFalse(watch1.__eq__(watch_ne1))
        self.assertFalse(watch1.__eq__(watch_ne2))

    def test___ne__(self):
        watch1 = ObservedWatch('/foobar', True)
        watch2 = ObservedWatch('/foobar', True)
        watch_ne1 = ObservedWatch('/foo', True)
        watch_ne2 = ObservedWatch('/foobar', False)

        self.assertFalse(watch1.__ne__(watch2))
        self.assertTrue(watch1.__ne__(watch_ne1))
        self.assertTrue(watch1.__ne__(watch_ne2))

    def test___repr__(self):
        observed_watch = ObservedWatch('/foobar', True)
        self.assertEqual('<ObservedWatch: path=' + '/foobar' + ', is_recursive=True>',
                         observed_watch.__repr__())


class TestEventEmitter(unittest.TestCase):

    def test___init__(self):
        event_queue = EventQueue()
        watch = ObservedWatch('/foobar', True)
        event_emitter = EventEmitter(event_queue, watch, timeout=1)
        event_emitter.queue_event(FileModifiedEvent('/foobar/blah'))


class TestEventDispatcher(unittest.TestCase):

    def test_dispatch_event(self):
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


class TestBaseObserver(unittest.TestCase):

    def test_basic(self):
        observer = BaseObserver(EventEmitter)
        handler = LoggingEventHandler()

        watch = observer.schedule(handler, '/foobar', True)
        observer.add_handler_for_watch(handler, watch)
        observer.add_handler_for_watch(handler, watch)
        observer.remove_handler_for_watch(handler, watch)
        self.assertRaises(KeyError,
                          observer.remove_handler_for_watch, handler, watch)
        observer.unschedule(watch)
        self.assertRaises(KeyError, observer.unschedule, watch)

        watch = observer.schedule(handler, '/foobar', True)
        observer.event_queue.put((FileModifiedEvent('/foobar'), watch))
        observer.start()
        time.sleep(1)
        observer.unschedule_all()
        observer.stop()
