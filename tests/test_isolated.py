import pytest
import importlib

from .markers import cpython_only
from .utils import run_isolated_test


@cpython_only
def test_observer_stops_in_eventlet():
    if not importlib.util.find_spec('eventlet'):
        pytest.skip("eventlet not installed")

    run_isolated_test('eventlet_observer_stops.py')


@cpython_only
def test_eventlet_skip_repeat_queue():
    if not importlib.util.find_spec('eventlet'):
        pytest.skip("eventlet not installed")

    run_isolated_test('eventlet_skip_repeat_queue.py')
