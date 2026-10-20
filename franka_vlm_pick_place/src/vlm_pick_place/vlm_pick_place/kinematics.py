"""Panda forward/inverse kinematics read from the URDF itself, independent of ROS."""
import math
import xml.etree.ElementTree as ET

import numpy as np

TCP_OFFSET = 0.1034  # panda_hand origin to the fingertip centre along hand z.


def rpy_matrix(r, p, y):
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return np.array([[cy*cp, cy*sp*sr - sy*cr, cy*sp*cr + sy*sr],
                     [sy*cp, sy*sp*sr + cy*cr, sy*sp*cr - cy*sr],
                     [-sp, cp*sr, cp*cr]])


def transform(xyz, rpy):
    t = np.eye(4)
    t[:3, :3] = rpy_matrix(*rpy)
    t[:3, 3] = xyz
    return t


def axis_rotation(axis, angle):
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    t = np.eye(4)
    t[:3, :3] = np.eye(3) + math.sin(angle)*k + (1 - math.cos(angle))*k @ k
    return t


class PandaKinematics:
    def __init__(self, urdf_text, base='panda_link0', tip='panda_hand'):
        joints = {}
        for j in ET.fromstring(urdf_text).iter('joint'):
            origin = j.find('origin')
            xyz = [float(v) for v in (origin.get('xyz', '0 0 0') if origin is not None else '0 0 0').split()]
            rpy = [float(v) for v in (origin.get('rpy', '0 0 0') if origin is not None else '0 0 0').split()]
            axis = j.find('axis')
            limit = j.find('limit')
            joints[j.find('child').get('link')] = dict(
                name=j.get('name'), type=j.get('type'), parent=j.find('parent').get('link'),
                origin=transform(xyz, rpy),
                axis=np.array([float(v) for v in axis.get('xyz').split()]) if axis is not None else None,
                limits=(float(limit.get('lower', 0)), float(limit.get('upper', 0))) if limit is not None else None)
        chain, link = [], tip
        while link != base:
            if link not in joints:
                raise ValueError(f'No joint chain from {base} to {tip}.')
            chain.append(joints[link])
            link = joints[link]['parent']
        self.chain = chain[::-1]
        movable = [j for j in self.chain if j['type'] == 'revolute']
        self.joint_names = [j['name'] for j in movable]
        self.lower = np.array([j['limits'][0] for j in movable])
        self.upper = np.array([j['limits'][1] for j in movable])

    def forward(self, q):
        """Return the 4x4 TCP pose in the base frame for 7 joint angles."""
        t, i = np.eye(4), 0
        for j in self.chain:
            t = t @ j['origin']
            if j['type'] == 'revolute':
                t = t @ axis_rotation(j['axis'], q[i])
                i += 1
        return t @ transform([0, 0, TCP_OFFSET], [0, 0, 0])

    def inverse(self, position, rotation, seed, iterations=300, tolerance=1e-4):
        """Damped least-squares IK for a full TCP pose; raises if unreachable."""
        q = np.clip(np.array(seed, dtype=float), self.lower, self.upper)
        for _ in range(iterations):
            error = self._error(q, position, rotation)
            if np.linalg.norm(error) < tolerance:
                return q
            jac = np.zeros((6, 7))
            for i in range(7):
                dq = q.copy()
                dq[i] += 1e-6
                jac[:, i] = (error - self._error(dq, position, rotation)) / 1e-6
            step = jac.T @ np.linalg.solve(jac @ jac.T + 1e-4*np.eye(6), error)
            q = np.clip(q + np.clip(step, -0.2, 0.2), self.lower, self.upper)
        raise ValueError(f'IK did not converge for position {np.round(position, 3).tolist()}.')

    def _error(self, q, position, rotation):
        t = self.forward(q)
        r = rotation @ t[:3, :3].T
        # Rotation-vector error from the skew part; adequate near convergence.
        w = 0.5*np.array([r[2, 1]-r[1, 2], r[0, 2]-r[2, 0], r[1, 0]-r[0, 1]])
        return np.concatenate([np.asarray(position) - t[:3, 3], w])


def top_down(yaw=0.0):
    """TCP orientation pointing straight down, fingers closing along world y at yaw 0."""
    return rpy_matrix(math.pi, 0.0, 0.0) @ rpy_matrix(0.0, 0.0, -yaw)
