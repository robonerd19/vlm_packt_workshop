#!/usr/bin/env python3
"""Generate the industrial plant world and its sign/gauge textures.

Run from anywhere: python3 scripts/make_world.py
Writes src/spot_inspection_sim/worlds/industrial_plant.sdf and worlds/textures/*.png.
Robot spawns at (0, 0) facing +x down the main aisle; inspection stations sit
either side of the aisle (see src/spot_inspection/config/route.yaml).
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / 'src/spot_inspection_sim/worlds'
TEX = OUT / 'textures'


def font(size):
    try:
        return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', size)
    except OSError:
        return ImageFont.load_default(size)


def gauge(name, value, label):
    """Pressure gauge 0-10 bar; green to 6, yellow to 8, red to 10."""
    s = 512
    im = Image.new('RGB', (s, s), (60, 60, 64))
    d = ImageDraw.Draw(im)
    c, r = s // 2, 230
    d.ellipse((c - r, c - r, c + r, c + r), fill=(20, 20, 20))
    r -= 14
    d.ellipse((c - r, c - r, c + r, c + r), fill=(245, 245, 240))
    start, sweep = 135, 270  # PIL angles: clockwise from +x

    def ang(v):
        return start + sweep * v / 10

    for lo, hi, col in ((0, 6, (40, 170, 60)), (6, 8, (240, 200, 0)), (8, 10, (220, 30, 30))):
        d.arc((c - r + 10, c - r + 10, c + r - 10, c + r - 10), ang(lo), ang(hi), fill=col, width=34)
    for v in range(11):
        a = math.radians(ang(v))
        d.line((c + (r - 50) * math.cos(a), c + (r - 50) * math.sin(a),
                c + (r - 10) * math.cos(a), c + (r - 10) * math.sin(a)), fill=(0, 0, 0), width=5)
        d.text((c + (r - 78) * math.cos(a), c + (r - 78) * math.sin(a)), str(v),
               fill=(0, 0, 0), font=font(30), anchor='mm')
    d.text((c, c + 70), 'bar', fill=(0, 0, 0), font=font(34), anchor='mm')
    d.text((c, c + 120), label, fill=(0, 0, 120), font=font(30), anchor='mm')
    a = math.radians(ang(value))
    d.line((c, c, c + (r - 40) * math.cos(a), c + (r - 40) * math.sin(a)), fill=(200, 0, 0), width=14)
    d.ellipse((c - 22, c - 22, c + 22, c + 22), fill=(30, 30, 30))
    im.save(TEX / f'{name}.png')


def sign(name, lines, bg, fg, size=(512, 384), stripe=None):
    im = Image.new('RGB', size, bg)
    d = ImageDraw.Draw(im)
    if stripe:
        d.rectangle((0, 0, size[0] - 1, size[1] - 1), outline=stripe, width=24)
    y = size[1] // 2 - 60 * (len(lines) - 1) // 2
    for text in lines:
        d.text((size[0] // 2, y), text, fill=fg, font=font(64 if len(text) < 10 else 46), anchor='mm')
        y += 60
    im.save(TEX / f'{name}.png')


def floor():
    im = Image.new('RGB', (512, 512), (128, 128, 124))
    d = ImageDraw.Draw(im)
    for i in range(0, 512, 128):  # concrete slab joints
        d.line((i, 0, i, 512), fill=(100, 100, 96), width=3)
        d.line((0, i, 512, i), fill=(100, 100, 96), width=3)
    im.save(TEX / 'concrete.png')


# --- SDF helpers -------------------------------------------------------------

def mat(rgb, tex=None, emissive=None):
    r, g, b = rgb
    out = f'<material><ambient>{r} {g} {b} 1</ambient><diffuse>{r} {g} {b} 1</diffuse>'
    if emissive:
        out += f'<emissive>{emissive}</emissive>'
    if tex:
        out += f'<pbr><metal><albedo_map>textures/{tex}.png</albedo_map></metal></pbr>'
    return out + '</material>'


def link_geom(geom, rgb, tex=None, collide=True, emissive=None, pose='0 0 0 0 0 0'):
    col = f'<collision name="c"><pose>{pose}</pose><geometry>{geom}</geometry></collision>' if collide else ''
    return (f'<visual name="v"><pose>{pose}</pose><geometry>{geom}</geometry>{mat(rgb, tex, emissive)}</visual>'
            + col)


def model(name, pose, geom, rgb, tex=None, collide=True, emissive=None):
    return (f'<model name="{name}"><static>true</static><pose>{pose}</pose><link name="l">'
            f'{link_geom(geom, rgb, tex, collide, emissive)}</link></model>\n')


def box(name, pose, size, rgb, tex=None, collide=True, emissive=None):
    return model(name, pose, f'<box><size>{size}</size></box>', rgb, tex, collide, emissive)


def cyl(name, pose, radius, length, rgb, collide=True):
    return model(name, pose, f'<cylinder><radius>{radius}</radius><length>{length}</length></cylinder>', rgb,
                 collide=collide)


def plate(name, x, y, z, yaw, w, h, tex):
    """Flat textured panel facing direction yaw (normal along local +x)."""
    # A box's +x face shows the texture; rotate so it faces the aisle.
    return box(name, f'{x} {y} {z} 0 0 {yaw}', f'0.02 {w} {h}', (1, 1, 1), tex, collide=False)


STEEL = (0.55, 0.57, 0.6)
PIPE_GREEN = (0.15, 0.45, 0.2)
PIPE_YELLOW = (0.85, 0.7, 0.1)
SAFETY_RED = (0.75, 0.05, 0.05)


def pipe_rack(prefix, x, y, facing):
    """Vertical pipe with a gauge tee, mounted on a back panel. facing: +1 faces -y, -1 faces +y."""
    back = y + 0.35 * facing
    s = box(f'{prefix}_backplate', f'{x} {back} 1.2 0 0 0', '1.6 0.06 2.4', STEEL)
    s += cyl(f'{prefix}_pipe_v', f'{x - 0.55} {y + 0.15 * facing} 1.5 0 0 0', 0.09, 3.0, PIPE_GREEN)
    s += cyl(f'{prefix}_pipe_h', f'{x} {y + 0.15 * facing} 2.4 0 1.5708 0', 0.09, 1.6, PIPE_GREEN)
    return s


def build():
    TEX.mkdir(parents=True, exist_ok=True)
    floor()
    gauge('gauge_overpressure', 9.2, 'BOILER FEED')
    gauge('gauge_normal', 3.8, 'COOLING LOOP')
    sign('sign_high_voltage', ['DANGER', 'HIGH VOLTAGE'], (255, 210, 0), (0, 0, 0), stripe=(0, 0, 0))
    sign('sign_extinguisher', ['FIRE', 'EXTINGUISHER'], (200, 0, 0), (255, 255, 255))
    sign('sign_exit', ['EMERGENCY', 'EXIT'], (0, 140, 60), (255, 255, 255))
    sign('sign_hard_hat', ['HARD HAT', 'AREA'], (0, 70, 160), (255, 255, 255))
    sign('sign_station', ['PUMP', 'STATION 3'], (240, 240, 240), (0, 0, 0), stripe=(0, 70, 160))

    m = ''
    # Hall: 32 x 18 m, 7 m high
    m += model('floor', '11 0 0 0 0 0', '<box><size>32 18 0.02</size></box>', (0.5, 0.5, 0.5), 'concrete')
    for name, pose, size in (('wall_n', '11 9 3.5', '32 0.2 7'), ('wall_s', '11 -9 3.5', '32 0.2 7'),
                             ('wall_w', '-5 0 3.5', '0.2 18 7'), ('wall_e', '27 0 3.5', '0.2 18 7')):
        m += box(name, pose + ' 0 0 0', size, (0.72, 0.72, 0.68))
    # Yellow walkway lines along the main aisle
    for side in (1, -1):
        m += box(f'aisle_line_{side}', f'11 {1.6 * side} 0.012 0 0 0', '30 0.1 0.005', (0.95, 0.8, 0.0),
                 collide=False)
    # Overhead pipe runs and roof beams for atmosphere
    for i, (y, rgb) in enumerate(((7.6, PIPE_GREEN), (7.1, PIPE_YELLOW), (-7.6, (0.6, 0.1, 0.1)), (-7.1, STEEL))):
        m += cyl(f'overhead_pipe_{i}', f'11 {y} 4.2 0 1.5708 0', 0.15, 31.5, rgb, collide=False)
    for i, x in enumerate(range(-3, 27, 5)):
        m += box(f'roof_beam_{i}', f'{x} 0 6.7 0 0 0', '0.3 18 0.4', (0.35, 0.35, 0.38), collide=False)
    # Storage tanks along both walls
    for i, x in enumerate((-1, 6, 13)):
        m += cyl(f'tank_n_{i}', f'{x} 6.6 2.2 0 0 0', 1.4, 4.4, (0.82, 0.82, 0.8))
    for i, x in enumerate((2, 24)):
        m += cyl(f'tank_s_{i}', f'{x} -6.6 2.2 0 0 0', 1.4, 4.4, (0.25, 0.4, 0.65))
    m += plate('sign_hard_hat', -4.88, 0, 2.2, 0, 1.2, 0.9, 'sign_hard_hat')

    # S1 (x=4, north side): boiler feed gauge reading in the red zone
    m += pipe_rack('s1', 4, 2.4, 1)
    m += plate('s1_gauge', 4, 2.4, 1.1, -1.5708, 0.55, 0.55, 'gauge_overpressure')
    m += plate('s1_label', 4.75, 2.4, 1.75, -1.5708, 0.45, 0.34, 'sign_station')

    # S2 (x=8, south side): cooling loop gauge in the green
    m += pipe_rack('s2', 8, -2.4, -1)
    m += plate('s2_gauge', 8, -2.4, 1.1, 1.5708, 0.55, 0.55, 'gauge_normal')

    # S3 (x=12, north side): leaking flange with a water puddle spreading into the aisle
    m += cyl('s3_pipe', '12 2.6 0.9 0 1.5708 0', 0.16, 3.0, PIPE_GREEN)
    m += cyl('s3_flange', '12 2.6 0.9 0 1.5708 0', 0.26, 0.08, STEEL)
    m += cyl('s3_drip', '12 2.4 0.45 0 0 0', 0.02, 0.8, (0.2, 0.45, 0.9), collide=False)
    m += model('s3_puddle', '12 1.6 0.013 0 0 0', '<cylinder><radius>1.0</radius><length>0.004</length></cylinder>',
               (0.15, 0.35, 0.85), collide=False)
    m += box('s3_valve_body', '13.2 2.6 0.9 0 0 0', '0.3 0.4 0.4', SAFETY_RED)
    m += cyl('s3_valve_wheel', '13.2 2.6 1.35 0 0 0', 0.22, 0.04, SAFETY_RED)

    # S4 (x=16, south side): fire extinguisher bracket with the extinguisher missing
    m += box('s4_wall_panel', '16 -2.75 1.2 0 0 0', '1.2 0.06 2.4', (0.85, 0.85, 0.82))
    m += plate('s4_sign', 16, -2.7, 1.85, 1.5708, 0.8, 0.6, 'sign_extinguisher')
    m += box('s4_bracket', '16 -2.65 0.9 0 0 0', '0.25 0.12 0.06', (0.15, 0.15, 0.15))
    m += box('s4_outline', '16 -2.71 0.9 0 0 0', '0.32 0.01 0.7', (0.95, 0.95, 0.95), collide=False)
    # A correctly stocked reference extinguisher further along the wall
    m += cyl('ref_extinguisher', '18.5 -2.6 0.45 0 0 0', 0.09, 0.6, SAFETY_RED)
    m += plate('ref_extinguisher_sign', 18.5, -2.7, 1.5, 1.5708, 0.5, 0.375, 'sign_extinguisher')

    # S5 (x=20, north side): electrical cabinet with its door swung open, breakers and wiring exposed
    m += box('s5_cabinet', '20 2.75 1.0 0 0 0', '1.2 0.5 2.0', (0.6, 0.62, 0.66))
    m += box('s5_cabinet_inside', '20 2.49 1.0 0 0 0', '1.0 0.02 1.7', (0.1, 0.1, 0.12), collide=False)
    for i, z in enumerate((0.6, 0.9, 1.2, 1.5)):
        m += box(f's5_breaker_{i}', f'20 2.46 {z} 0 0 0', '0.8 0.05 0.14', (1.0, 0.45, 0.0), collide=False)
    for i, (dx, rgb) in enumerate(((-0.3, (0.9, 0.1, 0.1)), (-0.1, (0.1, 0.2, 0.9)), (0.15, (0.95, 0.85, 0.0)))):
        m += cyl(f's5_wire_{i}', f'{20 + dx} 2.43 0.55 0 0 0', 0.02, 0.9, rgb, collide=False)
    m += box('s5_door_open', '19.4 2.0 1.0 0 0 1.5708', '1.0 0.04 1.7', (0.6, 0.62, 0.66))
    m += box('s5_door_handle', '19.37 1.65 1.0 0 0 0', '0.04 0.04 0.25', (0.1, 0.1, 0.1), collide=False)
    m += plate('s5_sign', 20.3, 2.47, 1.82, -1.5708, 0.5, 0.375, 'sign_high_voltage')
    # Control: an identical cabinet, closed, out of S5's view
    m += box('ctrl_cabinet', '17.0 2.75 1.0 0 0 0', '1.2 0.5 2.0', (0.6, 0.62, 0.66))
    m += box('ctrl_cabinet_handle', '17.45 2.49 1.0 0 0 0', '0.04 0.04 0.25', (0.1, 0.1, 0.1), collide=False)
    m += plate('ctrl_sign', 17.0, 2.49, 1.82, -1.5708, 0.5, 0.375, 'sign_high_voltage')

    # S6 (east wall): emergency exit blocked by stacked boxes on a pallet
    m += box('s6_exit_door', '26.88 0 1.1 0 0 0', '0.06 1.6 2.2', (0.3, 0.35, 0.4))
    m += plate('s6_exit_sign', 26.86, 0, 2.6, 3.1416, 1.0, 0.75, 'sign_exit')
    m += box('s6_pallet', '25.6 0 0.07 0 0 0', '1.2 1.2 0.14', (0.6, 0.45, 0.25))
    for i, (dy, z) in enumerate(((-0.3, 0.44), (0.3, 0.44), (0.0, 1.04))):
        m += box(f's6_box_{i}', f'25.6 {dy} {z} 0 0 0', '0.6 0.6 0.6', (0.7, 0.55, 0.35))

    lights = ''.join(
        f'<light type="point" name="lamp_{i}"><pose>{x} {y} 6.2 0 0 0</pose><diffuse>0.9 0.9 0.85 1</diffuse>'
        f'<specular>0.1 0.1 0.1 1</specular><attenuation><range>14</range><constant>0.4</constant>'
        f'<linear>0.03</linear><quadratic>0.002</quadratic></attenuation><cast_shadows>false</cast_shadows></light>\n'
        for i, (x, y) in enumerate((x, y) for x in range(0, 27, 6) for y in (-4, 4)))

    sdf = f'''<?xml version="1.0"?>
<!-- Generated by scripts/make_world.py; edit the generator, not this file. -->
<sdf version="1.9">
<world name="industrial_plant">
  <physics name="1ms" type="ignored"><max_step_size>0.001</max_step_size><real_time_factor>1.0</real_time_factor></physics>
  <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
  <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
  <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
  <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
  <plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu"/>
  <scene><ambient>0.55 0.55 0.55 1</ambient><background>0.3 0.3 0.32 1</background><shadows>false</shadows></scene>
  <gravity>0 0 -9.81</gravity>
  <light type="directional" name="sun"><cast_shadows>false</cast_shadows><pose>0 0 10 0 0 0</pose>
    <diffuse>0.6 0.6 0.6 1</diffuse><specular>0.1 0.1 0.1 1</specular><direction>-0.3 0.2 -0.9</direction></light>
{lights}
{m}
</world>
</sdf>
'''
    (OUT / 'industrial_plant.sdf').write_text(sdf)
    print('wrote', OUT / 'industrial_plant.sdf')


if __name__ == '__main__':
    build()
