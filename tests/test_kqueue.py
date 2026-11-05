from __future__ import annotations

import select

import pytest

from watchdog.utils import platform

if (not platform.is_bsd() and not platform.is_darwin()) or not hasattr(select, "KQ_NOTE_DELETE"):
    pytest.skip(
        "kqueue (with KQ_NOTE_* constants) is not supported on this platform/interpreter.", allow_module_level=True
    )

import errno
import os
from unittest.mock import patch

from watchdog.observers.api import EventQueue, ObservedWatch
from watchdog.observers.kqueue import KqueueEmitter


def test_directory_filter_prunes_descriptors(tmp_path):
    for name in ("keep", "skip"):
        (tmp_path / name / "child").mkdir(parents=True)
        (tmp_path / name / "file").touch()
    watch = ObservedWatch(str(tmp_path), recursive=True, directory_filter=lambda path: os.path.basename(path) != "skip")
    emitter = KqueueEmitter(EventQueue(), watch)
    try:
        assert set(emitter._descriptors.paths) == {  # noqa: SLF001
            str(tmp_path),
            str(tmp_path / "keep"),
            str(tmp_path / "keep" / "child"),
            str(tmp_path / "keep" / "file"),
        }
        # Register the initial kevents before making changes.
        emitter.queue_events(0)
        (tmp_path / "skip").rename(tmp_path / "included")
        (tmp_path / "keep").rename(tmp_path / "skip")
        emitter.queue_events(1)
        assert set(emitter._descriptors.paths) == {  # noqa: SLF001
            str(tmp_path),
            str(tmp_path / "included"),
            str(tmp_path / "included" / "child"),
            str(tmp_path / "included" / "file"),
        }
    finally:
        emitter.on_thread_stop()


@pytest.mark.parametrize("err", [errno.EACCES, errno.EPERM])
def test_register_kevent_ignores_permission_errors(tmpdir, err):
    """A file we are not allowed to open must not kill the emitter thread.

    See https://github.com/gorakhargosh/watchdog/issues/1115
    """
    emitter = KqueueEmitter(EventQueue(), ObservedWatch(str(tmpdir), recursive=False), timeout=1)

    # The file appears after the watch was set up, as in the reported scenario.
    path = os.path.join(str(tmpdir), "denied")
    with open(path, "w"):
        pass

    real_open = os.open

    def fake_open(p, flags, *args, **kwargs):
        if p == path:
            raise PermissionError(err, os.strerror(err), p)
        return real_open(p, flags, *args, **kwargs)

    try:
        with patch("os.open", side_effect=fake_open):
            emitter._register_kevent(path, is_directory=False)  # noqa: SLF001
    finally:
        emitter._descriptors.clear()  # noqa: SLF001
