from multiprocessing import freeze_support, Process
from multiprocessing.managers import BaseManager
import time
from abc import ABCMeta, abstractmethod


class WorkerManager(BaseManager):
    pass


class Worker:
    __metaclass__ = ABCMeta

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

    def get_state(self):
        return self.state

    def set_state(self, state):
        self.state = state


class MyWorker(Worker):
    def work(self, *args):
        self.state = "Started"
        i = 0
        while self.state == "Started":
            i += 1
            print(i)
            time.sleep(1)


def start_new(worker):
    p = Process(target=worker.work)
    p.start()
    return p


def test():
    my_worker = MyWorker()
    print(my_worker.get_state())
    p = start_new(my_worker)
    time.sleep(1)
    print(my_worker.get_state())
    time.sleep(4)
    my_worker.set_state("Stopped")
    print(my_worker.get_state())
    p.join()


if __name__ == '__main__':
    test()
