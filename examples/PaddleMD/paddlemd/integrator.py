import numpy as np
import paddle

TIMEFACTOR = 48.88821
BOLTZMAN = 0.001987191


def paddlerandn_like(x):  # 添加飞桨的randn_like函数
    return paddle.randn(x.shape)


def kinetic_energy(masses, vel):
    Ekin = paddle.sum(
        0.5 * paddle.sum(vel * vel, axis=2, keepdim=True) * masses, axis=1
    )
    return Ekin


def maxwell_boltzmann(masses, T, replicas=1):
    natoms = len(masses)
    velocities = []
    for i in range(replicas):
        velocities.append(
            paddle.sqrt(T * BOLTZMAN / masses)
            * paddle.randn((natoms, 3)).astype(masses.dtype)
        )

    return paddle.stack(velocities, axis=0)


def kinetic_to_temp(Ekin, natoms):
    return 2.0 / (3.0 * natoms * BOLTZMAN) * Ekin


def _first_VV(pos, vel, force, mass, dt):
    accel = force / mass
    pos += vel * dt + 0.5 * accel * dt * dt
    vel += 0.5 * dt * accel


def _second_VV(vel, force, mass, dt):
    accel = force / mass
    vel += 0.5 * dt * accel


def langevin(vel, gamma, coeff, dt):
    #     csi = paddle.randn_like(vel, device=device) * coeff
    csi = paddlerandn_like(vel) * coeff
    vel += -gamma * vel * dt + csi


PICOSEC2TIMEU = 1000.0 / TIMEFACTOR


class Integrator:
    def __init__(
        self, systems, forces, timestep, device=None, gamma=None, T=None
    ):  # 临时用device=None
        self.dt = timestep / TIMEFACTOR
        self.systems = systems
        self.forces = forces
        #         self.device = device
        gamma = gamma / PICOSEC2TIMEU
        self.gamma = gamma
        self.T = T
        if T:
            M = self.forces.par.masses
            self.vcoeff = paddle.sqrt(2.0 * gamma / M * BOLTZMAN * T * self.dt)

    def step(self, niter=1):
        s = self.systems
        masses = self.forces.par.masses
        natoms = len(masses)
        for _ in range(niter):
            _first_VV(s.pos, s.vel, s.forces, masses, self.dt)
            pot = self.forces.compute(s.pos, s.box, s.forces)
            if self.T:
                langevin(s.vel, self.gamma, self.vcoeff, self.dt)
            _second_VV(s.vel, s.forces, masses, self.dt)

        Ekin = np.array([v.item() for v in kinetic_energy(masses, s.vel)])
        T = kinetic_to_temp(Ekin, natoms)
        return Ekin, pot, T
