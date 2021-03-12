import multiprocessing
import multiprocessing.queues
import sys
import time
import ctypes


class ReadyQueue(multiprocessing.queues.Queue):
    def __init__(self, ctx, *args, **kwargs):
        super(ReadyQueue, self).__init__(ctx=ctx, *args, **kwargs)
        self.ready = multiprocessing.Value(ctypes.c_bool, False)


def ready_queue(*args, **kwargs):
    return ReadyQueue(ctx=multiprocessing.get_context(), *args, **kwargs)


def foo(q):
    print(q.ready.value)
    time.sleep(2)
    print(q.ready.value)


if __name__ == "__main__":
    print(sys.version)
    my_queue = ready_queue()
    print(my_queue.ready.value)
    p = multiprocessing.Process(target=foo, args=(my_queue,))
    p.start()
    time.sleep(1)
    my_queue.ready.value = True
    p.join()
