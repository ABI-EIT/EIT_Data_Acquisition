import sys
from PyQt5 import QtWidgets, QtCore
import threading
import time


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        self.progress_bar = QtWidgets.QProgressBar()
        self.button = QtWidgets.QPushButton()
        self.v_layout = QtWidgets.QVBoxLayout()
        self.central_widget = QtWidgets.QWidget()

        self.button.setText("Stop")
        self.v_layout.addWidget(self.progress_bar)
        self.v_layout.addWidget(self.button)

        self.central_widget.setLayout(self.v_layout)
        self.setCentralWidget(self.central_widget)


class Worker(QtCore.QObject):
    def __init__(self):
        self.stop = False
        self.lock = threading.Lock()
        QtCore.QObject.__init__(self)

    value_changed = QtCore.pyqtSignal(int)

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

    def work(self):
        for i in range(101):
            if self.get_stop():
                break
            self.change_value(i)
            print(i)
            time.sleep(.05)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()

    worker = Worker()
    worker.value_changed.connect(main_window.progress_bar.setValue)
    main_window.button.clicked.connect(worker.set_stop)

    thread = threading.Thread(target=worker.work)

    thread.start()
    app.exec()




