/**
 * watchdog_fsevents.c: Python-C bridge to the OS X FSEvents API.
 *
 * Copyright 2010 Malthe Borch <mborch@gmail.com>
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


#include <Python.h>
#include <CoreFoundation/CoreFoundation.h>
#include <CoreServices/CoreServices.h>
#include <stdlib.h>
#include <signal.h>


#if (PY_VERSION_HEX < 0x02050000) && !defined(PY_SSIZE_T_MIN)
typedef int Py_ssize_t;
#define PY_SSIZE_T_MIN INT_MIN
#define PY_SSIZE_T_MAX INT_MAX
#endif

/* Convenience macros to make code more readable. */
#define G_NOT(o)                        (!(o))
#define G_IS_NULL(o)                    ((o) == NULL)
#define G_IS_NOT_NULL(o)                ((o) != NULL)
#define G_RETURN_NULL_IF_NULL(o)        do{if(NULL == (o)){ return NULL; }}while(0)
#define G_RETURN_NULL_IF(condition)     do{if((condition)){ return NULL; }}while(0)
#define G_RETURN_NULL_IF_NOT(condition) do{if(!(condition)){ return NULL; }}while(0)
#define G_RETURN_IF(condition)          do{if((condition)){ return; }}while(0)
#define G_RETURN_IF_NOT(condition)      do{if(!(condition)){ return; }}while(0)

/* Error message definitions. */
#define ERROR_CANNOT_CALL_CALLBACK "Unable to call Python callback."

/* Other information. */
#define MODULE_NAME  "_watchdog_fsevents"

/**
 * Event stream callback contextual information passed to
 * our ``watchdog_FSEventStreamCallback`` function by the
 * FSEvents API whenever an event occurs.
 */
typedef struct {
    /**
     * A pointer to the Python callback which will
     * will in turn be called by our event handler
     * with event information. The Python callback
     * function must accept 2 arguments, both of which
     * are Python lists::
     *
     *    def python_callback(event_paths, event_flags):
     *        pass
     */
    PyObject        *python_callback;
    /**
     * A pointer to the associated ``FSEventStream``
     * instance.
     */
    FSEventStreamRef stream_ref;
    /**
     * A pointer to the associated ``CFRunLoop``
     * instance.
     */
    CFRunLoopRef     run_loop_ref;
    /**
     * A pointer to the state of the Python thread.
     */
    PyThreadState   *thread_state;
} StreamCallbackInfo;


/**
 * Dictionary to keep track of which run loop
 * belongs to which emitter thread.
 */
PyObject *thread_to_run_loop = NULL;

/**
 * Dictionary to keep track of which stream
 * belongs to which watch.
 */
PyObject *watch_to_stream = NULL;


/**
 * PyCapsule destructor for Python 3 compatibility
 */
#if PY_MAJOR_VERSION >= 3
static void watchdog_pycapsule_destructor(PyObject *ptr)
{
    void *p = PyCapsule_GetPointer(ptr, NULL);
    if (p) {
        PyMem_Free(p);
    }
}
#endif


/**
 * This is the callback passed to the FSEvents API, which calls
 * the Python callback function, in turn, by passing in event data
 * as Python objects.
 *
 * :param stream_ref:
 *     A pointer to an ``FSEventStream`` instance.
 * :param stream_callback_info_ref:
 *     Callback context information passed by the FSEvents API.
 *     This contains a reference to the Python callback that this
 *     function calls in turn with information about the events.
 * :param num_events:
 *     An unsigned integer representing the number of events
 *     captured by the FSEvents API.
 * :param event_paths:
 *     An array of NUL-terminated C strings representing event paths.
 * :param event_flags:
 *     An array of ``FSEventStreamEventFlags`` unsigned integral
 *     mask values.
 * :param event_ids:
 *     An array of 64-bit unsigned integers representing event
 *     identifiers.
 */
