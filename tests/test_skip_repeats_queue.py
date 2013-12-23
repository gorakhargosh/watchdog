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

from tests import unittest
from watchdog.utils.bricks import SkipRepeatsQueue


class TestSkipRepeatsQueue(unittest.TestCase):

    def test_basic_queue(self):
        q = SkipRepeatsQueue()

        e1 = (2, 'fred')
        e2 = (2, 'george')
        e3 = (4, 'sally')

        q.put(e1)
        q.put(e2)
        q.put(e3)

        self.assertEqual(e1, q.get())
        self.assertEqual(e2, q.get())
        self.assertEqual(e3, q.get())
        self.assertTrue(q.empty())

    def test_allow_nonconsecutive(self):
        q = SkipRepeatsQueue()

        e1 = (2, 'fred')
        e2 = (2, 'george')

        q.put(e1)
        q.put(e2)
        q.put(e1)       # repeat the first entry

        self.assertEqual(e1, q.get())
        self.assertEqual(e2, q.get())
        self.assertEqual(e1, q.get())
        self.assertTrue(q.empty())

    def test_prevent_consecutive(self):
        q = SkipRepeatsQueue()

        e1 = (2, 'fred')
        e2 = (2, 'george')

        q.put(e1)
        q.put(e1)       # repeat the first entry (this shouldn't get added)
        q.put(e2)

        self.assertEqual(e1, q.get())
        self.assertEqual(e2, q.get())
        self.assertTrue(q.empty())

    def test_consecutives_allowed_across_empties(self):
        q = SkipRepeatsQueue()

        e1 = (2, 'fred')

        q.put(e1)
        q.put(e1)       # repeat the first entry (this shouldn't get added)

        self.assertEqual(e1, q.get())
        self.assertTrue(q.empty())

        q.put(e1)       # this repeat is allowed because 'last' added is now gone from queue
        self.assertEqual(e1, q.get())
        self.assertTrue(q.empty())
