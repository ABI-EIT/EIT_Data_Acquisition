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
    "columns": ["Time", "Tag", "Flow", "EIT"],
    "timestamp_format": "raw",
    "delimiter": ",",
    "extension": ".csv",
    "buffer_size": 1000,
    "buffer_timeout": .5
}
spectra_data_format = {
    "prefix": "magnitudes:        ",
    "separator": ",       "
}
flow_plot_buffer = 3000
test_names = ["Test 1", "Test 2", "Test 3", "Test 4"]


class TestButton(QtWidgets.QPushButton):
    def __init__(self, *args, **kwargs):
        self.name = kwargs.pop("name")
        self.queue = kwargs.pop("queue")
        super().__init__(*args, **kwargs)
        self.setText("Start " + self.name)
        self.setCheckable(True)
        self.clicked.connect(self.react_to_click)
        self.started_before = False

    def react_to_click(self):
        if self.isChecked():
            if self.started_before:
                message_box = QtWidgets.QMessageBox(text=("Are you sure you want to start {0} again?".format(self.name)))
                message_box.setWindowTitle("Warning")
                message_box.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
                message_box.buttonClicked.connect(lambda button: (self.start() if button.text() == "OK" else self.setChecked(False)))
                message_box.exec()
            else:
                self.started_before = True
                self.start()
        else:
            put_in_queue(self.queue, {"tag": "Tag", "data": "Stop " + self.name, "timestamp": time()})
            Toaster.showMessage(self, "%s stop time recorded" % self.name)
            self.setText("Start " + self.name)

    def start(self):
        put_in_queue(self.queue, {"tag": "Tag", "data": "Start " + self.name, "timestamp": time()})
        Toaster.showMessage(self, "%s start time recorded" % self.name)
        self.setText("Stop " + self.name)


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.first_plot = True
        self.first_flow_plot = True
        self.setupUi(self)
        self.canvas = None
        self.plot_axes = None
        self.flow_canvas = None
        self.flow_plot_axes = None
        self.populate_devices()
        self.eit_reader = Reader(tag="EIT")
        self.flow_reader = Reader(tag="Flow")
        self.eit_data_writer = QueueEmitter()
        self.flow_emitter = QueueEmitter(buffer_size=200, buffer_timeout=3)
        self.eit_processor = EITProcessor()
        self.data_saver = DataSaver()
        self.conf = default_conf
        self.initial_background = None
        self.color_axis = None
        self.test_buttons = []

        self.comboBox.currentTextChanged.connect(self.change_eit_device)
        self.startRecordingButton.clicked.connect(
            lambda: self.start_recording(self.dataFileSuffixTextEdit.toPlainText()))
        self.stopRecordingButton.clicked.connect(self.stop_recording)

        self.comboBoxFlow.currentTextChanged.connect(self.change_flow_device)

        self.eit_obj = self.initialize_eit_obj(default_pickle, self.conf)

        self.set_background_button.clicked.connect(self.set_background)
        self.set_background_button.setEnabled(False)
        self.clear_background_button.clicked.connect(lambda: self.eit_processor.set_background(None))
        self.clear_background_button.setEnabled(False)

        self.populate_test_buttons()

    def populate_test_buttons(self):
        self.test_buttons = [TestButton(name=name, queue=self.data_saver.queue, enabled=False) for name in test_names]
        [self.testButtonsLayout.addWidget(button) for button in self.test_buttons]

    def set_background(self):
        current_frame = self.eit_processor.get_current_frame()
        if current_frame is not None:
            self.eit_processor.set_background(current_frame)
            background_file = DataSaver.create_unique_save_file("background", data_saving_configuration)
            background_file.write(spectra_data_format["prefix"] + "".join(
                ("{}" + spectra_data_format["separator"]).format(item) for item in current_frame))
            background_file.close()
            Toaster.showMessage(self, "Background frame saved in: " + background_file.name)

    def start_recording(self, suffix):
        self.stopRecordingButton.setVisible(True)
        self.startRecordingButton.setVisible(False)

        self.data_saver.start_new(on_start_args=(suffix, data_saving_configuration))

        self.flow_reader.add_subscriber(self.data_saver.queue)
        self.eit_reader.add_subscriber(self.data_saver.queue)

        self.comboBox.setEnabled(False)
        self.comboBoxFlow.setEnabled(False)
        self.dataFileSuffixTextEdit.setEnabled(False)
        [button.setEnabled(True) for button in self.test_buttons]

        message = "Started recording in: " + self.data_saver.get_filename()

        Toaster.showMessage(self, message)

    def stop_recording(self):
        self.stopRecordingButton.setVisible(False)
        self.startRecordingButton.setVisible(True)

        self.comboBox.setEnabled(True)
        self.comboBoxFlow.setEnabled(True)
        self.dataFileSuffixTextEdit.setEnabled(True)
        [button.setEnabled(False) for button in self.test_buttons]
        [button.setChecked(False) for button in self.test_buttons]

        self.data_saver.stop_at_queue_end()
        self.eit_reader.remove_subscriber(self.data_saver.queue)
        self.flow_reader.remove_subscriber(self.data_saver.queue)
        Toaster.showMessage(self, "Stopped recording")

    # This should be in EITProcessor
    @staticmethod
    def initialize_eit_obj(eit_pickle, conf):
        conf = load_conf(conf)
        setup = conf["setup"]

        eit_obj = unpickle_eit(eit_pickle)
        eit_obj.setup(p=setup["p"], lamb=setup["lamb"], method=setup["method"])

        return eit_obj

    def add_eit_plot(self):
        self.placeholderWidget.setVisible(False)

        self.canvas = FigureCanvas(matplotlib.figure.Figure())
        self.plot_axes = self.canvas.figure.subplots()
        toolbar = NavigationToolbar(self.canvas, self.canvas, coordinates=True)

        self.verticalLayoutEIT.addWidget(self.canvas)
        self.verticalLayoutEIT.addWidget(toolbar)

    def add_flow_plot(self):
        self.placeholderWidgetFlow.setVisible(False)

        self.flow_canvas = FigureCanvas(matplotlib.figure.Figure())
        self.flow_plot_axes = self.flow_canvas.figure.subplots()
        toolbar = NavigationToolbar(self.flow_canvas, self.flow_canvas, coordinates=True)

        self.verticalLayout.addWidget(self.flow_canvas)
        self.verticalLayout.addWidget(toolbar)

    def update_eit_plot(self, triangulation, eit_image, electrode_points):
        if self.first_plot:
            self.add_eit_plot()
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

    def update_flow_plot(self, items):
        if self.first_flow_plot:
            self.add_flow_plot()
            self.first_flow_plot = False
            data = []
        else:
            data = self.flow_plot_axes.lines[0].get_ydata()

        # print(items)
        new_data = [float(item["data"]) for item in items]
        data = np.append(data, new_data)
        data = data[-1 * flow_plot_buffer:]

        # print(data)
        self.flow_plot_axes.clear()
        self.flow_plot_axes.plot(data)
        #
        # # plot points. maybe blit?
        #
        self.flow_plot_axes.figure.canvas.draw()

    def populate_devices(self):
        self.comboBox.addItems(pyvisa.ResourceManager().list_resources())
        self.comboBox.setCurrentIndex(-1)
        self.comboBoxFlow.addItems(pyvisa.ResourceManager().list_resources())
        self.comboBoxFlow.setCurrentIndex(-1)

    def change_eit_device(self, text):
        if self.eit_data_writer.get_state() != self.eit_data_writer.started:
            self.eit_reader.add_subscriber(self.eit_data_writer.queue)
            self.eit_data_writer.start_new()
            self.eit_data_writer.new_data.connect(
                lambda item_list: [self.textEdit.append(item["data"]) for item in item_list])

        if self.eit_processor.get_state() != self.eit_processor.started:
            self.eit_reader.add_subscriber(self.eit_processor.queue)
            self.eit_processor.start_new(on_start_args=(self.eit_obj, self.conf, self.initial_background))
            self.eit_processor.new_data.connect(lambda data: self.update_eit_plot(data[0], data[1], data[2]))

        if self.eit_reader.get_state() != self.eit_reader.stopped:
            self.eit_reader.set_stopped()

        self.set_background_button.setEnabled(True)
        self.clear_background_button.setEnabled(True)

        self.eit_reader.start_new(on_start_args=(text, spectra_configuration))

    def change_flow_device(self, text):
        if self.flow_emitter.get_state() != self.flow_emitter.started:
            self.flow_reader.add_subscriber(self.flow_emitter.queue)
            self.flow_emitter.start_new()
            self.flow_emitter.new_data.connect(lambda items: self.update_flow_plot(items))

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
