import sys
import numpy as np
from PyQt5 import QtWidgets, uic, QtCore
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar
)
import matplotlib
import matplotlib.pyplot
from abi_pyeit.app.eit import *
import pyvisa
from thread_helpers.worker import Producer, Consumer
import threading
import time
import codecs

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/layout.ui")

# default_pickle = "configuration/mesha06_bumpychestslice_pickle_dist1_step1"
default_pickle = "configuration/mesha06_bumpychestslice_pickle_lm"
default_conf = "configuration/conf.json"
default_baud_rate = 115200
frame_start_char = "m"
read_timeout = 10000
read_termination_char = "\n"
encoding = "latin-1"  # We sometimes get bytes from the spectra that aren't ascii or utf-8. Not sure what they are. Haven't seen it not work with this yet


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setupUi(self)
        self.canvas = None
        self.toolbar = None
        self.fig = None
        self.populate_devices()
        self.reader = Reader()
        self.data_writer = DataWriter()
        self.plotter = PlotterConsumer()
        self.add_plot(matplotlib.figure.Figure())
        self.pickle = default_pickle
        self.conf = default_conf
        self.initial_background = None

        self.set_background_button.clicked.connect(lambda: self.plotter.set_background(self.plotter.get_current_frame()))
        self.clear_background_button.clicked.connect(lambda: self.plotter.set_background(None))

    def add_plot(self, fig):
        self.fig = fig
        self.canvas = FigureCanvas(fig)
        self.toolbar = NavigationToolbar(self.canvas, self.widget, coordinates=True)

        self.verticalLayout.addWidget(self.canvas)
        self.verticalLayout.addWidget(self.toolbar)
        self.canvas.draw()

    def update_plot(self, eit_image, obj):
        fig, imgs = create_plot([eit_image], obj)
        canvas = FigureCanvas(fig)

        self.verticalLayout.removeWidget(self.canvas)
        self.canvas.deleteLater()
        self.canvas = None

        self.verticalLayout.removeWidget(self.toolbar)
        self.toolbar.deleteLater()
        self.toolbar = None

        old_fig = self.fig
        self.fig = fig
        self.canvas = canvas
        self.toolbar = NavigationToolbar(self.canvas, self.widget, coordinates=True)

        self.verticalLayout.addWidget(self.canvas)
        self.verticalLayout.addWidget(self.toolbar)
        self.canvas.draw()

        matplotlib.pyplot.close(old_fig)
        # old_fig.close()

    def populate_devices(self):
        self.comboBox.addItems(pyvisa.ResourceManager().list_resources())

    def change_device(self, text):
        if self.data_writer.get_state() != self.data_writer.started:
            self.reader.add_subscriber(self.data_writer.queue)
            self.data_writer.start_new(on_stopped_args="", work_args="", on_start_args="")
            self.data_writer.new_data.connect(lambda data: self.textEdit.append(data))

        if self.plotter.get_state() != self.plotter.started:
            self.reader.add_subscriber(self.plotter.queue)
            self.plotter.start_new(on_start_args=(self.pickle, self.conf, self.initial_background), work_args=(), on_stopped_args=())
            self.plotter.new_data.connect(lambda data: self.update_plot(data[0], data[1]))

        if self.reader.get_state() != self.reader.stopped:
            self.reader.set_stopped()

        self.reader.start_new(on_start_args=(text,), work_args=(), on_stopped_args=())


class Reader(Producer, QtCore.QObject):
    state_signal = QtCore.pyqtSignal(str)

    def __init__(self):
        Producer.__init__(self)
        QtCore.QObject.__init__(self)
        self.device = None

    def on_start(self, device_name):
        self.device = pyvisa.ResourceManager().open_resource(device_name)
        self.device.timeout = read_timeout
        self.device.baud_rate = default_baud_rate
        self.device.encoding = encoding
        self.device.flush(pyvisa.resources.resource.constants.VI_IO_IN_BUF)
        self.device.read_termination = read_termination_char

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
            if data[0] != frame_start_char:
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

    def on_start(self, pickle, conf, initial_background):
        self.eit_obj = unpickle_eit(pickle)
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
                self.new_data.emit((eit_image, self.eit_obj))

        return


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    dw = QtWidgets.QDesktopWidget()

    main_window.resize(dw.availableGeometry(dw).size() * 0.7)

    main_window.comboBox.currentTextChanged.connect(main_window.change_device)

    main_window.show()
    app.exec()





