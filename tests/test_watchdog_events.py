# -*- coding: utf-8 -*-
# test_watchdog_events.py: tests for the watchdog.events module.

from nose.tools import \
    assert_equal, \
    assert_true, \
    assert_false, \
    assert_not_equal

from utils import assert_readonly_public_attributes
from watchdog.utils import has_attribute, filter_paths
from watchdog.events import \
    FileSystemEvent, \
    FileSystemMovedEvent, \
    FileDeletedEvent, \
    FileModifiedEvent, \
    FileCreatedEvent, \
    DirDeletedEvent, \
    DirModifiedEvent, \
    DirCreatedEvent, \
    FileMovedEvent, \
    DirMovedEvent, \
    FileSystemEventHandler, \
    PatternMatchingEventHandler, \
    LoggingEventHandler, \
    EVENT_TYPE_MODIFIED, \
    EVENT_TYPE_CREATED, \
    EVENT_TYPE_DELETED, \
    EVENT_TYPE_MOVED, \
    _generate_sub_moved_events_for

path_1 = '/path/xyz'
path_2 = '/path/abc'

def assert_event_type(event, event_type):
    assert_true(event.event_type == event_type)
    #if event.event_type != event_type:
    #    assert False, "%s: event.event_type is not %s" % (event, event_type)

def assert_check_directory(handler, event):
    assert_false(handler.ignore_directories and event.is_directory)
    #if handler.ignore_directories and event.is_directory:
    #    assert False, "Event %s should have been ignored by event.ignore_directories=True" % event

class TestFileSystemEvent:
    def test___eq__(self):
        event1 = FileSystemEvent(EVENT_TYPE_MODIFIED, path_1, True)
        event2 = FileSystemEvent(EVENT_TYPE_MODIFIED, path_1, True)
        assert_true(event1.__eq__(event2))

    def test___hash__(self):
        event1 = FileSystemEvent(EVENT_TYPE_DELETED, path_1, False)
        event2 = FileSystemEvent(EVENT_TYPE_DELETED, path_1, False)
        event3 = FileSystemEvent(EVENT_TYPE_DELETED, path_2, False)
        assert_equal(event1.__hash__(), event2.__hash__())
        assert_not_equal(event1.__hash__(), event3.__hash__())

    def test___init__(self):
        event = FileSystemEvent(EVENT_TYPE_MODIFIED, path_1, True)
        assert_equal(event.src_path, path_1)
        assert_equal(event.event_type, EVENT_TYPE_MODIFIED)
        assert_equal(event.is_directory, True)

    def test___ne__(self):
        event1 = FileSystemEvent(EVENT_TYPE_MODIFIED, path_1, True)
        event2 = FileSystemEvent(EVENT_TYPE_MODIFIED, path_2, True)
        assert_true(event1.__ne__(event2))

    def test___repr__(self):
        event = FileSystemEvent(EVENT_TYPE_MODIFIED, path_1, False)
        assert_equal('<FileSystemEvent: event_type=%s, src_path=%s, is_directory=%s>' \
                     % (EVENT_TYPE_MODIFIED, path_1, False), event.__repr__())

    def test___str__(self):
        event = FileSystemEvent(EVENT_TYPE_MODIFIED, path_1, False)
        assert_equal('<FileSystemEvent: event_type=%s, src_path=%s, is_directory=%s>' \
                     % (EVENT_TYPE_MODIFIED, path_1, False), event.__str__())

    def test_event_type(self):
        event1 = FileSystemEvent(EVENT_TYPE_DELETED, path_1, False)
        event2 = FileSystemEvent(EVENT_TYPE_CREATED, path_2, True)
        assert_equal(EVENT_TYPE_DELETED, event1.event_type)
        assert_equal(EVENT_TYPE_CREATED, event2.event_type)

    def test_is_directory(self):
        event1 = FileSystemEvent(EVENT_TYPE_MODIFIED, path_1, True)
        event2 = FileSystemEvent(EVENT_TYPE_MODIFIED, path_1, False)
        assert_true(event1.is_directory)
        assert_false(event2.is_directory)

    def test_src_path(self):
        event1 = FileSystemEvent(EVENT_TYPE_CREATED, path_1, True)
        event2 = FileSystemEvent(EVENT_TYPE_CREATED, path_2, False)
        assert_equal(path_1, event1.src_path)
        assert_equal(path_2, event2.src_path)

    def test_behavior_readonly_public_attributes(self):
        event = FileSystemEvent(EVENT_TYPE_MODIFIED, path_1, True)
        assert_readonly_public_attributes(event)