static void
watchdog_FSEventStreamCallback(ConstFSEventStreamRef          stream_ref,
                               StreamCallbackInfo            *stream_callback_info_ref,
                               size_t                         num_events,
                               const char                    *event_paths[],
                               const FSEventStreamEventFlags  event_flags[],
                               const FSEventStreamEventId     event_ids[])
{
    size_t i = 0;
    PyObject *callback_result = NULL;
    PyObject *path = NULL;
    PyObject *flags = NULL;
    PyObject *py_event_flags = NULL;
    PyObject *py_event_paths = NULL;
    PyThreadState *saved_thread_state = NULL;

    /* Acquire interpreter lock and save original thread state. */
    PyGILState_STATE gil_state = PyGILState_Ensure();
    saved_thread_state = PyThreadState_Swap(stream_callback_info_ref->thread_state);

    /* Convert event flags and paths to Python ints and strings. */
    py_event_paths = PyList_New(num_events);
    py_event_flags = PyList_New(num_events);
    if (G_NOT(py_event_paths && py_event_flags))
    {
        Py_DECREF(py_event_paths);
        Py_DECREF(py_event_flags);
        return /*NULL*/;
    }
    for (i = 0; i < num_events; ++i)
    {
#if PY_MAJOR_VERSION >= 3
        path = PyUnicode_FromString(event_paths[i]);
        flags = PyLong_FromLong(event_flags[i]);
#else
        path = PyString_FromString(event_paths[i]);
        flags = PyInt_FromLong(event_flags[i]);
#endif
        if (G_NOT(path && flags))
        {
            Py_DECREF(py_event_paths);
            Py_DECREF(py_event_flags);
            return /*NULL*/;
        }
        PyList_SET_ITEM(py_event_paths, i, path);
        PyList_SET_ITEM(py_event_flags, i, flags);
    }

    /* Call the Python callback function supplied by the stream information
     * struct. The Python callback function should accept two arguments,
     * both being Python lists:
     *
     *    def python_callback(event_paths, event_flags):
     *        pass
     */
    callback_result = \
        PyObject_CallFunction(stream_callback_info_ref->python_callback,
                              "OO", py_event_paths, py_event_flags);
    if (G_IS_NULL(callback_result))
    {
        if (G_NOT(PyErr_Occurred()))
        {
            PyErr_SetString(PyExc_ValueError, ERROR_CANNOT_CALL_CALLBACK);
        }
        CFRunLoopStop(stream_callback_info_ref->run_loop_ref);
    }

    /* Release the lock and restore thread state. */
    PyThreadState_Swap(saved_thread_state);
    PyGILState_Release(gil_state);
}


/**
 * Converts a list of Python strings to a ``CFMutableArray`` of
 * UTF-8 encoded ``CFString`` instances and returns a pointer to
 * the array.
 *
 * :param py_string_list:
 *     List of Python strings.
 * :returns:
 *     A pointer to ``CFMutableArray`` (that is, a
 *     ``CFMutableArrayRef``) of UTF-8 encoded ``CFString``
 *     instances.
 */
static CFMutableArrayRef
watchdog_CFMutableArrayRef_from_PyStringList(PyObject *py_string_list)
{
    Py_ssize_t i = 0;
    Py_ssize_t string_list_size = 0;
    const char *c_string = NULL;
    CFMutableArrayRef array_of_cf_string = NULL;
    CFStringRef cf_string = NULL;
    PyObject *py_string = NULL;

    G_RETURN_NULL_IF_NULL(py_string_list);

    string_list_size = PyList_Size(py_string_list);

    /* Allocate a CFMutableArray. */
    array_of_cf_string = CFArrayCreateMutable(kCFAllocatorDefault, 1,
                                              &kCFTypeArrayCallBacks);
    G_RETURN_NULL_IF_NULL(array_of_cf_string);

    /* Loop through the Python string list and copy strings to the
     * CFString array list. */
    for (i = 0; i < string_list_size; ++i)
    {
        py_string = PyList_GetItem(py_string_list, i);
        G_RETURN_NULL_IF_NULL(py_string);
#if PY_MAJOR_VERSION >= 3
        if (PyUnicode_Check(py_string)) {
          c_string = PyUnicode_AsUTF8(py_string);
        } else {
          c_string = PyBytes_AS_STRING(py_string);
        }
#else
        c_string = PyString_AS_STRING(py_string);
#endif
        cf_string = CFStringCreateWithCString(kCFAllocatorDefault,
                                              c_string,
                                              kCFStringEncodingUTF8);
        CFArraySetValueAtIndex(array_of_cf_string, i, cf_string);
        CFRelease(cf_string);
    }

    return array_of_cf_string;
}


