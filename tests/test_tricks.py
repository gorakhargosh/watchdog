"""Coverage for watchdog.tricks validation and stop/restart guards."""

from __future__ import annotations

from unittest import mock

import pytest

from watchdog.events import FileModifiedEvent
from watchdog.tricks import AutoRestartTrick, LoggerTrick, ShellCommandTrick


def test_auto_restart_trick_rejects_negative_kill_after():
    with pytest.raises(ValueError, match="kill_after must be non-negative"):
        AutoRestartTrick("echo hi", kill_after=-1)


def test_auto_restart_trick_rejects_negative_debounce():
    with pytest.raises(ValueError, match="debounce_interval must be non-negative"):
        AutoRestartTrick("echo hi", debounce_interval=-0.5)


def test_auto_restart_trick_stop_is_idempotent():
    trick = AutoRestartTrick("echo hi")
    trick.stop()
    trick.stop()  # second stop must not raise or restart anything
    assert trick._is_trick_stopping  # noqa: SLF001


def test_auto_restart_trick_start_process_noop_when_stopping():
    trick = AutoRestartTrick("echo hi")
    trick._is_trick_stopping = True  # noqa: SLF001
    with mock.patch.object(trick, "_start_process", wraps=trick._start_process) as spy:  # noqa: SLF001
        trick._restart_process()  # noqa: SLF001
    assert trick.process is None
    spy.assert_not_called()


def test_shell_command_trick_drops_event_while_process_running():
    trick = ShellCommandTrick("echo hi", drop_during_process=True)
    trick.is_process_running = mock.Mock(return_value=True)
    with mock.patch("watchdog.tricks.subprocess.Popen") as popen:
        trick.on_any_event(FileModifiedEvent("x"))
    popen.assert_not_called()


def test_logger_trick_echoes_event_to_log(caplog):
    import logging

    trick = LoggerTrick()
    with caplog.at_level(logging.INFO, logger="watchdog.tricks"):
        trick.on_any_event(FileModifiedEvent("/tmp/some file.txt"))
    assert "on_any_event" in caplog.text
    assert "/tmp/some file.txt" in caplog.text
