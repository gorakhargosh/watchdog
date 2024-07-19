if __name__ == '__main__':
    import eventlet

    eventlet.monkey_patch()

    from watchdog.utils.bricks import SkipRepeatsQueue

    # same as test_basic_queue() inside test_skip_repeats_queue.py

    q = SkipRepeatsQueue()

    e1 = (2, "fred")
    e2 = (2, "george")
    e3 = (4, "sally")

    q.put(e1)
    q.put(e2)
    q.put(e3)

    assert e1 == q.get()
    assert e2 == q.get()
    assert e3 == q.get()
    assert q.empty()