class TestFileSystemMovedEvent:
    def test___init__(self):
        event = FileSystemMovedEvent(path_1, path_2, True)
        assert_equal(event.src_path, path_1)
        assert_equal(event.dest_path, path_2)
        assert_equal(event.event_type, EVENT_TYPE_MOVED)
        assert_equal(event.is_directory, True)

    def test___repr__(self):
        event = FileSystemMovedEvent(path_1, path_2, True)
        assert_equal('<FileSystemMovedEvent: src_path=%s, dest_path=%s, is_directory=%s>' \
                     % (path_1, path_2, True), event.__repr__())

    def test_dest_path(self):
        event = FileSystemMovedEvent(path_1, path_2, True)
        assert_equal(path_2, event.dest_path)


    def test_behavior_readonly_public_attributes(self):
        event = FileSystemMovedEvent(path_2, path_1, True)
        assert_readonly_public_attributes(event)


class TestFileDeletedEvent:
    def test___init__(self):
        event = FileDeletedEvent(path_1)
        assert_equal(path_1, event.src_path)
        assert_equal(EVENT_TYPE_DELETED, event.event_type)
        assert_false(event.is_directory)

    def test___repr__(self):
        event = FileDeletedEvent(path_1)
        assert_equal("<FileDeletedEvent: src_path=%s>" % path_1, event.__repr__())

    # Behavior tests.
    def test_behavior_readonly_public_attributes(self):
        event = FileDeletedEvent(path_1)
        assert_readonly_public_attributes(event)

    # Inherited properties.
    def test_is_directory(self):
        event1 = FileDeletedEvent(path_1)
        assert_false(event1.is_directory)



class TestFileModifiedEvent:
    def test___init__(self):
        event = FileModifiedEvent(path_1)
        assert_equal(path_1, event.src_path)
        assert_equal(EVENT_TYPE_MODIFIED, event.event_type)
        assert_false(event.is_directory)

    def test___repr__(self):
        event = FileModifiedEvent(path_1)
        assert_equal("<FileModifiedEvent: src_path=%s>" % path_1, event.__repr__())

    # Behavior
    def test_behavior_readonly_public_attributes(self):
        event = FileModifiedEvent(path_1)
        assert_readonly_public_attributes(event)

    # Inherited Properties
    def test_is_directory(self):
        event1 = FileModifiedEvent(path_1)
        assert_false(event1.is_directory)


class TestFileCreatedEvent:
    def test___init__(self):
        event = FileCreatedEvent(path_1)
        assert_equal(path_1, event.src_path)
        assert_equal(EVENT_TYPE_CREATED, event.event_type)
        assert_false(event.is_directory)

    def test___repr__(self):
        event = FileCreatedEvent(path_1)
        assert_equal("<FileCreatedEvent: src_path=%s>" % path_1, event.__repr__())

    def test_behavior_readonly_public_attributes(self):
        event = FileCreatedEvent(path_1)
        assert_readonly_public_attributes(event)


class TestFileMovedEvent:
    def test___init__(self):
        event = FileMovedEvent(path_1, path_2)
        assert_equal(path_1, event.src_path)
        assert_equal(path_2, event.dest_path)
        assert_equal(EVENT_TYPE_MOVED, event.event_type)
        assert_false(event.is_directory)

    def test___repr__(self):
        event = FileMovedEvent(path_1, path_2)
        assert_equal("<FileMovedEvent: src_path=%s, dest_path=%s>" % (path_1, path_2), event.__repr__())

    def test_behavior_readonly_public_attributes(self):
        event = FileMovedEvent(path_1, path_2)
        assert_readonly_public_attributes(event)


class TestDirDeletedEvent:
    def test___init__(self):
        event = DirDeletedEvent(path_1)
        assert_equal(path_1, event.src_path)
        assert_equal(EVENT_TYPE_DELETED, event.event_type)
        assert_true(event.is_directory)

    def test___repr__(self):
        event = DirDeletedEvent(path_1)
        assert_equal("<DirDeletedEvent: src_path=%s>" % path_1, event.__repr__())

    def test_behavior_readonly_public_attributes(self):
        event = DirDeletedEvent(path_1)
        assert_readonly_public_attributes(event)


class TestDirModifiedEvent:
    def test___init__(self):
        event = DirModifiedEvent(path_1)
        assert_equal(path_1, event.src_path)
        assert_equal(EVENT_TYPE_MODIFIED, event.event_type)
        assert_true(event.is_directory)

    def test___repr__(self):
        event = DirModifiedEvent(path_1)
        assert_equal("<DirModifiedEvent: src_path=%s>" % path_1, event.__repr__())

    def test_behavior_readonly_public_attributes(self):
        event = DirModifiedEvent(path_1)
        assert_readonly_public_attributes(event)


