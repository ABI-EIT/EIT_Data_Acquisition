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
            foos.append(str_hashed_create(Foo, arr))
        else:
            foos.append(Foo(arr))

    return foos


class StrHashingContainer:
    def __init__(self, object):
        self.object = object

    def __eq__(self, other):
        return str(self.object) == str(other.object)

    def __hash__(self):
        return hash(str(self.object))


def str_hashed_create(type, *args, **kwargs):
    hashed_args = [StrHashingContainer(arg) for arg in args]
    hashed_kwargs = {key: StrHashingContainer(val) for key, val in kwargs.items()}
    return create_with_str_hashables(type, *hashed_args, **hashed_kwargs)


@lru_cache
def create_with_str_hashables(type, *args, **kwargs):
    unhashed_args = [arg.object for arg in args]
    unhashed_kwargs = {key: val.object for key, val in kwargs.items()}
    foo = type(*unhashed_args, **unhashed_kwargs)
    return foo


if __name__ == "__main__":

    print("Cached loop...")
    loop(cached=True)

    print("Uncached loop...")
    loop(cached=False)
