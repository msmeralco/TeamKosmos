"""Sol kit, part C: the Sol story pieces (solar gear, Sol, coins, weather, Passport, chain, strata layers, letters)."""
import math, random
from voxlib import Vox, FONT

AMBER, AMBER_HI, TEAL = '#ffb43a', '#ffd479', '#2f8f8a'


def panel(name='panel', seed=1):
    """10 x 6 cells (2.5 m x 1.5 m), on a 1-cell stand. Lies flat; the web scene may tilt it."""
    m = Vox(name, seed, bottoms=True)
    m.box(0, 0, 0, 10, 6, 1, '#cdd5de', 0.01)                       # frame
    m.box(1, 1, 0, 9, 5, 1, '#1f3f7c', 0.02)                        # cells
    for x in range(1, 9):
        for y in range(1, 5):
            if x % 2 == 0 or y % 2 == 0:
                m.set(x, y, 0, '#3a63a8', 0.02)
    for y in range(1, 5):
        m.set(2, y, 0, '#2c4f94', 0.02)
    for x in range(1, 9):
        m.set(x, 3, 0, '#2c4f94', 0.02)
    m.box(0, 0, -1, 1, 1, 0, '#6d7076', 0)
    m.box(9, 5, -1, 10, 6, 0, '#6d7076', 0)
    m.box(0, 5, -1, 1, 6, 0, '#6d7076', 0)
    m.box(9, 0, -1, 10, 1, 0, '#6d7076', 0)
    # origin: middle of the panel's footprint
    out = Vox(name, seed, bottoms=True)
    out.merge(m, -5, -3, 1)
    return out


def battery(name='battery'):
    m = Vox(name, 2)
    m.box(-5, 0, 0, 5, 4, 15, '#f4f5f6', 0.01)
    m.box(-5, 0, 0, 5, 4, 1, '#c7cbd0', 0.01)
    m.box(-4, -1, 3, 4, 0, 13, '#e9ecee', 0.01)
    m.box(-3, -1, 10, 3, 0, 11, '#2f8f8a', 0, emit='g')              # status bar
    for i in range(4):
        m.box(-3 + i * 2, -1, 5, -2 + i * 2, 0, 8, '#2f8f8a' if i < 3 else '#3a3e44', 0, emit='g' if i < 3 else False)
    m.box(-1, 1, 15, 1, 3, 17, '#454a52', 0)                         # cable gland
    return m


def inverter(name='inverter'):
    m = Vox(name, 3)
    m.box(-4, 0, 0, 4, 3, 10, '#d9dde1', 0.01)
    m.box(-3, -1, 6, 3, 0, 9, '#1c2128', 0)
    m.box(-2, -1, 7, 2, 0, 8, '#4be06a', 0, emit='g')
    for i in range(4):
        m.box(-3, -1, 1 + (i % 2), -2, 0, 2 + (i % 2), '#a8adb3', 0)
    for x in (-2, 0, 2):
        m.box(x, -1, 2, x + 1, 0, 4, '#aeb3b9', 0)
    return m


def sun_big(name='sun_big'):
    m = Vox(name, 4, bottoms=True)
    m.ball(0, 0, 0, 17, c=AMBER, j=0, emit='g')
    m.ball(0, 0, 0, 12, c=AMBER_HI, j=0, emit='g')
    for a in range(8):
        t = a * math.pi / 4
        for r in range(21, 29):
            x, z = math.cos(t) * r, math.sin(t) * r
            m.box(round(x) - 1, -1, round(z) - 1, round(x) + 1, 1, round(z) + 1, AMBER, 0, emit='g')
    return m


def sol(name='sol'):
    """Sol, the companion: a small sun with a face."""
    m = Vox(name, 5, bottoms=True)
    m.ball(0, 0, 0, 5, c=AMBER, j=0, emit='g')
    m.ball(0, 0, 0, 3, c=AMBER_HI, j=0, emit='g')
    for a in range(8):
        t = a * math.pi / 4 + .39
        m.box(round(math.cos(t) * 8) - 1, -1, round(math.sin(t) * 8) - 1, round(math.cos(t) * 8), 0, round(math.sin(t) * 8), AMBER, 0, emit='g')
    # eyes + smile on the front (-Y) side
    for ex in (-2, 1):
        m.box(ex, -6, 0, ex + 1, -5, 2, '#17181c', 0, emit='g')
    for x, z in ((-2, -2), (-1, -3), (0, -3), (1, -2)):
        m.set(x, -6, z, '#17181c', 0, emit='g')
    return m


