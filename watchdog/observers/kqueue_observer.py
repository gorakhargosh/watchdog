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


import os
import stat
import sys
import errno
import os.path

from watchdog.utils import has_attribute, absolute_path, real_absolute_path

try:
    # Python 3k
    from queue import Queue, Empty as QueueEmpty
except ImportError:
    from Queue import Queue, Empty as QueueEmpty
import select
if not has_attribute(select, 'kqueue') or sys.version_info < (2,7,0):
    import select_backport as select

from threading import Thread, Lock as ThreadedLock, Event as ThreadedEvent
from watchdog.utils.dirsnapshot import DirectorySnapshot
from watchdog.decorator_utils import synchronized
from watchdog.observers import DaemonThread
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


class _FileSystemObject(object):
    """Handy structure to store relevant information in."""
    def __init__(self, fd, kev, path, is_directory):
        self.fd = fd
        self.path = path
        self.kev = kev
        self.is_directory = is_directory


class _KqueueEventEmitter(DaemonThread):
    def __init__(self, path, out_event_queue, recursive, interval=1):
        super(_KqueueEventEmitter, self).__init__(interval)
        self.path = real_absolute_path(path)
        self.out_event_queue = out_event_queue
        self.is_recursive = recursive
        self.kq = select.kqueue()
        self.kevent_list = list()
        self.fso_table = dict()
        self.descriptor_list = set()
        self.dir_snapshot = None


    @synchronized()
    def register_dir_tree(self, path, recursive):
        """Registers event handling for an entire directory tree."""
        path = real_absolute_path(path)
        def walker_callback(path, stat_info, self=self):
            self.register_path(path, stat.S_ISDIR(stat_info.st_mode))
        self.dir_snapshot = DirectorySnapshot(path, recursive, walker_callback)


    @synchronized()
    def unregister_path(self, path):
        """Bookkeeping method that unregisters watching a given path."""
        path = absolute_path(path)
        if path in self.fso_table:
            fso = self.fso_table[path]
            self.kevent_list.remove(fso.kev)
            del self.fso_table[path]
            del self.fso_table[fso.fd]
            try:
                os.close(fso.fd)
            except OSError, e:
                logging.warn(e)
            self.descriptor_list.remove(fso.fd)


    @synchronized()
    def register_path(self, path, is_directory=False):
        """Bookkeeping method that registers watching a given path."""
        path = absolute_path(path)
        if not path in self.fso_table:
            try:
                # If we haven't registered a kevent for this path already,
                # add a new kevent for the path.
                kev, fd = create_kevent_for_path(path)
                self.kevent_list.append(kev)
                fso = _FileSystemObject(fd, kev, path, is_directory)
                self.descriptor_list.add(fd)
                self.fso_table[fd] = fso
                self.fso_table[path] = fso
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
                    self.out_event_queue.put((self.path, event_created_class(path)))
                    self.out_event_queue.put((self.path, event_deleted_class(path)))
                    #logging.warn(e)


    def __process_kevents_except_movement(self, event_list, out_event_queue):
        """Process only basic kevents. Movement and directory modifications
        need to be further processed."""
        files_renamed = set()
        dirs_renamed = set()
        dirs_modified = set()

        for kev in event_list:
            fso = self.fso_table[kev.ident]
            src_path = fso.path

            if is_deleted(kev):
                if fso.is_directory:
                    event = DirDeletedEvent(src_path=src_path)
                else:
                    event = FileDeletedEvent(src_path=src_path)
                out_event_queue.put((self.path, event))
                self.unregister_path(src_path)
            elif is_attrib_modified(kev):
                if fso.is_directory:
                    event = DirModifiedEvent(src_path=src_path)
                else:
                    event = FileModifiedEvent(src_path=src_path)
                out_event_queue.put((self.path, event))
            elif is_modified(kev):
                if fso.is_directory:
                    dirs_modified.add(src_path)
                else:
                    out_event_queue.put((self.path, FileModifiedEvent(src_path=src_path)))
            elif is_renamed(kev):
                if fso.is_directory:
                    dirs_renamed.add(src_path)
                else:
                    files_renamed.add(src_path)

        return files_renamed, dirs_renamed, dirs_modified


    def __process_kevent_file_renames(self, out_event_queue, \
                                          ref_dir_snapshot, \
                                          new_dir_snapshot, \
                                          files_renamed):
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
                out_event_queue.put((self.path, FileCreatedEvent(path_renamed)))
                out_event_queue.put((self.path, FileDeletedEvent(path_renamed)))
                continue

            try:
                path = new_dir_snapshot.path_for_inode(ref_stat_info.st_ino)
                out_event_queue.put((self.path, FileMovedEvent(src_path=path_renamed, dest_path=path)))
                self.unregister_path(path_renamed)
                self.register_path(path, is_directory=False)
            except KeyError:
                # We could not find the new name.
                out_event_queue.put((self.path, FileDeletedEvent(src_path=path_renamed)))
                self.unregister_path(path_renamed)


    def __process_kevent_dir_renames(self, out_event_queue, \
                                         ref_dir_snapshot, \
                                         new_dir_snapshot, \
                                         dirs_renamed):
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
                out_event_queue.put((self.path, DirCreatedEvent(path_renamed)))
                out_event_queue.put((self.path, DirDeletedEvent(path_renamed)))
                continue
            try:
                path = new_dir_snapshot.path_for_inode(ref_stat_info.st_ino)
                path = absolute_path(path)

                # If we're in recursive mode, we fire move events for
                # the entire contents of the moved directory.
                if self.is_recursive:
                    dir_path_renamed = absolute_path(path_renamed)
                    for root, directories, filenames in os.walk(path):
                        for directory_path in directories:
                            full_path = os.path.join(root, directory_path)
                            renamed_path = full_path.replace(path, dir_path_renamed)
                            out_event_queue.put((self.path, DirMovedEvent(src_path=renamed_path, dest_path=full_path)))
                            self.unregister_path(renamed_path)
                            self.register_path(full_path, is_directory=True)
                        for filename in filenames:
                            full_path = os.path.join(root, filename)
                            renamed_path = full_path.replace(path, dir_path_renamed)
                            out_event_queue.put((self.path, FileMovedEvent(src_path=renamed_path, dest_path=full_path)))
                            self.unregister_path(renamed_path)
                            self.register_path(full_path, is_directory=False)

                # Fire the directory moved events after firing moved
                # events for its children file system objects.
                out_event_queue.put((self.path, DirMovedEvent(src_path=path_renamed, dest_path=path)))
                self.unregister_path(path_renamed)
                self.register_path(path, is_directory=True)
            except KeyError:
                # We could not find the new name.
                out_event_queue.put((self.path, DirDeletedEvent(src_path=path_renamed)))
                self.unregister_path(path)


    def __process_kevent_dir_modifications(self, out_event_queue, ref_dir_snapshot, new_dir_snapshot, dirs_modified):
        """Process kevent-hinted directory modifications. Created
        files/directories are also detected here."""
        for dir_modified in dirs_modified:
            out_event_queue.put((self.path, DirModifiedEvent(src_path=dir_modified)))
            # Don't need to register here. It's already registered.
            #self.register_path(dir_modified, is_directory=True)
        diff = new_dir_snapshot - ref_dir_snapshot
        for file_created in diff.files_created:
            out_event_queue.put((self.path, FileCreatedEvent(src_path=file_created)))
            self.register_path(file_created, is_directory=False)
        for dir_created in diff.dirs_created:
            out_event_queue.put((self.path, DirCreatedEvent(src_path=dir_created)))
            self.register_path(dir_created, is_directory=True)


    @synchronized()
    def process_events(self, out_event_queue):
        """Blocking call to kqueue.control that enlists events and then
    processes them classifying them into various events defined in watchdog.events."""
        event_list = self.kq.control(list(self.kevent_list), MAX_EVENTS)
        files_renamed, dirs_renamed, dirs_modified = \
            self.__process_kevents_except_movement(event_list,
                                                   out_event_queue)

        # Take a fresh snapshot of the directory and update saved snapshot.
        new_dir_snapshot = DirectorySnapshot(self.path, self.is_recursive)
        ref_dir_snapshot = self.dir_snapshot
        self.dir_snapshot = new_dir_snapshot

        # Process events for renames and directories modified.
        if files_renamed or dirs_renamed or dirs_modified:
            self.__process_kevent_file_renames(out_event_queue, ref_dir_snapshot, new_dir_snapshot, files_renamed)
            self.__process_kevent_dir_renames(out_event_queue, ref_dir_snapshot, new_dir_snapshot, dirs_renamed)

            if dirs_modified:
                self.__process_kevent_dir_modifications(out_event_queue, ref_dir_snapshot, new_dir_snapshot, dirs_modified)


    def run(self):
        self.register_dir_tree(self.path, self.is_recursive)
        while not self.is_stopped:
            try:
                #if not os.path.exists(self.path):
                #    self.stop()
                #    continue
                self.process_events(self.out_event_queue)
            except OSError, e:
                if e.errno == errno.EBADF:
                    # select.kqueue seems to be blowing up on the first
                    # call to kqueue.control with this error.
                    logging.debug(e)
                    continue
                else:
                    raise

        # Close all open file descriptors
        for fd in self.descriptor_list:
            try:
                os.close(fd)
            except OSError, e:
                logging.warn(e)
        self.kq.close()


class KqueueObserver(PollingObserver):
    """BSD/OS X kqueue-based observer implementation."""
    def _create_event_emitter(self, path, recursive):
        return _KqueueEventEmitter(path=path,
                                   interval=self.interval,
                                   out_event_queue=self.event_queue,
                                   recursive=recursive)

