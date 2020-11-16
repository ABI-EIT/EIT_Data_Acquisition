import sys
from PyQt5 import QtWidgets, QtCore
import threading
import time
import queue

from abc import ABCMeta, abstractmethod

title = "Qt Test"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        self.progress_bar_1 = QtWidgets.QProgressBar()
        self.progress_bar_2 = QtWidgets.QProgressBar()
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
        self.progress_bar_1.setValue(0)
        self.progress_bar_2.setValue(0)

        self.v_layout.addWidget(self.progress_bar_1)
        self.v_layout.addWidget(self.progress_bar_2)
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


class Worker:
    __metaclass__ = ABCMeta

    def __init__(self):
        self.worker_thread = None
        self.monitor_thread = None
        self.state = "Stop"
        # monitor queue

    def start(self, *args):
        self.worker_thread = threading.Thread(target=self.work, args=args, daemon=True)
        # start monitor thread

    # def state broadcast (abstract)

    @abstractmethod
    def work(self, *args):  # Maybe this shouldn't be abstract as we always need to send status
        pass                # but we need an abstract function within it


class Producer(Worker):
    def __init__(self):
        super().__init__()
        self.queues = []

    def add_subscriber(self, queue):
        self.queues.append(queue)

    def work(self, *args):
        # send work status
        # while not stopped:
        #   call producer_work
        #   publish result
        # send stopped
        pass

    @abstractmethod
    def producer_work(self, *args):
        pass


class Consumer(Worker):
    def __init__(self):
        super().__init__()
        self.queue = None

    def work(self, *args):
        # send work status
        #   While not stopped
        #   value = queue.get()
        #   on_work_done(value)
        # send work done
        pass

    @abstractmethod
    def on_work_done(self):
        pass

    @abstractmethod
    def consumer_work(self):
        pass


class MyProducer(QtCore.QObject):
    def __init__(self):
        QtCore.QObject.__init__(self)
        self.stop = False
        self.lock = threading.Lock()
        self.thread = None
        self.queues = []

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

    def publish(self, value):
        for queue in self.queues:
            queue.put(value)

    def add_subscriber(self, queue):
        self.queues.append(queue)

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
            self.publish(value)
            print(value)
            time.sleep(0.05)
        self.send_work_status(False)


class MyConsumer(QtCore.QObject):
    value_changed = QtCore.pyqtSignal(int)

    def __init__(self):
        QtCore.QObject.__init__(self)
        self.stop = False
        self.lock = threading.Lock()
        self.thread = None
        self.queue = queue.Queue()

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

    def start(self):
        if self.thread is not None:
            self.set_stop()
            while self.thread.is_alive():
                time.sleep(0)
        self.stop = False
        self.thread = threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        while not self.get_stop():
            value = self.queue.get()
            self.change_value(value)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.setMinimumWidth(300)
    main_window.show()

    producer = MyProducer()
    consumer_1 = MyConsumer()
    consumer_2 = MyConsumer()

    producer.add_subscriber(consumer_1.queue)
    producer.add_subscriber(consumer_2.queue)
    consumer_1.start()
    consumer_2.start()

    consumer_1.value_changed.connect(main_window.progress_bar_1.setValue)
    consumer_2.value_changed.connect(main_window.progress_bar_2.setValue)

    main_window.stop_button.clicked.connect(producer.set_stop)
    main_window.start_button.clicked.connect(
        lambda clicked: producer.start_new(main_window.progress_bar_1.value() % 100,
                                           main_window.progress_bar_1.maximum()))

    # Work status signal notifies us when the worker status changes. Switch to the appropriate button
    producer.work_status.connect(
        lambda status: main_window.switch_to_start() if status is False else main_window.switch_to_stop())

    app.exec()




