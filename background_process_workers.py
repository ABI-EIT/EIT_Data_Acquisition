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
import serial
from serial.tools import list_ports
from scipy import integrate
from scipy import signal
import pandas as pd
import io
from multiprocessing import Pipe


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
        self.work_args = (tag,)
        self.on_connect_failed = None

    @staticmethod
    def on_start(state, message_pipe, *args):
        device_name = args[0]
        configuration = args[1]
        try:
            device = serial.Serial(port=device_name, baudrate=configuration["baud"], timeout=configuration["read_timeout"])
            device.flushInput()
        except serial.SerialException as e:
            device = None
            print(e)
            state.value = Producer.stopped
            message_pipe.send("connect failed")
        return {"configuration": configuration, "device": device}

    @staticmethod
    def on_stop(on_start_results, state, message_pipe, *args):
        print("Reader stopped")
        device = on_start_results["device"]
        if device is not None:
            try:
                device.close()
            except serial.SerialException as e:
                print(e)
                pass
        pass

    @staticmethod
    def work(on_start_results, state, message_pipe, *args):
        tag = args[0]
        device = on_start_results["device"]
        configuration = on_start_results["configuration"]

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
    def work(items, on_start_results, state, message_pipe, *args):
        return [item for item in items if item is not None]

    def on_result_ready(self, results):
        if results is not None and len(results) > 0:
            self.new_data.emit([result for result in results if result is not None])


class BidirectionalVenturiFlowCalculator(Consumer, QtCore.QObject):

    state_signal = QtCore.pyqtSignal(str)
    new_data = QtCore.pyqtSignal(list)

    def __init__(self, work_timeout=0, buffer_size=1):
        Consumer.__init__(self, work_timeout, buffer_size)
        QtCore.QObject.__init__(self)
        self.con1, con2 = Pipe()
        self.work_args = (con2,)

    @staticmethod
    def on_start(state, message_pipe, *args):
        df = pd.DataFrame()
        config = args[0]

        return {"df": df, "config": config}

    @staticmethod
    def work(items, on_start_results, state, message_pipe, *args):
        if not items:
            return None

        filtered = []
        for item in items:
            try:
                if item is not None and item["data"] is not None:
                    item["data"] = float(item["data"])
                    filtered.append(item)
            except ValueError:
                pass

        items = filtered

        df = on_start_results["df"]
        config = on_start_results["config"]

        tags = np.array([item["tag"] for item in items])
        multipliers = np.array([config["{0}_multiplier".format(tag)] for tag in tags])
        offsets = np.array([config["{0}_offset".format(tag)] for tag in tags])

        data = np.array([item["data"] for item in items])
        timestamp = np.array([item["timestamp"] for item in items])

        # Convert pressure to flow and apply calibration
        data[np.where(data < 0)] = 0
        data = np.power(data, 0.5)
        data = (data*multipliers)-offsets

        # Put data in correct column based on tag
        data_array = []
        for i in range(len(data)):
            row = [None] * len(set(tags))
            row[list(set(tags)).index(tags[i])] = data[i]
            data_array.append(row)

        df_new = pd.DataFrame(columns=set(tags), data=data_array, index=pd.to_datetime(timestamp, unit="s"))

        if len(df) > 0:
            df = df.append(df_new)  # assume df_new is later than df
        else:
            df = df_new

        df = df.groupby(df.index).first()
        df = df.fillna(method="pad")
        df = df.resample(config["resample"]).pad()

        window = df.last(config["buffer"])
        if "Naive Volume (L)" in df.columns and len(window) < len(df):
            vol_leaving_window = df["Naive Volume (L)"].loc[window.index[0]-1*df.index.freq]
        else:
            vol_leaving_window = 0
        df = window # select last n seconds
        if df.empty:
            return None

        df["abs_max"] = df.fillna(0).apply(lambda row: max([row[col] for col in list(set(config["columns"]).intersection(df.columns))], key=abs), axis=1)

        fs = config["sampling_freq"]
        fc = config["cutoff_freq"]  # Cut-off frequency of the filter
        w = fc / (fs / 2)  # Normalize the frequency
        b, a = signal.butter(config["order"], w, 'low')
        pad_len = 3 * max(len(a), len(b)) # default filtfilt pad len
        if len(df["abs_max"]) < pad_len:
            return None
        df["abs_max_filtered"] = signal.filtfilt(b, a, df["abs_max"].fillna(0))
        # df["abs_max_filtered"] = df["abs_max"].dropna()

        df["abs_max_filtered"].mask(df["abs_max_filtered"].abs() <= config["flow_threshold"], 0, inplace=True)

        df["Naive Volume (L)"] = integrate.cumtrapz(df["abs_max_filtered"], x=df.index.astype(np.int64) / 10 ** 9,
                                                    initial=0) + vol_leaving_window

        con = args[0]
        if con.poll():
            value = con.recv()
            df = pd.DataFrame(columns=["Naive Volume (L)"], data=[value], index = [df.index[-1]])

        on_start_results["df"] = df

        return [{"tag": "Volume", "data": element[0], "timestamp": element[1]} for element in
                zip(df["Naive Volume (L)"], df.index.astype(np.int64) / 10 ** 9)]

    @staticmethod
    def on_stop(on_start_results, state, message_pipe, *args):
        pass

    def on_result_ready(self, results):
        if results is not None and len(results) > 0:
            self.new_data.emit([result for result in results if result is not None])

    def set_zero(self):
        self.con1.send(0.0)


class EITProcessor(Consumer, QtCore.QObject):
    new_data = QtCore.pyqtSignal(tuple)

    def __init__(self):
        Consumer.__init__(self)
        QtCore.QObject.__init__(self)
        man = Manager()
        self.bg_dict = man.dict()
        self.bg_dict["background"] = None
        self.bg_dict["current_frame"] = None
        self.on_start_args = (self.bg_dict,)

    @staticmethod
    def on_start(state, message_pipe, *args):
        bg_dict = args[0]
        eit_obj = args[1]
        conf = args[2]
        initial_background = args[3]
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
    def work(items, on_start_results, state, message_pipe, *args):
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
        if result is not None and len(result) > 0:
            # EIT data comes in one at at time
            self.new_data.emit(result[0])


class DataSaver(Consumer):
    def __init__(self, buffer_size=1, buffer_timeout=0):
        Consumer.__init__(self, buffer_size, buffer_timeout)
        man = Manager()
        self.filename_dict = man.dict()
        self.filename_dict["filename"] = None
        self.on_start_args = (self.filename_dict,)

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
    def on_start(state, message_pipe, *args):
        filename_dict = args[0]
        suffix = args[1]
        data_saving_configuration = args[2]
        file = DataSaver.create_unique_save_file(suffix, data_saving_configuration)
        filename_dict["filename"] = file.name
        csv_writer = csv.writer(file , delimiter=data_saving_configuration["delimiter"], quoting=csv.QUOTE_MINIMAL)
        csv_writer.writerow(data_saving_configuration["columns"])
        # TODO Write file with header section
        return file, csv_writer, data_saving_configuration

    @staticmethod
    def on_stop(on_start_results, state, message_pipe, *args):
        file = on_start_results[0]
        file.close()

    def get_filename(self):
        return self.filename_dict["filename"]

    @staticmethod
    def work(buffer, on_start_results, state, message_pipe, *args):
        buffer = np.array(buffer)
        buffer = buffer[buffer != np.array(None)]

        file = on_start_results[0]
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
