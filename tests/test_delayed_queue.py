# coding: utf-8
#
# Copyright 2014 Thomas Amland <thomas.amland@gmail.com>
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

from time import time

import pytest
from watchdog.utils.delayed_queue import DelayedQueue


@pytest.mark.flaky(max_runs=5, min_passes=1)
def test_delayed_get():
    q = DelayedQueue(2)
    q.put("", True)
    inserted = time()
    q.get()
    elapsed = time() - inserted
    # 2.10 instead of 2.05 for slow macOS slaves on Travis
    assert 2.10 > elapsed > 1.99


@pytest.mark.flaky(max_runs=5, min_passes=1)
def test_nondelayed_get():
    q = DelayedQueue(2)
    q.put("", False)
    inserted = time()
    q.get()
    elapsed = time() - inserted
    # Far less than 1 second
    assert elapsed < 1
