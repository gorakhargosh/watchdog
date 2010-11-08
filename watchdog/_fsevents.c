#include "Python.h"
#include <CoreFoundation/CoreFoundation.h>
#include <CoreServices/CoreServices.h>
#include <signal.h>
#include <limits.h>

#if PY_VERSION_HEX < 0x02050000 && !defined(PY_SSIZE_T_MIN)
typedef int Py_ssize_t;
#define PY_SSIZE_T_MAX INT_MAX
#define PY_SSIZE_T_MIN INT_MIN
#endif /* PY_VERSION_HEX && !PY_SSIZE_T_MIN */

/**
 * Error messages.
 */
const char callback_error_message[] = "Unable to call callback function.";

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
    PyObject *callback;
    FSEventStreamRef stream;
    CFRunLoopRef loop;
    PyThreadState *state;
} FSEventStreamInfo;


/**
 * Does something.
 *
 * @param stream
 * @param info
 * @param num_events
 * @param event_paths
 * @param event_masks
 * @param event_ids
 *
 * @synchronized()
 */
static void
_handler (FSEventStreamRef stream,
          FSEventStreamInfo *info,
          int num_events,
          const char *const event_paths[],
          const FSEventStreamEventFlags *event_masks,
          const uint64_t *event_ids)
{
    PyThreadState *saved_thread_state = NULL;

    PyEval_AcquireLock();
    //saved_thread_state = PyThreadState_Swap(info->state);




    //PyThreadState_Swap(saved_thread_state);
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
pyfsevents_loop (PyObject *self, PyObject *args)
{

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
pyfsevents_schedule (PyObject *self, PyObject *args)
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
pyfsevents_unschedule(PyObject *self, PyObject *stream)
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
pyfsevents_stop(PyObject *self, PyObject *thread)
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
static char module_documentation[] = "Low-level FSEvents interface.";

/**
 * Initialize the _fsevents module.
 *
 *
 */
PyMODINIT_FUNC init_fsevents(void){
    PyObject *module = Py_InitModule3("_fsevents", module_methods, module_documentation);
    PyModule_AddIntConstant(module, "POLLIN", kCFFileDescriptorReadCallBack);
    PyModule_AddIntConstant(module, "POLLOUT", kCFFileDescriptorWriteCallBack);

    g__pydict_loops = PyDict_New();
    g__pydict_streams = PyDict_New();
}