class TestDirCreatedEvent:
    def test___init__(self):
        event = DirCreatedEvent(path_1)
        assert_equal(path_1, event.src_path)
        assert_equal(EVENT_TYPE_CREATED, event.event_type)
        assert_true(event.is_directory)

    def test___repr__(self):
        event = DirCreatedEvent(path_1)
        assert_equal("<DirCreatedEvent: src_path=%s>" % path_1, event.__repr__())

    def test_behavior_readonly_public_attributes(self):
        event = DirCreatedEvent(path_1)
        assert_readonly_public_attributes(event)


class TestDirMovedEvent:
    def test___init__(self):
        event = DirMovedEvent(path_1, path_2)
        assert_equal(path_1, event.src_path)
        assert_equal(path_2, event.dest_path)
        assert_equal(EVENT_TYPE_MOVED, event.event_type)
        assert_true(event.is_directory)

    def test___repr__(self):
        event = DirMovedEvent(path_1, path_2)
        assert_equal("<DirMovedEvent: src_path=%s, dest_path=%s>" % (path_1, path_2), event.__repr__())

    def test_sub_moved_events(self):
        mock_walker_path = [
            ('/path',
                ['ad', 'bd'],
                ['af', 'bf', 'cf']),
            ('/path/ad',
                [],
                ['af', 'bf', 'cf']),
            ('/path/bd',
                [],
                ['af', 'bf', 'cf']),
        ]
        dest_path = '/path'
        src_path = '/foobar'
        expected_events = set([
            DirMovedEvent('/foobar/ad', '/path/ad'),
            DirMovedEvent('/foobar/bd', '/path/bd'),
            FileMovedEvent('/foobar/af', '/path/af'),
            FileMovedEvent('/foobar/bf', '/path/bf'),
            FileMovedEvent('/foobar/cf', '/path/cf'),
            FileMovedEvent('/foobar/ad/af', '/path/ad/af'),
            FileMovedEvent('/foobar/ad/bf', '/path/ad/bf'),
            FileMovedEvent('/foobar/ad/cf', '/path/ad/cf'),
            FileMovedEvent('/foobar/bd/af', '/path/bd/af'),
            FileMovedEvent('/foobar/bd/bf', '/path/bd/bf'),
            FileMovedEvent('/foobar/bd/cf', '/path/bd/cf'),
        ])
        dir_moved_event = DirMovedEvent(src_path, dest_path)

        def _mock_os_walker(path):
            for root, directories, filenames in mock_walker_path:
                yield (root, directories, filenames)
        calculated_events = set(dir_moved_event.sub_moved_events(_walker=_mock_os_walker))
        assert_equal(expected_events, calculated_events)

    def test_behavior_readonly_public_attributes(self):
        event = DirMovedEvent(path_1, path_2)
        assert_readonly_public_attributes(event)


class TestFileSystemEventHandler:
    def test_dispatch(self):
        # Utilities.

        dir_del_event = DirDeletedEvent('/path/blah.py')
        file_del_event = FileDeletedEvent('/path/blah.txt')
        dir_cre_event = DirCreatedEvent('/path/blah.py')
        file_cre_event = FileCreatedEvent('/path/blah.txt')
        dir_mod_event = DirModifiedEvent('/path/blah.py')
        file_mod_event = FileModifiedEvent('/path/blah.txt')
        dir_mov_event = DirMovedEvent('/path/blah.py', '/path/blah')
        file_mov_event = FileMovedEvent('/path/blah.txt', '/path/blah')

        all_events = [
            dir_mod_event,
            dir_del_event,
            dir_cre_event,
            dir_mov_event,
            file_mod_event,
            file_del_event,
            file_cre_event,
            file_mov_event,
        ]

        class TestableEventHandler(FileSystemEventHandler):
            def on_any_event(self, event):
                assert True

            def on_modified(self, event):
                assert_event_type(event, EVENT_TYPE_MODIFIED)

            def on_deleted(self, event):
                assert_event_type(event, EVENT_TYPE_DELETED)

            def on_moved(self, event):
                assert_event_type(event, EVENT_TYPE_MOVED)

            def on_created(self, event):
                assert_event_type(event, EVENT_TYPE_CREATED)

        handler = TestableEventHandler()

        for event in all_events:
            handler.dispatch(event)

