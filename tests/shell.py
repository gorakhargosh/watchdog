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
    :module: tests.shell
    :synopsis: Common shell operations for testing.
    :author: yesudeep@google.com (Yesudeep Mangalapilly)
"""

from __future__ import with_statement

import os.path
import tempfile
import shutil
import errno
import time


# def tree(path='.', show_files=False):
#    print(path)
#    padding = ''
#    for root, directories, filenames in os.walk(path):
#        print(padding + os.path.basename(root) + os.path.sep)
#        padding = padding + '   '
#        for filename in filenames:
#            print(padding + filename)


def cd(path):
    os.chdir(path)


def pwd():
    path = os.getcwd()
    print(path)
    return path


def mkdir(path, parents=False):
    """Creates a directory (optionally also creates all the parent directories
  in the path)."""
    if parents:
        try:
            os.makedirs(path)
        except OSError as e:
            if not e.errno == errno.EEXIST:
                raise
    else:
        os.mkdir(path)


def rm(path, recursive=False):
    """Deletes files or directories."""
    if os.path.isdir(path):
        if recursive:
            shutil.rmtree(path)
        # else:
        #    os.rmdir(path)
        else:
            raise OSError("rm: %s: is a directory." % path)
    else:
        os.remove(path)


def touch(path, times=None):
    """Updates the modified timestamp of a file or directory."""
    if os.path.isdir(path):
        os.utime(path, times)
    else:
        with open(path, 'ab'):
            os.utime(path, times)


def truncate(path):
    """Truncates a file."""
    with open(path, 'wb'):
        os.utime(path, None)


def mv(src_path, dest_path):
    """Moves files or directories."""
    try:
        os.rename(src_path, dest_path)
    except OSError:
        # this will happen on windows
        os.remove(dest_path)
        os.rename(src_path, dest_path)


def mkdtemp():
    return tempfile.mkdtemp()


def ls(path='.'):
    return os.listdir(path)
