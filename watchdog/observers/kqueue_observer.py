# -*- coding: utf-8 -*-
# kqueue_observer.py: kqueue-based observer implementation for BSD systems.
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

from __future__ import with_statement

import os
import stat
import sys
import errno
import os.path
import threading

from watchdog.utils import has_attribute
import select
if not has_attribute(select, 'kqueue') or sys.version_info < (2,7,0):
    import select_backport as select

from watchdog.utils import echo

from watchdog.utils import absolute_path, real_absolute_path
from watchdog.utils.dirsnapshot import DirectorySnapshot
from watchdog.observers import _EventEmitter
from watchdog.observers.polling_observer import PollingObserver
from watchdog.events import DirMovedEvent, DirDeletedEvent, DirCreatedEvent, DirModifiedEvent, \
    FileMovedEvent, FileDeletedEvent, FileCreatedEvent, FileModifiedEvent

import logging
logging.basicConfig(level=logging.DEBUG)

# Maximum number of events to process.
MAX_EVENTS = 104896

# Mac OS X file system performance guidelines:
# --------------------------------------------
# http://developer.apple.com/library/ios/#documentation/Performance/Conceptual/FileSystem/Articles/TrackingChanges.html#//apple_ref/doc/uid/20001993-CJBJFIDD
# http://www.mlsite.net/blog/?p=2312
#
# Specifically:
# -------------
# When you only want to track changes on a file or directory, be sure to
# open it# using the O_EVTONLY flag. This flag prevents the file or
# directory from being marked as open or in use. This is important
# if you are tracking files on a removable volume and the user tries to
# unmount the volume. With this flag in place, the system knows it can
# dismiss the volume. If you had opened the files or directories without
# this flag, the volume would be marked as busy and would not be unmounted.
O_EVTONLY = 0x8000

# Flags pre-calculated that we will use for the kevent filter, flags, and
# fflags attributes.
if sys.platform == 'darwin':
    WATCHDOG_OS_OPEN_FLAGS = O_EVTONLY
else:
    WATCHDOG_OS_OPEN_FLAGS = os.O_RDONLY | os.O_NONBLOCK
WATCHDOG_KQ_FILTER = select.KQ_FILTER_VNODE
WATCHDOG_KQ_EV_FLAGS = select.KQ_EV_ADD | select.KQ_EV_ENABLE | select.KQ_EV_CLEAR
WATCHDOG_KQ_FFLAGS = \
    select.KQ_NOTE_DELETE | \
    select.KQ_NOTE_WRITE  | \
    select.KQ_NOTE_EXTEND | \
    select.KQ_NOTE_ATTRIB | \
    select.KQ_NOTE_LINK   | \
    select.KQ_NOTE_RENAME | \
    select.KQ_NOTE_REVOKE


def create_kevent_for_path(path):
    """Creates a kevent for the given path."""
    fd = os.open(path, WATCHDOG_OS_OPEN_FLAGS)
    kev = select.kevent(fd,
                        filter=WATCHDOG_KQ_FILTER,
                        flags=WATCHDOG_KQ_EV_FLAGS,
                        fflags=WATCHDOG_KQ_FFLAGS)
    return kev, fd


# Flag tests.
def is_deleted(kev):
    """Determines whether the given kevent represents deletion."""
    return kev.fflags & select.KQ_NOTE_DELETE

def is_modified(kev):
    """Determines whether the given kevent represents modification."""
    fflags = kev.fflags
    return (fflags & select.KQ_NOTE_EXTEND) or (fflags & select.KQ_NOTE_WRITE)

def is_attrib_modified(kev):
    """Determines whether the given kevent represents attribute modification."""
    return kev.fflags & select.KQ_NOTE_ATTRIB

def is_renamed(kev):
    """Determines whether the given kevent represents movement."""
    return kev.fflags & select.KQ_NOTE_RENAME


class _Watch(object):
    """Handy structure to store relevant information in."""
    def __init__(self, fd, kev, path, is_directory):
        self.fd = fd
        self.path = path
        self.kev = kev
        self.is_directory = is_directory


