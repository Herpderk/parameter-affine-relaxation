#!/usr/bin/python3

import numpy as np
from numpy.random import uniform
from par.dynamics.vectors import State, Input, KoopmanLiftedState, \
                                    VectorList
from par.dynamics.models import CrazyflieModel, KoopmanLiftedQuadrotorModel
from par.utils.math import random_unit_quaternion
from par.mpc import NMPC


order = 8
nl_model = CrazyflieModel()
km_model = KoopmanLiftedQuadrotorModel(
    observables_order=order, parameters=nl_model.parameters)

dt = 0.1
N = 10
Q = np.diag(np.hstack((
    10.0 * np.ones(3), 10.0 * np.ones(3*(order-1)),   # position
    1.0 * np.ones(3), 1.0 * np.ones(3*(order-1)),    # velocity
    np.zeros(3*order),                                # gravity
    1.0 * np.ones(3), 1.0 * np.ones(3*(order-1)),    # angular velocity
)))
R = 0.0 * np.eye(4)
Qf = 2.0 * Q
km_mpc = NMPC(dt=dt, N=N, Q=Q, R=R, Qf=Qf, model=km_model, is_verbose=True)

x = State()
x.set_member("POSITION", uniform(-10.0, 10.0, size=3))
x.set_member("ATTITUDE", random_unit_quaternion())
x.set_member("BODY_FRAME_LINEAR_VELOCITY", uniform(-10.0, 10.0, size=3))
x.set_member("BODY_FRAME_ANGULAR_VELOCITY", uniform(-10.0, 10.0, size=3))

J = np.diag(np.hstack((
    km_model.parameters.get_member("Ixx"),
    km_model.parameters.get_member("Iyy"),
    km_model.parameters.get_member("Izz")
)))
z = x.as_lifted_koopman(J, order)

lbu = Input(np.zeros(4))
ubu = Input(0.15 * np.ones(4))

zref = VectorList( N * [KoopmanLiftedState(order=order)] )
uref = VectorList( N * [Input()] )

km_mpc.solve(x=z, xref=zref, uref=uref, lbu=lbu, ubu=ubu)
km_mpc.plot_trajectory()
