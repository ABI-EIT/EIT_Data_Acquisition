import sys
from PyQt5 import QtWidgets, QtCore
import threading
import time

title = "Qt Experiments"

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        self.progress_bar = QtWidgets.QProgressBar()
        self.start_button = QtWidgets.QPushButton()
        self.stop_button = QtWidgets.QPushButton()
        self.v_layout = QtWidgets.QVBoxLayout()
        self.central_widget = QtWidgets.QWidget()

        self.h_layout = QtWidgets.QHBoxLayout()
        self.h_layout.addWidget(self.start_button)
        self.h_layout.addWidget(self.stop_button)
        self.start_button.setText("Start")
        self.stop_button.setText("Stop")
        self.stop_button.setVisible(False)
        self.progress_bar.setValue(0)

        self.v_layout.addWidget(self.progress_bar)
        self.h_widget = QtWidgets.QWidget()
        self.h_widget.setLayout(self.h_layout)
        self.v_layout.addWidget(self.h_widget)

        self.central_widget.setLayout(self.v_layout)
        self.setCentralWidget(self.central_widget)

    def switch_to_stop(self):
        self.start_button.setVisible(False)
        self.stop_button.setVisible(True)

    def switch_to_start(self):
        self.start_button.setVisible(True)
        self.stop_button.setVisible(False)


class Worker(QtCore.QObject):
    def __init__(self):
        self.stop = False
        self.lock = threading.Lock()
        self.thread = None
        QtCore.QObject.__init__(self)

    value_changed = QtCore.pyqtSignal(int)
    work_status = QtCore.pyqtSignal(bool)

    def set_stop(self):
        self.lock.acquire()
        self.stop = True
        self.lock.release()

    def get_stop(self):
        self.lock.acquire()
        stop_value = self.stop
        self.lock.release()
        return stop_value

    def change_value(self, value):
        self.value_changed.emit(value)

    def send_work_status(self, status):
        self.work_status.emit(status)

    def start_new(self, starting_point, stopping_point):
        if self.thread is not None:
            self.set_stop()
            while self.thread.is_alive():
                time.sleep(0)
        self.stop = False
        self.thread = threading.Thread(target=self.work, args=[starting_point, stopping_point])
        self.thread.daemon = True  # So it will stop when the main thread stops
        self.thread.start()

    def work(self, starting_point, stopping_point):
        value = starting_point
        self.send_work_status(True)
        while not self.get_stop() and not value >= stopping_point:
            value += 1
            self.change_value(value)
            print(value)
            time.sleep(0.05)
        self.send_work_status(False)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.setMinimumWidth(300)
    main_window.show()

    worker = Worker()
    worker.value_changed.connect(main_window.progress_bar.setValue)
    main_window.stop_button.clicked.connect(worker.set_stop)
    main_window.start_button.clicked.connect(lambda clicked: worker.start_new(main_window.progress_bar.value() % 100, main_window.progress_bar.maximum()))

    # Work status signal notifies us when the worker status changes. Switch to the appropriate button
    worker.work_status.connect(lambda status: main_window.switch_to_start() if status is False else main_window.switch_to_stop())

    app.exec()




