# coding: utf-8
#
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

import errno
import os
import pickle
import time

from watchdog.utils.dirsnapshot import DirectorySnapshot
from watchdog.utils.dirsnapshot import DirectorySnapshotDiff
from watchdog.utils.dirsnapshot import EmptyDirectorySnapshot
from watchdog.utils import platform

from .shell import mkdir, touch, mv, rm


def wait():
    """
    Wait long enough for file/folder mtime to change. This is needed
    to be able to detected modifications.
    """
    if platform.is_darwin() or platform.is_windows():
        # on macOS resolution of stat.mtime is only 1 second
        time.sleep(1.5)
    else:
        time.sleep(0.5)


def test_pickle(p):
    """It should be possible to pickle a snapshot."""
    mkdir(p('dir1'))
    snasphot = DirectorySnapshot(p('dir1'))
    pickle.dumps(snasphot)


def test_move_to(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    ref = DirectorySnapshot(p('dir2'))
    mv(p('dir1', 'a'), p('dir2', 'b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('dir2')))
    assert diff.files_created == [p('dir2', 'b')]


def test_move_from(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    ref = DirectorySnapshot(p('dir1'))
    mv(p('dir1', 'a'), p('dir2', 'b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('dir1')))
    assert diff.files_deleted == [p('dir1', 'a')]


def test_move_internal(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    ref = DirectorySnapshot(p(''))
    mv(p('dir1', 'a'), p('dir2', 'b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert diff.files_moved == [(p('dir1', 'a'), p('dir2', 'b'))]
    assert diff.files_created == []
    assert diff.files_deleted == []


def test_move_replace(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    touch(p('dir2', 'b'))
    ref = DirectorySnapshot(p(''))
    mv(p('dir1', 'a'), p('dir2', 'b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert diff.files_moved == [(p('dir1', 'a'), p('dir2', 'b'))]
    assert diff.files_deleted == [p('dir2', 'b')]
    assert diff.files_created == []


def test_dir_modify_on_create(p):
    ref = DirectorySnapshot(p(''))
    wait()
    touch(p('a'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert diff.dirs_modified == [p('')]


def test_dir_modify_on_move(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    ref = DirectorySnapshot(p(''))
    wait()
    mv(p('dir1', 'a'), p('dir2', 'b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert set(diff.dirs_modified) == set([p('dir1'), p('dir2')])


def test_detect_modify_for_moved_files(p):
    touch(p('a'))
    ref = DirectorySnapshot(p(''))
    wait()
    touch(p('a'))
    mv(p('a'), p('b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert diff.files_moved == [(p('a'), p('b'))]
    assert diff.files_modified == [p('a')]


def test_replace_dir_with_file(p):
    # Replace a dir with a file of the same name just before the normal listdir
    # call and ensure it doesn't cause an exception

    def listdir_fcn(path):
        if path == p("root", "dir"):
            rm(path, recursive=True)
            touch(path)
        return os.listdir(path)

    mkdir(p('root'))
    mkdir(p('root', 'dir'))

    # Should NOT raise an OSError (ENOTDIR)
    DirectorySnapshot(p('root'), listdir=listdir_fcn)


def test_permission_error(monkeypatch, p):
    # Test that unreadable folders are not raising exceptions
    mkdir(p('a', 'b', 'c'), parents=True)

    ref = DirectorySnapshot(p(''))

    def walk(self, root):
        """Generate a permission error on folder "a/b"."""
        # Generate the permission error
        if root.startswith(p('a', 'b')):
            raise OSError(errno.EACCES, os.strerror(errno.EACCES))

        # Mimic the original method
        for entry in walk_orig(self, root):
            yield entry

    walk_orig = DirectorySnapshot.walk
    monkeypatch.setattr(DirectorySnapshot, "walk", walk)

    # Should NOT raise an OSError (EACCES)
    new_snapshot = DirectorySnapshot(p(''))

    monkeypatch.undo()

    diff = DirectorySnapshotDiff(ref, new_snapshot)
    assert repr(diff)

    # Children of a/b/ are no more accessible and so removed in the new snapshot
    assert diff.dirs_deleted == [(p('a', 'b', 'c'))]


def test_ignore_device(monkeypatch, p):
    # Create a file and take a snapshot.
    touch(p('file'))
    ref = DirectorySnapshot(p(''))
    wait()

    def inode(self, path):
        # This function will always return a different device_id,
        # even for the same file.
        result = inode_orig(self, path)
        inode.times += 1
        return result[0], result[1] + inode.times
    inode.times = 0

    # Set the custom inode function.
    inode_orig = DirectorySnapshot.inode
    monkeypatch.setattr(DirectorySnapshot, 'inode', inode)

    # If we make the diff of the same directory, since by default the
    # DirectorySnapshotDiff compares the snapshots using the device_id (and it will
    # be different), it thinks that the same file has been deleted and created again.
    snapshot = DirectorySnapshot(p(''))
    diff_with_device = DirectorySnapshotDiff(ref, snapshot)
    assert diff_with_device.files_deleted == [(p('file'))]
    assert diff_with_device.files_created == [(p('file'))]

    # Otherwise, if we choose to ignore the device, the file will not be detected as
    # deleted and re-created.
    snapshot = DirectorySnapshot(p(''))
    diff_without_device = DirectorySnapshotDiff(ref, snapshot, ignore_device=True)
    assert diff_without_device.files_deleted == []
    assert diff_without_device.files_created == []


def test_empty_snapshot(p):
    # Create a file and declare a DirectorySnapshot and a EmptyDirectorySnapshot.
    # When we make the diff, although both objects were declared with the same items on
    # the directory, the file and directories created BEFORE the DirectorySnapshot will
    # be detected as newly created.

    touch(p('a'))
    mkdir(p('b', 'c'), parents=True)
    ref = DirectorySnapshot(p(''))
    empty = EmptyDirectorySnapshot()

    diff = DirectorySnapshotDiff(empty, ref)
    assert diff.files_created == [p('a')]
    assert sorted(diff.dirs_created) == sorted([p(''), p('b'), p('b', 'c')])
