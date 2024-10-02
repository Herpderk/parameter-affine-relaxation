import casadi as cs
import numpy as np

H = np.vstack((
    np.zeros((1,3)),
    np.eye(3),
))

def L_or_R(q: cs.SX, is_L: bool) -> cs.SX:
    assert q.shape[0] == 4
    scalar = q[0]
    vector = q[-3:]
    if not is_L:
        sign = -1
    else:
        sign = 1
    return cs.SX(cs.vertcat(
        cs.horzcat(scalar, -vector.T),
        cs.horzcat(vector, scalar*cs.SX.eye(3) + sign*cs.skew(vector))
    ))

def L(q: cs.SX) -> cs.SX:
    return L_or_R(q, is_L=True)

def R(q: cs.SX) -> cs.SX:
    return L_or_R(q, is_L=False)

def G(q: cs.SX) -> cs.SX:
    return L(q) @ H

def Q(q: cs.SX) -> cs.SX:
    return H.T @ R(q) @ L(q) @ H

def random_unit_quat():
    unscaled_quat = np.random.uniform(low=-1.0, high=1.0, size=4)
    return unscaled_quat / np.linalg.norm(unscaled_quat)