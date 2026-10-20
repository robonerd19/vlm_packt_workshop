"""Bounded viewpoints in the connected, clearance-safe part of a known map."""
import math
import cv2
import numpy as np


def viewpoints(grid, resolution, origin, robot_xy, spacing=3.0, clearance=0.45, limit=3):
    # Unknown cells and map edges are obstacles. Inflate before connectivity:
    # a visually free cell beyond a narrow doorway is not a valid candidate.
    free = np.pad((np.asarray(grid) == 0).astype(np.uint8), 1)
    distance = cv2.distanceTransform(free, cv2.DIST_L2, 5)[1:-1, 1:-1] * resolution
    safe = (distance >= clearance).astype(np.uint8)
    x, y, yaw = origin
    c, s = math.cos(yaw), math.sin(yaw)
    delta = np.asarray(robot_xy) - [x, y]
    col = int(math.floor((c*delta[0]+s*delta[1])/resolution))
    row = int(math.floor((-s*delta[0]+c*delta[1])/resolution))
    if not (0 <= row < safe.shape[0] and 0 <= col < safe.shape[1]) or not safe[row, col]:
        return []
    _, labels = cv2.connectedComponents(safe, connectivity=4)
    connected = labels == labels[row, col]
    step = max(1, math.ceil(spacing/resolution))
    rows, cols = np.nonzero(connected[::step, ::step])
    local = np.column_stack(((cols*step+0.5)*resolution, (rows*step+0.5)*resolution))
    points = local @ np.array([[c, s], [-s, c]]) + [x, y]
    selected, previous = [], np.asarray(robot_xy)
    for _ in range(limit):
        if not len(points):
            break
        separation = np.linalg.norm(points - np.asarray(robot_xy), axis=1) >= spacing
        for point in selected:
            separation &= np.linalg.norm(points-point, axis=1) >= spacing
        points = points[separation]
        if not len(points):
            break
        point = points[np.argmin(np.linalg.norm(points-previous, axis=1))]
        selected.append(point)
        previous = point
    return [tuple(map(float, point)) for point in selected]
