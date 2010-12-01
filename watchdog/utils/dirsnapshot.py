# -*- coding: utf-8 -*-
# dirsnapshot.py: Directory snapshotter.
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

"""
Directory snapshotting classes and functionality.

Notes:
- Does not currently take into consideration stat information beyond
  partition boundaries.

"""

import os
import os.path
import sys
import stat

from watchdog.utils import get_walker, real_absolute_path

class DirectorySnapshotDiff(object):
    """Difference between two directory snapshots."""
    def __init__(self, ref_dirsnap, dirsnap):
        """
        Compares two directory snapshots and creates an object that represents
        the difference between the two snapshots.

        Arguments:
        - ref_dirsnap: The reference directory snapshot object instance.
        - dirsnap:  The directory snapshot object instance which will be compared
                    with the reference.
        """
        self._files_deleted = set()
        self._files_modified = set()
        self._files_created = set()
        self._files_moved = dict()

        self._dirs_modified = set()
        self._dirs_moved = dict()
        self._dirs_deleted = set()
        self._dirs_created = set()

        # Detect all the modifications.
        for path, stat_info in dirsnap.stat_snapshot.items():
            if path in ref_dirsnap.stat_snapshot:
                ref_stat_info = ref_dirsnap.stat_info(path)
                if stat_info.st_ino == ref_stat_info.st_ino and stat_info.st_mtime != ref_stat_info.st_mtime:
                    if stat.S_ISDIR(stat_info.st_mode):
                        self._dirs_modified.add(path)
                    else:
                        self._files_modified.add(path)

        paths_deleted = ref_dirsnap.paths_set - dirsnap.paths_set
        paths_created = dirsnap.paths_set - ref_dirsnap.paths_set

        # Detect all the moves/renames.
        # Doesn't work on Windows, so exlude on Windows.
        if not sys.platform.startswith('win'):
            for created_path in paths_created.copy():
                created_stat_info = dirsnap.stat_info(created_path)
                for deleted_path in paths_deleted.copy():
                    deleted_stat_info = ref_dirsnap.stat_info(deleted_path)
                    if created_stat_info.st_ino == deleted_stat_info.st_ino:
                        paths_deleted.remove(deleted_path)
                        paths_created.remove(created_path)
                        if stat.S_ISDIR(created_stat_info.st_mode):
                            self._dirs_moved[deleted_path] = created_path
                        else:
                            self._files_moved[deleted_path] = created_path

        # Now that we have renames out of the way, enlist the deleted and
        # created files/directories.
        for path in paths_deleted:
            stat_info = ref_dirsnap.stat_info(path)
            if stat.S_ISDIR(stat_info.st_mode):
                self._dirs_deleted.add(path)
            else:
                self._files_deleted.add(path)

        for path in paths_created:
            stat_info = dirsnap.stat_info(path)
            if stat.S_ISDIR(stat_info.st_mode):
                self._dirs_created.add(path)
            else:
                self._files_created.add(path)


    @property
    def files_created(self):
        """Set of files that were created."""
        return self._files_created

    @property
    def files_deleted(self):
        """Set of files that were deleted."""
        return self._files_deleted

    @property
    def files_modified(self):
        """Set of files that were modified."""
        return self._files_modified

    @property
    def files_moved(self):
        """Dictionary of files that were moved.

        Each key of the dictionary returned is the original file path
        while each value stores the new file path.
        """
        return self._files_moved

    @property
    def dirs_modified(self):
        return self._dirs_modified

    @property
    def dirs_moved(self):
        return self._dirs_moved

    @property
    def dirs_deleted(self):
        return self._dirs_deleted

    @property
    def dirs_created(self):
        return self._dirs_created


class DirectorySnapshot(object):
    """A snapshot of stat information of files in a directory."""
    def __init__(self, path, recursive=True, walker_callback=(lambda p, s: None)):
        self._path = real_absolute_path(path)
        self._stat_snapshot = {}
        self._inode_to_path = {}
        self.is_recursive = recursive

        walk = get_walker(recursive)

        stat_info = os.stat(self._path)
        self._stat_snapshot[self._path] = stat_info
        self._inode_to_path[stat_info.st_ino] = self._path
        walker_callback(self._path, stat_info)

        for root, directories, files in walk(self._path):
            for file_name in files:
                try:
                    file_path = os.path.join(root, file_name)
                    stat_info = os.stat(file_path)
                    self._stat_snapshot[file_path] = stat_info
                    self._inode_to_path[stat_info.st_ino] = file_path
                    walker_callback(file_path, stat_info)
                except OSError:
                    continue

            for directory_name in directories:
                try:
                    directory_path = os.path.join(root, directory_name)
                    stat_info = os.stat(directory_path)
                    self._stat_snapshot[directory_path] = stat_info
                    self._inode_to_path[stat_info.st_ino] = directory_path
                    walker_callback(directory_path, stat_info)
                except OSError:
                    continue


    def __sub__(self, previous_dirsnap):
        """Allow subtracting a DirectorySnapshot object instance from
        another.

        Returns a DirectorySnapshotDiff object instance.
        """
        return DirectorySnapshotDiff(previous_dirsnap, self)


    @property
    def stat_snapshot(self):
        """Returns a dictionary of stat information with file paths being keys."""
        return self._stat_snapshot


    def stat_info(self, path):
        """Returns a stat information object for the specified path from
        the snapshot."""
        return self._stat_snapshot[path]


    def path_for_inode(self, inode):
        return self._inode_to_path[inode]


    def stat_info_for_inode(self, inode):
        return self.stat_info(self.path_for_inode(inode))


    @property
    def paths_set(self):
        """Set of files in the snapshot."""
        return set(self._stat_snapshot)


    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return str(self._stat_snapshot)

