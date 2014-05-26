#!/usr/bin/env python
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
import pytest
from . import shell
from sys import version_info
from functools import partial

__all__ = ['unittest', 'Queue', 'tmpdir', 'p']

if version_info < (2, 7):
    import unittest2 as unittest
else:
    import unittest

try:
    from Queue import Queue  # Python 2
except ImportError:
    from queue import Queue  # Python 3


@pytest.fixture()
def tmpdir(request):
    path = os.path.realpath(shell.mkdtemp())
    def finalizer():
        shell.rm(path, recursive=True)
    request.addfinalizer(finalizer)
    return path


@pytest.fixture()
def p(tmpdir, *args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return partial(os.path.join, tmpdir)
