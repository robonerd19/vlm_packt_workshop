#!/usr/bin/env python3
"""Rasterize static collision footprints from the warehouse SDF into a map."""

from __future__ import annotations

import argparse
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORLD = ROOT / "src/go2_warehouse_world/worlds/warehouse.sdf"
DEFAULT_MODELS = ROOT / "src/go2_warehouse_world/models"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "maps/warehouse"


def pose_values(element: ET.Element | None) -> tuple[float, float, float, float, float, float]:
    if element is None or not (element.text or "").strip():
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    vals = [float(v) for v in (element.text or "").split()]
    return tuple((vals + [0.0] * 6)[:6])  # type: ignore[return-value]


def compose_pose(parent, child):
    px, py, pz, pr, pp, pyaw = parent
    x, y, z, r, p, yaw = child
    return (
        px + math.cos(pyaw) * x - math.sin(pyaw) * y,
        py + math.sin(pyaw) * x + math.cos(pyaw) * y,
        pz + z,
        pr + r,
        pp + p,
        pyaw + yaw,
    )


def rotate_translate(x, y, pose):
    return (
        pose[0] + math.cos(pose[5]) * x - math.sin(pose[5]) * y,
        pose[1] + math.sin(pose[5]) * x + math.cos(pose[5]) * y,
    )


def dae_collision(dae: Path, scale=(1.0, 1.0, 1.0)):
    root = ET.parse(dae).getroot()
    unit_element = root.find("{*}asset/{*}unit")
    unit = float("1" if unit_element is None else unit_element.get("meter", "1"))
    # Scene-node <matrix> transforms (e.g. the shelves' collision meshes are stored rotated), per geometry id.
    node_matrices = {}

    def walk(node, parent):
        matrix = parent
        text = node.findtext("{*}matrix")
        if text:
            m = [float(v) for v in text.split()]
            local = [m[0:4], m[4:8], m[8:12], m[12:16]]
            matrix = [[sum(parent[r][k] * local[k][c] for k in range(4)) for c in range(4)] for r in range(4)]
        for instance in node.findall("{*}instance_geometry"):
            node_matrices[instance.get("url", "")[1:]] = matrix
        for child in node.findall("{*}node"):
            walk(child, matrix)

    identity = [[float(r == c) for c in range(4)] for r in range(4)]
    for scene in root.findall(".//{*}visual_scene"):
        for node in scene.findall("{*}node"):
            walk(node, identity)

    triangles = []
    all_points = []
    for geometry in root.findall(".//{*}geometry"):
        m = node_matrices.get(geometry.get("id", ""), identity)
        position_sources = {}
        for source in geometry.findall(".//{*}source"):
            if "POSITION" in source.get("id", ""):
                array = source.find("{*}float_array")
                if array is not None and array.text:
                    vals = [float(v) for v in array.text.split()]
                    position_sources["#" + source.get("id", "")] = [
                        tuple(
                            (m[r][0] * vals[i] + m[r][1] * vals[i + 1] + m[r][2] * vals[i + 2] + m[r][3]) * unit * scale[r]
                            for r in range(3)
                        )
                        for i in range(0, len(vals), 3)
                    ]
        for primitive in geometry.findall(".//{*}triangles"):
            inputs = primitive.findall("{*}input")
            vertex_input = next((i for i in inputs if i.get("semantic") == "VERTEX"), None)
            if vertex_input is None:
                continue
            vertices_node = root.find(f".//{{*}}vertices[@id='{vertex_input.get('source', '')[1:]}']")
            position_input = None if vertices_node is None else next(
                (i for i in vertices_node.findall("{*}input") if i.get("semantic") == "POSITION"), None
            )
            if position_input is None:
                continue
            vertices = position_sources.get(position_input.get("source", ""))
            packed = primitive.find("{*}p")
            if not vertices or packed is None or not packed.text:
                continue
            stride = max(int(i.get("offset", "0")) for i in inputs) + 1
            vertex_offset = int(vertex_input.get("offset", "0"))
            indices = [int(v) for v in packed.text.split()]
            for i in range(0, len(indices), 3 * stride):
                tri = [vertices[indices[i + j * stride + vertex_offset]] for j in range(3)]
                triangles.append(tri)
                all_points.extend(tri)

    if not all_points:
        raise ValueError(f"No collision triangles found in {dae}")
    return triangles, all_points


def collision_footprints(model_dir: Path):
    model = ET.parse(model_dir / "model.sdf").getroot().find(".//{*}model")
    if model is None:
        raise ValueError(f"No model in {model_dir / 'model.sdf'}")
    footprints = []
    for link in model.findall("{*}link"):
        link_pose = pose_values(link.find("{*}pose"))
        for collision in link.findall("{*}collision"):
            local_pose = compose_pose(link_pose, pose_values(collision.find("{*}pose")))
            geometry = collision.find("{*}geometry")
            if geometry is None:
                continue
            mesh = geometry.find("{*}mesh")
            if mesh is not None:
                uri = (mesh.findtext("{*}uri") or "").strip()
                match = re.match(r"model://[^/]+/(.+)", uri)
                if not match:
                    raise ValueError(f"Unsupported collision mesh URI: {uri}")
                scale_node = mesh.findtext("{*}scale", default="1 1 1").split()
                scale = tuple(float(v) for v in scale_node[:3])
                triangles, points = dae_collision(model_dir / match.group(1), scale)
                if min(p[2] for p in points) + local_pose[2] > 2.0:
                    continue  # overhead geometry (ceiling lamps) cannot block the robot
                points_xy = [rotate_translate(p[0], p[1], local_pose) for p in points]
                bounds = (
                    min(x for x, _ in points_xy), min(y for _, y in points_xy),
                    max(x for x, _ in points_xy), max(y for _, y in points_xy),
                )
                world_triangles = [
                    [rotate_translate(p[0], p[1], local_pose) for p in tri] for tri in triangles
                ]
                footprints.append(("mesh", bounds, world_triangles, local_pose[2]))
            else:
                box = geometry.find("{*}box/{*}size")
                if box is None:
                    continue
                sx, sy, sz = (float(v) for v in box.text.split()[:3])
                corners = [rotate_translate(x, y, local_pose) for x in (-sx / 2, sx / 2) for y in (-sy / 2, sy / 2)]
                bounds = (
                    min(x for x, _ in corners), min(y for _, y in corners),
                    max(x for x, _ in corners), max(y for _, y in corners),
                )
                footprints.append(("box", bounds, corners, local_pose[2]))
    return footprints


