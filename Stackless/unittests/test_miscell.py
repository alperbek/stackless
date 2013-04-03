# import common

import pickle
import unittest
import stackless
import sys
import traceback
from support import StacklessTestCase


def is_soft():
    softswitch = stackless.enable_softswitch(0)
    stackless.enable_softswitch(softswitch)
    return softswitch

def runtask():
    x = 0
    # evoke pickling of an xrange object
    dummy = range(10)
    for ii in range(1000):
        x += 1


class TestWatchdog(StacklessTestCase):

    def lifecycle(self, t):
        # Initial state - unrun
        self.assertTrue(t.alive)
        self.assertTrue(t.scheduled)
        self.assertEqual(t.recursion_depth, 0)
        # allow hard switching
        t.set_ignore_nesting(1)

        softSwitching = stackless.enable_softswitch(0); stackless.enable_softswitch(softSwitching)

        # Run a little
        res = stackless.run(10)
        self.assertEqual(t, res)
        self.assertTrue(t.alive)
        self.assertTrue(t.paused)
        self.assertFalse(t.scheduled)
        self.assertEqual(t.recursion_depth, softSwitching and 1 or 2)

        # Push back onto queue
        t.insert()
        self.assertFalse(t.paused)
        self.assertTrue(t.scheduled)

        # Run to completion
        stackless.run()
        self.assertFalse(t.alive)
        self.assertFalse(t.scheduled)
        self.assertEqual(t.recursion_depth, 0)


    def test_aliveness1(self):
        """ Test flags after being run. """
        t = stackless.tasklet(runtask)()
        self.lifecycle(t)

    def test_aliveness2(self):
        """ Same as 1, but with a pickled unrun tasklet. """
        import pickle
        t = stackless.tasklet(runtask)()
        t_new = pickle.loads(pickle.dumps((t)))
        t.remove()
        t_new.insert()
        self.lifecycle(t_new)

    def test_aliveness3(self):
        """ Same as 1, but with a pickled run(slightly) tasklet. """

        t = stackless.tasklet(runtask)()
        t.set_ignore_nesting(1)

        # Initial state - unrun
        self.assertTrue(t.alive)
        self.assertTrue(t.scheduled)
        self.assertEqual(t.recursion_depth, 0)

        softSwitching = stackless.enable_softswitch(0); stackless.enable_softswitch(softSwitching)

        # Run a little
        res = stackless.run(100)

        self.assertEqual(t, res)
        self.assertTrue(t.alive)
        self.assertTrue(t.paused)
        self.assertFalse(t.scheduled)
        self.assertEqual(t.recursion_depth, softSwitching and 1 or 2)

        # Now save & load
        dumped = pickle.dumps(t)
        t_new = pickle.loads(dumped)

        # Remove and insert & swap names around a bit
        t.remove()
        t = t_new
        del t_new
        t.insert()

        self.assertTrue(t.alive)
        self.assertFalse(t.paused)
        self.assertTrue(t.scheduled)
        self.assertEqual(t.recursion_depth, 1)

        # Run to completion
        if is_soft():
            stackless.run()
        else:
            t.kill()
        self.assertFalse(t.alive)
        self.assertFalse(t.scheduled)
        self.assertEqual(t.recursion_depth, 0)

class TestTaskletThrowBase(object):
    def test_throw_noargs(self):
        c = stackless.channel()
        def foo():
            self.assertRaises(IndexError, c.receive)
        s = stackless.tasklet(foo)()
        s.run() #It needs to have started to run
        self.throw(s, IndexError)
        self.aftercheck(s)

    def test_throw_args(self):
        c = stackless.channel()
        def foo():
            try:
                c.receive()
            except Exception as e:
                self.assertTrue(isinstance(e, IndexError));
                self.assertEqual(e.args, (1,2,3))
        s = stackless.tasklet(foo)()
        s.run() #It needs to have started to run
        self.throw(s, IndexError, (1,2,3))
        self.aftercheck(s)

    def test_throw_inst(self):
        c = stackless.channel()
        def foo():
            try:
                c.receive()
            except Exception as e:
                self.assertTrue(isinstance(e, IndexError));
                self.assertEqual(e.args, (1,2,3))
        s = stackless.tasklet(foo)()
        s.run() #It needs to have started to run
        self.throw(s, IndexError(1,2,3))
        self.aftercheck(s)

    def test_throw_exc_info(self):
        c = stackless.channel()
        def foo():
            try:
                c.receive()
            except Exception as e:
                self.assertTrue(isinstance(e, ZeroDivisionError));
        s = stackless.tasklet(foo)()
        s.run() #It needs to have started to run
        def errfunc():
            1/0
        try:
            errfunc()
        except Exception:
            self.throw(s, *sys.exc_info())
        self.aftercheck(s)

    def test_throw_traceback(self):
        c = stackless.channel()
        def foo():
            try:
                c.receive()
            except Exception as e:
                s = "".join(traceback.format_tb(sys.exc_info()[2]))
                self.assertTrue("errfunc" in s)
        s = stackless.tasklet(foo)()
        s.run() #It needs to have started to run
        def errfunc():
            1/0
        try:
            errfunc()
        except Exception:
            self.throw(s, *sys.exc_info())
        self.aftercheck(s)

    def test_new(self):
        # disabled.  Sending to new tasklets will bounce the error back at us.
        # Not good.
        c = stackless.channel()
        def foo():
            c.receive()
        s = stackless.tasklet(foo)()
        def doit():
            self.throw(s, IndexError)
        self.assertRaises(RuntimeError, doit)

    def test_dead(self):
        c = stackless.channel()
        def foo():
            c.receive()
        s = stackless.tasklet(foo)()
        s.run()
        c.send(None)
        def doit():
            self.throw(s, IndexError)
        self.assertRaises(RuntimeError, doit)

    def test_throw_invalid(self):
        s = stackless.getcurrent()
        def t():
            self.throw(s)
        self.assertRaises(TypeError, t)
        def t():
            self.throw(s, IndexError(1), (1,2,3))
        self.assertRaises(TypeError, t)

