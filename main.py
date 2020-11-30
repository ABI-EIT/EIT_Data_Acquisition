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
import time

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/layout.ui")


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
        self.pickle = "configuration/mesha06_bumpychestslice_pickle"
        self.conf = "configuration/conf.json"
        self.background = None

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
        self.rm = pyvisa.ResourceManager()
        self.comboBox.addItems(self.rm.list_resources())

    def change_device(self, text):
        if self.data_writer.get_state() != self.data_writer.started:
            self.reader.add_subscriber(self.data_writer.queue)
            self.data_writer.start_new(on_stopped_args="", work_args="", on_start_args="")
            self.data_writer.new_data.connect(lambda data: self.textEdit.append(data))

        if self.plotter.get_state() != self.plotter.started:
            self.reader.add_subscriber(self.plotter.queue)
            self.plotter.start_new(on_start_args=(self.pickle, self.conf, self.background), work_args=(), on_stopped_args=())
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
        rm = pyvisa.ResourceManager()
        self.device = rm.open_resource(device_name)
        self.device.baud_rate = 115200

    def on_stopped(self, on_stopped_message):
        if self.device is not None:
            self.device.close()
        pass

    def producer_work(self, *args):
        try:
            while self.device.bytes_in_buffer < 2048:
                time.sleep(0.01)
            data = self.device.read()
        except pyvisa.errors.VisaIOError as e:
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

    def __init__(self):
        Consumer.__init__(self)
        QtCore.QObject.__init__(self)

    def on_start(self, pickle, conf, background):
        self.eit_obj = unpickle_eit(pickle)
        self.conf = load_conf(conf)
        if background is not None:
            self.background = load_oeit_data(background)[0]
        else:
            self.background = None

    def on_stopped(self, *args):
        pass

    def consumer_work(self, item, *args):
        if item is not None:
            data = parse_oeit_line(item)
            if data is not None:
                eit_image = process_frame(self.eit_obj, data, self.conf, self.background)
                self.new_data.emit((eit_image,self.eit_obj))

        return


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    dw = QtWidgets.QDesktopWidget()

    main_window.resize(dw.availableGeometry(dw).size() * 0.7)


    main_window.comboBox.currentTextChanged.connect(main_window.change_device)

    main_window.show()
    app.exec()






