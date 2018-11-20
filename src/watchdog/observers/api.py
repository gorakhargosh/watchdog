#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import with_statement
import threading
import sys
import time
from watchdog.utils import BaseThread
from watchdog.utils.compat import queue
from watchdog.utils.bricks import SkipRepeatsQueue
from watchdog.events import LoggingEventHandler
import os.path
from pathlib import Path
import configparser
#from retrying import retry

DEFAULT_EMITTER_TIMEOUT = 1    # in seconds.
DEFAULT_OBSERVER_TIMEOUT = 1   # in seconds.


# Collection classes
class EventQueue(SkipRepeatsQueue):
    """Thread-safe event queue based on a special queue that skips adding
    the same event (:class:`FileSystemEvent`) multiple times consecutively.
    Thus avoiding dispatching multiple event handling
    calls when multiple identical events are produced quicker than an observer
    can consume them.
    """


class ObservedWatch(object):
    """An scheduled watch.

    :param path:
        Path string.
    :param recursive:
        ``True`` if watch is recursive; ``False`` otherwise.
    """

    def __init__(self, path, recursive):
        self._path = path
        self._is_recursive = recursive

    @property
    def path(self):
        """The path that this watch monitors."""
        return self._path

    @property
    def is_recursive(self):
        """Determines whether subdirectories are watched for the path."""
        return self._is_recursive

    @property
    def key(self):
        return self.path, self.is_recursive

    def __eq__(self, watch):
        return self.key == watch.key

    def __ne__(self, watch):
        return self.key != watch.key

    def __hash__(self):
        return hash(self.key)

    def __repr__(self):
        return "<ObservedWatch: path=%s, is_recursive=%s>" % (
            self.path, self.is_recursive)


