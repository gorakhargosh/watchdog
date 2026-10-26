from __future__ import annotations

import itertools
import queue
import threading
from time import monotonic

import pytest

from watchdog import events
from watchdog.utils import bricks
from watchdog.utils.bricks import SkipRepeatsQueue


def test_basic_queue():
    q = SkipRepeatsQueue()

    e1 = (2, "fred")
    e2 = (2, "george")
    e3 = (4, "sally")

    q.put(e1)
    q.put(e2)
    q.put(e3)

    assert e1 == q.get()
    assert e2 == q.get()
    assert e3 == q.get()
    assert q.empty()


@pytest.mark.parametrize("item", [None, 0, False, ""])
def test_consecutive_false_items(item):
    q = SkipRepeatsQueue()
    q.put(item)
    q.put(item)
    assert q.qsize() == 1
    assert q.unfinished_tasks == 1
    assert q.get_nowait() is item
    q.task_done()
    q.join()
    assert q.empty()

    q.put(item)
    assert q.qsize() == 1
    assert q.get_nowait() is item
    q.task_done()
    q.join()


def test_allow_nonconsecutive():
    q = SkipRepeatsQueue()

    e1 = (2, "fred")
    e2 = (2, "george")

    q.put(e1)
    q.put(e2)
    q.put(e1)  # repeat the first entry

    assert e1 == q.get()
    assert e2 == q.get()
    assert e1 == q.get()
    assert q.empty()


def test_put_with_watchdog_events():
    # FileSystemEvent.__ne__() uses the key property without
    # doing any type checking. Since _last_item is set to
    # an empty sentinel in __init__(), an AttributeError would be raised when
    # FileSystemEvent.__ne__() tries to access the sentinel's key.
    queue = SkipRepeatsQueue()
    dummy_file = "dummy.txt"
    event = events.FileCreatedEvent(dummy_file)
    queue.put(event)
    assert queue.get() is event


def test_prevent_consecutive():
    q = SkipRepeatsQueue()

    e1 = (2, "fred")
    e2 = (2, "george")

    q.put(e1)
    q.put(e1)  # repeat the first entry (this shouldn't get added)
    q.put(e2)

    assert e1 == q.get()
    assert e2 == q.get()
    assert q.empty()


def test_consecutives_allowed_across_empties():
    q = SkipRepeatsQueue()

    e1 = (2, "fred")

    q.put(e1)
    q.put(e1)  # repeat the first entry (this shouldn't get added)

    assert e1 == q.get()
    assert q.empty()

    q.put(e1)  # this repeat is allowed because 'last' added is now gone from queue
    assert e1 == q.get()
    assert q.empty()


@pytest.mark.parametrize("item", [(1, "same"), events.FileCreatedEvent("same.txt")])
def test_concurrent_puts_skip_equal_items(monkeypatch, item):
    q = SkipRepeatsQueue()
    first_arrived = threading.Event()
    second_arrived = threading.Event()
    producer_lock = threading.Lock()
    failures = []
    original_put = queue.Queue.put

    class ObservedLock:
        def acquire(self, *args, **kwargs):
            if threading.current_thread() is second:
                second_arrived.set()
            return producer_lock.acquire(*args, **kwargs)

        def release(self):
            producer_lock.release()

        def __enter__(self):
            self.acquire()

        def __exit__(self, *args):
            self.release()

    def put(self, item, block=True, timeout=None):  # noqa: FBT002
        # Original: both producers reach Queue.put after the duplicate check.
        # Fixed: the second reaches the producer lock while the first is paused.
        if threading.current_thread() is first:
            first_arrived.set()
            assert second_arrived.wait(5)
        else:
            second_arrived.set()
        original_put(self, item, block, timeout)

    def produce():
        try:
            q.put(item)
        except Exception as exc:
            failures.append(exc)

    # Install the observation hook on either version, without requiring the
    # original implementation to have a producer lock.
    monkeypatch.setattr(q, "_put_lock", ObservedLock(), raising=False)
    monkeypatch.setattr(queue.Queue, "put", put)
    first = threading.Thread(target=produce)
    second = threading.Thread(target=produce)
    first.start()
    ready = first_arrived.wait(5)
    second.start()
    for thread in (first, second):
        thread.join(6)
    assert ready
    assert not first.is_alive()
    assert not second.is_alive()
    assert not failures
    assert q.qsize() == 1
    assert q.unfinished_tasks == 1
    assert q.get_nowait() == item
    assert q.empty()
    q.task_done()
    q.join()


