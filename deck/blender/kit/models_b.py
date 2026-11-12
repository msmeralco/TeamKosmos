"""Sol kit, part B: nature, street furniture, vehicles, people."""
import math, random
from voxlib import Vox, rgb, FONT

GREENS = ['#4c9a3c', '#5fb04a', '#3f8a37', '#6bbd52']
LEAF_HI = 1.14


def _top_light(m, k=LEAF_HI):
    for p, c in list(m.v.items()):
        if (p[0], p[1], p[2] + 1) not in m.v:
            m.v[p] = (min(c[0] * k, 1), min(c[1] * k, 1), min(c[2] * k, 1))


def wheel(m, cx, cz, y0, y1, r, tire='#23262b', hub='#c9ced4'):
    for x in range(int(cx - r - 1), int(cx + r + 2)):
        for z in range(int(cz - r - 1), int(cz + r + 2)):
            d = math.hypot(x + .5 - cx, z + .5 - cz)
            if d <= r:
                for y in range(y0, y1):
                    m.set(x, y, z, hub if d <= r * 0.45 and y in (y0, y1 - 1) else tire, 0.02)


def palm(name='palm_a', seed=1, h=34, lean=3):
    r = random.Random(seed)
    m = Vox(name, seed)
    pts = []
    for z in range(h):
        k = z / h
        x = int(lean * k * k * 1.5)
        y = int(math.sin(k * 3 + seed) * 1.2)
        pts.append((x, y))
        c = '#9b7a55' if z % 3 else '#85653f'
        if z < h - 8:
            m.box(x - 1, y - 1, z, x + 1, y + 1, z + 1, c, 0.04)
        else:
            m.set(x, y, z, c, 0.04)
    tx, ty = pts[-1][0], pts[-1][1]
    for dx in (0, 1):
        for dy in (0, 1):
            m.set(tx + dx - 1, ty + dy - 1, h, '#6e5636', 0.05)
    n = 9
    for i in range(n):
        a = i / n * math.tau + r.random() * 0.3
        L = 15 + r.randint(0, 3)
        for t in range(L):
            x = tx + math.cos(a) * t
            y = ty + math.sin(a) * t
            z = h + 3 + t * 0.55 - t * t * 0.052
            c = r.choice(['#3f8f3e', '#4fa447', '#5bb34d', '#37803a'])
            m.set(x, y, z, c, 0.05)
            # leaflets droop either side
            px, py = -math.sin(a), math.cos(a)
            wlen = 3 if 2 < t < L - 3 else 1
            for s in range(1, wlen + 1):
                for sg in (-1, 1):
                    m.set(x + px * s * sg, y + py * s * sg, z - s * 0.6, c, 0.06)
    for k in range(3):
        m.ball(tx - 1 + (k % 2) * 3 - 1, ty + (k // 2) * 3 - 1, h - 2, 1.6, c='#6a4a2c', j=0.05)
    return m


def round_tree(name='mango_a', seed=1, h=11, R=10, greens=GREENS, flower=None):
    r = random.Random(seed)
    m = Vox(name, seed)
    m.box(-1, -1, 0, 2, 2, h, '#7a5a3a', 0.06)
    m.box(-2, -2, 0, 3, 3, 2, '#7a5a3a', 0.06)
    m.line((0, 0, h - 3), (-6, 1, h + 3), '#6e4e30', 0.04, r=0)
    m.line((1, 1, h - 3), (7, -1, h + 2), '#6e4e30', 0.04, r=0)
    for i, (dx, dy, dz, k) in enumerate([(0, 0, h + 6, 1.0), (-6, 2, h + 3, .75), (7, -1, h + 3, .78), (1, 6, h + 4, .7), (-1, -6, h + 4, .7)]):
        m.ball(dx, dy, dz, R * k, R * k * .95, R * k * .8, c=greens, j=0.06, keep=0.97, seed=seed + i)
    if flower:
        for p in list(m.v):
            if (p[0], p[1], p[2] + 1) not in m.v and r.random() < 0.35:
                m.set(*p, r.choice(flower), 0.05)
    _top_light(m)
    return m


def banana(name='banana', seed=1):
    r = random.Random(seed)
    m = Vox(name, seed)
    m.box(-1, -1, 0, 1, 1, 12, '#86b04a', 0.05)
    for i in range(7):
        a = i / 7 * math.tau + r.random() * .4
        for t in range(1, 11):
            x, y = math.cos(a) * t, math.sin(a) * t
            z = 12 + t * .5 - t * t * .09
            for s in (-1, 0, 1):
                m.set(x - math.sin(a) * s, y + math.cos(a) * s, z - abs(s) * .5, r.choice(['#5ea83e', '#6fbb4a', '#4f9636']), 0.06)
    m.ball(3, 0, 6, 1.6, 2.2, 2.2, c='#d6c43a', j=0.05)
    return m


def bush(name='bush', seed=1, flower=None):
    r = random.Random(seed)
    m = Vox(name, seed)
    for i in range(3):
        m.ball(i * 4 - 4, r.randint(-1, 1), 3, 4.4, 4, 3.4, c=GREENS, j=0.07, keep=0.97, seed=seed + i)
    if flower:
        for p in list(m.v):
            if (p[0], p[1], p[2] + 1) not in m.v and r.random() < 0.4:
                m.set(*p, r.choice(flower), 0.04)
    _top_light(m)
    return m


def lamp_post(name='lamp'):
    m = Vox(name, 3)
    m.box(-1, -1, 0, 2, 2, 2, '#4a4f57', 0.02)
    m.box(0, 0, 2, 1, 1, 30, '#59606a', 0.02)
    m.box(0, 0, 29, 1, 9, 30, '#59606a', 0.02)
    m.box(-1, 7, 28, 3, 11, 29, '#454a52', 0.02)
    m.box(-1, 7, 29, 3, 11, 30, '#c9ced4', 0.02)
    m.box(-1, 7, 27, 3, 11, 28, '#ffffff', 0, emit=True)       # lamp face, lit at night
    return m


def utility_pole(name='pole'):
    """Meralco-style concrete pole. Crossarms run along Y so the wires run along X."""
    m = Vox(name, 4)
    for z in range(64):
        w = 3 if z < 40 else 2
        m.box(-w // 2 - (w % 2 == 0) * 0, -w // 2, z, -w // 2 + w, -w // 2 + w, z + 1, '#a7a399' if z % 8 else '#928e84', 0.03)
    for zz, half in ((60, 11), (52, 9)):
        m.box(-1, -half, zz, 2, half + 1, zz + 2, '#7a756b', 0.03)
        m.box(0, -half - 0, zz - 1, 1, half + 1, zz, '#6b665d', 0.02)
        for y in (-half, -half // 3, half // 3, half):
            m.box(0, y, zz + 2, 1, y + 1, zz + 4, '#d7e6ef', 0)       # insulator
            m.set(0, y, zz + 4, '#7aa1b8', 0)
    # transformer can
    m.disc(3.5, 0.5, 40, 3.5, '#8a8f95', h=9, j=0.03)
    m.disc(3.5, 0.5, 49, 3.5, '#6f747a', h=1, j=0.02)
    m.box(3, 0, 49, 4, 1, 52, '#2b2e33', 0)
    # lamp arm + tags
    m.box(-1, 2, 36, 1, 8, 37, '#59606a', 0.02)
    m.box(-2, 7, 35, 2, 11, 36, '#ffffff', 0, emit=True)
    m.box(-2, 7, 36, 2, 11, 37, '#c9ced4', 0.02)
    m.box(-1, -2, 30, 2, -1, 34, '#e8e2d4', 0.02)      # tag plate
    return m


def jeepney(name='jeepney', body='#f2c230', stripe='#d1342f', stripe2='#2a6fb5', seed=1):
    m = Vox(name, seed)
    L, W = 46, 14
    x0, x1, y0, y1 = -L // 2, L // 2, -W // 2, W // 2
    m.box(x0, y0, 3, x1 - 12, y1, 17, body, 0.03)                 # passenger box
    m.box(x1 - 12, y0, 3, x1, y1, 11, body, 0.03)                 # hood
    m.box(x0 - 1, y0, 3, x0, y1, 6, '#c9ced4', 0)                 # rear bumper
    m.box(x1, y0, 3, x1 + 1, y1, 7, '#c9ced4', 0)                 # front bumper
    m.box(x1, y0 + 2, 7, x1 + 1, y1 - 2, 10, '#2a2d32', 0)        # grille
    for z in (8, 9):
        for y in range(y0 + 2, y1 - 2, 2):
            m.set(x1, y, z, '#e5e8ea', 0)
    # windows band
    for x in range(x0 + 3, x1 - 15):
        if (x - x0) % 6 != 0:
            m.box(x, y0, 10, x + 1, y0 + 1, 15, '#26323d', 0)
            m.box(x, y1 - 1, 10, x + 1, y1, 15, '#26323d', 0)
    m.box(x1 - 14, y0 + 1, 10, x1 - 12, y1 - 1, 15, '#8fc3e0', 0)  # windscreen
    # stripes + decoration
    m.box(x0, y0, 7, x1 - 12, y0 + 1, 9, stripe, 0.02)
    m.box(x0, y1 - 1, 7, x1 - 12, y1, 9, stripe, 0.02)
    m.box(x0, y0, 5, x1 - 12, y0 + 1, 6, stripe2, 0.02)
    m.box(x0, y1 - 1, 5, x1 - 12, y1, 6, stripe2, 0.02)
    m.box(x1 - 12, y0, 6, x1, y0 + 1, 8, stripe, 0.02)
    m.box(x1 - 12, y1 - 1, 6, x1, y1, 8, stripe, 0.02)
    # roof, rack and a sign
    m.box(x0 - 1, y0 - 1, 17, x1 - 13, y1 + 1, 19, '#f3efe4', 0.02)
    for x in range(x0, x1 - 14, 5):
        m.box(x, y0, 19, x + 1, y1, 20, '#444a52', 0)
    m.box(x1 - 20, y0 + 2, 19, x1 - 14, y1 - 2, 22, '#ffffff', 0)
    m.box(x0 + 1, y0, 14, x0 + 2, y1, 17, stripe, 0.02)
    # lights
    m.box(x1, y0 + 1, 8, x1 + 1, y0 + 3, 10, '#ffffff', 0, emit=True)
    m.box(x1, y1 - 3, 8, x1 + 1, y1 - 1, 10, '#ffffff', 0, emit=True)
    m.box(x0 - 1, y0 + 1, 8, x0, y0 + 3, 10, '#d62f2f', 0, emit='g')
    m.box(x0 - 1, y1 - 3, 8, x0, y1 - 1, 10, '#d62f2f', 0, emit='g')
    for cx in (x0 + 7, x1 - 7):
        wheel(m, cx, 3, y0 - 1, y0 + 2, 3.6)
        wheel(m, cx, 3, y1 - 2, y1 + 1, 3.6)
    return m


def tricycle(name='tricycle', body='#d1342f', side='#f2c230', seed=2):
    m = Vox(name, seed)
    m.box(-4, -2, 3, 9, 2, 8, body, 0.03)                        # bike
    m.box(5, -2, 8, 9, 2, 11, body, 0.03)
    m.box(7, -3, 11, 8, 3, 12, '#2a2d32', 0)                     # handlebar
    m.box(-4, -1, 8, 3, 1, 9, '#2a2d32', 0)                       # seat
    m.box(-14, -3, 3, -4, 7, 4, side, 0.03)                        # sidecar floor
    m.box(-14, -3, 4, -4, 7, 10, side, 0.03)
    m.box(-13, -2, 8, -5, 6, 11, '#2d3138', 0)
    m.box(-15, -4, 12, -3, 8, 13, '#f3efe4', 0.02)                 # canopy
    for px, py in ((-14, -3), (-4, -3), (-14, 7), (-4, 7)):
        m.box(px, py, 10, px + 1, py + 1, 12, '#444a52', 0)
    m.box(9, -1, 6, 10, 1, 8, '#ffffff', 0, emit=True)
    wheel(m, 6, 3, -1, 1, 3.4)
    wheel(m, -2, 3, -1, 1, 3.4)
    wheel(m, -9, 3, 7, 9, 3.2)
    return m


def van(name='van', body='#f5f6f4', seed=3, rack=True):
    m = Vox(name, seed)
    L, W = 34, 14
    x0, x1, y0, y1 = -L // 2, L // 2, -W // 2, W // 2
    m.box(x0, y0, 3, x1, y1, 17, body, 0.012)
    m.box(x1 - 9, y0, 3, x1, y1, 10, body, 0.012)                  # nose
    m.clear(x1 - 9, y0, 10, x1, y1, 17)
    for i in range(6):                                              # sloped windscreen
        m.box(x1 - 9 + i, y0, 10 + i, x1 - 8 + i, y1, 11 + i, body, 0.012)
    m.box(x1 - 9, y0 + 1, 10, x1 - 5, y1 - 1, 12, '#8fc3e0', 0)
    # cab side windows
    m.box(x1 - 14, y0, 11, x1 - 9, y0 + 1, 16, '#26323d', 0)
    m.box(x1 - 14, y1 - 1, 11, x1 - 9, y1, 16, '#26323d', 0)
    # sliding door seam and a blank sign panel (a quote you cannot read)
    m.box(x0 + 12, y0, 4, x0 + 13, y0 + 1, 16, '#c9cdd0', 0)
    m.box(x0 + 3, y0, 7, x0 + 11, y0 + 1, 14, '#ffffff', 0)
    m.box(x0 + 3, y0, 7, x0 + 11, y0 + 1, 8, '#e4e7e9', 0)
    m.box(x0 + 3, y1 - 1, 7, x0 + 11, y1, 14, '#ffffff', 0)
    m.box(x0, y0, 3, x1, y1, 5, '#6b7078', 0.02)                    # lower trim
    m.box(x1, y0 + 2, 4, x1 + 1, y1 - 2, 6, '#2a2d32', 0)
    if rack:
        for x in (x0 + 4, x0 + 14, x0 + 22):
            m.box(x, y0 + 1, 17, x + 1, y1 - 1, 19, '#454a52', 0)
        for y in (y0 + 1, y1 - 2):
            m.box(x0 + 3, y, 19, x1 - 6, y + 1, 20, '#454a52', 0)
        m.box(x0 + 2, -2, 20, x1 - 4, -1, 21, '#e0a52c', 0)         # a ladder along the roof
        m.box(x0 + 2, 2, 20, x1 - 4, 3, 21, '#e0a52c', 0)
        for x in range(x0 + 3, x1 - 4, 3):
            m.box(x, -2, 20, x + 1, 3, 21, '#c58b1d', 0)
    m.box(x1, y0 + 1, 7, x1 + 1, y0 + 4, 9, '#ffffff', 0, emit=True)
    m.box(x1, y1 - 4, 7, x1 + 1, y1 - 1, 9, '#ffffff', 0, emit=True)
    m.box(x0 - 1, y0 + 1, 7, x0, y0 + 3, 10, '#d62f2f', 0, emit='g')
    m.box(x0 - 1, y1 - 3, 7, x0, y1 - 1, 10, '#d62f2f', 0, emit='g')
    for cx in (x0 + 7, x1 - 7):
        wheel(m, cx, 3.6, y0 - 1, y0 + 2, 3.8)
        wheel(m, cx, 3.6, y1 - 2, y1 + 1, 3.8)
    return m


def sedan(name='sedan', body='#6c8cb8', seed=4):
    m = Vox(name, seed)
    m.box(-14, -6, 3, 14, 6, 9, body, 0.02)
    m.box(-7, -6, 9, 8, 6, 15, body, 0.02)
    m.box(-6, -6, 10, 7, -5, 14, '#26323d', 0)
    m.box(-6, 5, 10, 7, 6, 14, '#26323d', 0)
    m.box(8, -5, 10, 9, 5, 13, '#8fc3e0', 0)
    m.box(14, -4, 4, 15, 4, 6, '#2a2d32', 0)
    m.box(14, -5, 6, 15, -3, 8, '#ffffff', 0, emit=True)
    m.box(14, 3, 6, 15, 5, 8, '#ffffff', 0, emit=True)
    m.box(-15, -5, 6, -14, -3, 8, '#d62f2f', 0, emit='g')
    m.box(-15, 3, 6, -14, 5, 8, '#d62f2f', 0, emit='g')
    for cx in (-9, 9):
        wheel(m, cx, 3.4, -7, -5, 3.4)
        wheel(m, cx, 3.4, 5, 7, 3.4)
    return m


def person(name='person', shirt='#2f6fb5', pants='#33384a', hair='#2a1d16', skin='#e0ac7c', hat=None, h=1.0):
    m = Vox(name, 5)
    m.box(-1, -1, 0, 0, 0, 4, pants, 0.02)
    m.box(0, -1, 0, 1, 0, 4, pants, 0.02)
    m.box(-1, -1, 4, 1, 0, 8, shirt, 0.03)
    m.set(-2, -1, 6, shirt, 0.03)
    m.set(1, -1, 6, shirt, 0.03)
    m.box(-1, -1, 8, 1, 0, 10, skin, 0.02)
    m.box(-1, -1, 10, 1, 0, 11, hair, 0.03)
    m.set(-1, 0, 9, hair, 0)
    m.set(0, 0, 9, hair, 0)
    if hat:
        m.box(-1, -1, 10, 1, 0, 12, hat, 0.02)
        m.box(-1, -2, 10, 1, -1, 11, hat, 0.02)
    return m


def dog(name='dog', coat='#c58b4a'):
    m = Vox(name, 6)
    m.box(-3, 0, 2, 3, 2, 5, coat, 0.04)
    m.box(3, 0, 4, 5, 2, 7, coat, 0.04)
    m.set(5, 0, 5, '#222', 0)
    m.set(5, 2 - 1, 5, '#222', 0)
    m.box(-4, 0, 4, -3, 1, 6, coat, 0.04)
    for x in (-2, 2):
        m.box(x, 0, 0, x + 1, 1, 2, coat, 0.04)
        m.box(x, 1, 0, x + 1, 2, 2, coat, 0.04)
    return m


def bench(name='bench'):
    m = Vox(name, 7)
    m.box(-6, 0, 3, 6, 3, 4, '#9a6b3f', 0.04)
    m.box(-6, 2, 4, 6, 3, 8, '#9a6b3f', 0.04)
    for x in (-5, 4):
        m.box(x, 0, 0, x + 2, 3, 3, '#4a4f57', 0.02)
    return m


def bin_(name='bin', c='#3f8f5a'):
    m = Vox(name, 8)
    m.disc(0, 0, 0, 2.6, c, h=6, j=0.03)
    m.disc(0, 0, 6, 3, '#2e6b43', h=1, j=0.02)
    m.set(0, -3, 3, '#e8e2d4', 0)
    return m


def hoop(name='hoop'):
    m = Vox(name, 9)
    m.box(0, 0, 0, 2, 2, 30, '#4a4f57', 0.02)
    m.box(0, -8, 28, 2, 2, 30, '#4a4f57', 0.02)
    m.box(-3, -9, 24, 5, -8, 33, '#f3efe4', 0.01)             # backboard
    m.box(-1, -9, 27, 3, -8, 30, '#d1342f', 0)
    m.ring(-1, -13, 24, 3, -9, 25, '#e0602a', 1, 0)           # rim
    return m


def flag_ph(name='flag_ph'):
    m = Vox(name, 10)
    m.box(0, 0, 0, 2, 2, 3, '#6b6f76', 0.02)
    m.box(0, 0, 3, 1, 1, 46, '#c9ced4', 0.01)
    m.box(1, 0, 34, 15, 1, 40, '#ce1126', 0)
    m.box(1, 0, 40, 15, 1, 46, '#0038a8', 0)
    for x in range(1, 8):                                       # white hoist triangle
        h = 7 - (x - 1)
        m.box(x, 0, 40 - h, x + 1, 1, 40 + h, '#ffffff', 0)
    m.box(2, 0, 39, 4, 1, 41, '#fcd116', 0)
    return m


def figure(name='figure', shirt='#2f6fb5', pants='#33384a', skin='#e0ac7c', hair='#2a1d16', shoes='#2a2622',
           hat=None, hat_kind='hard', vest=None, tie=None, sleeves='short', pose='rest', hairstyle='short',
           glasses=False, badge=None, seed=11):
    """A detailed standing person, 33 cells tall (a hat adds 2), front facing -Y.
    pose: rest | present (right hand out) | wave | cross (arms folded) | up (both arms raised, carrying)"""
    m = Vox(name, seed)
    # legs and shoes; shoes stick out one cell at the front
    for x0 in (-4, 1):
        m.box(x0, -2, 2, x0 + 3, 2, 12, pants, 0.02)
        m.box(x0, -4, 0, x0 + 3, 2, 2, shoes, 0.0)
    m.box(-1, -2, 8, 1, 2, 12, pants, 0.02)
    # torso, belt
    m.box(-4, -2, 12, 4, 2, 22, shirt, 0.025)
    m.box(-4, -2, 12, 4, 2, 13, '#2b2b2b', 0)
    m.set(0, -3, 12, '#c9b24a', 0)
    if vest:
        for x in range(-4, 4):
            for y in range(-2, 2):
                for z in range(13, 22):
                    if y in (-2, 1) or x in (-4, 3):
                        m.set(x, y, z, vest, 0.02)
        for z in (15, 19):
            m.box(-4, -3, z, 4, -2, z + 1, '#f1f1e8', 0)
            m.box(-4, 1, z, 4, 2, z + 1, '#f1f1e8', 0)
        m.box(-1, -2, 13, 1, -1, 22, shirt, 0.02)          # the shirt shows down the middle
    if tie:
        m.box(-1, -3, 20, 1, -2, 22, tie, 0)
        m.box(-1, -3, 14, 1, -2, 20, tie, 0)
        m.box(-1, -3, 13, 0, -2, 14, tie, 0)
        for x in (-2, 1):
            m.box(x, -3, 21, x + 1, -2, 22, '#fafafa', 0)    # collar
    if badge:
        m.box(1, -3, 16, 3, -2, 18, badge, 0)
        m.set(1, -3, 17, '#2f8f8a', 0)
    # arms
    sl = skin if sleeves == 'short' else shirt
    arm_c = vest or shirt

    def arm(xa, xb, z0, z1, hand_z=None):
        m.box(xa, -1, z0, xb, 1, z1, shirt, 0.025)
        m.box(xa, -1, z0, xb, 1, z0 + 5, sl, 0.02)
        m.box(xa, -1, z0 - 2, xb, 1, z0, skin, 0.02)
    if pose in ('rest', 'wave', 'present'):
        arm(-6, -4, 14, 21)
    if pose == 'rest':
        arm(4, 6, 14, 21)
    elif pose == 'present':        # right forearm forward, palm up
        m.box(4, -1, 17, 6, 1, 21, shirt, 0.025)
        m.box(4, -6, 17, 6, -1, 19, sl, 0.02)
        m.box(4, -9, 17, 6, -6, 19, skin, 0.02)
        m.box(4, -9, 19, 6, -7, 20, skin, 0.02)
    elif pose == 'wave':
        m.box(4, -1, 20, 6, 1, 25, shirt, 0.025)
        m.box(4, -1, 25, 6, 1, 29, sl, 0.02)
        m.box(4, -1, 29, 6, 1, 32, skin, 0.02)
    elif pose == 'cross':
        arm(-6, -4, 17, 21)
        arm(4, 6, 17, 21)
        m.box(-5, -4, 16, 5, -2, 19, shirt, 0.025)
        m.box(-5, -4, 16, -3, -2, 19, skin, 0.02)
    elif pose == 'up':
        for xa in (-6, 4):
            m.box(xa, -1, 18, xa + 2, 1, 24, shirt, 0.025)
            m.box(xa, -1, 24, xa + 2, 1, 29, sl, 0.02)
            m.box(xa, -1, 29, xa + 2, 1, 32, skin, 0.02)
    # neck, head
    m.box(-1, -1, 22, 1, 1, 23, skin, 0.02)
    m.box(-3, -3, 23, 3, 3, 30, skin, 0.015)
    m.set(-4, 0, 26, skin, 0.03)
    m.set(3, 0, 26, skin, 0.03)
    m.set(0, -4, 26, skin, 0.05)                              # nose
    for x in (-2, 1):
        m.set(x, -3, 27, '#1c1c1c', 0)                        # eyes
        m.set(x, -3, 25, '#e89a8a', 0.02)                     # cheeks
    m.box(-1, -3, 24, 1, -2, 25, '#8a3b2d', 0)               # mouth
    if glasses:
        for x0 in (-3, 0):
            m.box(x0, -4, 26, x0 + 3, -3, 29, '#3a3f4a', 0)
            m.box(x0 + 1, -4, 27, x0 + 2, -3, 28, None)
    # hair
    if hairstyle != 'none':
        m.box(-3, -3, 30, 3, 3, 32, hair, 0.03)
        m.box(-3, 1, 23, 3, 3, 30, hair, 0.03)
        for x in (-3, 2):
            m.box(x, -3, 27, x + 1, 3, 30, hair, 0.03)
        if hairstyle == 'long':
            m.box(-3, 1, 17, 3, 3, 23, hair, 0.03)
            for x in (-4, 3):
                m.box(x, -1, 20, x + 1, 3, 29, hair, 0.03)
    # hat
    if hat:
        if hat_kind == 'hard':
            m.box(-4, -4, 30, 4, 4, 32, hat, 0.015)
            m.box(-3, -3, 32, 3, 3, 33, hat, 0.015)
            m.box(-1, -3, 33, 1, 3, 34, hat, 0.015)
            m.box(-4, -6, 30, 4, -4, 31, hat, 0.015)
        else:  # cap
            m.box(-3, -3, 30, 3, 3, 33, hat, 0.015)
            m.box(-3, -6, 30, 3, -3, 31, hat, 0.015)
    return m
