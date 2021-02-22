/**
 * watchdog_fsevents.c: Python-C bridge to the OS X FSEvents API.
 *
 * Copyright 2010 Malthe Borch <mborch@gmail.com>
 * Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
 * Copyright 2012 Google, Inc & contributors.
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
#include <Availability.h>
#include <CoreFoundation/CoreFoundation.h>
#include <CoreServices/CoreServices.h>
#include <stdlib.h>
#include <signal.h>


/* Compatibility; since fsevents won't set these on earlier macOS versions the properties will always be False */
#if MAC_OS_X_VERSION_MAX_ALLOWED < MAC_OS_X_VERSION_10_13
#error Watchdog module requires at least macOS 10.13
#endif

/* Convenience macros to make code more readable. */
#define G_NOT(o)                        !o
#define G_IS_NULL(o)                    o == NULL
#define G_IS_NOT_NULL(o)                o != NULL
#define G_RETURN_NULL_IF_NULL(o)        do { if (NULL == o) { return NULL; } } while (0)
#define G_RETURN_NULL_IF(condition)     do { if (condition) { return NULL; } } while (0)
#define G_RETURN_NULL_IF_NOT(condition) do { if (!condition) { return NULL; } } while (0)
#define G_RETURN_IF(condition)          do { if (condition) { return; } } while (0)
#define G_RETURN_IF_NOT(condition)      do { if (!condition) { return; } } while (0)
#define UNUSED(x)                       (void)x

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
     *    def python_callback(event_paths, event_inodes, event_flags, event_ids):
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
 * NativeEvent type so that we don't need to expose the FSEvents constants to Python land
 */
typedef struct {
    PyObject_HEAD
    const char *path;
    PyObject *inode;
    FSEventStreamEventFlags flags;
    FSEventStreamEventId id;
} NativeEventObject;

PyObject* NativeEventRepr(PyObject* instance) {
    NativeEventObject *self = (NativeEventObject*)instance;

    return PyUnicode_FromFormat(
        "NativeEvent(path=\"%s\", inode=%S, flags=%x, id=%llu)",
        self->path,
        self->inode,
        self->flags,
        self->id
    );
}

PyObject* NativeEventTypeFlags(PyObject* instance, void* closure)
{
    UNUSED(closure);
    NativeEventObject *self = (NativeEventObject*)instance;
    return PyLong_FromLong(self->flags);
}

PyObject* NativeEventTypePath(PyObject* instance, void* closure)
{
    UNUSED(closure);
    NativeEventObject *self = (NativeEventObject*)instance;
    return PyUnicode_FromString(self->path);
}

PyObject* NativeEventTypeInode(PyObject* instance, void* closure)
{
    UNUSED(closure);
    NativeEventObject *self = (NativeEventObject*)instance;
    Py_INCREF(self->inode);
    return self->inode;
}

PyObject* NativeEventTypeID(PyObject* instance, void* closure)
{
    UNUSED(closure);
    NativeEventObject *self = (NativeEventObject*)instance;
    return PyLong_FromLong(self->id);
}

PyObject* NativeEventTypeIsCoalesced(PyObject* instance, void* closure)
{
    UNUSED(closure);
    NativeEventObject *self = (NativeEventObject*)instance;

    // if any of these bitmasks match then we have a coalesced event and need to do sys calls to figure out what happened
    FSEventStreamEventFlags coalesced_masks[] = {
        kFSEventStreamEventFlagItemCreated | kFSEventStreamEventFlagItemRemoved,
        kFSEventStreamEventFlagItemCreated | kFSEventStreamEventFlagItemRenamed,
        kFSEventStreamEventFlagItemRemoved | kFSEventStreamEventFlagItemRenamed,
    };
    for (size_t i = 0; i < sizeof(coalesced_masks) / sizeof(FSEventStreamEventFlags); ++i) {
        if ((self->flags & coalesced_masks[i]) == coalesced_masks[i]) {
            Py_RETURN_TRUE;
        }
    }

    Py_RETURN_FALSE;
}