def test_duplicate_task_accounting():
    q = SkipRepeatsQueue()
    q.put((1, "same"))
    q.put((1, "same"))
    assert q.unfinished_tasks == 1
    assert q.get_nowait() == (1, "same")
    q.task_done()
    q.join()
    assert q.unfinished_tasks == 0
    with pytest.raises(ValueError, match="task_done"):
        q.task_done()


@pytest.mark.parametrize("kwargs", [{"block": False}, {"timeout": 0}, {"timeout": 0.01}])
def test_bounded_queue_skips_duplicates(kwargs):
    q = SkipRepeatsQueue(maxsize=1)
    q.put("same")
    q.put("same", **kwargs)
    assert q.qsize() == q.unfinished_tasks == 1


@pytest.mark.parametrize("kwargs", [{"block": False}, {"timeout": 0}, {"timeout": 0.01}])
def test_bounded_queue_full(kwargs):
    q = SkipRepeatsQueue(maxsize=1)
    q.put("first")
    with pytest.raises(queue.Full):
        q.put("second", **kwargs)
    assert q.qsize() == q.unfinished_tasks == 1
    assert q.get_nowait() == "first"


def test_bounded_queue_negative_timeout():
    q = SkipRepeatsQueue(maxsize=1)
    with pytest.raises(ValueError, match="timeout"):
        q.put("first", timeout=-1)
    assert q.empty()
    assert q.unfinished_tasks == 0


def test_bounded_queue_blocking_put(monkeypatch):
    q = SkipRepeatsQueue(maxsize=1)
    q.put("first")
    waiting = threading.Event()
    failures = []
    original_wait = q.not_full.wait

    def wait(timeout=None):
        waiting.set()
        return original_wait(timeout)

    def produce():
        try:
            q.put("second", timeout=5)
        except Exception as exc:
            failures.append(exc)

    monkeypatch.setattr(q.not_full, "wait", wait)
    producer = threading.Thread(target=produce)
    producer.start()
    try:
        assert waiting.wait(5)
        assert q.qsize() == 1
        assert q.get_nowait() == "first"
        q.task_done()
    finally:
        producer.join(6)
    assert not producer.is_alive()
    assert not failures
    assert q.unfinished_tasks == 1
    assert q.get_nowait() == "second"
    q.task_done()
    q.join()


@pytest.mark.parametrize(
    ("kwargs", "exception", "timeout"),
    [
        ({"block": False}, queue.Full, 0),
        ({"timeout": 0}, queue.Full, 0),
        ({"timeout": 0.01}, queue.Full, 0.01),
        ({"timeout": -1}, ValueError, 0),
    ],
)
def test_put_deadline_with_waiting_producer(monkeypatch, kwargs, exception, timeout):
    q = SkipRepeatsQueue(maxsize=1)
    q.put("first")
    waiting = threading.Event()
    completed = threading.Event()
    failures = []
    results = []
    original_wait = q.not_full.wait

    def wait(timeout=None):
        waiting.set()
        return original_wait(timeout)

    def produce():
        try:
            q.put("second", timeout=5)
        except Exception as exc:
            failures.append(exc)

    def contend():
        started = monotonic()
        try:
            q.put("third", **kwargs)
        except Exception as exc:
            results.append((exc, monotonic() - started))
        finally:
            completed.set()

    monkeypatch.setattr(q.not_full, "wait", wait)
    producer = threading.Thread(target=produce)
    contender = threading.Thread(target=contend)
    producer.start()
    ready = waiting.wait(2)
    contender.start()
    returned_before_space = completed.wait(1)
    try:
        assert ready
        assert returned_before_space
        assert len(results) == 1
        error, elapsed = results[0]
        assert isinstance(error, exception)
        # A generous scheduler allowance; the holder is still blocked, so the
        # result cannot depend on a consumer eventually freeing queue capacity.
        assert elapsed < timeout + 0.5
        assert q.qsize() == q.unfinished_tasks == 1
    finally:
        assert q.get_nowait() == "first"
        q.task_done()
        producer.join(6)
        contender.join(6)
    assert not producer.is_alive()
    assert not contender.is_alive()
    assert not failures
    assert q.get_nowait() == "second"
    q.task_done()
    q.join()


