/**
 * _watchdog_fsevents.c: Low-level FSEvents Python/C API.
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


PyDoc_STRVAR(watchdog_fsevents_read_events__doc__,
        MODULE_NAME ".read_events(emitter_thread) -> None\n\
Blocking function that runs an event loop associated with an emitter thread.\n\n\
:param emitter_thread:\n\
   The emitter thread for which the event loop will be run.\n");
static PyObject *
watchdog_fsevents_read_events(PyObject *self, PyObject *emitter_thread)
{
    /* Locals */
    CFRunLoopRef runloop = NULL;

    RETURN_NULL_IF_NULL(emitter_thread);

    PyEval_InitThreads();

    /* Map the runloop to this emitter thread if the
     * mapping doesn't already exist. */
    if (0 == Watchdog_CFRunLoopForEmitter_Contains(emitter_thread))
        {
            runloop = CFRunLoopGetCurrent();
            RETURN_NULL_IF(
                0 > Watchdog_CFRunLoopForEmitter_SetItem(emitter_thread,
                                                         runloop));
        }

    /* A runloop must exist before we can run it.
     * No timeout, block until events. */
    Py_BEGIN_ALLOW_THREADS;
    CFRunLoopRun();
    Py_END_ALLOW_THREADS;

    Watchdog_CFRunLoopForEmitter_DelItem(emitter_thread);

    RETURN_NULL_IF(PyErr_Occurred());

    Py_INCREF(Py_None);
    return Py_None;
}


PyDoc_STRVAR(watchdog_fsevents_add_watch__doc__,
        MODULE_NAME ".add_watch(emitter_thread, watch, callback, paths) -> None\
\nAdds a watch into the event loop for the given emitter thread.\n\n\
:param emitter_thread:\n\
    The emitter thread.\n\
:param watch:\n\
    The watch to add.\n\
:param callback:\n\
    The callback function to call when an event occurs.\n\n\
    Example::\n\n\
        def callback(paths, flags):\n\
            for path, flag in zip(paths, flags):\n\
                print(\"%s=%ul\" % (path, flag))\n\
:param paths:\n\
    A list of paths to monitor.\n");
static PyObject *
watchdog_fsevents_add_watch(PyObject *self, PyObject *args)
{
    /* Arguments */
    PyObject *emitter_thread = NULL;
    PyObject *watch = NULL;
    PyObject *paths = NULL;
    PyObject *callback = NULL;

    /* Locals */
    StreamCallbackInfo *stream_callback_info = NULL;
    FSEventStreamRef stream = NULL;
    CFRunLoopRef runloop = NULL;

    RETURN_NULL_IF_NULL(args);
    RETURN_NULL_IF_NOT(PyArg_ParseTuple(args,
                                        "OOOO:add_watch",
                                        &emitter_thread,
                                        &watch,
                                        &callback,
                                        &paths));

    /* Watch must not already be scheduled. */
    RETURN_NULL_IF(1 == Watchdog_StreamForWatch_Contains(watch));

    /* Create the event stream. */
    stream_callback_info = PyMem_New(StreamCallbackInfo, 1);
    stream = Watchdog_FSEventStream_Create(stream_callback_info, paths);

    RETURN_NULL_IF_NULL(stream);
    RETURN_NULL_IF(0 > Watchdog_StreamForWatch_SetItem(watch, stream));

    runloop = Watchdog_CFRunLoopForEmitter_GetItemOrDefault(emitter_thread);
    FSEventStreamScheduleWithRunLoop(stream, runloop, kCFRunLoopDefaultMode);

    /* Set stream info for callback. */
    stream_callback_info->callback = callback;
    stream_callback_info->stream = stream;
    stream_callback_info->runloop = runloop;
    stream_callback_info->thread_state = PyThreadState_Get();
    Py_INCREF(callback);

    /* Start event streams. */
    if (!FSEventStreamStart(stream))
        {
            FSEventStreamInvalidate(stream);
            FSEventStreamRelease(stream);
            /* We couldn't start the stream, so raise an exception. */
            PyErr_SetString(PyExc_ValueError,
                            ERROR_MESSAGE_CANNOT_START_EVENT_STREAM);
            return NULL;
        }

    Py_INCREF(Py_None);
    return Py_None;
}


PyDoc_STRVAR(watchdog_fsevents_remove_watch__doc__,
        MODULE_NAME ".remove_watch(watch) -> None\n\
Removes a watch from the event loop.\n\n\
:param watch:\n\
    The watch to remove.\n");
static PyObject *
watchdog_fsevents_remove_watch(PyObject *self, PyObject *watch)
{
    FSEventStreamRef stream = NULL;

    RETURN_NULL_IF_NULL(watch);
    stream = Watchdog_StreamForWatch_PopItem(watch);
    RETURN_NULL_IF_NULL(stream);

    FSEventStreamStop(stream);
    FSEventStreamInvalidate(stream);
    FSEventStreamRelease(stream);

    Py_INCREF(Py_None);
    return Py_None;
}


PyDoc_STRVAR(watchdog_fsevents_stop__doc__,
        MODULE_NAME ".stop(emitter_thread) -> None\n\
Stops running the event loop from the specified thread.\n\n\
:param emitter_thread:\n\
    The thread for which the event loop will be stopped.\n");
static PyObject *
watchdog_fsevents_stop(PyObject *self, PyObject *emitter_thread)
{
    CFRunLoopRef runloop = NULL;

    runloop = Watchdog_CFRunLoopForEmitter_GetItem(emitter_thread);

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
        { { "read_events",
             watchdog_fsevents_read_events,
             METH_O,
             watchdog_fsevents_read_events__doc__ },
           { "stop",
             watchdog_fsevents_stop,
             METH_O,
             watchdog_fsevents_stop__doc__ },
           { "add_watch",
             watchdog_fsevents_add_watch,
             METH_VARARGS,
             watchdog_fsevents_add_watch__doc__ },
           { "remove_watch",
             watchdog_fsevents_remove_watch,
             METH_O,
             watchdog_fsevents_remove_watch__doc__ },
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
    PyModule_AddObject(module,
                       MODULE_ATTRIBUTE_NAME_VERSION,
                       Py_BuildValue("(iii)",
                                     WATCHDOG_VERSION_MAJOR,
                                     WATCHDOG_VERSION_MINOR,
                                     WATCHDOG_VERSION_BUILD));

    Watchdog_FSEvents_Init();
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
        PyModule_AddObject(module,
                           MODULE_ATTRIBUTE_NAME_VERSION,
                           Py_BuildValue("(iii)",
                                         WATCHDOG_VERSION_MAJOR,
                                         WATCHDOG_VERSION_MINOR,
                                         WATCHDOG_VERSION_BUILD));

        Watchdog_FSEvents_Init();

        return module;
    }
#endif /* PY_MAJOR_VERSION >= 3 */
