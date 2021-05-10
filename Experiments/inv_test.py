import numpy as np
from numpy.linalg import inv
import time

iterations = 100

invstart = time.time()
np.random.seed(0)
a = np.random.random((500,500))
ainv = [inv(a) for _ in range(iterations)]
invend = time.time()

mulstart = time.time()
np.random.seed(0)
a = np.random.random((500,500))
amul = [np.matmul(a, a) for _ in range(iterations)]
mulend = time.time()

print(f'inv took {invend-invstart:.2f} seconds\n' +
      f'mul took {mulend-mulstart:.2f} seconds')
