# -*- coding: utf-8 -*-

import threading
import time
from nose.tools import \
    assert_equal, \
    assert_true, \
    assert_false

try:
    import queue  # IGNORE:F0401
except ImportError:
    import Queue as queue # IGNORE:F0401

from watchdog.events import DirModifiedEvent, FileModifiedEvent
from watchdog.utils.bricks import OrderedSetQueue

class TestOrderedSetQueue:
    def test_behavior_ordered_set(self):
        dir_mod_event = DirModifiedEvent("/path/x")
        file_mod_event = FileModifiedEvent('/path/y')
        event_list = [
            dir_mod_event,
            dir_mod_event,
            dir_mod_event,
            dir_mod_event,
            dir_mod_event,
            file_mod_event,
            file_mod_event,
            dir_mod_event,
            dir_mod_event,
            dir_mod_event,
            dir_mod_event,
            dir_mod_event,
            file_mod_event,
            file_mod_event,
            dir_mod_event,
            dir_mod_event,
            dir_mod_event,
            dir_mod_event,
            dir_mod_event,
            file_mod_event,
            file_mod_event,
            file_mod_event,
            file_mod_event,
        ]
        event_set = set(event_list)
        event_queue = OrderedSetQueue()
        for event in event_list:
            event_queue.put(event)

        def event_consumer(in_queue):
            events = []
            while True:
                try:
                    event = in_queue.get(block=True, timeout=0.2)
                    events.append(event)
                    in_queue.task_done()
                except queue.Empty:
                    break

            # Check set behavior.
            assert_true(len(set(events)) == len(events))
            assert_equal(set(events), event_set)

            # Check order.
            assert_equal(events[0], dir_mod_event)
            assert_equal(events[1], file_mod_event)

        consumer_thread = threading.Thread(target=event_consumer, args=(event_queue,))
        consumer_thread.start()
        consumer_thread.join()
