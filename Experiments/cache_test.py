import numpy as np
import timeit
from functools import lru_cache, wraps
from hashlib import sha1
from numpy import uint8
import time
import pickle


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
            foos.append(cached_caller(Foo, str, arr))
        else:
            foos.append(Foo(arr))

    return foos


def cached_caller(callable, hashable_transform=str, *args, **kwargs):
    """
    A function to wrap the arguments of a callable into hashable containers, then run the callable with lru_cache turned on.
    The hashable transform is a callable used to transform the args and kwargs into a form that implements the __hash__()
    and __eq__() methods.

    TODO: Add ability to control the size of the lru_cache
    TODO: Add ability to specify a different hashable transform for each arg and kwarg

    Parameters
    ----------
    callable: callable to call with lru_cache
    hashable_transform: callable. default is str. Another option is pickle.dumps. If None is passed, the arguments must
                        already be hashable
    args: args for callable
    kwargs: kwargs for callable

    Returns
    -------
    result of callable

    """
    if hashable_transform is not None:
        hashable_args = [HashableContainer(arg, hashable_transform) for arg in args]
        hashable_kwargs = {key: HashableContainer(val, hashable_transform) for key, val in kwargs.items()}
    else:
        hashable_args = args
        hashable_kwargs = kwargs
    return _call_with_hashables(callable, *hashable_args, **hashable_kwargs)


class HashableContainer:
    def __init__(self, object, hashable_transform):
        self.object = object
        self.hash_trans = hashable_transform

    def __eq__(self, other):
        return self.hash_trans(self.object) == self.hash_trans(other.object)

    def __hash__(self):
        return hash(self.hash_trans(self.object))


@lru_cache
def _call_with_hashables(wrapped, *hashable_args, **hashable_kwargs):
    original_args = [arg.object for arg in hashable_args]
    original_kwargs = {key: val.object for key, val in hashable_kwargs.items()}
    result = wrapped(*original_args, **original_kwargs)
    return result



if __name__ == "__main__":
    print("Cached loop...")
    loop(cached=True)

    print("Uncached loop...")
    loop(cached=False)