# Observer classes
class EventEmitter(BaseThread):
    """
    Producer thread base class subclassed by event emitters
    that generate events and populate a queue with them.

    :param event_queue:
        The event queue to populate with generated events.
    :type event_queue:
        :class:`watchdog.events.EventQueue`
    :param watch:
        The watch to observe and produce events for.
    :type watch:
        :class:`ObservedWatch`
    :param timeout:
        Timeout (in seconds) between successive attempts at reading events.
    :type timeout:
        ``float``
    """

    def __init__(self, event_queue, watch, timeout=DEFAULT_EMITTER_TIMEOUT):
        BaseThread.__init__(self)
        self._event_queue = event_queue
        self._watch = watch
        self._timeout = timeout

    @property
    def timeout(self):
        """
        Blocking timeout for reading events.
        """
        return self._timeout

    @property
    def watch(self):
        """
        The watch associated with this emitter.
        """
        return self._watch

    def queue_event(self, event):
        """
        Queues a single event.

        :param event:
            Event to be queued.
        :type event:
            An instance of :class:`watchdog.events.FileSystemEvent`
            or a subclass.
        """
        self._event_queue.put((event, self.watch))

    def queue_events(self, timeout):
        print("q events from api.py")
        """Override this method to populate the event queue with events
        per interval period.

        :param timeout:
            Timeout (in seconds) between successive attempts at
            reading events.
        :type timeout:
            ``float``
        """

    def run(self):
        print("6b. Emitter run (self)" + str(self))
        print("   Child? has parent - " + str(self.parent_observer))
        '''
        maxInterval=32
        SecondsToWait=1
        maxTotalWait=100
        totalTimeWaited=0
        '''
        try:
            '''
            if SecondsToWait>maxInterval:
                SecondsToWait=maxInterval
            print("########running the loop" + str(self))
            '''
            print("before queue events called")
            self.queue_events(self.timeout)
            print("after queue events called")
            #added this
            self.parent_observer.refresh2(self)
            '''
            #SecondsToWait-=1
            time.sleep(SecondsToWait)
            print("----Just waited: " + str(SecondsToWait))
            print("---------Total: " + str(totalTimeWaited + SecondsToWait))
            if totalTimeWaited> maxTotalWait:
                #added this here
                print("before eliminate self" + str(self))
                #self._stopped_event.set()
                #self.stop()
                observer = self.parent_observer
                observer.unschedule(self._watch)
                print("after eliminate self" + str(self))
                #observer= self.parent_observer
                #oberver.stop()
                #break
            else:
                observer= self.parent_observer
                try:
                    print("About to refresh emitter, " + str(self))
                    print(self.should_keep_running())
                    observer.refresh(emitterToDelete=self)
                    print(self.should_keep_running())
                    print("Just refreshed emitter")
                except WindowsError as e:
                    totalTimeWaited+=SecondsToWait
                    SecondsToWait*=2
                    #self._stopped_event = False
                    print("We tried to refresh emitter too soon, " + str(self))
                    #make sure should_keep_running is true
                    with open("testlogfile.log", "a") as logf:
                        logf.write("From EventEmitter{0}--Error:{1}\n".format(time.asctime( time.localtime(time.time())),str(e) ) )
                        print("wrote error upon failing to refresh emitter, should keep running: " +str(self.should_keep_running()) )
            print(self.should_keep_running())
            '''
            '''
                if SecondsToWait>-10:
                    print("Seconds to Wait: "+str(SecondsToWait))
                if SecondsToWait<1:
                    answer=input("Would you like to try again(y/n): ")
                    if answer=="y":
                        SecondsToWait=3
                        print("ATTEMPT to access parent"+str(self.parent_observer))
                        observer= self.parent_observer
                        try:
                            print("About to refresh emitter, " + str(self))
                            observer.refresh(emitterToDelete=self)
                            print("Just refreshed emitter")
                        except WindowsError as e:
                            #self._stopped_event = False
                            print("We tried to refresh emitter too soon, " + str(self))
                            #make sure should_keep_running is true
                            with open("testlogfile.log", "a") as logf:
                                logf.write("From EventEmitter{0}--Error:{1}\n".format(time.asctime( time.localtime(time.time())),str(e) ) )
                                print("wrote error upon failing to refresh emitter, should keep running: " +str(self.should_keep_running()) )
                            continue
                    elif answer=="n":
                        #added this here
                        print("before eliminate self" + str(self))
                        #self._stopped_event.set()
                        #self.stop()
                        observer = self.parent_observer
                        observer.unschedule(self._watch)
                        print("after eliminate self" + str(self))
                        #observer= self.parent_observer
                        #oberver.stop()
                        #break
                    else:
                        print("incorrect input. try again.")
           '''     
        finally:
            pass
        print("about to end thread; current threads: " + str(threading.enumerate()))
        print("the end (of this thread)" + str(self))
        

class EventDispatcher(BaseThread):
    """
    Consumer thread base class subclassed by event observer threads
    that dispatch events from an event queue to appropriate event handlers.

    :param timeout:
        Event queue blocking timeout (in seconds).
    :type timeout:
        ``float``
    """

    def __init__(self, timeout=DEFAULT_OBSERVER_TIMEOUT):
        BaseThread.__init__(self)
        self._event_queue = EventQueue()
        self._timeout = timeout

    @property
    def timeout(self):
        """Event queue block timeout."""
        return self._timeout

    @property
    def event_queue(self):
        """The event queue which is populated with file system events
        by emitters and from which events are dispatched by a dispatcher
        thread."""
        return self._event_queue

    def dispatch_events(self, event_queue, timeout):
        """Override this method to consume events from an event queue, blocking
        on the queue for the specified timeout before raising :class:`queue.Empty`.

        :param event_queue:
            Event queue to populate with one set of events.
        :type event_queue:
            :class:`EventQueue`
        :param timeout:
            Interval period (in seconds) to wait before timing out on the
            event queue.
        :type timeout:
            ``float``
        :raises:
            :class:`queue.Empty`
        """

    def run(self):
        print("Observer run(self)"+str(self))
        while self.should_keep_running():
            try:
                self.dispatch_events(self.event_queue, self.timeout)
            except queue.Empty:
                continue


