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

static const char module__name__[] = "_watchdog_fsevents";

static const char MODULE_CONSTANT_NAME_POLLIN[] = "POLLIN";
static const char MODULE_CONSTANT_NAME_POLLOUT[] = "POLLOUT";

/**
 * Error messages.
 */
static const char CALLBACK_ERROR_MESSAGE[] = "Unable to call callback function.";

/**
 * Module documentation.
 */
PyDoc_STRVAR(watchdog_fsevents_module__doc__,
             "Low-level FSEvents interface.");

/**
 * Dictionary of all the event loops.
 */
PyObject *g__pydict_loops = NULL;

/**
 * Dictionary of all the event streams.
 */
PyObject *g__pydict_streams = NULL;

/**
 * Handles streamed events and calls the callback defined in Python code.
 *
 * @param stream       The stream of events.
 * @param info         Meta information about the stream of events.
 * @param num_events   Number of events.
 * @param event_paths  The paths on which events occurred.
 * @param event_masks  The masks for each of the paths in `event_paths'.
 * @param event_ids    Event identifiers.
 *
 * @synchronized()
 */
static void
event_stream_handler(FSEventStreamRef stream,
                     FSEventStreamInfo *stream_info,
                     const int num_events,
                     const char * const event_paths[],
                     const FSEventStreamEventFlags *event_masks,
                     const uint64_t *event_ids)
{
    PyThreadState *saved_thread_state = NULL;
    PyObject *event_path = NULL;
    PyObject *event_mask = NULL;
    PyObject *event_path_list = NULL;
    PyObject *event_mask_list = NULL;
    int i = 0;

    /* Acquire lock and save thread state. */
    PyEval_AcquireLock();
    saved_thread_state = PyThreadState_Swap(stream_info->thread_state);

    /* Create Python lists that will contain event paths and masks. */
    event_path_list = PyList_New(num_events);
    event_mask_list = PyList_New(num_events);

    RETURN_NULL_IF_NOT(event_path_list && event_mask_list);

    /* Enumerate event paths and masks into Python lists. */
    for (i = 0; i < num_events; ++i)
        {
            event_path = PyString_FromString(event_paths[i]);
            event_mask = PyInt_FromLong(event_masks[i]);
            if (!(event_mask && event_path))
                {
                    Py_DECREF(event_path_list);
                    Py_DECREF(event_mask_list);
                    return NULL;
                }
            PyList_SET_ITEM(event_path_list, i, event_path);
            PyList_SET_ITEM(event_mask_list, i, event_mask);
        }

    /* Call the callback event handler function with the enlisted event masks and paths as arguments.
     * On failure check whether an error occurred and stop this instance of the runloop.
     */
    if (NULL == PyObject_CallFunction(stream_info->callback_event_handler,
                                      "OO",
                                      event_path_list,
                                      event_mask_list))
        {
            /* An exception may have occurred. */
            if (!PyErr_Occurred())
                {
                    /* If one didn't occur, raise an exception informing that we could not execute the
                     callback function. */
                    PyErr_SetString(PyExc_ValueError, CALLBACK_ERROR_MESSAGE);
                }

            /* Stop listening for events. */
            CFRunLoopStop(stream_info->loop);
        }

    /* Restore original thread state and release lock. */
    PyThreadState_Swap(saved_thread_state);
    PyEval_ReleaseLock();
}

/**
 * Runs an event loop in a thread.
 *
 * @param self Python 'self'.
 * @param args Arguments tuple.
 *
 * @return None
 */
PyDoc_STRVAR(watchdog_fsevents_loop__doc__,
             "Runs an event loop in a thread.");
static PyObject *
watchdog_fsevents_loop(PyObject *self,
                       PyObject *args)
{
    PyObject *thread = NULL;
    PyObject *value = NULL;

    RETURN_NULL_IF_NOT(PyArg_ParseTuple(args, "O:loop", &thread));

    PyEval_InitThreads();

    /* Allocate info object and store thread state. */
    value = PyDict_GetItem(g__pydict_loops, thread);
    if (NULL == value)
        {
            CFRunLoopRef loop = CFRunLoopGetCurrent();
            value = PyCObject_FromVoidPtr((void *) loop, PyMem_Free);
            PyDict_SetItem(g__pydict_loops, thread, value);
            Py_INCREF(thread);
            Py_INCREF(value);
        }

    /* No timeout, block until events. */
    Py_BEGIN_ALLOW_THREADS;
    CFRunLoopRun();
    Py_END_ALLOW_THREADS;

    /* Clean up state information data. */
    if (0 == PyDict_DelItem(g__pydict_loops, thread))
        {
            Py_DECREF(thread);
            Py_INCREF(value);
        }

    RETURN_NULL_IF(PyErr_Occurred());

    Py_INCREF(Py_None);
    return Py_None;
}

