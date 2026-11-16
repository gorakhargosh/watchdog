from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from watchdog.utils import delayed_queue
from watchdog.utils.delayed_queue import DelayedQueue


@pytest.mark.flaky(max_runs=5, min_passes=1)
def test_delayed_get():
    delay = 2
    q = DelayedQueue[str](delay)
    q.put("", delay=True)
    inserted = time.monotonic()
    q.get()
    elapsed = time.monotonic() - inserted
    # The lower bound is what proves the delay was honoured. The upper bound
    # only has to catch a doubled delay or a blocking get(), so leave it
    # generous: CI runs with `pytest -n auto`, and a worker can be descheduled
    # for a moment right after `sleep()` returns. Wall-clock time is not
    # suitable here, the queue itself relies on the monotonic clock.
    assert delay - 0.01 < elapsed < delay * 1.5


@pytest.mark.flaky(max_runs=5, min_passes=1)
def test_nondelayed_get():
    q = DelayedQueue[str](2)
    q.put("")
    inserted = time.monotonic()
    q.get()
    elapsed = time.monotonic() - inserted
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


@pytest.mark.parametrize("remove_while_sleeping", [False, True])
def test_mixed_delays(monkeypatch, remove_while_sleeping):
    q = DelayedQueue[str](0.25)
    q.put("a", delay=False)
    q.put("b", delay=True)
    q.put("c", delay=False)

    if remove_while_sleeping:
        entered_wait = threading.Event()
        allow_wakeup = threading.Event()
        orig_sleep = delayed_queue.time.sleep

        def synchronized_sleep(secs: float) -> None:
            entered_wait.set()
            assert allow_wakeup.wait(timeout=2.0)
            orig_sleep(secs)

        monkeypatch.setattr(delayed_queue.time, "sleep", synchronized_sleep)

        def _consumer(results: list[str | None]) -> None:
            results.append(q.get())  # "a"
            results.append(q.get())  # enters sleep on "b", then returns "c" after "b" is removed

        results: list[str | None] = []
        t = threading.Thread(target=_consumer, args=(results,), daemon=True)
        t.start()
        assert entered_wait.wait(timeout=2.0)
        assert q.remove(lambda x: x == "b") == "b"
        allow_wakeup.set()
        t.join(timeout=2.0)
        assert not t.is_alive()
        assert results == ["a", "c"]
    else:
        q.delay = 0.01
        assert [q.get() for _ in range(3)] == ["a", "b", "c"]

    q.close()
    assert q.get() is None
