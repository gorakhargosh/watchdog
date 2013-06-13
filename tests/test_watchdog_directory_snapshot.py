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

#try:
#  import queue  # IGNORE:F0401
#except ImportError:
#  import Queue as queue  # IGNORE:F0401

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

from watchdog.utils.dirsnapshot import DirectorySnapshot

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
    global temp_dir

  def tearDown(self):
    global temp_dir
    rm(temp_dir, True)
    pass


  def verify_equivalent_sequences(self, seq1, seq2):
    self.assertEqual(len(seq1), len(seq2))
    for item in seq1:
      self.assertTrue(item in seq2)

  def verify(self, expected, changes):
    all_attributes = ['files_created', 'files_deleted', 'files_modified', 'files_moved',
                      'dirs_created', 'dirs_deleted', 'dirs_modified', 'dirs_moved',]
    comp_dict = dict((attr, getattr(changes, attr)) for attr in all_attributes)
    for attr in all_attributes:
      got = getattr(changes, attr)
      if attr in expected:
        self.verify_equivalent_sequences(expected[attr], got)
      else:
        self.assertEqual(0, len(got), "Actually got: %r when expected: %r" % (comp_dict, expected))


  def test_mv_file_to_other_sibling_folder(self):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))

    snapBefore = DirectorySnapshot(temp_dir)
    sleep(1)

    mv(p('dir1', 'a'), p('dir2', 'x'))

    snapAfter = DirectorySnapshot(temp_dir)
    changes = snapAfter - snapBefore

    expected = {
      'files_moved': [ (p('dir1', 'a'), p('dir2', 'x')), ],
      'dirs_modified': [ p('dir1'), p('dir2'), ]
    }

    self.verify(expected, changes)

  def test_replace_same_folder(self):
    mkdir(p('dir1'))
    touch(p('dir1', 'a'))
    touch(p('dir1', 'b'))

    snapBefore = DirectorySnapshot(temp_dir)
    sleep(1)

    mv(p('dir1', 'a'), p('dir1', 'b'))

    snapAfter = DirectorySnapshot(temp_dir)
    changes = snapAfter - snapBefore

    expected = {
      'files_moved': [ (p('dir1', 'a'), p('dir1', 'b')), ],
      'dirs_modified': [ p('dir1'), ]
    }

    self.verify(expected, changes)


  def test_replace_in_other_folder(self):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    touch(p('dir2', 'a'))

    snapBefore = DirectorySnapshot(temp_dir)
    sleep(1)

    # This case didn't work until the associated changes in disnapshot.py
    mv(p('dir1', 'a'), p('dir2', 'a'))

    snapAfter = DirectorySnapshot(temp_dir)
    changes = snapAfter - snapBefore

    expected = {
      'files_moved': [ (p('dir1', 'a'), p('dir2', 'a')), ],
      'dirs_modified': [ p('dir1'), p('dir2'), ]
    }

    self.verify(expected, changes)
