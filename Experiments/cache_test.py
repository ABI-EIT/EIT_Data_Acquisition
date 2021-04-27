import numpy as np
import timeit
from functools import lru_cache

from hashlib import sha1
from numpy import array, uint8
import time

@lru_cache
class Foo:
    def __init__(self, arr):
        arr = arr.unwrap()
        self.arr = arr**60
        time.sleep(0.1)


class Bar:
    def __init__(self, arr):
        self.arr = arr**60
        time.sleep(0.1)


loopnum = 100

def fooloop():
    an_array = np.array([1., 2., 3., 4.])

    foos = []
    for i in range(loopnum):
        foos.append(Foo(hashable(an_array)))

    return foos

def barloop():
    an_array = np.array([1., 2., 3., 4.])

    bars = []
    for i in range(loopnum):
        bars.append(Bar(an_array))

    return bars



class hashable(object):
    r'''Hashable wrapper for ndarray objects.
        Instances of ndarray are not hashable, meaning they cannot be added to
        sets, nor used as keys in dictionaries. This is by design - ndarray
        objects are mutable, and therefore cannot reliably implement the
        __hash__() method.
        The hashable class allows a way around this limitation. It implements
        the required methods for hashable objects in terms of an encapsulated
        ndarray object. This can be either a copied instance (which is safer)
        or the original object (which requires the user to be careful enough
        not to modify it).
    '''
    def __init__(self, wrapped, tight=False):
        r'''Creates a new hashable object encapsulating an ndarray.
            wrapped
                The wrapped ndarray.
            tight
                Optional. If True, a copy of the input ndaray is created.
                Defaults to False.
        '''
        self.__tight = tight
        self.__wrapped = array(wrapped) if tight else wrapped
        self.__hash = int(sha1(wrapped.view(uint8)).hexdigest(), 16)

    def __eq__(self, other):
        return all(self.__wrapped == other.__wrapped)

    def __hash__(self):
        return self.__hash

    def unwrap(self):
        r'''Returns the encapsulated ndarray.
            If the wrapper is "tight", a copy of the encapsulated ndarray is
            returned. Otherwise, the encapsulated ndarray itself is returned.
        '''
        if self.__tight:
            return array(self.__wrapped)

        return self.__wrapped


if __name__ == "__main__":
    a = timeit.timeit(fooloop, number=1)
    print(f"Cached loop took {a} seconds")


    a = timeit.timeit(barloop, number=1)
    print(f"Uncached loop took {a} seconds")