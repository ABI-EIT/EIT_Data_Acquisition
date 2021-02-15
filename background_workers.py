from PyQt5 import QtCore
from thread_helpers.worker import Producer, Consumer
import matplotlib.tri as tri
import pyvisa
import threading
from abi_pyeit.app.eit import load_oeit_data, load_conf, parse_oeit_line, process_frame
import os
from datetime import datetime
from time import time
import csv
import numpy as np


class Reader(Producer, QtCore.QObject):
    """
        Reader sends messages of type:
            { "tag": "tag"
              "data":  data }
    """
    state_signal = QtCore.pyqtSignal(str)

    def __init__(self, tag=None):
        Producer.__init__(self)
        QtCore.QObject.__init__(self)
        self.device = None
        self.configuration = None
        self.tag = tag

    def on_start(self, device_name, configuration):
        self.configuration = configuration
        self.device = pyvisa.ResourceManager().open_resource(device_name)
        self.device.timeout = configuration["read_timeout"]
        self.device.baud_rate = configuration["baud"]
        self.device.encoding = configuration["encoding"]
        self.device.flush(pyvisa.resources.resource.constants.VI_IO_IN_BUF)
        self.device.read_termination = configuration["read_termination_char"]

    def on_stopped(self, on_stopped_message):
        if self.device is not None:
            pyvisa.ResourceManager()  # Need to instantiate this here or resource will become invalid before we can close it. Not sure why
            try:
                self.device.close()
            except pyvisa.errors.VisaIOError as e:
                print(e)
                pass
        pass

    def producer_work(self, *args):
        try:
            data = self.device.read()
            if self.configuration["frame_start_char"] is not None and data[0] != self.configuration["frame_start_char"]:
                return None
        except pyvisa.errors.VisaIOError as e:
            print(e)
            return None
        except UnicodeDecodeError as e:
            print(e)
            return None
        return {"tag": self.tag, "data": data}

    def on_state_changed(self, state):
        self.state_signal.emit(state)


class DataWriter(Consumer, QtCore.QObject):
    state_signal = QtCore.pyqtSignal(str)
    new_data = QtCore.pyqtSignal(str)

    def __init__(self):
        Consumer.__init__(self)
        QtCore.QObject.__init__(self)

    def on_start(self, *args):
        pass

    def on_stopped(self, *args):
        pass

    def consumer_work(self, item, *args):
        if item[0] is not None:
            self.new_data.emit(item[0]["data"])


class EITProcessor(Consumer, QtCore.QObject):
    state_signal = QtCore.pyqtSignal(str)
    new_data = QtCore.pyqtSignal(tuple)
    eit_obj = None
    conf = None

    background_lock = threading.Lock()
    background = None

    current_frame_lock = threading.Lock()
    current_frame = None

    def __init__(self):
        Consumer.__init__(self)
        QtCore.QObject.__init__(self)

    def on_start(self, eit_obj, conf, initial_background):
        self.eit_obj = eit_obj
        self.conf = load_conf(conf)
        if initial_background is not None:
            self.background = load_oeit_data(initial_background)[0]
        else:
            self.background = None

    def set_background(self, background):
        self.background_lock.acquire()
        self.background = background
        self.background_lock.release()

    def get_background(self):
        self.background_lock.acquire()
        background = self.background
        self.background_lock.release()
        return background

    def set_current_frame(self, frame):
        self.current_frame_lock.acquire()
        self.current_frame = frame
        self.current_frame_lock.release()

    def get_current_frame(self):
        self.current_frame_lock.acquire()
        current_frame = self.current_frame
        self.current_frame_lock.release()
        return current_frame

    def on_stopped(self, *args):
        pass

    def consumer_work(self, item, *args):
        item = item[0]
        if item is not None:
            data = parse_oeit_line(item["data"])
            if data is not None:
                self.set_current_frame(data)
                eit_image = process_frame(self.eit_obj, data, self.conf, self.get_background())

                pts = self.eit_obj.mesh['node']
                triangles = self.eit_obj.mesh['element']
                x = pts[:, 0]
                y = pts[:, 1]
                triangulation = tri.Triangulation(x, y, triangles=triangles)

                electrode_points = [(x[e], y[e]) for e in self.eit_obj.el_pos]

                self.new_data.emit((triangulation, eit_image, electrode_points))

        return


class DataSaver(Consumer):
    def __init__(self, buffer_size=1, buffer_timeout=0):
        Consumer.__init__(self, buffer_size, buffer_timeout)
        self.file = None
        self.csv_writer = None
        self.file_lock = threading.Lock()
        self.data_saving_configuration = None

    @staticmethod
    def create_unique_save_file(suffix, data_saving_configuration):
        directory = data_saving_configuration["directory"]
        date_format = data_saving_configuration["format"]
        default_suffix = data_saving_configuration["default_suffix"]
        ext = data_saving_configuration["extension"]

        if suffix == "":
            suffix = default_suffix

        if not os.path.exists(directory):
            os.mkdir(data_saving_configuration["directory"])

        file_name = datetime.now().strftime(date_format) + "_" + suffix
        addition = ""

        i = 1
        while os.path.exists(directory + file_name + addition + ext):
            addition = "_" + str(i)
            i += 1

        return open(directory + file_name + addition + ext, "x", newline="")

    def on_start(self, suffix, data_saving_configuration):
        self.file_lock.acquire()
        self.file = self.create_unique_save_file(suffix, data_saving_configuration)
        self.csv_writer = csv.writer(self.file, delimiter=data_saving_configuration["delimiter"], quoting=csv.QUOTE_MINIMAL)
        self.csv_writer.writerow(data_saving_configuration["columns"])
        # TODO Write file with header section
        self.data_saving_configuration = data_saving_configuration
        self.file_lock.release()

    def on_stopped(self, *args):
        self.file_lock.acquire()
        self.file.close()
        self.file_lock.release()

    def get_filename(self):
        self.file_lock.acquire()
        filename = self.file.name
        self.file_lock.release()
        return filename

    def consumer_work(self, buffer, *args):
        buffer = np.array(buffer)
        buffer = buffer[buffer != np.array(None)]

        self.file_lock.acquire()

        # # Strip newline characters
        # data = str.rstrip(item["data"])
        output_list = []

        if "timestamp_format" in self.data_saving_configuration and self.data_saving_configuration[
            "timestamp_format"] is not None:
            if self.data_saving_configuration["timestamp_format"] == "raw":
                time_string = str(time())
            else:
                time_string = time.strftime(self.data_saving_configuration["timestamp_format"])
        else:
            time_string = None

        for item in buffer:
            columns = self.data_saving_configuration["columns"]
            output = [None] * len(columns)
            if "Time" in columns:
                output[columns.index("Time")] = time_string

            if item["tag"] in columns:
                output[columns.index(item["tag"])] = item["data"]

            output_list.append(output)

        self.csv_writer.writerows(output_list)
        self.file.flush()
        self.file_lock.release()
