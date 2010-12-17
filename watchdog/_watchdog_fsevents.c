/**
 * _watchdog_fsevents.c: Low-level FSEvents Python API.
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

#include "_watchdog_fsevents.h"

/**
 * Module documentation.
 */
PyDoc_STRVAR(watchdog_fsevents_module__doc__,
        "Low-level FSEvents Python/C API.");

PyDoc_STRVAR(watchdog_fsevents_loop__doc__,
        "Runs an event loop associated with an observer thread.\n\n\
:param observer_thread:\n\
   The observer_thread for which the event loop will be run.\n");
static PyObject *
watchdog_fsevents_loop(PyObject *self, PyObject *args)
{
    /* Arguments */
    PyObject *observer_thread = NULL;

    RETURN_NULL_IF_NOT(PyArg_ParseTuple(args, "O:loop", &observer_thread));

    PyEval_InitThreads();

    /* Map the runloop to this observer thread if the
     * mapping doesn't already exist. */
    if (0 == CFRunLoopForObserver_Contains(observer_thread))
        {
            CFRunLoopRef runloop = CFRunLoopGetCurrent();
            RETURN_NULL_IF_NULL(CFRunLoopForObserver_SetItem(observer_thread,
                                                             runloop));
        }

    /* A runloop must exist before we can run it.
     * No timeout, block until events. */
    Py_BEGIN_ALLOW_THREADS;
    CFRunLoopRun();
    Py_END_ALLOW_THREADS;

    CFRunLoopForObserver_DelItem(observer_thread);

    RETURN_NULL_IF(PyErr_Occurred());

    Py_INCREF(Py_None);
    return Py_None;
}

PyDoc_STRVAR(watchdog_fsevents_schedule__doc__,
        "Schedules a watch.\n\n\
:param thread:\n\
    The observer thread.\n\
:param watch:\n\
    The watch to schedule.\n\
:param callback:\n\
    The callback function to call when an event occurs.\n\
:param paths:\n\
    A list of paths to monitor.\n");
static PyObject *
watchdog_fsevents_schedule(PyObject *self, PyObject *args)
{
    /* Arguments */
    PyObject *observer_thread = NULL;
    PyObject *watch = NULL;
    PyObject *paths = NULL;
    PyObject *callback = NULL;

    /* Other locals */
    FSEventStreamInfo *stream_info = NULL;
    FSEventStreamRef stream = NULL;
    CFRunLoopRef runloop = NULL;

    RETURN_NULL_IF_NOT(PyArg_ParseTuple(args,
                                        "OOOO:schedule",
                                        &observer_thread,
                                        &watch,
                                        &callback,
                                        &paths));

    /* Stream must not already be scheduled. */
    RETURN_NULL_IF(1 == StreamForWatch_Contains(watch));

    /* Create the event stream. */
    stream_info = PyMem_New(FSEventStreamInfo, 1);
    stream = FSEventStream_Create(stream_info, paths);

    RETURN_NULL_IF_NULL(stream);
    RETURN_NULL_IF_NULL(StreamForWatch_SetItem(watch, stream));

    runloop = CFRunLoopForObserver_GetItemOrDefault(observer_thread);
    FSEventStreamScheduleWithRunLoop(stream, runloop, kCFRunLoopDefaultMode);

    /* Set stream info for callback. */
    stream_info->callback_event_handler = callback;
    stream_info->stream = stream;
    stream_info->loop = runloop;
    stream_info->thread_state = PyThreadState_Get();
    Py_INCREF(callback);

    /* Start event streams. */
    if (!FSEventStreamStart(stream))
        {
            FSEventStreamInvalidate(stream);
            FSEventStreamRelease(stream);
            return NULL;
        }

    Py_INCREF(Py_None);
    return Py_None;
}

PyDoc_STRVAR(watchdog_fsevents_unschedule__doc__,
        "Unschedules a watch.\n\n\
:param watch:\n\
    The watch to unschedule.\n");
static PyObject *
watchdog_fsevents_unschedule(PyObject *self, PyObject *watch)
{
    FSEventStreamRef stream = StreamForWatch_PopItem(watch);

    RETURN_NULL_IF_NULL(stream);

    FSEventStreamStop(stream);
    FSEventStreamInvalidate(stream);
    FSEventStreamRelease(stream);

    Py_INCREF(Py_None);
    return Py_None;
}

PyDoc_STRVAR(watchdog_fsevents_stop__doc__,
        "Stops running the event loop from the specified thread.\n\n\
:param thread:\n\
    The thread for which the event loop will be stopped.\n");
static PyObject *
watchdog_fsevents_stop(PyObject *self, PyObject *observer_thread)
{
    CFRunLoopRef runloop = CFRunLoopForObserver_GetItem(observer_thread);

    /* Stop runloop */
    if (runloop)
        {
            CFRunLoopStop(runloop);
        }

    Py_INCREF(Py_None);
    return Py_None;
}

/**
 * Module public API.
 */
static PyMethodDef _watchdog_fseventsmethods[] =
        { { "loop",
             watchdog_fsevents_loop,
             METH_VARARGS,
             watchdog_fsevents_loop__doc__ },
           { "stop",
             watchdog_fsevents_stop,
             METH_O,
             watchdog_fsevents_stop__doc__ },
           { "schedule",
             watchdog_fsevents_schedule,
             METH_VARARGS,
             watchdog_fsevents_schedule__doc__ },
           { "unschedule",
             watchdog_fsevents_unschedule,
             METH_O,
             watchdog_fsevents_unschedule__doc__ },
           { NULL, NULL, 0, NULL } };

/**
 * Initialize the _fsevents module.
 */
#if PY_MAJOR_VERSION < 3
void
init_watchdog_fsevents(void)
{
    PyObject *module = Py_InitModule3(MODULE_NAME,
                                      _watchdog_fseventsmethods,
                                      watchdog_fsevents_module__doc__);
    PyModule_AddIntConstant(module,
                            MODULE_CONSTANT_NAME_POLLIN,
                            kCFFileDescriptorReadCallBack);
    PyModule_AddIntConstant(module,
                            MODULE_CONSTANT_NAME_POLLOUT,
                            kCFFileDescriptorWriteCallBack);

    g__runloop_for_observer = PyDict_New();
    g__stream_for_watch = PyDict_New();
}
#else /* PY_MAJOR_VERSION >= 3 */
static struct PyModuleDef _watchdog_fseventsmodule =
    {
        PyModuleDef_HEAD_INIT,
        MODULE_NAME,
        watchdog_fsevents_module__doc__,
        -1,
        _watchdog_fseventsmethods
    };
PyMODINIT_FUNC
PyInit__watchdog_fsevents(void)
    {
        PyObject *module = PyModule_Create(&_watchdog_fseventsmodule);
        PyModule_AddIntConstant(module,
                MODULE_CONSTANT_NAME_POLLIN,
                kCFFileDescriptorReadCallBack);
        PyModule_AddIntConstant(module,
                MODULE_CONSTANT_NAME_POLLOUT,
                kCFFileDescriptorWriteCallBack);

        g__runloop_for_observer = PyDict_New();
        g__stream_for_watch = PyDict_New();

        return module;
    }
#endif /* PY_MAJOR_VERSION >= 3 */
