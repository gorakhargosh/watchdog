#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2010, 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
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
:module: nosy
:synopsis: Rewrite of Jeff Winkler's nosy script tailored to testing watchdog
:platform: OS-independent
"""

import os.path
import sys
import stat
import time
import subprocess
from fnmatch import fnmatch


def match_patterns(pathname, patterns):
    """Returns ``True`` if the pathname matches any of the given patterns."""
    for pattern in patterns:
        if fnmatch(pathname, pattern):
            return True
    return False


def filter_paths(pathnames, patterns=None, ignore_patterns=None):
    """Filters from a set of paths based on acceptable patterns and
   ignorable patterns."""
    result = []
    if patterns is None:
        patterns = ['*']
    if ignore_patterns is None:
        ignore_patterns = []
    for pathname in pathnames:
        if match_patterns(pathname, patterns) and not match_patterns(pathname, ignore_patterns):
            result.append(pathname)
    return result


def absolute_walker(pathname, recursive):
    if recursive:
        walk = os.walk
    else:
        def walk(_path):
            try:
                return next(os.walk(_path))
            except NameError:
                return next(os.walk(_path))
    for root, directories, filenames in walk(pathname):
        yield root
        for directory in directories:
            yield os.path.abspath(os.path.join(root, directory))
        for filename in filenames:
            yield os.path.abspath(os.path.join(root, filename))


def glob_recursive(pathname, patterns=None, ignore_patterns=None):
    full_paths = []
    for root, _, filenames in os.walk(pathname):
        for filename in filenames:
            full_path = os.path.abspath(os.path.join(root, filename))
            full_paths.append(full_path)
    filepaths = filter_paths(full_paths, patterns, ignore_patterns)
    return filepaths


def check_sum(pathname='.', patterns=None, ignore_patterns=None):
    checksum = 0
    for f in glob_recursive(pathname, patterns, ignore_patterns):
        stats = os.stat(f)
        checksum += stats[stat.ST_SIZE] + stats[stat.ST_MTIME]
    return checksum


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = '.'

    if len(sys.argv) > 2:
        command = sys.argv[2]
    else:
        commands = [
            # Build documentation automatically as well as the source code
            # changes.
            "make SPHINXBUILD=../bin/sphinx-build -C docs html",

            "python -m pytest",
        ]
        command = '; '.join(commands)

    previous_checksum = 0
    while True:
        calculated_checksum = check_sum(path, patterns=['*.py', '*.rst', '*.rst.inc'])
        if calculated_checksum != previous_checksum:
            previous_checksum = calculated_checksum
            subprocess.Popen(command, shell=True)
        time.sleep(2)
