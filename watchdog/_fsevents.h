/**
 * Common macros and type declarations.
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

#endif /* _WATCHDOG_FSEVENTS_H_ */
