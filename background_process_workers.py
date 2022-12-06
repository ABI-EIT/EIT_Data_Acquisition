from PyQt5 import QtCore
from adv_prodcon import Producer, Consumer
from multiprocessing import Manager
import matplotlib.tri as tri
import threading
import json
import os
from datetime import datetime
from time import time
import csv
import numpy as np
import serial
from serial.tools import list_ports
from scipy import integrate
from scipy import signal
import pandas as pd
import io
from multiprocessing import Pipe
from eit import process_frame, parse_oeit_line, load_conf, load_oeit_data


class Reader(Producer, QtCore.QObject):
    """
        Reader sends messages of type:
            { "tag": string
              "data":  any
              "timestamp": time}
    """
    new_data = QtCore.pyqtSignal(dict)

    def __init__(self, *args, **kwargs):
        tag = kwargs.pop("tag")
        Producer.__init__(self, *args, **kwargs)
        QtCore.QObject.__init__(self)
        self.work_kwargs = {"tag": tag}
        self.on_connect_failed = None
        self.on_connect_succeeded = None

    @staticmethod
    def on_start(state, message_pipe, *args, **kwargs):
        device_name = kwargs["device_name"]
        configuration = kwargs["configuration"]
        try:
            device = serial.Serial(port=device_name, baudrate=configuration["baud"], timeout=configuration["read_timeout"])
            device.flushInput()
            message_pipe.send("connect succeeded")
        except serial.SerialException as e:
            device = None
            print(e)
            state.value = Producer.stopped
            message_pipe.send("connect failed")
        return {"configuration": configuration, "device": device}

    @staticmethod
    def on_stop(shared_var, state, message_pipe, *args, **kwargs):
        print("Reader stopped")
        device = shared_var["device"]
        if device is not None:
            try:
                device.close()
            except serial.SerialException as e:
                print(e)
                pass
        pass

    @staticmethod
    def work(shared_var, state, message_pipe, *args, **kwargs):
        tag = kwargs["tag"]
        device = shared_var["device"]
        configuration = shared_var["configuration"]

        try:
            # data = device.read_until(configuration["read_termination_char"])
            data = device.readline()
            try:
                data = data.decode(configuration["encoding"])
            except UnicodeDecodeError as e:
                print(e)
                return None
            if configuration["frame_start_char"] is not None and data[0] != configuration["frame_start_char"]:
                return None
        except serial.SerialException as e:
            state.value = Reader.stopped
            print(e)
            return None
        return {"tag": tag, "data": data, "timestamp": time()}

    def on_result_ready(self, result):
        if result is not None:
            self.new_data.emit(result)

    def on_message_ready(self, message):
        if message == "connect failed":
            if self.on_connect_failed is not None:
                self.on_connect_failed()
        if message == "connect succeeded":
            if self.on_connect_succeeded is not None:
                self.on_connect_succeeded()

    @staticmethod
    def list_devices():
        device_names = [port.name for port in list_ports.comports()]
        return device_names


# Consumer emitter. Useful because the consumer is buffered
class QueueEmitter(Consumer, QtCore.QObject):

    state_signal = QtCore.pyqtSignal(str)
    new_data = QtCore.pyqtSignal(list)

    def __init__(self, work_timeout=0, buffer_size=1):
        Consumer.__init__(self, work_timeout, buffer_size)
        QtCore.QObject.__init__(self)

    @staticmethod
    def work(items, shared_var, state, message_pipe, *args, **kwargs):
        return [item for item in items if item is not None]

    def on_result_ready(self, results):
        if results is not None and len(results) > 0:
            self.new_data.emit([result for result in results if result is not None])


