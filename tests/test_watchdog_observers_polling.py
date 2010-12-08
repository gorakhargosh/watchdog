# -*- coding: utf-8 -*-

from time import sleep
from tests.shell import *
from nose import SkipTest
from nose.tools import \
    assert_equal, \
    assert_sequence_equal, \
    assert_true, \
    assert_false
from os.path import join as path_join

import logging

logging.basicConfig(level=logging.DEBUG)

try:
    import queue  # IGNORE:F0401
except ImportError:
    import Queue as queue  # IGNORE:F0401

from watchdog.utils import real_absolute_path
from watchdog.events import *
from watchdog.observers.api import EventQueue, ObservedWatch
from watchdog.observers.polling import PollingEmitter as Emitter


temp_dir = mkdtemp()

def p(*args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return os.path.join(temp_dir, *args)

class TestPollingEmitter:
    def setup(self):
        self.event_queue = queue.Queue()
        self.watch = ObservedWatch(temp_dir, True)
        self.emitter = Emitter(self.event_queue, self.watch, timeout=0.2)

    def teardown(self):
        pass

    def test___init__(self):
        SLEEP_TIME = 0.4
        self.emitter.start()
        sleep(SLEEP_TIME)
        mkdir(p('project'))
        sleep(SLEEP_TIME)
        mkdir(p('project', 'blah'))
        sleep(SLEEP_TIME)
        touch(p('afile'))
        sleep(SLEEP_TIME)
        touch(p('fromfile'))
        sleep(SLEEP_TIME)
        mv(p('fromfile'), p('project', 'tofile'))
        sleep(SLEEP_TIME)
        touch(p('afile'))
        sleep(SLEEP_TIME)
        mv(p('project', 'blah'), p('project', 'boo'))
        sleep(SLEEP_TIME)
        rm(p('project'), recursive=True)
        sleep(SLEEP_TIME)
        rm(p('afile'))
        sleep(SLEEP_TIME)
        self.emitter.stop()

        expected = set([
            DirModifiedEvent(p()),
            DirCreatedEvent(p('project')),

            DirModifiedEvent(p('project')),
            DirCreatedEvent(p('project', 'blah')),

            FileCreatedEvent(p('afile')),
            DirModifiedEvent(p()),

            FileCreatedEvent(p('fromfile')),
            DirModifiedEvent(p()),

            DirModifiedEvent(p()),
            FileMovedEvent(p('fromfile'), p('project', 'tofile')),

            FileModifiedEvent(p('afile')),

            DirModifiedEvent(p('project')),
            DirMovedEvent(p('project', 'blah'), p('project', 'boo')),

            DirModifiedEvent(p()),
            FileDeletedEvent(p('project', 'boo')),
            DirDeletedEvent(p('project', 'boo')),
            DirDeletedEvent(p('project')),

            DirModifiedEvent(p()),
            FileDeletedEvent(p('afile')),

        ])
        got = set()

        while True:
            try:
                event, watch = self.event_queue.get_nowait()
                got.add(event)
            except queue.Empty:
                break

        assert_sequence_equal(expected, got)


    def test_on_thread_exit(self):
        # polling_emitter = PollingEmitter(event_queue, watch, timeout)
        # assert_equal(expected, polling_emitter.on_thread_exit())
        raise SkipTest # TODO: implement your test here

    def test_queue_events(self):
        # polling_emitter = PollingEmitter(event_queue, watch, timeout)
        # assert_equal(expected, polling_emitter.queue_events(event_queue, watch, timeout))
        raise SkipTest # TODO: implement your test here