def fill_polygon(mask, width, height, origin_x, origin_y, resolution, polygon):
    # Convert world XY coordinates to image coordinates (rows grow down).
    points = [((x - origin_x) / resolution, height - (y - origin_y) / resolution) for x, y in polygon]
    min_col = max(0, int(math.floor(min(p[0] for p in points))) - 1)
    max_col = min(width - 1, int(math.ceil(max(p[0] for p in points))) + 1)
    min_row = max(0, int(math.floor(min(p[1] for p in points))) - 1)
    max_row = min(height - 1, int(math.ceil(max(p[1] for p in points))) + 1)
    area = 0.0
    if len(points) >= 3:
        area = abs(sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points)))) / 2
    if area < 0.01:
        # Vertical wall triangles collapse to lines in a 2D projection.
        for row in range(min_row, max_row + 1):
            cy = row + 0.5
            for col in range(min_col, max_col + 1):
                cx = col + 0.5
                distance = min(
                    point_segment_distance(cx, cy, points[i], points[(i + 1) % len(points)])
                    for i in range(len(points))
                )
                if distance <= 1.5:
                    mask[row * width + col] = 1
        return

    for row in range(min_row, max_row + 1):
        cy = row + 0.5
        for col in range(min_col, max_col + 1):
            cx = col + 0.5
            inside = False
            j = len(points) - 1
            for i in range(len(points)):
                xi, yi = points[i]
                xj, yj = points[j]
                if ((yi > cy) != (yj > cy)) and cx < (xj - xi) * (cy - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
            if inside:
                mask[row * width + col] = 1


def point_segment_distance(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / length2))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--models", type=Path, default=DEFAULT_MODELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resolution", type=float, default=0.05)
    args = parser.parse_args()

    world = ET.parse(args.world).getroot().find("{*}world")
    if world is None:
        raise ValueError(f"No world element in {args.world}")

    instances = []
    floor_bounds = None
    for instance in world.findall("{*}model"):
        include = instance.find("{*}include/{*}uri")
        if include is None or not (include.text or "").strip().startswith("model://"):
            continue
        model_name = include.text.strip().removeprefix("model://")
        model_name = model_name.split("/")[0]
        model_dir = args.models / model_name
        model_pose = pose_values(instance.find("{*}pose"))
        if model_pose[2] < -1.0:
            continue
        for kind, bounds, triangles_or_corners, z in collision_footprints(model_dir):
            if "GroundB" in model_name:
                corners = [
                    rotate_translate(x, y, model_pose)
                    for x in (bounds[0], bounds[2])
                    for y in (bounds[1], bounds[3])
                ]
                floor_bounds = (
                    min(x for x, _ in corners), min(y for _, y in corners),
                    max(x for x, _ in corners), max(y for _, y in corners),
                )
                continue
            if "WallB" in model_name and kind == "mesh":
                # Preserve the wall layout and openings by rasterizing the
                # actual mesh triangles rather than its whole-room bounding box.
                for tri in triangles_or_corners:
                    transformed = [rotate_translate(x, y, model_pose) for x, y in tri]
                    instances.append(("triangle", transformed))
            else:
                x0, y0, x1, y1 = bounds
                corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                transformed = [rotate_translate(x, y, model_pose) for x, y in corners]
                instances.append(("polygon", transformed))

    if floor_bounds is None:
        raise ValueError("Could not derive map bounds from the warehouse GroundB collision")
    min_x, min_y, max_x, max_y = floor_bounds
    resolution = args.resolution
    width = math.ceil((max_x - min_x) / resolution)
    height = math.ceil((max_y - min_y) / resolution)
    mask = bytearray(width * height)
    for kind, footprint in instances:
        if kind == "triangle":
            fill_polygon(mask, width, height, min_x, min_y, resolution, footprint)
        else:
            fill_polygon(mask, width, height, min_x, min_y, resolution, footprint)

    args.output.mkdir(parents=True, exist_ok=True)
    image = args.output / "warehouse.pgm"
    # Map server convention: white is free and black is occupied.
    pixels = bytes(0 if value else 254 for value in mask)
    image.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + pixels)
    metadata = args.output / "warehouse.yaml"
    metadata.write_text(
        "image: warehouse.pgm\n"
        f"resolution: {resolution:.3f}\n"
        f"origin: [{min_x:.6f}, {min_y:.6f}, 0.0]\n"
        "negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\nmode: trinary\n"
    )
    print(f"Generated {image} from {len(instances)} world collision footprints ({width} x {height} cells)")


if __name__ == "__main__":
    main()