class EITProcessor(Consumer, QtCore.QObject):
    new_data = QtCore.pyqtSignal(tuple)

    def __init__(self, *args, **kwargs):
        Consumer.__init__(self, lossy_queue=True, maxsize=1, *args, **kwargs)
        QtCore.QObject.__init__(self)
        man = Manager()
        self.bg_dict = man.dict()
        self.bg_dict["background"] = None
        self.bg_dict["current_frame"] = None
        self.work_kwargs = {"bg_dict": self.bg_dict}

    @staticmethod
    def on_start(state, message_pipe, *args, **kwargs):
        conf = kwargs["configuration"]
        conf = load_conf(conf)

        bg_dict = kwargs["bg_dict"]
        initial_background = kwargs["initial_bg"]
        if initial_background is not None:
            background = load_oeit_data(initial_background)[0]
        else:
            background = None
        bg_dict["background"] = background
        return {"bg_dict": bg_dict, "conf": conf}

    def set_background(self, background):
        self.bg_dict["background"] = background

    def get_background(self):
        return self.bg_dict["background"]

    def set_current_frame(self, frame):
        self.bg_dict["current_frame"] = frame

    def get_current_frame(self):
        return self.bg_dict["current_frame"]

    @staticmethod
    def work(items, shared_var, state, message_pipe, *args, **kwargs):
        bg_dict = shared_var["bg_dict"]
        eit_obj = kwargs["eit_obj"]
        conf = shared_var["conf"]
        background = bg_dict["background"]  # bg_dict is a managed dict, so shared across processes

        results = []
        for item in items:
            if item is not None:
                data = parse_oeit_line(item["data"])
                if data is not None:
                    bg_dict["current_frame"] = data
                    eit_image = process_frame(eit_obj, data, conf, background)

                    pts = eit_obj.mesh.node
                    triangles = eit_obj.mesh.element
                    x = pts[:, 0]
                    y = pts[:, 1]
                    triangulation = tri.Triangulation(x, y, triangles=triangles)

                    electrode_points = [(x[e], y[e]) for e in eit_obj.mesh.el_pos]

                    results.append((triangulation, eit_image, electrode_points))

        return results

    def on_result_ready(self, result):
        if result is not None and len(result) > 0:
            # EIT data comes in one at at time
            self.new_data.emit(result[0])


class DataSaver(Consumer):
    def __init__(self, buffer_size=1, buffer_timeout=0):
        Consumer.__init__(self, buffer_size, buffer_timeout)
        man = Manager()
        self.filename_dict = man.dict()
        self.filename_dict["filename"] = None
        self.work_kwargs = {"filename_dict": self.filename_dict}

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

    @staticmethod
    def on_start(state, message_pipe, *args, **kwargs):
        filename_dict = kwargs["filename_dict"]
        suffix = kwargs["suffix"]
        data_saving_configuration = kwargs["configuration"]
        file = DataSaver.create_unique_save_file(suffix, data_saving_configuration)
        filename_dict["filename"] = file.name
        csv_writer = csv.writer(file, delimiter=data_saving_configuration["delimiter"], quoting=csv.QUOTE_MINIMAL)
        csv_writer.writerow(data_saving_configuration["columns"])
        # TODO Write file with header section
        return {"file": file, "csv_writer": csv_writer}

    @staticmethod
    def on_stop(shared_var, state, message_pipe, *args, **kwargs):
        file = shared_var["file"]
        file.close()

    def get_filename(self):
        return self.filename_dict["filename"]

    @staticmethod
    def work(buffer, shared_var, state, message_pipe, *args, **kwargs):
        buffer = np.array(buffer)
        buffer = buffer[buffer != np.array(None)]

        file = shared_var["file"]
        csv_writer = shared_var["csv_writer"]
        data_saving_configuration = kwargs["configuration"]

        output_list = []
        for item in buffer:
            timestamp = item["timestamp"]

            if "timestamp_format" in data_saving_configuration and data_saving_configuration[
                    "timestamp_format"] is not None:
                if data_saving_configuration["timestamp_format"] == "raw":
                    time_string = str(timestamp)
                else:
                    time_string = timestamp.strftime(data_saving_configuration["timestamp_format"])
            else:
                time_string = None

            columns = data_saving_configuration["columns"]
            output = [None] * len(columns)
            if "Time" in columns:
                output[columns.index("Time")] = time_string

            if item["tag"] in columns:
                output[columns.index(item["tag"])] = item["data"]

            output_list.append(output)

        csv_writer.writerows(output_list)
        file.flush()
        return output_list


