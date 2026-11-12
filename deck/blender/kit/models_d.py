"""Sol kit, part D: the environment. Ground tiles (32 x 32, top at z = 0), mid-rise, store, court, hills, skyline."""
import math, random
from voxlib import Vox, _hash

T = 32
SIDEWALK, SEAM, CURB, ASPHALT = '#d6d0c2', '#bdb6a6', '#ebe7da', '#4d525b'


def _noise(x, y, s):
    return _hash(x, y, 0, s)


def grass(name='grass_a', seed=1, flowers=None, dirt=False, pebbles=False, bushes=0):
    m = Vox(name, seed)
    r = random.Random(seed)
    h = T // 2
    for x in range(-h, h):
        for y in range(-h, h):
            n = _noise(x // 3, y // 3, seed) * 0.5 + _noise(x, y, seed + 3) * 0.5
            c = '#7fb957' if n > .55 else '#74ae4f' if n > .3 else '#6aa548'
            m.box(x, y, -2, x + 1, y + 1, 0, c, 0.035)
    # tufts: a taller cell, sometimes two
    for _ in range(95):
        x, y = r.randint(-h, h - 1), r.randint(-h, h - 1)
        m.set(x, y, 0, r.choice(['#8cc761', '#80bd58', '#98d06b']), 0.05)
        if r.random() < .3:
            m.set(x, y, 1, '#98d06b', 0.05)
    if dirt:
        for x in range(-h, h):
            for y in range(-h, h):
                d = abs(y - 3 * math.sin(x * .22)) 
                if d < 3.5 + 1.2 * _noise(x, y, 5):
                    m.box(x, y, -2, x + 1, y + 1, 0, '#b68f5e' if _noise(x, y, 8) > .3 else '#a8825a', 0.05)
    if flowers:
        for _ in range(26):
            x, y = r.randint(-h, h - 1), r.randint(-h, h - 1)
            m.set(x, y, 0, r.choice(flowers), 0.03)
            m.set(x, y, 1, r.choice(flowers), 0.03)
    if pebbles:
        for _ in range(16):
            x, y = r.randint(-h, h - 2), r.randint(-h, h - 2)
            m.box(x, y, 0, x + 2, y + 1, 1, r.choice(['#b8b3a6', '#a29d92']), 0.04)
    return m


def _slab(m, x0, x1, y0, y1, z, base=SIDEWALK, seam=SEAM, pitch=4):
    for x in range(x0, x1):
        for y in range(y0, y1):
            c = seam if (x % pitch == 0 or y % pitch == 0) else base
            m.set(x, y, z, c, 0.025)


def _road(m, x0, x1, y0, y1, seed):
    for x in range(x0, x1):
        for y in range(y0, y1):
            m.box(x, y, -2, x + 1, y + 1, 0, ASPHALT if _noise(x, y, seed) > .12 else '#454a52', 0.03)


def street(name='street_h', seed=2, zebra=False, manhole=True):
    """E-W street. y: sidewalk -16..-12, curb, road -11..11, curb, sidewalk 12..16."""
    m = Vox(name, seed)
    m.box(-16, -16, -2, 16, 16, 0, '#8a8e94', 0.02)
    _road(m, -16, 16, -11, 11, seed)
    for y0, y1 in ((-16, -12), (12, 16)):
        m.box(-16, y0, 0, 16, y1, 1, SIDEWALK, 0.02)
        _slab(m, -16, 16, y0, y1, 0)
    for y in (-12, 11):
        m.box(-16, y, 0, 16, y + 1, 1, CURB, 0.015)
    for x in range(-16, 16):
        m.set(x, -10, -1, '#d8d6cc', 0.02)
        m.set(x, 9, -1, '#d8d6cc', 0.02)
        if (x + 16) % 10 < 6:
            m.set(x, 0, -1, '#f2c744', 0.02)
    if manhole:
        m.disc(6, 4, -1, 2.2, '#5a5f66', h=1, j=0.02)
    if zebra:
        for y in range(-10, 10):
            if y % 2 == 0:
                m.box(-3, y, -1, 3, y + 1, 0, '#f1efe6', 0.01)
    return m


def street_cross(name='street_cross', seed=3):
    m = Vox(name, seed)
    m.box(-16, -16, -2, 16, 16, 0, ASPHALT, 0.03)
    _road(m, -16, 16, -16, 16, seed)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, x1 = (-16, -11) if sx < 0 else (11, 16)
            y0, y1 = (-16, -11) if sy < 0 else (11, 16)
            m.box(x0, y0, 0, x1, y1, 1, SIDEWALK, 0.02)
            _slab(m, x0, x1, y0, y1, 0)
            for x in range(x0, x1):
                m.set(x, y1 - 1 if sy < 0 else y0, 0, CURB, 0.01)
            for y in range(y0, y1):
                m.set(x1 - 1 if sx < 0 else x0, y, 0, CURB, 0.01)
    for y in range(-10, 10):
        if y % 2 == 0:
            m.box(-10, y, -1, -7, y + 1, 0, '#f1efe6', 0.01)
            m.box(7, y, -1, 10, y + 1, 0, '#f1efe6', 0.01)
    for x in range(-10, 10):
        if x % 2 == 0:
            m.box(x, -10, -1, x + 1, -7, 0, '#f1efe6', 0.01)
            m.box(x, 7, -1, x + 1, 10, 0, '#f1efe6', 0.01)
    return m


def plaza(name='plaza', seed=4):
    m = Vox(name, seed)
    for x in range(-16, 16):
        for y in range(-16, 16):
            a = ((x // 4) + (y // 4)) % 2
            seam = x % 4 == 0 or y % 4 == 0
            m.box(x, y, -2, x + 1, y + 1, 0, '#cbb497' if seam else ('#e0cfb2' if a else '#d8c4a4'), 0.03)
    return m


def driveway(name='yard_path', seed=5):
    m = grass(name, seed, pebbles=True)
    m.box(-6, -16, -2, 6, 16, 0, '#bfb9ac', 0.03)
    for y in range(-16, 16, 6):
        m.box(-6, y, -1, 6, y + 1, 0, '#aaa497', 0.02)
    return m


def court(name='court', seed=6):
    """a barangay basketball court, 64 x 64, painted blue and orange with white lines"""
    m = Vox(name, seed)
    for x in range(-32, 32):
        for y in range(-32, 32):
            inner = abs(x) < 26 and abs(y) < 26
            c = '#4f7fb5' if inner else '#d8643a'
            m.box(x, y, -2, x + 1, y + 1, 0, c, 0.02)
    def line(x0, y0, x1, y1):
        m.box(x0, y0, -1, x1, y1, 0, '#f4f1e8', 0)
    line(-26, -26, 26, -25), line(-26, 25, 26, 26), line(-26, -26, -25, 26), line(25, -26, 26, 26)
    line(-26, -1, 26, 0)
    m.disc(0, 0, -1, 7, '#f4f1e8', h=1, j=0, hollow=1)
    for sy in (-1, 1):
        y0 = -26 if sy < 0 else 26
        line(-8, min(y0, y0 + sy * 16), 8, min(y0, y0 + sy * 16) + 1)
        line(-8, y0 if sy < 0 else y0 - 16, -7, y0 + 16 if sy < 0 else y0)
        line(7, y0 if sy < 0 else y0 - 16, 8, y0 + 16 if sy < 0 else y0)
    return m


def fence_seg(name='fence', seed=7, wall='#e8dfc9'):
    m = Vox(name, seed)
    m.box(0, -1, 0, 2, 1, 12, wall, 0.03)
    m.box(-1, -1, 12, 3, 2, 13, '#fffdf6', 0.01)
    m.box(2, 0, 0, 16, 1, 6, wall, 0.03)
    m.box(2, -1, 6, 16, 1, 7, '#fffdf6', 0.01)
    for x in range(3, 16, 2):
        m.box(x, 0, 7, x + 1, 1, 11, '#4a5059', 0)
    m.box(2, 0, 10, 16, 1, 11, '#4a5059', 0)
    return m


def hedge(name='hedge', seed=8):
    m = Vox(name, seed)
    for i in range(4):
        m.ball(i * 5 - 8, 0, 3, 3.4, 2.6, 3.2, c=['#4c9a3c', '#5fb04a', '#3f8a37'], j=0.06, seed=seed + i)
    return m


def midrise(name='midrise', seed=1, floors=4, w=40, d=28, wall='#e8d9bd', accent='#d9644a', lit_p=0.35):
    m = Vox(name, seed)
    r = random.Random(seed)
    X0, X1, Y0, Y1 = -w // 2, w // 2, -d // 2, d // 2
    FH = 11
    H = floors * FH
    m.box(X0, Y0, 0, X1, Y1, 2, '#a59d90', 0.05)
    m.box(X0, Y0, 2, X1, Y1, H, wall, 0.025)
    for f in range(1, floors + 1):
        m.box(X0 - 1, Y0 - 1, f * FH, X1 + 1, Y1 + 1, f * FH + 1, '#f1ede2', 0.02)
    m.box(X0 - 1, Y0 - 1, H + 1, X1 + 1, Y1 + 1, H + 3, accent, 0.03)
    m.box(X0, Y0, H + 1, X1, Y1, H + 3, accent, 0.03)
    m.box(X0 + 1, Y0 + 1, H + 1, X1 - 1, Y1 - 1, H + 3, None)
    m.box(X0 + 1, Y0 + 1, H, X1 - 1, Y1 - 1, H + 1, '#8d9094', 0.04)
    # windows, a grid on the front and the sides
    for f in range(floors):
        z0 = f * FH + (4 if f == 0 else 3)
        for x in range(X0 + 4, X1 - 4, 8):
            lit = r.random() < lit_p
            for xx in range(x, x + 5):
                for z in range(z0, z0 + 5):
                    m.set(xx, Y0, z, '#ffffff' if lit else '#86b9d8', 0, emit=lit)
            for xx in range(x - 1, x + 6):
                for z in range(z0 - 1, z0 + 6):
                    if xx in (x - 1, x + 5) or z in (z0 - 1, z0 + 5):
                        m.set(xx, Y0 - 1, z, '#f1ede2', 0.02)
            if f > 0:      # a small balcony rail under each upper window
                m.box(x - 1, Y0 - 3, f * FH, x + 6, Y0 - 1, f * FH + 1, '#f1ede2', 0.02)
                for xx in range(x - 1, x + 6, 2):
                    m.box(xx, Y0 - 3, f * FH + 1, xx + 1, Y0 - 2, f * FH + 4, '#4a5059', 0)
                m.box(x - 1, Y0 - 3, f * FH + 4, x + 6, Y0 - 2, f * FH + 5, '#f1ede2', 0.02)
        for y in range(Y0 + 5, Y1 - 3, 8):
            for sx, xf in ((1, X1 - 1), (-1, X0)):
                lit = r.random() < lit_p
                for yy in range(y, y + 4):
                    for z in range(z0, z0 + 5):
                        m.set(xf, yy, z, '#ffffff' if lit else '#86b9d8', 0, emit=lit)
    # entrance
    m.box(-4, Y0 - 1, 2, 4, Y0, 10, '#4a5059', 0)
    m.box(-3, Y0 - 1, 3, 3, Y0, 9, '#86b9d8', 0)
    m.box(-6, Y0 - 5, 10, 6, Y0, 11, '#f1ede2', 0.02)
    # roof: tank + stair box
    m.disc(X0 + 6, Y1 - 6, H + 5, 4.5, '#3d78c4', h=7, j=0.03)
    for dx, dy in ((-3, -3), (3, -3), (-3, 3), (3, 3)):
        m.box(X0 + 6 + dx, Y1 - 6 + dy, H + 1, X0 + 7 + dx, Y1 - 5 + dy, H + 5, '#55595f', 0)
    m.box(X1 - 12, Y1 - 12, H + 1, X1 - 4, Y1 - 4, H + 8, wall, 0.03)
    return m


def sari_sari(name='sari_sari', seed=3, wall='#58b3a2', awning=('#d1342f', '#f7f3e8')):
    m = Vox(name, seed)
    w, d = 28, 20
    X0, X1, Y0, Y1 = -w // 2, w // 2, -d // 2, d // 2
    m.box(X0, Y0, 0, X1, Y1, 1, '#a59d90', 0.05)
    m.box(X0, Y0, 1, X1, Y1, 15, wall, 0.03)
    m.box(X0 - 1, Y0 - 1, 15, X1 + 1, Y1 + 1, 17, '#f1ede2', 0.02)
    # open counter window in front
    m.clear(-9, Y0, 5, 9, Y0 + 1, 13)
    m.box(-10, Y0 - 3, 4, 10, Y0, 5, '#9a6b3f', 0.04)                  # counter
    m.box(-9, Y0 - 3, 1, 9, Y0 - 2, 4, '#8a5738', 0.04)
    # shelves with products
    rr = random.Random(seed)
    for z in (6, 9, 12):
        m.box(-9, Y0 + 1, z - 1, 9, Y0 + 3, z, '#6d4a2e', 0.03)
        for x in range(-9, 9):
            if rr.random() < .85:
                m.box(x, Y0 + 1, z, x + 1, Y0 + 3, z + rr.randint(1, 2), rr.choice(['#d1342f', '#f2c230', '#2a6fb5', '#f7f3e8', '#3c9a6a', '#e07fae']), 0.02)
    # striped awning
    for x in range(-12, 12):
        c = awning[(x // 2) % 2]
        for k in range(5):
            m.box(x, Y0 - 1 - k, 14 - (k + 1) // 2, x + 1, Y0 - k, 15 - (k + 1) // 2, c, 0.02)
    # sign board on the roof edge, a colour-block sign
    m.box(-11, Y0 - 1, 17, 11, Y0, 22, '#f7f3e8', 0.01)
    for i, c in enumerate(['#d1342f', '#2a6fb5', '#f2c230', '#3c9a6a']):
        m.box(-10 + i * 5, Y0 - 2, 18, -6 + i * 5, Y0 - 1, 21, c, 0.02)
    m.box(-10, Y0 - 2, 17, 10, Y0 - 1, 18, '#23262b', 0)
    # side window and door
    m.box(X1 - 1, -3, 5, X1, 3, 11, '#86b9d8', 0)
    m.box(X0, -2, 1, X0 + 1, 3, 11, '#7a4a2e', 0.03)
    # hanging chip packs, a little lit lamp
    for x in range(-8, 8, 3):
        m.box(x, Y0 - 1, 12, x + 2, Y0, 14, rr.choice(['#d1342f', '#f2c230', '#2a6fb5']), 0.02)
    m.box(-1, Y0 - 3, 13, 1, Y0 - 2, 14, '#ffffff', 0, emit=True)
    return m


def pavilion(name='pavilion', seed=2):
    """covered-court roof: four posts and a steel roof, for the barangay hall plaza"""
    m = Vox(name, seed)
    for x in (-26, 26):
        for y in (-18, 18):
            m.box(x - 1, y - 1, 0, x + 1, y + 1, 30, '#c9ced4', 0.02)
    m.box(-30, -22, 30, 30, 22, 32, '#e5e8ea', 0.02)
    for k in range(7):
        m.box(-30, -22 + k * 4, 32, 30, -21 + k * 4, 33, '#d1342f', 0.02)
    return m


def hills(name='hills_a', seed=1, nx=150, ny=36, scale=4, hmax=34, base='#5f9a56', rock='#8c8a78'):
    """a far hill strip, x across, y deep; one cell = `scale` units"""
    m = Vox(name, seed, scale=scale, ao=False)
    for x in range(nx):
        for y in range(ny):
            # ridge profile rises toward the back
            n = (_noise(x // 6, y // 5, seed) * .6 + _noise(x // 2, y // 2, seed + 4) * .25 + _noise(x, y, seed + 9) * .15)
            back = (y / ny) ** 1.1
            fall = math.sin(math.pi * (x + .5) / nx) ** 0.4
            h = int(2 + hmax * (0.18 + 0.82 * n) * (0.25 + back * .75) * fall)
            for z in range(0, h):
                tone = _noise(x, y, seed + 21)
                if z > h - 3 and h > hmax * 0.8 and tone > .6:
                    c = rock
                else:
                    c = ['#4f8a4a', '#5f9a56', '#6aa65d', '#548f4c'][int(tone * 4) % 4]
                m.set(x, y, z, c, 0.04)
    return m


def skyline(name='skyline', seed=1, nx=110, scale=4):
    m = Vox(name, seed, scale=scale, ao=False)
    r = random.Random(seed)
    x = 0
    tones = ['#9aa7b8', '#a9b4c2', '#8e9bad', '#b6c0cc', '#7f8ea3']
    while x < nx:
        w = r.randint(4, 8)
        h = r.choice([14, 18, 22, 26, 34, 42, 54]) if 14 < x < nx - 14 else r.choice([8, 12, 16])
        tone = r.choice(tones)
        m.box(x, 0, 0, x + w, 5, h, tone, 0.03)
        for z in range(3, h - 1, 3):
            for xx in range(x + 1, x + w - 1):
                if r.random() < .38:
                    m.set(xx, 0, z, '#ffffff', 0, emit=True)
        if h > 30:
            m.box(x + w // 2 - 1, 1, h, x + w // 2 + 1, 3, h + 6, '#a0aab6', 0)
        x += w + r.randint(0, 3)
    return m
