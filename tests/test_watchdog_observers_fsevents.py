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
import unittest2

try:
  import queue  # IGNORE:F0401
except ImportError:
  import Queue as queue  # IGNORE:F0401

from time import sleep
from tests.shell import\
  mkdir,\
  mkdtemp,\
  touch,\
  rm,\
  mv

from watchdog.events import DirModifiedEvent, DirCreatedEvent,\
  FileCreatedEvent,\
  FileMovedEvent, FileModifiedEvent, DirMovedEvent, FileDeletedEvent,\
  DirDeletedEvent

from watchdog.observers.api import ObservedWatch
from watchdog.observers.fsevents import FSEventsEmitter as Emitter

temp_dir = None

def p(*args):
  """
  Convenience function to join the temporary directory path
  with the provided arguments.
  """
  return os.path.join(temp_dir, *args)


class TestPollingEmitterSimple(unittest2.TestCase):
  def setUp(self):
    global temp_dir
    temp_dir = mkdtemp()

  def start(self):
    sleep(0.5)
    self.event_queue = queue.Queue()
    global temp_dir
    self.watch = ObservedWatch(temp_dir, True)
    self.emitter = Emitter(self.event_queue, self.watch, timeout=0.2)
    self.emitter.start()
    sleep(0.5)

  def tearDown(self):
    global temp_dir
    rm(temp_dir, True)
    pass

  def collect_results(self):
    sleep(0.5)
    self.emitter.stop()

    got = []
    while True:
      try:
        event, _ = self.event_queue.get_nowait()
        got.append(event)
      except queue.Empty:
        break

    return got

  def fs(self, action):
    sleep(0.4)
    action()

  def test_mkdir(self):

    self.start()

    self.fs(lambda: mkdir(p('project')))

    expected = [
      DirModifiedEvent(p()),
      DirCreatedEvent(p('project')),
      ]

    got = self.collect_results()

    self.assertEqual(expected, got)


  def test_create_mv_a_b(self):

    touch(p('a'))

    self.start()

    self.fs(lambda: mv(p('a'), p('b')))

    expected = [
      FileMovedEvent(p('a'), p('b')),
      DirModifiedEvent(p()),
      ]

    got = self.collect_results()

    self.assertEqual(expected, got)


  def test_create_file(self):
    self.start()

    self.fs(lambda: touch(p('file')))

    expected = [
      FileCreatedEvent(p('file')),
      DirModifiedEvent(p()),
      ]

    got = self.collect_results()

    self.assertEqual(expected, got)