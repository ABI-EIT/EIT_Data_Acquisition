import multiprocessing
from queue import Empty
import time
import ctypes


class ReadyQueue:
    def __init__(self, *args, **kwargs):
        self.queue = multiprocessing.Queue(*args, **kwargs)
        self._ready = multiprocessing.Value(ctypes.c_bool, False)

    def set_ready(self):
        self._ready.value = True

    def set_not_ready(self):
        self._ready.value = False
        self.clear()

    def is_ready(self):
        return self._ready.value

    def clear(self):
        try:
            while True:
                self.queue.get(block=False)
        except Empty:
            pass

    def get(self, block=True, timeout=None):
        return self.queue.get(block, timeout)

    def put(self, obj, block=True, timeout=None):
        return self.queue.put(obj, block, timeout)

    def full(self):
        return self.queue.full()

    def empty(self):
        return self.queue.empty()

    def qsize(self):
        return self.queue.qsize()


def foo(q):
    while q.is_ready():
        time.sleep(1)
        q.put("hello from foo")
    print("q no longer ready, foo loop finished")


if __name__ == "__main__":
    my_queue = ReadyQueue()
    my_queue.set_ready()
    p = multiprocessing.Process(target=foo, args=(my_queue,))
    p.start()

    for i in range(2):
        print(my_queue.get())
        time.sleep(2)

    print("my_queue._ready = %s, qsize: %d. Setting not ready.." % (str(my_queue.is_ready()), my_queue.qsize()))
    my_queue.set_not_ready()
    print("my_queue._ready = %s, qusize: %d" % (str(my_queue.is_ready()), my_queue.qsize()))