class BaseObserver(EventDispatcher):
    """Base observer."""

    def __init__(self, emitter_class, timeout=DEFAULT_OBSERVER_TIMEOUT):
        EventDispatcher.__init__(self, timeout)
        self._emitter_class = emitter_class
        self._lock = threading.RLock()
        self._watches = set()
        self._handlers = dict()
        self._emitters = set()
        self._emitter_for_watch = dict()
        #We added this
        self._lost_emitters = list()

    def _add_emitter(self, emitter):
        self._emitter_for_watch[emitter.watch] = emitter
        self._emitters.add(emitter)

    def _remove_emitter(self, emitter):
        del self._emitter_for_watch[emitter.watch]
        self._emitters.remove(emitter)
        emitter.stop()
        try:
            print("remove_emitter about to join")
            emitter.join()
        except RuntimeError:
            print("remove_emitter failed to join")
            pass

    def _clear_emitters(self):
        for emitter in self._emitters:
            emitter.stop()
        for emitter in self._emitters:
            try:
                emitter.join()
            except RuntimeError:
                pass
        self._emitters.clear()
        self._emitter_for_watch.clear()

    def _add_handler_for_watch(self, event_handler, watch):
        if watch not in self._handlers:
            self._handlers[watch] = set()
        self._handlers[watch].add(event_handler)

    def _remove_handlers_for_watch(self, watch):
        del self._handlers[watch]

    @property
    def emitters(self):
        """Returns event emitter created by this observer."""
        return self._emitters

    #When we call refresh, we WILL be unscheduling
    # the current emitter thread and attemepting to
    # make a new one.
    def refresh2(self, emitterToDelete):

        #get setup vars and info
        rescheduled = False
        #maxInterval=32
        #maxTotalWait=32
        Config = configparser.ConfigParser()
        Config.read("expBackoffConfig.ini")
        maxInterval = Config.getint("ExpBackoff", "maxInterval")
        maxTotalWait = Config.getint("ExpBackoff", "maxTotalWait")
        expBackoffBase = Config.getint("ExpBackoff", "expBackoffBase")
        print("--------------" + str(maxInterval))
        SecondsToWait=1
        totalTimeWaited=0
        #Figure out which handler to use
        handler=LoggingEventHandler()
        #Figure out which path to use
        path=emitterToDelete._watch._path
        folderPath=Path(path)
        newWatch=ObservedWatch(path,True)

        e = WindowsError()

        #unschedule the old thread
        print("about to unschedule")
        print("\nThreads before unschedule: " + str(threading.enumerate())+"\n")
        print(self._emitter_for_watch.get(emitterToDelete._watch))
        self.unschedule(emitterToDelete._watch)
        print(self._emitter_for_watch.get(emitterToDelete._watch))
        print("\nThreads after unschedule: " + str(threading.enumerate())+"\n")
        print("just unscheduled")


        #try to schedule new thread immedeiately (in case connection already exists)
        #on exception, loop using exponential backoff to attempt making the new thread
        try:
            print("about to try to schedule")
            #answer=input("press any key to continue: ")
            print("Emitters? " + str(self._emitter_for_watch.get(emitterToDelete._watch)))
            newWatch = self.schedule(event_handler=handler,path=path,recursive=True)
            print("Schedule Returns: " + str(newWatch))
            print("Threads after first attempt at scheduling: " + str(threading.enumerate))
        except:
            #delete the broken emitter that was created in the try block
            print("*1Emitters? " + str(self._emitter_for_watch.get(emitterToDelete._watch)))
            self.unschedule(newWatch)
            print("*2Emitters? " + str(self._emitter_for_watch.get(emitterToDelete._watch)))

            #loop until you have successfully re-scheduled the folder with a new emitter,
            #  or until you exceed the max total wait time
            while rescheduled == False:
                #cap the secondsToWait at the max interval
                if SecondsToWait>maxInterval:
                    SecondsToWait=maxInterval
                print("########running the loop" + str(self))
                #wait
                time.sleep(SecondsToWait)
                print("----Just waited: " + str(SecondsToWait))
                print("---------Total: " + str(totalTimeWaited + SecondsToWait))
                #increment the exponential backoff values appropriately.
                totalTimeWaited+=SecondsToWait
                SecondsToWait*=expBackoffBase
                #if totalTimeWaited is maxed out, exit the loop
                if totalTimeWaited+SecondsToWait> maxTotalWait:
                    print("Waited too long, stop trying to make emitter " + str(threading.enumerate))
                    self._lost_emitters.append(path)
                    #connectionNotReFoundError = WindowsError("Connection not found after max wait time")
                    #raise connectionNotReFoundError
                    break
                #if totalTimeWaited is not maxed out
                else:
                    #observer= self.parent_observer
                    #try to schedule the new emitter
                    try:
                        print("About to schedule emitter")
                        newWatch = self.schedule(event_handler=handler,path=path,recursive=True)
                        print("Just scheduled emitter")
                        rescheduled = True
                    #if scheduling fails, unschedule the junk emitter/watch
                    except WindowsError as e:
                        print("error is " + str(e))
                        self.unschedule(newWatch)
                        #self._stopped_event = False
                        print("We tried to schedule emitter too soon, " + str(self))
                        with open("testlogfile.log", "a") as logf:
                            logf.write("From EventEmitter{0}--Error:{1}\n".format(time.asctime( time.localtime(time.time())),str(e) ) )
                            print("wrote error upon failing to schedule emitter" )

        print("finished attempts to refresh")
                

    def refresh(self,emitterToDelete):
        #thePath = self.emitter.path
        #self._emitters= set()
        #self._watches=set()
        #self._handlers=dict()
        #self._watches_for_emitters=set()
        #handler=handler()
        

        #Figure out which handler to use
        handler=LoggingEventHandler()
        #Figure out which path to use
        path=emitterToDelete._watch._path
        folderPath=Path(path)
        #Remove emitterToDelete from the observer's list of emitters (self._emitters)
        e=WindowsError()
        if folderPath.exists():
            
            try:
                print("about to try to schedule")
                print("A.emitter for watch" +str(self._emitter_for_watch))
                answer=input("press any key to continue: ")
                newWatch = self.schedule(event_handler=handler,path=path,recursive=True)
                print("Schedule Returns: " + str(newWatch))
                #print("Schedule Returns: " + str(self.schedule(event_handler=handler,path=path,recursive=True) ))

                print("scheduled?")
            except WindowsError as e:
                print("schedule failed, should continue on orig. emitter")
                return
            print("about to unschedule")
            print("\nThreads before unschedule: " + str(threading.enumerate())+"\n")
            print("B.emitter for watch" +str(self._emitter_for_watch))
            self.unschedule(emitterToDelete._watch)
            print("C.emitter for watch" +str(self._emitter_for_watch))
            print("\nThreads after unschedule: " + str(threading.enumerate())+"\n")
            print("just unscheduled")
            watch1 = ObservedWatch(path, True)
            watch2 = ObservedWatch(path, True)
            if (watch1 == watch2):
                print("--------Watches are identical-------------")
            else:
                print("--------Watches are NOT identical-------------")
 
        else:
            print("File path not Found")
            raise e
                               
            '''
            print("about to schedule new event")
            #store the emitter-watch pair
            tempOldWatch = emitterToDelete._watch
            tempOldEmitter = emitterToDelete
            #remove the emitter-watch pair
            print("temp before deleting: " + str(tempOldEmitter))
            self.unschedule(emitterToDelete._watch)
            print("temp after deleting: " + str(tempOldEmitter))
            #print("   and its handler: " + str(tempOldWatch._handler))
            answer=input("press any key to continue: ")
            print("just unscheduled old event")
            try:
                #schedule the event, and if is succeeds (returns a watch), unschedule the old one
                print("Schedule Returns: " + str(self.schedule(event_handler=handler,path=path,recursive=True) ))
                print("just scheduled new event")
            except:
                #put the old pair back
                print("want to put back the old pair")
                self._add_emitter(tempOldEmitter)
                self._watches.add(tempOldWatch)
            '''

            

    def start(self):
        print("Observer: " + str(self) + " ---has emitters:--- " + str(self._emitters))
        for emitter in self._emitters:
            print("6. in observer.start() about to call emitter.start()" + " " + str(emitter))
            emitter.start()

            print("7. in observer.start() just finished emitter.start()" + " " + str(emitter))
        print("8. BaseObserver calls start(self)")
        super(BaseObserver, self).start()
        print("9. After BaseObserver calls start(self)" +str(self))

    def schedule(self, event_handler, path, recursive=False):
        print("2. schedule called")
        """
        Schedules watching a path and calls appropriate methods specified
        in the given event handler in response to file system events.

        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param path:
            Directory path that will be monitored.
        :type path:
            ``str``
        :param recursive:
            ``True`` if events will be emitted for sub-directories
            traversed recursively; ``False`` otherwise.
        :type recursive:
            ``bool``
        :return:
            An :class:`ObservedWatch` object instance representing
            a watch.
        """
        with self._lock:
            watch = ObservedWatch(path, recursive)
            self._add_handler_for_watch(event_handler, watch)

            #print("  inside with self._lock")
            # If we don't have an emitter for this watch already, create it.
            #if the emitter for this watch == none
            if self._emitter_for_watch.get(watch) is None:
                print("  self._emitter_for_watch.get(watch) found to be None")
                #print("Should initialize emitter next...")
                emitter = self._emitter_class(event_queue=self.event_queue,
                                              watch=watch, parent_observer=self,
                                              timeout=self.timeout)
                #print("...Should have just initialized emitter")
                self._add_emitter(emitter)
                self._watches.add(watch)
                if self.is_alive():
                    
                    print("3. within observer.schedule, about to call emitter.start()")
                    emitter.start()
                    print("4. within observer.schedule, just finished calling emitter.start()")
                #remove this else block
                else:
                    print("  this observer is not alive");
            #remove this else block
            else:
                print("self._emitter_for_watch.get(watch) WASN'T found to be None")
                self._watches.add(watch)
        return watch

    def add_handler_for_watch(self, event_handler, watch):
        """Adds a handler for the given watch.

        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param watch:
            The watch to add a handler for.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """
        with self._lock:
            self._add_handler_for_watch(event_handler, watch)

    def remove_handler_for_watch(self, event_handler, watch):
        """Removes a handler for the given watch.

        :param event_handler:
            An event handler instance that has appropriate event handling
            methods which will be called by the observer in response to
            file system events.
        :type event_handler:
            :class:`watchdog.events.FileSystemEventHandler` or a subclass
        :param watch:
            The watch to remove a handler for.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """
        with self._lock:
            self._handlers[watch].remove(event_handler)

    def unschedule(self, watch):
        """Unschedules a watch.

        :param watch:
            The watch to unschedule.
        :type watch:
            An instance of :class:`ObservedWatch` or a subclass of
            :class:`ObservedWatch`
        """
        with self._lock:
            emitter = self._emitter_for_watch[watch]
            del self._handlers[watch]
            self._remove_emitter(emitter)
            self._watches.remove(watch)

    def unschedule_all(self):
        """Unschedules all watches and detaches all associated event
        handlers."""
        with self._lock:
            self._handlers.clear()
            self._clear_emitters()
            self._watches.clear()

    def on_thread_stop(self):
        self.unschedule_all()

    def dispatch_events(self, event_queue, timeout):
        event, watch = event_queue.get(block=True, timeout=timeout)

        with self._lock:
            # To allow unschedule/stop and safe removal of event handlers
            # within event handlers itself, check if the handler is still
            # registered after every dispatch.
            for handler in list(self._handlers.get(watch, [])):
                if handler in self._handlers.get(watch, []):
                    handler.dispatch(event)
        event_queue.task_done()
