#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc.
# Copyright 2014 Thomas Amland <thomas.amland@gmail.com>
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
:module: watchdog.utils.dirsnapshot
:synopsis: Directory snapshots and comparison.
:author: yesudeep@google.com (Yesudeep Mangalapilly)

.. ADMONITION:: Where are the moved events? They "disappeared"

        This implementation does not take partition boundaries
        into consideration. It will only work when the directory
        tree is entirely on the same file system. More specifically,
        any part of the code that depends on inode numbers can
        break if partition boundaries are crossed. In these cases,
        the snapshot diff will represent file/directory movement as
        created and deleted events.

Classes
-------
.. autoclass:: DirectorySnapshot
   :members:
   :show-inheritance:

.. autoclass:: DirectorySnapshotDiff
   :members:
   :show-inheritance:

"""

import os
import stat as is_stat
from watchdog.utils import platform
from watchdog.utils import stat as default_stat


class DirectorySnapshotDiff(object):
    """
    Compares two directory snapshots and creates an object that represents
    the difference between the two snapshots.

    :param ref:
        The reference directory snapshot.
    :type ref:
        :class:`DirectorySnapshot`
    :param snapshot:
        The directory snapshot which will be compared
        with the reference snapshot.
    :type snapshot:
        :class:`DirectorySnapshot`
    """
    def __init__(self, new, old):
        self.init(new, old)
    
    def init(self, old, new):
        new_inodes = new.get_inodes()
        old_inodes = old.get_inodes()
        created = set([new.path(inode) for inode in new_inodes - old_inodes])
        deleted = set([old.path(inode) for inode in old_inodes - new_inodes])
        modified = set([old.path(inode) for inode in new_inodes.intersection(old_inodes) if new.mtime(inode) != old.mtime(inode)])
        moved = set([(old.path(inode), new.path(inode)) for inode in new_inodes.intersection(old_inodes) if new.path(inode) != old.path(inode)])

        self._dirs_created = [path for path in created if new.isdir(path)]
        self._dirs_deleted = [path for path in deleted if old.isdir(path)]
        self._dirs_modified = [path for path in modified if old.isdir(path)]
        self._dirs_moved = [(frm, to) for (frm, to) in moved if old.isdir(frm)]
        
        self._files_created = list(created - set(self._dirs_created))
        self._files_deleted = list(deleted - set(self._dirs_deleted))
        self._files_modified = list(modified - set(self._dirs_modified))
        self._files_moved = list(moved - set(self._dirs_moved))

                
    @property
    def files_created(self):
        """List of files that were created."""
        return self._files_created

    @property
    def files_deleted(self):
        """List of files that were deleted."""
        return self._files_deleted

    @property
    def files_modified(self):
        """List of files that were modified."""
        return self._files_modified

    @property
    def files_moved(self):
        """
        List of files that were moved.

        Each event is a two-tuple the first item of which is the path
        that has been renamed to the second item in the tuple.
        """
        return self._files_moved

    @property
    def dirs_modified(self):
        """
        List of directories that were modified.
        """
        return self._dirs_modified

    @property
    def dirs_moved(self):
        """
        List of directories that were moved.

        Each event is a two-tuple the first item of which is the path
        that has been renamed to the second item in the tuple.
        """
        return self._dirs_moved

    @property
    def dirs_deleted(self):
        """
        List of directories that were deleted.
        """
        return self._dirs_deleted

    @property
    def dirs_created(self):
        """
        List of directories that were created.
        """
        return self._dirs_created

class DirectorySnapshot(object):
    """
    A snapshot of stat information of files in a directory.

    :param path:
        The directory path for which a snapshot should be taken.
    :type path:
        ``str``
    :param recursive:
        ``True`` if the entired directory tree should be included in the
        snapshot; ``False`` otherwise.
    :type recursive:
        ``bool``
    :param walker_callback:
        .. deprecated:: 0.7.2
    :param stat:
        Use custom stat function that returns a stat structure for path.
        Currently only st_dev, st_ino, st_mode and st_mtime are needed.
        
        A function with the signature ``walker_callback(path, stat_info)``
        which will be called for every entry in the directory tree.
    :param listdir:
        Use custom listdir function. See ``os.listdir`` for details.
    """
    
    def __init__(self, path, recursive=True,
                 walker_callback=(lambda p, s: None),
                 stat=os.stat,
                 dev_id=None,
                 follow_symlinks=True,
                 listdir=os.listdir):
        self._init_kw = {}
        self._path = path
        self._init_kw["_recursive"] = recursive
        self._init_kw["_walker_callback"] = walker_callback
        self._init_kw["_stat"] = stat
        self._init_kw["_follow_symlinks"] = follow_symlinks
        self._init_kw["_dev_id"] = dev_id
        self._init_kw["_listdir"] = listdir
        self.__dict__.update(self._init_kw)
        self._stat_info = {}
        self._inode_to_path = {}
        self.scan()

    def copy(self):
        return self.__class__(self._path, **self._init_kw)
        
    def track_file(self, path, st=None):
        if not st:
            st = self._stat(path)
        self._inode_to_path[st.st_ino] = path
        self._stat_info[path] = st

    def get_inodes(self):
        return set(self._inode_to_path.keys())

    def scan(self):
        self.track_file(self._path)
        for p, st in self._walk(self._path):
            self.track_file(p, st)
            self._walker_callback(p, st)

    def _walk(self, root=None):
        if root == None:
            root = self._path
        try:
            paths = [os.path.join(root, name) for name in self._listdir(root)]
        except OSError:
            paths = []
        entries = []
        for p in paths:
            try:
                entries.append((p, self._stat(p)))
            except OSError:
                continue
        for path, st in entries:
            is_dir = is_stat.S_ISDIR(st.st_mode)
            lst = os.lstat(path)
            is_symlink = is_stat.S_ISLNK(lst.st_mode)
            is_same_dev = (st.st_dev == self._dev_id)
            if (is_dir and self._recursive) and \
                (not is_symlink or self._follow_symlinks) and \
                (not self._dev_id or is_same_dev):
                    for info in self._walk(path):
                        yield info
            yield (path, st)

    @property
    def paths(self):
        """
        Set of file/directory paths in the snapshot.
        """
        return set(self._stat_info.keys())
    
    def path(self, inode):
        """
        Returns path for inode. None if inode is unknown to this snapshot.
        """
        return self._inode_to_path.get(inode)
    
    def inode(self, path):
        """ Returns an id for path. """
        st = self._stat_info[path]
        return st.st_ino
    
    def dev_id(self, path):
        """ Returns an devid for path. """
        st = self._stat_info[path]
        return st.st_dev

    def isdir(self, path):
        return is_stat.S_ISDIR(self._stat_info[path].st_mode)
    
    def mtime(self, path_or_inode):
        if type(path_or_inode) == int:
            path_or_inode = self.path(path_or_inode)
        return self._stat_info[path_or_inode].st_mtime
    
    def stat_info(self, path):
        """
        Returns a stat information object for the specified path from
        the snapshot.

        Attached information is subject to change. Do not use unless
        you specify `stat` in constructor. Use :func:`inode`, :func:`mtime`,
        :func:`isdir` instead.

        :param path:
            The path for which stat information should be obtained
            from a snapshot.
        """
        return self._stat_info.get(path)

    def __sub__(self, previous_dirsnap):
        """Allow subtracting a DirectorySnapshot object instance from
        another.

        :returns:
            A :class:`DirectorySnapshotDiff` object.
        """
        return DirectorySnapshotDiff(previous_dirsnap, self)
    
    def __str__(self):
        return self.__repr__()
    
    def __repr__(self):
        return str(self._stat_info)
    
    def __contains__(self, path):
        return path in self._stat_info
    
    ### deprecated methods ###
    
    @property
    def stat_snapshot(self):
        """
        .. deprecated:: 0.7.2
           Use :func:`stat_info` or :func:`inode`/:func:`mtime`/:func:`isdir`

        Returns a dictionary of stat information with file paths being keys.
        """
        return self._stat_info

    def path_for_inode(self, inode):
        """
        .. deprecated:: 0.7.2
           Use :func:`path` instead.
        
        Determines the path that an inode represents in a snapshot.

        :param inode:
            inode number.
        """
        return self._inode_to_path[inode]

    def has_inode(self, inode):
        """
        .. deprecated:: 0.7.2
           Use :func:`inode` instead.
        
        Determines if the inode exists.

        :param inode:
            inode number.
        """
        return inode in self._inode_to_path

    def stat_info_for_inode(self, inode):
        """
        .. deprecated:: 0.7.2
        
        Determines stat information for a given inode.

        :param inode:
            inode number.
        """
        return self.stat_info(self.path_for_inode(inode))
