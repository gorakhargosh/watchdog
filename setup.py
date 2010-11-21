#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
from setuptools import setup
from setuptools.extension import Extension
from setuptools.command.build_ext import build_ext
from distutils.util import get_platform

VERSION_INFO = (0,3,4)
VERSION_STRING = "%d.%d.%d" % VERSION_INFO

logging.basicConfig(level=logging.DEBUG)

def read_file(filename):
    """Reads the contents of a given file and returns it."""
    return open(os.path.join(os.path.dirname(__file__), filename)).read()

PLATFORM_LINUX = 'linux'
PLATFORM_WINDOWS = 'windows'
PLATFORM_MACOSX = 'macosx'

# Determine platform to pick the implementation.
platform = get_platform()
logging.debug("Platform: " + platform)
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
    'License :: OSI Approved :: MIT License',
    'Natural Language :: English',
    'Operating System :: POSIX :: Linux',
    'Operating System :: MacOS :: MacOS X',
    'Operating System :: Microsoft :: Windows :: Windows NT/2000',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: C',
    'Topic :: Software Development :: Libraries',
    'Topic :: System :: Monitoring',
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

common_install_requires = ['PyYAML >= 3.09', 'argh >= 0.6.0']

install_requires = {
    PLATFORM_MACOSX: [],
    PLATFORM_LINUX: ['pyinotify >= 0.9.1'],
    PLATFORM_WINDOWS: ['pywin32 >= 214'],
}

setup(
    name="watchdog",
    version=VERSION_STRING,
    description="Filesystem events monitoring",
    long_description=read_file('README.md'),
    author="Gora Khargosh",
    author_email="gora.khargosh@gmail.com",
    license="MIT License",
    cmdclass=dict(build_ext=build_ext),
    url="http://github.com/gorakhargosh/watchdog",
    download_url="http://watchdog-python.googlecode.com/files/watchdog-%s.tar.gz" % VERSION_STRING,
    keywords = "python filesystem monitoring monitor fsevents inotify",
    classifiers=trove_classifiers,
    ext_modules=ext_modules.get(platform, []),
    packages=['watchdog'],
    zip_safe=False,
    install_requires=common_install_requires + install_requires.get(platform, []),
    py_modules=[],
    )
