from functools import partial
import os
import sys
import threading
import pytest
from . import shell


@pytest.fixture()
def tmpdir(request):
    path = os.path.realpath(shell.mkdtemp())
    yield path
    shell.rm(path, recursive=True)


@pytest.fixture()
def p(tmpdir, *args):
    """
    Convenience function to join the temporary directory path
    with the provided arguments.
    """
    return partial(os.path.join, tmpdir)


@pytest.fixture(autouse=True)
def no_thread_leaks():
    """
    Fail on thread leak.
    We do not use pytest-threadleak because it is not reliable.
    """

    yield

    if sys.version_info < (3,):
        return

    main = threading.main_thread()
    assert not [th for th in threading._dangling
                if th is not main and th.is_alive()]


@pytest.fixture(autouse=True)
def no_warnings(recwarn):
    """Fail on warning."""

    yield

    warnings = []
    for warning in recwarn:  # pragma: no cover
        message = str(warning.message)
        if (
            "Not importing directory" in message
            or "Using or importing the ABCs" in message
        ):
            continue
        warnings.append("{w.filename}:{w.lineno} {w.message}".format(w=warning))
    assert not warnings
