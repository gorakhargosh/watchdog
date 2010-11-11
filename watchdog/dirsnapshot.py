# -*- coding: utf-8 -*-

"""
Directory snapshotting classes and functionality.

Notes:
- Does not currently take into consideration stat information beyond
  partition boundaries.

"""

from os import walk, stat as os_stat
from os.path import join as path_join, realpath, abspath
from stat import S_ISDIR

class DirectorySnapshotDiff(object):
    """Difference between two directory snapshots."""
    def __init__(self, ref_dirsnap, dirsnap):
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
                    if S_ISDIR(stat_info.st_mode):
                        self._dirs_modified.add(path)
                    else:
                        self._files_modified.add(path)

        paths_deleted = ref_dirsnap.paths_set - dirsnap.paths_set
        paths_created = dirsnap.paths_set - ref_dirsnap.paths_set

        # Detect all the moves/renames.
        for created_path in paths_created.copy():
            created_stat_info = dirsnap.stat_info(created_path)
            for deleted_path in paths_deleted.copy():
                deleted_stat_info = ref_dirsnap.stat_info(deleted_path)
                if created_stat_info.st_ino == deleted_stat_info.st_ino:
                    paths_deleted.remove(deleted_path)
                    paths_created.remove(created_path)
                    if S_ISDIR(created_stat_info.st_mode):
                        self._dirs_moved[deleted_path] = created_path
                    else:
                        self._files_moved[deleted_path] = created_path

        # Now that we have renames out of the way, enlist the deleted and
        # created files/directories.
        for path in paths_deleted:
            stat_info = ref_dirsnap.stat_info(path)
            if S_ISDIR(stat_info.st_mode):
                self._dirs_deleted.add(path)
            else:
                self._files_modified.add(path)

        for path in paths_created:
            stat_info = dirsnap.stat_info(path)
            if S_ISDIR(stat_info.st_mode):
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
    def __init__(self, path):
        self._path = abspath(realpath(path))
        self._dirs_stat_snapshot = {}
        self._stat_snapshot = {}
        for root, directories, files in walk(self._path):
            for file_name in files:
                try:
                    file_path = path_join(root, file_name)
                    self._stat_snapshot[file_path] = os_stat(file_path)
                except OSError:
                    continue

            for directory_name in directories:
                try:
                    directory_path = path_join(root, directory_name)
                    self._stat_snapshot[directory_path] = os_stat(directory_path)
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

    def stat_info(self, path, default=None):
        """Returns a stat information object for the specified path from
        the snapshot."""
        return self._stat_snapshot.get(path, default)

    @property
    def paths_set(self):
        """Set of files in the snapshot."""
        return set(self._stat_snapshot)


    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return str(self._stat_snapshot)

