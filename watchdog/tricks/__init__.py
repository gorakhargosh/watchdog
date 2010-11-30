# -*- coding: utf-8 -*-
# watchdog.tricks.__init__.py: tricks framework.
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

import subprocess

from watchdog.utils import echo, filter_paths, has_attribute
from watchdog.events import PatternMatchingEventHandler


class Trick(PatternMatchingEventHandler):
    """Your tricks should subclass this class."""

    @classmethod
    def generate_yaml(cls):
        context = dict(module_name=cls.__module__,
                       klass_name=cls.__name__)
        template_yaml = """- %(module_name)s.%(klass_name)s:
  args:
  - argument1
  - argument2
  kwargs:
    patterns:
    - "*.py"
    - "*.js"
    ignore_patterns:
    - "version.py"
    ignore_directories: false
"""
        return template_yaml % context


class LoggerTrick(Trick):
    """A simple trick that does only logs events."""
    @echo.echo
    def on_any_event(self, event):
        pass


class ShellCommandTrick(Trick):
    """Execeutes shell commands in response to matched events."""
    def __init__(self, shell_command=None, patterns=['*'], ignore_patterns=[], ignore_directories=False):
        super(ShellCommandTrick, self).__init__(patterns, ignore_patterns, ignore_directories)
        self.shell_command = shell_command

    def on_any_event(self, event):
        from string import Template
        if event.is_directory:
            object_type = 'directory'
        else:
            object_type = 'file'

        context = {
            'watch_src_path': event.src_path,
            'watch_dest_path': '',
            'watch_event_type': event.event_type,
            'watch_object': object_type,
            }

        if self.shell_command is None:
            if has_attribute(event, 'dest_path'):
                context.update({'dest_path': event.dest_path})
                command = 'echo "${watch_event_type} ${watch_object} from ${watch_src_path} to ${watch_dest_path}"'
            else:
                command = 'echo "${watch_event_type} ${watch_object} ${watch_src_path}"'
        else:
            if has_attribute(event, 'dest_path'):
                context.update({'watch_dest_path': event.dest_path})
            command = self.shell_command

        command = Template(command).safe_substitute(**context)
        p = subprocess.Popen(command, shell=True)


