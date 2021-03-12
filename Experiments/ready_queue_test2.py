import multiprocessing


class ReadyQueue:
    def __init__(self, *args, **kwargs):
        self.queue = multiprocessing.Queue(*args, **kwargs)
        self.ready = False

    def get(self, block, timeout):
        return self.queue.get(block, timeout)

    def put(self, obj, block, timeout):
        return self.queue.put(obj, block, timeout)

    def full(self):
        return self.queue.full()

    def empty(self):
        return self.queue.empty()

    def qsize(self):
        return self.queue.qsize()


def foo(q):
    print(q.ready)


if __name__ == "__main__":
    my_queue = ReadyQueue()
    print(my_queue.ready)
    p = multiprocessing.Process(target=foo, args=(my_queue,))
    p.start()
    p.join()
