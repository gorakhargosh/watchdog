"""Coverage for watchdog.utils module-loading helpers and BaseThread."""

from __future__ import annotations

import threading

import pytest

from watchdog.utils import BaseThread, load_class, load_module


def test_load_module_returns_imported_module():
    assert load_module("os") is __import__("os")


def test_load_module_missing_raises_importerror():
    with pytest.raises(ImportError, match="No module named definitely_not_a_module"):
        load_module("definitely_not_a_module")


def test_load_class_loads_class_from_dotted_path():
    assert load_class("watchdog.events.FileSystemEventHandler") is not None
    from watchdog.events import FileSystemEventHandler

    assert load_class("watchdog.events.FileSystemEventHandler") is FileSystemEventHandler


def test_load_class_rejects_bare_classname():
    with pytest.raises(ValueError, match="must contain a module name and a classname"):
        load_class("FileSystemEventHandler")


def test_load_class_missing_attribute():
    with pytest.raises(AttributeError, match="does not have class attribute"):
        load_class("watchdog.events.NoSuchClass")


def test_load_class_missing_module():
    with pytest.raises(ImportError, match="No module named"):
        load_class("no_such_module.SomeClass")


def test_base_thread_is_daemon_and_stopped_event():
    thread = BaseThread()
    assert isinstance(thread, threading.Thread)
    assert thread.daemon is True
    assert isinstance(thread.stopped_event, threading.Event)
    assert not thread.stopped_event.is_set()
