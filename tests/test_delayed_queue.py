from __future__ import annotations

from time import time
from types import SimpleNamespace

import pytest

from watchdog.utils import delayed_queue
from watchdog.utils.delayed_queue import DelayedQueue


@pytest.mark.flaky(max_runs=5, min_passes=1)
def test_delayed_get():
    q = DelayedQueue[str](2)
    q.put("", delay=True)
    inserted = time()
    q.get()
    elapsed = time() - inserted
    # 2.10 instead of 2.05 for slow macOS slaves on Travis
    assert 2.10 > elapsed > 1.99


@pytest.mark.flaky(max_runs=5, min_passes=1)
def test_nondelayed_get():
    q = DelayedQueue[str](2)
    q.put("")
    inserted = time()
    q.get()
    elapsed = time() - inserted
    # Far less than 1 second
    assert elapsed < 1


@pytest.mark.parametrize("clock_adjustment", [-3600, 0, 3600])
def test_delay_ignores_wall_clock_adjustments(monkeypatch, clock_adjustment):
    elapsed = 0.0
    wall_time = 10000.0
    sleeps = []

    def sleep(seconds):
        nonlocal elapsed, wall_time
        sleeps.append(seconds)
        elapsed += seconds
        wall_time += seconds

    clock = SimpleNamespace(monotonic=lambda: elapsed, time=lambda: wall_time, sleep=sleep)
    monkeypatch.setattr(delayed_queue, "time", clock)

    queue = DelayedQueue[str](1)
    queue.put("event", delay=True)
    elapsed += 0.25
    wall_time += 0.25 + clock_adjustment

    assert queue.get() == "event"
    assert sleeps == [0.75]


def test_delay_attribute():
    queue = DelayedQueue[str](2)
    assert queue.delay == 2


def test_deprecated_delay_sec_attribute():
    queue = DelayedQueue[str](2)

    with pytest.warns(DeprecationWarning, match="'delay_sec' is deprecated, use 'delay' instead") as record:
        assert queue.delay_sec == 2
    # The warning points at the caller, not at watchdog.
    assert record[0].filename == __file__

    with pytest.warns(DeprecationWarning, match="'delay_sec' is deprecated"):
        queue.delay_sec = 3
    assert queue.delay == 3
