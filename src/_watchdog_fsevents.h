/**
 * _watchdog_fsevents.h: Common macros and type declarations.
 *
 * Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
 * Copyright 2012 Google, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */


#ifndef _WATCHDOG_FSEVENTS_H_
#define _WATCHDOG_FSEVENTS_H_ 1

#include <Python.h>
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
 * Destructor call for PyCapsule API when compiling against Python 3
 */
#if PY_MAJOR_VERSION >= 3
static void watchdog_pycapsule_destructor(PyObject *ptr);
#endif

/**
 * Error messages.
 */
#define ERROR_MESSAGE_CANNOT_CALL_CALLBACK "Cannot call callback function."
#define ERROR_MESSAGE_CANNOT_START_EVENT_STREAM "Cannot start event stream."

#define MODULE_NAME "_watchdog_fsevents"
#define MODULE_CONSTANT_NAME_POLLIN "POLLIN"
#define MODULE_CONSTANT_NAME_POLLOUT "POLLOUT"
#define MODULE_CONSTANT_NAME_VERSION_MAJOR "VERSION_MAJOR"
#define MODULE_CONSTANT_NAME_VERSION_MINOR "VERSION_MINOR"
#define MODULE_CONSTANT_NAME_VERSION_BUILD "VERSION_BUILD"
#define MODULE_ATTRIBUTE_NAME_VERSION "__version__"
#define MODULE_ATTRIBUTE_NAME_VERSION_INFO "VERSION_INFO"
#define MODULE_ATTRIBUTE_NAME_VERSION_STRING "VERSION_STRING"

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
 * Macro that forces returning NULL from the caller function if given argument
 * is NULL.
 */
#define RETURN_NULL_IF_NULL(o)                  \
    do                                          \
        {                                       \
            if (NULL == (o)) { return NULL; }   \
        }                                       \
    while(0)

/**
 * Macro that forces returning NULL from the caller function if given argument
 * is truthy.
 */
#define RETURN_NULL_IF(c)                       \
    do                                          \
        {                                       \
            if ((c)) { return NULL; }           \
        }                                       \
    while(0)

/**
 * Macro that forces returning NULL from the caller function if given argument
 * is falsy.
 */
#define RETURN_NULL_IF_NOT(c)                   \
    do                                          \
        {                                       \
            if (!(c)) { return NULL; }          \
        }                                       \
    while(0)

/**
 * Macro that forces returning from the caller function if given argument is
 * truthy.
 */
#define RETURN_IF(c)                            \
    do                                          \
        {                                       \
            if ((c)) { return; }                \
        }                                       \
    while(0)

/**
 * Macro that forces returning from the caller function if given argument is
 * falsy.
 */
#define RETURN_IF_NOT(c)                        \
    do                                          \
        {                                       \
            if (!(c)) { return; }               \
        }                                       \
    while(0)

/**
 * Latency (float) for the event streams registered with the FSEvents API.
 */
#define FS_EVENT_STREAM_LATENCY (0.01)

/* Initializes internal data structures when the module is initialized. */
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

