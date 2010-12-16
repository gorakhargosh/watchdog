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
 * File system event stream meta information structure.
 */
typedef struct FSEventStreamInfo
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


#endif /* _WATCHDOG_FSEVENTS_H_ */