#define FLAG_PROPERTY(suffix, flag) \
    PyObject* NativeEventType##suffix(PyObject* instance, void* closure) \
    { \
        UNUSED(closure); \
        NativeEventObject *self = (NativeEventObject*)instance; \
        if (self->flags & flag) { \
            Py_RETURN_TRUE; \
        } \
        Py_RETURN_FALSE; \
    }

FLAG_PROPERTY(IsMustScanSubDirs, kFSEventStreamEventFlagMustScanSubDirs)
FLAG_PROPERTY(IsUserDropped, kFSEventStreamEventFlagUserDropped)
FLAG_PROPERTY(IsKernelDropped, kFSEventStreamEventFlagKernelDropped)
FLAG_PROPERTY(IsEventIdsWrapped, kFSEventStreamEventFlagEventIdsWrapped)
FLAG_PROPERTY(IsHistoryDone, kFSEventStreamEventFlagHistoryDone)
FLAG_PROPERTY(IsRootChanged, kFSEventStreamEventFlagRootChanged)
FLAG_PROPERTY(IsMount, kFSEventStreamEventFlagMount)
FLAG_PROPERTY(IsUnmount, kFSEventStreamEventFlagUnmount)
FLAG_PROPERTY(IsCreated, kFSEventStreamEventFlagItemCreated)
FLAG_PROPERTY(IsRemoved, kFSEventStreamEventFlagItemRemoved)
FLAG_PROPERTY(IsInodeMetaMod, kFSEventStreamEventFlagItemInodeMetaMod)
FLAG_PROPERTY(IsRenamed, kFSEventStreamEventFlagItemRenamed)
FLAG_PROPERTY(IsModified, kFSEventStreamEventFlagItemModified)
FLAG_PROPERTY(IsItemFinderInfoMod, kFSEventStreamEventFlagItemFinderInfoMod)
FLAG_PROPERTY(IsChangeOwner, kFSEventStreamEventFlagItemChangeOwner)
FLAG_PROPERTY(IsXattrMod, kFSEventStreamEventFlagItemXattrMod)
FLAG_PROPERTY(IsFile, kFSEventStreamEventFlagItemIsFile)
FLAG_PROPERTY(IsDirectory, kFSEventStreamEventFlagItemIsDir)
FLAG_PROPERTY(IsSymlink, kFSEventStreamEventFlagItemIsSymlink)
FLAG_PROPERTY(IsOwnEvent, kFSEventStreamEventFlagOwnEvent)
FLAG_PROPERTY(IsHardlink, kFSEventStreamEventFlagItemIsHardlink)
FLAG_PROPERTY(IsLastHardlink, kFSEventStreamEventFlagItemIsLastHardlink)
FLAG_PROPERTY(IsCloned, kFSEventStreamEventFlagItemCloned)

static int NativeEventInit(NativeEventObject *self, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {"path", "inode", "flags", "id", NULL};

    self->inode = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|sOIL", kwlist, &self->path, &self->inode, &self->flags, &self->id)) {
        return -1;
    }

    Py_INCREF(self->inode);

    return 0;
}

static void NativeEventDealloc(NativeEventObject *self) {
    Py_XDECREF(self->inode);
}