def coin(name='coin'):
    m = Vox(name, 6, bottoms=True)
    m.disc(0, 0, 0, 6, '#e0a21e', h=2, j=0.02)
    m.disc(0, 0, 1, 5, '#f6c445', h=1, j=0.02)
    m.disc(0, 0, 1, 2.4, '#e0a21e', h=1, j=0.02)
    return m


def cloud(name='cloud_a', seed=1, storm=False, size=1.0):
    r = random.Random(seed)
    m = Vox(name, seed, bottoms=True)
    cols = ['#5a6577', '#667388', '#4f596a'] if storm else ['#ffffff', '#f4f8fc', '#e9f0f7']
    for i in range(5):
        cx, cy = r.randint(-12, 12) * size, r.randint(-5, 5) * size
        m.ball(cx, cy, r.randint(0, 3), r.randint(6, 10) * size, r.randint(5, 8) * size, r.randint(4, 6) * size, c=cols, j=0.03, seed=seed + i)
    # flatten the belly
    for p in [p for p in m.v if p[2] < -1]:
        m.v.pop(p)
    for p, c in list(m.v.items()):
        if (p[0], p[1], p[2] + 1) in m.v:
            f = .93
            m.v[p] = (c[0] * f, c[1] * f, c[2] * f)
    return m


def passport(name='passport', seed=7):
    """the Solar Passport: an upright card, 30 x 3 x 40 cells"""
    m = Vox(name, seed)
    m.box(-15, 0, 0, 15, 3, 40, '#f6f2e6', 0.01)
    m.box(-15, -1, 0, 15, 0, 40, '#f6f2e6', 0.01)
    # teal border and header
    for x in range(-15, 15):
        for z in range(0, 40):
            if x in (-15, 14) or z in (0, 39):
                m.set(x, -1, z, TEAL, 0.01)
    m.box(-14, -1, 31, 14, 0, 38, TEAL, 0.01)
    m.box(-12, -2, 34, -4, -1, 36, '#f6f2e6', 0)                       # small sun mark
    for i in range(3):
        m.box(-3 + i * 5, -2, 33 + (i % 2), 0 + i * 5, -1, 34 + (i % 2), '#cfe7e4', 0)
    # text lines
    rr = random.Random(seed)
    for z in range(27, 12, -3):
        ln = rr.randint(14, 24)
        m.box(-12, -1, z, -12 + ln, 0, z + 1, '#b9b4a6', 0.02)
    # QR-style block
    for x in range(8):
        for z in range(8):
            if (x in (0, 7) or z in (0, 7) or rr.random() < .5):
                m.set(-12 + x, -1, 3 + z, '#23282f', 0)
    # signature squiggle
    for i in range(12):
        m.set(1 + i, -1, 6 + int(2 * math.sin(i * .9)), '#2f8f8a', 0)
    # stand
    return m


def seal(name='seal'):
    m = Vox(name, 8)
    m.disc(0, 0, 0, 8, TEAL, h=2, j=0.02, hollow=0)
    m.disc(0, 0, 2, 7, '#3aa59f', h=1, j=0.02)
    m.disc(0, 0, 2, 5, '#2f8f8a', h=1, j=0.02)
    # tick: front (-Y) is the seal's face, so build the disc standing: rotate by writing into y
    t = Vox(name, 8)
    for (x, y, z), c in m.v.items():
        t.v[(x, -z, y)] = c
    for (x, z) in ((-3, 0), (-2, -1), (-1, -2), (0, -1), (1, 0), (2, 1), (3, 2), (4, 3)):
        t.set(x, -3, z, '#ffffff', 0, emit='g')
        t.set(x, -3, z - 1, '#ffffff', 0, emit='g')
    for x in (-5, 5):
        t.box(x - 1, -1, -13, x + 1, 0, -8, '#c94b4b', 0.02)         # ribbons
    return t


def chain_block(name='chain_block', seed=3):
    """a block of the hash chain, 8 cells wide, with a 4-cell link at each side (pitch 12)"""
    m = Vox(name, seed)
    rr = random.Random(seed)
    m.box(-4, -4, 0, 4, 4, 8, '#3a4a5c', 0.03)
    for x in range(-4, 4):
        for z in range(0, 8):
            if rr.random() < .5:
                m.set(x, -4, z, '#2f8f8a', 0.03)
    for y in range(-4, 4):
        for z in range(0, 8):
            if rr.random() < .45:
                m.set(3, y, z, '#4a6a86', 0.03)
    m.box(-4, -4, 8, 4, 4, 9, '#c9d3dd', 0.02)
    for sx in (-1, 1):
        m.box(sx * 6 - 2, -1, 3, sx * 6 + 2, 1, 5, '#e0a21e', 0.02)
    return m


