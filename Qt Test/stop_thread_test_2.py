import sys
from PyQt5 import QtWidgets, QtCore
import threading
import time

app = QtWidgets.QApplication(sys.argv)
progress_bar = QtWidgets.QProgressBar()
button = QtWidgets.QPushButton()
button.setText("Stop")
main_window = QtWidgets.QMainWindow()
v_layout = QtWidgets.QVBoxLayout()

v_layout.addWidget(progress_bar)
v_layout.addWidget(button)

central_widget = QtWidgets.QWidget()
central_widget.setLayout(v_layout)

main_window.setCentralWidget(central_widget)

main_window.show()


# This class separates the worker thread from the qt widgets. Worker thread calls change_value, change_value emits a signal
# to the progress bar. This stops the program from crashing when the button is moused over
class ValueChanger(QtCore.QObject):
    value_changed = QtCore.pyqtSignal(int)

    def change_value(self, value):
        self.value_changed.emit(value)


class StopFlag:  # Simple mutex for communicating with the worker thread
    def __init__(self):
        self.stop = False
        self.lock = threading.Lock()

    def set_stop(self):
        self.lock.acquire()
        self.stop = True
        self.lock.release()


value_changer = ValueChanger()
value_changer.value_changed.connect(progress_bar.setValue)
stop_flag = StopFlag()
button.clicked.connect(stop_flag.set_stop)


def work():
    for i in range(101):
        stop_flag.lock.acquire()
        if stop_flag.stop:
            break
        stop_flag.lock.release()
        value_changer.change_value(i)
        print(i)
        time.sleep(.05)


def ui():
    app.exec()


thread = threading.Thread(target=work)


def main():
    thread.start()
    ui()


main()





