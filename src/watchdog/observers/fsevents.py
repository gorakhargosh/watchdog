# -*- coding: utf-8 -*-
# fsevents.py: FSEvents-based event emitter for Mac OS X.
#
# Copyright (C) 2010 Yesudeep Mangalapilly <yesudeep@gmail.com>
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
:module: watchdog.observers.fsevents
:synopsis: FSEvents based emitter implementation.
:author: Yesudeep Mangalapilly <yesudeep@gmail.com>
:platforms: Mac OS X
"""

from __future__ import with_statement
from watchdog.utils import platform

if platform.is_darwin():
    import threading
    import unicodedata
    import os.path
    import _watchdog_fsevents as _fsevents

    from pathtools.path import absolute_path
    from watchdog.events import\
        FileDeletedEvent,\
        FileModifiedEvent,\
        FileCreatedEvent,\
        FileMovedEvent,\
        DirDeletedEvent,\
        DirModifiedEvent,\
        DirCreatedEvent,\
        DirMovedEvent,\
        DirMovedEvent
    from watchdog.utils.dirsnapshot import DirectorySnapshot
    from watchdog.observers.api import\
        BaseObserver,\
        EventEmitter,\
        DEFAULT_EMITTER_TIMEOUT,\
        DEFAULT_OBSERVER_TIMEOUT


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
            self.snapshot = DirectorySnapshot(watch.path, watch.is_recursive)

        def on_thread_exit(self):
            _fsevents.remove_watch(self.watch)
            _fsevents.stop(self)

        def queue_events(self, timeout):
            with self._lock:
                if not self.watch.is_recursive\
                and self.watch.path not in pathnames:
                    return
                new_snapshot = DirectorySnapshot(self.watch.path,
                                                 self.watch.is_recursive)
                events = new_snapshot - self.snapshot
                self.snapshot = new_snapshot

                # Files.
                for src_path in events.files_deleted:
                    self.queue_event(FileDeletedEvent(src_path))
                for src_path in events.files_modified:
                    self.queue_event(FileModifiedEvent(src_path))
                for src_path in events.files_created:
                    self.queue_event(FileCreatedEvent(src_path))
                for src_path, dest_path in events.files_moved:
                    self.queue_event(FileMovedEvent(src_path, dest_path))

                # Directories.
                for src_path in events.dirs_deleted:
                    self.queue_event(DirDeletedEvent(src_path))
                for src_path in events.dirs_modified:
                    self.queue_event(DirModifiedEvent(src_path))
                for src_path in events.dirs_created:
                    self.queue_event(DirCreatedEvent(src_path))
                for src_path, dest_path in events.dirs_moved:
                    self.queue_event(DirMovedEvent(src_path, dest_path))


        def run(self):
            try:
                def callback(pathnames, flags, emitter=self):
                    emitter.queue_events(emitter.timeout)

                #for pathname, flag in zip(pathnames, flags):
                #if emitter.watch.is_recursive: # and pathname != emitter.watch.path:
                #    new_sub_snapshot = DirectorySnapshot(pathname, True)
                #    old_sub_snapshot = self.snapshot.copy(pathname)
                #    diff = new_sub_snapshot - old_sub_snapshot
                #    self.snapshot += new_subsnapshot
                #else:
                #    new_snapshot = DirectorySnapshot(emitter.watch.path, False)
                #    diff = new_snapshot - emitter.snapshot
                #    emitter.snapshot = new_snapshot


                # INFO: FSEvents reports directory notifications recursively
                # by default, so we do not need to add subdirectory paths.
                #pathnames = set([self.watch.path])
                #if self.watch.is_recursive:
                #    for root, directory_names, _ in os.walk(self.watch.path):
                #        for directory_name in directory_names:
                #            full_path = absolute_path(
                #                            os.path.join(root, directory_name))
                #            pathnames.add(full_path)

                pathnames = [self.watch.path]
                _fsevents.add_watch(self,
                                    self.watch,
                                    callback,
                                    pathnames)
                _fsevents.read_events(self)
            finally:
                self.on_thread_exit()


    class FSEventsObserver(BaseObserver):
        def __init__(self, timeout=DEFAULT_OBSERVER_TIMEOUT):
            BaseObserver.__init__(self, emitter_class=FSEventsEmitter,
                                  timeout=timeout)

        def schedule(self, event_handler, path, recursive=False):
            # Fix for issue #26: Trace/BPT error when given a unicode path
            # string. https://github.com/gorakhargosh/watchdog/issues#issue/26
            if isinstance(path, unicode):
                #path = unicode(path, 'utf-8')
                path = unicodedata.normalize('NFC', path).encode('utf-8')
            BaseObserver.schedule(self, event_handler, path, recursive)
