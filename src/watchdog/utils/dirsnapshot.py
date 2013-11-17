#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc.
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

        Windows does not have any concept of ``inodes``, which prevents
        this snapshotter from determining file or directory renames/movement
        on it. The snapshotter does not try to handle this on Windows.
        File or directory movement will show up as creation and deletion
        events.

        Please do not use this on a virtual file system mapped to
        a network share.

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
import sys
import stat

from pathtools.path import walk as path_walk, absolute_path

if sys.version_info >= (2, 6, 0):
    from watchdog.utils.bricks import OrderedSet as set


class DirectorySnapshotDiff(object):

    """
    Compares two directory snapshots and creates an object that represents
    the difference between the two snapshots.

    :param ref_dirsnap:
        The reference directory snapshot.
    :type ref_dirsnap:
        :class:`DirectorySnapshot`
    :param dirsnap:
        The directory snapshot which will be compared
        with the reference snapshot.
    :type dirsnap:
        :class:`DirectorySnapshot`
    """

    def __init__(self, ref_dirsnap, dirsnap):
        """
        """
        self._files_deleted = list()
        self._files_modified = list()
        self._files_created = list()
        self._files_moved = list()

        self._dirs_modified = list()
        self._dirs_moved = list()
        self._dirs_deleted = list()
        self._dirs_created = list()

        paths_moved_from_not_deleted = []
        paths_deleted = set()
        paths_created = set()

        # Detect modifications and distinguish modifications that are actually
        # renames of files on top of existing file names (OS X/Linux only)
        for path, stat_info in list(dirsnap.stat_snapshot.items()):
            if path in ref_dirsnap.stat_snapshot:
                ref_stat_info = ref_dirsnap.stat_info(path)
                if stat_info.st_ino == ref_stat_info.st_ino and stat_info.st_mtime != ref_stat_info.st_mtime:
                    if stat.S_ISDIR(stat_info.st_mode):
                        self._dirs_modified.append(path)
                    else:
                        self._files_modified.append(path)
                elif stat_info.st_ino != ref_stat_info.st_ino:
                    # Same path exists... but different inode
                    if ref_dirsnap.has_inode(stat_info.st_ino):
                        old_path = ref_dirsnap.path_for_inode(stat_info.st_ino)
                        paths_moved_from_not_deleted.append(old_path)
                        if stat.S_ISDIR(stat_info.st_mode):
                            self._dirs_moved.append((old_path, path))
                        else:
                            self._files_moved.append((old_path, path))
                    else:
                        # we have a newly created item with existing name, but different inode
                        paths_deleted.add(path)
                        paths_created.add(path)

        paths_deleted = paths_deleted | (
            (ref_dirsnap.paths - dirsnap.paths) - set(paths_moved_from_not_deleted))
        paths_created = paths_created | (dirsnap.paths - ref_dirsnap.paths)

        # Detect all the moves/renames except for atomic renames on top of existing files
        # that are handled in the file modification check for-loop above
        # Doesn't work on Windows since st_ino is always 0, so exclude on Windows.
        if not sys.platform.startswith('win'):
            for created_path in paths_created:
                created_stat_info = dirsnap.stat_info(created_path)
                for deleted_path in paths_deleted:
                    deleted_stat_info = ref_dirsnap.stat_info(deleted_path)
                    if created_stat_info.st_ino == deleted_stat_info.st_ino:
                        paths_deleted.remove(deleted_path)
                        paths_created.remove(created_path)
                        if stat.S_ISDIR(created_stat_info.st_mode):
                            self._dirs_moved.append((deleted_path, created_path))
                        else:
                            self._files_moved.append((deleted_path, created_path))

        # Now that we have renames out of the way, enlist the deleted and
        # created files/directories.
        for path in paths_deleted:
            stat_info = ref_dirsnap.stat_info(path)
            if stat.S_ISDIR(stat_info.st_mode):
                self._dirs_deleted.append(path)
            else:
                self._files_deleted.append(path)

        for path in paths_created:
            stat_info = dirsnap.stat_info(path)
            if stat.S_ISDIR(stat_info.st_mode):
                self._dirs_created.append(path)
            else:
                self._files_created.append(path)

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
        A function with the signature ``walker_callback(path, stat_info)``
        which will be called for every entry in the directory tree.
    """

    def __init__(self,
                 path,
                 recursive=True,
                 walker_callback=(lambda p, s: None),
                 _copying=False):
        self._path = absolute_path(path)
        self._stat_snapshot = {}
        self._inode_to_path = {}
        self.is_recursive = recursive

        if not _copying:
            stat_info = os.stat(self._path)
            self._stat_snapshot[self._path] = stat_info
            self._inode_to_path[stat_info.st_ino] = self._path
            walker_callback(self._path, stat_info)

            for root, directories, files in path_walk(self._path, recursive):
                for directory_name in directories:
                    try:
                        directory_path = os.path.join(root, directory_name)
                        stat_info = os.stat(directory_path)
                        self._stat_snapshot[directory_path] = stat_info
                        self._inode_to_path[stat_info.st_ino] = directory_path
                        walker_callback(directory_path, stat_info)
                    except OSError:
                        continue

                for file_name in files:
                    try:
                        file_path = os.path.join(root, file_name)
                        stat_info = os.stat(file_path)
                        self._stat_snapshot[file_path] = stat_info
                        self._inode_to_path[stat_info.st_ino] = file_path
                        walker_callback(file_path, stat_info)
                    except OSError:
                        continue

    def __sub__(self, previous_dirsnap):
        """Allow subtracting a DirectorySnapshot object instance from
        another.

        :returns:
            A :class:`DirectorySnapshotDiff` object.
        """
        return DirectorySnapshotDiff(previous_dirsnap, self)

    # def __add__(self, new_dirsnap):
    #    self._stat_snapshot.update(new_dirsnap._stat_snapshot)

    def copy(self, from_pathname=None):
        snapshot = DirectorySnapshot(path=from_pathname,
                                     recursive=self.is_recursive,
                                     _copying=True)
        for pathname, stat_info in list(self._stat_snapshot.items()):
            if pathname.starts_with(from_pathname):
                snapshot._stat_snapshot[pathname] = stat_info
                snapshot._inode_to_path[stat_info.st_ino] = pathname
        return snapshot

    @property
    def stat_snapshot(self):
        """
        Returns a dictionary of stat information with file paths being keys.
        """
        return self._stat_snapshot

    def stat_info(self, path):
        """
        Returns a stat information object for the specified path from
        the snapshot.

        :param path:
            The path for which stat information should be obtained
            from a snapshot.
        """
        return self._stat_snapshot[path]

    def path_for_inode(self, inode):
        """
        Determines the path that an inode represents in a snapshot.

        :param inode:
            inode number.
        """
        return self._inode_to_path[inode]

    def has_inode(self, inode):
        """
        Determines if the inode exists.

        :param inode:
            inode number.
        """
        return inode in self._inode_to_path

    def stat_info_for_inode(self, inode):
        """
        Determines stat information for a given inode.

        :param inode:
            inode number.
        """
        return self.stat_info(self.path_for_inode(inode))

    @property
    def paths(self):
        """
        List of file/directory paths in the snapshot.
        """
        return set(self._stat_snapshot)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return str(self._stat_snapshot)
