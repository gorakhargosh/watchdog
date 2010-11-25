#!/usr/bin/env python
# -*- coding: utf-8 -*-
# watchmedo.py - Reads a tricks.yaml file and executes all the tricks.
#
# Copyright (C) 2010 Gora Khargosh <gora.khargosh@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


import os
import sys
import yaml
import time
import uuid
import logging

from os.path import exists as path_exists, dirname, join as path_join, abspath, realpath, pathsep
from argh import arg, alias, ArghParser
from watchdog import Observer, VERSION_STRING
from watchdog.utils import read_text_file, load_class
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


logging.basicConfig(level=logging.DEBUG)


CURRENT_DIR_PATH = abspath(realpath(os.getcwd()))
DEFAULT_TRICKS_FILE_NAME = 'tricks.yaml'
DEFAULT_TRICKS_FILE_PATH = path_join(CURRENT_DIR_PATH, DEFAULT_TRICKS_FILE_NAME)

CONFIG_KEY_TRICKS = 'tricks'
CONFIG_KEY_PYTHON_PATH = 'python-path'

def path_split(path_spec, separator=pathsep):
    """Splits a path specification separated by an OS-dependent separator
    (: on Unix and ; on Windows, for examples)."""
    return list(path_spec.split(separator))

def add_to_sys_path(paths, index=0):
    """Adds specified paths at specified index into the sys.path list."""
    for path in paths[::-1]:
        sys.path.insert(index, path)

def load_config(tricks_file):
    """Loads the YAML configuration from the specified file."""
    content = read_text_file(tricks_file)
    config = yaml.load(content)
    return config


def check_trick_has_key(trick_name, trick, key):
    if key not in trick:
        logging.warn("Key `%s' not found for trick `%s'. Typo or missing?", key, trick_name)


def parse_patterns(patterns_spec, ignore_patterns_spec):
    """Parses pattern argument specs and returns a two-tuple of (patterns, ignore_patterns)."""
    separator = ';'
    patterns = patterns_spec.split(separator)
    ignore_patterns = ignore_patterns_spec.split(separator)
    if ignore_patterns == ['']:
        ignore_patterns = []
    return (patterns, ignore_patterns)


def observe_with(identifier, event_handler, paths, recursive):
    """Single observer given an identifier, event handler, and directories
    to watch."""
    o = Observer()
    o.schedule(identifier, event_handler, paths, recursive)
    o.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        o.unschedule(identifier)
        o.stop()
    o.join()


def schedule_tricks(observer, tricks, watch_path):
    """Schedules tricks with the specified observer and for the given watch
    path."""
    for trick in tricks:
        for trick_name, trick_value in trick.items():
            check_trick_has_key(trick_name, trick_value, 'kwargs')
            check_trick_has_key(trick_name, trick_value, 'args')

            trick_kwargs = trick_value.get('kwargs', {})
            trick_args = trick_value.get('args', ())

            TrickClass = load_class(trick_name)
            trick_event_handler = TrickClass(*trick_args, **trick_kwargs)

            unique_identifier = uuid.uuid1().hex
            observer.schedule(unique_identifier, trick_event_handler, [watch_path], recursive=True)


@alias('tricks')
@arg('files', nargs='*', help='perform tricks from given file')
@arg('--python-path', default='.', help='string of paths separated by %s to add to the python path' % pathsep)
def tricks_from(args):
    add_to_sys_path(path_split(args.python_path))
    observers = []
    for tricks_file in args.files:
        observer = Observer()

        if not path_exists(tricks_file):
            raise IOError("cannot find tricks file: %s" % tricks_file)

        config = load_config(tricks_file)

        if CONFIG_KEY_TRICKS not in config:
            raise KeyError("No `%s' key specified in %s." % (CONFIG_KEY_TRICKS, input_file))
        tricks = config[CONFIG_KEY_TRICKS]

        if CONFIG_KEY_PYTHON_PATH in config:
            add_to_sys_path(config[CONFIG_KEY_PYTHON_PATH])

        dir_path = abspath(realpath(dirname(tricks_file)))
        schedule_tricks(observer, tricks, dir_path)
        observer.start()
        observers.append(observer)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for o in observers:
            o.unschedule()
            o.stop()
    for o in observers:
        o.join()




@alias('generate-yaml')
@arg('trick_paths', nargs='*', help='Dotted paths for all the tricks you want to generate')
@arg('--python-path', default='.', help='string of paths separated by %s to add to the python path' % pathsep)
@arg('--append-to-file', default=None, help='appends the generated tricks YAML to a file; if not specified, prints to standard output')
@arg('--append', default=False, help='if --append-to-file is not specified, produces output for appending instead of a complete tricks yaml file.')
def tricks_generate_yaml(args):
    python_paths = path_split(args.python_path)
    add_to_sys_path(python_paths)
    output = StringIO()

    for trick_path in args.trick_paths:
        TrickClass = load_class(trick_path)
        output.write(TrickClass.generate_yaml())

    content = output.getvalue()
    output.close()

    header = yaml.dump({CONFIG_KEY_PYTHON_PATH: python_paths}) + "%s:\n" % CONFIG_KEY_TRICKS
    if args.append_to_file is None:
        # Output to standard output.
        if not args.append:
            content = header + content
        sys.stdout.write(content)
    else:
        if not path_exists(args.append_to_file):
            content = header + content
        output = open(args.append_to_file, 'ab')
        output.write(content)
        output.close()


@arg('directories', nargs='*', default='.', help='directories to watch.')
@arg('--patterns', default='*', help='matches event paths with these patterns (separated by ;).')
@arg('--ignore-patterns', default='', help='ignores event paths with these patterns (separated by ;).')
@arg('--ignore-directories', default=False, help='ignores events for directories')
@arg('--recursive', default=False, help='monitors the directories recursively')
def log(args):
    from watchdog.tricks import LoggerTrick
    patterns, ignore_patterns = parse_patterns(args.patterns, args.ignore_patterns)
    event_handler = LoggerTrick(patterns=patterns,
                                ignore_patterns=ignore_patterns,
                                ignore_directories=args.ignore_directories)
    observe_with('logger', event_handler, args.directories, args.recursive)


@alias('shell-command')
@arg('command', nargs='*', default=None, help='command that will be executed by the shell in reaction to matched events')
@arg('--watch-directories', default='.', help='directories to watch (separated by %s)' % pathsep)
@arg('--patterns', default='*', help='matches event paths with these patterns (separated by ;).')
@arg('--ignore-patterns', default='', help='ignores event paths with these patterns (separated by ;).')
@arg('--ignore-directories', default=False, help='ignores events for directories')
@arg('--recursive', default=False, help='monitors the directories recursively')
def shell_command(args):
    from watchdog.tricks import ShellCommandTrick

    if not args.command:
        args.command = None
    else:
        args.command = args.command[0]

    patterns, ignore_patterns = parse_patterns(args.patterns, args.ignore_patterns)
    watch_directories = path_split(args.watch_directories)
    event_handler = ShellCommandTrick(shell_command=args.command,
                                      patterns=patterns,
                                      ignore_patterns=ignore_patterns,
                                      ignore_directories=args.ignore_directories)
    observe_with('shell-command', event_handler, watch_directories, args.recursive)


parser = ArghParser()
parser.add_commands([tricks_from,
                     tricks_generate_yaml,
                     log,
                     shell_command])
parser.add_argument('--version', action='version', version='%(prog)s ' + VERSION_STRING)


def main():
    """Entry-point function."""
    parser.dispatch()


if __name__ == '__main__':
    main()

