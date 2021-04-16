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
    "baud": 500000,
    "frame_start_char": None,
    "read_timeout": 10000,
    "read_termination_char": "\n",
    "encoding": "utf-8"
}
data_saving_configuration = {
    "directory": "data/",
    "format": "%Y-%m-%dT%H_%M_flow",
    "default_suffix": "data",
    "columns": ["Time", "Tag", "Flow"],
    "timestamp_format": "raw",
    "delimiter": ",",
    "extension": ".csv",
    "buffer_size": 1000,
    "buffer_timeout": .5
}

flow_plot_config = {
    "buffer": 10000,
    "slope": 1,
    "offset": 0,
    "min_range": 2
}

bidirectional_venturi_config = {
    "columns": ["Flow1", "Flow2"],
    "sensor_orientations": [-1, 1],  # Orientation of pressure sensor. 1 for positive reading from air flow through venturi tube
    # "Flow1_multiplier": 0.09885543577,
    "Flow1_multiplier": 0,
    "Flow2_multiplier": -1,
    # "Flow1_offset": 0.16,
    "Flow1_offset": 0.16,
    "Flow2_offset": 0,
    "flow_threshold": 0.02,
    "sampling_freq": 1000,
    "cutoff_freq": 50,
    "order": 5,
    "buffer": "10s",
    "resample": "1ms"
}


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.first_flow_plots = [True, True, True, True]
        self.setupUi(self)
        self.flow_canvases = [None, None, None, None]
        self.flow_plot_axes = [None, None, None, None]
        self.vertical_layouts = [self.verticalLayoutFlow, self.verticalLayoutVolume, self.verticalLayoutUniFlow1, self.verticalLayoutUniFlow2]
        self.placeholder_widgets = [self.placeholderWidgetFlow1, self.placeholderWidgetVolume, self.placeholderWidgetUniFlow1, self.placeholderWidgetUniFlow2]
        self.flow_combo_box = self.comboBoxFlow1
        self.flow_reader = Reader(tag="Flow")  # Tags used for saving AND to refer to calibration in venturi config dict
        self.volume_calc = BidirectionalVenturiFlowCalculator(work_timeout=.5, buffer_size=1000)
        self.data_saver = DataSaver()

        self.populate_devices()

        self.startRecordingButton.clicked.connect(
            lambda: self.start_recording(self.dataFileSuffixTextEdit.toPlainText()))
        self.stopRecordingButton.clicked.connect(self.stop_recording)

        self.comboBoxFlow1.currentTextChanged.connect(lambda text: self.change_flow_device(text))

        self.flow_reader.set_subscribers([self.volume_calc.get_work_queue(), self.data_saver.get_work_queue()])
        self.volume_calc.start_new(on_start_args=(bidirectional_venturi_config,))

        # self.volume_calc.new_data.connect(lambda items: (self.update_flow_plot(items, 0), self.update_flow_plot(items, 1),
        #                                                  self.flowLabel.setText("{0:.2}".format(np.average([item["data"][0] for item in items]))), self.volumeLabel.setText("{0:.2}".format(items[-1]["data"][1])),
        #                                                  self.update_flow_plot(items, 2), self.update_flow_plot(items, 3),
        #                                                  self.uniFlowLabel1.setText("{0:.2}".format(np.average([item["data"][2] for item in items]))),self.uniFlowLabel1.setText("{0:.2}".format(np.average([item["data"][3] for item in items])))
        #                                                  ))
        self.volume_calc.new_data.connect(lambda items: (self.update_flow_plot(items, 0), self.update_flow_plot(items, 1),
                                                         self.flowLabel.setText("{0:.2}".format(np.average([item["data"][0] for item in items]))), self.volumeLabel.setText("{0:.2}".format(items[-1]["data"][1]))))
        self.zeroVolumeButton.clicked.connect(self.volume_calc.set_zero)

        self.start_time = time()

    def start_recording(self, suffix):
        self.stopRecordingButton.setVisible(True)
        self.startRecordingButton.setVisible(False)

        self.data_saver.start_new(on_start_args=(suffix, data_saving_configuration))

        self.comboBoxFlow1.setEnabled(False)
        self.dataFileSuffixTextEdit.setEnabled(False)

        message = "Started recording"# in: " + self.data_saver.get_filename()

        Toaster.showMessage(self, message)

    def stop_recording(self):
        self.stopRecordingButton.setVisible(False)
        self.startRecordingButton.setVisible(True)

        self.comboBoxFlow1.setEnabled(True)
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

    def parse_flow_data(self, items, i):
        data_list = []
        time_list = []
        for item in items:
            try:
                data = float(item["data"][i])
                time = float(item["timestamp"]) - float(self.start_time)
            except ValueError:
                continue
            data_list.append(data)
            time_list.append(time)

        data_list = np.multiply(data_list, flow_plot_config["slope"])
        data_list = np.add(data_list, flow_plot_config["offset"])
        return data_list, time_list

    def update_flow_plot(self, items, i):
        new_data, new_times = self.parse_flow_data(items, i)

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

    def populate_devices(self):
        self.flow_combo_box.addItems(self.flow_reader.list_devices())
        self.flow_combo_box.setCurrentIndex(-1)

    def change_flow_device(self, text):
        self.flow_reader.start_new(on_start_args=(text, flow_configuration))


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    dw = QtWidgets.QDesktopWidget()

    # main_window.resize(dw.availableGeometry(dw).size() * 0.7)

    main_window.show()
    app.exec()
