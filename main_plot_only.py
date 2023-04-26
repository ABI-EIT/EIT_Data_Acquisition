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
from background_process_workers import *
from Toaster import Toaster
from PyQt5.QtGui import QIcon
from pyeit.visual.plot import create_plot
from eit import setup_eit

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/layout_plot_only.ui")

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
        self.conf = default_conf
        self.eit_setup = default_eit_setup
        self.initial_background = None
        self.color_axis = None
        self.eit_scale = (np.inf, np.NINF)  # ymin, ymax

        self.comboBox.currentTextChanged.connect(self.change_eit_device)

        self.eit_obj = self.initialize_eit_obj(default_mesh, self.eit_setup)
        self.eit_reader.new_data.connect(
            lambda result: (self.textEdit.append(result["data"])))
        self.eit_reader.set_subscribers([self.eit_processor.get_work_queue()])
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

        if self.eit_reader.get_state() == self.eit_reader.started:
            self.set_background_button.setEnabled(True)
            self.clear_background_button.setEnabled(True)
        else:
            self.set_background_button.setEnabled(False)
            self.clear_background_button.setEnabled(False)

    def set_background(self):
        current_frame = self.eit_processor.get_current_frame()
        if current_frame is not None:
            self.eit_processor.set_background(current_frame)

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
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.setWindowTitle("ABI EIT")
    main_window.setWindowIcon(QIcon("layout/lung_icon.png"))
    dw = QtWidgets.QDesktopWidget()

    main_window.resize(dw.availableGeometry(dw).size() * 0.7)

    main_window.show()
    app.exec()