@pytest.mark.parametrize("initial", [None, "same", "other"])
def test_negative_timeout_preserves_queue(initial):
    q = SkipRepeatsQueue(maxsize=1)
    if initial is not None:
        q.put(initial)
    before = list(q.queue)
    unfinished = q.unfinished_tasks
    with pytest.raises(ValueError, match="timeout"):
        q.put("same", timeout=-0.01)
    assert list(q.queue) == before
    assert q.unfinished_tasks == unfinished


@pytest.mark.parametrize(
    ("maxsize", "initial", "block", "timeout"),
    [
        case
        for case in itertools.product([0, 1], [None, "other"], [False, True], [None, 0, -1])
        # A blocking put without timeout on a full queue never returns.
        if case != (1, "other", True, None)
    ]
    + [
        (1, None, True, threading.TIMEOUT_MAX * 2),
        (1, None, True, float("inf")),
    ],
)
def test_put_arguments_match_base_queue(maxsize, initial, block, timeout):
    def outcome(q):
        if initial is not None:
            q.put(initial)
        try:
            q.put("new", block, timeout)
        except (queue.Full, ValueError) as exc:
            result = type(exc)
        else:
            result = None
        return result, list(q.queue), q.unfinished_tasks

    assert outcome(SkipRepeatsQueue(maxsize)) == outcome(queue.Queue(maxsize))


def test_unbounded_nonblocking_put_waits_for_producer_lock(monkeypatch):
    q = SkipRepeatsQueue()
    lock = threading.Lock()
    monkeypatch.setattr(q, "_put_lock", lock)
    completed = threading.Event()
    failures = []

    def produce():
        try:
            q.put("first", block=False)
        except Exception as exc:
            failures.append(exc)
        finally:
            completed.set()

    lock.acquire()
    producer = threading.Thread(target=produce)
    try:
        producer.start()
        assert not completed.wait(0.05)
    finally:
        lock.release()
    producer.join(5)
    assert not producer.is_alive()
    assert not failures
    assert q.get_nowait() == "first"


def test_lock_and_capacity_share_timeout(monkeypatch):
    q = SkipRepeatsQueue(maxsize=1)
    q.put("first")
    elapsed = 0.0
    waits = []

    class DelayedLock:
        def acquire(self, *args, **kwargs):
            nonlocal elapsed
            elapsed += 0.007
            return True

        def release(self):
            pass

        def __enter__(self):
            self.acquire()

        def __exit__(self, *args):
            self.release()

    def wait(timeout):
        nonlocal elapsed
        waits.append(timeout)
        elapsed += timeout

    monkeypatch.setattr(q, "_put_lock", DelayedLock(), raising=False)
    monkeypatch.setattr(bricks, "monotonic", lambda: elapsed, raising=False)
    monkeypatch.setattr(queue, "time", lambda: elapsed)
    monkeypatch.setattr(q.not_full, "wait", wait)
    with pytest.raises(queue.Full):
        q.put("second", timeout=0.01)
    assert elapsed == pytest.approx(0.01)
    assert waits == pytest.approx([0.003])
    assert q.qsize() == q.unfinished_tasks == 1
    assert q.get_nowait() == "first"


def test_nonblocking_put_can_fail_on_producer_contention(monkeypatch):
    q = SkipRepeatsQueue(maxsize=2)
    lock = threading.Lock()
    monkeypatch.setattr(q, "_put_lock", lock)
    lock.acquire()
    try:
        with pytest.raises(queue.Full):
            q.put("first", block=False)
    finally:
        lock.release()
    assert q.empty()
    assert q.unfinished_tasks == 0
    q.put("first", block=False)
    assert q.get_nowait() == "first"
    q.task_done()
    q.join()
