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
import sys
import errno
try:
    # Python 3k
    from queue import Queue, Empty as QueueEmpty
except ImportError:
    from Queue import Queue, Empty as QueueEmpty
try:
    import select
except ImportError:
    import select26 as select

from os.path import join as path_join, realpath, abspath
from threading import Thread, Lock as ThreadedLock, Event as ThreadedEvent
from watchdog.utils import get_walker
from watchdog.decorator_utils import synchronized
from watchdog.observers.polling_observer import PollingObserver
from watchdog.events import DirMovedEvent, DirDeletedEvent, DirCreatedEvent, DirModifiedEvent, \
    FileMovedEvent, FileDeletedEvent, FileCreatedEvent, FileModifiedEvent

import logging
logging.basicConfig(level=logging.DEBUG)

# Maximum number of events to process.
MAX_EVENTS = 104896

# Flags pre-calculated that we will use for the kevent filter, flags, and
# fflags attributes.
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
    return kev.fflags & select.KQ_NOTE_DELETE

def is_modified(kev):
    fflags = kev.fflags
    return (fflags & select.KQ_NOTE_EXTEND) or (fflags & select.KQ_NOTE_WRITE)

def is_attrib_modified(kev):
    return kev.fflags & select.KQ_NOTE_ATTRIB

def is_renamed(kev):
    return kev.fflags & select.KQ_NOTE_RENAME



class _DescriptorObject(object):
    def __init__(self, fd, kev, path, is_directory):
        self.fd = fd
        self.path = path
        self.kev = kev
        self.is_directory = is_directory


class _KqueueEventEmitter(Thread):
    def __init__(self, path, out_event_queue, recursive, *args, **kwargs):
        Thread.__init__(self)
        self.stopped = ThreadedEvent()
        self.setDaemon(True)
        self.path = abspath(realpath(path))
        self.out_event_queue = out_event_queue
        self.is_recursive = recursive
        self.kq = select.kqueue()
        self.kevent_list = list()
        self.descriptor_table = dict()
        self.descriptor_list = set()


    def stop(self):
        self.stopped.set()
        # Close all open file descriptors
        for fd in self.descriptor_list:
            os.close(fd)


    @synchronized()
    def register_dir_path(self, path, recursive, callback=None):
        if callback is None:
            callback = (lambda w: w)
        path = abspath(realpath(path))
        walk = get_walker(recursive)
        self.register_path(path, is_directory=True, callback=callback)
        for root, directories, filenames in walk(path):
            for directory in directories:
                full_path = path_join(root, directory)
                self.register_path(full_path, is_directory=True, callback=callback)
            for filename in filenames:
                full_path = path_join(root, filename)
                self.register_path(full_path, is_directory=False, callback=callback)


    @synchronized()
    def unregister_path(self, path):
        if path in self.descriptor_table:
            descriptor_object = self.descriptor_table[path]
            self.kevent_list.remove(descriptor_object.kev)
            del self.descriptor_table[path]
            del self.descriptor_table[descriptor_object.fd]
            try:
                os.close(fd)
            except OSError, e:
                logging.debug(e)
            self.descriptor_list.remove(descriptor_object.fd)


    @synchronized()
    def register_path(self, path, is_directory=False, callback=None):
        """Call from within a synchronized method."""
        if callback is None:
            callback = (lambda w: w)
        if not path in self.descriptor_table:
            # If we haven't registered a kevent for this path already,
            # add a new kevent for the path.
            kev, fd = create_kevent_for_path(path)
            self.kevent_list.append(kev)
            descriptor_object = _DescriptorObject(fd, kev, path, is_directory)
            self.descriptor_list.add(fd)
            self.descriptor_table[fd] = descriptor_object
            self.descriptor_table[path] = descriptor_object
            callback(path)


    @synchronized()
    def process_kqueue(self):
        event_list = self.kq.control(list(self.kevent_list), MAX_EVENTS)
        for kev in event_list:
            descriptor_object = self.descriptor_table[kev.ident]
            src_path = descriptor_object.path

            walk = get_walker(self.is_recursive)

            if is_modified(kev):
                if descriptor_object.is_directory:
                    if src_path == self.path:
                        # Top-level directory
                        for root, directories, filenames in walk(src_path):
                            for directory in directories:
                                full_path = path_join(root, directory)
                                if not full_path in self.descriptor_table:
                                    # new directory created
                                    print('created directory %s' % full_path)
                                    # register directory path
                                    if self.is_recursive:
                                        self.register_dir_path(full_path, recursive=True)
                                    else:
                                        self.register_path(full_path, is_directory=False)
                            for filename in filenames:
                                full_path = path_join(root, filename)
                                if not full_path in self.descriptor_table:
                                    # new file created
                                    print('created file %s' % full_path)
                                    # register path
                                    self.register_path(full_path, is_directory=False)
                    else:
                        pass
                # if a directory is modified
                #    and the directory is the top level directory
                #    scan it and determine what was added.
                # if a directory is modified
                #    and the directory is not the top level directory
                #    scan it only if we're recursive.

                print('modified %s' % src_path)
            elif is_attrib_modified(kev):
                print('attrib modified %s' % src_path)
            elif is_deleted(kev):
                print('deleted %s' % src_path)
            elif is_renamed(kev):
                print('renamed %s' % src_path)

            #if self.is_recursive and descriptor_object.is_directory:
            #    self.register_dir_path(src_path, recursive=True)
            #else:
            #    self.register_path(src_path, is_directory=descriptor_object.is_directory)


    def run(self):
        self.register_dir_path(self.path, self.is_recursive)
        while not self.stopped.is_set():
            try:
                self.process_kqueue()
            except OSError, e:
                if e.errno == errno.EBADF:
                    # select.kqueue seems to be blowing up on the first
                    # call to kqueue.control with this error.
                    logging.debug(e)
                    continue
                else:
                    raise


class KqueueObserver(PollingObserver):
    def _create_event_emitter(self, path, recursive):
        return _KqueueEventEmitter(path=path,
                                   interval=self.interval,
                                   out_event_queue=self.event_queue,
                                   recursive=recursive)

