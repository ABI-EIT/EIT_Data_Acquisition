from multiprocessing import freeze_support, Process, Queue
from multiprocessing.managers import BaseManager
import multiprocessing.managers
import time
from abc import ABCMeta, abstractmethod
from PyQt5 import QtWidgets, QtCore
import sys
import threading


class WorkerManager(BaseManager):
    pass


class Worker:
    __metaclass__ = ABCMeta

    queue = None
    use_queue = False

    state = "Stopped"

    def __new__(cls, manager_calling=False):
        if manager_calling:
            return super().__new__(cls)
        else:
            WorkerManager.register('Worker', cls)
            manager = WorkerManager()
            manager.start()
            return manager.Worker(manager_calling=True)

    @abstractmethod
    def work(self, *args):
        pass

    def set_use_queue(self, use_queue):
        self.use_queue = use_queue

    def get_state(self):
        return self.state

    def set_state(self, state):
        self.state = state


class StringEmitter(QtCore.QObject):
    new_data = QtCore.pyqtSignal(str)

    def emit(self, data):
        self.new_data.emit(data)


class MyWorker(Worker):

    def work(self, queue=None):
        self.state = "Started"
        i = 0
        self.queue = queue
        while self.state == "Started":
            i += 1
            self.process_work(i)
            time.sleep(1)

    def process_work(self, result):
        print(result)
        if self.use_queue:
            self.queue.put(result)


def start_new(worker, *args):
    p = Process(target=worker.work, args=args)
    p.start()
    return p


def receive_and_emit(queue, emitter):
    while 1:
        item = queue.get()
        emitter.new_data.emit(str(item))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        self.label = QtWidgets.QLabel()
        self.label.setText("Label")
        self.grid_layout = QtWidgets.QGridLayout()
        self.central_widget = QtWidgets.QWidget()
        self.grid_layout.addWidget(self.label)
        self.central_widget.setLayout(self.grid_layout)
        self.setCentralWidget(self.central_widget)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()

    queue = multiprocessing.Manager().Queue()
    my_worker = MyWorker()
    start_new(my_worker, queue)
    my_worker.set_use_queue(True)

    string_emitter = StringEmitter()
    string_emitter.new_data.connect(main_window.label.setText)

    threading.Thread(target=receive_and_emit, args=(queue, string_emitter)).start()

    app.exec()

