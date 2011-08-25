#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
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
:author: Yesudeep Mangalapilly <yesudeep@gmail.com>
:synopsis: ``watchmedo`` shell script utility.
"""

import os.path
import sys
import yaml
import time
import logging

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from argh import arg, alias, ArghParser

from watchdog.version import VERSION_STRING
from watchdog.utils import\
    read_text_file,\
    load_class
from pathtools.path import absolute_path, parent_dir_path


logging.basicConfig(level=logging.DEBUG)

CURRENT_DIR = absolute_path(os.getcwd())
DEFAULT_TRICKS_FILE_NAME = 'tricks.yaml'
DEFAULT_TRICKS_FILE_PATH = os.path.join(CURRENT_DIR, DEFAULT_TRICKS_FILE_NAME)
CONFIG_KEY_TRICKS = 'tricks'
CONFIG_KEY_PYTHON_PATH = 'python-path'


def path_split(pathname_spec, separator=os.path.sep):
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


def load_config(tricks_file_pathname):
    """
    Loads the YAML configuration from the specified file.

    :param tricks_file_path:
        The path to the tricks configuration file.
    :returns:
        A dictionary of configuration information.
    """
    content = read_text_file(tricks_file_pathname)
    config = yaml.load(content)
    return config


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
    except KeyboardInterrupt:
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
        for name, value in trick.items():
            TrickClass = load_class(name)
            handler = TrickClass(**value)
            trick_pathname = absolute_path(getattr(handler, 'source_directory', None) or pathname)
            observer.schedule(handler, trick_pathname, recursive)


@alias('tricks')
@arg('files',
     nargs='*',
     help='perform tricks from given file')
@arg('--python-path',
     default='.',
     help='paths separated by %s to add to the python path' % os.path.sep)
@arg('--interval',
     '--timeout',
     dest='timeout',
     default=1.0,
     help='use this as the polling interval/blocking timeout')
@arg('--recursive',
     default=True,
     help='recursively monitor paths')
def tricks_from(args):
    """
    Subcommand to execute tricks from a tricks configuration file.

    :param args:
        Command line argument options.
    """
    from watchdog.observers import Observer

    add_to_sys_path(path_split(args.python_path))
    observers = []
    for tricks_file in args.files:
        observer = Observer(timeout=args.timeout)

        if not os.path.exists(tricks_file):
            raise IOError("cannot find tricks file: %s" % tricks_file)

        config = load_config(tricks_file)

        try:
            tricks = config[CONFIG_KEY_TRICKS]
        except KeyError:
            raise KeyError("No `%s' key specified in %s." % (
                            CONFIG_KEY_TRICKS, tricks_file))

        if CONFIG_KEY_PYTHON_PATH in config:
            add_to_sys_path(config[CONFIG_KEY_PYTHON_PATH])

        dir_path = parent_dir_path(tricks_file)
        schedule_tricks(observer, tricks, dir_path, args.recursive)
        observer.start()
        observers.append(observer)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for o in observers:
            o.unschedule_all()
            o.stop()
    for o in observers:
        o.join()


@alias('generate-tricks-yaml')
@arg('trick_paths',
     nargs='*',
     help='Dotted paths for all the tricks you want to generate')
@arg('--python-path',
     default='.',
     help='paths separated by %s to add to the python path' % os.path.sep)
@arg('--append-to-file',
     default=None,
     help='appends the generated tricks YAML to a file; \
if not specified, prints to standard output')
@arg('-a',
     '--append-only',
     dest='append_only',
     default=False,
     help='if --append-to-file is not specified, produces output for \
appending instead of a complete tricks yaml file.')
def tricks_generate_yaml(args):
    """
    Subcommand to generate Yaml configuration for tricks named on the command
    line.

    :param args:
        Command line argument options.
    """
    python_paths = path_split(args.python_path)
    add_to_sys_path(python_paths)
    output = StringIO()

    for trick_path in args.trick_paths:
        TrickClass = load_class(trick_path)
        output.write(TrickClass.generate_yaml())

    content = output.getvalue()
    output.close()

    header = yaml.dump({CONFIG_KEY_PYTHON_PATH: python_paths})
    header += "%s:\n" % CONFIG_KEY_TRICKS
    if args.append_to_file is None:
        # Output to standard output.
        if not args.append_only:
            content = header + content
        sys.stdout.write(content)
    else:
        if not os.path.exists(args.append_to_file):
            content = header + content
        output = open(args.append_to_file, 'ab')
        output.write(content)
        output.close()


@arg('directories',
     nargs='*',
     default='.',
     help='directories to watch.')
@arg('-p',
     '--pattern',
     '--patterns',
     dest='patterns',
     default='*',
     help='matches event paths with these patterns (separated by ;).')
@arg('-i',
     '--ignore-pattern',
     '--ignore-patterns',
     dest='ignore_patterns',
     default='',
     help='ignores event paths with these patterns (separated by ;).')
@arg('-D',
     '--ignore-directories',
     dest='ignore_directories',
     default=False,
     help='ignores events for directories')
@arg('-R',
     '--recursive',
     dest='recursive',
     default=False,
     help='monitors the directories recursively')
@arg('--interval',
     '--timeout',
     dest='timeout',
     default=1.0,
     help='use this as the polling interval/blocking timeout')
@arg('--trace',
     default=False,
     help='dumps complete dispatching trace')
@arg('--debug-force-polling',
     default=False,
     help='[debug] forces polling')
@arg('--debug-force-kqueue',
     default=False,
     help='[debug] forces BSD kqueue(2)')
@arg('--debug-force-winapi',
     default=False,
     help='[debug] forces Windows API')
@arg('--debug-force-winapi-async',
     default=False,
     help='[debug] forces Windows API + I/O completion')
@arg('--debug-force-fsevents',
     default=False,
     help='[debug] forces Mac OS X FSEvents')
@arg('--debug-force-inotify',
     default=False,
     help='[debug] forces Linux inotify(7)')
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


@arg('directories',
     nargs='*',
     default='.',
     help='directories to watch')
@arg('-c',
     '--command',
     dest='command',
     default=None,
     help='''shell command executed in response to matching events.
These interpolation variables are available to your command string::

    ${watch_src_path}    - event source path;
    ${watch_dest_path}   - event destination path (for moved events);
    ${watch_event_type}  - event type;
    ${watch_object}      - ``file`` or ``directory``

Note::
    Please ensure you do not use double quotes (") to quote
    your command string. That will force your shell to
    interpolate before the command is processed by this
    subcommand.

Example option usage::

    --command='echo "${watch_src_path}"'
''')
@arg('-p',
     '--pattern',
     '--patterns',
     dest='patterns',
     default='*',
     help='matches event paths with these patterns (separated by ;).')
@arg('-i',
     '--ignore-pattern',
     '--ignore-patterns',
     dest='ignore_patterns',
     default='',
     help='ignores event paths with these patterns (separated by ;).')
@arg('-D',
     '--ignore-directories',
     dest='ignore_directories',
     default=False,
     help='ignores events for directories')
@arg('-R',
     '--recursive',
     dest='recursive',
     default=False,
     help='monitors the directories recursively')
@arg('--interval',
     '--timeout',
     dest='timeout',
     default=1.0,
     help='use this as the polling interval/blocking timeout')
@arg('-w', '--wait',
     dest='wait_for_process',
     action='store_true',
     default=False,
     help="wait for process to finish to avoid multiple simultaneous instances")
def shell_command(args):
    """
    Subcommand to execute shell commands in response to file system events.

    :param args:
        Command line argument options.
    """
    from watchdog.observers import Observer
    from watchdog.tricks import ShellCommandTrick

    if not args.command:
        args.command = None

    patterns, ignore_patterns = parse_patterns(args.patterns,
                                               args.ignore_patterns)
    handler = ShellCommandTrick(shell_command=args.command,
                                patterns=patterns,
                                ignore_patterns=ignore_patterns,
                                ignore_directories=args.ignore_directories,
                                wait_for_process=args.wait_for_process)
    observer = Observer(timeout=args.timeout)
    observe_with(observer, handler, args.directories, args.recursive)


epilog = """Copyright (C) 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>.

Licensed under the terms of the Apache license, version 2.0. Please see
LICENSE in the source code for more information."""

parser = ArghParser(epilog=epilog)
parser.add_commands([tricks_from,
                     tricks_generate_yaml,
                     log,
                     shell_command])
parser.add_argument('--version',
                    action='version',
                    version='%(prog)s ' + VERSION_STRING)


def main():
    """Entry-point function."""
    parser.dispatch()


if __name__ == '__main__':
    main()
