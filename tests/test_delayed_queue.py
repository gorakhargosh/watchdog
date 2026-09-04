from __future__ import annotations

from time import time

import pytest

from watchdog.utils.delayed_queue import DelayedQueue


@pytest.mark.flaky(max_runs=5, min_passes=1)
def test_delayed_get():
    q = DelayedQueue[str](2)
    q.put("", delay=True)
    inserted = time()
    q.get()
    elapsed = time() - inserted
    # Allow a reasonable upper bound for busy/slow CI runners
    assert 2.50 > elapsed > 1.99


@pytest.mark.flaky(max_runs=5, min_passes=1)
def test_nondelayed_get():
    q = DelayedQueue[str](2)
    q.put("")
    inserted = time()
    q.get()
    elapsed = time() - inserted
    # Far less than 1 second
    assert elapsed < 1
