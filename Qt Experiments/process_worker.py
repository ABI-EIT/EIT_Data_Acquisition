from multiprocessing import Process, Queue, Value, Pipe
from threading import Thread
import time
from abc import ABCMeta, abstractmethod
import atexit


class Worker:
    __metaclass__ = ABCMeta

    stopped = 1
    started = 2
    stop_at_queue_end = 3

    def __init__(self):
        self.process = None
        self.work_queues = []
        self.state = Value('i', 0)
        self.result_pipe_parent, self.result_pipe_child = Pipe()
        atexit.register(self.set_stopped)

    def start_new(self, on_start_args=(), work_args=(), on_stopped_args=()):
        self.process = Process(target=self.work_loop,
                               args=(self.work, self.on_start, self.on_stop, self.state, self.work_queues,
                                     on_start_args, work_args, on_stopped_args, self.result_pipe_child))
        self.process.start()
        Thread(target=self.wait_on_result_pipe).start()

    @staticmethod
    @abstractmethod
    def work_loop(*args):
        pass

    @staticmethod
    @abstractmethod
    def work(*args):
        pass

    @staticmethod
    def on_start(*args):
        pass

    @staticmethod
    def on_stop(*args):
        pass

    def set_stopped(self):
        self.state.value = Worker.stopped

    def wait_on_result_pipe(self):
        while 1:
            result = self.result_pipe_parent.recv()
            self.on_result_ready(result)

    def on_result_ready(self, result):
        pass


class Producer(Worker):
    __metaclass__ = ABCMeta

    def __init__(self, subscriber_queues=None):
        super().__init__()
        self.work_queues = subscriber_queues

    def set_subscribers(self, subscriber_queues):
        self.work_queues = subscriber_queues

    @staticmethod
    def work_loop(work, on_start, on_stop, state, work_queues,
                  on_start_args, work_args, on_stopped_args, pipe_conn):

        on_start_results = on_start(on_start_args)

        work_freq = 1
        last_worked = time.time()
        while 1:
            if state.value == Worker.stopped:
                break
            if time.time()-last_worked >= work_freq:
                last_worked = time.time()
                result = work(on_start_results)
                for queue in work_queues:
                    queue.put(result)
                pipe_conn.send(result)

        on_stop(on_start_results, on_stopped_args)

    @staticmethod
    @abstractmethod
    def work(on_start_results, *args):
        pass


class Consumer(Worker):
    def __init__(self):
        super().__init__()
        self.work_queues = [Queue()]

    @staticmethod
    def work_loop(work, on_start, on_stop, state, work_queues,
                  on_start_args, work_args, on_stopped_args, pipe_conn):
        assert len(work_queues) == 1
        work_queue = work_queues[0]

        on_start_results = on_start(on_start_args)

        while 1:
            if state.value == Worker.stopped:
                break
            if state.value == Worker.stop_at_queue_end:
                pass
            if work_queue.qsize() > 0:
                item = work_queue.get()
                result = work(item, on_start_results)
                pipe_conn.send(result)

        on_stop(on_start_results, on_stopped_args)

    @staticmethod
    @abstractmethod
    def work(item, on_start_results, *args):
        pass

    def get_work_queue(self):
        return self.work_queues[0]

    def set_stop_at_queue_end(self):
        self.state.value = Worker.stop_at_queue_end


class MyProducer(Producer):
    def on_result_ready(self, result):
        print("Got %s from the producer result pipe" % result)

    @staticmethod
    def work(on_start_results, *args):
        return "hello"


class MyConsumer(Consumer):
    def on_result_ready(self, result):
        print("Got %s from the consumer result pipe" % result)

    @staticmethod
    def work(item, on_start_results, *args):
        return "{0} world!".format(item)


def test():
    my_consumer = MyConsumer()
    my_consumer.start_new()
    my_producer = MyProducer(subscriber_queues=[my_consumer.get_work_queue()])
    my_producer.start_new()

    time.sleep(5)
    my_producer.set_stopped()
    my_consumer.set_stopped()


if __name__ == '__main__':
    test()