/**
 * Converts a Python string list to a CFMutableArray of CFStrings
 * and returns a reference to the array.
 *
 * @param pystring_list
 * 		Pointer to a Python list of Python strings.
 * @return A pointer of type CFMutableArrayRef to a mutable array of CFString instances.
 */
static CFMutableArrayRef
_convert_pystring_list_to_cf_string_array(PyObject *pystring_list)
{
    CFMutableArrayRef cf_array_strings = NULL;
    const char *c_string = NULL;
    CFStringRef cf_string = NULL;
    Py_ssize_t i = 0;
    Py_ssize_t string_list_size = 0;

    string_list_size = PyList_Size(pystring_list);

    cf_array_strings = CFArrayCreateMutable(kCFAllocatorDefault, 1, &kCFTypeArrayCallBacks);

    RETURN_NULL_IF_NULL(cf_array_strings);

    for (i = 0; i < string_list_size; ++i)
        {
            c_string = PyString_AS_STRING(PyList_GetItem(pystring_list, i));
            cf_string = CFStringCreateWithCString(kCFAllocatorDefault,
                                                  c_string,
                                                  kCFStringEncodingUTF8);
            CFArraySetValueAtIndex(cf_array_strings, i, cf_string);
            CFRelease(cf_string);
        }

    return cf_array_strings;
}

/**
 * Creates an FSEventStream object and returns a reference to it.
 *
 * @param stream_info
 *      Pointer to an FSEventStreamInfo object.
 * @param paths
 *      Python list of Python string paths.
 * @param callback
 *      A callback that the FSEvents API will call.
 */
static FSEventStreamRef
_create_fs_stream(FSEventStreamInfo *stream_info,
                  PyObject *paths,
                  FSEventStreamCallback callback)
{
    CFMutableArrayRef cf_array_paths = _convert_pystring_list_to_cf_string_array(paths);

    RETURN_NULL_IF_NULL(cf_array_paths);

    /* Create event stream. */
    FSEventStreamContext fs_stream_context =
        { 0, stream_info, NULL, NULL, NULL };
    FSEventStreamRef fs_stream = FSEventStreamCreate(kCFAllocatorDefault,
                                                     callback,
                                                     &fs_stream_context,
                                                     cf_array_paths,
                                                     kFSEventStreamEventIdSinceNow,
                                                     0.01, // latency
                                                     kFSEventStreamCreateFlagNoDefer);
    CFRelease(cf_array_paths);
    return fs_stream;
}

/**
 * Get runloop reference from observer info data or current runloop.
 *
 * @param loops
 *      The dictionary of loops from which to obtain the loop
 *      for the given thread.
 * @return A pointer CFRunLookRef to a runloop.
 */
static CFRunLoopRef
_get_runloop_for_thread_or_current(PyObject *loops,
                                   PyObject *thread)
{
    PyObject *value = NULL;
    CFRunLoopRef loop = NULL;

    value = PyDict_GetItem(loops, thread);
    if (NULL == value)
        {
            loop = CFRunLoopGetCurrent();
        }
    else
        {
            loop = (CFRunLoopRef) PyCObject_AsVoidPtr(value);
        }

    return loop;
}

/**
 * Schedules a stream.
 *
 * @param self
 *     Python 'self'.
 * @param args
 *     Arguments tuple.
 *
 * @return None
 */
PyDoc_STRVAR(watchdog_fsevents_schedule__doc__,
             "Schedules a stream.");
static PyObject *
watchdog_fsevents_schedule(PyObject *self,
                           PyObject *args)
{
    /* Arguments */
    PyObject *thread = NULL;
    PyObject *stream = NULL;
    PyObject *paths = NULL;
    PyObject *callback = NULL;

    /* Other locals */
    FSEventStreamInfo *stream_info = NULL;
    FSEventStreamRef fs_stream = NULL;
    CFRunLoopRef loop = NULL;
    PyObject *value = NULL;

    RETURN_NULL_IF_NOT(PyArg_ParseTuple(args, "OOOO:schedule", &thread, &stream, &callback, &paths));

    /* Stream must not already be scheduled. */
    RETURN_NULL_IF(1 == PyDict_Contains(g__pydict_streams, stream));

    /* Create the file stream. */
    stream_info = PyMem_New(FSEventStreamInfo, 1);
    fs_stream = _create_fs_stream(stream_info, paths, (FSEventStreamCallback)
            & event_stream_handler);

    RETURN_NULL_IF_NULL(fs_stream);

    /* Convert the fs_stream to a Python C Object and store it in the streams dictionary. */
    value = PyCObject_FromVoidPtr(fs_stream, PyMem_Free);
    PyDict_SetItem(g__pydict_streams, stream, value);

    /* Get the runloop associated with the thread. */
    loop = _get_runloop_for_thread_or_current(g__pydict_loops, thread);

    /* Schedule the fs_stream in the runloop */
    FSEventStreamScheduleWithRunLoop(fs_stream, loop, kCFRunLoopDefaultMode);

    /* Set stream info for callback. */
    stream_info->callback_event_handler = callback;
    stream_info->stream = fs_stream;
    stream_info->loop = loop;
    stream_info->thread_state = PyThreadState_Get();
    Py_INCREF(callback);

    /* Start event streams. */
    if (!FSEventStreamStart(fs_stream))
        {
            FSEventStreamInvalidate(fs_stream);
            FSEventStreamRelease(fs_stream);
            return NULL;
        }

    Py_INCREF(Py_None);
    return Py_None;
}

