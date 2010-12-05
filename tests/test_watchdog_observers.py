# -*- coding: utf-8 -*-

from nose.tools import *
from nose import SkipTest

from watchdog.observers import Observer

class TestObserver:
    def test___init__(self):
        observer = Observer()
