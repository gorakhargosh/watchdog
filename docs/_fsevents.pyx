# coding: utf-8

cdef extern from "CoreFoundation/CoreFoundation.h":
    struct dummy:
        pass
    ctypedef double CFTimeInterval
    ctypedef dummy *CFAllocatorRef
    ctypedef dummy *CFArrayRef
    ctypedef dummy *CFStringRef
    ctypedef dummy *CFRunLoopRef
    ctypedef unsigned char Boolean

cdef extern from "CoreServices/CoreServices.h":
    ctypedef unsigned int FSEventStreamCreateFlags

    enum:
        kFSEventStreamCreateFlagNone = 0x00000000
        kFSEventStreamCreateFlagUseCFTypes = 0x00000001
        kFSEventStreamCreateFlagNoDefer = 0x00000002
        kFSEventStreamCreateFlagWatchRoot = 0x00000004
        kFSEventStreamCreateFlagIgnoreSelf = 0x00000008
        kFSEventStreamCreateFlagFileEvents = 0x00000010

    ctypedef unsigned int FSEventStreamEventFlags
    enum:
        kFSEventStreamEventFlagNone = 0x00000000
        kFSEventStreamEventFlagMustScanSubDirs = 0x00000001
        kFSEventStreamEventFlagUserDropped = 0x00000002
        kFSEventStreamEventFlagKernelDropped = 0x00000004
        kFSEventStreamEventFlagEventIdsWrapper = 0x00000008
        kFSEventStreamEventFlagHistoryDone = 0x00000010
        kFSEventStreamEventFlagRootChanged = 0x00000020
        kFSEventStreamEventFlagMount = 0x00000040
        kFSEventStreamEventFlagUnmount = 0x00000080
        kFSEventStreamEventFlagItemCreated = 0x00000100
        kFSEventStreamEventFlagItemRemoved = 0x00000200
        kFSEventStreamEventFlagItemInodeMetaMod = 0x00000400
        kFSEventStreamEventFlagItemRenamed = 0x00000800
        kFSEventStreamEventFlagItemModified = 0x00001000
        kFSEventStreamEventFlagItemFinderInfoMod = 0x00002000
        kFSEventStreamEventFlagItemChangeOwner = 0x00004000
        kFSEventStreamEventFlagItemXattrMod = 0x00008000
        kFSEventStreamEventFlagItemIsFile = 0x00010000
        kFSEventStreamEventFlagItemIsDir = 0x00020000
        kFSEventStreamEventFlagItemIsSymlink = 0x00040000
    
    ctypedef unsigned long long FSEventStreamEventId
    enum:
        kFSEventStreamEventIdSinceNow = 0xFFFFFFFFFFFFFFFFULL
    
    ctypedef void *FSEventStreamRef
    ctypedef void *ConstFSEventStreamRef
    ctypedef struct FSEventStreamContext
    
    ctypedef void (*FSEventStreamCallback)(
        ConstFSEventStreamRef streamRef,
        void *clientCallBackInfo,
        size_t numEvents,
        void *eventPaths,
        FSEventStreamEventFlags *eventFlags,
        FSEventStreamEventId *eventIds
    )
    
    FSEventStreamRef FSEventStreamCreate(
        CFAllocatorRef              allocator,
        FSEventStreamCallback       callback,
        FSEventStreamContext        *context,
        CFArrayRef                  pathsToWatch,
        FSEventStreamEventId        sinceWhen,
        CFTimeInterval              latency,
        FSEventStreamCreateFlags    flags
    )
    
    FSEventStreamEventId FSEventStreamGetLatestEventId(ConstFSEventStreamRef streamRef)
    
    FSEventStreamEventId FSEventsGetCurrentEventId()
    void FSEventStreamRelease(FSEventStreamRef streamRef)
    void FSEventStreamScheduleWithRunloop(
        FSEventStreamRef        streamRef,
        CFRunLoopRef            runLoop,
        CFStringRef             runLoopMode
    )
    void FSEventStreamUnscheduleFromRunLoop(
        FSEventStreamRef        streamRef,
        CFRunLoopRef            runLoop,
        CFStringRef             runLoopMode
    )
    void FSEventStreamInvalidate(FSEventStreamRef streamRef)
    Boolean FSEventStreamStart(FSEventStreamRef streamRef)
    void FSEventStreamStop(FSEventStreamRef streamRef)
    
    
map_emitter_to_runloop = dict()
map_watch_to_stream = dict()

cdef CFRunLoopRef get_runloop_for_emitter(emitter_thread):
    cdef CFRunLoopRef runloop
    py_runloop = map_emitter_to_runloop[emitter_thread]
    runloop = py_runloop
    return runloop


