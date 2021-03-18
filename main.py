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
from background_process_workers import *
from Toaster import Toaster

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/eit_with_dual_flow.ui")

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
    "baud": 115200,
    "frame_start_char": None,
    "read_timeout": 10000,
    "read_termination_char": "\n",
    "encoding": "utf-8"
}
data_saving_configuration = {
    "directory": "data/",
    "format": "%Y-%m-%dT%H_%M_eit",
    "default_suffix": "data",
    "columns": ["Time", "Tag", "Flow1", "Flow2", "EIT"],
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
flow_plot_config = {
    "buffer": 60000,
    "slope": 1,
    "offset": 0,
    "min_range": 2
}

bidirectional_venturi_config = {
    "columns": ["Flow1", "Flow2"],
    "Flow1_multiplier": 0.09302907076,  # V1 calibration
    "Flow2_multiplier": -0.09372544465,  # V2 calibration
    "Flow1_offset": 0,
    "Flow2_offset": 0,
    "flow_threshold": 0.02,
    "sampling_freq": 1000,
    "cutoff_freq": 50,
    "order": 5,
    "buffer": "10s",
    "resample": "1ms"
}


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
        self.flow_combo_boxes = [self.comboBoxFlow1, self.comboBoxFlow2]
        self.populate_devices()
        self.eit_reader = Reader(tag="EIT")
        self.flow_readers = [Reader(tag="Flow1"), Reader(tag="Flow2")]  # Tags used for saving AND to refer to calibration in venturi config dict
        self.volume_calc = BidirectionalVenturiFlowCalculator(work_timeout=.5, buffer_size=1000)
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

        self.eit_obj = self.initialize_eit_obj(default_pickle, self.conf)
        self.eit_reader.new_data.connect(
            lambda result: (self.textEdit.append(result["data"]), self.FrameCountCountLabel.setText(str(int(self.FrameCountCountLabel.text())+1))))
        self.eit_reader.set_subscribers([self.eit_processor.get_work_queue(), self.data_saver.get_work_queue()])
        self.eit_reader.on_connect_failed = self.eit_connect_failed

        self.set_background_button.clicked.connect(self.set_background)
        self.clear_background_button.clicked.connect(lambda: self.eit_processor.set_background(None))

        self.flow_combo_boxes[0].currentTextChanged.connect(lambda text: self.change_flow_device(text, 0))
        self.flow_combo_boxes[1].currentTextChanged.connect(lambda text: self.change_flow_device(text, 1))

        self.flow_readers[0].set_subscribers([self.volume_calc.get_work_queue(), self.data_saver.get_work_queue()])
        self.flow_readers[1].set_subscribers([self.volume_calc.get_work_queue(), self.data_saver.get_work_queue()])
        self.flow_readers[0].on_connect_failed = lambda: self.flow_connect_failed(0)
        self.flow_readers[1].on_connect_failed = lambda: self.flow_connect_failed(1)
        self.volume_calc.start_new(on_start_args=(bidirectional_venturi_config,))

        self.volume_calc.new_data.connect(lambda items: (self.update_flow_plot(items), self.volumeLabel.setText("{0:.2}".format(items[-1]["data"]))))
        self.zeroVolumeButton.clicked.connect(self.volume_calc.set_zero)

        self.populate_test_buttons()

        self.start_time = time()
        self.update_ui_state()

    def flow_connect_failed(self, i):
        print("Flow%d reader connect failed" % (i+1))
        self.flow_combo_boxes[i].setCurrentIndex(-1)
        self.update_ui_state()

    def eit_connect_failed(self):
        print("EIT reader connect failed")
        self.comboBox.setCurrentIndex(-1)
        self.update_ui_state()

    def update_ui_state(self):
        self.update_ui_reader_state()

        if self.eit_reader.get_state() == self.eit_reader.started:
            self.set_background_button.setEnabled(True)
            self.clear_background_button.setEnabled(True)
        else:
            self.set_background_button.setEnabled(False)
            self.clear_background_button.setEnabled(False)

    def update_ui_reader_state(self):
        if self.flow_readers[0].get_state() == Reader.started or \
           self.flow_readers[1].get_state() == Reader.started or \
           self.eit_reader.get_state() == Reader.started:
            self.startRecordingButton.setEnabled(True)
        else:
            self.startRecordingButton.setEnabled(False)

    def populate_test_buttons(self):
        self.test_buttons = [TestButton(name=name, queue=self.data_saver.get_work_queue(), enabled=False) for name in test_names]
        for button in self.test_buttons:
            self.testButtonsLayout.addWidget(button)

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

        self.comboBox.setEnabled(False)
        self.comboBoxFlow1.setEnabled(False)
        self.comboBoxFlow2.setEnabled(False)
        self.dataFileSuffixTextEdit.setEnabled(False)
        for button in self.test_buttons:
            button.setEnabled(True)

        message = "Started recording"  # +" in: " + self.data_saver.get_filename()
        Toaster.showMessage(self, message)

    def stop_recording(self):
        self.stopRecordingButton.setVisible(False)
        self.startRecordingButton.setVisible(True)

        self.comboBox.setEnabled(True)
        self.comboBoxFlow1.setEnabled(True)
        self.comboBoxFlow2.setEnabled(True)
        self.dataFileSuffixTextEdit.setEnabled(True)

        for button in self.test_buttons:
            button.setEnabled(False)
            button.setChecked(False)

        self.data_saver.set_stop_at_queue_end()

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
        self.placeholderWidgetVolume.setVisible(False)

        self.flow_canvas = FigureCanvas(matplotlib.figure.Figure())
        self.flow_plot_axes = self.flow_canvas.figure.subplots()
        toolbar = NavigationToolbar(self.flow_canvas, self.flow_canvas, coordinates=True)

        self.verticalLayoutVolume.addWidget(self.flow_canvas)
        self.verticalLayoutVolume.addWidget(toolbar)

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

    def parse_flow_data(self, items):
        data_list = []
        time_list = []
        for item in items:
            try:
                data = float(item["data"])
                time = float(item["timestamp"]) - float(self.start_time)
            except ValueError:
                continue
            data_list.append(data)
            time_list.append(time)

        data_list = np.multiply(data_list, flow_plot_config["slope"])
        data_list = np.add(data_list, flow_plot_config["offset"])
        return data_list, time_list

    def update_flow_plot(self, items):
        new_data, new_times = self.parse_flow_data(items)
        if self.first_flow_plot:
            self.add_flow_plot()
            self.first_flow_plot = False
            data = [0]
            times = [0]
        else:
            data = self.flow_plot_axes.lines[0].get_ydata()
            times = self.flow_plot_axes.lines[0].get_xdata()

        nd = [element for i, element in enumerate(new_data) if new_times[i] > times[-1]]
        nt = [element for i, element in enumerate(new_times) if new_times[i] > times[-1]]
        new_data = nd
        new_times = nt

        self.flow_plot_axes.clear()

        data = np.append(data, new_data)
        data = data[-1 * flow_plot_config["buffer"]:]

        times = np.append(times, new_times)
        times = times[-1 * flow_plot_config["buffer"]:]

        self.flow_plot_axes.plot(times, data)
        ylim = self.flow_plot_axes.get_ylim()
        range = ylim[1] - ylim[0]
        range_min = flow_plot_config["min_range"]
        if range < range_min:
            self.flow_plot_axes.set_ylim((ylim[0]-((range_min-range)/2)), ylim[1]+((range_min-range)/2))

        self.flow_plot_axes.figure.canvas.draw()

    def populate_devices(self):
        self.comboBox.addItems(Reader.list_devices())
        self.comboBox.setCurrentIndex(-1)
        self.comboBoxFlow1.addItems(Reader.list_devices())
        self.comboBoxFlow1.setCurrentIndex(-1)
        self.comboBoxFlow2.addItems(Reader.list_devices())
        self.comboBoxFlow2.setCurrentIndex(-1)

    def change_eit_device(self, text):
        if text == "":
            return
        self.eit_processor.start_new(on_start_args=(self.eit_obj, self.conf, self.initial_background))
        self.eit_processor.new_data.connect(lambda data: self.update_eit_plot(data[0], data[1], data[2]))

        self.set_background_button.setEnabled(True)
        self.clear_background_button.setEnabled(True)

        self.eit_reader.start_new(on_start_args=(text, spectra_configuration))

        self.update_ui_state()

    def change_flow_device(self, text, i):
        if text == "":
            return
        self.flow_readers[i].start_new(on_start_args=(text, flow_configuration))
        self.update_ui_state()


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    dw = QtWidgets.QDesktopWidget()

    main_window.resize(dw.availableGeometry(dw).size() * 0.7)

    main_window.show()
    app.exec()
