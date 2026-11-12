"""Sol kit, part A: buildings. Each builder returns a Vox with its origin at the middle of the base, front facing -Y."""
import math
from voxlib import Vox, rgb

GLASS, GRILL, TRIM, DOOR = '#86b9d8', '#4a5059', '#f1ede2', '#8a5738'
CONC = '#9d968a'


def _win(m, x0, x1, z0, z1, yf, lit, frame=TRIM, grill=True, side=False):
    """window with a frame. yf = wall plane. side=True means the opening runs along y on an x-facing wall"""
    for a in range(x0, x1):
        for z in range(z0, z1):
            c, e = (None, False)
            if lit:
                m.set(a, yf, z, '#ffffff', 0, emit=True)
            else:
                m.set(a, yf, z, GLASS, 0.02)
    # frame sits proud of the wall by one cell
    for a in range(x0 - 1, x1 + 1):
        for z in range(z0 - 1, z1 + 1):
            edge = a in (x0 - 1, x1) or z in (z0 - 1, z1)
            if edge:
                m.set(a, yf - 1, z, frame, 0.02)
    if grill:
        for a in range(x0, x1):
            if (a - x0) % 3 == 1:
                for z in range(z0, z1):
                    m.set(a, yf - 1, z, GRILL, 0)
        for a in range(x0, x1):
            m.set(a, yf - 1, z0, GRILL, 0)


def _winx(m, xf, y0, y1, z0, z1, lit, sgn):
    """window on an x-facing wall (sgn=+1 east wall at x=xf, -1 west wall)"""
    for yy in range(y0, y1):
        for z in range(z0, z1):
            m.set(xf, yy, z, '#ffffff' if lit else GLASS, 0, emit=bool(lit))
    for yy in range(y0 - 1, y1 + 1):
        for z in range(z0 - 1, z1 + 1):
            if yy in (y0 - 1, y1) or z in (z0 - 1, z1):
                m.set(xf + sgn, yy, z, TRIM, 0.02)
    for yy in range(y0, y1):
        if (yy - y0) % 3 == 1:
            for z in range(z0, z1):
                m.set(xf + sgn, yy, z, GRILL, 0)


