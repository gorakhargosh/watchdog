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

import os
import sys
from fnmatch import fnmatch

def match_patterns(pathname, patterns):
    """Returns True if the pathname matches any of the given patterns."""
    for pattern in patterns:
        if fnmatch(pathname, pattern):
            return True
    return False


def filter_paths(pathnames, patterns=["*"], ignore_patterns=[]):
    """Filters from a set of paths based on acceptable patterns and
    ignorable patterns."""
    result = []
    if patterns is None:
        patterns = []
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


def load_class(dotted_path, *args, **kwargs):
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
        if hasattr(module, klass_name):
            klass = getattr(module, klass_name)
            return klass
            # Finally create and return an instance of the class
            #return klass(*args, **kwargs)
        else:
            raise AttributeError('Module %s does not have class attribute %s' % (module_name, klass_name))
    else:
        raise ValueError('Dotted module path %s must contain a module name and a classname' % dotted_path)


def read_text_file(file_path, mode='rb'):
    """Returns the contents of a file after opening it in read-only mode."""
    return open(file_path, mode).read()


def get_walker(recursive=False):
    """Returns a recursive or a non-recursive directory walker."""
    if recursive:
        walk = os.walk
    else:
        def walk(path):
            yield next(os.walk(path))
    return walk
