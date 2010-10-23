#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
from setuptools import setup
from distutils.util import get_platform

logging.basicConfig(level=logging.DEBUG)

def read_file(filename):
    """Reads the contents of a given file and returns it."""
    return open(os.path.join(os.path.dirname(__file__), filename)).read()

# Determine platform to pick the implementation.
platform = get_platform()
logging.debug("Platform: " + platform)
if platform.startswith('macosx'):
    platform = 'macosx'
elif platform.startswith('linux'):
    platform = 'linux'
else:
    platform = None

trove_classifiers = (
    'Environment :: Console',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Natural Language :: English',
    'Operating System :: POSIX :: Linux',
    'Operating System :: MacOS :: MacOS X',
    'Programming Language :: Python',
    'Programming Language :: C',
    'Topic :: Software Development :: Libraries',
    'Topic :: System :: Monitoring',
)

setup(
    name="Watchdog",
    version="0.0",
    description="Filesystem events monitoring",
    long_description=read_file('README'),
    author="Gora Khargosh",
    author_email="gora.khargosh@gmail.com",
    license="MIT License",
    url="http://github.com/gorakhargosh/watchdog",
    keywords = "python filesystem monitoring monitor fsevents inotify",
    classifiers=trove_classifiers,
    packages=('watchdog',),
    )
