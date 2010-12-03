# -*- coding: utf-8 -*-
# events.py: File system events and event handlers.
#
# Copyright (C) 2010 Gora Khargosh <gora.khargosh@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""   
    :module: watchdog.events
    :author: Gora Khargosh <gora.khargosh@gmail.com>
"""

import os
import os.path
import logging

from watchdog.utils.collections import OrderedSetQueue
from watchdog.utils import filter_paths, \
    has_attribute, get_walker, absolute_path, \
    match_allowed_and_ignored_patterns


EVENT_TYPE_MOVED = 'moved'
EVENT_TYPE_DELETED = 'deleted'
EVENT_TYPE_CREATED = 'created'
EVENT_TYPE_MODIFIED = 'modified'



class FileSystemEvent(object):
    """
    Immutable type that represents a file system event that is triggered
    when a change occurs on the monitored file system.
    
    All FileSystemEvent objects are required to be immutable and hence
    can be used as keys in dictionaries or be added to sets.
    
    **Usage**
    
    >>> a = FileSystemEvent('modified', '/path/x', False)
    >>> equal_a = FileSystemEvent('modified', '/path/x', False)
    >>> not_equal_a_1 = FileSystemEvent('modified', '/path/y', False)
    >>> not_equal_a_2 = FileSystemEvent('modified', '/path/x', True)
    >>> not_equal_a_3 = FileSystemEvent('deleted', '/path/x', False)
    >>> a == equal_a
    True
    >>> a != equal_a
    False
    >>> a == not_equal_a_1
    False
    >>> a != not_equal_a_1
    True
    >>> a == not_equal_a_2
    False
    >>> a != not_equal_a_2
    True
    >>> a == not_equal_a_3
    False
    >>> a != not_equal_a_3
    True
    """
    def __init__(self, event_type, src_path, is_directory=False):
        self._src_path = src_path
        self._is_directory = is_directory
        self._event_type = event_type

    @property
    def is_directory(self):
        """True if event was emitted for a directory; False otherwise."""
        return self._is_directory

    @property
    def src_path(self):
        """Source path of the file system object that triggered this event."""
        return self._src_path

    @property
    def event_type(self):
        """The type of the event as a string."""
        return self._event_type

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "<%(class_name)s: event_type=%(event_type)s, \
src_path=%(src_path)s, is_directory=%(is_directory)s>" % \
                dict(class_name=self.__class__.__name__,
                     event_type=self.event_type,
                     src_path=self.src_path,
                     is_directory=self.is_directory)

    # Used for comparison of events.
    def _key(self):
        return (self.event_type,
                self.src_path,
                self.is_directory)

    def __eq__(self, event):
        return self._key() == event._key()

    def __ne__(self, event):
        return self._key() != event._key()

    def __hash__(self):
        return hash(self._key())


class FileSystemMovedEvent(FileSystemEvent):
    """
    File system event representing any kind of file system movement.
    """
    def __init__(self, src_path, dest_path, is_directory):
        super(FileSystemMovedEvent, self).__init__(event_type=EVENT_TYPE_MOVED,
                                                   src_path=src_path,
                                                   is_directory=is_directory)

        self._dest_path = dest_path

    @property
    def dest_path(self):
        """The destination path of the move event."""
        return self._dest_path

    # Used for hashing this as an immutable object.
    def _key(self):
        return (self.event_type,
                self.src_path,
                self.dest_path,
                self.is_directory)

    def __repr__(self):
        return "<%(class_name)s: src_path=%(src_path)s, dest_path=%(dest_path)s, \
is_directory=%(is_directory)s>" % \
                dict(class_name=self.__class__.__name__,
                     src_path=self.src_path,
                     dest_path=self.dest_path,
                     is_directory=self.is_directory)


# File events.
class FileDeletedEvent(FileSystemEvent):
    """File system event representing file deletion on the file system."""
    def __init__(self, src_path):
        super(FileDeletedEvent, self).__init__(event_type=EVENT_TYPE_DELETED,
                                               src_path=src_path)

    def __repr__(self):
        return "<%(class_name)s: src_path=%(src_path)s>" % \
                dict(class_name=self.__class__.__name__,
                     src_path=self.src_path)

class FileModifiedEvent(FileSystemEvent):
    """File system event representing file modification on the file system."""
    def __init__(self, src_path):
        super(FileModifiedEvent, self).__init__(event_type=EVENT_TYPE_MODIFIED,
                                                src_path=src_path)

    def __repr__(self):
        return "<%(class_name)s: src_path=%(src_path)s>" % \
                dict(class_name=self.__class__.__name__,
                     src_path=self.src_path)


class FileCreatedEvent(FileSystemEvent):
    """File system event representing file creation on the file system."""
    def __init__(self, src_path):
        super(FileCreatedEvent, self).__init__(event_type=EVENT_TYPE_CREATED,
                                               src_path=src_path)

    def __repr__(self):
        return "<%(class_name)s: src_path=%(src_path)s>" % \
                dict(class_name=self.__class__.__name__,
                     src_path=self.src_path)

class FileMovedEvent(FileSystemMovedEvent):
    """File system event representing file movement on the file system."""
    def __init__(self, src_path, dest_path):
        super(FileMovedEvent, self).__init__(src_path=src_path,
                                             dest_path=dest_path,
                                             is_directory=False)

    def __repr__(self):
        return "<%(class_name)s: src_path=%(src_path)s, \
dest_path=%(dest_path)s>" % \
                dict(class_name=self.__class__.__name__,
                     src_path=self.src_path,
                     dest_path=self.dest_path)

# Directory events.
class DirDeletedEvent(FileSystemEvent):
    """File system event representing directory deletion on the file system."""
    def __init__(self, src_path):
        super(DirDeletedEvent, self).__init__(event_type=EVENT_TYPE_DELETED,
                                              src_path=src_path,
                                              is_directory=True)

    def __repr__(self):
        return "<%(class_name)s: src_path=%(src_path)s>" % \
                dict(class_name=self.__class__.__name__,
                     src_path=self.src_path)

class DirModifiedEvent(FileSystemEvent):
    """File system event representing directory modification on the file system."""
    def __init__(self, src_path):
        super(DirModifiedEvent, self).__init__(event_type=EVENT_TYPE_MODIFIED,
                                               src_path=src_path,
                                               is_directory=True)

    def __repr__(self):
        return "<%(class_name)s: src_path=%(src_path)s>" % \
                dict(class_name=self.__class__.__name__,
                     src_path=self.src_path)

class DirCreatedEvent(FileSystemEvent):
    """File system event representing directory creation on the file system."""
    def __init__(self, src_path):
        super(DirCreatedEvent, self).__init__(event_type=EVENT_TYPE_CREATED,
                                              src_path=src_path,
                                              is_directory=True)

    def __repr__(self):
        return "<%(class_name)s: src_path=%(src_path)s>" % \
                dict(class_name=self.__class__.__name__,
                     src_path=self.src_path)


class DirMovedEvent(FileSystemMovedEvent):
    """File system event representing directory movement on the file system."""
    def __init__(self, src_path, dest_path):
        super(DirMovedEvent, self).__init__(src_path=src_path,
                                            dest_path=dest_path,
                                            is_directory=True)

    def __repr__(self):
        return "<%(class_name)s: src_path=%(src_path)s, \
dest_path=%(dest_path)s>" % \
                dict(class_name=self.__class__.__name__,
                     src_path=self.src_path,
                     dest_path=self.dest_path)


    def sub_moved_events(self, _walker=os.walk):
        """Generates moved events for file sytem objects within the moved directory.
        
        
        :param _walker:
            Walker used to walk directory trees :func:`os.walk` style. Sanity tests
            use this parameter to inject a mock walker that behaves like 
            :func:`os.walk`.
        :returns: 
            iterable of event objects of type :class:`FileMovedEvent` and 
            :class:`DirMovedEvent`.
        """
        return list(generate_sub_moved_events_for(self.src_path, self.dest_path, _walker=_walker))



class FileSystemEventHandler(object):
    """Base file system event handler that you can override methods from.
    """

    def _dispatch(self, event):
        """Dispatches events to the appropriate methods.

        :param event: 
            The event object representing the file system event.
        :type event: 
            :class:`FileSystemEvent`
        """
        self.on_any_event(event)
        _method_map = {
            EVENT_TYPE_MODIFIED: self.on_modified,
            EVENT_TYPE_MOVED: self.on_moved,
            EVENT_TYPE_CREATED: self.on_created,
            EVENT_TYPE_DELETED: self.on_deleted,
            }
        event_type = event.event_type
        _method_map[event_type](event)


    def on_any_event(self, event):
        """Catch-all event handler.

        :param event: 
            The event object representing the file system event.
        :type event: 
            :class:`FileSystemEvent`
        """
        return event

    def on_moved(self, event):
        """Called when a file or a directory is moved or renamed.

        :param event: 
            Event representing file/directory movement.
        :type event: 
            :class:`DirMovedEvent` or :class:`FileMovedEvent`
        """
        if not event.event_type == EVENT_TYPE_MOVED:
            raise ValueError("Expected event type `%s`. Got `%s`", EVENT_TYPE_MOVED, event.event_type)
        return event

    def on_created(self, event):
        """Called when a file or directory is created.

        :param event: 
            Event representing file/directory creation.
        :type event:
            :class:`DirCreatedEvent` or :class:`FileCreatedEvent`
        """
        if not event.event_type == EVENT_TYPE_CREATED:
            raise ValueError("Expected event type `%s`. Got `%s`", EVENT_TYPE_CREATED, event.event_type)
        return event


    def on_deleted(self, event):
        """Called when a file or directory is deleted.

        :param event:
            Event representing file/directory deletion.
        :type event:
            :class:`DirDeletedEvent` or :class:`FileDeletedEvent`
        """
        if not event.event_type == EVENT_TYPE_DELETED:
            raise ValueError("Expected event type `%s`. Got `%s`", EVENT_TYPE_DELETED, event.event_type)
        return event

    def on_modified(self, event):
        """Called when a file or directory is modified.

        :param event:
            Event representing file/directory modification.
        :type event:
            :class:`DirModifiedEvent` or :class:`FileModifiedEvent`
        """
        if not event.event_type == EVENT_TYPE_MODIFIED:
            raise ValueError("Expected event type `%s`. Got `%s`", EVENT_TYPE_MODIFIED, event.event_type)
        return event



class PatternMatchingEventHandler(FileSystemEventHandler):
    """Matches given patterns with file paths associated with occurring events."""
    def __init__(self, patterns=['*'], ignore_patterns=[], ignore_directories=False):
        super(PatternMatchingEventHandler, self).__init__()

        self._patterns = patterns
        self._ignore_patterns = ignore_patterns
        self._ignore_directories = ignore_directories


    def _check_patterns_for_event(self, event):
        if self.ignore_directories and event.is_directory:
            raise ValueError('Directories are ignored, yet received a directory event %s' % event)
        if has_attribute(event, 'dest_path'):
            paths = set([event.src_path, event.dest_path])
        else:
            paths = set([event.src_path])
        filtered_paths = filter_paths(paths, self.patterns, self.ignore_patterns)
        if not filtered_paths:
            raise ValueError("Pattern matching failed for event %s" % event)


    @property
    def patterns(self):
        """(Read-only) Patterns to allow matching event paths."""
        return self._patterns

    @property
    def ignore_patterns(self):
        """(Read-only) Patterns to ignore matching event paths."""
        return self._ignore_patterns

    @property
    def ignore_directories(self):
        """(Read-only) True if directories should be ignored; False otherwise."""
        return self._ignore_directories


    def _dispatch(self, event):
        """Dispatches events to the appropriate methods.

        - event: The event object representing the file system event.
        """
        if self.ignore_directories and event.is_directory:
            return

        if has_attribute(event, 'dest_path'):
            paths = [event.src_path, event.dest_path]
        else:
            paths = [event.src_path]

        if filter_paths(paths, self.patterns, self.ignore_patterns):
            self.on_any_event(event)
            _method_map = {
                EVENT_TYPE_MODIFIED: self.on_modified,
                EVENT_TYPE_MOVED: self.on_moved,
                EVENT_TYPE_CREATED: self.on_created,
                EVENT_TYPE_DELETED: self.on_deleted,
                }
            event_type = event.event_type
            _method_map[event_type](event)

    def on_any_event(self, event):
        """Catch-all event handler.

        :param event: 
            The event object representing the file system event.
        :type event: 
            :class:`FileSystemEvent`
        """
        super(PatternMatchingEventHandler, self).on_any_event(event)
        self._check_patterns_for_event(event)
        return event


    def on_moved(self, event):
        """Called when a file or a directory is moved or renamed.

        :param event: 
            Event representing file/directory movement.
        :type event: 
            :class:`DirMovedEvent` or :class:`FileMovedEvent`
        """
        super(PatternMatchingEventHandler, self).on_moved(event)
        self._check_patterns_for_event(event)
        return event

    def on_created(self, event):
        """Called when a file or directory is created.

        :param event: 
            Event representing file/directory creation.
        :type event:
            :class:`DirCreatedEvent` or :class:`FileCreatedEvent`
        """
        super(PatternMatchingEventHandler, self).on_created(event)
        self._check_patterns_for_event(event)
        return event


    def on_deleted(self, event):
        """Called when a file or directory is deleted.

        :param event:
            Event representing file/directory deletion.
        :type event:
            :class:`DirDeletedEvent` or :class:`FileDeletedEvent`
        """
        super(PatternMatchingEventHandler, self).on_deleted(event)
        self._check_patterns_for_event(event)
        return event

    def on_modified(self, event):
        """Called when a file or directory is modified.

        :param event:
            Event representing file/directory modification.
        :type event:
            :class:`DirModifiedEvent` or :class:`FileModifiedEvent`
        """
        super(PatternMatchingEventHandler, self).on_modified(event)
        self._check_patterns_for_event(event)
        return event


class LoggingEventHandler(FileSystemEventHandler):
    """Logs all the events captured."""
    def on_moved(self, event):
        super(LoggingEventHandler, self).on_moved(event)

        what = 'directory' if event.is_directory else 'file'
        logging.info("Moved %s: from %s to %s", what, event.src_path, event.dest_path)
        return event

    def on_created(self, event):
        super(LoggingEventHandler, self).on_created(event)

        what = 'directory' if event.is_directory else 'file'
        logging.info("Created %s: %s", what, event.src_path)
        return event

    def on_deleted(self, event):
        super(LoggingEventHandler, self).on_deleted(event)

        what = 'directory' if event.is_directory else 'file'
        logging.info("Deleted %s: %s", what, event.src_path)
        return event

    def on_modified(self, event):
        super(LoggingEventHandler, self).on_modified(event)

        what = 'directory' if event.is_directory else 'file'
        logging.info("Modified %s: %s", what, event.src_path)
        return event



def generate_sub_moved_events_for(src_dir_path, dest_dir_path, _walker=os.walk):
    """Generates an event list of :class:`DirMovedEvent` and :class:`FileMovedEvent` 
    objects for all the files and directories within the given moved directory
    that were moved along with the directory.
    
    :param src_dir_path: 
        The source path of the moved directory.
    :param dest_dir_path: 
        The destination path of the moved directory.
    :param _walker:
        Walker used to walk directory trees :func:`os.walk` style. Sanity tests
        use this parameter to inject a mock walker that behaves like 
        :func:`os.walk`.
    :returns:
        An iterable of file system events of type :class:`DirMovedEvent` and 
        :class:`FileMovedEvent`.
    """
    src_dir_path = absolute_path(src_dir_path)
    dest_dir_path = absolute_path(dest_dir_path)
    for root, directories, filenames in _walker(dest_dir_path):
        for directory in directories:
            full_path = os.path.join(root, directory)
            renamed_path = full_path.replace(dest_dir_path, src_dir_path)
            yield DirMovedEvent(renamed_path, full_path)
        for filename in filenames:
            full_path = os.path.join(root, filename)
            renamed_path = full_path.replace(dest_dir_path, src_dir_path)
            yield FileMovedEvent(renamed_path, full_path)


class EventQueue(OrderedSetQueue):
    """Thread-safe event queue based on a thread-safe ordered-set queue 
    to ensure duplicate :class:`FileSystemEvent` objects are prevented from
    adding themselves to the queue to avoid dispatching multiple event handling
    calls.
    """
    pass

