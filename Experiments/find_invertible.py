import numpy as np


def find_invertible(size, max_tries=1000000):
    for i in range(max_tries):
        np.random.seed(i)
        r = np.random.random(size)
        if not np.isclose(np.linalg.det(r), 0):
            return r, i

    return None, i


a, b = find_invertible((500, 500))
print((a, b))
