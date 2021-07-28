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

import pytest
import watchdog.events as events
from watchdog.utils.bricks import SkipRepeatsQueue

from .markers import cpython_only


def basic_actions():
    q = SkipRepeatsQueue()

    e1 = (2, 'fred')
    e2 = (2, 'george')
    e3 = (4, 'sally')

    q.put(e1)
    q.put(e2)
    q.put(e3)

    assert e1 == q.get()
    assert e2 == q.get()
    assert e3 == q.get()
    assert q.empty()


def test_basic_queue():
    basic_actions()


def test_allow_nonconsecutive():
    q = SkipRepeatsQueue()

    e1 = (2, 'fred')
    e2 = (2, 'george')

    q.put(e1)
    q.put(e2)
    q.put(e1)       # repeat the first entry

    assert e1 == q.get()
    assert e2 == q.get()
    assert e1 == q.get()
    assert q.empty()


def test_put_with_watchdog_events():
    # FileSystemEvent.__ne__() uses the key property without
    # doing any type checking. Since _last_item is set to
    # None in __init__(), an AttributeError is raised when
    # FileSystemEvent.__ne__() tries to use None.key
    queue = SkipRepeatsQueue()
    dummy_file = 'dummy.txt'
    event = events.FileCreatedEvent(dummy_file)
    queue.put(event)
    assert queue.get() is event


def test_prevent_consecutive():
    q = SkipRepeatsQueue()

    e1 = (2, 'fred')
    e2 = (2, 'george')

    q.put(e1)
    q.put(e1)  # repeat the first entry (this shouldn't get added)
    q.put(e2)

    assert e1 == q.get()
    assert e2 == q.get()
    assert q.empty()


def test_consecutives_allowed_across_empties():
    q = SkipRepeatsQueue()

    e1 = (2, 'fred')

    q.put(e1)
    q.put(e1)   # repeat the first entry (this shouldn't get added)

    assert e1 == q.get()
    assert q.empty()

    q.put(e1)  # this repeat is allowed because 'last' added is now gone from queue
    assert e1 == q.get()
    assert q.empty()


@cpython_only
def test_eventlet_monkey_patching():
    try:
        import eventlet
    except Exception:
        pytest.skip("eventlet not installed")

    eventlet.monkey_patch()
    basic_actions()
