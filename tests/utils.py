
#!/usr/bin/env python

from __future__ import with_statement

import sys
import os
import time
import os.path
import tempfile
import shutil

def list_attributes(o, only_public=True):
    if only_public:
        def isattribute(o, attribute):
            return not (attribute.startswith('_') or callable(getattr(o, attribute)))
    else:
        def isattribute(o, attribute):
            return not callable(getattr(o, attribute))
    return [attribute for attribute in dir(o) if isattribute(o, attribute)]


def make_directory(path):
    try:
        os.mkdir(path)
    except OSError:
        pass


def remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def touch(path):
    with open(path, 'ab'):
        pass


def truncate(path):
    with open(path, 'wb'):
        pass


def get_test_path(*args):
    return os.path.join(temp_dir_path, *args)


def make_temp_dir():
    return tempfile.mkdtemp()

