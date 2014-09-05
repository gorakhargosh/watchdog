# -*- coding: utf-8 -*-
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

from __future__ import unicode_literals

import pytest
from watchdog.observers.api import EventEmitter, BaseObserver


@pytest.fixture()
def observer(request):
    observer = BaseObserver(EventEmitter)
    def finalizer():
        try:
            observer.stop()
            observer.join(5)
        except:
            pass
    request.addfinalizer(finalizer)
    return observer


def test_schedule_should_start_emitter_if_running(observer):
    observer.start()
    observer.schedule(None, '')
    (emitter,) = observer.emitters
    assert emitter.is_alive()


def test_schedule_should_not_start_emitter_if_not_running(observer):
    observer.schedule(None, '')
    (emitter,) = observer.emitters
    assert not emitter.is_alive()


def test_start_should_start_emitter(observer):
    observer.schedule(None, '')
    observer.start()
    (emitter,) = observer.emitters
    assert emitter.is_alive()


def test_stop_should_stop_emitter(observer):
    observer.schedule(None, '')
    observer.start()
    (emitter,) = observer.emitters
    assert emitter.is_alive()
    observer.stop()
    observer.join()
    assert not observer.is_alive()
    assert not emitter.is_alive()
