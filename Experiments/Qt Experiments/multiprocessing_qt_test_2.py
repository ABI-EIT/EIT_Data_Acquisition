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

    state = "Stopped"

    @abstractmethod
    def work(self, *args):
        pass

    def get_state(self):
        return self.state

    def set_state(self, state):
        self.state = state


class StringEmitter(QtCore.QObject):
    new_data = QtCore.pyqtSignal(str)

    def emit(self, data):
        self.new_data.emit(data)


class Producer(Worker):
    def __init__(self, queue):
        self.queue = queue

    def work(self):
        self.state = "Started"
        i = 0
        while self.state == "Started":
            i += 1
            self.process_work(i)
            time.sleep(1)

    def process_work(self, result):
        print("Producer: " + str(result))
        self.queue.put(result)


class Consumer(Worker):

    def __init__(self, producer_queue, result_queue):
        self.producer_queue = producer_queue
        self.result_queue = result_queue

    def work(self):
        self.state = "Started"
        while self.state == "Started":
            i = self.producer_queue.get()
            self.process_work(i)

    def process_work(self, result):
        result = result*2
        print("Consumer: " + str(result))
        self.result_queue.put(result)


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

    WorkerManager.register('Producer', Producer)
    WorkerManager.register('Consumer', Consumer)
    manager = WorkerManager()
    manager.start()

    producer_queue = multiprocessing.Manager().Queue()
    result_queue = multiprocessing.Manager().Queue()

    producer = manager.Producer(producer_queue)
    start_new(producer)

    consumer = manager.Consumer(producer_queue, result_queue)
    start_new(consumer)

    string_emitter = StringEmitter()
    string_emitter.new_data.connect(main_window.label.setText)

    threading.Thread(target=receive_and_emit, args=(result_queue, string_emitter)).start()

    app.exec()

