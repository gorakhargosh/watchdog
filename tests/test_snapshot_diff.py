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

import os
import time
import pytest
from functools import partial
from .shell import mkdtemp, mkdir, touch, mv
from watchdog.utils.dirsnapshot import DirectorySnapshot
from watchdog.utils.dirsnapshot import DirectorySnapshotDiff
from watchdog.utils import platform

skip_on_windows = pytest.mark.skipif(platform.is_windows(),
                        reason="Can't detect moves on windows file systems")

windows_only = pytest.mark.skipif(not platform.is_windows(),
                                 reason="Should detect moves instead")


def wait():
    time.sleep(0.5)

@pytest.fixture()
def tmpdir():
    return mkdtemp()


@pytest.fixture()
def p(tmpdir, *args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return partial(os.path.join, tmpdir)


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


@windows_only
def test_move_on_windows(p):
    touch(p('a'))
    ref = DirectorySnapshot(p(''))
    mv(p('a'), p('b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert diff.files_created == [p('b')]
    assert diff.files_deleted == [p('a')]


@skip_on_windows
def test_move_internal(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    ref = DirectorySnapshot(p(''))
    mv(p('dir1/a'), p('dir2/b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert diff.files_moved == [(p('dir1/a'), p('dir2/b'))]
    assert diff.files_created == []
    assert diff.files_deleted == []


@skip_on_windows
def test_move_replace(p):
    mkdir(p('dir1'))
    mkdir(p('dir2'))
    touch(p('dir1', 'a'))
    touch(p('dir2', 'b'))
    ref = DirectorySnapshot(p(''))
    mv(p('dir1/a'), p('dir2/b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert diff.files_moved == [(p('dir1/a'), p('dir2/b'))]
    assert diff.files_deleted == [p('dir2/b')]
    assert diff.files_created == []


@windows_only
def test_move_replace_windows(p):
    touch(p('a'))
    wait() #set a and b to different timestamp
    touch(p('b'))
    ref = DirectorySnapshot(p(''))
    mv(p('a'), p('b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert diff.files_deleted == [p('a')]
    assert diff.files_modified == [p('b')]


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
    mv(p('dir1/a'), p('dir2/b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert set(diff.dirs_modified) == set([p('dir1'), p('dir2')])


@skip_on_windows
def test_detect_modify_for_moved_files(p):
    touch(p('a'))
    ref = DirectorySnapshot(p(''))
    wait()
    touch(p('a'))
    mv(p('a'), p('b'))
    diff = DirectorySnapshotDiff(ref, DirectorySnapshot(p('')))
    assert diff.files_moved == [(p('a'), p('b'))]
    assert diff.files_modified == [p('a')]
