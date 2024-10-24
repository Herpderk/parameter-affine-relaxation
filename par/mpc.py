from typing import List, Union
import time

import casadi as cs
import numpy as np
from scipy.interpolate import make_interp_spline
import matplotlib.pyplot as plt
import matplotlib

from par.dynamics.models import DynamicsModel, KoopmanLiftedQuadrotorModel
from par.dynamics.vectors import State, Input, ModelParameters, \
                                    KoopmanLiftedState, VectorList
from par.config import STATE_CONFIG, KOOPMAN_STATE_CONFIG, INPUT_CONFIG
from par.utils.config import get_config_values, get_dimensions
from par.utils.misc import is_none


# TODO: separate solver initialization and solver call
class NMPC():
    def __init__(
        self,
        dt: float,
        N: int,
        Q: np.ndarray,
        R: np.ndarray,
        Qf: np.ndarray,
        model: DynamicsModel,
        is_verbose=False,
    ) -> None:
        self._dt = dt
        self._N = N
        self._Q = Q
        self._R = R
        self._Qf = Qf
        self._model = model
        self._sol = {}
        self._lbg = None
        self._ubg = None

        if type(model) == KoopmanLiftedQuadrotorModel:
            self._is_koopman = True
            self._lbx = KoopmanLiftedState(
                get_config_values(
                    "lower_bound", model.state_config, copies=model.order),
                self._model.order
            )
            self._ubx = KoopmanLiftedState(
                get_config_values(
                    "upper_bound", KOOPMAN_STATE_CONFIG, copies=model.order),
                self._model.order
            )
        else:
            self._is_koopman = False
            self._lbx = State(get_config_values("lower_bound", STATE_CONFIG))
            self._ubx = State(get_config_values("upper_bound", STATE_CONFIG))

        self._lbu = Input(get_config_values("lower_bound", INPUT_CONFIG))
        self._ubu = Input(get_config_values("upper_bound", INPUT_CONFIG))
        self._theta = self._model.parameters
        self._us_guess = VectorList(self._N * [Input()])
        self._solver = self._init_solver(is_verbose)

    def get_predicted_states(self) -> VectorList:
        nx = self._model.nx
        nu = self._model.nu
        xs = VectorList()
        for k in range(1, self._N + 1):
            if self._is_koopman:
                xs.append(KoopmanLiftedState(np.array(
                    self._sol["x"][k*(nx+nu) : k*(nx+nu) + nx]).flatten(),
                    self._model.order
                ))
            else:
                xs.append(State(np.array(
                    self._sol["x"][k*(nx+nu) : k*(nx+nu) + nx]).flatten()))
        return xs

    def get_predicted_inputs(self) -> VectorList:
        nx = self._model.nx
        nu = self._model.nu
        us = VectorList()
        for k in range(self._N):
            us.append(Input(np.array(
                self._sol["x"][(k+1)*nx+k*nu : (k+1)*nx+(k+1)*nu]).flatten()))
        return us

    def plot_trajectory(
        self,
        xs: VectorList = None,
        us: VectorList = None,
        dt: float = None,
        N: float = None,
        order: int = None,
    ) -> None:
        """
        Display the series of control inputs
        and trajectory over prediction horizon.
        """
        if is_none(dt): dt = self._dt
        if is_none(N): N = self._N

        t = dt * np.arange(N)
        interp_N = 1000
        fig, axs = plt.subplots(5, figsize=(11, 9))

        if is_none(us):
            us = self.get_predicted_inputs().as_array()
        else:
            us = us.as_array()
        legend = ["u1", "u2", "u3", "u4"]
        self._plot_trajectory(
            axs[0], t, us, interp_N, legend,
            "squared motor\nang vel (rad/s)^2",
        )

        if not self._is_koopman:
            if is_none(xs):
                xs = self.get_predicted_states().as_array()
            else:
                xs = xs.as_array()
            if len(xs) > len(us):
                xs = xs[:len(us), :]
            legend = ["x", "y", "z"]
            self._plot_trajectory(
                axs[1], t, xs[:,:3], interp_N, legend,
                "pos (m)"
            )
            legend = ["qw", "qx", "qy", "qz"]
            self._plot_trajectory(
                axs[2], t, xs[:, 3:7], interp_N, legend,
                "att (quat)"
            )
            legend = ["vx", "vy", "vz"]
            self._plot_trajectory(
                axs[3], t, xs[:, 7:10], interp_N, legend,
                "body frame\nvel (m/s)"
            )
            legend = ["wx", "wy", "wz"]
            self._plot_trajectory(
                axs[4], t, xs[:, 10:13], interp_N, legend,
                "body frame\nang vel (rad/s)",
            )

        for ax in axs.flat:
            ax.set(xlabel="time (s)")
            ax.label_outer()
        plt.show()

    def solve(
        self,
        x: Union[State, KoopmanLiftedState],
        xref: VectorList,
        uref: VectorList,
        theta: ModelParameters = None,
        lbx: State = None,
        ubx: State = None,
        lbu: Input = None,
        ubu: Input = None,
        xs_guess: VectorList = None,
        us_guess: VectorList = None,
    ) -> dict:
        # Enforce correct horizon length
        assert len(xref.get()) == len(uref.get()) == self._N

        # Get default inequality constraints
        if is_none(lbx): lbx = self._lbx
        if is_none(ubx): ubx = self._ubx
        if is_none(lbu): lbu = self._lbu
        if is_none(ubu): ubu = self._ubu
        if is_none(theta): theta = self._theta
        if is_none(us_guess): us_guess = self._us_guess
        if is_none(xs_guess): xs_guess = VectorList(self._N * [x])

        # Initialize the parameter argument
        p = theta.as_list()
        if self._is_koopman:
            assert type(x) == KoopmanLiftedState
            p += KoopmanLiftedState(x.get_zero_order_array(), 1).as_list()
        else:
            assert type(x) == State

        # Construct optimization arguments
        lbd = x.as_list()
        ubd = x.as_list()
        guess = x.as_list()
        for k in range(self._N):
            lbd += lbu.as_list() + lbx.as_list()
            ubd += ubu.as_list() + ubx.as_list()
            guess += us_guess.get(k).as_list() + xs_guess.get(k).as_list()
            p += uref.get(k).as_list() + xref.get(k).as_list()

        # Solve
        st = time.perf_counter()
        self._sol = self._solver(
            x0=guess, p=p, lbx=lbd, ubx=ubd, lbg=self._lbg, ubg=self._ubg)
        et = time.perf_counter()
        self._sol["solve_time"] = et - st
        return self._sol

    def _init_solver(
        self,
        is_verbose: bool
    ) -> dict:
        # Decision variable for state
        x0 = cs.SX.sym("x0", self._model.nx)
        # Constant for model parameters
        theta = cs.SX.sym("theta", self._model.ntheta)
        # Constant for koopman initialization
        if self._is_koopman:
            z0 = cs.SX.sym("z0", get_dimensions(KOOPMAN_STATE_CONFIG))
        else:
            z0 = cs.SX()

        # Variables for formulating NLP
        p = [theta, z0]
        d = [x0]
        g = []
        lbg = []
        ubg = []
        J = 0.0

        # Formulate the nlp
        xk = x0
        for k in range(self._N):
            # New decision variable for control
            uk = cs.SX.sym("u" + str(k), self._model.nu)
            d += [uk]

            # Get the state at the end of the time step
            if self._is_koopman:
                xf = self._model.F(self._dt, x=xk, u=uk, theta=theta, z0=z0)
            else:
                xf = self._model.F(dt=self._dt, x=xk, u=uk, theta=theta)

            # New NLP variable for state at the end of the interval
            xk = cs.SX.sym("x" + str(k+1), self._model.nx)
            d += [xk]

            # New constants for reference tracking
            uref_k = cs.SX.sym("uref" + str(k), self._model.nu)
            xref_k = cs.SX.sym("xref" + str(k+1), self._model.nx)
            p += [uref_k, xref_k]

            # Add costs
            J += self._get_stage_cost(x=xk, u=uk, xref=xref_k, uref=uref_k)
            if k == self._N - 1:
                J += self._get_terminal_cost(x=xk, xref=xref_k)

            # Add dynamics equality constraint
            g += [xf - xk]
            lbg += self._model.nx * [0.0]
            ubg += self._model.nx * [0.0]

        # Concatenate decision variables and constraint terms
        d = cs.vertcat(*d)
        p = cs.vertcat(*p)
        g = cs.vertcat(*g)

        # Initialize equality constraint values
        self._lbg = lbg
        self._ubg = ubg

        # Create NLP solver
        nlp_prob = {"f": J, "x": d, "p": p, "g": g}
        opts = {"ipopt.max_iter": 3000} #{"ipopt.hessian_approximation": "exact"}
        if not is_verbose:
            opts["ipopt.print_level"] = 0
            opts["print_time"] = 0
            opts["ipopt.sb"] = "yes"
            #opts["ipopt.hessian_approximation"] = "exact"
        #opts = {"error_on_fail": False}
        #return cs.qpsol("nlp_solver", "osqp", nlp_prob, opts)
        return cs.nlpsol("nlp_solver", "ipopt", nlp_prob, opts)

    def _get_stage_cost(
        self,
        x: cs.SX,
        u: cs.SX,
        xref: cs.SX,
        uref: cs.SX,
    ) -> cs.SX:
        state_err = x - xref
        input_err = u - uref
        return state_err.T @ self._Q @ state_err + \
                input_err.T @ self._R @ input_err

    def _get_terminal_cost(
        self,
        x: cs.SX,
        xref: np.ndarray,
    ) -> cs.SX:
        err = x - xref
        return err.T @ (self._Qf - self._Q) @ err

    def _plot_trajectory(
        self,
        ax: matplotlib.axes,
        Xs: np.ndarray,
        traj: np.ndarray,
        interp_N: int,
        legend: List[str],
        ylabel: str,
    ) -> None:
        ax.set_ylabel(ylabel)
        for i in range(traj.shape[1]):
            x_interp = self._get_interpolation(Xs, Xs, interp_N)
            y_interp = self._get_interpolation(Xs, traj[:, i], interp_N)
            ax.plot(x_interp, y_interp, label=legend[i])
        ax.legend()

    def _get_interpolation(
        self,
        Xs: np.ndarray,
        Ys: np.ndarray,
        N: int,
    ) -> np.ndarray:
        spline_func = make_interp_spline(Xs, Ys)
        interp_x = np.linspace(Xs.min(), Xs.max(), N)
        interp_y = spline_func(interp_x)
        return interp_y