static PyGetSetDef NativeEventProperties[] = {
    {"flags", NativeEventTypeFlags, NULL, "The raw mask of flags as returend by FSEvents", NULL},
    {"path", NativeEventTypePath, NULL, "The path for which this event was generated", NULL},
    {"inode", NativeEventTypeInode, NULL, "The inode for which this event was generated", NULL},
    {"event_id", NativeEventTypeID, NULL, "The id of the generated event", NULL},
    {"is_coalesced", NativeEventTypeIsCoalesced, NULL, "True if multiple ambiguous changes to the monitored path happened", NULL},
    {"must_scan_subdirs", NativeEventTypeIsMustScanSubDirs, NULL, "True if application must rescan all subdirectories", NULL},
    {"is_user_dropped", NativeEventTypeIsUserDropped, NULL, "True if a failure during event buffering occured", NULL},
    {"is_kernel_dropped", NativeEventTypeIsKernelDropped, NULL, "True if a failure during event buffering occured", NULL},
    {"is_event_ids_wrapped", NativeEventTypeIsEventIdsWrapped, NULL, "True if event_id wrapped around", NULL},
    {"is_history_done", NativeEventTypeIsHistoryDone, NULL, "True if all historical events are done", NULL},
    {"is_root_changed", NativeEventTypeIsRootChanged, NULL, "True if a change to one of the directories along the path to one of the directories you watch occurred", NULL},
    {"is_mount", NativeEventTypeIsMount, NULL, "True if a volume is mounted underneath one of the paths being monitored", NULL},
    {"is_unmount", NativeEventTypeIsUnmount, NULL, "True if a volume is unmounted underneath one of the paths being monitored", NULL},
    {"is_created", NativeEventTypeIsCreated, NULL, "True if self.path was created on the filesystem", NULL},
    {"is_removed", NativeEventTypeIsRemoved, NULL, "True if self.path was removed from the filesystem", NULL},
    {"is_inode_meta_mod", NativeEventTypeIsInodeMetaMod, NULL, "True if meta data for self.path was modified ", NULL},
    {"is_renamed", NativeEventTypeIsRenamed, NULL, "True if self.path was renamed on the filesystem", NULL},
    {"is_modified", NativeEventTypeIsModified, NULL, "True if self.path was modified", NULL},
    {"is_item_finder_info_modified", NativeEventTypeIsItemFinderInfoMod, NULL, "True if FinderInfo for self.path was modified", NULL},
    {"is_owner_change", NativeEventTypeIsChangeOwner, NULL, "True if self.path had its ownership changed", NULL},
    {"is_xattr_mod", NativeEventTypeIsXattrMod, NULL, "True if extended attributes for self.path were modified ", NULL},
    {"is_file", NativeEventTypeIsFile, NULL, "True if self.path is a file", NULL},
    {"is_directory", NativeEventTypeIsDirectory, NULL, "True if self.path is a directory", NULL},
    {"is_symlink", NativeEventTypeIsSymlink, NULL, "True if self.path is a symbolic link", NULL},
    {"is_own_event", NativeEventTypeIsOwnEvent, NULL, "True if the event originated from our own process", NULL},
    {"is_hardlink", NativeEventTypeIsHardlink, NULL, "True if self.path is a hard link", NULL},
    {"is_last_hardlink", NativeEventTypeIsLastHardlink, NULL, "True if self.path was the last hard link", NULL},
    {"is_cloned", NativeEventTypeIsCloned, NULL, "True if self.path is a clone or was cloned", NULL},
    {NULL, NULL, NULL, NULL, NULL},
};


static PyTypeObject NativeEventType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_watchdog_fsevents.NativeEvent",
    .tp_doc = "A wrapper around native FSEvents events",
    .tp_basicsize = sizeof(NativeEventObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = PyType_GenericNew,
    .tp_getset = NativeEventProperties,
    .tp_init = (initproc) NativeEventInit,
    .tp_repr = (reprfunc) NativeEventRepr,
    .tp_dealloc = (destructor) NativeEventDealloc,
};


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
 * PyCapsule destructor.
 */
static void watchdog_pycapsule_destructor(PyObject *ptr)
{
    void *p = PyCapsule_GetPointer(ptr, NULL);
    if (p) {
        PyMem_Free(p);
    }
}



/**
 * Converts a ``CFStringRef`` to a Python string object.
 *
 * :param cf_string:
 *      A ``CFStringRef``.
 * :returns:
 *      A Python unicode or utf-8 encoded bytestring object.
 */
PyObject * CFString_AsPyUnicode(CFStringRef cf_string_ref)
{

    if (G_IS_NULL(cf_string_ref)) {
        return PyUnicode_FromString("");
    }

    PyObject *py_string;

    const char *c_string_ptr = CFStringGetCStringPtr(cf_string_ref, kCFStringEncodingUTF8);

    if (G_IS_NULL(c_string_ptr)) {
        CFIndex length = CFStringGetLength(cf_string_ref);
        CFIndex max_size = CFStringGetMaximumSizeForEncoding(length, kCFStringEncodingUTF8) + 1;
        char *buffer = (char *)malloc(max_size);
        if (CFStringGetCString(cf_string_ref, buffer, max_size, kCFStringEncodingUTF8)) {
            py_string = PyUnicode_FromString(buffer);
        }
        else {
            py_string = PyUnicode_FromString("");
        }
        free(buffer);
    } else {
        py_string = PyUnicode_FromString(c_string_ptr);
    }

    return py_string;

}

