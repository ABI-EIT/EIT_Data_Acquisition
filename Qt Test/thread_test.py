import sys
from PyQt5 import QtWidgets
import threading
import time

app = QtWidgets.QApplication(sys.argv)
p = QtWidgets.QProgressBar()
p.show()


def work():
    for i in range(101):
        p.setValue(i)
        print(i)
        time.sleep(.05)


def ui():
    app.exec()


def main():
    thread = threading.Thread(target=work)
    thread.start()
    ui()


main()





