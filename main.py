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

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/layout.ui")

# default_pickle = "configuration/mesha06_bumpychestslice_pickle_dist1_step1"
default_pickle = "configuration/mesha06_bumpychestslice_pickle"
default_conf = "configuration/conf.json"
spectra_configuration = {
    "baud": 115200,
    "frame_start_char": "m",
    "read_timeout": 10000,
    "read_termination_char": "\n",
    "encoding": "latin-1"
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
        self.data_writer = DataWriter()
        self.plotter = PlotterConsumer()
        self.conf = default_conf
        self.initial_background = None
        self.color_axis = None

        self.comboBox.currentTextChanged.connect(self.change_device)
        self.startRecordingButton.clicked.connect(lambda: self.start_recording(self.dataFilePrefixTextEdit.toPlainText(), ""))
        self.stopRecordingButton.clicked.connect(self.stop_recording)

        self.eit_obj = self.initialize_eit_obj(default_pickle, self.conf)

        self.set_background_button.clicked.connect(lambda: self.plotter.set_background(self.plotter.get_current_frame()))
        self.clear_background_button.clicked.connect(lambda: self.plotter.set_background(None))

    def start_recording(self, prefix, reader):
        print("start recording with prefix: %s" % prefix)
        self.stopRecordingButton.setVisible(True)
        self.startRecordingButton.setVisible(False)
        # Start consumer to save frames
        # Create file to save data in. Take text from data file prefix
        # swap start recording button for stop recording button
        # Dialog?
        pass

    def stop_recording(self):
        self.stopRecordingButton.setVisible(False)
        self.startRecordingButton.setVisible(True)

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
        start_time = time.time()

        if self.first_plot:
            self.add_plot()

        self.plot_axes.clear()

        plot_image = self.plot_axes.tripcolor(triangulation, eit_image)
        plot_image.axes.set_aspect('equal')
        tripcolor_done = time.time()

        for i, e in enumerate(electrode_points):
            self.plot_axes.text(e[0], e[1], str(i + 1), size=12)

        electrode_labels_done = time.time()

        if self.first_plot:
            divider = make_axes_locatable(self.plot_axes)
            self.color_axis = divider.append_axes("right", size="5%", pad=0.1)
            self.color_axis.yaxis.tick_right()
            self.plot_axes.figure.colorbar(plot_image, cax=self.color_axis)

        else:
            self.color_axis.clear()
            self.plot_axes.figure.colorbar(plot_image, cax=self.color_axis)

        colorbar_done = time.time()

        self.plot_axes.figure.canvas.draw()
        self.first_plot = False

        canvas_draw_done = time.time()

        total_time = canvas_draw_done - start_time
        tripcolor_time = tripcolor_done - start_time
        electrode_labels_time = electrode_labels_done -tripcolor_done
        colorbar_time = colorbar_done - electrode_labels_done
        canvas_draw_time = canvas_draw_done - colorbar_done

        # print("Plotting time total: %.2fs, tripcolor: %.2fs, elec labels: %.2fs, colorbar: %.2fs, canvas draw: %.2fs" % (total_time, tripcolor_time, electrode_labels_time, colorbar_time, canvas_draw_time))

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

        self.reader.start_new(on_start_args=(text, spectra_configuration), work_args=(), on_stopped_args=())


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    dw = QtWidgets.QDesktopWidget()

    main_window.resize(dw.availableGeometry(dw).size() * 0.7)

    main_window.show()
    app.exec()





