.. include:: global.rst.inc

.. _usage:

Choosing and managing observers
===============================

Native notifications and polling
--------------------------------

``from watchdog.observers import Observer`` selects an implementation for the
operating system. It does not inspect each scheduled path to decide whether its
filesystem delivers notifications. A native API being available does not mean
that every mounted filesystem supports it.

All implementations selected by ``Observer`` accept ``timeout`` in seconds.
If the selected implementation is polling, this is the wait between directory
scans. For example, ``Observer(timeout=10)`` also sets a ten-second interval
when the platform falls back to polling. There is no need to change
``DEFAULT_OBSERVER_TIMEOUT``. ``PollingObserver(timeout=10)`` chooses polling
explicitly; the virtual-filesystem variant, ``PollingObserverVFS``, names the
same setting ``polling_interval``. On native observers, ``timeout`` does not
turn notifications into periodic snapshots or debounce callbacks.

Use :class:`watchdog.observers.polling.PollingObserver` explicitly when changes
are visible through directory listings and file metadata but native
notifications are unavailable:

* For CIFS/SMB shares, polling is a supported choice, not an indication that
  watchdog cannot be used. Each scan costs filesystem operations, so choose
  the watched subtree and interval to suit the share.
* Under WSL 2, changes to Windows-drive paths such as ``/mnt/c/...`` may not
  generate Linux inotify notifications. Polling can observe changes that are
  visible to WSL. Alternatively, run the watcher on Windows for Windows files,
  or keep the watched files in the WSL filesystem.
* FUSE mounts depend on their provider. For example, s3fs-fuse documents that
  inotify only detects local modifications, not changes made by other clients.
  Polling can only detect external changes after the mount exposes them through
  listings and metadata; its cache may delay that visibility. Watchdog does not
  subscribe directly to S3 notifications.

This complete example includes the polling import. Pass a directory and,
optionally, the interval in seconds::

    python polling.py /path/to/share --interval 2

.. literalinclude:: examples/polling.py
   :language: python

Polling compares snapshots; it does not record every operation between them.
A file created and deleted between scans may never appear, and several edits
may become a single modification. Scanning a large tree also takes time: the
interval is a wait between scans, not a guarantee of a new result every N
seconds. If changes are missing, first verify that the watcher process can list
the affected directory and see the changed metadata on that same mount.

File readiness and close events
-------------------------------

Polling emits changes inferred from file metadata. It cannot observe file
handles and never emits ``opened``, ``closed`` or ``closed_no_write`` events,
including on CIFS shares. Linux inotify can report those events; the other
native observers do not provide the same close-event interface.

A creation or modification notification can arrive while another process is
still writing the file. For a reliable handoff, coordinate with the producer:
write and close a temporary file, then publish its final name, or publish a
separate completion marker. Handle the resulting move or creation as
appropriate for the backend. A quiet period or an unchanged size across scans
is a useful heuristic, but a paused writer can resume afterwards. Applications
should handle transient read errors, including Windows sharing violations.

Avoiding events caused by a handler
-----------------------------------

Filesystem notifications also include operations performed by the watcher
process. A path-pattern filter cannot identify which process changed a file.
A flag set only while the handler writes is insufficient: the notification may
already be queued and dispatched after the flag is cleared.

Keep generated output and logs outside the watched input tree, or exclude their
paths. If a handler must rewrite an input, make the operation idempotent: compare
the intended contents with the existing contents and write only when they
differ. Subscribe only to events that drive that operation. In particular,
reading a file from ``on_opened`` can cause another open notification on Linux;
reading from a handler that only processes modifications avoids that cycle.
Idempotence still matters when the handler itself writes.

An ``opened`` notification reports an operation that has already occurred. It
cannot delay another program's read until an encryption or decryption handler
finishes; transparent access control requires a different integration with the
application or filesystem.

Knowing when the initial snapshot is ready
------------------------------------------

For a ``PollingObserver`` whose watches were scheduled before startup,
``observer.start()`` takes the initial snapshots before returning. The example
logs their completion immediately after that call. On a large or slow share,
startup can therefore take minutes. Files already present form the baseline;
they are not emitted as newly created files.

Adding a watch to an already running polling observer takes that watch's first
snapshot inside ``schedule()``. When it returns successfully, that baseline is
ready too. These are initial-snapshot boundaries, not notifications of every
later scan. Avoid acquiring private emitter locks to determine readiness.

Adding and removing watches while running
-----------------------------------------

An observer can manage several watches, including watches scheduled after
``start()``. ``schedule()`` synchronizes access to its watch registry and starts
the new emitter when needed. Keep the returned watch to remove it later:

