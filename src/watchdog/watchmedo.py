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

import errno
import os
import os.path
import sys
import yaml
import time
import logging
from io import StringIO

from argh import arg, aliases, ArghParser, expects_obj
from watchdog.version import VERSION_STRING
from watchdog.utils import WatchdogShutdown, load_class
from watchdog._watchmedo import path_split, add_to_sys_path, \
        parse_patterns, observe_with, schedule_tricks
from watchdog import _watchmedo


logging.basicConfig(level=logging.INFO)

CONFIG_KEY_TRICKS = 'tricks'
CONFIG_KEY_PYTHON_PATH = 'python-path'


def load_config(tricks_file_pathname):
    """
    Loads the YAML configuration from the specified file.

    :param tricks_file_path:
        The path to the tricks configuration file.
    :returns:
        A dictionary of configuration information.
    """
    with open(tricks_file_pathname, 'rb') as f:
        return yaml.safe_load(f.read())



@aliases('tricks')
@arg('files',
     nargs='*',
     help='perform tricks from given file')
@arg('--python-path',
     default='.',
     help='paths separated by %s to add to the python path' % os.pathsep)
@arg('--interval',
     '--timeout',
     dest='timeout',
     default=1.0,
     help='use this as the polling interval/blocking timeout (in seconds)')
@arg('--recursive',
     default=True,
     help='recursively monitor paths')
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
@expects_obj
def tricks_from(args):
    """
    Subcommand to execute tricks from a tricks configuration file.

    :param args:
        Command line argument options.
    """
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

    add_to_sys_path(path_split(args.python_path))
    observers = []
    for tricks_file in args.files:
        observer = Observer(timeout=args.timeout)

        if not os.path.exists(tricks_file):
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT), tricks_file)

        config = load_config(tricks_file)

        try:
            tricks = config[CONFIG_KEY_TRICKS]
        except KeyError:
            raise KeyError("No %r key specified in %s." % (
                           CONFIG_KEY_TRICKS, tricks_file))

        if CONFIG_KEY_PYTHON_PATH in config:
            add_to_sys_path(config[CONFIG_KEY_PYTHON_PATH])

        dir_path = os.path.dirname(tricks_file)
        if not dir_path:
            dir_path = os.path.relpath(os.getcwd())
        schedule_tricks(observer, tricks, dir_path, args.recursive)
        observer.start()
        observers.append(observer)

    try:
        while True:
            time.sleep(1)
    except WatchdogShutdown:
        for o in observers:
            o.unschedule_all()
            o.stop()
    for o in observers:
        o.join()


@aliases('generate-tricks-yaml')
@arg('trick_paths',
     nargs='*',
     help='Dotted paths for all the tricks you want to generate')
@arg('--python-path',
     default='.',
     help='paths separated by %s to add to the python path' % os.pathsep)
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
@expects_obj
def tricks_generate_yaml(args):
    return _watchmedo.tracks_generate_yaml(args)


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
@expects_obj
def log(args):
    return _watchmedo.log(args)


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
@arg('-W', '--drop',
     dest='drop_during_process',
     action='store_true',
     default=False,
     help="Ignore events that occur while command is still being executed "
          "to avoid multiple simultaneous instances")
@arg('--debug-force-polling',
     default=False,
     help='[debug] forces polling')
@expects_obj
def shell_command(args):
    return _watchmedo.shell_command(args)


@arg('command',
     help='''Long-running command to run in a subprocess.
''')
@arg('command_args',
     metavar='arg',
     nargs='*',
     help='''Command arguments.

Note: Use -- before the command arguments, otherwise watchmedo will
try to interpret them.
''')
@arg('-d',
     '--directory',
     dest='directories',
     metavar='directory',
     action='append',
     help='Directory to watch. Use another -d or --directory option '
          'for each directory.')
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
@arg('--signal',
     dest='signal',
     default='SIGINT',
     help='stop the subprocess with this signal (default SIGINT)')
@arg('--debug-force-polling',
     default=False,
     help='[debug] forces polling')
@arg('--kill-after',
     dest='kill_after',
     default=10.0,
     help='when stopping, kill the subprocess after the specified timeout '
          '(default 10)')
@expects_obj
def auto_restart(args):
    return _watchmedo.auto_restart(args)


epilog = """Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>.
Copyright 2012 Google, Inc & contributors.

Licensed under the terms of the Apache license, version 2.0. Please see
LICENSE in the source code for more information."""

parser = ArghParser(epilog=epilog)
parser.add_commands([tricks_from,
                     tricks_generate_yaml,
                     log,
                     shell_command,
                     auto_restart])
parser.add_argument('--version',
                    action='version',
                    version='%(prog)s ' + VERSION_STRING)


def main():
    """Entry-point function."""
    parser.dispatch()


if __name__ == '__main__':
    main()
