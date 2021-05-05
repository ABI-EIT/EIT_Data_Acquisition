import concurrent_workers
import time
from itertools import count


class ExampleProducer(concurrent_workers.Producer):

    @staticmethod
    def on_start(state, message_pipe, *args, **kwargs):
        return {"count": count()}

    @staticmethod
    def work(shared_var, state, message_pipe, *args):
        return next(shared_var["count"])


class ExampleConsumer(concurrent_workers.Consumer):

    @staticmethod
    def work(items, shared_var, state, message_pipe, *args):
        return f"Got :{items} from producer"

    def on_result_ready(self, result):
        print(result)


if __name__ == "__main__":
    example_producer = ExampleProducer(work_timeout=1)
    example_consumer = ExampleConsumer(work_timeout=2, max_buffer_size=1000)

    example_producer.set_subscribers([example_consumer.get_work_queue()])
    example_producer.start_new()
    example_consumer.start_new()

    time.sleep(10)
