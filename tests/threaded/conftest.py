from __future__ import annotations

import contextlib
import gc
import os
import threading
from functools import partial

import pytest

from tests.utils import ExpectEvent, Helper, P, StartWatching, TestEventQueue


@pytest.fixture(autouse=True)
def _no_thread_leaks():
    """
    A fixture override, disables thread counter from parent folder
    """


