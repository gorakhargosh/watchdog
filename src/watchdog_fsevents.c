/**
 * watchdog_fsevents.c: Python-C bridge to the OS X FSEvents API.
 *
 * Copyright 2018-2026 Mickaël Schoentgen & contributors
 * Copyright 2012-2018 Google, Inc.
 * Copyright 2011-2012 Yesudeep Mangalapilly <yesudeep@gmail.com>
 * Copyright 2010-2011 Malthe Borch <mborch@gmail.com>
 */


#include <Python.h>
#include <Availability.h>
#include <CoreFoundation/CoreFoundation.h>
#include <CoreServices/CoreServices.h>
#include <stdlib.h>
#include "pythoncapi_compat.h"


/* Compatibility; since fsevents won't set these on earlier macOS versions the properties will always be False */
#if MAC_OS_X_VERSION_MAX_ALLOWED < MAC_OS_X_VERSION_10_13
#error Watchdog module requires at least macOS 10.13
#endif

#define UNUSED(x)                       (void)x

/* Other information. */
#define MODULE_NAME  "_watchdog_fsevents"

/**
 * NativeEvent type so that we don't need to expose the FSEvents constants to Python land
 */
typedef struct {
    PyObject_HEAD
    PyObject *path;
    PyObject *inode;
    FSEventStreamEventFlags flags;
    FSEventStreamEventId id;
} NativeEventObject;

PyObject* NativeEventRepr(PyObject* instance) {
    NativeEventObject *self = (NativeEventObject*)instance;

    return PyUnicode_FromFormat(
        "NativeEvent(path=\"%S\", inode=%S, flags=%x, id=%llu)",
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
    return Py_NewRef(self->path);
}

PyObject* NativeEventTypeInode(PyObject* instance, void* closure)
{
    UNUSED(closure);
    NativeEventObject *self = (NativeEventObject*)instance;
    return Py_NewRef(self->inode);
}

PyObject* NativeEventTypeID(PyObject* instance, void* closure)
{
    UNUSED(closure);
    NativeEventObject *self = (NativeEventObject*)instance;
    return PyLong_FromUnsignedLongLong(self->id);
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

static PyObject *NativeEventNew(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {"path", "inode", "flags", "id", NULL};
    PyObject *path, *inode;
    unsigned int flags;
    unsigned long long id;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "UOIK:NativeEvent", kwlist, &path, &inode, &flags, &id)) {
        return NULL;
    }

    NativeEventObject *self = (NativeEventObject *)type->tp_alloc(type, 0);
    if (self == NULL) {
        return NULL;
    }
    self->path = Py_NewRef(path);
    self->inode = Py_NewRef(inode);
    self->flags = flags;
    self->id = id;
    return (PyObject *)self;
}

static int NativeEventTraverse(NativeEventObject *self, visitproc visit, void *arg) {
    Py_VISIT(self->path);
    Py_VISIT(self->inode);
    return 0;
}

static int NativeEventClear(NativeEventObject *self) {
    Py_CLEAR(self->path);
    Py_CLEAR(self->inode);
    return 0;
}

