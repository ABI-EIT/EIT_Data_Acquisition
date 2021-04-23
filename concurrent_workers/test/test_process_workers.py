import unittest
from concurrent_workers import Producer, ReadyQueue


class TestWorkers(unittest.TestCase):
    def test_set_stopped(self):
        t = MyTestProducer()
        t.set_subscribers([ReadyQueue()])
        t.start_new()
        t.set_stopped()
        t.process.join()
        self.assertEqual(t.message, "stopped")


class MyTestProducer(Producer):
    def __init__(self):
        super().__init__()
        self.message = None

    @staticmethod
    def work(on_start_results, state, message_pipe, *args):
        pass

    @staticmethod
    def on_stop(shared_var, state, message_pipe, *args, **kwargs):
        message_pipe.send("stopped")

    def on_message_ready(self, message):
        self.message = message