class TestTaskletThrowImmediate(StacklessTestCase, TestTaskletThrowBase):
    immediate = 1
    @classmethod
    def throw(cls, s, *args):
        args = args+(None, None)
        args = args[:3] + (cls.immediate,)
        s.throw(*args)

    def aftercheck(self, s):
        # the tasklet ran immediately
        self.assertFalse(s.alive)

class TestTaskletThrowNonImmediate(TestTaskletThrowImmediate):
    immediate = 0
    def aftercheck(self, s):
        # After the throw, the tasklet still hasn't run
        self.assertTrue(s.alive)
        s.run()
        self.assertFalse(s.alive)

class TestSwitchTrap(StacklessTestCase):
    class SwitchTrap(object):
        def __enter__(self):
            stackless.switch_trap(1)
        def __exit__(self, exc, val, tb):
            stackless.switch_trap(-1)
    switch_trap = SwitchTrap()

    def _test_schedule(self):
        s = stackless.tasklet(lambda:None)()
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", stackless.schedule)
        stackless.run()

    def _test_schedule_remove(self):
        main = []
        s = stackless.tasklet(lambda:stackless.insert(main[0]))()
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", stackless.schedule_remove)
        main.append(stackless.getcurrent())
        stackless.schedule_remove()

    def _test_run(self):
        s = stackless.tasklet(lambda:None)()
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", stackless.run)
        stackless.run()

    def _test_run_specific(self):
        s = stackless.tasklet(lambda:None)()
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", s.run)
        s.run()

    def test_send(self):
        c = stackless.channel()
        s = stackless.tasklet(lambda: c.receive())()
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", c.send, None)
        c.send(None)

    def test_send_throw(self):
        c = stackless.channel()
        def f():
            self.assertRaises(NotImplementedError, c.receive)
        s = stackless.tasklet(f)()
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", c.send_throw, NotImplementedError)
        c.send_throw(NotImplementedError)

    def test_receive(self):
        c = stackless.channel()
        s = stackless.tasklet(lambda: c.send(1))()
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", c.receive)
        self.assertEqual(c.receive(), 1)

    def test_receive_throw(self):
        c = stackless.channel()
        s = stackless.tasklet(lambda: c.send_throw(NotImplementedError))()
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", c.receive)
        self.assertRaises(NotImplementedError, c.receive)

    def test_raise_exception(self):
        c = stackless.channel()
        def foo():
            self.assertRaises(IndexError, c.receive)
        s = stackless.tasklet(foo)()
        s.run() #necessary, since raise_exception won't automatically run it
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", s.raise_exception, RuntimeError)
        s.raise_exception(IndexError)

    def test_kill(self):
        c = stackless.channel()
        def foo():
            self.assertRaises(TaskletExit, c.receive)
        s = stackless.tasklet(foo)()
        s.run() #necessary, since raise_exception won't automatically run it
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", s.kill)
        s.kill()

    def test_run(self):
        c = stackless.channel()
        def foo():
            pass
        s = stackless.tasklet(foo)()
        with self.switch_trap:
            self.assertRaisesRegex(RuntimeError, "switch_trap", s.run)
        s.run()


#///////////////////////////////////////////////////////////////////////////////

if __name__ == '__main__':
    import sys
    if not sys.argv[1:]:
        sys.argv.append('-v')

    unittest.main()
