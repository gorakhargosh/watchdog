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

PLATFORM_LINUX = 'linux'
PLATFORM_WINDOWS = 'windows'
PLATFORM_MACOSX = 'macosx'
PLATFORM_BSD = 'bsd'

# Determine platform to pick the implementation.


def determine_platform():
    platform = get_platform()
    if platform.startswith('macosx'):
        platform = PLATFORM_MACOSX
    elif platform.startswith('linux'):
        platform = PLATFORM_LINUX
    elif platform.startswith('win'):
        platform = PLATFORM_WINDOWS
    else:
        platform = None
    return platform

platform = determine_platform()

ext_modules = {
    PLATFORM_MACOSX: [
        Extension(
            name='_watchdog_fsevents',
            sources=[
                'src/watchdog_fsevents.c',
            ],
            libraries=['m'],
            define_macros=[
                ('WATCHDOG_VERSION_STRING',
                 '"' + version.VERSION_STRING + '"'),
                ('WATCHDOG_VERSION_MAJOR', version.VERSION_MAJOR),
                ('WATCHDOG_VERSION_MINOR', version.VERSION_MINOR),
                ('WATCHDOG_VERSION_BUILD', version.VERSION_BUILD),
            ],
            extra_link_args=[
                '-framework', 'CoreFoundation',
                '-framework', 'CoreServices',
            ],
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

extra_args = dict(
    cmdclass={
        'build_ext': build_ext
    },
    ext_modules=ext_modules.get(platform, []),
)

install_requires = ['PyYAML >=3.09',
                    'argh >=0.8.1',
                    'pathtools >=0.1.1']
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

if not sys.version_info < (3,):
    extra_args.update(dict(use_2to3=False))

setup(name="watchdog",
      version=version.VERSION_STRING,
      description="Filesystem events monitoring",
      long_description=read_file('README.rst'),
      author="Yesudeep Mangalapilly",
      author_email="yesudeep@gmail.com",
      license="Apache License 2.0",
      url="http://github.com/gorakhargosh/watchdog",
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
      ]),
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Environment :: Console',
          'Intended Audience :: Developers',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: Apache Software License',
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
      package_dir={'': SRC_DIR},
      packages=find_packages(SRC_DIR),
      include_package_data=True,
      install_requires=install_requires,
      entry_points={'console_scripts': [
          'watchmedo = watchdog.watchmedo:main',
      ]},
      zip_safe=False,
      **extra_args
      )
