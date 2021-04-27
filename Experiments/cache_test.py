import numpy as np
import timeit
from functools import lru_cache

from hashlib import sha1
from numpy import array, uint8
import time

@lru_cache
class Foo:
    def __init__(self, arr):
        self.arr = np.power(arr,60)
        time.sleep(0.1)


class Bar:
    def __init__(self, arr):
        self.arr = np.power(arr,60)
        time.sleep(0.1)


loopnum = 100


def fooloop():
    an_array = np.array([1., 2., 3., 4.])
    a_hashable = HashableNdarray(an_array)

    foos = []
    for i in range(loopnum):
        foos.append(Foo(a_hashable))

    return foos


def barloop():
    an_array = np.array([1., 2., 3., 4.])

    bars = []
    for i in range(loopnum):
        bars.append(Bar(an_array))

    return bars


class Wrapper(object):
    """Wrapper class that provides proxy access to an instance of some
       internal instance."""

    __wraps__  = None
    __ignore__ = "class mro new init setattr getattr getattribute"

    def __init__(self, obj):
        if self.__wraps__ is None:
            raise TypeError("base class Wrapper may not be instantiated")
        elif isinstance(obj, self.__wraps__):
            self._obj = obj
        else:
            raise ValueError("wrapped object must be of %s" % self.__wraps__)

    # provide proxy access to regular attributes of wrapped object
    def __getattr__(self, name):
        return getattr(self._obj, name)

    # create proxies for wrapped object's double-underscore attributes
    class __metaclass__(type):
        def __init__(cls, name, bases, dct):

            def make_proxy(name):
                def proxy(self, *args):
                    return getattr(self._obj, name)
                return proxy

            type.__init__(cls, name, bases, dct)
            if cls.__wraps__:
                ignore = set("__%s__" % n for n in cls.__ignore__.split())
                for name in dir(cls.__wraps__):
                    if name.startswith("__"):
                        if name not in ignore and name not in dct:
                            setattr(cls, name, property(make_proxy(name)))


class HashableNdarray(Wrapper):
    __wraps__ = np.ndarray

    def __eq__(self, other):
        return all(self == other)

    def __hash__(self):
        return int(sha1(self.view(uint8)).hexdigest(), 16)


if __name__ == "__main__":
    a = timeit.timeit(fooloop, number=1)
    print(f"Cached loop took {a} seconds")


    a = timeit.timeit(barloop, number=1)
    print(f"Uncached loop took {a} seconds")