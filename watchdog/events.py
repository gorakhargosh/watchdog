# -*- coding: utf-8 -*-
# events.py: event handling.
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

import logging
import os.path

from watchdog.utils.collections import OrderedSetQueue
from watchdog.utils import filter_paths, \
    has_attribute, get_walker, absolute_path
from watchdog.decorator_utils import deprecated


class EventQueue(OrderedSetQueue):
    def _item_repr(self, event):
        return event.repr()


EVENT_TYPE_MOVED = 'moved'
EVENT_TYPE_DELETED = 'deleted'
EVENT_TYPE_CREATED = 'created'
EVENT_TYPE_MODIFIED = 'modified'


def get_moved_events_for(src_dir_path, dest_dir_path, recursive, handler):
    walk = get_walker(recursive)
    src_dir_path = absolute_path(src_dir_path)
    dest_dir_path = absolute_path(dest_dir_path)
    for root, directories, filenames in walk(dest_dir_path):
        for directory in directories:
            full_path = os.path.join(root, directory)
            renamed_path = full_path.replace(dest_dir_path, src_dir_path)
            yield DirMovedEvent(renamed_path, full_path, handler=handler)
        for filename in filenames:
            full_path = os.path.join(root, filename)
            renamed_path = full_path.replace(dest_dir_path, src_dir_path)
            yield FileMovedEvent(renamed_path, full_path, handler=handler)


class FileSystemEvent(object):
    """
    Represents a file system event that is triggered when a change occurs
    in a directory that is being monitored.
    """
    def __init__(self, event_type, src_path, is_directory=False, handler=None):
        self._src_path = src_path
        self._is_directory = is_directory
        self._event_type = event_type
        self._handler = handler

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return str((self.event_type, self.src_path, self.is_directory))

    def repr(self):
        return (self.event_type, self.src_path, self.is_directory, self.handler)

    def dispatch(self):
        self.handler.dispatch(self)

    @property
    def handler(self):
        return self._handler

    @property
    def is_directory(self):
        return self._is_directory

    @property
    def src_path(self):
        return self._src_path

    @property
    @deprecated
    def path(self):
        return self._src_path

    @property
    def event_type(self):
        return self._event_type


class FileSystemMovedEvent(FileSystemEvent):
    """
    Base class for file system movement.
    """
    def __init__(self, src_path, dest_path, is_directory=False, handler=None):
        super(FileSystemMovedEvent, self).__init__(event_type=EVENT_TYPE_MOVED,
                                                   src_path=src_path,
                                                   is_directory=is_directory,
                                                   handler=handler)
        self._dest_path = dest_path


    def repr(self):
        return (self.event_type, self.src_path, self.dest_path, self.is_directory, self.handler)


    @property
    @deprecated
    def new_path(self):
        return self._dest_path


    @property
    def dest_path(self):
        return self._dest_path


    def __repr__(self):
        return str((self.event_type, self.src_path, self.dest_path, self.is_directory))


# File events.
class FileDeletedEvent(FileSystemEvent):
    def __init__(self, src_path, handler=None):
        super(FileDeletedEvent, self).__init__(event_type=EVENT_TYPE_DELETED,
                                               src_path=src_path,
                                               handler=handler)

class FileModifiedEvent(FileSystemEvent):
    def __init__(self, src_path, handler=None):
        super(FileModifiedEvent, self).__init__(event_type=EVENT_TYPE_MODIFIED,
                                                src_path=src_path,
                                                handler=handler)

class FileCreatedEvent(FileSystemEvent):
    def __init__(self, src_path, handler=None):
        super(FileCreatedEvent, self).__init__(event_type=EVENT_TYPE_CREATED,
                                               src_path=src_path,
                                               handler=handler)

class FileMovedEvent(FileSystemMovedEvent):
    pass

# Directory events.
class DirDeletedEvent(FileSystemEvent):
    def __init__(self, src_path, handler=None):
        super(DirDeletedEvent, self).__init__(event_type=EVENT_TYPE_DELETED,
                                              src_path=src_path,
                                              is_directory=True,
                                              handler=handler)

class DirModifiedEvent(FileSystemEvent):
    def __init__(self, src_path, handler=None):
        super(DirModifiedEvent, self).__init__(event_type=EVENT_TYPE_MODIFIED,
                                               src_path=src_path,
                                               is_directory=True,
                                               handler=handler)

class DirCreatedEvent(FileSystemEvent):
    def __init__(self, src_path, handler=None):
        super(DirCreatedEvent, self).__init__(event_type=EVENT_TYPE_CREATED,
                                              src_path=src_path,
                                              is_directory=True,
                                              handler=handler)

class DirMovedEvent(FileSystemMovedEvent):
    def __init__(self, src_path, dest_path, handler=None):
        super(DirMovedEvent, self).__init__(src_path=src_path,
                                            dest_path=dest_path,
                                            is_directory=True,
                                            handler=handler)



class FileSystemEventHandler(object):
    """File system base event handler."""

    def dispatch(self, event):
        """Dispatches events to the appropriate methods.

        Arguments:
        - event: The event object representing the file system event.
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

        Arguments:
        - event: The event object representing the file system event.
        """
        pass

    def on_moved(self, event):
        """Called when a file or a directory is moved or renamed.

        Arguments:
        - event: The event object representing the file system event.
        """
        pass

    def on_created(self, event):
        """Called when a file or directory is created.

        Arguments:
        - event: The event object representing the file system event.
        """
        pass

    def on_deleted(self, event):
        """Called when a file or directory is deleted.

        Arguments:
        - event: The event object representing the file system event.
        """
        pass

    def on_modified(self, event):
        """Called when a file or directory is modified.

        Arguments:
        - event: The event object representing the file system event.
        """
        pass


class PatternMatchingEventHandler(FileSystemEventHandler):
    """Matches given patterns with file paths associated with occurring events."""
    def __init__(self, patterns=['*'], ignore_patterns=[], ignore_directories=False):
        super(PatternMatchingEventHandler, self).__init__()
        self.patterns = patterns
        self.ignore_patterns = ignore_patterns
        self.ignore_directories = ignore_directories

    def dispatch(self, event):
        """Dispatches events to the appropriate methods.

        Arguments:
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


class LoggingFileSystemEventHandler(FileSystemEventHandler):
    """Logs all the events captured."""
    def on_moved(self, event):
        what = 'directory' if event.is_directory else 'file'
        logging.info("Moved %s: from %s to %s", what, event.src_path, event.dest_path)

    def on_created(self, event):
        what = 'directory' if event.is_directory else 'file'
        logging.info("Created %s: %s", what, event.src_path)

    def on_deleted(self, event):
        what = 'directory' if event.is_directory else 'file'
        logging.info("Deleted %s: %s", what, event.src_path)

    def on_modified(self, event):
        what = 'directory' if event.is_directory else 'file'
        logging.info("Modified %s: %s", what, event.src_path)
