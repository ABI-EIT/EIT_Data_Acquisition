from background_workers import *
import time

run_time_1 = 5
run_time_2 = 10
conf_1 = {
    "sleep_time": 5,
    "data": "big data: big, big, big, big, big, big, big, big, big, data,\
         big, big, big, big, big, big, big, big, big, data,\
         big, big, big, big, big, big, big, big, big, data,\
         big, big, big, big, big, big, big, big, big, data,\
         big, big, big, big, big, big, big, big, big, data,\
         big, big, big, big, big, big, big, big, big, data,\
         big, big, big, big, big, big, big, big, big, data,\
         big, big, big, big, big, big, big, big, big, data,\
         big, big, big, big, big, big, big, big, big, data,\
         big, big, big, big, big, big, big, big, big, data,\
         big, big, big, big, big, big, big, big, big, data"
}

conf_2 = {
    "sleep_time": 0.01,
    "data": "small data"
}

data_saving_configuration = {
    "directory": "data/",
    "format": "%Y-%m-%dT%H_%M_eit",
    "default_suffix": "data",
    "columns": ["Time", "small_data", "big_data"],
    "timestamp_format": "raw",
    "delimiter": ",",
    "extension": ".csv"
}


class DataCreator(Producer):

    def __init__(self, tag=None):
        Producer.__init__(self)
        self.device = None
        self.configuration = None
        self.tag = tag

    def on_start(self, configuration):
        self.configuration = configuration

    def on_stopped(self, on_stopped_message):
        pass

    def producer_work(self, *args):
        time.sleep(self.configuration["sleep_time"])
        data = self.configuration["data"]

        return {"tag": self.tag, "data": data, "timestamp": time.time()}

    def on_state_changed(self, state):
        pass


if __name__ == "__main__":
    start_time = time.time()
    saver = DataSaver(buffer_size=50, buffer_timeout=3)

    creator_1 = DataCreator(tag="big_data")
    creator_2 = DataCreator(tag="small_data")

    creator_1.add_subscriber(saver.queue)
    creator_1.start_new(on_start_args=(conf_1,))

    saver.start_new(on_start_args=("", data_saving_configuration))

    while time.time() - start_time <= run_time_1:
        pass

    start_time_2 = time.time()

    creator_2.add_subscriber(saver.queue)
    creator_2.start_new(on_start_args=(conf_2,))

    while time.time() - start_time_2 <= run_time_2:
        pass
