/**
 * _watchdog_util.c: Common routines and global data used by _watchdog_fsevents.
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
 * Dictionary that maps an emitter thread to a CFRunLoop.
 */
static PyObject *g__runloop_for_emitter = NULL;

/**
 * Dictionary that maps an ObservedWatch to a FSEvent stream.
 */
static PyObject *g__stream_for_watch = NULL;


void
WatchdogFSEvents_Init(void)
{
    g__runloop_for_emitter = PyDict_New();
    g__stream_for_watch = PyDict_New();
}

/**
 * Obtains the CFRunLoopRef for a given emitter thread.
 */
CFRunLoopRef
CFRunLoopForEmitter_GetItem(PyObject *emitter_thread)
{
    PyObject *py_runloop = PyDict_GetItem(g__runloop_for_emitter,
                                          emitter_thread);
    CFRunLoopRef runloop = PyCObject_AsVoidPtr(py_runloop);
    return runloop;
}

PyObject *
CFRunLoopForEmitter_SetItem(PyObject *emitter_thread, CFRunLoopRef runloop)
{
    PyObject *emitter_runloop = PyCObject_FromVoidPtr(runloop, PyMem_Free);
    if (0 > PyDict_SetItem(g__runloop_for_emitter,
                           emitter_thread,
                           emitter_runloop))
        {
            Py_DECREF(emitter_runloop);
            return NULL;
        }

    return emitter_runloop;
    //Py_INCREF(emitter_thread);
    //Py_INCREF(emitter_runloop);
}

int
CFRunLoopForEmitter_DelItem(PyObject *emitter_thread)
{
    return PyDict_DelItem(g__runloop_for_emitter, emitter_thread);
    /*if (0 == PyDict_DelItem(g__runloop_for_emitter, emitter_thread))
     {
     Py_DECREF(emitter_thread);
     Py_DECREF(emitter_runloop);
     }*/
}

int
CFRunLoopForEmitter_Contains(PyObject *emitter_thread)
{
    return PyDict_Contains(g__runloop_for_emitter, emitter_thread);
}

/**
 * Get runloop reference from emitter info data or current runloop.
 *
 * @param loops
 *      The dictionary of loops from which to obtain the loop
 *      for the given thread.
 * @return A pointer CFRunLookRef to a runloop.
 */
CFRunLoopRef
CFRunLoopForEmitter_GetItemOrDefault(PyObject *emitter_thread)
{
    PyObject *py_runloop = NULL;
    CFRunLoopRef runloop = NULL;

    py_runloop = PyDict_GetItem(g__runloop_for_emitter, emitter_thread);
    if (NULL == py_runloop)
        {
            runloop = CFRunLoopGetCurrent();
        }
    else
        {
            runloop = /*(CFRunLoopRef)*/PyCObject_AsVoidPtr(py_runloop);
        }

    return runloop;
}

PyObject *
StreamForWatch_SetItem(PyObject *watch, FSEventStreamRef stream)
{
    PyObject *py_stream = PyCObject_FromVoidPtr(stream, PyMem_Free);
    if (0 > PyDict_SetItem(g__stream_for_watch, watch, py_stream))
        {
            Py_DECREF(py_stream);
            return NULL;
        }
    return py_stream;
}

FSEventStreamRef
StreamForWatch_GetItem(PyObject *watch)
{
    PyObject *py_stream = PyDict_GetItem(g__stream_for_watch, watch);
    FSEventStreamRef stream = PyCObject_AsVoidPtr(py_stream);
    return stream;
}

int
StreamForWatch_DelItem(PyObject *watch)
{
    return PyDict_DelItem(g__stream_for_watch, watch);
}

FSEventStreamRef
StreamForWatch_PopItem(PyObject *watch)
{
    FSEventStreamRef stream = StreamForWatch_GetItem(watch);
    if (stream)
        {
            StreamForWatch_DelItem(watch);
        }
    return stream;
}

int
StreamForWatch_Contains(PyObject *watch)
{
    return PyDict_Contains(g__stream_for_watch, watch);
}

