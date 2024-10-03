from __future__ import annotations

import pytest

from watchdog.utils import platform

if not platform.is_linux():
    pytest.skip("GNU/Linux only.", allow_module_level=True)

import ctypes
import errno
import logging
import os
import select
import struct
from typing import TYPE_CHECKING
from unittest.mock import patch

from watchdog.events import DirCreatedEvent, DirDeletedEvent, DirModifiedEvent
from watchdog.observers.inotify_c import Inotify, InotifyConstants, InotifyEvent

if TYPE_CHECKING:
    from ..utils import Helper, P, StartWatching, TestEventQueue

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)




def test_watch_file_move(p: P, event_queue: TestEventQueue, start_watching: StartWatching) -> None:
    folder = p()
    path = p("this_is_a_file")
    path_moved = p("this_is_a_file2")
    with open(path, "a"):
        pass
    start_watching(path=folder)
    os.rename(path, path_moved)
    event, _ = event_queue.get(timeout=5)
    assert event.src_path == path
    assert event.dest_path == path_moved
    assert repr(event)

