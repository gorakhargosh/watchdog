"""Coverage for watchdog.observers._get_observer_cls platform branches and `python -m watchdog`."""

from __future__ import annotations

import os
import subprocess
import sys
import types

import pytest

import watchdog.observers as observers
from watchdog.observers import polling
from watchdog.utils import platform


class _RaisingModule(types.ModuleType):
    """A fake module whose attribute access raises, simulating a broken backend."""

    def __init__(self, name, exc):
        super().__init__(name)
        self._exc = exc

    def __getattr__(self, item):
        raise self._exc


def _force_platform(monkeypatch, **flags):
    for name in ("is_linux", "is_darwin", "is_windows", "is_bsd"):
        monkeypatch.setattr(platform, name, lambda f=name: flags.get(f, False))


def test_linux_with_broken_inotify_falls_back_to_polling(monkeypatch):
    from watchdog.utils import UnsupportedLibcError

    monkeypatch.setitem(
        sys.modules, "watchdog.observers.inotify", _RaisingModule("inotify", UnsupportedLibcError("no libc"))
    )
    _force_platform(monkeypatch, is_linux=True)
    assert observers._get_observer_cls()  # noqa: SLF001 is polling.PollingObserver


def test_linux_with_working_inotify(monkeypatch):
    fake = types.ModuleType("watchdog.observers.inotify")
    fake.InotifyObserver = polling.PollingObserver  # stand-in class
    monkeypatch.setitem(sys.modules, "watchdog.observers.inotify", fake)
    _force_platform(monkeypatch, is_linux=True)
    assert observers._get_observer_cls()  # noqa: SLF001 is polling.PollingObserver


def test_darwin_fsevents_import_fails_falls_back_to_kqueue(monkeypatch):

    monkeypatch.setitem(
        sys.modules, "watchdog.observers.fsevents", _RaisingModule("fsevents", ImportError("no fsevents"))
    )
    _force_platform(monkeypatch, is_darwin=True)
    with pytest.warns(UserWarning, match="kqueue"):
        assert observers._get_observer_cls()  # noqa: SLF001 is kqueue.KqueueObserver


def test_darwin_both_backends_broken_falls_back_to_polling_with_warning(monkeypatch):
    monkeypatch.setitem(sys.modules, "watchdog.observers.fsevents", _RaisingModule("fsevents", ImportError("x")))
    monkeypatch.setitem(sys.modules, "watchdog.observers.kqueue", _RaisingModule("kqueue", ImportError("x")))
    _force_platform(monkeypatch, is_darwin=True)
    with pytest.warns(UserWarning, match="polling"):
        assert observers._get_observer_cls()  # noqa: SLF001 is polling.PollingObserver


def test_darwin_with_working_fsevents(monkeypatch):
    fake = types.ModuleType("watchdog.observers.fsevents")
    fake.FSEventsObserver = polling.PollingObserver
    monkeypatch.setitem(sys.modules, "watchdog.observers.fsevents", fake)
    _force_platform(monkeypatch, is_darwin=True)
    assert observers._get_observer_cls()  # noqa: SLF001 is polling.PollingObserver


def test_windows_broken_read_directory_changes_falls_back_to_polling(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "watchdog.observers.read_directory_changes", _RaisingModule("rdc", ImportError("x"))
    )
    _force_platform(monkeypatch, is_windows=True)
    with pytest.warns(UserWarning, match="polling"):
        assert observers._get_observer_cls()  # noqa: SLF001 is polling.PollingObserver


def test_bsd_uses_kqueue(monkeypatch):

    _force_platform(monkeypatch, is_bsd=True)
    assert observers._get_observer_cls()  # noqa: SLF001 is kqueue.KqueueObserver


def test_unknown_platform_uses_polling(monkeypatch):
    _force_platform(monkeypatch)
    assert observers._get_observer_cls()  # noqa: SLF001 is polling.PollingObserver


def test_python_dash_m_watchdog_runs():
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(["src", os.environ.get("PYTHONPATH", "")]))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-m", "watchdog", "--help"],
        capture_output=True,
        text=True,
        cwd=root,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()