.. code-block:: python

    from watchdog.events import LoggingEventHandler
    from watchdog.observers import Observer

    observer = Observer()
    observer.start()
    try:
        first = observer.schedule(LoggingEventHandler(), "/path/to/first", recursive=True)
        second = observer.schedule(LoggingEventHandler(), "/path/to/second", recursive=True)
        # The application keeps running while both paths are watched.
        # When the first watch is no longer needed:
        observer.unschedule(first)
        # The second watch remains active until shutdown.
    finally:
        observer.stop()
        observer.join()

Sharing an observer shares its dispatch thread; it does not eliminate the
emitters or native resources needed for distinct watches. Overlapping recursive
roots are not automatically merged into one watch. A registered recursive root
also does not prove every descendant is accessible to the process.

Exceptions in application handlers
----------------------------------

An unhandled exception from an event handler escapes the observer's dispatch
thread. Catch failures that the application can recover from and log them so
that later events can still be handled. A ``dispatch`` wrapper covers both
``on_any_event`` and the specific ``on_created``, ``on_modified``, and other
callbacks on that handler:

.. code-block:: python

    import logging

    from watchdog.events import FileSystemEventHandler

    class ResilientHandler(FileSystemEventHandler):
        def dispatch(self, event):
            try:
                super().dispatch(event)
            except Exception:
                logging.exception("Failed to process event %s", event)

        def on_created(self, event):
            if not event.is_directory:
                # Perform the application's work here, or enqueue it for a worker.
                logging.info("Created: %s", event.src_path)

This wrapper handles failures in application callbacks, not failures while an
emitter reads the filesystem. Polling retries most ``OSError`` failures on a
later scan, but a missing watched root is treated as a deletion and stops that
emitter. See :class:`watchdog.observers.polling.PollingObserver` for details.
Keep handlers short; blocking work delays other handlers on the same observer.

Stopping and joining
--------------------

Call ``stop()`` and then ``join()`` from the thread managing the observer, as in
the examples. ``stop()`` requests shutdown and stops the emitters; ``join()``
waits for the dispatch thread to finish. Shutdown may have to wait for a running
callback, filesystem operation, or polling snapshot. Time spent in these
operations can appear in either ``stop()`` or ``join()``.

``join(timeout=...)`` limits that particular wait; it does not kill the thread.
Check ``is_alive()`` afterwards if the application needs to know whether it has
finished. Do not call ``join()`` on the observer from one of its own callbacks.
Shutdown is not a promise that every queued event has been dispatched. If all
application work must finish, manage and drain the application's work queue
separately. A stopped observer, like a Python thread, cannot be started again;
create a new observer when restarting monitoring.

``stop()`` clears the watch handlers and ends dispatch; queued events are not
guaranteed to reach a callback. ``join()`` on the observer waits for the thread,
not for that queue to drain. To finish events already queued while the observer
and its handlers are healthy, stop and join its emitters first, then wait for
the event queue, and finally stop the observer:

.. code-block:: python

    # Run from the managing thread after the application's producers are quiet.
    # Do not add or remove watches during this sequence.
    emitters = list(observer.emitters)
    for emitter in emitters:
        emitter.stop()
    for emitter in emitters:
        emitter.join()
    observer.event_queue.join()
    observer.stop()
    observer.join()

This drains events already enqueued; it does not promise to read every pending
native notification or finish a final polling scan. ``event_queue.join()`` has
no timeout and needs a live dispatcher whose callbacks return. Call it from the
managing thread, not a callback. It also does not wait for work a callback has
handed to another worker; drain that application's queue separately.

Comparing snapshots on demand
-----------------------------

There is no ``Observer.poll_now()`` method. Use the public snapshot utilities
when the application needs to compare filesystem state on its own schedule:

.. code-block:: python

    from watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff

    path = "/path/to/watch"
    previous = DirectorySnapshot(path, recursive=True)

    def poll_changes():
        global previous
        current = DirectorySnapshot(path, recursive=True)
        changes = DirectorySnapshotDiff(previous, current)
        previous = current
        return changes

    # Later, when the application chooses to poll:
    changes = poll_changes()
    print("Created:", changes.files_created)
    print("Modified:", changes.files_modified)
    print("Deleted:", changes.files_deleted)
    print("Moved:", changes.files_moved)  # (old_path, new_path) pairs

The diff also has corresponding ``dirs_created``, ``dirs_modified``,
``dirs_deleted`` and ``dirs_moved`` properties. It returns paths, not dispatched
events, and does not alter an observer's internal snapshot. Serialize calls to
``poll_changes`` if several threads can trigger them. Snapshot comparisons have
the same between-scan limitations as ``PollingObserver``. Triggering them only
from native events cannot recover changes for which no native event arrives;
use periodic reconciliation if that is a requirement.
