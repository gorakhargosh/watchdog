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
from watchdog.utils import filter_paths

logging.basicConfig(level=logging.DEBUG,
                    format='(%(threadName)-10s) %(message)s',
                    )

EVENT_TYPE_MOVED = 'moved'
EVENT_TYPE_DELETED = 'deleted'
EVENT_TYPE_CREATED = 'created'
EVENT_TYPE_MODIFIED = 'modified'


class FileSystemEvent(object):
    """
    Represents a file system event that is triggered when a change occurs
    in a directory that is being monitored.
    """
    def __init__(self, event_type, path, is_directory=False):
        self._path = path
        self._is_directory = is_directory
        self._event_type = event_type

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return str((self._event_type, self._path, self._is_directory))

    @property
    def is_directory(self):
        return self._is_directory

    @property
    def path(self):
        return self._path

    @property
    def event_type(self):
        return self._event_type


class FileSystemMovedEvent(FileSystemEvent):
    """
    Base class for file system movement.
    """
    def __init__(self, path, new_path, is_directory=False):
        self._new_path = new_path
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_MOVED, path=path, is_directory=is_directory)

    @property
    def new_path(self):
        return self._new_path

    def __repr__(self):
        return str((self.event_type, self.path, self.new_path, self.is_directory))


# File events.
class FileDeletedEvent(FileSystemEvent):
    def __init__(self, path):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_DELETED, path=path)

class FileModifiedEvent(FileSystemEvent):
    def __init__(self, path):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_MODIFIED, path=path)

class FileCreatedEvent(FileSystemEvent):
    def __init__(self, path):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_CREATED, path=path)

class FileMovedEvent(FileSystemMovedEvent):
    pass

# Directory events.
class DirDeletedEvent(FileSystemEvent):
    def __init__(self, path):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_DELETED, path=path, is_directory=True)

class DirModifiedEvent(FileSystemEvent):
    def __init__(self, path):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_MODIFIED, path=path, is_directory=True)

class DirCreatedEvent(FileSystemEvent):
    def __init__(self, path):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_CREATED, path=path, is_directory=True)

class DirMovedEvent(FileSystemMovedEvent):
    def __init__(self, path, new_path):
        FileSystemMovedEvent.__init__(self, path=path, new_path=new_path, is_directory=True)



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
        FileSystemEventHandler.__init__(self)
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

        if hasattr(event, 'new_path'):
            paths = [event.path, event.new_path]
        else:
            paths = [event.path]

        if filter_paths(paths, self.patterns, self.ignore_patterns):
            logging.debug(event)
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
        logging.debug("Moved %s: from %s to %s", what, event.path, event.new_path)

    def on_created(self, event):
        what = 'directory' if event.is_directory else 'file'
        logging.debug("Created %s: %s", what, event.path)

    def on_deleted(self, event):
        what = 'directory' if event.is_directory else 'file'
        logging.debug("Deleted %s: %s", what, event.path)

    def on_modified(self, event):
        what = 'directory' if event.is_directory else 'file'
        logging.debug("Modified %s: %s", what, event.path)