def house(name, wall='#f2e3c4', trim=TRIM, roof='flat', roofc='#b8493a', floors=2, w=32, d=26, lit=(), seed=1, accent='#d9a441', meter=True):
    m = Vox(name, seed)
    X0, X1, Y0, Y1 = -w // 2, w // 2, -d // 2, d // 2
    H = floors * 12 + 1
    # plinth + walls
    m.box(X0, Y0, 0, X1, Y1, 2, '#a59d90', 0.05)
    m.box(X0, Y0, 2, X1, Y1, H, wall, 0.025)
    # block-seam lines: every 4th row a touch darker, makes big walls read as concrete block
    for z in range(5, H, 4):
        for x in range(X0, X1):
            for y in (Y0, Y1 - 1):
                if (x, y, z) in m.v:
                    c = m.v[(x, y, z)]
                    m.v[(x, y, z)] = (c[0] * .94, c[1] * .94, c[2] * .94)
        for y in range(Y0, Y1):
            for x in (X0, X1 - 1):
                if (x, y, z) in m.v:
                    c = m.v[(x, y, z)]
                    m.v[(x, y, z)] = (c[0] * .94, c[1] * .94, c[2] * .94)
    # slab bands, outset by one
    for f in range(1, floors + 1):
        m.box(X0 - 1, Y0 - 1, f * 12, X1 + 1, Y1 + 1, f * 12 + 1, trim, 0.02)
    # roof
    if roof == 'flat':
        m.box(X0 - 1, Y0 - 1, H, X1 + 1, Y1 + 1, H + 3, trim, 0.02)           # parapet
        m.box(X0, Y0, H, X1, Y1, H + 3, trim, 0.02)
        m.box(X0 + 1, Y0 + 1, H, X1 - 1, Y1 - 1, H + 3, None)                  # hollow top
        m.box(X0 + 1, Y0 + 1, H - 1, X1 - 1, Y1 - 1, H, '#8d9094', 0.05)       # roof deck
        m.box(X0 - 1, Y0 - 1, H + 3, X1 + 1, Y1 + 1, H + 4, '#fffdf6', 0.01)   # coping
        m.box(X0 + 1, Y0 + 1, H + 3, X1 - 1, Y1 - 1, H + 4, None)
        # water tank on a stand, rear left
        tx, ty = X0 + 6, Y1 - 6
        for dx, dy in ((-3, -3), (3, -3), (-3, 3), (3, 3)):
            m.box(tx + dx, ty + dy, H, tx + dx + 1, ty + dy + 1, H + 5, '#55595f', 0)
        m.disc(tx + .5, ty + .5, H + 5, 4.5, '#3d78c4', h=1, j=0.02)
        m.disc(tx + .5, ty + .5, H + 6, 4.5, '#4a88d6', h=6, j=0.03)
        m.disc(tx + .5, ty + .5, H + 12, 3.5, '#d9e6f2', h=1, j=0.02)
        # sat dish + antenna + hatch
        m.box(X1 - 8, Y1 - 8, H, X1 - 3, Y1 - 3, H + 6, '#d7d2c5', 0.03)
        m.box(X1 - 7, Y1 - 9, H + 1, X1 - 4, Y1 - 8, H + 4, '#8d9094', 0)
        m.line((X1 - 12, Y1 - 4, H), (X1 - 12, Y1 - 4, H + 14), '#6d7076', 0)
        m.line((X1 - 15, Y1 - 4, H + 10), (X1 - 9, Y1 - 4, H + 10), '#6d7076', 0)
        m.line((X1 - 14, Y1 - 4, H + 7), (X1 - 10, Y1 - 4, H + 7), '#6d7076', 0)
        for k in (3, 7):
            m.box(X1 - 6 + k // 3, Y0 + 6, H, X1 - 5 + k // 3, Y0 + 7, H + 6 + k // 2, '#4b5057', 0)
    else:  # gable, ridge along x, GI sheet
        ov = 2
        pitch = 0.62
        half = d / 2 + ov
        top = int(half * pitch)
        # gable end triangles in wall colour
        for x in (X0, X1 - 1):
            for y in range(Y0, Y1):
                hh = int((d / 2 - abs(y + .5)) * pitch)
                for z in range(H, H + hh):
                    m.set(x, y, z, wall, 0.03)
        for x in range(X0 - ov, X1 + ov):
            for y in range(Y0 - ov, Y1 + ov):
                hh = int((half - abs(y + .5)) * pitch)
                stripe = ((x - X0) // 2) % 2
                c = roofc if stripe == 0 else tuple(v * .86 for v in rgb(roofc))
                m.set(x, y, H + hh - 1, c, 0.03)
                if hh > 1:
                    m.set(x, y, H + hh - 2, '#7a6d60', 0.03)
        for x in range(X0 - ov, X1 + ov):
            for y in (-1, 0):
                m.set(x, y, H + top, '#e6e0d2', 0.02)
        # fascia
        m.box(X0 - ov, Y0 - ov, H - 1, X1 + ov, Y0 - ov + 1, H, trim, 0.02)
    # drain pipe at the front-right corner
    m.box(X1 - 1, Y0 - 1, 2, X1, Y0, H - 1, '#6d7076', 0)
    # --- front facade ---
    yf = Y0
    # door + canopy + step
    dx0 = -2
    m.box(dx0, yf, 2, dx0 + 5, yf + 1, 11, DOOR, 0.03)
    m.box(dx0 + 1, yf - 1, 3, dx0 + 4, yf, 7, '#7a4a2e', 0.03)
    m.box(dx0 + 1, yf - 1, 8, dx0 + 4, yf, 10, '#7a4a2e', 0.03)
    m.set(dx0 + 4, yf - 1, 6, '#e4c14e', 0)
    for a in range(dx0 - 1, dx0 + 6):
        for z in range(2, 12):
            if a in (dx0 - 1, dx0 + 5) or z == 11:
                m.set(a, yf - 1, z, trim, 0.02)
    m.box(dx0 - 3, yf - 5, 12, dx0 + 8, yf, 13, trim, 0.02)                    # canopy
    m.box(dx0 - 3, yf - 5, 13, dx0 + 8, yf - 4, 14, trim, 0.02)
    m.box(dx0 - 1, yf - 4, 0, dx0 + 6, yf, 1, '#c9c3b6', 0.04)                 # step
    m.box(dx0 - 1, yf - 6, 0, dx0 + 6, yf - 4, 1, '#c9c3b6', 0.04)
    # ground windows
    _win(m, -13, -7, 5, 10, yf, 0 in lit)
    _win(m, 7, 13, 5, 10, yf, 1 in lit)
    # meter box by the door
    if meter:
        m.box(4, yf - 2, 5, 7, yf, 10, '#c8cacd', 0.02)
        m.box(4, yf - 3, 6, 7, yf - 2, 9, '#dcdee0', 0.02)
        m.set(5, yf - 3, 8, '#9fc7e0', 0)
        m.set(5, yf - 3, 7, '#1c1f24', 0)
        m.set(6, yf - 3, 7, '#d33b3b', 0)
        m.line((5, yf - 1, 10), (5, yf - 1, H - 1), '#4b5057', 0)
    if floors > 1:
        # balcony with railing and a glass door
        m.box(-9, yf - 5, 12, 10, yf, 13, trim, 0.02)
        for x in range(-9, 10):
            if x % 2 == 0 or x in (-9, 9):
                m.box(x, yf - 5, 13, x + 1, yf - 4, 17, GRILL, 0)
        m.box(-9, yf - 5, 16, 10, yf - 4, 17, trim, 0.02)
        for x in range(-5, 5):
            for z in range(14, 22):
                m.set(x, yf, z, '#ffffff' if 2 in lit else GLASS, 0, emit=(2 in lit))
        for x in range(-6, 6):
            for z in range(13, 23):
                if x in (-6, 5) or z == 22:
                    m.set(x, yf - 1, z, trim, 0.02)
        m.box(-1, yf - 1, 14, 0, yf, 22, trim, 0)
        # side windows, AC unit
        _win(m, -13, -8, 15, 21, yf, 3 in lit)
        _win(m, 9, 14, 15, 21, yf, 4 in lit)
        m.box(11, yf - 4, 7, 15, yf - 2, 8, '#a8abb0', 0.02)
        # (AC outdoor unit mounted beside the upper window)
        m.box(12, yf - 4, 22, 15, yf - 1, 25, '#e9ebed', 0.02)
        m.disc(13.5, yf - 4.5, 22, 1.4, '#3a3e44', h=1, j=0)
    # --- side walls ---
    for sgn, xf in ((1, X1 - 1), (-1, X0)):
        _winx(m, xf, -3, 3, 5, 10, (5 if sgn > 0 else 6) in lit, sgn)
        if floors > 1:
            _winx(m, xf, -3, 3, 16, 21, (7 if sgn > 0 else 8) in lit, sgn)
    return m


def fence_gate(name='gate', w=20, seed=2, wall='#e8dfc9'):
    """low wall with pillars and a black gate in the middle, front faces -Y"""
    m = Vox(name, seed)
    hw = w // 2
    for px in (-hw, hw - 2):
        m.box(px, -1, 0, px + 2, 1, 12, wall, 0.03)
        m.box(px - 1, -1, 12, px + 3, 2, 13, '#fffdf6', 0.01)
        m.box(px, -1, 13, px + 2, 1, 14, wall, 0.02)
    for sx in (-1, 1):
        # walls between pillar and gate
        x0, x1 = (-hw + 2, -5) if sx < 0 else (5, hw - 2)
        m.box(x0, 0, 0, x1, 1, 7, wall, 0.03)
        m.box(x0, -1, 7, x1, 1, 8, '#fffdf6', 0.01)
        for x in range(x0, x1, 2):
            m.box(x, 0, 8, x + 1, 1, 12, GRILL, 0)
    for x in range(-5, 5):
        m.box(x, 0, 1, x + 1, 1, 11 if x % 2 else 12, GRILL, 0)
    m.box(-5, 0, 1, 5, 1, 2, GRILL, 0)
    m.box(-5, 0, 6, 5, 1, 7, GRILL, 0)
    m.box(-5, 0, 10, 5, 1, 11, GRILL, 0)
    m.box(-1, -1, 5, 1, 0, 7, '#d9b44a', 0)
    return m
