#include "Python.h"
#include <CoreFoundation/CoreFoundation.h>
#include <CoreServices/CoreServices.h>
#include <stdlib.h>
#include <signal.h>
#include <limits.h>

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
const char CALLBACK_ERROR_MESSAGE[] = "Unable to call callback function.";

/**
 * Dictionary of all the event loops.
 */
PyObject *g__pydict_loops = NULL;

/**
 * Dictionary of all the event streams.
 */
PyObject *g__pydict_streams = NULL;

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
     *
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
                      int num_events,
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
    if (!(event_path_list && event_mask_list))
        {
            return NULL;
        }

    /* Convert event paths and masks into python lists. */
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
                    /* Set exception information telling python that we could not execute the callback function. */
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
static PyObject *
pyfsevents_loop (PyObject *self,
                 PyObject *args)
{
    PyObject *thread = NULL;
    PyObject *value = NULL;

    if (!PyArg_ParseTuple(args, "O:loop", &thread))
        {
            return NULL;
        }

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

    if (PyErr_Occurred())
        {
            return NULL;
        }


    Py_INCREF(Py_None);
    return Py_None;
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
static PyObject *
pyfsevents_schedule (PyObject *self,
                     PyObject *args)
{

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
static PyMethodDef module_methods[] = {
    {"loop", pyfsevents_loop, METH_VARARGS, NULL},
    {"stop", pyfsevents_stop, METH_O, NULL},
    {"schedule", pyfsevents_schedule, METH_VARARGS, NULL},
    {"unschedule", pyfsevents_unschedule, METH_O, NULL},
    {NULL},
};

/**
 * Module documentation.
 */
static const char MODULE_DOCUMENTATION[] = "Low-level FSEvents interface.";

/**
 * Initialize the _fsevents module.
 *
 *
 */
PyMODINIT_FUNC init_fsevents(void){
    PyObject *module = Py_InitModule3("_fsevents", module_methods, MODULE_DOCUMENTATION);
    PyModule_AddIntConstant(module, "POLLIN", kCFFileDescriptorReadCallBack);
    PyModule_AddIntConstant(module, "POLLOUT", kCFFileDescriptorWriteCallBack);

    g__pydict_loops = PyDict_New();
    g__pydict_streams = PyDict_New();
}
