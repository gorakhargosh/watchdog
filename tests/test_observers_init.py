from __future__ import annotations

import builtins
import types
import warnings
from typing import Any, Callable

import pytest

from watchdog.observers import _get_observer_cls
from watchdog.utils import UnsupportedLibcError


def _stub_module(name: str, **attrs: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def _patch_imports(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, types.ModuleType | Exception],
) -> None:
    """Make `from <name> import ...` return a stub or raise, for the given dotted names.

    Everything else falls through to the real ``__import__``, so unrelated
    imports (including the platform-detection helpers themselves) still work.
    """
    real_import: Callable[..., Any] = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in overrides:
            override = overrides[name]
            if isinstance(override, Exception):
                raise override
            return override
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def _set_platform(
    monkeypatch: pytest.MonkeyPatch,
    *,
    linux: bool = False,
    darwin: bool = False,
    windows: bool = False,
    bsd: bool = False,
) -> None:
    monkeypatch.setattr("watchdog.observers.platform.is_linux", lambda: linux)
    monkeypatch.setattr("watchdog.observers.platform.is_darwin", lambda: darwin)
    monkeypatch.setattr("watchdog.observers.platform.is_windows", lambda: windows)
    monkeypatch.setattr("watchdog.observers.platform.is_bsd", lambda: bsd)


def test_linux_reraises_errors_other_than_unsupported_libc(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only UnsupportedLibcError is meant to trigger a fallback on Linux; any
    # other failure while importing the inotify backend should propagate.
    _set_platform(monkeypatch, linux=True)
    _patch_imports(monkeypatch, {"watchdog.observers.inotify": ImportError("boom")})

    with pytest.raises(ImportError, match="boom"):
        _get_observer_cls()


def test_linux_falls_back_to_polling_on_unsupported_libc(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_platform(monkeypatch, linux=True)
    sentinel = object()
    _patch_imports(
        monkeypatch,
        {
            "watchdog.observers.inotify": UnsupportedLibcError("no libc"),
            "watchdog.observers.polling": _stub_module("watchdog.observers.polling", PollingObserver=sentinel),
        },
    )

    assert _get_observer_cls() is sentinel


def test_darwin_falls_back_to_kqueue_when_fsevents_import_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_platform(monkeypatch, darwin=True)
    sentinel = object()
    _patch_imports(
        monkeypatch,
        {
            "watchdog.observers.fsevents": ImportError("no fsevents extension"),
            "watchdog.observers.kqueue": _stub_module("watchdog.observers.kqueue", KqueueObserver=sentinel),
        },
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _get_observer_cls()

    assert result is sentinel
    assert any("Fall back to kqueue" in str(w.message) for w in caught)


def test_darwin_falls_back_to_polling_when_fsevents_and_kqueue_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_platform(monkeypatch, darwin=True)
    sentinel = object()
    _patch_imports(
        monkeypatch,
        {
            "watchdog.observers.fsevents": ImportError("no fsevents extension"),
            "watchdog.observers.kqueue": ImportError("no kqueue support"),
            "watchdog.observers.polling": _stub_module("watchdog.observers.polling", PollingObserver=sentinel),
        },
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _get_observer_cls()

    assert result is sentinel
    assert any("Fall back to polling" in str(w.message) for w in caught)


def test_windows_falls_back_to_polling_on_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_platform(monkeypatch, windows=True)
    sentinel = object()
    _patch_imports(
        monkeypatch,
        {
            "watchdog.observers.read_directory_changes": ImportError("no winapi extension"),
            "watchdog.observers.polling": _stub_module("watchdog.observers.polling", PollingObserver=sentinel),
        },
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _get_observer_cls()

    assert result is sentinel
    assert any("Failed to import `read_directory_changes`" in str(w.message) for w in caught)


def test_unrecognized_platform_returns_polling_observer(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_platform(monkeypatch)
    sentinel = object()
    _patch_imports(
        monkeypatch,
        {"watchdog.observers.polling": _stub_module("watchdog.observers.polling", PollingObserver=sentinel)},
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _get_observer_cls()

    assert result is sentinel
    assert not caught