def letters(text, px=4, name=None, color=AMBER, emit=False, depth=None):
    m = Vox(name or 'word_' + text, 11)
    depth = depth or px
    w = len(text) * 6 * px - px
    for i, ch in enumerate(text):
        g = FONT[ch]
        for r, row in enumerate(g):
            for q, bit in enumerate(row):
                if bit == '1':
                    x0 = -w // 2 + i * 6 * px + q * px
                    m.box(x0, 0, (6 - r) * px, x0 + px, depth, (7 - r) * px, color, 0.03, emit)
    return m


def layer(name, kind, seed=1):
    """one slab of the strata stack, 40 x 40 x 5. Lies flat; the web scene lifts it apart."""
    m = Vox(name, seed, bottoms=True)
    rr = random.Random(seed)
    base = {'weather': '#8fc1e6', 'tariff': '#eab04a', 'credit': '#66b9ae', 'prices': '#d4d7dc'}[kind]
    dark = {'weather': '#6ba3d0', 'tariff': '#c98a28', 'credit': '#3f9a8f', 'prices': '#9ea4ac'}[kind]
    m.box(-20, -20, 0, 20, 20, 5, base, 0.03)
    m.box(-20, -20, 0, 20, 20, 1, dark, 0.02)
    for x in range(-20, 20):
        for y in range(-20, 20):
            if x in (-20, 19) or y in (-20, 19):
                m.set(x, y, 4, dark, 0.02)
    if kind == 'weather':
        m.ball(-8, 6, 6, 5, 5, 3, c=AMBER, j=0, emit='g')
        for cx, cy, rx in ((6, -6, 8), (12, 8, 6), (-6, -10, 6)):
            m.ball(cx, cy, 6, rx, 4, 2.2, c='#ffffff', j=0.02)
    elif kind == 'tariff':
        hs = [3, 4, 4, 5, 6, 7, 8, 9]
        for i, h in enumerate(hs):
            m.box(-16 + i * 4, -10, 5, -13 + i * 4, 0, 5 + h, '#8a4e12', 0.03)
            m.box(-16 + i * 4, -10, 5 + h, -13 + i * 4, 0, 6 + h, '#c97a1f', 0.03)
    elif kind == 'credit':
        for cx, cy in ((-10, 6), (0, 10), (10, 4), (-4, -6), (8, -10), (-14, -12)):
            m.disc(cx, cy, 5, 4, '#e0a21e', h=1, j=0.02)
            m.disc(cx, cy, 6, 3, '#f6c445', h=1, j=0.02)
    else:
        for cx in (-12, 0, 12):
            for cy in (-9, 6):
                m.box(cx - 5, cy - 3, 5, cx + 5, cy + 3, 6, '#f4f2ea', 0.02)
                m.box(cx - 4, cy - 1, 6, cx + 1, cy, 7, '#454a52', 0)
                m.set(cx + 3, cy + 1, 6, '#c94b4b', 0)
    return m


def flag_board(name='flag_board', w=20, h=12):
    m = Vox(name, 12)
    m.box(0, 0, 0, 2, 2, 3, '#6b6f76', 0.02)
    m.box(0, 0, 3, 1, 1, 40, '#c9ced4', 0.01)
    m.box(1, 0, 40 - h, 1 + w, 1, 40, '#fafaf6', 0.01)
    m.box(1, 0, 40 - h, 1 + w, 1, 41 - h, '#d9d6cb', 0)
    m.box(1, 0, 39, 1 + w, 1, 40, '#d9d6cb', 0)
    m.box(1, 0, 40 - h, 2, 1, 40, '#d9d6cb', 0)
    m.box(w, 0, 40 - h, 1 + w, 1, 40, '#d9d6cb', 0)
    return m


def energy_cube(name='energy_cube', big=True):
    m = Vox(name, 13, bottoms=True)
    s = 3 if big else 2
    m.box(0, 0, 0, s, s, s, AMBER, 0, emit='g')
    return m


def rec_slot(name='rec_slot'):
    """the empty REC-meter slot on a meter post: a dashed outline on a plain box"""
    m = Vox(name, 14)
    m.box(-5, 0, 0, 5, 4, 14, '#c8cacd', 0.02)
    for x in range(-4, 4):
        for z in range(2, 12):
            edge = x in (-4, 3) or z in (2, 11)
            if edge and (x + z) % 2 == 0:
                m.set(x, -1, z, '#6d7076', 0)
    return m


