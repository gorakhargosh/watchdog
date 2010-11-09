/**
 * _fsevents.c: Low-level FSEvents Python API.
 *
 */
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

static const char *MODULE_NAME = "_fsevents";
static const char *MODULE_CONSTANT_NAME_POLLIN = "POLLIN";
static const char *MODULE_CONSTANT_NAME_POLLOUT = "POLLOUT";

/**
 * Error messages.
 */
static const char *CALLBACK_ERROR_MESSAGE = "Unable to call callback function.";

/**
 * Module documentation.
 */
static const char *MODULE_DOCUMENTATION = "Low-level FSEvents interface.";


/**
 * Dictionary of all the event loops.
 */
PyObject *g__pydict_loops = NULL;

/**
 * Dictionary of all the event streams.
 */
PyObject *g__pydict_streams = NULL;

/**
 * Macro that forces returning NULL if stream exists.
 */
#define RETURN_NULL_IF_DUPLICATE_STREAM(fs_stream)                      \
    do                                                                  \
        {                                                               \
            if ((PyDict_Contains(g__pydict_streams, (fs_stream)) == 1)) { return NULL; } \
        }                                                               \
    while(0)

/**
 * Macro that forces returning NULL if given argument is NULL.
 */
#define RETURN_NULL_IF_NULL(o)                  \
    do                                          \
        {                                       \
            if ((o) == NULL) { return NULL; }   \
        }                                       \
    while(0)


/**
 * Macro that forces returning NULL if given argument is true.
 */
#define RETURN_NULL_IF(c)                       \
    do                                          \
        {                                       \
            if ((c)) { return NULL; }          \
        }                                       \
    while(0)

/**
 * Macro that forces returning NULL if given argument is true.
 */
#define RETURN_NULL_IF_NOT(c)                       \
    do                                          \
        {                                       \
            if (!(c)) { return NULL; }          \
        }                                       \
    while(0)


/**
 * Filesystem event stream meta information structure.
 */
