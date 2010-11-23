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

from watchdog.events import PatternMatchingEventHandler
from watchdog.utils import filter_paths

import logging
#logging.basicConfig(level=logging.DEBUG)


class Trick(PatternMatchingEventHandler):
    """Your tricks should subclass this class."""
    def on_any_event(self, event):
        self.do(event)

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

    def do(self, event):
        raise NotImplementedError('Please implement this method.')



class LoggerTrick(Trick):
    def do(self, event):
        logging.info(event)