static void NativeEventDealloc(NativeEventObject *self) {
    PyObject_GC_UnTrack(self);
    NativeEventClear(self);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyGetSetDef NativeEventProperties[] = {
    {"flags", NativeEventTypeFlags, NULL, "The raw mask of flags as returned by FSEvents", NULL},
    {"path", NativeEventTypePath, NULL, "The path for which this event was generated", NULL},
    {"inode", NativeEventTypeInode, NULL, "The inode for which this event was generated", NULL},
    {"event_id", NativeEventTypeID, NULL, "The id of the generated event", NULL},
    {"is_coalesced", NativeEventTypeIsCoalesced, NULL, "True if multiple ambiguous changes to the monitored path happened", NULL},
    {"must_scan_subdirs", NativeEventTypeIsMustScanSubDirs, NULL, "True if application must rescan all subdirectories", NULL},
    {"is_user_dropped", NativeEventTypeIsUserDropped, NULL, "True if a failure during event buffering occurred", NULL},
    {"is_kernel_dropped", NativeEventTypeIsKernelDropped, NULL, "True if a failure during event buffering occurred", NULL},
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
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE | Py_TPFLAGS_HAVE_GC,
    .tp_new = NativeEventNew,
    .tp_getset = NativeEventProperties,
    .tp_traverse = (traverseproc) NativeEventTraverse,
    .tp_clear = (inquiry) NativeEventClear,
    .tp_repr = (reprfunc) NativeEventRepr,
    .tp_dealloc = (destructor) NativeEventDealloc,
};


/* Convert a native event path to Python. */
static PyObject *
CFString_AsPyUnicode(CFStringRef path)
{
    if (path == NULL) {
        return PyUnicode_FromString("");
    }
    const char *utf8 = CFStringGetCStringPtr(path, kCFStringEncodingUTF8);
    if (utf8 != NULL) {
        return PyUnicode_FromString(utf8);
    }

    CFIndex size = CFStringGetMaximumSizeForEncoding(CFStringGetLength(path), kCFStringEncodingUTF8) + 1;
    char *buffer = malloc(size);
    if (buffer == NULL) {
        return PyErr_NoMemory();
    }
    PyObject *result = CFStringGetCString(path, buffer, size, kCFStringEncodingUTF8)
        ? PyUnicode_FromString(buffer) : PyUnicode_FromString("");
    free(buffer);
    return result;
}

static PyObject *
CFNumberRef_AsPyLong(CFNumberRef number)
{
    long value;
    CFNumberGetValue(number, kCFNumberSInt64Type, &value);
    return PyLong_FromLong(value);
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

/* Copy a snapshot of the caller's mutable list into native storage. */
static CFArrayRef
paths_to_cf_array(PyObject *paths)
{
    PyObject *snapshot = PyList_AsTuple(paths);
    if (snapshot == NULL) {
        return NULL;
    }
    CFMutableArrayRef array = CFArrayCreateMutable(kCFAllocatorDefault, PyTuple_GET_SIZE(snapshot),
                                                  &kCFTypeArrayCallBacks);
    if (array == NULL) {
        goto error;
    }
    for (Py_ssize_t i = 0; i < PyTuple_GET_SIZE(snapshot); ++i) {
        CFStringRef path = PyString_AsUTF8EncodedCFStringRef(PyTuple_GET_ITEM(snapshot, i));
        if (path == NULL) {
            CFRelease(array);
            goto error;
        }
        CFArrayAppendValue(array, path);
        CFRelease(path);
    }
    Py_DECREF(snapshot);
    return array;

error:
    Py_DECREF(snapshot);
    if (!PyErr_Occurred()) {
        PyErr_NoMemory();
    }
    return NULL;
}


typedef struct {
    PyObject_HEAD
#if PY_VERSION_HEX >= 0x030D0000
    PyMutex           mutex;  /* Zero-initialized by tp_alloc. */
#else
    PyThread_type_lock mutex;
#endif
    int               stopped;
    CFRunLoopRef      run_loop;
    CFArrayRef        paths;
    PyObject         *callback;
} StreamObject;


/* Call with an attached thread state; keep Python calls outside the lock. */
static void
stream_lock(StreamObject *self)
{
#if PY_VERSION_HEX >= 0x030D0000
    PyMutex_Lock(&self->mutex);
#else
    if (!PyThread_acquire_lock(self->mutex, NOWAIT_LOCK)) {
        /* Like PyMutex_Lock, detach while waiting for another thread. */
        Py_BEGIN_ALLOW_THREADS;
        PyThread_acquire_lock(self->mutex, WAIT_LOCK);
        Py_END_ALLOW_THREADS;
    }
#endif
}

static void
stream_unlock(StreamObject *self)
{
#if PY_VERSION_HEX >= 0x030D0000
    PyMutex_Unlock(&self->mutex);
#else
    PyThread_release_lock(self->mutex);
#endif
}


static void
stream_stop(StreamObject *self)
{
    stream_lock(self);
    self->stopped = 1;
    CFRunLoopRef run_loop = self->run_loop;
    if (run_loop != NULL) {
        // as a block, not a bare CFRunLoopStop: a pending block also stops a loop that has not started yet
        CFRunLoopPerformBlock(run_loop, kCFRunLoopDefaultMode, ^{ CFRunLoopStop(run_loop); });
        CFRunLoopWakeUp(run_loop);
    }
    stream_unlock(self);
}


static void
watchdog_FSEventStreamCallback(ConstFSEventStreamRef          stream_ref,
                               void                          *info,
                               size_t                         num_events,
                               CFArrayRef                     event_path_info_array_ref,
                               const FSEventStreamEventFlags  event_flags[],
                               const FSEventStreamEventId     event_ids[])
{
    UNUSED(stream_ref);
    StreamObject *self = (StreamObject *)info;
    size_t i = 0;
    PyObject *callback_result = NULL;
    PyObject *py_event_flags = NULL;
    PyObject *py_event_ids = NULL;
    PyObject *py_event_paths = NULL;
    PyObject *py_event_inodes = NULL;

    PyGILState_STATE gil_state = PyGILState_Ensure();

    py_event_paths = PyList_New(num_events);
    py_event_inodes = PyList_New(num_events);
    py_event_flags = PyList_New(num_events);
    py_event_ids = PyList_New(num_events);
    if (!(py_event_paths && py_event_inodes && py_event_flags && py_event_ids)) {
        goto done;
    }
    for (i = 0; i < num_events; ++i)
    {
        PyObject *id = PyLong_FromUnsignedLongLong(event_ids[i]);
        PyObject *flags = PyLong_FromLong(event_flags[i]);

        CFDictionaryRef path_info_dict = CFArrayGetValueAtIndex(event_path_info_array_ref, i);
        CFStringRef cf_path = CFDictionaryGetValue(path_info_dict, kFSEventStreamEventExtendedDataPathKey);
        CFNumberRef cf_inode = CFDictionaryGetValue(path_info_dict, kFSEventStreamEventExtendedFileIDKey);

        PyObject *path = CFString_AsPyUnicode(cf_path);
        PyObject *inode = cf_inode != NULL ? CFNumberRef_AsPyLong(cf_inode) : Py_NewRef(Py_None);

        if (!(path && inode && flags && id))
        {
            Py_XDECREF(path);
            Py_XDECREF(inode);
            Py_XDECREF(flags);
            Py_XDECREF(id);
            goto done;
        }
        PyList_SET_ITEM(py_event_paths, i, path);
        PyList_SET_ITEM(py_event_inodes, i, inode);
        PyList_SET_ITEM(py_event_flags, i, flags);
        PyList_SET_ITEM(py_event_ids, i, id);
    }

    /* Call the Python callback function supplied to ``run()``:
     *
     *    def python_callback(event_paths, event_inodes, event_flags, event_ids):
     *        pass
     */
    callback_result = PyObject_CallFunction(self->callback, "OOOO",
                                            py_event_paths, py_event_inodes, py_event_flags, py_event_ids);

done:
    if (callback_result == NULL)
    {
        PyErr_WriteUnraisable(self->callback);
        stream_stop(self);
    }
    Py_XDECREF(callback_result);
    Py_XDECREF(py_event_paths);
    Py_XDECREF(py_event_inodes);
    Py_XDECREF(py_event_flags);
    Py_XDECREF(py_event_ids);

    PyGILState_Release(gil_state);
}


static PyObject *
Stream_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {"paths", NULL};
    PyObject *py_paths = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O!:Stream", kwlist, &PyList_Type, &py_paths)) {
        return NULL;
    }
    CFArrayRef paths = paths_to_cf_array(py_paths);
    if (paths == NULL) {
        return NULL;
    }
    StreamObject *self = (StreamObject *)type->tp_alloc(type, 0);
    if (self == NULL) {
        CFRelease(paths);
        return NULL;
    }
#if PY_VERSION_HEX < 0x030D0000
    self->mutex = PyThread_allocate_lock();
    if (self->mutex == NULL) {
        CFRelease(paths);
        type->tp_free((PyObject *)self);
        return PyErr_NoMemory();
    }
#endif
    self->stopped = 0;
    self->run_loop = NULL;
    self->paths = paths;
    self->callback = NULL;
    return (PyObject *)self;
}

