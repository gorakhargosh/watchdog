# -*- coding: utf-8 -*-
# utils.py: Utility functions.
#
# Copyright (C) 2010 Gora Khargosh <gora.khargosh@gmail.com>
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
:module: watchdog.utils
:synopsis: Utility classes and functions.
:author: Gora Khargosh <gora.khargosh@gmail.com>

Functions
---------

.. autofunction:: absolute_path

.. autofunction:: filter_paths

.. autofunction:: get_parent_dir_path

.. autofunction:: get_walker

.. autofunction:: has_attribute

.. autofunction:: load_class

.. autofunction:: load_module

.. autofunction:: match_patterns

.. autofunction:: read_text_file

.. autofunction:: real_absolute_path


Classes
-------
.. autoclass:: DaemonThread
   :members:
   :show-inheritance:
   :inherited-members:

"""

import os
import os.path
import sys
import threading
import ctypes.util

from fnmatch import fnmatch


def ctypes_find_library(name, default):
    """Finds a dynamic library."""
    module_path = None
    try:
        module_path = ctypes.util.find_library(name)
    except (OSError, IOError):
        module_path = default
    return module_path


def has_attribute(ob, attribute):
    """
    :func:`hasattr` swallows exceptions. :func:`has_attribute` tests a Python object for the
    presence of an attribute.

    :param ob:
        object to inspect
    :param attribute:
        ``str`` for the name of the attribute.
    """
    return getattr(ob, attribute, None) is not None


class DaemonThread(threading.Thread):
    """
    Daemon thread convenience class, sets a few properties and makes
    writing daemon threads a little easier.
    """
    def __init__(self):
        threading.Thread.__init__(self)
        if has_attribute(self, 'daemon'):
            self.daemon = True
        else:
            self.setDaemon(True)
        self._stopped_event = threading.Event()

        if not has_attribute(self._stopped_event.is_set, 'is_set'):
            self._stopped_event.is_set = self._stopped_event.isSet

    @property
    def stopped_event(self):
        return self._stopped_event

    def should_stop(self):
        """Determines whether the daemon thread should stop."""
        return self._stopped_event.is_set()

    def should_keep_running(self):
        """Determines whether the daemon thread should continue running."""
        return not self._stopped_event.is_set()

    def on_thread_told_to_stop(self):
        """Override this method instead of :meth:`stop()`.
        :meth:`stop()` calls this method.

        Note that this method is called immediately after the daemon thread
        is signaled to halt.
        """
        pass

    def stop(self):
        """Signals the daemon thread to stop."""
        self._stopped_event.set()
        self.on_thread_told_to_stop()


if not has_attribute(DaemonThread, 'is_alive'):
    DaemonThread.is_alive = DaemonThread.isAlive


def match_patterns(pathname, patterns):
    """
    Returns True if the pathname matches any of the given patterns.

    :param pathname:
        A path name that will be matched against a wildcard pattern.
    :param patterns:
        A list of wildcard patterns to match the filename against.
    :returns:
        ``True`` if the pattern matches; ``False`` otherwise.
    """
    for pattern in patterns:
        if fnmatch(pathname, pattern):
            return True
    return False


#def match_allowed_and_ignored_patterns(pathname, allowed_patterns, ignore_patterns):
#    return match_patterns(pathname, allowed_patterns) and not match_patterns(pathname, ignore_patterns)


def filter_paths(pathnames, patterns=None, ignore_patterns=None):
    """
    Filters from a set of paths based on acceptable patterns and
    ignorable patterns.

    :param pathnames:
        A list of path names that will be filtered based on matching and
        ignored patterns.
    :param patterns:
        Allow filenames matching wildcard patterns specified in this list.
    :param ignore_patterns:
        Ignores filenames matching wildcard patterns specified in this list.
    :returns:
        A list of pathnames that matched the allowable patterns and passed
        through the ignored patterns.
    """
    result = []
    if patterns is None:
        patterns = ['*']
    if ignore_patterns is None:
        ignore_patterns = []
    for path in pathnames:
        if match_patterns(path, patterns) and not match_patterns(path, ignore_patterns):
            result.append(path)
    return result


def load_module(module_name):
    """Imports a module given its name and returns a handle to it."""
    try:
        __import__(module_name)
    except ImportError:
        raise ImportError('No module named %s' % module_name)
    return sys.modules[module_name]


def load_class(dotted_path):
    """Loads and returns a class definition provided a dotted path
    specification the last part of the dotted path is the class name
    and there is at least one module name preceding the class name.

    Notes:
    You will need to ensure that the module you are trying to load
    exists in the Python path.

    Examples:
    - module.name.ClassName    # Provided module.name is in the Python path.
    - module.ClassName         # Provided module is in the Python path.

    What won't work:
    - ClassName
    - modle.name.ClassName     # Typo in module name.
    - module.name.ClasNam      # Typo in classname.
    """
    dotted_path_split = dotted_path.split('.')
    if len(dotted_path_split) > 1:
        klass_name = dotted_path_split[-1]
        module_name = '.'.join(dotted_path_split[:-1])

        module = load_module(module_name)
        if has_attribute(module, klass_name):
            klass = getattr(module, klass_name)
            return klass
            # Finally create and return an instance of the class
            #return klass(*args, **kwargs)
        else:
            raise AttributeError('Module %s does not have class attribute %s' % (module_name, klass_name))
    else:
        raise ValueError('Dotted module path %s must contain a module name and a classname' % dotted_path)


def read_text_file(file_path, mode='rb'):
    """
    Returns the contents of a file after opening it in read-only mode.

    :param file_path:
        Path to the file to be read from.
    :param mode:
        Mode string.
    """
    return open(file_path, mode).read()


def get_walker(recursive=False):
    """
    Returns a recursive or a non-recursive directory walker.

    :param recursive:
        ``True`` produces a recursive walker; ``False`` produces a non-recursive
        walker
    :returns:
        A walker function.
    """
    if recursive:
        walk = os.walk
    else:
        def walk(path):
            try:
                yield next(os.walk(path))
            except NameError:
                yield os.walk(path).next() #IGNORE:E1101
    return walk


def absolute_path(path):
    """
    Returns the absolute path for the given path and normalizes the path as well.

    :param path:
        Path for which the absolute normalized path will be found.
    :returns:
        Absolute normalized path.
    """
    return os.path.abspath(os.path.normpath(path))


def real_absolute_path(path):
    """
    Returns the real absolute normalized path for the given path.

    :param path:
        Path for which the real absolute normalized path will be found.
    :returns:
        Real absolute normalized path.
    """
    return os.path.realpath(absolute_path(path))


def get_parent_dir_path(path):
    """
    Returns the parent directory path.

    :param path:
        Path for which the parent directory will be obtained.
    :returns:
        Parent directory path.
    """
    return absolute_path(os.path.dirname(path))

