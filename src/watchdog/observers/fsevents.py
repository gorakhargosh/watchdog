# coding: utf-8
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc & contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
:module: watchdog.observers.fsevents
:synopsis: FSEvents based emitter implementation.
:author: yesudeep@google.com (Yesudeep Mangalapilly)
:author: contact@tiger-222.fr (Mickaël Schoentgen)
:platforms: Mac OS X
"""

import os
import threading
import unicodedata
import _watchdog_fsevents as _fsevents

from watchdog.events import (
    FileDeletedEvent,
    FileModifiedEvent,
    FileCreatedEvent,
    FileMovedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirCreatedEvent,
    DirMovedEvent
)

from watchdog.observers.api import (
    BaseObserver,
    EventEmitter,
    DEFAULT_EMITTER_TIMEOUT,
    DEFAULT_OBSERVER_TIMEOUT
)


class FSEventsEmitter(EventEmitter):

    """
    Mac OS X FSEvents Emitter class.

    :param event_queue:
        The event queue to fill with events.
    :param watch:
        A watch object representing the directory to monitor.
    :type watch:
        :class:`watchdog.observers.api.ObservedWatch`
    :param timeout:
        Read events blocking timeout (in seconds).
    :type timeout:
        ``float``
    """

    def __init__(self, event_queue, watch, timeout=DEFAULT_EMITTER_TIMEOUT):
        EventEmitter.__init__(self, event_queue, watch, timeout)
        self._lock = threading.Lock()

    def on_thread_stop(self):
        if self.watch:
            _fsevents.remove_watch(self.watch)
            _fsevents.stop(self)
            self._watch = None

    def queue_events(self, timeout):
        with self._lock:
            events = self.native_events
            i = 0
            while i < len(events):
                event = events[i]
                src_path = self._encode_path(event.path)

                # For some reason the create and remove flags are sometimes also
                # set for rename and modify type events, so let those take
                # precedence.
                if event.is_renamed:
                    # Internal moves appears to always be consecutive in the same
                    # buffer and have IDs differ by exactly one (while others
                    # don't) making it possible to pair up the two events coming
                    # from a singe move operation. (None of this is documented!)
                    # Otherwise, guess whether file was moved in or out.
                    # TODO: handle id wrapping
                    if (i + 1 < len(events) and events[i + 1].is_renamed
                            and events[i + 1].event_id == event.event_id + 1):
                        cls = DirMovedEvent if event.is_directory else FileMovedEvent
                        dst_path = self._encode_path(events[i + 1].path)
                        self.queue_event(cls(src_path, dst_path))
                        self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
                        self.queue_event(DirModifiedEvent(os.path.dirname(dst_path)))
                        i += 1
                    elif os.path.exists(event.path):
                        cls = DirCreatedEvent if event.is_directory else FileCreatedEvent
                        self.queue_event(cls(src_path))
                        self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
                    else:
                        cls = DirDeletedEvent if event.is_directory else FileDeletedEvent
                        self.queue_event(cls(src_path))
                        self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
                    # TODO: generate events for tree

                elif event.is_modified or event.is_inode_meta_mod or event.is_xattr_mod:
                    cls = DirModifiedEvent if event.is_directory else FileModifiedEvent
                    self.queue_event(cls(src_path))

                elif event.is_created:
                    cls = DirCreatedEvent if event.is_directory else FileCreatedEvent
                    self.queue_event(cls(src_path))
                    self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))

                elif event.is_removed:
                    cls = DirDeletedEvent if event.is_directory else FileDeletedEvent
                    self.queue_event(cls(src_path))
                    self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))

                    if src_path == self.watch.path:
                        # this should not really occur, instead we expect
                        # is_root_changed to be set
                        self.stop()

                elif event.is_root_changed:
                    # This will be set if root or any if its parents is renamed or
                    # deleted.
                    # TODO: find out new path and generate DirMovedEvent?
                    self.queue_event(DirDeletedEvent(self.watch.path))
                    self.stop()

                i += 1

    def run(self):
        try:
            def callback(pathnames, flags, ids, emitter=self):
                with emitter._lock:
                    emitter.native_events = [
                        _fsevents.NativeEvent(event_path, event_flags, event_id)
                        for event_path, event_flags, event_id in zip(pathnames, flags, ids)
                    ]
                emitter.queue_events(emitter.timeout)

            # for pathname, flag in zip(pathnames, flags):
            # if emitter.watch.is_recursive: # and pathname != emitter.watch.path:
            #    new_sub_snapshot = DirectorySnapshot(pathname, True)
            #    old_sub_snapshot = self.snapshot.copy(pathname)
            #    diff = new_sub_snapshot - old_sub_snapshot
            #    self.snapshot += new_subsnapshot
            # else:
            #    new_snapshot = DirectorySnapshot(emitter.watch.path, False)
            #    diff = new_snapshot - emitter.snapshot
            #    emitter.snapshot = new_snapshot

            # INFO: FSEvents reports directory notifications recursively
            # by default, so we do not need to add subdirectory paths.
            # pathnames = set([self.watch.path])
            # if self.watch.is_recursive:
            #    for root, directory_names, _ in os.walk(self.watch.path):
            #        for directory_name in directory_names:
            #            full_path = absolute_path(
            #                            os.path.join(root, directory_name))
            #            pathnames.add(full_path)
            self.pathnames = [self.watch.path]
            _fsevents.add_watch(self,
                                self.watch,
                                callback,
                                self.pathnames)
            _fsevents.read_events(self)
        except Exception:
            pass

    def _encode_path(self, path):
        """Encode path only if bytes were passed to this emitter. """
        if isinstance(self.watch.path, bytes):
            return os.fsencode(path)
        return path


class FSEventsObserver(BaseObserver):

    def __init__(self, timeout=DEFAULT_OBSERVER_TIMEOUT):
        BaseObserver.__init__(self, emitter_class=FSEventsEmitter,
                              timeout=timeout)

    def schedule(self, event_handler, path, recursive=False):
        # Fix for issue #26: Trace/BPT error when given a unicode path
        # string. https://github.com/gorakhargosh/watchdog/issues#issue/26
        if isinstance(path, str):
            path = unicodedata.normalize('NFC', path)
        return BaseObserver.schedule(self, event_handler, path, recursive)
