#!/usr/bin/env python
# -*- coding: utf-8 -*-
# nosy: continuous integration for watchdog
#
# Copyright (C) 2010 Yesudeep Mangalapilly <yesudeep@gmail.com>
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
                return os.walk(_path).next()
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

            # The reports coverage generates all by itself are more
            # user-friendly than the ones which `nosetests --with-coverage`
            # generates. Therefore, we call `coverage` explicitly to
            # generate reports, and to keep the reports in synchronization
            # with the source code, we erase all coverage information
            # before regenerating reports or running `nosetests`.
            "bin/coverage erase",
            "bin/python-tests tests/run_tests.py",
            "bin/coverage html",
        ]
        command = '; '.join(commands)


    previous_checksum = 0
    while True:
        calculated_checksum = check_sum(path, patterns=['*.py', '*.rst', '*.rst.inc'])
        if calculated_checksum != previous_checksum:
            previous_checksum = calculated_checksum
            subprocess.Popen(command, shell=True)
        time.sleep(2)



