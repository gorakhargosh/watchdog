# -*- coding: utf-8 -*-

from os import walk, stat
from os.path import join as path_join, realpath, abspath

class DirectorySnapshotDiff(object):
    """Difference between two directory snapshots."""
    def __init__(self, ref_dirsnap, dirsnap):
        self._files_deleted = set()
        self._files_modified = set()
        self._files_created = set()
        self._files_moved = dict()

        for file_path, stat_info in dirsnap.stat_snapshot.items():
            if file_path in ref_dirsnap.stat_snapshot:
                ref_stat_info = ref_dirsnap.stat_info(file_path)
                if stat_info.st_mtime != ref_stat_info.st_mtime:
                    self._files_modified.add(file_path)

        self._files_deleted = ref_dirsnap.files_set - dirsnap.files_set
        self._files_created = dirsnap.files_set - ref_dirsnap.files_set

        files_deleted = self._files_deleted.copy()
        files_created = self._files_created.copy()

        for created_file_path in files_created:
            for deleted_file_path in files_deleted:
                deleted_stat_info = ref_dirsnap.stat_info(deleted_file_path)
                created_stat_info = dirsnap.stat_info(created_file_path)
                if created_stat_info.st_ino == deleted_stat_info.st_ino:
                    self._files_deleted.remove(deleted_file_path)
                    self._files_created.remove(created_file_path)
                    self._files_moved[deleted_file_path] = created_file_path

    @property
    def files_created(self):
        return self._files_created

    @property
    def files_deleted(self):
        return self._files_deleted

    @property
    def files_modified(self):
        return self._files_modified

    @property
    def files_moved(self):
        return self._files_moved


class DirectorySnapshot(object):
    """A snapshot of stat information of files in a directory."""
    def __init__(self, path):
        self._path = abspath(realpath(path))
        self._dirs_set = set()
        self._stat_snapshot = {}
        for root, directories, files in walk(self._path):
            for file_name in files:
                try:
                    file_path = path_join(root, file_name)
                    self._stat_snapshot[file_path] = stat(file_path)
                except OSError:
                    continue

            for directory_name in directories:
                directory_path = path_join(root, directory_name)
                self._dirs_set.add(directory_path)

    def __sub__(self, previous_dirsnap):
        return DirectorySnapshotDiff(previous_dirsnap, self)

    @property
    def stat_snapshot(self):
        return self._stat_snapshot

    def stat_info(self, file_path, default=None):
        return self._stat_snapshot.get(file_path, default)

    @property
    def files_set(self):
        return set(self._stat_snapshot)

    @property
    def directories_set(self):
        return self._dirs_set


    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return str(self._stat_snapshot)

