import pytest
import importlib

from watchdog.utils import platform

from .utils import run_isolated_test


# Kqueue isn't supported by Eventlet, so BSD is out
# Current usage ReadDirectoryChangesW on Windows is blocking, though async may be possible
@pytest.mark.skipif(not platform.is_linux(), reason="Eventlet only supported in Linux")
def test_observer_stops_in_eventlet():
    if not importlib.util.find_spec('eventlet'):
        pytest.skip("eventlet not installed")

    run_isolated_test('eventlet_observer_stops.py')


@pytest.mark.skipif(not platform.is_linux(), reason="Eventlet only supported in Linux")
def test_eventlet_skip_repeat_queue():
    if not importlib.util.find_spec('eventlet'):
        pytest.skip("eventlet not installed")

    run_isolated_test('eventlet_skip_repeat_queue.py')