g_allowed_patterns = ["*.py", "*.txt"]
g_ignore_patterns = ["*.foo"]

class TestPatternMatchingEventHandler:
    def test_dispatch(self):
        # Utilities.
        patterns = ['*.py', '*.txt']
        ignore_patterns = ["*.pyc"]
        def assert_patterns(event):
            if has_attribute(event, 'dest_path'):
                paths = [event.src_path, event.dest_path]
            else:
                paths = [event.src_path]
            filtered_paths = filter_paths(paths, patterns, ignore_patterns)
            assert_true(filtered_paths)

        dir_del_event_match = DirDeletedEvent('/path/blah.py')
        dir_del_event_not_match = DirDeletedEvent('/path/foobar')
        dir_del_event_ignored = DirDeletedEvent('/path/foobar.pyc')
        file_del_event_match = FileDeletedEvent('/path/blah.txt')
        file_del_event_not_match = FileDeletedEvent('/path/foobar')
        file_del_event_ignored = FileDeletedEvent('/path/blah.pyc')

        dir_cre_event_match = DirCreatedEvent('/path/blah.py')
        dir_cre_event_not_match = DirCreatedEvent('/path/foobar')
        dir_cre_event_ignored = DirCreatedEvent('/path/foobar.pyc')
        file_cre_event_match = FileCreatedEvent('/path/blah.txt')
        file_cre_event_not_match = FileCreatedEvent('/path/foobar')
        file_cre_event_ignored = FileCreatedEvent('/path/blah.pyc')

        dir_mod_event_match = DirModifiedEvent('/path/blah.py')
        dir_mod_event_not_match = DirModifiedEvent('/path/foobar')
        dir_mod_event_ignored = DirModifiedEvent('/path/foobar.pyc')
        file_mod_event_match = FileModifiedEvent('/path/blah.txt')
        file_mod_event_not_match = FileModifiedEvent('/path/foobar')
        file_mod_event_ignored = FileModifiedEvent('/path/blah.pyc')

        dir_mov_event_match = DirMovedEvent('/path/blah.py', '/path/blah')
        dir_mov_event_not_match = DirMovedEvent('/path/foobar', '/path/blah')
        dir_mov_event_ignored = DirMovedEvent('/path/foobar.pyc', '/path/blah')
        file_mov_event_match = FileMovedEvent('/path/blah.txt', '/path/blah')
        file_mov_event_not_match = FileMovedEvent('/path/foobar', '/path/blah')
        file_mov_event_ignored = FileMovedEvent('/path/blah.pyc', '/path/blah')

        all_dir_events = [
            dir_mod_event_match,
            dir_mod_event_not_match,
            dir_mod_event_ignored,
            dir_del_event_match,
            dir_del_event_not_match,
            dir_del_event_ignored,
            dir_cre_event_match,
            dir_cre_event_not_match,
            dir_cre_event_ignored,
            dir_mov_event_match,
            dir_mov_event_not_match,
            dir_mov_event_ignored,
        ]
        all_file_events = [
            file_mod_event_match,
            file_mod_event_not_match,
            file_mod_event_ignored,
            file_del_event_match,
            file_del_event_not_match,
            file_del_event_ignored,
            file_cre_event_match,
            file_cre_event_not_match,
            file_cre_event_ignored,
            file_mov_event_match,
            file_mov_event_not_match,
            file_mov_event_ignored,
        ]
        all_events = all_file_events + all_dir_events

        class TestableEventHandler(PatternMatchingEventHandler):
            def on_any_event(self, event):
                assert_check_directory(self, event)

            def on_modified(self, event):
                assert_check_directory(self, event)
                assert_event_type(event, EVENT_TYPE_MODIFIED)
                assert_patterns(event)

            def on_deleted(self, event):
                assert_check_directory(self, event)
                assert_event_type(event, EVENT_TYPE_DELETED)
                assert_patterns(event)

            def on_moved(self, event):
                assert_check_directory(self, event)
                assert_event_type(event, EVENT_TYPE_MOVED)
                assert_patterns(event)

            def on_created(self, event):
                assert_check_directory(self, event)
                assert_event_type(event, EVENT_TYPE_CREATED)
                assert_patterns(event)

        no_dirs_handler = TestableEventHandler(patterns=patterns,
                                               ignore_patterns=ignore_patterns,
                                               ignore_directories=True)
        handler = TestableEventHandler(patterns=patterns,
                                       ignore_patterns=ignore_patterns,
                                       ignore_directories=False)

        for event in all_events:
            no_dirs_handler.dispatch(event)
        for event in all_events:
            handler.dispatch(event)


    def test___init__(self):
        handler1 = PatternMatchingEventHandler(g_allowed_patterns, g_ignore_patterns, True)
        handler2 = PatternMatchingEventHandler(g_allowed_patterns, g_ignore_patterns, False)
        assert_equal(handler1.patterns, g_allowed_patterns)
        assert_equal(handler1.ignore_patterns, g_ignore_patterns)
        assert_true(handler1.ignore_directories)
        assert_false(handler2.ignore_directories)

    def test_ignore_directories(self):
        handler1 = PatternMatchingEventHandler(g_allowed_patterns, g_ignore_patterns, True)
        handler2 = PatternMatchingEventHandler(g_allowed_patterns, g_ignore_patterns, False)
        assert_true(handler1.ignore_directories)
        assert_false(handler2.ignore_directories)

    def test_ignore_patterns(self):
        handler1 = PatternMatchingEventHandler(g_allowed_patterns, g_ignore_patterns, True)
        assert_equal(handler1.ignore_patterns, g_ignore_patterns)

    def test_patterns(self):
        handler1 = PatternMatchingEventHandler(g_allowed_patterns, g_ignore_patterns, True)
        assert_equal(handler1.patterns, g_allowed_patterns)


