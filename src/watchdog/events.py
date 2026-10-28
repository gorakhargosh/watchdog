""":module: watchdog.events
:synopsis: File system events and event handlers.
:author: yesudeep@google.com (Yesudeep Mangalapilly)
:author: Mickaël Schoentgen <contact@tiger-222.fr>

Event Classes
-------------
.. autoclass:: FileSystemEvent
   :members:
   :show-inheritance:
   :inherited-members:

.. autoclass:: FileSystemMovedEvent
   :members:
   :show-inheritance:

.. autoclass:: FileMovedEvent
   :members:
   :show-inheritance:

.. autoclass:: DirMovedEvent
   :members:
   :show-inheritance:

.. autoclass:: FileModifiedEvent
   :members:
   :show-inheritance:

.. autoclass:: DirModifiedEvent
   :members:
   :show-inheritance:

.. autoclass:: FileAttribEvent
   :members:
   :show-inheritance:

.. autoclass:: DirAttribEvent
   :members:
   :show-inheritance:

.. autoclass:: FileCreatedEvent
   :members:
   :show-inheritance:

.. autoclass:: FileClosedEvent
   :members:
   :show-inheritance:

.. autoclass:: FileClosedNoWriteEvent
   :members:
   :show-inheritance:

.. autoclass:: FileOpenedEvent
   :members:
   :show-inheritance:

.. autoclass:: DirCreatedEvent
   :members:
   :show-inheritance:

.. autoclass:: FileDeletedEvent
   :members:
   :show-inheritance:

.. autoclass:: DirDeletedEvent
   :members:
   :show-inheritance:


Event Handler Classes
---------------------
.. autoclass:: FileSystemEventHandler
   :members:
   :show-inheritance:

.. autoclass:: PathMatchingEventHandler
   :members:
   :show-inheritance:

.. autoclass:: PatternMatchingEventHandler
   :members:
   :show-inheritance:

.. autoclass:: RegexMatchingEventHandler
   :members:
   :show-inheritance:

.. autoclass:: LoggingEventHandler
   :members:
   :show-inheritance:

.. autoclass:: IgnorePolicy
   :members:
   :show-inheritance:
   :undoc-members:

"""

from __future__ import annotations

import logging
import os.path
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Literal

from watchdog.utils.patterns import match_any_paths

if TYPE_CHECKING:
    from collections.abc import Generator

EVENT_TYPE_MOVED = "moved"
EVENT_TYPE_DELETED = "deleted"
EVENT_TYPE_CREATED = "created"
EVENT_TYPE_MODIFIED = "modified"
EVENT_TYPE_CLOSED = "closed"
EVENT_TYPE_CLOSED_NO_WRITE = "closed_no_write"
EVENT_TYPE_OPENED = "opened"
EVENT_TYPE_ATTRIB = "attrib"


@dataclass(unsafe_hash=True)
class FileSystemEvent:
    """Represents a file system event that is triggered when a change
    occurs on the monitored file system.

    FileSystemEvent instances are mutable, so avoid using them as
    dictionary keys or set members: mutating an instance after
    insertion can silently break lookups.
    """

    src_path: bytes | str
    dest_path: bytes | str = ""
    event_type: str = field(default="", init=False)
    is_directory: bool = field(default=False, init=False)
    """True if event was triggered for a directory; False otherwise."""

    is_synthetic: bool = field(default=False)
    """True if event was synthesized; False otherwise.
    These are events that weren't actually broadcast by the OS, but
    are presumed to have happened based on other, actual events.
    """


class FileSystemMovedEvent(FileSystemEvent):
    """File system event representing any kind of file system movement."""

    event_type = EVENT_TYPE_MOVED


# File events.


class FileDeletedEvent(FileSystemEvent):
    """File system event representing file deletion on the file system."""

    event_type = EVENT_TYPE_DELETED


class FileModifiedEvent(FileSystemEvent):
    """File system event representing file modification on the file system."""

    event_type = EVENT_TYPE_MODIFIED


class FileAttribEvent(FileSystemEvent):
    """File system event representing file metadata modification on the file system.

    Emitted on Linux (inotify), macOS (FSEvents/kqueue), BSD, and Windows (via
    ``ReadDirectoryChangesExW`` on Windows 10 1709+ / Server 2016+; older versions
    or unsupported network shares fall back to ``ReadDirectoryChangesW`` where
    ``FileModifiedEvent`` is emitted instead).
    """

    event_type = EVENT_TYPE_ATTRIB


