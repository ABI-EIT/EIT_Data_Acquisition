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
        self.result_thread = None
        self.work_queues = []
        self.state = Value('i', 1)
        self.result_pipe_parent, self.result_pipe_child = Pipe()
        atexit.register(self.set_stopped)
        self.work_timeout = 0
        self.buffer_size = 1
        self.on_start_args = ()
        self.on_stopped_args = ()
        self.work_args = ()

    def get_state(self):
        return self.state.value

    def start_new(self, on_start_args=(), work_args=(), on_stopped_args=()):
        if self.process is not None:
            self.set_stopped()
            while self.process.is_alive():
                time.sleep(0)
        self.state.value = Worker.started
        self.process = Process(target=self.work_loop,
                               args=(self.work, self.on_start, self.on_stop, self.state, self.work_queues,
                                     (*self.on_start_args, *on_start_args), (*self.work_args, *work_args),
                                     (*self.on_stopped_args, *on_stopped_args), self.result_pipe_child,
                                     self.work_timeout, self.buffer_size), daemon=True)
        self.process.start()
        self.result_thread = Thread(target=self.wait_on_result_pipe, daemon=True)
        self.result_thread.start()

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


# Make this the interface in case queue item ever needs to be a dict with e.g. a command + the data
def put_in_queue(queue, data):
    queue.put(data)


class Producer(Worker):
    __metaclass__ = ABCMeta

    def __init__(self, subscriber_queues=None, work_timeout=0):
        super().__init__()
        self.work_queues = subscriber_queues
        self.work_timeout = work_timeout

    # set_subscribers must be called before start_new
    def set_subscribers(self, subscriber_queues):
        self.work_queues = subscriber_queues

    @staticmethod
    def work_loop(work, on_start, on_stop, state, work_queues,
                  on_start_args, work_args, on_stopped_args, pipe_conn, work_timeout, buffer_size):
        # Producer does not make use of the buffer size argument
        assert buffer_size == 1
        on_start_results = on_start(*on_start_args)

        last_worked = time.time()
        while state.value != Worker.stopped:
            if time.time()-last_worked >= work_timeout:
                last_worked = time.time()
                result = work(on_start_results, *work_args)
                for queue in work_queues:
                    if not (queue.full()):
                        queue.put(result)
                pipe_conn.send(result)

        on_stop(on_start_results, *on_stopped_args)

    @staticmethod
    @abstractmethod
    def work(on_start_results, *args):
        # Gets called in loop. Use self.set_stopped() to stop
        pass


class Consumer(Worker):
    def __init__(self, work_timeout=100, buffer_size=1, max_q_size=0):
        super().__init__()
        self.work_queues = [Queue(maxsize=max_q_size)]
        self.work_timeout = work_timeout
        self.buffer_size = buffer_size

    def purge_queue(self):
        for i in range(self.work_queues[0].qsize()):
            self.work_queues[0].get()

    # This can be used so that a queue that is subscribed to a
    # producer does not fill up while the consumer is not active
    def close_queue(self):
        self.work_queues[0].maxsize = 1

    def start_new(self, on_start_args=(), work_args=(), on_stopped_args=()):
        self.purge_queue()
        super().start_new(on_start_args=on_start_args, work_args=work_args, on_stopped_args=on_stopped_args)

    @staticmethod
    def work_loop(work, on_start, on_stop, state, work_queues,
                  on_start_args, work_args, on_stopped_args, pipe_conn, work_timeout, buffer_size):
        # Consumer only uses one work queue: its own
        assert len(work_queues) == 1
        work_queue = work_queues[0]

        on_start_results = on_start(*on_start_args)

        last_worked = time.time()
        while state.value != Worker.stopped:
            if work_queue.qsize() >= buffer_size or \
               (time.time() - last_worked) >= work_timeout or \
               state.value == Worker.stop_at_queue_end:
                last_worked = time.time()
                items = [work_queue.get() for i in range(work_queue.qsize())]
                results = work(items, on_start_results, *work_args)
                pipe_conn.send(results)
                if state.value == Worker.stop_at_queue_end:
                    state.value = Worker.stopped
                    break

        on_stop(on_start_results, *on_stopped_args)

    @staticmethod
    @abstractmethod
    def work(items, on_start_results, *args):
        # Gets called in loop. Use self.set_stopped() to stop
        pass

    def get_work_queue(self):
        return self.work_queues[0]

    def set_stop_at_queue_end(self):
        self.state.value = Worker.stop_at_queue_end