/**
 * Converts a Python string list to a CFMutableArray of CFStrings
 * and returns a reference to the array.
 *
 * @param py_string_list
 *      Pointer to a Python list of Python strings.
 * @return
 *      A pointer of type CFMutableArrayRef to a mutable array of CFString
 *      instances.
 */
CFMutableArrayRef
CFMutableArray_FromStringList(PyObject *py_string_list)
{
    CFMutableArrayRef cf_array_strings = NULL;
    const char *c_string = NULL;
    CFStringRef cf_string = NULL;
    Py_ssize_t i = 0;
    Py_ssize_t string_list_size = 0;

    string_list_size = PyList_Size(py_string_list);

    cf_array_strings = CFArrayCreateMutable(kCFAllocatorDefault,
                                            1,
                                            &kCFTypeArrayCallBacks);

    RETURN_NULL_IF_NULL(cf_array_strings);

    for (i = 0; i < string_list_size; ++i)
        {
            c_string = PyString_AS_STRING(PyList_GetItem(py_string_list, i));
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
 * @param py_path_list
 *      Python list of Python string paths.
 */
FSEventStreamRef
FSEventStream_Create(FSEventStreamInfo *stream_info, PyObject *py_path_list)
{
    CFMutableArrayRef cf_array_paths = NULL;
    FSEventStreamRef stream = NULL;

    /* Convert the path list to an array for OS X Api. */
    cf_array_paths = CFMutableArray_FromStringList(py_path_list);
    RETURN_NULL_IF_NULL(cf_array_paths);

    /* Create event stream. */
    FSEventStreamContext fs_stream_context =
            { 0, stream_info, NULL, NULL, NULL };
    stream
            = FSEventStreamCreate(kCFAllocatorDefault,
                                  (FSEventStreamCallback)
                                          & event_stream_handler,
                                  &fs_stream_context,
                                  cf_array_paths,
                                  kFSEventStreamEventIdSinceNow,
                                  FS_EVENT_STREAM_LATENCY,
                                  kFSEventStreamCreateFlagNoDefer);
    CFRelease(cf_array_paths);
    return stream;
}

/**
 * Handles streamed events and calls the callback defined in Python code.
 *
 * :param stream:
 *      The stream of events.
 * :param info:
 *      Meta information about the stream of events.
 * :param num_events:
 *      Number of events.
 * :param event_paths:
 *      The paths on which events occurred.
 * :param event_masks:
 *      The masks for each of the paths in `event_paths'.
 * :param event_ids:
 *      Event identifiers.
 */
void
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

    RETURN_IF_NOT(event_path_list && event_mask_list);

    /* Enumerate event paths and masks into Python lists. */
    for (i = 0; i < num_events; ++i)
        {
            event_path = PyString_FromString(event_paths[i]);
            event_mask = PyInt_FromLong(event_masks[i]);
            if (!(event_mask && event_path))
                {
                    Py_DECREF(event_path_list);
                    Py_DECREF(event_mask_list);
                    return;
                }
            PyList_SET_ITEM(event_path_list, i, event_path);
            PyList_SET_ITEM(event_mask_list, i, event_mask);
        }

    /* Call the callback event handler function with the enlisted event masks
     * and paths as arguments. On failure check whether an error occurred and
     * stop this instance of the runloop.
     */
    if (NULL == PyObject_CallFunction(stream_info->callback_event_handler,
                                      "OO",
                                      event_path_list,
                                      event_mask_list))
        {
            /* An exception may have occurred. */
            if (!PyErr_Occurred())
                {
                    /* If one didn't occur, raise an exception informing that
                     * we could not execute the
                     * callback function. */
                    PyErr_SetString(PyExc_ValueError,
                                    ERROR_MESSAGE_CANNOT_CALL_CALLBACK);
                }

            /* Stop listening for events. */
            CFRunLoopStop(stream_info->loop);
        }

    /* Restore original thread state and release lock. */
    PyThreadState_Swap(saved_thread_state);
    PyEval_ReleaseLock();
}

