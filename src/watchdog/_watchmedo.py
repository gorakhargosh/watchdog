# coding: utf-8
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc & contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
:module: watchdog.watchmedo
:author: yesudeep@google.com (Yesudeep Mangalapilly)
:author: contact@tiger-222.fr (Mickaël Schoentgen)
:synopsis: ``watchmedo`` shell script utility.
"""

import os
import os.path
import sys
import time
import logging

from watchdog.utils import WatchdogShutdown, load_class


logging.basicConfig(level=logging.INFO)

CONFIG_KEY_TRICKS = 'tricks'
CONFIG_KEY_PYTHON_PATH = 'python-path'


def path_split(pathname_spec, separator=os.pathsep):
    """
    Splits a pathname specification separated by an OS-dependent separator.

    :param pathname_spec:
        The pathname specification.
    :param separator:
        (OS Dependent) `:` on Unix and `;` on Windows or user-specified.
    """
    return list(pathname_spec.split(separator))


def add_to_sys_path(pathnames, index=0):
    """
    Adds specified paths at specified index into the sys.path list.

    :param paths:
        A list of paths to add to the sys.path
    :param index:
        (Default 0) The index in the sys.path list where the paths will be
        added.
    """
    for pathname in pathnames[::-1]:
        sys.path.insert(index, pathname)


def parse_patterns(patterns_spec, ignore_patterns_spec, separator=';'):
    """
    Parses pattern argument specs and returns a two-tuple of
    (patterns, ignore_patterns).
    """
    patterns = patterns_spec.split(separator)
    ignore_patterns = ignore_patterns_spec.split(separator)
    if ignore_patterns == ['']:
        ignore_patterns = []
    return (patterns, ignore_patterns)


def observe_with(observer, event_handler, pathnames, recursive):
    """
    Single observer thread with a scheduled path and event handler.

    :param observer:
        The observer thread.
    :param event_handler:
        Event handler which will be called in response to file system events.
    :param pathnames:
        A list of pathnames to monitor.
    :param recursive:
        ``True`` if recursive; ``False`` otherwise.
    """
    for pathname in set(pathnames):
        observer.schedule(event_handler, pathname, recursive)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except WatchdogShutdown:
        observer.stop()
    observer.join()


def schedule_tricks(observer, tricks, pathname, recursive):
    """
    Schedules tricks with the specified observer and for the given watch
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
        for name, value in list(trick.items()):
            TrickClass = load_class(name)
            handler = TrickClass(**value)
            trick_pathname = getattr(handler, 'source_directory', None) or pathname
            observer.schedule(handler, trick_pathname, recursive)


def log(args):
    """
    Subcommand to log file system events to the console.

    :param args:
        Command line argument options.
    """
    from watchdog.utils import echo
    from watchdog.tricks import LoggerTrick

    if args.trace:
        echo.echo_class(LoggerTrick)

    patterns, ignore_patterns =\
        parse_patterns(args.patterns, args.ignore_patterns)
    handler = LoggerTrick(patterns=patterns,
                          ignore_patterns=ignore_patterns,
                          ignore_directories=args.ignore_directories)
    if args.debug_force_polling:
        from watchdog.observers.polling import PollingObserver as Observer
    elif args.debug_force_kqueue:
        from watchdog.observers.kqueue import KqueueObserver as Observer
    elif args.debug_force_winapi_async:
        from watchdog.observers.read_directory_changes_async import\
            WindowsApiAsyncObserver as Observer
    elif args.debug_force_winapi:
        from watchdog.observers.read_directory_changes import\
            WindowsApiObserver as Observer
    elif args.debug_force_inotify:
        from watchdog.observers.inotify import InotifyObserver as Observer
    elif args.debug_force_fsevents:
        from watchdog.observers.fsevents import FSEventsObserver as Observer
    else:
        # Automatically picks the most appropriate observer for the platform
        # on which it is running.
        from watchdog.observers import Observer
    observer = Observer(timeout=args.timeout)
    observe_with(observer, handler, args.directories, args.recursive)


def shell_command(args):
    """
    Subcommand to execute shell commands in response to file system events.

    :param args:
        Command line argument options.
    """
    from watchdog.tricks import ShellCommandTrick

    if not args.command:
        args.command = None

    if args.debug_force_polling:
        from watchdog.observers.polling import PollingObserver as Observer
    else:
        from watchdog.observers import Observer

    patterns, ignore_patterns = parse_patterns(args.patterns,
                                               args.ignore_patterns)
    handler = ShellCommandTrick(shell_command=args.command,
                                patterns=patterns,
                                ignore_patterns=ignore_patterns,
                                ignore_directories=args.ignore_directories,
                                wait_for_process=args.wait_for_process,
                                drop_during_process=args.drop_during_process)
    observer = Observer(timeout=args.timeout)
    observe_with(observer, handler, args.directories, args.recursive)


def auto_restart(args):
    """
    Subcommand to start a long-running subprocess and restart it
    on matched events.

    :param args:
        Command line argument options.
    """

    if args.debug_force_polling:
        from watchdog.observers.polling import PollingObserver as Observer
    else:
        from watchdog.observers import Observer

    from watchdog.tricks import AutoRestartTrick
    import signal

    if not args.directories:
        args.directories = ['.']

    # Allow either signal name or number.
    if args.signal.startswith("SIG"):
        stop_signal = getattr(signal, args.signal)
    else:
        stop_signal = int(args.signal)

    # Handle termination signals by raising a semantic exception which will
    # allow us to gracefully unwind and stop the observer
    termination_signals = {signal.SIGTERM, signal.SIGINT}

    def handler_termination_signal(_signum, _frame):
        # Neuter all signals so that we don't attempt a double shutdown
        for signum in termination_signals:
            signal.signal(signum, signal.SIG_IGN)
        raise WatchdogShutdown

    for signum in termination_signals:
        signal.signal(signum, handler_termination_signal)

    patterns, ignore_patterns = parse_patterns(args.patterns,
                                               args.ignore_patterns)
    command = [args.command]
    command.extend(args.command_args)
    handler = AutoRestartTrick(command=command,
                               patterns=patterns,
                               ignore_patterns=ignore_patterns,
                               ignore_directories=args.ignore_directories,
                               stop_signal=stop_signal,
                               kill_after=args.kill_after)
    handler.start()
    observer = Observer(timeout=args.timeout)
    try:
        observe_with(observer, handler, args.directories, args.recursive)
    except WatchdogShutdown:
        pass
    finally:
        handler.stop()
