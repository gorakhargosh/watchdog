/**
 * _watchdog_fsevents.h: Common macros and type declarations.
 *
 * Copyright (C) 2009, 2010 Malthe Borch <mborch@gmail.com>
 * Copyright (C) 2010 Gora Khargosh <gora.khargosh@gmail.com>
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#ifndef _WATCHDOG_FSEVENTS_H_
#define _WATCHDOG_FSEVENTS_H_ 1

#include "Python.h"
#include <stdlib.h>
#include <signal.h>
#include <limits.h>
#include <CoreFoundation/CoreFoundation.h>
#include <CoreServices/CoreServices.h>

/**
 * Py_ssize_t type for Python versions that don't define it.
 */
#if PY_VERSION_HEX < 0x02050000 && !defined(PY_SSIZE_T_MIN)
typedef int Py_ssize_t;
#define PY_SSIZE_T_MAX INT_MAX
#define PY_SSIZE_T_MIN INT_MIN
#endif /* PY_VERSION_HEX && !PY_SSIZE_T_MIN */

/**
 * Dictionary that maps an observer thread to a CFRunLoop.
 * Defined in ``_watchdog_data.c``
 */
extern PyObject *g__runloop_for_observer;

/**
 * Dictionary that maps an ObservedWatch to a FSEvent stream.
 * Defined in ``_watchdog_data.c``
 */
extern PyObject *g__stream_for_watch;

/**
 * Error messages.
 */
#define ERROR_MESSAGE_CANNOT_CALL_CALLBACK "Cannot call callback function."

#define MODULE_NAME "_watchdog_fsevents"
#define MODULE_CONSTANT_NAME_POLLIN "POLLIN"
#define MODULE_CONSTANT_NAME_POLLOUT "POLLOUT"

/**
 * File system event stream meta information structure.
 */
typedef struct _FSEventStreamInfo
{
    /**
     * Callback called when an event is triggered with the event paths and masks
     * as arguments.
     */
    PyObject *callback_event_handler;

    /**
     * Event stream.
     */
    FSEventStreamRef stream;

    /**
     * Loop associated with the event stream.
     */
    CFRunLoopRef loop;

    /**
     * Python thread state.
     */
    PyThreadState *thread_state;
} FSEventStreamInfo;

/**
 * Macro that forces returning NULL if given argument is NULL.
 */
#define RETURN_NULL_IF_NULL(o)                  \
    do                                          \
        {                                       \
            if (NULL == (o)) { return NULL; }   \
        }                                       \
    while(0)

/**
 * Macro that forces returning NULL if given argument is true.
 */
#define RETURN_NULL_IF(c)                       \
    do                                          \
        {                                       \
            if ((c)) { return NULL; }           \
        }                                       \
    while(0)

/**
 * Macro that forces returning NULL if given argument is false.
 */
#define RETURN_NULL_IF_NOT(c)                   \
    do                                          \
        {                                       \
            if (!(c)) { return NULL; }          \
        }                                       \
    while(0)

/**
 * Macro that forces returning if given argument is true.
 */
#define RETURN_IF(c)                            \
    do                                          \
        {                                       \
            if ((c)) { return; }                \
        }                                       \
    while(0)

/**
 * Macro that forces returning if given argument is false.
 */
#define RETURN_IF_NOT(c)                        \
    do                                          \
        {                                       \
            if (!(c)) { return; }               \
        }                                       \
    while(0)

#define FS_EVENT_STREAM_LATENCY (0.01)

/* CFRunLoopForObserver functions. */
CFRunLoopRef
CFRunLoopForObserver_GetItem(PyObject *observer_thread);
CFRunLoopRef
CFRunLoopForObserver_GetItemOrDefault(PyObject *observer_thread);
PyObject *
CFRunLoopForObserver_SetItem(PyObject *observer_thread, CFRunLoopRef runloop);
int
CFRunLoopForObserver_DelItem(PyObject *observer_thread);
int
CFRunLoopForObserver_Contains(PyObject *observer_thread);

/* StreamForWatch functions. */
PyObject *
StreamForWatch_SetItem(PyObject *watch, FSEventStreamRef stream);
FSEventStreamRef
StreamForWatch_GetItem(PyObject *watch);
FSEventStreamRef
StreamForWatch_PopItem(PyObject *watch);
int
StreamForWatch_Contains(PyObject *watch);

/* Miscellaneous. */
CFMutableArrayRef
CFMutableArray_FromStringList(PyObject *py_string_list);
FSEventStreamRef
FSEventStream_Create(FSEventStreamInfo *stream_info, PyObject *py_path_list);

void
event_stream_handler(FSEventStreamRef stream,
                     FSEventStreamInfo *stream_info,
                     const int num_events,
                     const char * const event_paths[],
                     const FSEventStreamEventFlags *event_masks,
                     const uint64_t *event_ids);

#endif /* _WATCHDOG_FSEVENTS_H_ */

