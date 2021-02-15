import threading
import time
import queue
from abc import ABCMeta, abstractmethod
import atexit


class Worker:
    __metaclass__ = ABCMeta

    stopped = "Stopped"
    started = "Started"

    def __init__(self):
        self.worker_thread = None
        self._state = self.stopped
        self.lock = threading.Lock()
        atexit.register(self.set_stopped)

    def set_stopped(self):
        self.lock.acquire()
        self._state = self.stopped
        self.lock.release()

    def get_state(self):
        self.lock.acquire()
        state = self._state
        self.lock.release()
        return state

    def start_new(self, on_start_args=(), work_args=(), on_stopped_args=()):
        if self.worker_thread is not None:
            self.set_stopped()
            while self.worker_thread.is_alive():
                time.sleep(0)
        self._state = self.started
        self.worker_thread = threading.Thread(target=self.work, args=(on_start_args, work_args, on_stopped_args), daemon=True).start()

    @abstractmethod
    def on_state_changed(self, state):
        pass

    @abstractmethod
    def work(self, *args):
        pass

    @abstractmethod
    def on_start(self, *args):
        pass

    @abstractmethod
    def on_stopped(self, *args):
        pass


class Producer(Worker):
    __metaclass__ = ABCMeta

    def __init__(self):
        super().__init__()
        self.queues = []

    def add_subscriber(self, queue):
        self.queues.append(queue)

    def remove_subscriber(self, queue):
        if queue in self.queues:
            self.queues.remove(queue)

    def work(self, on_start_args=(), work_args=(), on_stopped_args=()):
        self.on_state_changed(self.get_state())
        self.on_start(*on_start_args)
        while self.get_state() != self.stopped:
            result = self.producer_work(*work_args)
            for queue in self.queues:
                item = {
                    "command": None,
                    "data": result
                }
                queue.put(item)
        self.on_state_changed(self.get_state())
        self.on_stopped(self, *on_stopped_args)

    @abstractmethod
    def producer_work(self, *args):
        # Gets called in loop. Use self.set_stopped() to stop
        pass


class Consumer(Worker):
    __metaclass__ = ABCMeta

    def __init__(self, buffer_size=1, buffer_timeout=0):
        super().__init__()
        self.queue = queue.Queue()
        self.buffer_size = buffer_size
        self.buffer_timeout = buffer_timeout
        self.buffer = []
        self.last_time_worked = None

    def stop_at_queue_end(self):
        self.queue.put({"command": "stop"})

    def work(self,  on_start_args=(), work_args=(), on_stopped_args=()):
        self.on_state_changed(self.get_state())
        self.on_start(*on_start_args)
        while 1:  # Continuously check for both state change and new item in queue
            if self.get_state() == self.stopped:
                break
            if not self.queue.empty():
                item = self.queue.get()
                self.buffer.append(item)

                if item["command"] == "stop":
                    # clear the buffer then stop
                    self.consumer_work(self.buffer, *work_args)
                    self.set_stopped()
                    break

                # if buffer timeout or buffer sizeout, do work on buffer
                if (time.time() - self.last_time_worked) >= self.buffer_timeout or \
                        len(self.buffer) >= self.buffer_size:
                    self.consumer_work(self.buffer, *work_args)

                self.consumer_work(item["data"], *work_args)
            time.sleep(0.00001)  # Yield to thread scheduler

        self.on_state_changed(self.get_state())
        self.on_stopped(*on_stopped_args)

    @abstractmethod
    def consumer_work(self, item, *args):
        # Gets called in loop. Use self.set_stopped() to stop
        pass

    def on_state_changed(self, state):
        if self.get_state() == self.started:
            self.last_time_worked = time.time()
