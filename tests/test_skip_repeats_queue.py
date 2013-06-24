import unittest2
from watchdog.utils.bricks import SkipRepeatsQueue

class TestSkipRepeatsQueue(unittest2.TestCase):
    def test_basic_queue(self):
        q = SkipRepeatsQueue()

        e1 = (2, 'fred')
        e2 = (2, 'george')
        e3 = (4, 'sally')

        q.put(e1)
        q.put(e2)
        q.put(e3)

        self.assertEqual(e1, q.get())
        self.assertEqual(e2, q.get())
        self.assertEqual(e3, q.get())
        self.assertTrue(q.empty())

    def test_allow_nonconsecutive(self):
        q = SkipRepeatsQueue()

        e1 = (2, 'fred')
        e2 = (2, 'george')

        q.put(e1)
        q.put(e2)
        q.put(e1)       # repeat the first entry

        self.assertEqual(e1, q.get())
        self.assertEqual(e2, q.get())
        self.assertEqual(e1, q.get())
        self.assertTrue(q.empty())


    def test_prevent_consecutive(self):
        q = SkipRepeatsQueue()

        e1 = (2, 'fred')
        e2 = (2, 'george')

        q.put(e1)
        q.put(e1)       # repeat the first entry (this shouldn't get added)
        q.put(e2)

        self.assertEqual(e1, q.get())
        self.assertEqual(e2, q.get())
        self.assertTrue(q.empty())

    def test_consecutives_allowed_across_empties(self):
        q = SkipRepeatsQueue()

        e1 = (2, 'fred')

        q.put(e1)
        q.put(e1)       # repeat the first entry (this shouldn't get added)

        self.assertEqual(e1, q.get())
        self.assertTrue(q.empty())

        q.put(e1)       # this repeat is allowed because 'last' added is now gone from queue
        self.assertEqual(e1, q.get())
        self.assertTrue(q.empty())