typedef struct {
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
event_stream_handler (FSEventStreamRef stream,
                      FSEventStreamInfo *stream_info,
                      const int num_events,
                      const char *const event_paths[],
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

    /* Enumerate event paths and masks into python lists. */
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
    if (PyObject_CallFunction(stream_info->callback_event_handler, "OO", event_path_list, event_mask_list) == NULL)
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
static char pyfsevents_loop_doc[] = "Runs an event loop in a thread.";
static PyObject *
pyfsevents_loop (PyObject *self,
                 PyObject *args)
{
    PyObject *thread = NULL;
    PyObject *value = NULL;

    RETURN_NULL_IF_NOT(PyArg_ParseTuple(args, "O:loop", &thread));

    PyEval_InitThreads();

    /* Allocate info object and store thread state. */
    value = PyDict_GetItem(g__pydict_loops, thread);
    if (value == NULL)
        {
            CFRunLoopRef loop = CFRunLoopGetCurrent();
            value = PyCObject_FromVoidPtr((void *)loop, PyMem_Free);
            PyDict_SetItem(g__pydict_loops, thread, value);
            Py_INCREF(thread);
            Py_INCREF(value);
        }


    /* No timeout, block until events. */
    Py_BEGIN_ALLOW_THREADS;
    CFRunLoopRun();
    Py_END_ALLOW_THREADS;


    /* Clean up state information data. */
    if (PyDict_DelItem(g__pydict_loops, thread) == 0)
        {
            Py_DECREF(thread);
            Py_INCREF(value);
        }

    RETURN_NULL_IF(PyErr_Occurred());


    Py_INCREF(Py_None);
    return Py_None;
}


/* Converts a Python string list to a CFMutableArray of CFStrings and returns a reference to the array. */
static CFMutableArrayRef
__convert_pystring_list_to_cf_string_array(PyObject *pystring_list)
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


/* Creates an FSEventStream object and returns a reference to it. */
static FSEventStreamRef
__create_fs_stream(FSEventStreamInfo *stream_info, PyObject *paths, FSEventStreamCallback callback)
{
    CFMutableArrayRef cf_array_paths = __convert_pystring_list_to_cf_string_array(paths);

    RETURN_NULL_IF_NULL(cf_array_paths);

    /* Create event stream. */
    FSEventStreamContext fs_stream_context = {0, /* (void *) */stream_info, NULL, NULL, NULL};
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


/* Get runloop reference from observer info data or current. */
static CFRunLoopRef
__get_runloop_for_thread(PyObject *loops, PyObject *thread)
{
    PyObject *value = NULL;
    CFRunLoopRef loop = NULL;

    value = PyDict_GetItem(loops, thread);
    if (value == NULL)
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
static char pyfsevents_schedule_doc[] = "Schedules a stream.";
static PyObject *
pyfsevents_schedule (PyObject *self,
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
    RETURN_NULL_IF_DUPLICATE_STREAM(stream);

    /* Create the file stream. */
    stream_info = PyMem_New(FSEventStreamInfo, 1);
    fs_stream = __create_fs_stream(stream_info, paths, (FSEventStreamCallback) &event_stream_handler);

    RETURN_NULL_IF_NULL(fs_stream);

    /* Convert the fs_stream to a Python C Object and store it in the streams dictionary. */
    value = PyCObject_FromVoidPtr(/* (void *) */fs_stream, PyMem_Free);
    PyDict_SetItem(g__pydict_streams, stream, value);

    /* Get the runloop associated with the thread. */
    loop = __get_runloop_for_thread(g__pydict_loops, thread);

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
static char pyfsevents_unschedule_doc[] = "Unschedules a stream.";
static PyObject *
pyfsevents_unschedule(PyObject *self,
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
static char pyfsevents_stop_doc[] = "Stops running the event loop in the specified thread.";
static PyObject *
pyfsevents_stop(PyObject *self,
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
static PyMethodDef _fseventsmethods[] = {
    {"loop", pyfsevents_loop, METH_VARARGS, pyfsevents_loop_doc},
    {"stop", pyfsevents_stop, METH_O, pyfsevents_stop_doc},
    {"schedule", pyfsevents_schedule, METH_VARARGS, pyfsevents_schedule_doc},
    {"unschedule", pyfsevents_unschedule, METH_O, pyfsevents_unschedule_doc},
    {NULL, NULL, 0, NULL},
};


/**
 * Initialize the _fsevents module.
 */
#if PY_MAJOR_VERSION < 3
void
init_fsevents(void){
    PyObject *module = Py_InitModule3(MODULE_NAME, _fseventsmethods, MODULE_DOCUMENTATION);
    PyModule_AddIntConstant(module, MODULE_CONSTANT_NAME_POLLIN, kCFFileDescriptorReadCallBack);
    PyModule_AddIntConstant(module, MODULE_CONSTANT_NAME_POLLOUT, kCFFileDescriptorWriteCallBack);

    g__pydict_loops = PyDict_New();
    g__pydict_streams = PyDict_New();
}
#else /* PY_MAJOR_VERSION >= 3 */
static struct PyModuleDef _fseventsmodule = {
    PyModuleDef_HEAD_INIT,
    MODULE_NAME,
    MODULE_DOCUMENTATION,
    -1,
    _fseventsmethods
};
PyMODINIT_FUNC
PyInit__fsevents(void)
{
    PyObject *module = PyModule_Create(&_fseventsmodule);
    PyModule_AddIntConstant(module, MODULE_CONSTANT_NAME_POLLIN, kCFFileDescriptorReadCallBack);
    PyModule_AddIntConstant(module, MODULE_CONSTANT_NAME_POLLOUT, kCFFileDescriptorWriteCallBack);

    g__pydict_loops = PyDict_New();
    g__pydict_streams = PyDict_New();

    return module;
}
#endif /* PY_MAJOR_VERSION >= 3 */