/**
 * Unschedules a stream.
 *
 * @param self
 *     Python 'self'.
 * @param stream
 *     Stream to unschedule
 *
 * @return None
 */
PyDoc_STRVAR(watchdog_fsevents_unschedule__doc__,
             "Unschedules a stream.");
static PyObject *
watchdog_fsevents_unschedule(PyObject *self,
                             PyObject *stream)
{
    PyObject *value = PyDict_GetItem(g__pydict_streams, stream);
    FSEventStreamRef fs_stream = PyCObject_AsVoidPtr(value);

    PyDict_DelItem(g__pydict_streams, stream);

    FSEventStreamStop(fs_stream);
    FSEventStreamInvalidate(fs_stream);
    FSEventStreamRelease(fs_stream);

    Py_INCREF(Py_None);
    return Py_None;
}

/**
 * Stops running the event loop in the specified thread.
 *
 * @param self
 *     Python 'self'.
 * @param thread
 *     Thread running the event runloop.
 *
 * @return None
 */
PyDoc_STRVAR(watchdog_fsevents_stop__doc__,
             "Stops running the event loop in the specified thread.");
static PyObject *
watchdog_fsevents_stop(PyObject *self,
                       PyObject *thread)
{
    PyObject *value = PyDict_GetItem(g__pydict_loops, thread);
    CFRunLoopRef loop = PyCObject_AsVoidPtr(value);

    /* Stop runloop */
    if (loop)
        {
            CFRunLoopStop(loop);
        }

    Py_INCREF(Py_None);
    return Py_None;
}

/**
 * Module public API.
 */
static PyMethodDef _watchdog_fseventsmethods[] =
    {
        { "loop",       watchdog_fsevents_loop,       METH_VARARGS, watchdog_fsevents_loop__doc__ },
        { "stop",       watchdog_fsevents_stop,       METH_O,       watchdog_fsevents_stop__doc__ },
        { "schedule",   watchdog_fsevents_schedule,   METH_VARARGS, watchdog_fsevents_schedule__doc__ },
        { "unschedule", watchdog_fsevents_unschedule, METH_O,       watchdog_fsevents_unschedule__doc__ },
        { NULL, NULL, 0, NULL } };

/**
 * Initialize the _fsevents module.
 */
#if PY_MAJOR_VERSION < 3
void
init_watchdog_fsevents(void)
{
    PyObject *module = Py_InitModule3(module__name__, _watchdog_fseventsmethods, watchdog_fsevents_module__doc__);
    PyModule_AddIntConstant(module, MODULE_CONSTANT_NAME_POLLIN, kCFFileDescriptorReadCallBack);
    PyModule_AddIntConstant(module, MODULE_CONSTANT_NAME_POLLOUT, kCFFileDescriptorWriteCallBack);

    g__pydict_loops = PyDict_New();
    g__pydict_streams = PyDict_New();
}
#else /* PY_MAJOR_VERSION >= 3 */
static struct PyModuleDef _watchdog_fseventsmodule =
    {
        PyModuleDef_HEAD_INIT,
        module__name__,
        watchdog_fsevents_module__doc__,
        -1,
        _watchdog_fseventsmethods
    };
PyMODINIT_FUNC
PyInit__watchdog_fsevents(void)
    {
        PyObject *module = PyModule_Create(&_watchdog_fseventsmodule);
        PyModule_AddIntConstant(module, MODULE_CONSTANT_NAME_POLLIN, kCFFileDescriptorReadCallBack);
        PyModule_AddIntConstant(module, MODULE_CONSTANT_NAME_POLLOUT, kCFFileDescriptorWriteCallBack);

        g__pydict_loops = PyDict_New();
        g__pydict_streams = PyDict_New();

        return module;
    }
#endif /* PY_MAJOR_VERSION >= 3 */
