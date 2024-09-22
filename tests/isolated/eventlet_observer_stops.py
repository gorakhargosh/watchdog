if __name__ == '__main__':
    import eventlet

    eventlet.monkey_patch()

    import signal
    import sys
    import tempfile

    from watchdog.observers import Observer
    from watchdog.events import LoggingEventHandler

    with tempfile.TemporaryDirectory() as temp_dir:
        def run_observer():
            event_handler = LoggingEventHandler()
            observer = Observer()
            observer.schedule(event_handler, temp_dir)
            observer.start()
            eventlet.sleep(1)
            observer.stop()

        def on_alarm(signum, frame):
            print("Observer.stop() never finished!", file=sys.stderr)
            sys.exit(1)

        signal.signal(signal.SIGALRM, on_alarm)
        signal.alarm(4)

        thread = eventlet.spawn(run_observer)
        thread.wait()
