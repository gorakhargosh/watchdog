# -*- coding: utf-8 -*-
# platform.py: platform determination.
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

import sys

PLATFORM_WINDOWS = 'windows'
PLATFORM_LINUX = 'linux'
PLATFORM_BSD = 'bsd'
PLATFORM_DARWIN = 'darwin'
PLATFORM_UNKNOWN = 'unknown'

def get_platform_name():
    if sys.platform.startswith("win"):
        return PLATFORM_WINDOWS
    elif sys.platform.startswith('darwin'):
        return PLATFORM_DARWIN
    elif sys.platform.startswith('linux'):
        return PLATFORM_LINUX
    elif sys.platform.startswith('bsd'):
        return PLATFORM_BSD
    else:
        return PLATFORM_UNKNOWN

__platform__ = get_platform_name()

def is_linux():
    return __platform__ == PLATFORM_LINUX

def is_bsd():
    return __platform__ == PLATFORM_BSD

def is_darwin():
    return __platform__ == PLATFORM_DARWIN

def is_windows():
    return __platform__ == PLATFORM_WINDOWS

