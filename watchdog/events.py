

EVENT_TYPE_MOVED = 'moved'
EVENT_TYPE_DELETED = 'deleted'
EVENT_TYPE_CREATED = 'created'
EVENT_TYPE_MODIFIED = 'modified'

class FileSystemEvent(object):
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
