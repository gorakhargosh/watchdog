#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import subprocess

from watchdog.utils import echo, has_attribute
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
    def on_any_event(self, event):
        pass

    @echo.echo
    def on_modified(self, event):
        pass

    @echo.echo
    def on_deleted(self, event):
        pass

    @echo.echo
    def on_created(self, event):
        pass

    @echo.echo
    def on_moved(self, event):
        pass


class ShellCommandTrick(Trick):
    """Execeutes shell commands in response to matched events."""
    def __init__(self, shell_command=None, patterns=None, ignore_patterns=None, ignore_directories=False):
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
        subprocess.Popen(command, shell=True)
