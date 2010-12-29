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


#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */


/**
 * Py_ssize_t type for Python versions that don't define it.
 */
#if PY_VERSION_HEX < 0x02050000 && !defined(PY_SSIZE_T_MIN)
typedef int Py_ssize_t;
#define PY_SSIZE_T_MAX INT_MAX
#define PY_SSIZE_T_MIN INT_MIN
#endif /* PY_VERSION_HEX && !PY_SSIZE_T_MIN */

/**
 * Error messages.
 */
#define ERROR_MESSAGE_CANNOT_CALL_CALLBACK "Cannot call callback function."
#define ERROR_MESSAGE_CANNOT_START_EVENT_STREAM "Cannot start event stream."

#define MODULE_NAME "_watchdog_fsevents"
#define MODULE_CONSTANT_NAME_POLLIN "POLLIN"
#define MODULE_CONSTANT_NAME_POLLOUT "POLLOUT"
#define MODULE_ATTRIBUTE_NAME_VERSION "__version__"

/**
 * An information structure that is passed to the callback function registered
 * with FSEventsStreamCreate.
 */
typedef struct _StreamCallbackInfo
{
    /**
     * Python callback called when an event is triggered with the event paths
     * and flags as arguments.
     */
    PyObject *callback;

    /**
     * Event stream.
     */
    FSEventStreamRef stream;

    /**
     * CFRunLoop associated with the event stream.
     */
    CFRunLoopRef runloop;

    /**
     * Python thread state.
     */
    PyThreadState *thread_state;
} StreamCallbackInfo;

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

/* Initialization. */
void
Watchdog_FSEvents_Init(void);


/* CFRunLoopForEmitter global dict functions. */
CFRunLoopRef
Watchdog_CFRunLoopForEmitter_GetItem(PyObject *emitter_thread);
CFRunLoopRef
Watchdog_CFRunLoopForEmitter_GetItemOrDefault(PyObject *emitter_thread);
int
Watchdog_CFRunLoopForEmitter_SetItem(PyObject *emitter_thread,
                                     CFRunLoopRef runloop);
int
Watchdog_CFRunLoopForEmitter_DelItem(PyObject *emitter_thread);
int
Watchdog_CFRunLoopForEmitter_Contains(PyObject *emitter_thread);

/* StreamForWatch global dict functions. */
int
Watchdog_StreamForWatch_SetItem(PyObject *watch, FSEventStreamRef stream);
FSEventStreamRef
Watchdog_StreamForWatch_GetItem(PyObject *watch);
FSEventStreamRef
Watchdog_StreamForWatch_PopItem(PyObject *watch);
int
Watchdog_StreamForWatch_Contains(PyObject *watch);

/* Miscellaneous. */
FSEventStreamRef
Watchdog_FSEventStream_Create(StreamCallbackInfo *stream_callback_info,
                              PyObject *py_path_list);


#ifdef __cplusplus
} /* extern "C" { */
#endif /* __cplusplus */


#endif /* _WATCHDOG_FSEVENTS_H_ */

