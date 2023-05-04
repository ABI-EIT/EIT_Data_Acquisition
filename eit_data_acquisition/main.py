import sys
from PyQt5 import QtWidgets, uic
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar
)
import matplotlib
import matplotlib.pyplot
import time
from eit_data_acquisition.background_process_workers import *
from eit_data_acquisition.Toaster import Toaster
from PyQt5.QtGui import QIcon
from pyeit.visual.plot import create_plot
from eit_data_acquisition.eit import setup_eit
import multiprocessing

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/layout.ui")

default_mesh = "configuration/circle_phantom_mesh_no_inclusion.stl"
default_conf = "configuration/conf.json"
default_eit_setup = "configuration/eit_setup.json"
device_configuration = {
    "baud": 115200,
    "frame_start_char": "m",
    "read_timeout": 10000,
    "read_termination_char": "\n",
    "encoding": "latin-1"
}
data_saving_configuration = {
    "directory": "data/",
    "format": "%Y-%m-%dT%H_%M_eit",
    "default_suffix": "data",
    "columns": ["Time", "EIT"],
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

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.first_plot = True
        self.setupUi(self)
        self.canvas = None
        self.plot_axes = None
        self.populate_devices()
        self.eit_reader = Reader(tag="EIT")
        self.eit_processor = EITProcessor()
        self.data_saver = DataSaver()
        self.conf = default_conf
        self.eit_setup = default_eit_setup
        self.initial_background = None
        self.color_axis = None
        self.eit_scale = (np.inf, np.NINF)  # ymin, ymax

        self.comboBox.currentTextChanged.connect(self.change_eit_device)
        self.startRecordingButton.clicked.connect(
            lambda: self.start_recording(self.dataFileSuffixTextEdit.text()))
        self.stopRecordingButton.clicked.connect(self.stop_recording)

        self.eit_obj = self.initialize_eit_obj(default_mesh, self.eit_setup)
        self.eit_reader.new_data.connect(
            lambda result: (self.textEdit.append(result["data"])))
        self.eit_reader.set_subscribers([self.eit_processor.get_work_queue(), self.data_saver.get_work_queue()])
        self.eit_reader.on_connect_failed = self.eit_connect_failed

        self.set_background_button.clicked.connect(self.set_background)
        self.clear_background_button.clicked.connect(lambda: self.eit_processor.set_background(None))

        self.start_time = time()
        self.update_ui_state()

    def reset_eit_scale(self):
        self.eit_scale = (np.inf, np.NINF)

    def eit_connect_failed(self):
        print("EIT reader connect failed")
        self.comboBox.setCurrentIndex(0)
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
        if self.eit_reader.get_state() == Reader.started:
            self.startRecordingButton.setEnabled(True)
        else:
            self.startRecordingButton.setEnabled(False)

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

        self.data_saver.start_new(work_kwargs={"suffix": suffix, "configuration": data_saving_configuration})

        self.comboBox.setEnabled(False)
        self.dataFileSuffixTextEdit.setEnabled(False)

        message = "Started recording"  # +" in: " + self.data_saver.get_filename()
        Toaster.showMessage(self, message)

    def stop_recording(self):
        self.stopRecordingButton.setVisible(False)
        self.startRecordingButton.setVisible(True)

        self.comboBox.setEnabled(True)
        self.dataFileSuffixTextEdit.setEnabled(True)

        self.data_saver.set_stop_at_queue_end()

        Toaster.showMessage(self, "Stopped recording")

    # This should be in EITProcessor
    @staticmethod
    def initialize_eit_obj(eit_mesh, conf):
        eit_obj = setup_eit(eit_mesh, conf)
        return eit_obj

    def add_eit_plot(self):
        self.placeholderWidget.setVisible(False)

        self.canvas = FigureCanvas(matplotlib.figure.Figure())
        self.plot_axes = self.canvas.figure.subplots()
        toolbar = NavigationToolbar(self.canvas, self.canvas, coordinates=True)

        self.verticalLayout_5.addWidget(self.canvas)
        self.verticalLayout_5.addWidget(toolbar)


    def update_eit_plot(self, eit_image, pyeit_obj):
        if self.first_plot:
            self.add_eit_plot()
            self.first_plot = False

        # Removing all axes since create_plot creates a colorbar, which creates its own axes
        for ax in self.canvas.figure.axes:
            ax.remove()
        ax = self.canvas.figure.subplots()

        vmin = min(eit_image)
        vmax = max(eit_image)

        img, text, _ = create_plot(ax, eit_image,  pyeit_obj.mesh, vmax=vmax, vmin=vmin)
        self.canvas.draw_idle()
        return img, text

    def populate_devices(self):
        self.comboBox.addItems(["None"])
        self.comboBox.addItems(Reader.list_devices())
        self.comboBox.setCurrentIndex(0)

    def change_eit_device(self, text):
        if text == "":
            return
        if text == "None":
            if self.eit_reader.get_state() == Reader.started:
                self.eit_processor.set_stopped()
                self.eit_reader.set_stopped()
                self.update_ui_state()
                return
        self.eit_processor.start_new(work_kwargs={"eit_obj": self.eit_obj, "configuration": self.conf, "initial_bg": self.initial_background})
        self.eit_processor.new_data.connect(lambda data: self.update_eit_plot(data[1], self.eit_obj))
        self.set_background_button.setEnabled(True)
        self.clear_background_button.setEnabled(True)

        self.eit_reader.start_new(work_kwargs={"device_name": text, "configuration": device_configuration})

        self.update_ui_state()


if __name__ == '__main__':
    # Pyinstaller fix
    multiprocessing.freeze_support()

    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.setWindowTitle("ABI EIT")
    main_window.setWindowIcon(QIcon("layout/lung_icon.PNG"))
    dw = QtWidgets.QDesktopWidget()

    main_window.resize(dw.availableGeometry(dw).size() * 0.7)

    main_window.show()
    app.exec()
