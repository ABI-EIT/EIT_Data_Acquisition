from multiprocessing import Process, Value, Pipe, Queue
from threading import Thread
import time
from abc import ABCMeta, abstractmethod
import atexit
from queue import Empty
import ctypes


class Worker:
    __metaclass__ = ABCMeta

    stopped = 1
    started = 2
    stop_at_queue_end = 3

    def __init__(self):
        self.process = None
        self.result_thread = None
        self.message_thread = None
        self.work_queues = []
        self.state = Value('i', 1)
        self.result_pipe_parent, self.result_pipe_child = Pipe()  # Producer and Consumer put results into this pipe
        self.message_pipe_parent, self.message_pipe_child = Pipe()  # Derived classes have access to this through on_start, on_stop, and work
        atexit.register(self.set_stopped)
        self.work_timeout = 0
        self.max_buffer_size = 1
        self.work_args = ()
        self.work_kwargs = {}

    def get_state(self):
        return self.state.value

    def start_new(self, work_args=(), work_kwargs=None):
        if work_kwargs is None:
            work_kwargs = {}
        if self.process is not None:
            self.set_stopped()
            while self.process.is_alive():
                time.sleep(0)
        self.state.value = Worker.started
        self.process = Process(target=self.work_loop,
                               args=(self.work, self.on_start, self.on_stop, self.state, self.work_queues,
                                     (*self.work_args, *work_args), {**self.work_kwargs, **work_kwargs},
                                     self.result_pipe_child, self.message_pipe_child, self.work_timeout, self.max_buffer_size))
        self.process.start()
        self.result_thread = Thread(target=self.wait_on_result_pipe, daemon=True)
        self.result_thread.start()
        self.message_thread = Thread(target=self.wait_on_message_pipe, daemon=True)
        self.message_thread.start()

    @staticmethod
    @abstractmethod
    def work_loop(*args, **kwargs):
        pass

    @staticmethod
    @abstractmethod
    def work(*args, **kwargs):
        pass

    @staticmethod
    def on_start(state, message_pipe, *args, **kwargs):
        pass

    @staticmethod
    def on_stop(shared_var, state, message_pipe, *args, **kwargs):
        pass

    def set_stopped(self):
        self.state.value = Worker.stopped

    def wait_on_result_pipe(self):
        while 1:
            try:
                result = self.result_pipe_parent.recv()
                self.on_result_ready(result)
            except BrokenPipeError:
                return

    def wait_on_message_pipe(self):
        while 1:
            try:
                message = self.message_pipe_parent.recv()
                self.on_message_ready(message)
            except BrokenPipeError:
                return

    def on_result_ready(self, result):
        pass

    def on_message_ready(self, message):
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
                  work_args, work_kwargs, result_pipe, message_pipe, work_timeout, buffer_size):
        # Producer does not make use of the buffer size argument
        assert buffer_size == 1
        shared_var = on_start(state, message_pipe, *work_args, **work_kwargs)

        last_worked = time.time()
        while state.value != Worker.stopped:
            if time.time()-last_worked >= work_timeout:
                last_worked = time.time()
                result = work(shared_var, state, message_pipe, *work_args, **work_kwargs)
                for queue in work_queues:
                    if queue.is_ready() and not (queue.full()):
                        queue.put(result)
                result_pipe.send(result)

                # sleep until it's time to work again (if there is time)
                sleep_time = max(0, work_timeout - (time.time() - last_worked) - 0.000001)
                time.sleep(sleep_time)

        on_stop(shared_var, state, message_pipe, *work_args, **work_kwargs)

    @staticmethod
    @abstractmethod
    def work(shared_var, state, message_pipe, *args):
        # Gets called in loop. Use self.set_stopped() to stop
        pass


class Consumer(Worker):
    def __init__(self, work_timeout=5, max_buffer_size=1, lossy_queue=False, *args, **kwargs):
        super().__init__()
        maxsize = kwargs.pop("maxsize", 0)
        self.work_queues = [ReadyQueue(lossy=lossy_queue, maxsize=maxsize)]

        # work_timeout is the time to wait between work and the timeout for queue.get
        self.work_timeout = work_timeout
        self.max_buffer_size = max_buffer_size

    def start_new(self, work_args=(), work_kwargs=None):
        if work_kwargs is None:
            work_kwargs = {}
        self.work_queues[0].set_ready()
        super().start_new(work_args=work_args, work_kwargs=work_kwargs)

    @staticmethod
    def work_loop(work, on_start, on_stop, state, work_queues,
                  work_args, work_kwargs, result_pipe, message_pipe, work_timeout, max_buffer_size):
        # Consumer only uses one work queue: its own
        assert len(work_queues) == 1
        work_queue = work_queues[0]

        shared_var = on_start(state, message_pipe, *work_args, **work_kwargs)

        buffer = []

        last_worked = time.time()
        while state.value != Worker.stopped:
            try:
                # calling get and rebuffering so that we can wait and give someone else a chance to go
                # print(work_queue.qsize())
                buffer.append(work_queue.get(timeout=work_timeout))
            except Empty:
                # if we didn't get anything, check if we should be stopped
                continue

            if len(buffer) >= max_buffer_size or \
               (time.time() - last_worked) >= work_timeout or \
               state.value == Worker.stop_at_queue_end:

                last_worked = time.time()
                results = work(buffer, shared_var, state, message_pipe,  *work_args, **work_kwargs)
                buffer = []
                try:
                    result_pipe.send(results)
                except BrokenPipeError as e:
                    if state.value != Worker.stopped:
                        print(e)
                if state.value == Worker.stop_at_queue_end:
                    state.value = Worker.stopped
                    break

        work_queue.set_not_ready()
        on_stop(shared_var, state, message_pipe,  *work_args, **work_kwargs)

    @staticmethod
    @abstractmethod
    def work(items, shared_var, state, message_pipe, *args):
        # Gets called in loop. Use self.set_stopped() to stop
        pass

    def get_work_queue(self):
        return self.work_queues[0]

    def set_stop_at_queue_end(self):
        self.state.value = Worker.stop_at_queue_end


# https://stackoverflow.com/questions/66591320/python-multiprocessing-queue-child-class-losing-attributes-in-process/66607658#66607658
# There is an issue with making child classes from multiprocessing.queues.queue. This is a workaround
class ReadyQueue:
    def __init__(self, *args, **kwargs):
        self.lossy = kwargs.pop("lossy", False)
        self.queue = Queue(*args, **kwargs)
        self._ready = Value(ctypes.c_bool, False)

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
        if self.lossy and self.full():
            self.get()
        return self.queue.put(obj, block, timeout)

    def full(self):
        return self.queue.full()

    def empty(self):
        return self.queue.empty()

    def qsize(self):
        return self.queue.qsize()

