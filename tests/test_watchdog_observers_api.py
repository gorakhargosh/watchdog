# -*- coding: utf-8 -*-

import time
from nose.tools import *
from nose import SkipTest
from watchdog.observers.api import \
    BaseObserver, \
    EventEmitter, \
    ObservedWatch, \
    EventDispatcher, \
    EventQueue
from watchdog.events import LoggingEventHandler, FileModifiedEvent

class TestObservedWatch:
    def test___eq__(self):
        watch1 = ObservedWatch('/foobar', True)
        watch2 = ObservedWatch('/foobar', True)
        watch_ne1 = ObservedWatch('/foo', True)
        watch_ne2 = ObservedWatch('/foobar', False)

        assert_true(watch1.__eq__(watch2))
        assert_false(watch1.__eq__(watch_ne1))
        assert_false(watch1.__eq__(watch_ne2))

    def test___hash__(self):
        # observed_watch = ObservedWatch(path, recursive)
        # assert_equal(expected, observed_watch.__hash__())
        raise SkipTest # TODO: implement your test here

    def test___init__(self):
        # observed_watch = ObservedWatch(path, recursive)
        raise SkipTest # TODO: implement your test here

    def test___ne__(self):
        watch1 = ObservedWatch('/foobar', True)
        watch2 = ObservedWatch('/foobar', True)
        watch_ne1 = ObservedWatch('/foo', True)
        watch_ne2 = ObservedWatch('/foobar', False)

        assert_false(watch1.__ne__(watch2))
        assert_true(watch1.__ne__(watch_ne1))
        assert_true(watch1.__ne__(watch_ne2))

    def test___repr__(self):
        observed_watch = ObservedWatch('/foobar', True)
        assert_equal('<ObservedWatch: path=/foobar, is_recursive=True>', observed_watch.__repr__())

    def test_is_recursive(self):
        # observed_watch = ObservedWatch(path, recursive)
        # assert_equal(expected, observed_watch.is_recursive())
        raise SkipTest # TODO: implement your test here

    def test_path(self):
        # observed_watch = ObservedWatch(path, recursive)
        # assert_equal(expected, observed_watch.path())
        raise SkipTest # TODO: implement your test here

    def test_signature(self):
        # observed_watch = ObservedWatch(path, recursive)
        # assert_equal(expected, observed_watch.signature())
        raise SkipTest # TODO: implement your test here


class TestEventEmitter:
    def test___init__(self):
        event_queue = EventQueue()
        watch = ObservedWatch('/foobar', True)
        event_emitter = EventEmitter(event_queue, watch, timeout=1)
        event_emitter.queue_event(FileModifiedEvent('/foobar/blah'))

    def test_timeout(self):
        # event_emitter = EventEmitter(event_queue, watch, timeout)
        # assert_equal(expected, event_emitter.timeout())
        raise SkipTest # TODO: implement your test here

    def test_on_thread_exit(self):
        # event_emitter = EventEmitter(event_queue, watch, timeout)
        # assert_equal(expected, event_emitter.on_thread_exit())
        raise SkipTest # TODO: implement your test here

    def test_queue_events(self):
        # event_emitter = EventEmitter(event_queue, watch, timeout)
        # assert_equal(expected, event_emitter.queue_events(event_queue, watch, timeout))
        raise SkipTest # TODO: implement your test here

    def test_run(self):
        # event_emitter = EventEmitter(event_queue, watch, timeout)
        # assert_equal(expected, event_emitter.run())
        raise SkipTest # TODO: implement your test here

    def test_watch(self):
        # event_emitter = EventEmitter(event_queue, watch, timeout)
        # assert_equal(expected, event_emitter.watch())
        raise SkipTest # TODO: implement your test here

class TestEventDispatcher:
    def test___init__(self):
        # event_dispatcher = EventDispatcher(timeout)
        raise SkipTest # TODO: implement your test here

    def test_dispatch_event(self):
        event = FileModifiedEvent('/foobar')
        watch = ObservedWatch('/path', True)

        class TestableEventDispatcher(EventDispatcher):
            def dispatch_event(self, event, watch):
                assert True

        event_dispatcher = TestableEventDispatcher()
        event_dispatcher.event_queue.put((event, watch))
        event_dispatcher.start()
        time.sleep(1)
        event_dispatcher.stop()

    def test_event_queue(self):
        # event_dispatcher = EventDispatcher(timeout)
        # assert_equal(expected, event_dispatcher.event_queue())
        raise SkipTest # TODO: implement your test here

    def test_timeout(self):
        # event_dispatcher = EventDispatcher(timeout)
        # assert_equal(expected, event_dispatcher.timeout())
        raise SkipTest # TODO: implement your test here

    def test_on_thread_exit(self):
        # event_dispatcher = EventDispatcher(timeout)
        # assert_equal(expected, event_dispatcher.on_thread_exit())
        raise SkipTest # TODO: implement your test here

    def test_run(self):
        # event_dispatcher = EventDispatcher(timeout)
        # assert_equal(expected, event_dispatcher.run())
        raise SkipTest # TODO: implement your test here

class TestBaseObserver:
    def test_basic(self):
        observer = BaseObserver(EventEmitter)
        handler = LoggingEventHandler()


        watch = observer.schedule(handler, '/foobar', True)
        observer.add_handler_for_watch(handler, watch)
        observer.add_handler_for_watch(handler, watch)
        observer.remove_handler_for_watch(handler, watch)
        assert_raises(KeyError, observer.remove_handler_for_watch, handler, watch)
        observer.unschedule(watch)
        assert_raises(KeyError, observer.unschedule, watch)


        watch = observer.schedule(handler, '/foobar', True)
        observer.event_queue.put((FileModifiedEvent('/foobar'), watch))
        observer.start()
        time.sleep(1)
        observer.unschedule_all()
        observer.stop()

    def test___init__(self):
        # base_observer = BaseObserver(emitter_class, timeout)
        raise SkipTest # TODO: implement your test here

    def test_add_handler_for_watch(self):
        # base_observer = BaseObserver(emitter_class, timeout)
        # assert_equal(expected, base_observer.add_handler_for_watch(event_handler, watch))
        raise SkipTest # TODO: implement your test here

    def test_dispatch_event(self):
        # base_observer = BaseObserver(emitter_class, timeout)
        # assert_equal(expected, base_observer.dispatch_event(event, watch))
        raise SkipTest # TODO: implement your test here

    def test_on_thread_exit(self):
        # base_observer = BaseObserver(emitter_class, timeout)
        # assert_equal(expected, base_observer.on_thread_exit())
        raise SkipTest # TODO: implement your test here

    def test_remove_handler_for_watch(self):
        # base_observer = BaseObserver(emitter_class, timeout)
        # assert_equal(expected, base_observer.remove_handler_for_watch(event_handler, watch))
        raise SkipTest # TODO: implement your test here

    def test_schedule(self):
        # base_observer = BaseObserver(emitter_class, timeout)
        # assert_equal(expected, base_observer.schedule(event_handler, path, recursive))
        raise SkipTest # TODO: implement your test here

    def test_unschedule(self):
        # base_observer = BaseObserver(emitter_class, timeout)
        # assert_equal(expected, base_observer.unschedule(watch))
        raise SkipTest # TODO: implement your test here

    def test_unschedule_all(self):
        # base_observer = BaseObserver(emitter_class, timeout)
        # assert_equal(expected, base_observer.unschedule_all())
        raise SkipTest # TODO: implement your test here

