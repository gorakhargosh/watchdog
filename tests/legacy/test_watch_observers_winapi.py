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
from tests import unittest

try:
    import queue  # IGNORE:F0401
except ImportError:
    import Queue as queue  # IGNORE:F0401

from time import sleep

from tests.shell import (
    mkdir,
    mkdtemp,
    mv
)


from watchdog.events import (
    DirCreatedEvent,
    DirMovedEvent,
)

from watchdog.observers.api import ObservedWatch
from watchdog.utils import platform

if platform.is_windows():
    from watchdog.observers.read_directory_changes import WindowsApiEmitter as Emitter

    temp_dir = mkdtemp()

    def p(*args):
        """
        Convenience function to join the temporary directory path
        with the provided arguments.
        """
        return os.path.join(temp_dir, *args)

    class TestWindowsApiEmitter(unittest.TestCase):

        def setUp(self):
            self.event_queue = queue.Queue()
            self.watch = ObservedWatch(temp_dir, True)
            self.emitter = Emitter(self.event_queue, self.watch, timeout=0.2)

        def teardown(self):
            pass

        def test___init__(self):
            SLEEP_TIME = 1
            self.emitter.start()
            sleep(SLEEP_TIME)
            mkdir(p('fromdir'))
            sleep(SLEEP_TIME)
            mv(p('fromdir'), p('todir'))
            sleep(SLEEP_TIME)
            self.emitter.stop()

            # What we need here for the tests to pass is a collection type
            # that is:
            #   * unordered
            #   * non-unique
            # A multiset! Python's collections.Counter class seems appropriate.
            expected = set([
                           DirCreatedEvent(p('fromdir')),
                           DirMovedEvent(p('fromdir'), p('todir')),
                           ])
            got = set()

            while True:
                try:
                    event, _ = self.event_queue.get_nowait()
                    got.add(event)
                except queue.Empty:
                    break

            print(got)
            self.assertEqual(expected, got)
