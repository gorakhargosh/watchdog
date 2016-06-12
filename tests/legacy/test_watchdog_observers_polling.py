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


import os
import sys
from tests import unittest

try:
    import queue  # IGNORE:F0401
except ImportError:
    import Queue as queue  # IGNORE:F0401

from time import sleep
from tests.shell import (
    mkdir,
    mkdtemp,
    touch,
    rm,
    mv
)

from watchdog.events import (
    DirModifiedEvent,
    DirCreatedEvent,
    FileCreatedEvent,
    FileMovedEvent,
    FileModifiedEvent,
    DirMovedEvent,
    FileDeletedEvent,
    DirDeletedEvent
)

from watchdog.observers.api import ObservedWatch
from watchdog.observers.polling import PollingEmitter as Emitter


temp_dir = mkdtemp()


def p(*args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return os.path.join(temp_dir, *args)


class TestPollingEmitter(unittest.TestCase):

    def setUp(self):
        self.event_queue = queue.Queue()
        self.watch = ObservedWatch(temp_dir, True)
        self.emitter = Emitter(self.event_queue, self.watch, timeout=0.2)

    def teardown(self):
        pass

    def test___init__(self):
        SLEEP_TIME = 0.4
        self.emitter.start()
        sleep(SLEEP_TIME)
        mkdir(p('project'))
        sleep(SLEEP_TIME)
        mkdir(p('project', 'blah'))
        sleep(SLEEP_TIME)
        touch(p('afile'))
        sleep(SLEEP_TIME)
        touch(p('fromfile'))
        sleep(SLEEP_TIME)
        mv(p('fromfile'), p('project', 'tofile'))
        sleep(SLEEP_TIME)
        touch(p('afile'))
        sleep(SLEEP_TIME)
        mv(p('project', 'blah'), p('project', 'boo'))
        sleep(SLEEP_TIME)
        rm(p('project'), recursive=True)
        sleep(SLEEP_TIME)
        rm(p('afile'))
        sleep(SLEEP_TIME)
        self.emitter.stop()

        # What we need here for the tests to pass is a collection type
        # that is:
        #   * unordered
        #   * non-unique
        # A multiset! Python's collections.Counter class seems appropriate.
        expected = set(
            [
                DirModifiedEvent(p()),
                DirCreatedEvent(p('project')),

                DirModifiedEvent(p('project')),
                DirCreatedEvent(p('project', 'blah')),

                FileCreatedEvent(p('afile')),
                DirModifiedEvent(p()),

                FileCreatedEvent(p('fromfile')),
                DirModifiedEvent(p()),

                DirModifiedEvent(p()),
                FileModifiedEvent(p('afile')),

                DirModifiedEvent(p('project')),

                DirModifiedEvent(p()),
                FileDeletedEvent(p('project', 'tofile')),
                DirDeletedEvent(p('project', 'boo')),
                DirDeletedEvent(p('project')),

                DirModifiedEvent(p()),
                FileDeletedEvent(p('afile')),
            ]
        )

        expected.add(FileMovedEvent(p('fromfile'), p('project', 'tofile')))
        expected.add(DirMovedEvent(p('project', 'blah'), p('project', 'boo')))

        got = set()
        while True:
            try:
                event, _ = self.event_queue.get_nowait()
                got.add(event)
            except queue.Empty:
                break

        self.assertEqual(expected, got)

    def test_delete_watched_dir(self):
        SLEEP_TIME = 0.4
        self.emitter.start()
        rm(p(''), recursive=True)
        sleep(SLEEP_TIME)
        self.emitter.stop()

        # What we need here for the tests to pass is a collection type
        # that is:
        #   * unordered
        #   * non-unique
        # A multiset! Python's collections.Counter class seems appropriate.
        expected = set(
            [

                DirDeletedEvent(os.path.dirname(p(''))),
            ]
        )

        got = set()
        while True:
            try:
                event, _ = self.event_queue.get_nowait()
                got.add(event)
            except queue.Empty:
                break

        self.assertEqual(expected, got)
