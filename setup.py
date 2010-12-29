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
import os.path

from setuptools import setup, find_packages
from setuptools.extension import Extension
from setuptools.command.build_ext import build_ext
from distutils.util import get_platform

SRC_DIR = 'src'
WATCHDOG_PKG_DIR = os.path.join(SRC_DIR, 'watchdog')

version = imp.load_source('version',
                          os.path.join(WATCHDOG_PKG_DIR, 'version.py'))
DOWNLOAD_URL =\
"http://watchdog-python.googlecode.com/files/watchdog-%s.tar.gz"\
% version.VERSION_STRING

PLATFORM_LINUX = 'linux'
PLATFORM_WINDOWS = 'windows'
PLATFORM_MACOSX = 'macosx'
PLATFORM_BSD = 'bsd'

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

_watchdog_fsevents_sources = [
    os.path.join(SRC_DIR, '_watchdog_fsevents.c'),
    os.path.join(SRC_DIR, '_watchdog_util.c'),
]

ext_modules = {
    PLATFORM_MACOSX: [
        Extension(name='_watchdog_fsevents',
                  sources=_watchdog_fsevents_sources,
                  libraries=['m'],
                  define_macros=[
                      ('WATCHDOG_VERSION_STRING', version.VERSION_STRING),
                      ('WATCHDOG_VERSION_MAJOR', version.VERSION_MAJOR),
                      ('WATCHDOG_VERSION_MINOR', version.VERSION_MINOR),
                      ('WATCHDOG_VERSION_BUILD', version.VERSION_BUILD),
                  ],
                  extra_link_args=['-framework', 'CoreFoundation',
                                   '-framework', 'CoreServices'],
                  extra_compile_args=[
                      '-std=c99',
                      '-pedantic',
                      '-Wall',
                      '-Wextra',
                      '-fPIC',
                      ]
                  ),
    ],
}

install_requires = ['PyYAML >=3.09', 'argh >=0.8.1']
if sys.version_info < (2, 7, 0):
# argparse is merged into Python 2.7 in the Python 2x series
# and Python 3.2 in the Python 3x series.
    install_requires.append('argparse >=1.1')
    if any([key in sys.platform for key in ['bsd', 'darwin']]):
    # Python 2.6 and below have the broken/non-existent kqueue implementations
    # in the select module. This backported patch adds one from Python 2.7,
    # which works.
        install_requires.append('select_backport >=0.2')


def read_file(filename):
    """
    Reads the contents of a given file relative to the directory
    containing this file and returns it.

    :param filename:
        The file to open and read contents from.
    """
    return open(os.path.join(os.path.dirname(__file__), filename)).read()

if sys.version_info < (3,):
    extra = {}
else:
    extra = dict(use_2to3=True)

setup(name="watchdog",
      version=version.VERSION_STRING,
      description="Filesystem events monitoring",
      long_description=read_file('README'),
      author="Gora Khargosh",
      author_email="gora.khargosh@gmail.com",
      license="MIT License",
      url="http://github.com/gorakhargosh/watchdog",
      download_url=DOWNLOAD_URL,
      keywords=' '.join([
                            'python',
                            'filesystem',
                            'monitoring',
                            'monitor',
                            'FSEvents',
                            'kqueue',
                            'inotify',
                            'ReadDirectoryChangesW',
                            'polling',
                            'DirectorySnapshot',
                            ]
                        ),
      classifiers=[
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
          ],
      cmdclass={
          'build_ext': build_ext
          },
      ext_modules=ext_modules.get(platform, []),
      package_dir={'': SRC_DIR},
      packages=find_packages(SRC_DIR),
      include_package_data=True,
      install_requires=install_requires,
      entry_points={
          'console_scripts': [
              'watchmedo = watchdog.watchmedo:main',
              ]
          },
      zip_safe=False,
      **extra
      )
