# -*- coding: utf-8 -*-

import logging

logging.basicConfig(level=logging.DEBUG,
                    format='%(pathname)s/%(funcName)s/(%(threadName)-10s) %(message)s',
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
        _method_map = {
            EVENT_TYPE_MODIFIED: self.on_modified,
            EVENT_TYPE_MOVED: self.on_moved,
            EVENT_TYPE_CREATED: self.on_created,
            EVENT_TYPE_DELETED: self.on_deleted,
            }
        event_type = event.event_type
        _method_map[event_type](event)

    def on_moved(self, event):
        """Called when a file or a directory is moved or renamed.

        Arguments:
        - event: The event object representing the file system event.
        """
        logging.debug(event)

    def on_created(self, event):
        """Called when a file or directory is created.

        Arguments:
        - event: The event object representing the file system event.
        """
        logging.debug(event)

    def on_deleted(self, event):
        """Called when a file or directory is deleted.

        Arguments:
        - event: The event object representing the file system event.
        """
        logging.debug(event)

    def on_modified(self, event):
        """Called when a file or directory is modified.

        Arguments:
        - event: The event object representing the file system event.
        """
        logging.debug(event)
