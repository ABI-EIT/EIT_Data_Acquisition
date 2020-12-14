import sys
import numpy as np
from PyQt5 import QtWidgets, uic, QtCore, QtGui
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar
)
import matplotlib
import matplotlib.pyplot
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.animation import FuncAnimation
from abi_pyeit.app.eit import *
import pyvisa
from thread_helpers.worker import Producer, Consumer
import threading
import time
import codecs
import matplotlib.tri as tri

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/layout.ui")

# default_pickle = "configuration/mesha06_bumpychestslice_pickle_dist1_step1"
default_pickle = "configuration/mesha06_bumpychestslice_pickle"
default_conf = "configuration/conf.json"
default_baud_rate = 115200
frame_start_char = "m"
read_timeout = 10000
read_termination_char = "\n"
encoding = "latin-1"  # We sometimes get bytes from the spectra that aren't ascii or utf-8. Not sure what they are. Haven't seen it not work with this yet


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.first_plot = True
        self.setupUi(self)
        self.canvas = None
        self.toolbar = None
        self.ax = None
        self.populate_devices()
        self.reader = Reader()
        self.data_writer = DataWriter()
        self.plotter = PlotterConsumer()
        self.bm = None
        self.add_plot()
        self.conf = default_conf
        self.initial_background = None
        self.cb = None
        self.plot_image = None
        self.divider = None
        self.color_axis = None

        self.eit_obj = self.initialize_eit_obj(default_pickle, self.conf)

        self.set_background_button.clicked.connect(lambda: self.plotter.set_background(self.plotter.get_current_frame()))
        self.clear_background_button.clicked.connect(lambda: self.plotter.set_background(None))

    def initialize_eit_obj(self, pickle, conf):
        conf = load_conf(conf)
        setup = conf["setup"]

        eit_obj = unpickle_eit(pickle)
        eit_obj.setup(p=setup["p"], lamb=setup["lamb"], method=setup["method"])

        return eit_obj

    def add_plot(self):
        self.canvas = FigureCanvas(matplotlib.figure.Figure())
        self.ax = self.canvas.figure.subplots()
        self.toolbar = NavigationToolbar(self.canvas, self.widget, coordinates=True)

        self.verticalLayout.addWidget(self.canvas)
        self.verticalLayout.addWidget(self.toolbar)

    def update_plot(self, triangulation, eit_image, electrode_points):
        start_time = time.time()

        self.ax.clear()

        self.plot_image = self.ax.tripcolor(triangulation, eit_image)
        self.plot_image.axes.set_aspect('equal')

        for i, e in enumerate(electrode_points):
            self.ax.text(e[0], e[1], str(i + 1), size=12)

        # if self.first_plot:
        #     self.divider = make_axes_locatable(self.ax)
        #     self.color_axis = self.divider.append_axes("right", size="5%", pad=0.1)
        #     self.color_axis.yaxis.tick_right()
        #     self.cb = self.ax.figure.colorbar(self.plot_image, cax=self.color_axis)
        #     self.first_plot = False
        #
        # else:
        #     self.color_axis.clear()
        #     self.cb = self.ax.figure.colorbar(self.plot_image, cax=self.color_axis)

        self.ax.figure.canvas.draw()


        elapsed_time = time.time()-start_time
        print("Plotting time: %.2fs" % elapsed_time)

    def populate_devices(self):
        self.comboBox.addItems(pyvisa.ResourceManager().list_resources())
        self.comboBox.setCurrentIndex(-1)

    def change_device(self, text):
        if self.data_writer.get_state() != self.data_writer.started:
            self.reader.add_subscriber(self.data_writer.queue)
            self.data_writer.start_new(on_stopped_args="", work_args="", on_start_args="")
            self.data_writer.new_data.connect(lambda data: self.textEdit.append(data))

        if self.plotter.get_state() != self.plotter.started:
            self.reader.add_subscriber(self.plotter.queue)
            self.plotter.start_new(on_start_args=(self.eit_obj, self.conf, self.initial_background), work_args=(), on_stopped_args=())
            self.plotter.new_data.connect(lambda data: self.update_plot(data[0], data[1], data[2]))

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


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    dw = QtWidgets.QDesktopWidget()

    main_window.resize(dw.availableGeometry(dw).size() * 0.7)

    main_window.comboBox.currentTextChanged.connect(main_window.change_device)

    main_window.show()
    app.exec()





