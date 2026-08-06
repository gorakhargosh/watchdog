"""Configuration helpers for watchdog tricks.

Functions in this module were extracted from :mod:`watchdog.watchmedo` to
separate configuration/parsing concerns from CLI command logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from watchdog.utils import load_class

if TYPE_CHECKING:
    from watchdog.observers.api import BaseObserver


def load_config(tricks_file_pathname: str) -> dict:
    """Loads the YAML configuration from the specified file.

    :param tricks_file_pathname:
        The path to the tricks configuration file.
    :returns:
        A dictionary of configuration information.
    """
    import yaml

    with open(tricks_file_pathname, "rb") as f:
        return yaml.safe_load(f.read())


def parse_patterns(
    patterns_spec: str, ignore_patterns_spec: str, *, separator: str = ";"
) -> tuple[list[str], list[str]]:
    """Parses pattern argument specs and returns a two-tuple of
    (patterns, ignore_patterns).
    """
    patterns = patterns_spec.split(separator)
    ignore_patterns = ignore_patterns_spec.split(separator)
    if ignore_patterns == [""]:
        ignore_patterns = []
    return patterns, ignore_patterns


def schedule_tricks(observer: BaseObserver, tricks: list[dict], pathname: str, *, recursive: bool) -> None:
    """Schedules tricks with the specified observer and for the given watch
    path.

    :param observer:
        The observer thread into which to schedule the trick and watch.
    :param tricks:
        A list of tricks.
    :param pathname:
        A path name which should be watched.
    :param recursive:
        ``True`` if recursive; ``False`` otherwise.
    """
    for trick in tricks:
        for name, value in trick.items():
            trick_cls = load_class(name)
            handler = trick_cls(**value)
            trick_pathname = getattr(handler, "source_directory", None) or pathname
            observer.schedule(handler, trick_pathname, recursive=recursive)