/**
 * Converts a ``CFNumberRef`` to a Python string object.
 *
 * :param cf_number:
 *      A ``CFNumberRef``.
 * :returns:
 *      A Python unicode or utf-8 encoded bytestring object.
 */
PyObject * CFNumberRef_AsPyLong(CFNumberRef cf_number)
{
    long c_int;
    PyObject *py_long;

    CFNumberGetValue(cf_number, kCFNumberSInt64Type, &c_int);

    py_long = PyLong_FromLong(c_int);

    return py_long;
}


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
                               CFArrayRef                     event_path_info_array_ref,
                               const FSEventStreamEventFlags  event_flags[],
                               const FSEventStreamEventId     event_ids[])
{
    UNUSED(stream_ref);
    size_t i = 0;
    CFDictionaryRef path_info_dict;
    CFStringRef cf_path;
    CFNumberRef cf_inode;
    PyObject *callback_result = NULL;
    PyObject *path = NULL;
    PyObject *inode = NULL;
    PyObject *id = NULL;
    PyObject *flags = NULL;
    PyObject *py_event_flags = NULL;
    PyObject *py_event_ids = NULL;
    PyObject *py_event_paths = NULL;
    PyObject *py_event_inodes = NULL;
    PyThreadState *saved_thread_state = NULL;

    /* Acquire interpreter lock and save original thread state. */
    PyGILState_STATE gil_state = PyGILState_Ensure();
    saved_thread_state = PyThreadState_Swap(stream_callback_info_ref->thread_state);

    /* Convert event flags and paths to Python ints and strings. */
    py_event_paths = PyList_New(num_events);
    py_event_inodes = PyList_New(num_events);
    py_event_flags = PyList_New(num_events);
    py_event_ids = PyList_New(num_events);
    if (G_NOT(py_event_paths && py_event_inodes && py_event_flags && py_event_ids))
    {
        Py_XDECREF(py_event_paths);
        Py_XDECREF(py_event_inodes);
        Py_XDECREF(py_event_ids);
        Py_XDECREF(py_event_flags);
        return /*NULL*/;
    }
    for (i = 0; i < num_events; ++i)
    {
        id = PyLong_FromLongLong(event_ids[i]);
        flags = PyLong_FromLong(event_flags[i]);

        path_info_dict = CFArrayGetValueAtIndex(event_path_info_array_ref, i);
        cf_path = CFDictionaryGetValue(path_info_dict, kFSEventStreamEventExtendedDataPathKey);
        cf_inode = CFDictionaryGetValue(path_info_dict, kFSEventStreamEventExtendedFileIDKey);

        path = CFString_AsPyUnicode(cf_path);

        if (G_IS_NOT_NULL(cf_inode)) {
            inode = CFNumberRef_AsPyLong(cf_inode);
        } else {
            Py_INCREF(Py_None);
            inode = Py_None;
        }

        if (G_NOT(path && inode && flags && id))
        {
            Py_DECREF(py_event_paths);
            Py_DECREF(py_event_inodes);
            Py_DECREF(py_event_ids);
            Py_DECREF(py_event_flags);
            return /*NULL*/;
        }
        PyList_SET_ITEM(py_event_paths, i, path);
        PyList_SET_ITEM(py_event_inodes, i, inode);
        PyList_SET_ITEM(py_event_flags, i, flags);
        PyList_SET_ITEM(py_event_ids, i, id);
    }

    /* Call the Python callback function supplied by the stream information
     * struct. The Python callback function should accept two arguments,
     * both being Python lists:
     *
     *    def python_callback(event_paths, event_flags, event_ids):
     *        pass
     */
    callback_result = \
        PyObject_CallFunction(stream_callback_info_ref->python_callback,
                              "OOOO", py_event_paths, py_event_inodes, py_event_flags, py_event_ids);
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
 * Converts a Python string object to an UTF-8 encoded ``CFStringRef``.
 *
 * :param py_string:
 *      A Python unicode or utf-8 encoded bytestring object.
 * :returns:
 *      A new ``CFStringRef`` with the contents of ``py_string``, or ``NULL`` if an error occurred.
 */
CFStringRef PyString_AsUTF8EncodedCFStringRef(PyObject *py_string)
{
    CFStringRef cf_string = NULL;

    if (PyUnicode_Check(py_string)) {
        PyObject* helper = PyUnicode_AsUTF8String(py_string);
        if (!helper) {
            return NULL;
        }
        cf_string = CFStringCreateWithCString(kCFAllocatorDefault, PyBytes_AS_STRING(helper), kCFStringEncodingUTF8);
        Py_DECREF(helper);
    } else if (PyBytes_Check(py_string)) {
        PyObject *utf8 = PyUnicode_FromEncodedObject(py_string, NULL, "strict");
        if (!utf8) {
            return NULL;
        }
        Py_DECREF(utf8);
        cf_string = CFStringCreateWithCString(kCFAllocatorDefault, PyBytes_AS_STRING(py_string), kCFStringEncodingUTF8);
    } else {
        PyErr_SetString(PyExc_TypeError, "Path to watch must be a string or a UTF-8 encoded bytes object.");
        return NULL;
    }

    return cf_string;
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
        cf_string = PyString_AsUTF8EncodedCFStringRef(py_string);
        G_RETURN_NULL_IF_NULL(cf_string);
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
                                     kFSEventStreamCreateFlagNoDefer
                                     | kFSEventStreamCreateFlagFileEvents
                                     | kFSEventStreamCreateFlagWatchRoot
                                     | kFSEventStreamCreateFlagUseExtendedData
                                     | kFSEventStreamCreateFlagUseCFTypes);
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
        def callback(paths, flags, ids):\n\
            for path, flag, event_id in zip(paths, flags, ids):\n\
                print(\"%d: %s=%ul\" % (event_id, path, flag))\n\
:param paths:\n\
    A list of paths to monitor.\n");
static PyObject *
watchdog_add_watch(PyObject *self, PyObject *args)
{
    UNUSED(self);
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
    if(PyDict_Contains(watch_to_stream, watch) == 1) {
        PyErr_Format(PyExc_RuntimeError, "Cannot add watch %S - it is already scheduled", watch);
        return NULL;
    }

    /* Create an instance of the callback information structure. */
    stream_callback_info_ref = PyMem_New(StreamCallbackInfo, 1);
    if(stream_callback_info_ref == NULL) {
        PyErr_SetString(PyExc_SystemError, "Failed allocating stream callback info");
        return NULL;
    }

    /* Create an FSEvent stream and
     * Save the stream reference to the global watch-to-stream dictionary. */
    stream_ref = watchdog_FSEventStreamCreate(stream_callback_info_ref,
                                              paths_to_watch,
                                              (FSEventStreamCallback) &watchdog_FSEventStreamCallback);
    if (!stream_ref) {
        PyMem_Del(stream_callback_info_ref);
        PyErr_SetString(PyExc_RuntimeError, "Failed creating fsevent stream");
        return NULL;
    }
    value = PyCapsule_New(stream_ref, NULL, watchdog_pycapsule_destructor);
    if (!value || !PyCapsule_IsValid(value, NULL)) {
        PyMem_Del(stream_callback_info_ref);
        FSEventStreamInvalidate(stream_ref);
        FSEventStreamRelease(stream_ref);
        return NULL;
    }
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
        run_loop_ref = PyCapsule_GetPointer(value, NULL);
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
        // There's no documentation on _why_ this might fail - "it ought to always succeed". But if it fails the
        // documentation says to "fall back to performing recursive scans of the directories [...] as appropriate".
        PyErr_SetString(PyExc_SystemError, "Cannot start fsevents stream. Use a kqueue or polling observer instead.");
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
    UNUSED(self);
    CFRunLoopRef run_loop_ref = NULL;
    PyObject *emitter_thread = NULL;
    PyObject *value = NULL;

    G_RETURN_NULL_IF_NOT(PyArg_ParseTuple(args, "O:loop", &emitter_thread));

// PyEval_InitThreads() does nothing as of Python 3.7 and is deprecated in 3.9.
// https://docs.python.org/3/c-api/init.html#c.PyEval_InitThreads
#if PY_VERSION_HEX < 0x030700f0
    PyEval_InitThreads();
#endif

    /* Allocate information and store thread state. */
    value = PyDict_GetItem(thread_to_run_loop, emitter_thread);
    if (G_IS_NULL(value))
    {
        run_loop_ref = CFRunLoopGetCurrent();
        value = PyCapsule_New(run_loop_ref, NULL, watchdog_pycapsule_destructor);
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

PyDoc_STRVAR(watchdog_flush_events__doc__,
        MODULE_NAME ".flush_events(watch) -> None\n\
Flushes events for the watch.\n\n\
:param watch:\n\
    The watch to flush.\n");
static PyObject *
watchdog_flush_events(PyObject *self, PyObject *watch)
{
    UNUSED(self);
    PyObject *value = PyDict_GetItem(watch_to_stream, watch);

    FSEventStreamRef stream_ref = PyCapsule_GetPointer(value, NULL);

    FSEventStreamFlushSync(stream_ref);

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
    UNUSED(self);
    PyObject *value = PyDict_GetItem(watch_to_stream, watch);
    PyDict_DelItem(watch_to_stream, watch);

    FSEventStreamRef stream_ref = PyCapsule_GetPointer(value, NULL);

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
    UNUSED(self);
    PyObject *value = PyDict_GetItem(thread_to_run_loop, emitter_thread);
    if (G_IS_NULL(value)) {
      goto success;
    }

    CFRunLoopRef run_loop_ref = PyCapsule_GetPointer(value, NULL);
    G_RETURN_NULL_IF(PyErr_Occurred());

    /* Stop the run loop. */
    if (G_IS_NOT_NULL(run_loop_ref))
    {
        CFRunLoopStop(run_loop_ref);
    }

 success:
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
    {"flush_events", watchdog_flush_events, METH_O,       watchdog_flush_events__doc__},
    {"remove_watch", watchdog_remove_watch, METH_O,       watchdog_remove_watch__doc__},

    /* Aliases for compatibility with macfsevents. */
    {"schedule",     watchdog_add_watch,    METH_VARARGS, "Alias for add_watch."},
    {"loop",         watchdog_read_events,  METH_VARARGS, "Alias for read_events."},
    {"unschedule",   watchdog_remove_watch, METH_O,       "Alias for remove_watch."},

    {"stop",         watchdog_stop,         METH_O,       watchdog_stop__doc__},

    {NULL, NULL, 0, NULL},
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

static struct PyModuleDef watchdog_fsevents_module = {
    PyModuleDef_HEAD_INIT,
    MODULE_NAME,
    watchdog_fsevents_module__doc__,
    -1,
    watchdog_fsevents_methods,
    NULL,  /* m_slots */
    NULL,  /* m_traverse */
    0,     /* m_clear */
    NULL   /* m_free */
};

/**
 * Initialize the Python 3.x module.
 */
PyMODINIT_FUNC
PyInit__watchdog_fsevents(void){
    G_RETURN_NULL_IF(PyType_Ready(&NativeEventType) < 0);
    PyObject *module = PyModule_Create(&watchdog_fsevents_module);
    G_RETURN_NULL_IF_NULL(module);
    Py_INCREF(&NativeEventType);
    if (PyModule_AddObject(module, "NativeEvent", (PyObject*)&NativeEventType) < 0) {
        Py_DECREF(&NativeEventType);
        Py_DECREF(module);
        return NULL;
    }
    watchdog_module_add_attributes(module);
    watchdog_module_init();
    return module;
}
