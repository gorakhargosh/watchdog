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

import logging
import os
import sys
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
    DirMovedEvent,
    generate_sub_created_events,
    generate_sub_moved_events
)

from watchdog.observers.api import (
    BaseObserver,
    EventEmitter,
    DEFAULT_EMITTER_TIMEOUT,
    DEFAULT_OBSERVER_TIMEOUT
)

from watchdog.utils import unicode_paths

logger = logging.getLogger('fsevents')


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

    def queue_event(self, event):
        logger.info("queue_event %s", event)
        EventEmitter.queue_event(self, event)

    def queue_events(self, timeout, events):

        if logger.getEffectiveLevel() <= logging.DEBUG:
            for event in events:
                flags = ", ".join(attr for attr in dir(event) if getattr(event, attr) is True)
                logger.debug("%s: %s", event, flags)

        while events:
            event = events.pop(0)
            src_path = self._encode_path(event.path)

            if event.is_renamed:
                dest_event = next(iter(e for e in events if e.is_renamed and e.inode == event.inode), None)
                if dest_event:
                    # item was moved within the watched folder
                    events.remove(dest_event)
                    logger.debug("Destination event for rename is %s", dest_event)
                    cls = DirMovedEvent if event.is_directory else FileMovedEvent
                    dst_path = self._encode_path(dest_event.path)
                    self.queue_event(cls(src_path, dst_path))
                    self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
                    self.queue_event(DirModifiedEvent(os.path.dirname(dst_path)))
                    for sub_event in generate_sub_moved_events(src_path, dst_path):
                        logger.debug("Generated sub event: %s", sub_event)
                        self.queue_event(sub_event)
                elif os.path.exists(event.path):
                    # item was moved into the watched folder
                    cls = DirCreatedEvent if event.is_directory else FileCreatedEvent
                    self.queue_event(cls(src_path))
                    self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))
                    for sub_event in generate_sub_created_events(src_path):
                        self.queue_event(sub_event)
                else:
                    # item was moved out of the watched folder
                    cls = DirDeletedEvent if event.is_directory else FileDeletedEvent
                    self.queue_event(cls(src_path))
                    self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))

            if event.is_created:
                cls = DirCreatedEvent if event.is_directory else FileCreatedEvent
                if not event.is_coalesced or (
                    event.is_coalesced and not event.is_renamed and not event.is_modified and not
                    event.is_inode_meta_mod and not event.is_xattr_mod
                ):
                    self.queue_event(cls(src_path))
                    self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))

            if event.is_modified and not event.is_coalesced and os.path.exists(src_path):
                cls = DirModifiedEvent if event.is_directory else FileModifiedEvent
                self.queue_event(cls(src_path))

            if event.is_inode_meta_mod or event.is_xattr_mod:
                if os.path.exists(src_path) and not event.is_coalesced:
                    # NB: in the scenario of touch(file) -> rm(file) we can trigger this twice
                    cls = DirModifiedEvent if event.is_directory else FileModifiedEvent
                    self.queue_event(cls(src_path))

            if event.is_removed:
                cls = DirDeletedEvent if event.is_directory else FileDeletedEvent
                if not event.is_coalesced or (event.is_coalesced and not os.path.exists(event.path)):
                    self.queue_event(cls(src_path))
                    self.queue_event(DirModifiedEvent(os.path.dirname(src_path)))

                    if src_path == self.watch.path:
                        # this should not really occur, instead we expect
                        # is_root_changed to be set
                        logger.debug("Stopping because root path was removed")
                        self.stop()

            if event.is_root_changed:
                # This will be set if root or any of its parents is renamed or
                # deleted.
                # TODO: find out new path and generate DirMovedEvent?
                self.queue_event(DirDeletedEvent(self.watch.path))
                logger.debug("Stopping because root path was changed")
                self.stop()

    def run(self):
        try:
            def callback(paths, inodes, flags, ids, emitter=self):
                try:
                    with emitter._lock:
                        events = [
                            _fsevents.NativeEvent(path, inode, event_flags, event_id)
                            for path, inode, event_flags, event_id in zip(paths, inodes, flags, ids)
                        ]
                        emitter.queue_events(emitter.timeout, events)
                except Exception:
                    logger.exception("Unhandled exception in fsevents callback")

            self.pathnames = [self.watch.path]

            _fsevents.add_watch(self, self.watch, callback, self.pathnames)
            _fsevents.read_events(self)
        except Exception:
            logger.exception("Unhandled exception in FSEventsEmitter")

    def _encode_path(self, path):
        """Encode path only if bytes were passed to this emitter. """
        if isinstance(self.watch.path, unicode_paths.bytes_cls):
            return path.encode('utf-8')
        return path


class FSEventsObserver(BaseObserver):

    def __init__(self, timeout=DEFAULT_OBSERVER_TIMEOUT):
        BaseObserver.__init__(self, emitter_class=FSEventsEmitter,
                              timeout=timeout)

    def schedule(self, event_handler, path, recursive=False):
        # Fix for issue #26: Trace/BPT error when given a unicode path
        # string. https://github.com/gorakhargosh/watchdog/issues#issue/26
        if isinstance(path, unicode_paths.str_cls):
            path = unicodedata.normalize('NFC', path)
            # We only encode the path in Python 2 for backwards compatibility.
            # On Python 3 we want the path to stay as unicode if possible for
            # the sake of path matching not having to be rewritten to use the
            # bytes API instead of strings. The _watchdog_fsevent.so code for
            # Python 3 can handle both str and bytes paths, which is why we
            # do not HAVE to encode it with Python 3. The Python 2 code in
            # _watchdog_fsevents.so was not changed for the sake of backwards
            # compatibility.
            if sys.version_info < (3,):
                path = path.encode('utf-8')
        return BaseObserver.schedule(self, event_handler, path, recursive)