class FileCreatedEvent(FileSystemEvent):
    """File system event representing file creation on the file system."""

    event_type = EVENT_TYPE_CREATED


class FileMovedEvent(FileSystemMovedEvent):
    """File system event representing file movement on the file system."""


class FileClosedEvent(FileSystemEvent):
    """File system event representing file close on the file system.

    Emitted only by ``InotifyObserver`` on Linux.
    """

    event_type = EVENT_TYPE_CLOSED


class FileClosedNoWriteEvent(FileSystemEvent):
    """File system event representing an unmodified file close on the file system.

    Emitted only by ``InotifyObserver`` on Linux.
    """

    event_type = EVENT_TYPE_CLOSED_NO_WRITE


class FileOpenedEvent(FileSystemEvent):
    """File system event representing file open on the file system.

    Emitted only by ``InotifyObserver`` on Linux.
    """

    event_type = EVENT_TYPE_OPENED


# Directory events.


class DirDeletedEvent(FileSystemEvent):
    """File system event representing directory deletion on the file system."""

    event_type = EVENT_TYPE_DELETED
    is_directory = True


class DirModifiedEvent(FileSystemEvent):
    """File system event representing directory modification on the file system."""

    event_type = EVENT_TYPE_MODIFIED
    is_directory = True


class DirAttribEvent(FileSystemEvent):
    """File system event representing directory metadata modification on the file system.

    Emitted on Linux (inotify), macOS (FSEvents/kqueue), BSD, and Windows (via
    ``ReadDirectoryChangesExW`` on Windows 10 1709+ / Server 2016+; older versions
    or unsupported network shares fall back to ``ReadDirectoryChangesW`` where
    ``DirModifiedEvent`` is emitted instead).
    """

    event_type = EVENT_TYPE_ATTRIB
    is_directory = True


class DirCreatedEvent(FileSystemEvent):
    """File system event representing directory creation on the file system."""

    event_type = EVENT_TYPE_CREATED
    is_directory = True


class DirMovedEvent(FileSystemMovedEvent):
    """File system event representing directory movement on the file system."""

    is_directory = True


