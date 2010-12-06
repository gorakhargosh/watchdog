# -*- coding: utf-8 -*-

import time

from nose import SkipTest
from nose.tools import *

from watchdog.observers.api import EventQueue, ObservedWatch
from watchdog.observers.polling_emitter import PollingEmitter

class TestPollingEmitter:
    def test___init__(self):
        #class PollingObserver(BaseObserver):
        #    def __init__(self, interval=1):
        #        BaseObserver.__init__(self, emitter_class=PollingEmitter, interval=interval)
        event_queue = EventQueue()
        watch = ObservedWatch('.', recursive=False)
        emitter = PollingEmitter(event_queue, watch)
        emitter.start()
        time.sleep(3)
        emitter.stop()
        emitter.join()


    def test_on_thread_exit(self):
        # polling_emitter = PollingEmitter(event_queue, watch, interval)
        # assert_equal(expected, polling_emitter.on_thread_exit())
        raise SkipTest # TODO: implement your test here

    def test_queue_events(self):
        # polling_emitter = PollingEmitter(event_queue, watch, interval)
        # assert_equal(expected, polling_emitter.queue_events(event_queue, watch, interval))
        raise SkipTest # TODO: implement your test here