class _TestableEventHandler(LoggingEventHandler):
    def on_any_event(self, event):
        assert True

    def on_modified(self, event):
        super(_TestableEventHandler, self).on_modified(event)
        assert_event_type(event, EVENT_TYPE_MODIFIED)

    def on_deleted(self, event):
        super(_TestableEventHandler, self).on_deleted(event)
        assert_event_type(event, EVENT_TYPE_DELETED)

    def on_moved(self, event):
        super(_TestableEventHandler, self).on_moved(event)
        assert_event_type(event, EVENT_TYPE_MOVED)

    def on_created(self, event):
        super(_TestableEventHandler, self).on_created(event)
        assert_event_type(event, EVENT_TYPE_CREATED)

class TestLoggingEventHandler:
    def test_dispatch(self):
        # Utilities.
        dir_del_event = DirDeletedEvent('/path/blah.py')
        file_del_event = FileDeletedEvent('/path/blah.txt')
        dir_cre_event = DirCreatedEvent('/path/blah.py')
        file_cre_event = FileCreatedEvent('/path/blah.txt')
        dir_mod_event = DirModifiedEvent('/path/blah.py')
        file_mod_event = FileModifiedEvent('/path/blah.txt')
        dir_mov_event = DirMovedEvent('/path/blah.py', '/path/blah')
        file_mov_event = FileMovedEvent('/path/blah.txt', '/path/blah')

        all_events = [
            dir_mod_event,
            dir_del_event,
            dir_cre_event,
            dir_mov_event,
            file_mod_event,
            file_del_event,
            file_cre_event,
            file_mov_event,
        ]

        handler = _TestableEventHandler()
        for event in all_events:
            handler.dispatch(event)

class TestGenerateSubMovedEventsFor:
    def test_generate_sub_moved_events_for(self):
        mock_walker_path = [
            ('/path',
                ['ad', 'bd'],
                ['af', 'bf', 'cf']),
            ('/path/ad',
                [],
                ['af', 'bf', 'cf']),
            ('/path/bd',
                [],
                ['af', 'bf', 'cf']),
        ]
        dest_path = '/path'
        src_path = '/foobar'
        expected_events = set([
            DirMovedEvent('/foobar/ad', '/path/ad'),
            DirMovedEvent('/foobar/bd', '/path/bd'),
            FileMovedEvent('/foobar/af', '/path/af'),
            FileMovedEvent('/foobar/bf', '/path/bf'),
            FileMovedEvent('/foobar/cf', '/path/cf'),
            FileMovedEvent('/foobar/ad/af', '/path/ad/af'),
            FileMovedEvent('/foobar/ad/bf', '/path/ad/bf'),
            FileMovedEvent('/foobar/ad/cf', '/path/ad/cf'),
            FileMovedEvent('/foobar/bd/af', '/path/bd/af'),
            FileMovedEvent('/foobar/bd/bf', '/path/bd/bf'),
            FileMovedEvent('/foobar/bd/cf', '/path/bd/cf'),
        ])
        def _mock_os_walker(path):
            for root, directories, filenames in mock_walker_path:
                yield (root, directories, filenames)
        calculated_events = set(_generate_sub_moved_events_for(src_path, dest_path, _walker=_mock_os_walker))
        assert_equal(expected_events, calculated_events)

