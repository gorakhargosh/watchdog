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
"""
Tests for generic observer, generic emitter, generic event dispatcher...etc
"""
import tempfile
import threading

from watchdog.observers.api import BaseObserver, EventEmitter, ObservedWatch

from tests import WatchdogTestCase


class DummyEventEmitter(EventEmitter):
    """
    Simple event emitter implementation to help with testing generic
    event emitters.
    """

    _ready = None

    @property
    def ready(self):
        """
        Delay `ready` for the next call.
        """
        if self._ready is None:
            self._ready = object()
            return False
        return True



class TestEventEmitter(WatchdogTestCase):
    """
    Unit test for EventEmitter.
    """

    def setUp(self):
        super(TestEventEmitter, self).setUp()
        self.queue = []
        watch = ObservedWatch(path=tempfile.tempdir, recursive=False)
        self.sut = DummyEventEmitter(self.queue, watch, timeout=0)

    def tearDown(self):
        if self.sut.isAlive():
            self.sut.stop()
            self.sut.join()
        super(TestEventEmitter, self).setUp()

    def test_start_blocking(self):
        """
        It will start the emitter and for it to finish the start.
        """
        self.sut.start()

        self.assertTrue(self.sut.ready)


class DummyObserver(BaseObserver):
    """
    Dummy implementation to help with testing the TestBaseObserver.
    """


class TestBaseObserver(WatchdogTestCase):
    """
    Unit tests for BaseObserver.
    """

    def setUp(self):
        super(TestBaseObserver, self).setUp()
        self.sut = DummyObserver(DummyEventEmitter, timeout=0)

    def tearDown(self):
        if self.sut.isAlive():
            self.sut.stop()
            self.sut.join()
        super(TestBaseObserver, self).tearDown()

    def test_schedule_not_started(self):
        """
        It does not start the emitter when observer is not started yet.
        """
        handler = self.sut.schedule('handler', tempfile.tempdir)

        emitter = handler._emitter

        self.assertFalse(emitter.isAlive())

    def test_schedule_started(self):
        """
        When observer is already started, it starts the emitter when
        it is scheduled.
        """
        self.sut.start()

        handler = self.sut.schedule('handler', tempfile.tempdir)
        emitter = handler._emitter

        self.assertTrue(emitter.isAlive())
        self.assertTrue(emitter.ready)

    def test_start(self):
        """
        It starts the attached emitters.
        """
        handler = self.sut.schedule('handler', tempfile.tempdir)
        emitter = handler._emitter
        self.assertFalse(emitter.isAlive())

        self.sut.start_blocking()

        self.assertTrue(emitter.isAlive())
        self.assertTrue(emitter.ready)

    def test_unschedule_not_started(self):
        """
        Removes the scheduled emitter.
        """
        handler = self.sut.schedule('handler', tempfile.tempdir)

        self.sut.unschedule(handler)

    def test_unschedule_all_not_started(self):
        """
        Removes all scheduled emitters.
        """
        handler = self.sut.schedule('handler', tempfile.tempdir)

        self.sut.unschedule_all()
