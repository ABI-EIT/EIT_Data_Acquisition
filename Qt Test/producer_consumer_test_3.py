import sys
from PyQt5 import QtWidgets, QtCore
import threading
import time
import queue
from abc import ABCMeta, abstractmethod


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


class Worker(QtCore.QObject):
    __metaclass__ = ABCMeta
    state_signal = QtCore.pyqtSignal(str)  # Replace all this shit with the monitor thread + a virtual function

    def __init__(self):
        QtCore.QObject.__init__(self)
        self.worker_thread = None
        self.monitor_thread = None
        self.state = "Stopped"
        self.lock = threading.Lock()
        # monitor queue + monitor thread should replace the threading.lock

    def set_stopped(self):
        self.lock.acquire()
        self.state = "Stopped"
        self.lock.release()

    def get_state(self):
        self.lock.acquire()
        state = self.state
        self.lock.release()
        return state

    def send_state(self):
        self.state_signal.emit(self.state)

    def start_new(self, on_start_args, work_args, on_stopped_args):
        if self.worker_thread is not None:
            self.set_stop()
            while self.worker_therad.is_alive():
                time.sleep(0)
        self.state = "Started"
        self.worker_thread = threading.Thread(target=self.work, args=(on_start_args, work_args, on_stopped_args), daemon=True).start()
        # start monitor thread

    # def state broadcast (abstract)

    @abstractmethod
    def work(self, *args):  # Maybe this shouldn't be abstract as we always need to send status
        pass                # but we need an abstract function within it

    @abstractmethod
    def on_start(self, *args):
        pass

    @abstractmethod
    def on_stopped(self, *args):
        pass


class Producer(Worker):
    __metaclass__ = ABCMeta

    def __init__(self):
        super().__init__()
        self.queues = []

    def add_subscriber(self, queue):
        self.queues.append(queue)

    def work(self, on_start_args, work_args, on_stopped_args):
        self.send_state()
        self.on_start(*on_start_args)
        while self.state != "Stopped":
            result = self.producer_work(*work_args)
            for queue in self.queues:
                queue.put(result)
        self.send_state()
        self.on_stopped(*on_stopped_args)

    @abstractmethod
    def producer_work(self, *args):
        # Gets called in loop. Use self.set_stopped() to stop
        pass


class Consumer(Worker):
    __metaclass__ = ABCMeta

    def __init__(self):
        super().__init__()
        self.queue = queue.Queue()

    def work(self,  on_start_args, work_args, on_stopped_args):
        self.send_state()
        self.on_start(*on_start_args)
        while self.state != "Stopped":
            item = self.queue.get()
            self.consumer_work(item, *work_args)
        self.send_state()
        self.on_stopped(*on_stopped_args)

    @abstractmethod
    def consumer_work(self, item, *args):
        # Gets called in loop. Use self.set_stopped() to stop
        pass


class MyProducer(Producer):
    def on_start(self, start_point, stop_point, on_start_message):
        self.value = start_point
        self.stop_point = stop_point
        print(on_start_message)

    def on_stopped(self, on_stopped_message):
        print(on_stopped_message)

    def producer_work(self, *args):
        time.sleep(0.05)
        if self.value < self.stop_point:
            self.value += 1
        else:
            self.set_stopped()
        return self.value


class MyConsumer(Consumer, QtCore.QObject):
    value_changed = QtCore.pyqtSignal(int)

    def on_start(self, on_start_message):
        print(on_start_message)

    def on_stopped(self, on_stopped_message):
        print(on_stopped_message)

    def consumer_work(self, item, *args):
        self.value_changed.emit(item)


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
    consumer_1.start_new(on_start_args=("Started consumer_1",), work_args="", on_stopped_args=("Stopped consumer_1",))
    consumer_2.start_new(on_start_args=("Started consumer_2",), work_args="", on_stopped_args=("Stopped consumer_2",))

    consumer_1.value_changed.connect(main_window.progress_bar_1.setValue)
    consumer_2.value_changed.connect(main_window.progress_bar_2.setValue)

    main_window.stop_button.clicked.connect(producer.set_stopped)
    main_window.start_button.clicked.connect(
        lambda clicked: producer.start_new(on_start_args=(main_window.progress_bar_1.value() % 100, main_window.progress_bar_1.maximum(), "Started producer"),
                                           work_args="", on_stopped_args=("Stopped producer",),
                                           ))

    # Work status signal notifies us when the worker status changes. Switch to the appropriate button
    producer.state_signal.connect(
        lambda status: main_window.switch_to_start() if status == "Stopped" else main_window.switch_to_stop())

    app.exec()