static void
Stream_dealloc(StreamObject *self)
{
    CFRelease(self->paths);
    if (self->run_loop != NULL) {
        CFRelease(self->run_loop);
    }
    Py_XDECREF(self->callback);
#if PY_VERSION_HEX < 0x030D0000
    PyThread_free_lock(self->mutex);
#endif
    Py_TYPE(self)->tp_free((PyObject *)self);
}

PyDoc_STRVAR(Stream_run__doc__,
             "run(callback, started=None)\n\n\
Creates the FSEvents stream, schedules it on the calling thread's run loop and\n\
runs that loop until stop() is called. Returns immediately if stop() was already\n\
called. callback(paths, inodes, flags, ids) is invoked on the calling thread;\n\
started(), if given, is called once the stream has been started.");
static PyObject *
Stream_run(StreamObject *self, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {"callback", "started", NULL};
    PyObject *callback = NULL;
    PyObject *started = Py_None;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|O:run", kwlist, &callback, &started)) {
        return NULL;
    }
    if (!PyCallable_Check(callback)) {
        PyErr_SetString(PyExc_TypeError, "callback must be callable");
        return NULL;
    }
    CFRunLoopRef run_loop = CFRunLoopGetCurrent();

    stream_lock(self);
    if (self->stopped) {
        stream_unlock(self);
        Py_RETURN_NONE;
    }
    if (self->run_loop != NULL) {
        stream_unlock(self);
        PyErr_SetString(PyExc_RuntimeError, "Stream is already running");
        return NULL;
    }
    self->run_loop = (CFRunLoopRef)CFRetain(run_loop);
    stream_unlock(self);
    self->callback = Py_NewRef(callback);

    PyObject *result = NULL;
    FSEventStreamContext stream_context = {0, self, NULL, NULL, NULL};
    FSEventStreamRef stream_ref = FSEventStreamCreate(kCFAllocatorDefault,
                                                      (FSEventStreamCallback)&watchdog_FSEventStreamCallback,
                                                      &stream_context,
                                                      self->paths,
                                                      kFSEventStreamEventIdSinceNow,
                                                      0.01,
                                                      kFSEventStreamCreateFlagNoDefer
                                                      | kFSEventStreamCreateFlagFileEvents
                                                      | kFSEventStreamCreateFlagWatchRoot
                                                      | kFSEventStreamCreateFlagUseExtendedData
                                                      | kFSEventStreamCreateFlagUseCFTypes);
    if (stream_ref == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "Failed creating fsevent stream");
        goto finish;
    }
    FSEventStreamScheduleWithRunLoop(stream_ref, run_loop, kCFRunLoopDefaultMode);
    if (!FSEventStreamStart(stream_ref)) {
        PyErr_SetString(PyExc_SystemError, "Cannot start fsevents stream. Use a kqueue or polling observer instead.");
        goto invalidate;
    }
    if (started != Py_None) {
        PyObject *ready = PyObject_CallNoArgs(started);
        if (ready == NULL) {
            goto stop;
        }
        Py_DECREF(ready);
    }

    Py_BEGIN_ALLOW_THREADS;
    CFRunLoopRun();
    Py_END_ALLOW_THREADS;
    result = Py_NewRef(Py_None);

