# -*- coding: utf-8 -*-
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

from watchdog.utils import has_attribute
from threading import Thread, Event as ThreadedEvent

class DaemonThread(Thread):
    def __init__(self, interval=1, *args, **kwargs):
        super(DaemonThread, self).__init__()
        if has_attribute(self, 'daemon'):
            self.daemon = True
        else:
            self.setDaemon(True)
        self.stopped = ThreadedEvent()
        self.interval = interval
        self.args = args
        self.kwargs = kwargs

    @property
    def is_stopped(self):
        if has_attribute(self.stopped, 'is_set'):
            return self.stopped.is_set()
        else:
            return self.stopped.isSet()

    def on_stopping(self):
        """Implement this instead of Thread.stop(), it calls this method
        for you."""
        pass

    def stop(self):
        self.stopped.set()
        self.on_stopping()
