import sys
from PyQt5 import QtWidgets
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


def work():
    for i in range(101):
        progress_bar.setValue(i)  # This is not safe. This app crashes when you mouse over the stop button
        print(i)                  # By the way, we didn't get a chance to try to implement stopping the thread
        time.sleep(.05)


def ui():
    app.exec()


def main():
    thread = threading.Thread(target=work)
    thread.start()
    ui()


main()





