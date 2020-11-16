import sys
from PyQt5 import QtWidgets, uic
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar
)
import numpy as np
from pyeit.app.eit import *
import pyvisa

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/test_layout.ui")

pickle = "C:/Users/acre018/github/pyEIT/scripts/auckland/results/mesha06_bumpychestslice_pickle"
data = "C:/Users/acre018/github/pyEIT/scripts/auckland/data/201029_17HSWMGkumara2.txt"
conf = "C:/Users/acre018/github/pyEIT/scripts/auckland/configuration/conf.json"
background = None

 
class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setupUi(self)
        self.canvas = None
        self.toolbar = None
        self.fig = None
        self.populate_devices()

    def add_plot(self, fig):
        self.fig = fig
        self.canvas = FigureCanvas(fig)
        self.toolbar = NavigationToolbar(self.canvas, self.widget, coordinates=True)

        self.verticalLayout.addWidget(self.canvas)
        self.verticalLayout.addWidget(self.toolbar)
        self.canvas.draw()

        self.device = None

    def change_plot(self):
        self.fig.clear()
        ax = fig.subplots()
        ax.plot(np.random.rand(5))
        self.canvas.draw()

    def populate_devices(self):
        self.rm = pyvisa.ResourceManager()
        self.comboBox.addItems(self.rm.list_resources())

    def change_device(self, text):
        try:
            self.device = self.rm.open_resource(text)
        except pyvisa.errors.VisaIOError as e:
            print(e)

    def read(self):
        if self.device is not None:
            try:
                self.textEdit.append(self.device.read())
            except pyvisa.errors.VisaIOError as e:
                print(e)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    dw = QtWidgets.QDesktopWidget()

    main_window.resize(dw.availableGeometry(dw).size() * 0.7)

    eit_obj = unpickle_eit(pickle)
    data = load_oeit_data(data)
    conf = load_conf(conf)
    if background is not None:
        background = load_oeit_data(background)[0]
    else:
        background = None

    eit_image = process_frame(eit_obj, data[0], conf, background)
    fig, imgs = create_plot([eit_image], eit_obj)

    main_window.add_plot(fig)
    main_window.pushButton.clicked.connect(main_window.read)

    main_window.comboBox.currentTextChanged.connect(main_window.change_device)

    main_window.show()
    app.exec()