def solar_rack(name='solar_rack', cols=3, rows=2, seed=21):
    """A ground-mount array: cols x rows panels on a stepped tilt, low edge toward -Y (the viewer). 32 x 13 cells for 3 x 2."""
    m = Vox(name, seed, bottoms=True)
    pw, pd, gap = 10, 6, 1
    W = cols * pw + (cols - 1) * gap
    D = rows * pd + (rows - 1) * gap
    x0 = -(W // 2)
    zb = lambda y: 6 + y // 2
    for ci in range(cols):
        for ri in range(rows):
            px, py = x0 + ci * (pw + gap), ri * (pd + gap)
            for dx in range(pw):
                for dy in range(pd):
                    edge = dx in (0, pw - 1) or dy in (0, pd - 1)
                    if edge:
                        c = '#cdd5de'
                    elif dy == 3:
                        c = '#2c4f94'
                    elif dx % 2 == 0 or dy % 2 == 0:
                        c = '#3a63a8'
                    else:
                        c = '#1f3f7c'
                    m.set(px + dx, py + dy, zb(py + dy), c, 0.02)
                    m.set(px + dx, py + dy, zb(py + dy) - 1, '#6d7076', 0)
    for y in range(D):                                   # rails in the gaps and under the rows
        for x in range(x0, x0 + W):
            if m.v.get((x, y, zb(y))) is None:
                m.set(x, y, zb(y), '#454a52', 0)
    for x in (x0 + 2, x0 + W // 2, x0 + W - 3):          # posts: short at the front, tall at the back
        m.box(x, 0, 0, x + 1, 1, zb(0) - 1, '#9aa0a8', 0.02)
        m.box(x, D - 1, 0, x + 1, D, zb(D - 1) - 1, '#9aa0a8', 0.02)
        m.box(x - 1, -1, 0, x + 2, 2, 1, '#9d968a', 0.03)
        m.box(x - 1, D - 2, 0, x + 2, D + 1, 1, '#9d968a', 0.03)
    for x in (x0 + 1, x0 + W - 2):                       # side braces
        m.line((x, 0, 1), (x, D - 1, zb(D - 1) - 2), '#7b8088', 0)
    return m


def meter_stand(name='meter_stand', seed=31):
    """The meter post by the road: inverter on top, the optional REC meter slot in the middle, the net meter at the bottom. Front -Y."""
    m = Vox(name, seed)
    m.box(-9, -2, 0, 9, 8, 2, '#9d968a', 0.04)                       # footing
    m.box(-7, 0, 2, 7, 6, 40, '#b4afa4', 0.03)                       # concrete post
    m.box(-8, -1, 40, 8, 7, 42, '#d9d4c8', 0.02)                     # cap
    for z in range(8, 40, 8):
        m.box(-7, 0, z, 7, 1, z + 1, '#a29d92', 0)
    # top bay: inverter
    m.box(-6, -1, 28, 6, 0, 39, '#e8ebee', 0.01)
    m.box(-4, -2, 31, 4, -1, 37, '#1c2128', 0)
    m.box(-2, -3, 33, 2, -2, 35, '#4be06a', 0, emit='g')
    for i in range(5):
        m.box(-5 + i * 2 + 1, -2, 29, -4 + i * 2 + 1, -1, 30, '#aeb3b9', 0)
    # middle bay: the REC meter slot, empty and dashed
    m.box(-6, -1, 16, 6, 0, 27, '#c9cdd0', 0.02)
    for x in range(-5, 5):
        for z in range(17, 26):
            if (x in (-5, 4) or z in (17, 25)) and (x + z) % 2 == 0:
                m.set(x, -2, z, '#6d7076', 0)
    # bottom bay: the net meter, a glass dome with a dial
    m.box(-6, -1, 4, 6, 0, 15, '#c8cacd', 0.02)
    for x in range(-5, 5):
        for z in range(5, 14):
            d = math.hypot(x + 0.5, z - 9.5)
            if d <= 4.4:
                m.set(x, -2, z, '#cfe6f2' if d > 3.3 else '#fbfbf8', 0)
    m.box(-1, -3, 8, 2, -2, 11, '#1c1f24', 0)
    m.set(0, -3, 10, '#d33b3b', 0)
    m.box(-3, -2, 13, 3, -1, 14, '#2a6fb5', 0)
    # conduits
    m.box(-1, 2, 42, 1, 4, 50, '#4b5057', 0)
    m.box(6, 2, 8, 9, 4, 10, '#4b5057', 0)
    m.box(-9, 2, 8, -6, 4, 10, '#4b5057', 0)
    return m


def map_pin(name='map_pin'):
    """A glowing location pin, 14 cells wide, 30 tall."""
    m = Vox(name, 41)
    for z in range(0, 14):
        r = 1 + 6 * (z / 13.0)
        m.disc(0, 0, z, r, '#e2483d', h=1, j=0, emit='g')
    m.ball(0, 0, 20, 7, c='#e2483d', j=0, emit='g')
    m.ball(0, -6, 20, 3.2, ry=2, rz=3.2, c='#fff6e6', j=0, emit='g')
    return m
