# -*- coding: utf-8 -*-
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

import time
from tests import tmpdir, p  # pytest magic
from .shell import mkdir, touch, mv
from watchdog.utils.dirsnapshot import DirectorySnapshot
from watchdog.utils.dirsnapshot import DirectorySnapshotDiff
from watchdog.utils import platform


def wait():
    """
    Wait long enough for file/folder mtime to change. This is needed
    to be able to detected modifications.
    """
    if platform.is_darwin() or platform.is_windows():
         # on osx resolution of stat.mtime is only 1 second
        time.sleep(1.5)
    else:
        time.sleep(0.5)


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
