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

import threading

import pytest

from watchdog.events import FileSystemEventHandler, FileModifiedEvent
from watchdog.observers.api import EventEmitter, BaseObserver


@pytest.fixture
def observer():
    obs = BaseObserver(EventEmitter)
    yield obs
    obs.stop()
    try:
        obs.join()
    except RuntimeError:
        pass


@pytest.fixture
def observer2():
    obs = BaseObserver(EventEmitter)
    yield obs
    obs.stop()
    try:
        obs.join()
    except RuntimeError:
        pass


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


def test_unschedule_self(observer):
    """
    Tests that unscheduling a watch from within an event handler correctly
    correctly unregisters emitter and handler without deadlocking.
    """
    class EventHandler(FileSystemEventHandler):
        def on_modified(self, event):
            observer.unschedule(watch)
            unschedule_finished.set()

    unschedule_finished = threading.Event()
    watch = observer.schedule(EventHandler(), '')
    observer.start()

    (emitter,) = observer.emitters
    emitter.queue_event(FileModifiedEvent(''))

    assert unschedule_finished.wait()
    assert len(observer.emitters) == 0


def test_schedule_after_unschedule_all(observer):
    observer.start()
    observer.schedule(None, '')
    assert len(observer.emitters) == 1

    observer.unschedule_all()
    assert len(observer.emitters) == 0

    observer.schedule(None, '')
    assert len(observer.emitters) == 1


def test_2_observers_on_the_same_path(observer, observer2):
    assert observer is not observer2

    observer.schedule(None, '')
    assert len(observer.emitters) == 1

    observer2.schedule(None, '')
    assert len(observer2.emitters) == 1


def test_start_failure_should_not_prevent_further_try(monkeypatch, observer):
    observer.schedule(None, '')
    emitters = observer.emitters
    assert len(emitters) == 1

    # Make the emitter to fail on start()

    def mocked_start():
        raise OSError()

    emitter = next(iter(emitters))
    monkeypatch.setattr(emitter, "start", mocked_start)
    with pytest.raises(OSError):
        observer.start()
    # The emitter should be removed from the list
    assert len(observer.emitters) == 0

    # Restoring the original behavior should work like there never be emitters
    monkeypatch.undo()
    observer.start()
    assert len(observer.emitters) == 0

    # Re-schduling the watch should work
    observer.schedule(None, '')
    assert len(observer.emitters) == 1
