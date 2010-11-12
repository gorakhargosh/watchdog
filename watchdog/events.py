

EVENT_TYPE_MOVED = 'moved'
EVENT_TYPE_DELETED = 'deleted'
EVENT_TYPE_CREATED = 'created'
EVENT_TYPE_MODIFIED = 'modified'

class FileSystemEvent(object):
    def __init__(self, event_type, path, is_directory=False):
        self._path = path
        self._is_directory = is_directory
        self._event_type = event_type

    @property
    def is_directory(self):
        return self.is_directory

    @property
    def path(self):
        return self.path

    @property
    def new_path(self):
        return self._new_path

    @property
    def event_type(self):
        return self._event_type

# File events.
class FileDeletedEvent(FileSystemEvent):
    def __init__(self, path, *args, **kwargs):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_DELETED, path=path)

class FileModifiedEvent(FileSystemEvent):
    def __init__(self, path, *args, **kwargs):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_MODIFIED, path=path)

class FileCreatedEvent(FileSystemEvent):
    def __init__(self, path, *args, **kwargs):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_CREATED, path=path)

class FileMovedEvent(FileSystemEvent):
    def __init__(self, path, new_path, *args, **kwargs):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_MOVED, path=path)
        self._new_path = new_path

    @property
    def new_path(self):
        return self._new_path

# Directory events.
class DirDeletedEvent(FileSystemEvent):
    def __init__(self, path, *args, **kwargs):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_DELETED, path=path, is_directory=True)

class DirModifiedEvent(FileSystemEvent):
    def __init__(self, path, *args, **kwargs):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_MODIFIED, path=path, is_directory=True)

class DirCreatedEvent(FileSystemEvent):
    def __init__(self, path, *args, **kwargs):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_CREATED, path=path, is_directory=True)

class DirMovedEvent(FileSystemEvent):
    def __init__(self, path, new_path, *args, **kwargs):
        FileSystemEvent.__init__(self, event_type=EVENT_TYPE_MOVED, path=path, is_directory=True)
        self._new_path = new_path

    @property
    def new_path(self):
        return self._new_path

