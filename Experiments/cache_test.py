import numpy as np
import timeit
from functools import lru_cache, wraps
from hashlib import sha1
from numpy import uint8
import time


def measure(func):
    @wraps(func)
    def _time_it(*args, **kwargs):
        start = int(round(time.time() * 1000))
        try:
            return func(*args, **kwargs)
        finally:
            end_ = int(round(time.time() * 1000)) - start
            print(f"Function {func.__name__} execution time: {end_ if end_ > 0 else 0} ms")
    return _time_it


class Foo:
    def __init__(self, arr):
        self.arr = arr**60
        time.sleep(0.1)


@measure
def loop(cached=False):
    arr = np.array([1., 2., 3., 4.])

    foos = []
    for i in range(100):
        if cached:
            foos.append(cached_create_foo(arr))
        else:
            foos.append(Foo(arr))

    return foos


class HashableArrayContainer:
    def __init__(self, array):
        self.array = array

    def __eq__(self, other):
        return all(self.array == other.array)

    def __hash__(self):
        return int(sha1(self.array.view(uint8)).hexdigest(), 16)


def cached_create_foo(array):
    hashable_array_container = HashableArrayContainer(array)
    create_foo_with_hashables(hashable_array_container)


@lru_cache
def create_foo_with_hashables(hashable_array_container):
    arr = hashable_array_container.array
    foo = Foo(arr)
    return foo


if __name__ == "__main__":

    print("Cached loop...")
    loop(cached=True)

    print("Uncached loop...")
    loop(cached=False)
