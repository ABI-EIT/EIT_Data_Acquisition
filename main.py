import sys
import numpy as np
from PyQt5 import QtWidgets, uic
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar
)
import matplotlib
import matplotlib.pyplot
from mpl_toolkits.axes_grid1 import make_axes_locatable
from abi_pyeit.app.eit import *
import time
from background_workers import *
from Toaster import Toaster

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/layout_with_flow.ui")

default_pickle = "configuration/mesha06_bumpychestslice_pickle_dist3"
default_conf = "configuration/conf.json"
spectra_configuration = {
    "baud": 115200,
    "frame_start_char": "m",
    "read_timeout": 10000,
    "read_termination_char": "\n",
    "encoding": "latin-1"
}
flow_configuration = {
    "baud": 19200,
    "frame_start_char": None,
    "read_timeout": 10000,
    "read_termination_char": "\n",
    "encoding": "utf-8"
}
data_saving_configuration = {
    "directory": "data/",
    "format": "%Y-%m-%dT%H_%M_eit",
    "default_suffix": "data",
    "timestamp_format": "raw",
    "delimiter": "\t"
}
flow_data_saving_configuration = {
    "directory": "data/",
    "format": "%Y-%m-%dT%H_%M_flow",
    "default_suffix": "data",
    "timestamp_format": "raw",
    "delimiter": "\t"
}
spectra_data_format = {
    "prefix": "magnitudes:        ",
    "separator": ",       "
}


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.first_plot = True
        self.setupUi(self)
        self.canvas = None
        self.plot_axes = None
        self.populate_devices()
        self.reader = Reader()
        self.flow_reader = Reader()
        self.data_writer = DataWriter()
        self.eit_processor = EITProcessor()
        self.data_saver = DataSaver()
        self.flow_data_saver = DataSaver()
        self.conf = default_conf
        self.initial_background = None
        self.color_axis = None

        self.comboBox.currentTextChanged.connect(self.change_device)
        self.startRecordingButton.clicked.connect(lambda: self.start_recording(self.dataFileSuffixTextEdit.toPlainText(), self.reader))
        self.stopRecordingButton.clicked.connect(lambda: self.stop_recording(self.reader))

        self.comboBoxFlow.currentTextChanged.connect(self.change_flow_device)
        self.startRecordingButtonFlow.clicked.connect(lambda: self.start_recording_flow(self.dataFileSuffixTextEditFlow.toPlainText(), self.flow_reader))
        self.stopRecordingButtonFlow.clicked.connect(lambda: self.stop_recording_flow(self.flow_reader))

        self.eit_obj = self.initialize_eit_obj(default_pickle, self.conf)

        self.set_background_button.clicked.connect(self.set_background)
        self.clear_background_button.clicked.connect(lambda: self.eit_processor.set_background(None))

    def set_background(self):
        current_frame = self.eit_processor.get_current_frame()
        self.eit_processor.set_background(current_frame)
        background_file = DataSaver.create_unique_save_file("background", data_saving_configuration)
        background_file.write(spectra_data_format["prefix"] + "".join(("{}"+spectra_data_format["separator"]).format(item) for item in current_frame))
        background_file.close()
        Toaster.showMessage(self, "Background frame saved in: " + background_file.name)

    def start_recording(self, suffix, reader):
        self.stopRecordingButton.setVisible(True)
        self.startRecordingButton.setVisible(False)

        self.data_saver.start_new(on_start_args=(suffix, data_saving_configuration))
        reader.add_subscriber(self.data_saver.queue)

        message = "Started recording in: " + self.data_saver.get_filename()

        Toaster.showMessage(self, message)

    def start_recording_flow(self, suffix, reader):
        self.stopRecordingButtonFlow.setVisible(True)
        self.startRecordingButtonFlow.setVisible(False)

        self.flow_data_saver.start_new(on_start_args=(suffix, flow_data_saving_configuration))
        reader.add_subscriber(self.flow_data_saver.queue)

        message = "Started recording flow in: " + self.flow_data_saver.get_filename()

        Toaster.showMessage(self, message)

    def stop_recording(self, reader):
        self.stopRecordingButton.setVisible(False)
        self.startRecordingButton.setVisible(True)

        self.data_saver.set_stopped()
        reader.remove_subscriber(self.data_saver.queue)
        Toaster.showMessage(self, "Stopped recording")

    def stop_recording_flow(self, reader):
        self.stopRecordingButtonFlow.setVisible(False)
        self.startRecordingButtonFlow.setVisible(True)

        self.flow_data_saver.set_stopped()
        reader.remove_subscriber(self.flow_data_saver.queue)
        Toaster.showMessage(self, "Stopped recording flow")

    # This should be in EITProcessor
    @staticmethod
    def initialize_eit_obj(eit_pickle, conf):
        conf = load_conf(conf)
        setup = conf["setup"]

        eit_obj = unpickle_eit(eit_pickle)
        eit_obj.setup(p=setup["p"], lamb=setup["lamb"], method=setup["method"])

        return eit_obj

    def add_plot(self):
        self.placeholderWidget.setVisible(False)

        self.canvas = FigureCanvas(matplotlib.figure.Figure())
        self.plot_axes = self.canvas.figure.subplots()
        toolbar = NavigationToolbar(self.canvas, self.canvas, coordinates=True)

        self.verticalLayout.addWidget(self.canvas)
        self.verticalLayout.addWidget(toolbar)

    def update_plot(self, triangulation, eit_image, electrode_points):
        if self.first_plot:
            self.add_plot()
            # self.first_plot is set to False below

        self.plot_axes.clear()

        plot_image = self.plot_axes.tripcolor(triangulation, eit_image)
        plot_image.axes.set_aspect('equal')

        for i, e in enumerate(electrode_points):
            self.plot_axes.text(e[0], e[1], str(i + 1), size=12)

        if self.first_plot:
            divider = make_axes_locatable(self.plot_axes)
            self.color_axis = divider.append_axes("right", size="5%", pad=0.1)
            self.color_axis.yaxis.tick_right()
            self.plot_axes.figure.colorbar(plot_image, cax=self.color_axis)
            self.first_plot = False

        else:
            self.color_axis.clear()
            self.plot_axes.figure.colorbar(plot_image, cax=self.color_axis)

        self.plot_axes.figure.canvas.draw()

    def populate_devices(self):
        self.comboBox.addItems(pyvisa.ResourceManager().list_resources())
        self.comboBox.setCurrentIndex(-1)
        self.comboBoxFlow.addItems(pyvisa.ResourceManager().list_resources())
        self.comboBoxFlow.setCurrentIndex(-1)

    def change_device(self, text):
        if self.data_writer.get_state() != self.data_writer.started:
            self.reader.add_subscriber(self.data_writer.queue)
            self.data_writer.start_new()
            self.data_writer.new_data.connect(lambda data: self.textEdit.append(data))

        if self.eit_processor.get_state() != self.eit_processor.started:
            self.reader.add_subscriber(self.eit_processor.queue)
            self.eit_processor.start_new(on_start_args=(self.eit_obj, self.conf, self.initial_background))
            self.eit_processor.new_data.connect(lambda data: self.update_plot(data[0], data[1], data[2]))

        if self.reader.get_state() != self.reader.stopped:
            self.reader.set_stopped()

        self.reader.start_new(on_start_args=(text, spectra_configuration))

    def change_flow_device(self, text):
        if self.flow_reader.get_state() != self.flow_reader.stopped:
            self.flow_reader.set_stopped()

        self.flow_reader.start_new(on_start_args=(text, flow_configuration))


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    dw = QtWidgets.QDesktopWidget()

    main_window.resize(dw.availableGeometry(dw).size() * 0.7)

    main_window.show()
    app.exec()





