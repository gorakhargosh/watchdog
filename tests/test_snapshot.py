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
from .shell import mkdtemp, mkdir, touch, mv, symlink
from watchdog.utils.dirsnapshot import DirectorySnapshot
from watchdog.utils.dirsnapshot import DirectorySnapshotDiff

def sync():
    os.system("sync")
def wait():
    sync()
    time.sleep(1)

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

def test_follow_symlink(p):
    mkdir(p('root'))
    mkdir(p('root', 'real'))
    symlink(p('root', 'real'), p('root', 'symlink'))
    touch(p('root', 'real', 'a'))
    ref = DirectorySnapshot(p(''), follow_symlinks=True)
    assert p('root', 'symlink', 'a') in ref.paths
    ref = DirectorySnapshot(p(''), follow_symlinks=False)
    assert p('root', 'symlink', 'a') not in ref.paths

def test_one_filesystem(p):
    mkdir(p('root'))
    target = p('root', 'a')
    touch(target)
    dev_id = os.stat(target).st_dev
    ref = DirectorySnapshot(p(''))
    assert target in ref.paths
    ref = DirectorySnapshot(p(''), dev_id=dev_id)
    assert target in ref.paths
    ref = DirectorySnapshot(p(''), dev_id=(dev_id + 1))
    assert target not in ref.paths