stop:
    FSEventStreamStop(stream_ref);
invalidate:
    FSEventStreamInvalidate(stream_ref);
    FSEventStreamRelease(stream_ref);
finish:
    /* Finish Python cleanup before another run() can acquire the stream. */
    Py_CLEAR(self->callback);
    stream_lock(self);
    self->run_loop = NULL;
    stream_unlock(self);
    CFRelease(run_loop);
    return result;
}

PyDoc_STRVAR(Stream_stop__doc__,
             "stop()\n\n\
Makes a running run() return and a future run() return immediately. May be\n\
called from any thread, including from inside the callback.");
static PyObject *
Stream_stop(StreamObject *self, PyObject *unused)
{
    UNUSED(unused);
    stream_stop(self);
    Py_RETURN_NONE;
}

static PyMethodDef Stream_methods[] = {
    {"run",  (PyCFunction)Stream_run,  METH_VARARGS | METH_KEYWORDS, Stream_run__doc__},
    {"stop", (PyCFunction)Stream_stop, METH_NOARGS, Stream_stop__doc__},
    {NULL, NULL, 0, NULL},
};

static PyTypeObject StreamType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = MODULE_NAME ".Stream",
    .tp_doc = "FSEvents stream for a list of paths, driven by the thread that calls run().",
    .tp_basicsize = sizeof(StreamObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = Stream_new,
    .tp_dealloc = (destructor)Stream_dealloc,
    .tp_methods = Stream_methods,
};


/******************************************************************************
 * Module initialization.
 *****************************************************************************/

PyDoc_STRVAR(watchdog_fsevents_module__doc__,
             "Low-level FSEvents Python/C API bridge.");

static struct PyModuleDef watchdog_fsevents_module = {
    PyModuleDef_HEAD_INIT,
    MODULE_NAME,
    watchdog_fsevents_module__doc__,
    -1,
    NULL,  /* m_methods */
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
    if (PyType_Ready(&NativeEventType) < 0 || PyType_Ready(&StreamType) < 0) {
        return NULL;
    }
    PyObject *module = PyModule_Create(&watchdog_fsevents_module);
    if (module == NULL) {
        return NULL;
    }
#ifdef Py_GIL_DISABLED
    PyUnstable_Module_SetGIL(module, Py_MOD_GIL_NOT_USED);
#endif
    if (PyModule_AddObjectRef(module, "NativeEvent", (PyObject *)&NativeEventType) < 0
        || PyModule_AddObjectRef(module, "Stream", (PyObject *)&StreamType) < 0
        || PyModule_AddIntConstant(module, "POLLIN", kCFFileDescriptorReadCallBack) < 0
        || PyModule_AddIntConstant(module, "POLLOUT", kCFFileDescriptorWriteCallBack) < 0
        || PyModule_Add(module, "__version__", Py_BuildValue("(iii)", WATCHDOG_VERSION_MAJOR,
                                                          WATCHDOG_VERSION_MINOR, WATCHDOG_VERSION_BUILD)) < 0
        || PyModule_AddStringConstant(module, "version_string", WATCHDOG_VERSION_STRING) < 0) {
        Py_DECREF(module);
        return NULL;
    }
    return module;
}
