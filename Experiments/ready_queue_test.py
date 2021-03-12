import multiprocessing
import multiprocessing.queues
import sys


class ReadyQueue(multiprocessing.queues.Queue):
    def __init__(self, ctx, *args, **kwargs):
        super(ReadyQueue, self).__init__(ctx=ctx, *args, **kwargs)
        self.ready = False


def ready_queue(*args, **kwargs):
    return ReadyQueue(ctx=multiprocessing.get_context(), *args, **kwargs)


def foo(q):
    print(q.ready)


if __name__ == "__main__":
    print(sys.version)
    my_queue = ready_queue()
    print(my_queue.ready)
    p = multiprocessing.Process(target=foo, args=(my_queue,))
    p.start()
    p.join()
