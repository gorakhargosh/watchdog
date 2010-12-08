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

"""
:module: watchdog.observers
:synopsis: Observer that picks a native implementation if available.
:author: Gora Khargosh <gora.khargosh@gmail.com>


Classes
=======
.. autoclass:: Observer
   :members:
   :show-inheritance:
   :inherited-members:

"""

from watchdog.observers.api import BaseObserver, DEFAULT_OBSERVER_TIMEOUT

try: # pragma: no cover
    from watchdog.observers.inotify import InotifyEmitter as Emitter
except ImportError: # pragma: no cover
    try: # pragma: no cover
        from watchdog.observers.fsevents import FSEventsEmitter as Emitter
    except ImportError: # pragma: no cover
        try: # pragma: no cover
            from watchdog.observers.kqueue import KqueueEmitter as Emitter
        except ImportError: # pragma: no cover
            try: # pragma: no cover
                from watchdog.observers.win32_async import AsyncWin32Emitter as Emitter
            except ImportError: # pragma: no cover
                try: # pragma: no cover
                    from watchdog.observers.win32 import Win32Emitter as Emitter
                except ImportError: # pragma: no cover
                    from watchdog.observers.polling import PollingEmitter as Emitter


class Observer(BaseObserver):
    """
    Observer thread that schedules watching directories and dispatches
    calls to event handlers.
    """
    def __init__(self, timeout=DEFAULT_OBSERVER_TIMEOUT, emitter_class=Emitter):
        BaseObserver.__init__(self, emitter_class=emitter_class, timeout=timeout)

