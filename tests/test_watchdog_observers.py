# -*- coding: utf-8 -*-

from nose import SkipTest

from watchdog.observers import Observer

class TestObserver:
    def test___init__(self):
        observer = Observer()