/**
 * Creates an instance of ``FSEventStream`` and returns a pointer
 * to the instance.
 *
 * :param stream_callback_info_ref:
 *      Pointer to the callback context information that will be
 *      passed by the FSEvents API to the callback handler specified
 *      by the ``callback`` argument to this function. This
 *      information contains a reference to the Python callback that
 *      it must call in turn passing on the event information
 *      as Python objects to the the Python callback.
 * :param py_paths:
 *      A Python list of Python strings representing path names
 *      to monitor.
 * :param callback:
 *      A function pointer of type ``FSEventStreamCallback``.
 * :returns:
 *      A pointer to an ``FSEventStream`` instance (that is, it returns
 *      an ``FSEventStreamRef``).
 */
static FSEventStreamRef
watchdog_FSEventStreamCreate(StreamCallbackInfo *stream_callback_info_ref,
                             PyObject *py_paths,
                             FSEventStreamCallback callback)
{
    CFAbsoluteTime stream_latency = 0.01;
    CFMutableArrayRef paths = NULL;
    FSEventStreamRef stream_ref = NULL;

    /* Check arguments. */
    G_RETURN_NULL_IF_NULL(py_paths);
    G_RETURN_NULL_IF_NULL(callback);

    /* Convert the Python paths list to a CFMutableArray. */
    paths = watchdog_CFMutableArrayRef_from_PyStringList(py_paths);
    G_RETURN_NULL_IF_NULL(paths);

    /* Create the event stream. */
    FSEventStreamContext stream_context = {
        0, stream_callback_info_ref, NULL, NULL, NULL
    };
    stream_ref = FSEventStreamCreate(kCFAllocatorDefault,
                                     callback,
                                     &stream_context,
                                     paths,
                                     kFSEventStreamEventIdSinceNow,
                                     stream_latency,
                                     kFSEventStreamCreateFlagNoDefer);
    CFRelease(paths);
    return stream_ref;
}