class FileSystemEventHandler:
    """Base file system event handler that you can override methods from."""

    def dispatch(self, event: FileSystemEvent) -> None:
        """Dispatches events to the appropriate methods.

        :param event:
            The event object representing the file system event.
        :type event:
            :class:`watchdog.events.FileSystemEvent`
        """
        self.on_any_event(event)
        getattr(self, f"on_{event.event_type}")(event)

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Catch-all event handler.

        :param event:
            The event object representing the file system event.
        :type event:
            :class:`watchdog.events.FileSystemEvent`
        """

    def on_moved(self, event: DirMovedEvent | FileMovedEvent) -> None:
        """Called when a file or a directory is moved or renamed.

        :param event:
            Event representing file/directory movement.
        :type event:
            :class:`watchdog.events.DirMovedEvent` or :class:`watchdog.events.FileMovedEvent`
        """

    def on_created(self, event: DirCreatedEvent | FileCreatedEvent) -> None:
        """Called when a file or directory is created.

        :param event:
            Event representing file/directory creation.
        :type event:
            :class:`watchdog.events.DirCreatedEvent` or :class:`watchdog.events.FileCreatedEvent`
        """

    def on_deleted(self, event: DirDeletedEvent | FileDeletedEvent) -> None:
        """Called when a file or directory is deleted.

        :param event:
            Event representing file/directory deletion.
        :type event:
            :class:`watchdog.events.DirDeletedEvent` or :class:`watchdog.events.FileDeletedEvent`
        """

    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        """Called when a file or directory is modified.

        :param event:
            Event representing file/directory modification.
        :type event:
            :class:`watchdog.events.DirModifiedEvent` or :class:`watchdog.events.FileModifiedEvent`
        """

    def on_attrib(self, event: DirAttribEvent | FileAttribEvent) -> None:
        """Called when a file or directory metadata is modified.

        :param event:
            Event representing file/directory metadata modification.
        :type event:
            :class:`watchdog.events.DirAttribEvent` or :class:`watchdog.events.FileAttribEvent`
        """

    def on_closed(self, event: FileClosedEvent) -> None:
        """Called when a file opened for writing is closed.

        Emitted only by ``InotifyObserver`` on Linux.

        :param event:
            Event representing file closing.
        :type event:
            :class:`watchdog.events.FileClosedEvent`
        """

    def on_closed_no_write(self, event: FileClosedNoWriteEvent) -> None:
        """Called when a file opened for reading is closed.

        Emitted only by ``InotifyObserver`` on Linux.

        :param event:
            Event representing file closing.
        :type event:
            :class:`watchdog.events.FileClosedNoWriteEvent`
        """

    def on_opened(self, event: FileOpenedEvent) -> None:
        """Called when a file is opened.

        Emitted only by ``InotifyObserver`` on Linux.

        :param event:
            Event representing file opening.
        :type event:
            :class:`watchdog.events.FileOpenedEvent`
        """


class IgnorePolicy(str, Enum):
    """Policy for ignoring multi-path events (such as file moves or renames)."""

    ANY = "any"
    """Drops the event if any path matches the ignore rules (strict mode, default)."""

    ALL = "all"
    """Drops the event only if all paths match the ignore rules (permissive mode)."""


class PathMatchingEventHandler(FileSystemEventHandler):
    """Base class for event handlers matching paths against patterns or regexes.

    :param ignore_directories:
        ``True`` if directories should be ignored; ``False`` otherwise.
    :param case_sensitive:
        ``True`` if path names should be matched sensitive to case; ``False``
        otherwise.
    :param ignore_policy:
        Policy for multi-path events (e.g. moves/renames). Defaults to
        :attr:`~watchdog.events.IgnorePolicy.ANY`.
    :type ignore_policy:
        :class:`~watchdog.events.IgnorePolicy` | str
    """

    def __init__(
        self,
        *,
        ignore_directories: bool = False,
        case_sensitive: bool = False,
        ignore_policy: IgnorePolicy | Literal["any", "all"] = IgnorePolicy.ANY,
    ) -> None:
        super().__init__()
        self._ignore_directories = ignore_directories
        self._case_sensitive = case_sensitive
        self._ignore_policy = IgnorePolicy(ignore_policy)

    @property
    def ignore_directories(self) -> bool:
        """``True`` if directories should be ignored; ``False`` otherwise."""
        return self._ignore_directories

    @property
    def case_sensitive(self) -> bool:
        """``True`` if path names should be matched sensitive to case; ``False``
        otherwise.
        """
        return self._case_sensitive

    @property
    def ignore_policy(self) -> IgnorePolicy:
        """Return the ignore policy."""
        return self._ignore_policy

    def is_ignored(self, path: str) -> bool:
        """Return True if path matches ignore criteria."""
        raise NotImplementedError

    def is_included(self, path: str) -> bool:
        """Return True if path matches include criteria."""
        raise NotImplementedError

    def _validate_rules(self) -> None:
        """Hook to validate matching and ignore rules."""

    def dispatch(self, event: FileSystemEvent) -> None:
        """Dispatches events to the appropriate methods.

        :param event:
            The event object representing the file system event.
        :type event:
            :class:`watchdog.events.FileSystemEvent`
        """
        if self.ignore_directories and event.is_directory:
            return

        paths = []
        if event.dest_path:
            paths.append(os.fsdecode(event.dest_path))
        if event.src_path:
            paths.append(os.fsdecode(event.src_path))

        if self.ignore_policy == IgnorePolicy.ANY:
            if any(self.is_ignored(p) for p in paths):
                return
        elif all(self.is_ignored(p) for p in paths):
            return

        if any(self.is_included(p) for p in paths):
            super().dispatch(event)


class PatternMatchingEventHandler(PathMatchingEventHandler):
    """Matches given patterns with file paths associated with occurring events.
    Uses pathlib's `PurePath.full_match()` method. `patterns` and `ignore_patterns`
    are expected to be a list of strings following standard glob syntax.

    Patterns follow standard glob semantics where ``*`` matches any characters,
    ``?`` matches a single character, and ``[...]`` denotes a character class.
    To match literal special characters like ``[``, use standard glob escapes
    such as ``[[]`` or :func:`glob.escape`.

    :param patterns:
        Patterns to allow matching event paths.
    :param ignore_patterns:
        Patterns to ignore matching event paths.
    :param ignore_directories:
        ``True`` if directories should be ignored; ``False`` otherwise.
    :param case_sensitive:
        ``True`` if path names should be matched sensitive to case; ``False``
        otherwise.
    :param ignore_policy:
        Policy for multi-path events (e.g. moves/renames). Defaults to
        :attr:`~watchdog.events.IgnorePolicy.ANY`.
    :type ignore_policy:
        :class:`~watchdog.events.IgnorePolicy` | str
    """

    def __init__(
        self,
        *,
        patterns: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
        ignore_directories: bool = False,
        case_sensitive: bool = False,
        ignore_policy: IgnorePolicy | Literal["any", "all"] = IgnorePolicy.ANY,
    ) -> None:
        super().__init__(
            ignore_directories=ignore_directories,
            case_sensitive=case_sensitive,
            ignore_policy=ignore_policy,
        )

        self._patterns = patterns
        self._ignore_patterns = ignore_patterns
        self._validate_rules()

    @property
    def patterns(self) -> list[str] | None:
        """Patterns to allow matching event paths."""
        return self._patterns

    @property
    def ignore_patterns(self) -> list[str] | None:
        """Patterns to ignore matching event paths."""
        return self._ignore_patterns

    def is_ignored(self, path: str) -> bool:
        return bool(
            self.ignore_patterns
            and match_any_paths(
                [path],
                included_patterns=self.ignore_patterns,
                case_sensitive=self.case_sensitive,
            )
        )

    def is_included(self, path: str) -> bool:
        return bool(
            match_any_paths(
                [path],
                included_patterns=self.patterns,
                case_sensitive=self.case_sensitive,
            )
        )

    def _validate_rules(self) -> None:
        if self.ignore_patterns:
            included = set(["**"] if self.patterns is None else self.patterns)
            excluded = set(self.ignore_patterns)
            if not self.case_sensitive:
                included = {p.lower() for p in included}
                excluded = {p.lower() for p in excluded}
            common_patterns = included & excluded
            if common_patterns:
                error = f"conflicting patterns `{common_patterns}` included and excluded"
                raise ValueError(error)


class RegexMatchingEventHandler(PathMatchingEventHandler):
    """Matches given regexes with file paths associated with occurring events.
    Uses the `re` module.

    :param regexes:
        Regexes to allow matching event paths.
    :param ignore_regexes:
        Regexes to ignore matching event paths.
    :param ignore_directories:
        ``True`` if directories should be ignored; ``False`` otherwise.
    :param case_sensitive:
        ``True`` if path names should be matched sensitive to case; ``False``
        otherwise.
    :param ignore_policy:
        Policy for multi-path events (e.g. moves/renames). Defaults to
        :attr:`~watchdog.events.IgnorePolicy.ANY`.
    :type ignore_policy:
        :class:`~watchdog.events.IgnorePolicy` | str
    """

    def __init__(
        self,
        *,
        regexes: list[str] | None = None,
        ignore_regexes: list[str] | None = None,
        ignore_directories: bool = False,
        case_sensitive: bool = False,
        ignore_policy: IgnorePolicy | Literal["any", "all"] = IgnorePolicy.ANY,
    ) -> None:
        super().__init__(
            ignore_directories=ignore_directories,
            case_sensitive=case_sensitive,
            ignore_policy=ignore_policy,
        )

        if regexes is None:
            regexes = [r".*"]
        elif isinstance(regexes, str):
            regexes = [regexes]
        if ignore_regexes is None:
            ignore_regexes = []
        flags = 0 if case_sensitive else re.IGNORECASE
        self._regexes = [re.compile(r, flags) for r in regexes]
        self._ignore_regexes = [re.compile(r, flags) for r in ignore_regexes]
        self._validate_rules()

    @property
    def regexes(self) -> list[re.Pattern[str]]:
        """Regexes to allow matching event paths."""
        return self._regexes

    @property
    def ignore_regexes(self) -> list[re.Pattern[str]]:
        """Regexes to ignore matching event paths."""
        return self._ignore_regexes

    def is_ignored(self, path: str) -> bool:
        return any(r.match(path) for r in self.ignore_regexes)

    def is_included(self, path: str) -> bool:
        return any(r.match(path) for r in self.regexes)

    def _validate_rules(self) -> None:
        if self._ignore_regexes:
            included = {r.pattern if self.case_sensitive else r.pattern.lower() for r in self._regexes}
            excluded = {r.pattern if self.case_sensitive else r.pattern.lower() for r in self._ignore_regexes}
            common_regexes = included & excluded
            if common_regexes:
                error = f"conflicting regexes `{common_regexes}` included and excluded"
                raise ValueError(error)


class LoggingEventHandler(FileSystemEventHandler):
    """Logs all the events captured."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        super().__init__()
        self.logger = logger or logging.root

    def on_moved(self, event: DirMovedEvent | FileMovedEvent) -> None:
        super().on_moved(event)

        what = "directory" if event.is_directory else "file"
        self.logger.info("Moved %s: from %s to %s", what, event.src_path, event.dest_path)

    def on_created(self, event: DirCreatedEvent | FileCreatedEvent) -> None:
        super().on_created(event)

        what = "directory" if event.is_directory else "file"
        self.logger.info("Created %s: %s", what, event.src_path)

    def on_deleted(self, event: DirDeletedEvent | FileDeletedEvent) -> None:
        super().on_deleted(event)

        what = "directory" if event.is_directory else "file"
        self.logger.info("Deleted %s: %s", what, event.src_path)

    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        super().on_modified(event)

        what = "directory" if event.is_directory else "file"
        self.logger.info("Modified %s: %s", what, event.src_path)

    def on_attrib(self, event: DirAttribEvent | FileAttribEvent) -> None:
        super().on_attrib(event)

        what = "directory" if event.is_directory else "file"
        self.logger.info("Attrib %s: %s", what, event.src_path)

    def on_closed(self, event: FileClosedEvent) -> None:
        super().on_closed(event)

        self.logger.info("Closed modified file: %s", event.src_path)

    def on_closed_no_write(self, event: FileClosedNoWriteEvent) -> None:
        super().on_closed_no_write(event)

        self.logger.info("Closed read file: %s", event.src_path)

    def on_opened(self, event: FileOpenedEvent) -> None:
        super().on_opened(event)

        self.logger.info("Opened file: %s", event.src_path)


def generate_sub_moved_events(
    src_dir_path: bytes | str,
    dest_dir_path: bytes | str,
) -> Generator[DirMovedEvent | FileMovedEvent]:
    """Generates an event list of :class:`DirMovedEvent` and
    :class:`FileMovedEvent` objects for all the files and directories within
    the given moved directory that were moved along with the directory.

    :param src_dir_path:
        The source path of the moved directory.
    :param dest_dir_path:
        The destination path of the moved directory.
    :returns:
        An iterable of file system events of type :class:`DirMovedEvent` and
        :class:`FileMovedEvent`.
    """
    for root, directories, filenames in os.walk(dest_dir_path):  # type: ignore[type-var]
        for directory in directories:
            full_path = os.path.join(root, directory)  # type: ignore[call-overload]
            renamed_path = src_dir_path + full_path[len(dest_dir_path) :] if src_dir_path else ""
            yield DirMovedEvent(renamed_path, full_path, is_synthetic=True)
        for filename in filenames:
            full_path = os.path.join(root, filename)  # type: ignore[call-overload]
            renamed_path = src_dir_path + full_path[len(dest_dir_path) :] if src_dir_path else ""
            yield FileMovedEvent(renamed_path, full_path, is_synthetic=True)


def generate_sub_created_events(src_dir_path: bytes | str) -> Generator[DirCreatedEvent | FileCreatedEvent]:
    """Generates an event list of :class:`DirCreatedEvent` and
    :class:`FileCreatedEvent` objects for all the files and directories within
    the given moved directory that were moved along with the directory.

    :param src_dir_path:
        The source path of the created directory.
    :returns:
        An iterable of file system events of type :class:`DirCreatedEvent` and
        :class:`FileCreatedEvent`.
    """
    for root, directories, filenames in os.walk(src_dir_path):  # type: ignore[type-var]
        for directory in directories:
            full_path = os.path.join(root, directory)  # type: ignore[call-overload]
            yield DirCreatedEvent(full_path, is_synthetic=True)
        for filename in filenames:
            full_path = os.path.join(root, filename)  # type: ignore[call-overload]
            yield FileCreatedEvent(full_path, is_synthetic=True)
