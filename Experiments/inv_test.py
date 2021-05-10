import numpy as np
from numpy.linalg import inv
import time

iterations = 1
n = 1000

invstart = time.time()
a = np.linspace(0, 1,  n*n).reshape(n, n)
ainv = [inv(a) for _ in range(iterations)]
invend = time.time()

mulstart = time.time()
a = np.linspace(0, 1, n*n).reshape(n, n)
amul = [np.matmul(a, a) for _ in range(iterations)]
mulend = time.time()

print(f'inv took {invend-invstart:.2f} seconds\n' +
      f'mul took {mulend-mulstart:.2f} seconds')
