from typing import Tuple, Union
from math import factorial as fact

import numpy as np


def alternating_ones(shape: Union[int, Tuple[int]]) -> np.ndarray:
    ones = np.ones(shape)
    ones[::2] = -1.0
    return ones


def jordan_block(lam: float, n: int) -> np.ndarray:
    J = np.diag(lam * np.ones(n))
    for i in range(n - 1):
        J[i, i+1] = 1.0
    return J


def binomial_coefficient(k: int, n: int) -> float:
    return fact(k) / ( fact(n) * fact(k-n) )


def skew(a: np.ndarray) -> np.ndarray:
    assert a.shape == (3,)
    return np.array([
        [ 0.0, -a[2], a[1] ],
        [ a[2], 0.0, -a[0] ],
        [ -a[1], a[0], 0.0 ]
    ])
