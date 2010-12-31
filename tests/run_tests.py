#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os.path
import sys

import nose

def absolute_path(path):
    return os.path.abspath(os.path.normpath(path))

dir_path = absolute_path(os.path.dirname(__file__))
parent_dir_path = os.path.dirname(dir_path)
sys.path[0:0] = [parent_dir_path]

from watchdog.utils import platform

# Explicitly define which packages/modules to cover.
cover_packages = [
    #'watchdog.version',
    #'watchdog.platform',
    'watchdog.events',
    'watchdog.tricks',
    'watchdog.utils',
    #'watchdog.utils.echo',
    'watchdog.utils.dirsnapshot',
    'watchdog.utils.bricks',
    'watchdog.observers',
    'watchdog.observers.api',
    'watchdog.observers.polling',
]
cover_packages_windows = [
    'watchdog.observers.read_directory_changes',
    'watchdog.observers.read_directory_changes_async',
]
cover_packages_bsd = [
    'watchdog.observers.kqueue',
]
cover_packages_darwin = [
    'watchdog.observers.fsevents',
    'watchdog.observers.kqueue',
]
cover_packages_linux = [
    'watchdog.observers.inotify',
]

if platform.is_windows():
    cover_packages.extend(cover_packages_windows)
elif platform.is_darwin():
    cover_packages.extend(cover_packages_darwin)
elif platform.is_bsd():
    cover_packages.extend(cover_packages_bsd)
elif platform.is_linux():
    cover_packages.extend(cover_packages_linux)


if __name__ == "__main__":
    config_path = os.path.join(parent_dir_path, 'nose.cfg')

    argv = [__file__]
    argv.append('--detailed-errors')
    argv.append('--with-coverage')
    # Coverage by itself generates more usable reports.
    #argv.append('--cover-erase')
    #argv.append('--cover-html')
    argv.append('--cover-package=%s' % ','.join(cover_packages))
    argv.append('--config=%s' % config_path)
    nose.run(argv=argv)
