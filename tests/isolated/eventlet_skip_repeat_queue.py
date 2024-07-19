if __name__ == '__main__':
    import eventlet

    eventlet.monkey_patch()

    from watchdog.utils.bricks import SkipRepeatsQueue

    q = SkipRepeatsQueue(10)
    q.put('A')
    q.put('A')
    q.put('A')
    q.put('A')
    q.put('B')
    q.put('A')

    value = q.get()
    assert value == 'A'
    q.task_done()

    assert q.unfinished_tasks == 2

    value = q.get()
    assert value == 'B'
    q.task_done()

    assert q.unfinished_tasks == 1

    value = q.get()
    assert value == 'A'
    q.task_done()

    assert q.empty()
    assert q.unfinished_tasks == 0