PyDoc_STRVAR(watchdog_add_watch__doc__,
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
watchdog_add_watch(PyObject *self, PyObject *args)
{
    FSEventStreamRef stream_ref = NULL;
    StreamCallbackInfo *stream_callback_info_ref = NULL;
    CFRunLoopRef run_loop_ref = NULL;
    PyObject *emitter_thread = NULL;
    PyObject *watch = NULL;
    PyObject *paths_to_watch = NULL;
    PyObject *python_callback = NULL;
    PyObject *value = NULL;

    /* Ensure all arguments are received. */
    G_RETURN_NULL_IF_NOT(PyArg_ParseTuple(args, "OOOO:schedule",
                                          &emitter_thread, &watch,
                                          &python_callback, &paths_to_watch));

    /* Watch must not already be scheduled. */
    G_RETURN_NULL_IF(PyDict_Contains(watch_to_stream, watch) == 1);

    /* Create an instance of the callback information structure. */
    stream_callback_info_ref = PyMem_New(StreamCallbackInfo, 1);
    G_RETURN_NULL_IF_NULL(stream_callback_info_ref);

    /* Create an FSEvent stream and
     * Save the stream reference to the global watch-to-stream dictionary. */
    stream_ref = watchdog_FSEventStreamCreate(stream_callback_info_ref,
                                              paths_to_watch,
                                              (FSEventStreamCallback) &watchdog_FSEventStreamCallback);
#if PY_MAJOR_VERSION >= 3
    value = PyCapsule_New(stream_ref, NULL, watchdog_pycapsule_destructor);
#else
    value = PyCObject_FromVoidPtr(stream_ref, PyMem_Free);
#endif
    PyDict_SetItem(watch_to_stream, watch, value);

    /* Get a reference to the runloop for the emitter thread
     * or to the current runloop. */
    value = PyDict_GetItem(thread_to_run_loop, emitter_thread);
    if (G_IS_NULL(value))
    {
        run_loop_ref = CFRunLoopGetCurrent();
    }
    else
    {
#if PY_MAJOR_VERSION >= 3
        run_loop_ref = PyCapsule_GetPointer(value, NULL);
#else
        run_loop_ref = PyCObject_AsVoidPtr(value);
#endif
    }

    /* Schedule the stream with the obtained runloop. */
    FSEventStreamScheduleWithRunLoop(stream_ref, run_loop_ref, kCFRunLoopDefaultMode);

    /* Set the stream information for the callback.
     * This data will be passed to our watchdog_FSEventStreamCallback function
     * by the FSEvents API whenever an event occurs.
     */
    stream_callback_info_ref->python_callback = python_callback;
    stream_callback_info_ref->stream_ref = stream_ref;
    stream_callback_info_ref->run_loop_ref = run_loop_ref;
    stream_callback_info_ref->thread_state = PyThreadState_Get();
    Py_INCREF(python_callback);

    /* Start the event stream. */
    if (G_NOT(FSEventStreamStart(stream_ref)))
    {
        FSEventStreamInvalidate(stream_ref);
        FSEventStreamRelease(stream_ref);
        return NULL;
    }

    Py_INCREF(Py_None);
    return Py_None;
}


PyDoc_STRVAR(watchdog_read_events__doc__,
             MODULE_NAME ".read_events(emitter_thread) -> None\n\
Blocking function that runs an event loop associated with an emitter thread.\n\n\
:param emitter_thread:\n\
    The emitter thread for which the event loop will be run.\n");
static PyObject *
watchdog_read_events(PyObject *self, PyObject *args)
{
    CFRunLoopRef run_loop_ref = NULL;
    PyObject *emitter_thread = NULL;
    PyObject *value = NULL;

    G_RETURN_NULL_IF_NOT(PyArg_ParseTuple(args, "O:loop", &emitter_thread));

    PyEval_InitThreads();

    /* Allocate information and store thread state. */
    value = PyDict_GetItem(thread_to_run_loop, emitter_thread);
    if (G_IS_NULL(value))
    {
        run_loop_ref = CFRunLoopGetCurrent();
#if PY_MAJOR_VERSION >= 3
        value = PyCapsule_New(run_loop_ref, NULL, watchdog_pycapsule_destructor);
#else
        value = PyCObject_FromVoidPtr(run_loop_ref, PyMem_Free);
#endif
        PyDict_SetItem(thread_to_run_loop, emitter_thread, value);
        Py_INCREF(emitter_thread);
        Py_INCREF(value);
    }

    /* No timeout, block until events. */
    Py_BEGIN_ALLOW_THREADS;
    CFRunLoopRun();
    Py_END_ALLOW_THREADS;

    /* Clean up state information. */
    if (PyDict_DelItem(thread_to_run_loop, emitter_thread) == 0)
    {
        Py_DECREF(emitter_thread);
        Py_INCREF(value);
    }

    G_RETURN_NULL_IF(PyErr_Occurred());

    Py_INCREF(Py_None);
    return Py_None;
}

PyDoc_STRVAR(watchdog_remove_watch__doc__,
        MODULE_NAME ".remove_watch(watch) -> None\n\
Removes a watch from the event loop.\n\n\
:param watch:\n\
    The watch to remove.\n");
static PyObject *
watchdog_remove_watch(PyObject *self, PyObject *watch)
{
    PyObject *value = PyDict_GetItem(watch_to_stream, watch);
    PyDict_DelItem(watch_to_stream, watch);

#if PY_MAJOR_VERSION >= 3
    FSEventStreamRef stream_ref = PyCapsule_GetPointer(value, NULL);
#else
    FSEventStreamRef stream_ref = PyCObject_AsVoidPtr(value);
#endif

    FSEventStreamStop(stream_ref);
    FSEventStreamInvalidate(stream_ref);
    FSEventStreamRelease(stream_ref);

    Py_INCREF(Py_None);
    return Py_None;
}

PyDoc_STRVAR(watchdog_stop__doc__,
        MODULE_NAME ".stop(emitter_thread) -> None\n\
Stops running the event loop from the specified thread.\n\n\
:param emitter_thread:\n\
    The thread for which the event loop will be stopped.\n");
static PyObject *
watchdog_stop(PyObject *self, PyObject *emitter_thread)
{
    PyObject *value = PyDict_GetItem(thread_to_run_loop, emitter_thread);
#if PY_MAJOR_VERSION >= 3
    CFRunLoopRef run_loop_ref = PyCapsule_GetPointer(value, NULL);
#else
    CFRunLoopRef run_loop_ref = PyCObject_AsVoidPtr(value);
#endif

    /* Stop the run loop. */
    if (G_IS_NOT_NULL(run_loop_ref))
    {
        CFRunLoopStop(run_loop_ref);
    }

    Py_INCREF(Py_None);
    return Py_None;
}


/******************************************************************************
 * Module initialization.
 *****************************************************************************/

PyDoc_STRVAR(watchdog_fsevents_module__doc__,
             "Low-level FSEvents Python/C API bridge.");

static PyMethodDef watchdog_fsevents_methods[] =
{
    {"add_watch",    watchdog_add_watch,    METH_VARARGS, watchdog_add_watch__doc__},
    {"read_events",  watchdog_read_events,  METH_VARARGS, watchdog_read_events__doc__},
    {"remove_watch", watchdog_remove_watch, METH_O,       watchdog_remove_watch__doc__},

    /* Aliases for compatibility with macfsevents. */
    {"schedule",     watchdog_add_watch,    METH_VARARGS, "Alias for add_watch."},
    {"loop",         watchdog_read_events,  METH_VARARGS, "Alias for read_events."},
    {"unschedule",   watchdog_remove_watch, METH_O,       "Alias for remove_watch."},

    {"stop",         watchdog_stop,         METH_O,       watchdog_stop__doc__},

    {NULL},
};


/**
 * Initialize the module globals.
 */
static void
watchdog_module_init(void)
{
    thread_to_run_loop = PyDict_New();
    watch_to_stream = PyDict_New();
}


/**
 * Adds various attributes to the Python module.
 *
 * :param module:
 *     A pointer to the Python module object to inject
 *     the attributes into.
 */
static void
watchdog_module_add_attributes(PyObject *module)
{
    PyObject *version_tuple = Py_BuildValue("(iii)",
                                            WATCHDOG_VERSION_MAJOR,
                                            WATCHDOG_VERSION_MINOR,
                                            WATCHDOG_VERSION_BUILD);
    PyModule_AddIntConstant(module,
                            "POLLIN",
                            kCFFileDescriptorReadCallBack);
    PyModule_AddIntConstant(module,
                            "POLLOUT",
                            kCFFileDescriptorWriteCallBack);

    /* Adds version information. */
    PyModule_AddObject(module,
                       "__version__",
                       version_tuple);
    PyModule_AddObject(module,
                       "version_string",
                       Py_BuildValue("s", WATCHDOG_VERSION_STRING));
}


#if PY_MAJOR_VERSION < 3

void initwatchdog_fsevents(void);

/**
 * Initialize the Python 2.x module.
 */
void
init_watchdog_fsevents(void)
{
    PyObject *module = Py_InitModule3(MODULE_NAME,
                                      watchdog_fsevents_methods,
                                      watchdog_fsevents_module__doc__);
    watchdog_module_add_attributes(module);
    watchdog_module_init();
}

#else /* !PY_MAJOR_VERSION < 3 */

static struct PyModuleDef watchdog_fsevents_module = {
    PyModuleDef_HEAD_INIT,
    MODULE_NAME,
    watchdog_fsevents_module__doc__,
    -1,
    watchdog_fsevents_methods
};

/**
 * Initialize the Python 3.x module.
 */
PyMODINIT_FUNC
PyInit__watchdog_fsevents(void){
    PyObject *module = PyModule_Create(&watchdog_fsevents_module);
    watchdog_module_add_attributes(module);
    watchdog_module_init();
    return module;
}

#endif /* !PY_MAJOR_VERSION < 3 */
