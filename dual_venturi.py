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

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/layout_dual_venturi.ui")

flow_configuration = {
    "baud": 115200,
    "frame_start_char": None,
    "read_timeout": 10000,
    "read_termination_char": "\n",
    "encoding": "utf-8"
}
data_saving_configuration = {
    "directory": "data/",
    "format": "%Y-%m-%dT%H_%M",
    "default_suffix": "data",
    "columns": ["Time", "Flow1", "Flow2"],
    "timestamp_format": "raw",
    "delimiter": ",",
    "extension": ".csv",
    "buffer_size": 1000,
    "buffer_timeout": .5
}
flow_plot_config = {
    "buffer": 60000,
    "slope": 1,
    "offset": 0,
    "min_range": 2
}

bidirectional_venturi_config = {
    "columns": ["Flow1", "Flow2"],
    "Flow1_multiplier": 0.09114830539,  # V1 calibration
    "Flow2_multiplier": -0.08960919406,  # V2 calibration
    "Flow1_offset": 0.03618421041453358,
    "Flow2_offset": 0.012253753906233688,
    "flow_threshold": 0.01,
    "sampling_freq": 1000,
    "cutoff_freq": 50,
    "order": 5,
    "buffer": "10s",
    "resample": "1ms"
}


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.first_flow_plots = [True, True, True]
        self.setupUi(self)
        self.flow_canvases = [None, None, None]
        self.flow_plot_axes = [None, None, None]
        self.vertical_layouts = [self.verticalLayoutFlow1, self.verticalLayoutFlow2, self.verticalLayoutVolume]
        self.placeholder_widgets = [self.placeholderWidgetFlow1, self.placeholderWidgetFlow2, self.placeholderWidgetVolume]
        self.flow_combo_boxes = [self.comboBoxFlow1, self.comboBoxFlow2]
        self.flow_readers = [Reader(tag="Flow1"), Reader(tag="Flow2")]  # Tags used for saving AND to refer to calibration in venturi config dict
        self.flow_emitters = [QueueEmitter(buffer_size=10000, work_timeout=.5), QueueEmitter(buffer_size=10000, work_timeout=.5)]
        self.volume_calc = BidirectionalVenturiFlowCalculator(work_timeout=.5, buffer_size=1000)
        self.data_saver = DataSaver()

        self.populate_devices(0)
        self.populate_devices(1)

        self.startRecordingButton.clicked.connect(
            lambda: self.start_recording(self.dataFileSuffixTextEdit.toPlainText()))
        self.stopRecordingButton.clicked.connect(self.stop_recording)

        self.flow_combo_boxes[0].currentTextChanged.connect(lambda text: self.change_flow_device(text, 0))
        self.flow_combo_boxes[1].currentTextChanged.connect(lambda text: self.change_flow_device(text, 1))

        self.flow_readers[0].set_subscribers([self.flow_emitters[0].get_work_queue(), self.volume_calc.get_work_queue(), self.data_saver.get_work_queue()])
        self.flow_readers[1].set_subscribers([self.flow_emitters[1].get_work_queue(), self.volume_calc.get_work_queue(), self.data_saver.get_work_queue()])
        self.volume_calc.start_new(on_start_args=(bidirectional_venturi_config,))

        self.flow_emitters[0].new_data.connect(lambda items: self.update_flow_plot(items, 0))
        self.flow_emitters[1].new_data.connect(lambda items: self.update_flow_plot(items, 1))
        self.volume_calc.new_data.connect(lambda items: (self.update_flow_plot(items, 2), self.volumeLabel.setText("{0:.2}".format(items[-1]["data"]))))
        self.zeroVolumeButton.clicked.connect(self.volume_calc.set_zero)

        self.start_time = time()

    def start_recording(self, suffix):
        self.stopRecordingButton.setVisible(True)
        self.startRecordingButton.setVisible(False)

        self.data_saver.start_new(on_start_args=(suffix, data_saving_configuration))

        self.comboBoxFlow1.setEnabled(False)
        self.comboBoxFlow2.setEnabled(False)
        self.dataFileSuffixTextEdit.setEnabled(False)

        message = "Started recording"# in: " + self.data_saver.get_filename()

        Toaster.showMessage(self, message)

    def stop_recording(self):
        self.stopRecordingButton.setVisible(False)
        self.startRecordingButton.setVisible(True)

        self.comboBoxFlow1.setEnabled(True)
        self.comboBoxFlow2.setEnabled(True)
        self.dataFileSuffixTextEdit.setEnabled(True)

        self.data_saver.set_stop_at_queue_end()
        Toaster.showMessage(self, "Stopped recording")

    def add_flow_plot(self, i):
        self.placeholder_widgets[i].setVisible(False)

        self.flow_canvases[i] = FigureCanvas(matplotlib.figure.Figure())
        self.flow_plot_axes[i] = self.flow_canvases[i].figure.subplots()
        toolbar = NavigationToolbar(self.flow_canvases[i], self.flow_canvases[i], coordinates=True)

        self.vertical_layouts[i].addWidget(self.flow_canvases[i])
        self.vertical_layouts[i].addWidget(toolbar)

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

    def update_flow_plot(self, items, i):
        new_data, new_times = self.parse_flow_data(items)

        if self.first_flow_plots[i]:
            self.add_flow_plot(i)
            self.first_flow_plots[i] = False
            data = [0]
            times = [0]
        else:
            data = self.flow_plot_axes[i].lines[0].get_ydata()
            times = self.flow_plot_axes[i].lines[0].get_xdata()

        nd = [element for i, element in enumerate(new_data) if new_times[i] > times[-1]]
        nt = [element for i, element in enumerate(new_times) if new_times[i] > times[-1]]
        new_data = nd
        new_times = nt

        self.flow_plot_axes[i].clear()

        data = np.append(data, new_data)
        data = data[-1 * flow_plot_config["buffer"]:]

        times = np.append(times, new_times)
        times = times[-1 * flow_plot_config["buffer"]:]

        self.flow_plot_axes[i].plot(times, data)
        ylim = self.flow_plot_axes[i].get_ylim()
        range = ylim[1] - ylim[0]
        range_min = flow_plot_config["min_range"]
        if range < range_min:
            self.flow_plot_axes[i].set_ylim((ylim[0]-((range_min-range)/2)), ylim[1]+((range_min-range)/2))

        self.flow_plot_axes[i].figure.canvas.draw()

    def populate_devices(self, i):
        self.flow_combo_boxes[i].addItems(self.flow_readers[i].list_devices())
        self.flow_combo_boxes[i].setCurrentIndex(-1)

    def change_flow_device(self, text, i):
        self.flow_readers[i].start_new(on_start_args=(text, flow_configuration))
        self.flow_emitters[i].start_new()


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    dw = QtWidgets.QDesktopWidget()

    main_window.resize(dw.availableGeometry(dw).size() * 0.7)

    main_window.show()
    app.exec()
