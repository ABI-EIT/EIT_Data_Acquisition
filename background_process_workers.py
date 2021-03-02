from PyQt5 import QtCore
from process_helpers.process_worker import Producer, Consumer, put_in_queue
from multiprocessing import Manager
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
            { "tag": string
              "data":  any
              "timestamp": time}
    """
    new_data = QtCore.pyqtSignal(list)

    def __init__(self, *args, **kwargs):
        tag = kwargs.pop("tag")
        Producer.__init__(self, *args, **kwargs)
        QtCore.QObject.__init__(self)
        self.on_start_args = (tag,)

    @staticmethod
    def on_start(device_name, configuration):
        configuration = configuration
        device = pyvisa.ResourceManager().open_resource(device_name)
        device.timeout = configuration["read_timeout"]
        device.baud_rate = configuration["baud"]
        device.encoding = configuration["encoding"]
        device.flush(pyvisa.resources.resource.constants.VI_IO_IN_BUF)
        device.read_termination = configuration["read_termination_char"]

        return {"configuration": configuration, "device": device}

    @staticmethod
    def on_stopped(on_start_results):
        device = on_start_results["device"]
        if device is not None:
            pyvisa.ResourceManager()  # Need to instantiate this here or resource will become invalid before we can close it. Not sure why
            try:
                device.close()
            except pyvisa.errors.VisaIOError as e:
                print(e)
                pass
        pass

    @staticmethod
    def work(on_start_results, *args):
        tag = args[0]
        device = on_start_results["device"]
        configuration = on_start_results["configuration"]
        try:
            data = device.read()
            if configuration["frame_start_char"] is not None and data[0] != configuration["frame_start_char"]:
                return None
        except pyvisa.errors.VisaIOError as e:
            print(e)
            return None
        except UnicodeDecodeError as e:
            print(e)
            return None
        return {"tag": tag, "data": data, "timestamp": time()}

    def on_result_ready(self, result):
        emit_items = [item for item in result if item is not None]
        self.new_data.emit(emit_items)


class EITProcessor(Consumer, QtCore.QObject):
    new_data = QtCore.pyqtSignal(list)

    def __init__(self):
        Consumer.__init__(self)
        QtCore.QObject.__init__(self)
        man = Manager()
        self.bg_dict = man.dict()
        self.bg_dict["background"] = None
        self.bg_dict["current_frame"] = None
        self.on_start_args = (self.bg_dict,)

    @staticmethod
    def on_start(*args, eit_obj, conf, initial_background):
        bg_dict = args[0]
        eit_obj = eit_obj
        conf = load_conf(conf)
        if initial_background is not None:
            background = load_oeit_data(initial_background)[0]
        else:
            background = None
        bg_dict["background"] = background
        return {"bg_dict": bg_dict, "eit_obj": eit_obj, "conf": conf}

    def set_background(self, background):
        self.bg_dict["background"] = background

    def get_background(self):
        return self.bg_dict["background"]

    def set_current_frame(self, frame):
        self.bg_dict["current_frame"] = frame

    def get_current_frame(self):
        return self.bg_dict["current_frame"]

    @staticmethod
    def work(items, on_start_results, *args):
        bg_dict = on_start_results["bg_dict"]
        eit_obj = on_start_results["eit_obj"]
        conf = on_start_results["conf"]
        background = bg_dict["background"]  # bg_dict is a managed dict, so shared across processes

        results = []
        for item in items:
            if item is not None:
                data = parse_oeit_line(item["data"])
                if data is not None:
                    bg_dict["current_frame"] = data
                    eit_image = process_frame(eit_obj, data, conf, background)

                    pts = eit_obj.mesh['node']
                    triangles = eit_obj.mesh['element']
                    x = pts[:, 0]
                    y = pts[:, 1]
                    triangulation = tri.Triangulation(x, y, triangles=triangles)

                    electrode_points = [(x[e], y[e]) for e in eit_obj.el_pos]

                    results.append((triangulation, eit_image, electrode_points))

        return results

    def on_result_ready(self, result):
        emit_items = [item for item in result if item is not None]
        self.new_data.emit(emit_items)


class DataSaver(Consumer):
    def __init__(self, buffer_size=1, buffer_timeout=0):
        Consumer.__init__(self, buffer_size, buffer_timeout)
        man = Manager()
        self.file_dict = man.dict()
        self.file_dict["file"] = None
        self.on_start_args = (self.file_dict,)

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
    def on_start(suffix, data_saving_configuration, *args):
        file_dict = args[0]
        file_dict["file"] = DataSaver.create_unique_save_file(suffix, data_saving_configuration)
        csv_writer = csv.writer(file_dict["file"] , delimiter=data_saving_configuration["delimiter"], quoting=csv.QUOTE_MINIMAL)
        csv_writer.writerow(data_saving_configuration["columns"])
        # TODO Write file with header section
        return file_dict, csv_writer, data_saving_configuration

    @staticmethod
    def on_stopped(on_start_results, *args):
        file_dict = on_start_results[0]
        file_dict["file"].close()

    def get_filename(self):
        return self.file_dict["file"].name

    @staticmethod
    def work(buffer, on_start_results,  *args):
        buffer = np.array(buffer)
        buffer = buffer[buffer != np.array(None)]

        file_dict = on_start_results[0]
        file = file_dict["file"]
        csv_writer = on_start_results[1]
        data_saving_configuration = on_start_results[2]

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