class _KqueueEventEmitter(_EventEmitter):
    def __init__(self, path, handler, event_queue, recursive, interval=1):
        super(_KqueueEventEmitter, self).__init__(path, handler, event_queue, recursive, interval)

        #self._lock = threading.RLock()

        self._kq = select.kqueue()
        self._kevent_list = list()
        self._watch_table = dict()
        self._descriptors = set()

        def walker_callback(path, stat_info, self=self):
            self._register_path(path, stat.S_ISDIR(stat_info.st_mode))
        self._dir_snapshot = DirectorySnapshot(path, recursive, walker_callback)


    def _unregister_path(self, path):
        """Bookkeeping method that unregisters watching a given path."""
        #with self.lock:
        path = absolute_path(path)
        if path in self._watch_table:
            watch = self._watch_table[path]
            self._kevent_list.remove(watch.kev)
            del self._watch_table[path]
            del self._watch_table[watch.fd]
            try:
                os.close(watch.fd)
            except OSError, e:
                logging.warn(e)
            self._descriptors.remove(watch.fd)


    def _register_path(self, path, is_directory=False):
        """Bookkeeping method that registers watching a given path."""
        #with self._lock:
        path = absolute_path(path)
        if not path in self._watch_table:
            try:
                # If we haven't registered a kevent for this path already,
                # add a new kevent for the path.
                kev, fd = create_kevent_for_path(path)
                self._kevent_list.append(kev)
                watch = _Watch(fd, kev, path, is_directory)
                self._descriptors.add(fd)
                self._watch_table[fd] = watch
                self._watch_table[path] = watch
            except OSError, e:
                if e.errno == errno.ENOENT:
                    # No such file or directory.
                    # Possibly a temporary file we can ignore.
                    if is_directory:
                        event_created_class = DirCreatedEvent
                        event_deleted_class = DirDeletedEvent
                    else:
                        event_created_class = FileCreatedEvent
                        event_deleted_class = FileDeletedEvent

                    self.event_queue.put(
                        event_created_class(path,
                                            handlers=self.handlers))
                    self.event_queue.put(
                        event_deleted_class(path,
                                            handlers=self.handlers))

    def _kevent_file_renames(self, ref_dir_snapshot, new_dir_snapshot, files_renamed):
        """Process kevent-hinted file renames. These may be deletes too
        relative to the watched directory."""
        for path_renamed in files_renamed:
            # These are kqueue-hinted renames. We classify them into
            # either moved if the new path is found or deleted.
            try:
                ref_stat_info = ref_dir_snapshot.stat_info(path_renamed)
            except KeyError:
                # Caught a temporary file most probably.
                # So fire a created+deleted event sequence.
                self.event_queue.put(
                    FileCreatedEvent(path_renamed,
                                     handlers=self.handlers))
                self.event_queue.put(
                    FileDeletedEvent(path_renamed,
                                     handlers=self.handlers))
                continue

            try:
                path = new_dir_snapshot.path_for_inode(ref_stat_info.st_ino)
                self.event_queue.put(
                    FileMovedEvent(path_renamed,
                                   dest_path=path,
                                   handlers=self.handlers))
                self._unregister_path(path_renamed)
                self._register_path(path, is_directory=False)
            except KeyError:
                # We could not find the new name.
                self.event_queue.put(
                    FileDeletedEvent(path_renamed,
                                     handlers=self.handlers))
                self._unregister_path(path_renamed)

    def _kevent_dir_renames(self, ref_dir_snapshot, new_dir_snapshot, dirs_renamed):
        """Process kevent-hinted directory renames. These may be deletes
        too relative to the watched directory."""
        for path_renamed in dirs_renamed:
            # These are kqueue-hinted renames. We classify them into
            # either moved if the new path is found or deleted.
            try:
                ref_stat_info = ref_dir_snapshot.stat_info(path_renamed)
            except KeyError:
                # Caught a temporary directory most probably.
                # So fire a created+deleted event sequence.
                self.event_queue.put(
                    DirCreatedEvent(path_renamed,
                                    handlers=self.handlers))
                self.event_queue.put(
                    DirDeletedEvent(path_renamed,
                                    handlers=self.handlers))
                continue

            try:
                path = new_dir_snapshot.path_for_inode(ref_stat_info.st_ino)
                path = absolute_path(path)

                # If we're in recursive mode, we fire move events for
                # the entire contents of the moved directory.
                if self._is_recursive:
                    dir_path_renamed = absolute_path(path_renamed)
                    for root, directories, filenames in os.walk(path):
                        for directory_path in directories:
                            full_path = os.path.join(root, directory_path)
                            renamed_path = full_path.replace(path, dir_path_renamed)

                            self.event_queue.put(
                                DirMovedEvent(src_path=renamed_path,
                                              dest_path=full_path,
                                              handlers=self.handlers))

                            self._unregister_path(renamed_path)
                            self._register_path(full_path, is_directory=True)
                        for filename in filenames:
                            full_path = os.path.join(root, filename)
                            renamed_path = full_path.replace(path, dir_path_renamed)

                            self.event_queue.put(
                                FileMovedEvent(src_path=renamed_path,
                                               dest_path=full_path,
                                               handlers=self.handlers))

                            self._unregister_path(renamed_path)
                            self._register_path(full_path, is_directory=False)

                # Fire the directory moved event after firing moved
                # events for its children file system objects.
                self.event_queue.put(
                    DirMovedEvent(src_path=path_renamed,
                                  dest_path=path,
                                  handlers=self.handlers))
                self._unregister_path(path_renamed)
                self._register_path(path, is_directory=True)
            except KeyError:
                # We could not find the new name.
                self.event_queue.put(
                    DirDeletedEvent(path_renamed,
                                    handlers=self.handlers))
                self._unregister_path(path)

    def _kevent_dir_modifications(self, ref_dir_snapshot, new_dir_snapshot, dirs_modified):
        """Process kevent-hinted directory modifications. Created
        files/directories are also detected here."""
        if dirs_modified:
            for dir_modified in dirs_modified:
                self.event_queue.put(
                    DirModifiedEvent(dir_modified,
                                     handlers=self.handlers))
                # Don't need to register here. It's already registered.
                # self._register_path(dir_modified, is_directory=True)

            diff = new_dir_snapshot - ref_dir_snapshot

            for file_created in diff.files_created:
                self.event_queue.put(
                    FileCreatedEvent(file_created,
                                     handlers=self.handlers))
                self._register_path(file_created, is_directory=False)

            for dir_created in diff.dirs_created:
                self.event_queue.put(
                    DirCreatedEvent(dir_created,
                                    handlers=self.handlers))
                self._register_path(dir_created, is_directory=True)

    def _kevents_except_movement(self, event_list):
        """Process only basic kevents. Movement and directory modifications
        need to be further processed."""
        files_renamed = set()
        dirs_renamed = set()
        dirs_modified = set()
        for kev in event_list:
            watch = self._watch_table[kev.ident]
            src_path = watch.path

            if is_deleted(kev):
                # Deleted
                if watch.is_directory:
                    event = DirDeletedEvent(src_path,
                                            handlers=self.handlers)
                else:
                    event = FileDeletedEvent(src_path,
                                             handlers=self.handlers)
                self.event_queue.put(event)
                self._unregister_path(src_path)

            elif is_attrib_modified(kev):
                # Modified
                if watch.is_directory:
                    event = DirModifiedEvent(src_path,
                                             handlers=self.handlers)
                else:
                    event = FileModifiedEvent(src_path,
                                              handlers=self.handlers)
                self.event_queue.put(event)

            elif is_modified(kev):
                # Modified
                if watch.is_directory:
                    dirs_modified.add(src_path)
                else:
                    self.event_queue.put(
                        FileModifiedEvent(src_path,
                                          handlers=self.handlers))

            elif is_renamed(kev):
                # Renamed/moved
                if watch.is_directory:
                    dirs_renamed.add(src_path)
                else:
                    files_renamed.add(src_path)

        return files_renamed, dirs_renamed, dirs_modified


    def _queue_events(self):
        """Blocking call to kqueue.control that enlists events and then
    processes them classifying them into various events defined in watchdog.events."""
        with self._lock:
            event_list = self._kq.control(list(self._kevent_list), MAX_EVENTS)
            files_renamed, dirs_renamed, dirs_modified = \
                self._kevents_except_movement(event_list)

            # Take a fresh snapshot of the directory and update saved snapshot.
            new_dir_snapshot = DirectorySnapshot(self._path, self._is_recursive)
            ref_dir_snapshot = self._dir_snapshot
            self._dir_snapshot = new_dir_snapshot

            # Process events for renames and directories modified.
            if files_renamed or dirs_renamed or dirs_modified:
                self._kevent_file_renames(ref_dir_snapshot,
                                          new_dir_snapshot,
                                          files_renamed)
                self._kevent_dir_renames(ref_dir_snapshot,
                                         new_dir_snapshot,
                                         dirs_renamed)
                self._kevent_dir_modifications(ref_dir_snapshot,
                                               new_dir_snapshot,
                                               dirs_modified)

    def run(self):
        while not self.is_stopped:
            try:
                #if not os.path.exists(self._path):
                #    self.stop()
                #    continue
                self._queue_events()
            except OSError, e:
                if e.errno == errno.EBADF:
                    # select.kqueue seems to be blowing up on the first
                    # call to kqueue.control with this error.
                    logging.debug(e)
                    continue
                else:
                    raise
        self._clean_up()


    def _clean_up(self):
        # Close all open file descriptors
        for fd in self._descriptors:
            try:
                os.close(fd)
            except OSError, e:
                logging.warn(e)
        self._kq.close()


class KqueueObserver(PollingObserver):
    """BSD/OS X kqueue-based observer implementation."""
    def create_event_emitter(self, path, handler, event_queue, recursive, interval):
        return _KqueueEventEmitter(path=path,
                                   handler=handler,
                                   event_queue=event_queue,
                                   recursive=recursive,
                                   interval=interval)
