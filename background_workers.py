from PyQt5 import QtCore
from thread_helpers.worker import Producer, Consumer
import matplotlib.tri as tri
import pyvisa
import threading
from abi_pyeit.app.eit import load_oeit_data, load_conf, parse_oeit_line, process_frame


class Reader(Producer, QtCore.QObject):
    state_signal = QtCore.pyqtSignal(str)

    def __init__(self):
        Producer.__init__(self)
        QtCore.QObject.__init__(self)
        self.device = None
        self.spectra_configuration = None

    def on_start(self, device_name, spectra_configuration):
        self.spectra_configuration = spectra_configuration
        self.device = pyvisa.ResourceManager().open_resource(device_name)
        self.device.timeout = spectra_configuration["read_timeout"]
        self.device.baud_rate = spectra_configuration["baud"]
        self.device.encoding = spectra_configuration["encoding"]
        self.device.flush(pyvisa.resources.resource.constants.VI_IO_IN_BUF)
        self.device.read_termination = spectra_configuration["read_termination_char"]

    def on_stopped(self, on_stopped_message):
        if self.device is not None:
            pyvisa.ResourceManager()  # Need to instatiate this here or resource will become invalid before we can close it. Not sure why
            try:
                self.device.close()
            except pyvisa.errors.VisaIOError as e:
                print(e)
                pass
        pass

    def producer_work(self, *args):
        try:
            data = self.device.read()
            if data[0] != self.spectra_configuration["frame_start_char"]:
                return None
        except pyvisa.errors.VisaIOError as e:
            print(e)
            return None
        except UnicodeDecodeError as e:
            print(e)
            return None
        return data

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
        if item is not None:
            self.new_data.emit(item)


class PlotterConsumer(Consumer, QtCore.QObject):
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
        if item is not None:
            data = parse_oeit_line(item)
            if data is not None:
                self.set_current_frame(data)
                eit_image = process_frame(self.eit_obj, data, self.conf, self.get_background())

                pts = self.eit_obj.mesh['node']
                triangles = self.eit_obj.mesh['element']
                x = pts[:, 0]
                y = pts[:, 1]
                triangulation = tri.Triangulation(x, y, triangles=triangles)

                electrode_points = [(x[e],y[e]) for e in self.eit_obj.el_pos]

                self.new_data.emit((triangulation, eit_image, electrode_points))

        return


class DataSaver(Consumer):
    def on_start(self, *args):
        pass

    def on_stopped(self, *args):
        pass

    def consumer_work(self, item, *args):
        pass