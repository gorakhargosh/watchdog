/**
 * _watchdog_fsevents.c: Low-level FSEvents Python/C API.
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

#include "_watchdog_fsevents.h"

/**
 * Module documentation.
 */
PyDoc_STRVAR(watchdog_fsevents_module__doc__,
        "Low-level FSEvents Python/C API.");


PyDoc_STRVAR(watchdog_fsevents_read_events__doc__,
        MODULE_NAME ".read_events(emitter_thread) -> None\n\
Blocking function that runs an event loop associated with an emitter thread.\n\
\n:param emitter_thread:\n\
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
 * Adds all the _watchdog_fsevents module attributes and is meant only to be
 * called within the module initialization function.
 *
 * :param module:
 *     The module to which attributes will be added.
 * :type module:
 *     A pointer to a Python object representing a module.
 *
 * Attributes:
 * * __version__: tuple denoting the version number of the module.
 * * VERSION_INFO: tuple denoting the version number of the module.
 * * VERSION_STRING: string denoting the version number of the module.
 * * VERSION_MAJOR: major version
 * * VERSION_MINOR: minor version
 * * VERSION_BUILD: build version
 */
static void
Watchdog_AddModuleAttributes(PyObject *module)
{
    PyObject *version_tuple = Py_BuildValue("(iii)",
                                             WATCHDOG_VERSION_MAJOR,
                                             WATCHDOG_VERSION_MINOR,
                                             WATCHDOG_VERSION_BUILD);

    PyModule_AddIntConstant(module,
                            MODULE_CONSTANT_NAME_POLLIN,
                            kCFFileDescriptorReadCallBack);
    PyModule_AddIntConstant(module,
                            MODULE_CONSTANT_NAME_POLLOUT,
                            kCFFileDescriptorWriteCallBack);
    /* Version tuple */
    PyModule_AddObject(module,
                       MODULE_ATTRIBUTE_NAME_VERSION,
                       version_tuple);
    PyModule_AddObject(module,
                       MODULE_ATTRIBUTE_NAME_VERSION_INFO,
                       version_tuple);
    /* Version string */
    PyModule_AddObject(module,
                       MODULE_ATTRIBUTE_NAME_VERSION_STRING,
                       Py_BuildValue("s",
                                     WATCHDOG_VERSION_STRING));
    /* major version */
    PyModule_AddIntConstant(module,
                            MODULE_CONSTANT_NAME_VERSION_MAJOR,
                            WATCHDOG_VERSION_MAJOR);
    /* minor version */
    PyModule_AddIntConstant(module,
                            MODULE_CONSTANT_NAME_VERSION_MINOR,
                            WATCHDOG_VERSION_MINOR);
    /* build version */
    PyModule_AddIntConstant(module,
                            MODULE_CONSTANT_NAME_VERSION_BUILD,
                            WATCHDOG_VERSION_BUILD);
}


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
    Watchdog_AddModuleAttributes(module);
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
        Watchdog_AddModuleAttributes(module);
        Watchdog_FSEvents_Init();

        return module;
    }
#endif /* PY_MAJOR_VERSION >= 3 */
