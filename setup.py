#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Gora Khargosh <gora.khargosh@gmail.com>
# Copyright (C) 2010 Filip Noetzel <filip@j03.de>
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
import imp

from os.path import join as path_join, dirname
from setuptools import setup
from setuptools.extension import Extension
from setuptools.command.build_ext import build_ext
from distutils.util import get_platform

version = imp.load_source('version', path_join('watchdog', 'version.py'))

def read_file(filename):
    """Reads the contents of a given file and returns it."""
    return open(path_join(dirname(__file__), filename)).read()

PLATFORM_LINUX = 'linux'
PLATFORM_WINDOWS = 'windows'
PLATFORM_MACOSX = 'macosx'

# Determine platform to pick the implementation.
platform = get_platform()
if platform.startswith('macosx'):
    platform = PLATFORM_MACOSX
elif platform.startswith('linux'):
    platform = PLATFORM_LINUX
elif platform.startswith('win'):
    platform = PLATFORM_WINDOWS
else:
    platform = None

trove_classifiers = (
    'Development Status :: 3 - Alpha',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'Intended Audience :: System Administrators',
    'License :: OSI Approved :: MIT License',
    'Natural Language :: English',
    'Operating System :: POSIX :: Linux',
    'Operating System :: MacOS :: MacOS X',
    'Operating System :: POSIX :: BSD',
    'Operating System :: Microsoft :: Windows :: Windows NT/2000',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: C',
    'Topic :: Software Development :: Libraries',
    'Topic :: System :: Monitoring',
    'Topic :: System :: Filesystems',
    'Topic :: Utilities',
)

ext_modules = {
    PLATFORM_MACOSX: [
        Extension(name='_watchdog_fsevents',
                  sources=['watchdog/_watchdog_fsevents.c'],
                  extra_link_args=['-framework', 'CoreFoundation',
                                   '-framework', 'CoreServices'],
                  ),
    ],
    PLATFORM_LINUX: [],
    PLATFORM_WINDOWS: [],
}

common_install_requires = ['PyYAML >=3.09', 'argh >=0.8.1']
if sys.version_info < (2, 7, 0) and \
    ('bsd' in sys.platform or 'darwin' in sys.platform):
    # Python 2.6 and below have the broken/non-existent kqueue implementations
    # in the select module. This backported patch adds one from Python 2.7,
    # which works.
    common_install_requires.append('select_backport >=0.2')
    common_install_requires.append('argparse >=1.1')

install_requires = {
    PLATFORM_MACOSX: [],
    PLATFORM_LINUX: ['pyinotify >=0.9.1'],
    PLATFORM_WINDOWS: ['pywin32 >=214'],
}

scripts = []
#if platform == PLATFORM_WINDOWS:
#    scripts.append(path_join('scripts', 'watchmedo.bat'))

setup(
    name="watchdog",
    version=version.VERSION_STRING,
    description="Filesystem events monitoring",
    long_description=read_file('README'),
    author="Gora Khargosh",
    author_email="gora.khargosh@gmail.com",
    license="MIT License",
    url="http://github.com/gorakhargosh/watchdog",
    download_url="http://watchdog-python.googlecode.com/files/watchdog-%s.tar.gz" % version.VERSION_STRING,
    keywords="python filesystem monitoring monitor fsevents inotify",
    classifiers=trove_classifiers,
    cmdclass=dict(build_ext=build_ext),
    ext_modules=ext_modules.get(platform, []),
    packages=['watchdog', 'watchdog.observers', 'watchdog.tricks', 'watchdog.utils'],
    scripts=scripts,
    entry_points={'console_scripts': ['watchmedo = watchdog.watchmedo:main']},
    install_requires=common_install_requires + install_requires.get(platform, []),
    zip_safe=False,
    )

