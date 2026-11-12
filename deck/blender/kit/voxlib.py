"""Sol deck, voxel kit: a small voxel modeller that runs inside Blender.

A Vox is a dict of cells. mesh() culls hidden faces, bakes per-corner ambient occlusion
into a vertex colour layer ("Col", linear), and writes a Blender mesh. Glowing cells go to a
second object named "<name>__e" so the web scene can light them separately.

Axes: Blender Z is up. A model's front faces -Y (toward the web camera after the glTF
Y-up conversion). 1 cell = 1 unit = 0.25 m. Author with the origin at the middle of the base.
"""
import math
import bpy

_c = {}


def _lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def rgb(h):
    """'#rrggbb' -> linear rgb tuple (tuples pass through)"""
    if not isinstance(h, str):
        return h
    if h not in _c:
        n = h.lstrip('#')
        if len(n) == 3:
            n = ''.join(ch * 2 for ch in n)
        _c[h] = tuple(_lin(int(n[i:i + 2], 16) / 255) for i in (0, 2, 4))
    return _c[h]


def _hash(x, y, z, s=0):
    h = (x * 374761393 + y * 668265263 + z * 2147483647 + s * 1274126177) & 0xffffffff
    h = ((h ^ (h >> 13)) * 1274126177) & 0xffffffff
    return ((h ^ (h >> 16)) & 0xffffffff) / 4294967296.0


AO = (0.52, 0.70, 0.86, 1.0)
# (normal, u axis, v axis): u x v = normal, so winding is counter-clockwise from outside
DIRS = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
        ((0, 1, 0), (0, 0, 1), (1, 0, 0)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
        ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (0, 1, 0), (1, 0, 0))]
CORNERS = ((0, 0), (1, 0), (1, 1), (0, 1))


class Vox:
    def __init__(self, name, seed=1, bottoms=False, scale=1.0, ao=True):
        self.name, self.seed, self.bottoms, self.scale, self.use_ao = name, seed, bottoms, scale, ao
        self.v, self.e, self.g = {}, {}, {}

    # ---------- placing cells ----------
    def set(self, x, y, z, c, j=0.03, emit=False):
        x, y, z = int(math.floor(x)), int(math.floor(y)), int(math.floor(z))
        p = (x, y, z)
        self.v.pop(p, None)
        self.e.pop(p, None)
        self.g.pop(p, None)
        if c is None:
            return
        col = rgb(c)
        if j and not emit:
            k = 1 + (_hash(x, y, z, self.seed) - 0.5) * 2 * j
            col = (col[0] * k, col[1] * k, col[2] * k)
        # emit False: lit by the sun. emit True: a window or lamp (white; switches day/night in the web scene).
        # emit 'g': always glowing, keeps its own colour.
        (self.g if emit == 'g' else self.e if emit else self.v)[p] = col

    def box(self, x0, y0, z0, x1, y1, z1, c, j=0.03, emit=False):
        for x in range(int(x0), int(x1)):
            for y in range(int(y0), int(y1)):
                for z in range(int(z0), int(z1)):
                    self.set(x, y, z, c, j, emit)

    def clear(self, x0, y0, z0, x1, y1, z1):
        self.box(x0, y0, z0, x1, y1, z1, None)

    def ring(self, x0, y0, z0, x1, y1, z1, c, t=1, j=0.03, emit=False):
        """box outline in x/y (walls) with thickness t, no cap"""
        for x in range(int(x0), int(x1)):
            for y in range(int(y0), int(y1)):
                if x < x0 + t or x >= x1 - t or y < y0 + t or y >= y1 - t:
                    for z in range(int(z0), int(z1)):
                        self.set(x, y, z, c, j, emit)

    def disc(self, cx, cy, z0, r, c, h=1, ry=None, j=0.03, emit=False, hollow=0):
        ry = r if ry is None else ry
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            for y in range(int(cy - ry - 1), int(cy + ry + 2)):
                d = ((x + .5 - cx) / r) ** 2 + ((y + .5 - cy) / ry) ** 2
                if d <= 1 and (not hollow or d >= ((r - hollow) / r) ** 2):
                    for z in range(int(z0), int(z0 + h)):
                        self.set(x, y, z, c, j, emit)

    def ball(self, cx, cy, cz, rx, ry=None, rz=None, c='#ffffff', j=0.05, emit=False, keep=1.0, seed=0):
        ry = rx if ry is None else ry
        rz = rx if rz is None else rz
        for x in range(int(cx - rx - 1), int(cx + rx + 2)):
            for y in range(int(cy - ry - 1), int(cy + ry + 2)):
                for z in range(int(cz - rz - 1), int(cz + rz + 2)):
                    d = ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 + ((z + .5 - cz) / rz) ** 2
                    if d <= 1 and (keep >= 1 or _hash(x, y, z, seed + 7) < keep):
                        cc = c[int(_hash(x, y, z, seed) * len(c)) % len(c)] if isinstance(c, (list, tuple)) else c
                        self.set(x, y, z, cc, j, emit)

    def line(self, p0, p1, c, j=0.03, emit=False, r=0):
        n = int(max(abs(p1[i] - p0[i]) for i in range(3))) * 2 + 1
        for i in range(n + 1):
            t = i / n
            x, y, z = (p0[k] + (p1[k] - p0[k]) * t for k in range(3))
            if r:
                self.box(round(x) - r, round(y) - r, round(z) - r, round(x) + r + 1, round(y) + r + 1, round(z) + r + 1, c, j, emit)
            else:
                self.set(round(x), round(y), round(z), c, j, emit)

    def text(self, s, x, y, z, c, font, px=1, emit=False, j=0, face='front'):
        """5x7 glyphs standing up, facing -Y. (x, z) is the lower-left of the first glyph."""
        for ch in s:
            g = font.get(ch)
            if g:
                for r, row in enumerate(g):
                    for q, bit in enumerate(row):
                        if bit == '1':
                            self.box(x + q * px, y, z + (6 - r) * px, x + q * px + px, y + px, z + (7 - r) * px, c, j, emit)
            x += 6 * px

    def merge(self, other, dx=0, dy=0, dz=0, rot=0, flip=False):
        """copy another model in; rot = quarter turns about Z"""
        for dct, dst in ((other.v, self.v), (other.e, self.e), (other.g, self.g)):
            for (x, y, z), col in dct.items():
                if flip:
                    x = -x - 1
                for _ in range(rot % 4):
                    x, y = -y - 1, x
                q = (x + dx, y + dy, z + dz)
                for d in (self.v, self.e, self.g):
                    d.pop(q, None)
                dst[q] = col
        return self

    def count(self):
        return len(self.v) + len(self.e) + len(self.g)

    # ---------- meshing ----------
    def _build(self, which):
        src = {'v': self.v, 'e': self.e, 'g': self.g}[which]
        solid = lambda p: p in self.v or p in self.e or p in self.g
        verts, vid, tris, cols = [], {}, [], []
        s = self.scale
        for (x, y, z), col in src.items():
            for n, u, v in DIRS:
                if n[2] < 0 and not self.bottoms:
                    continue
                if solid((x + n[0], y + n[1], z + n[2])):
                    continue
                o = (x + (n[0] > 0), y + (n[1] > 0), z + (n[2] > 0))
                ids, shade = [], []
                for a, b in CORNERS:
                    p = (o[0] + a * u[0] + b * v[0], o[1] + a * u[1] + b * v[1], o[2] + a * u[2] + b * v[2])
                    if p not in vid:
                        vid[p] = len(verts)
                        verts.append((p[0] * s, p[1] * s, p[2] * s))
                    ids.append(vid[p])
                    if which != 'v' or not self.use_ao:
                        shade.append(3)
                    else:
                        su, sv = (1 if a else -1), (1 if b else -1)
                        bx, by, bz = x + n[0], y + n[1], z + n[2]
                        s1 = solid((bx + su * u[0], by + su * u[1], bz + su * u[2]))
                        s2 = solid((bx + sv * v[0], by + sv * v[1], bz + sv * v[2]))
                        cc = solid((bx + su * u[0] + sv * v[0], by + su * u[1] + sv * v[1], bz + su * u[2] + sv * v[2]))
                        shade.append(0 if (s1 and s2) else 3 - (s1 + s2 + cc))
                if shade[0] + shade[2] > shade[1] + shade[3]:
                    order = ((0, 1, 3), (1, 2, 3))
                else:
                    order = ((0, 1, 2), (0, 2, 3))
                for t in order:
                    tris.append(tuple(ids[i] for i in t))
                    for i in t:
                        k = AO[shade[i]]
                        cols.append((col[0] * k, col[1] * k, col[2] * k, 1.0))
        return verts, tris, cols

    def objects(self, collection, mats, loc=(0, 0, 0)):
        out = []
        for which, suffix, mat in (('v', '', mats[0]), ('e', '__e', mats[1]), ('g', '__g', mats[1])):
            if not {'v': self.v, 'e': self.e, 'g': self.g}[which]:
                continue
            verts, tris, cols = self._build(which)
            me = bpy.data.meshes.new(self.name + suffix)
            me.from_pydata(verts, [], tris)
            ca = me.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
            flat = [c for col in cols for c in col]
            ca.data.foreach_set('color', flat)
            me.color_attributes.active_color = ca
            me.color_attributes.render_color_index = 0
            me.materials.append(mat)
            ob = bpy.data.objects.new(self.name + suffix, me)
            ob.location = loc
            collection.objects.link(ob)
            out.append(ob)
        return out


def make_materials():
    ms = []
    for nm, emit in (('M_vox', False), ('M_vox_emit', True)):
        m = bpy.data.materials.get(nm) or bpy.data.materials.new(nm)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        vc = nt.nodes.new('ShaderNodeVertexColor')
        vc.layer_name = 'Col'
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        if emit:
            sh = nt.nodes.new('ShaderNodeEmission')
            sh.inputs['Strength'].default_value = 2.0
            nt.links.new(vc.outputs['Color'], sh.inputs['Color'])
            nt.links.new(sh.outputs['Emission'], out.inputs['Surface'])
        else:
            sh = nt.nodes.new('ShaderNodeBsdfPrincipled')
            sh.inputs['Roughness'].default_value = 0.92
            for k in ('Specular IOR Level', 'Specular'):
                if k in sh.inputs:
                    sh.inputs[k].default_value = 0.1
            nt.links.new(vc.outputs['Color'], sh.inputs['Base Color'])
            nt.links.new(sh.outputs['BSDF'], out.inputs['Surface'])
        ms.append(m)
    return ms


FONT = {  # 5 x 7
    'S': ['01110', '10001', '10000', '01110', '00001', '10001', '01110'],
    'O': ['01110', '10001', '10001', '10001', '10001', '10001', '01110'],
    'L': ['10000', '10000', '10000', '10000', '10000', '10000', '11111'],
    '?': ['01110', '10001', '00001', '00110', '00100', '00000', '00100'],
    'P': ['11110', '10001', '10001', '11110', '10000', '10000', '10000'],
    '+': ['00000', '00100', '00100', '11111', '00100', '00100', '00000'],
    '0': ['01110', '10001', '10011', '10101', '11001', '10001', '01110'],
    '1': ['00100', '01100', '00100', '00100', '00100', '00100', '01110'],
    '2': ['01110', '10001', '00001', '00010', '00100', '01000', '11111'],
    '3': ['11110', '00001', '00001', '01110', '00001', '00001', '11110'],
    '4': ['00010', '00110', '01010', '10010', '11111', '00010', '00010'],
    '5': ['11111', '10000', '11110', '00001', '00001', '10001', '01110'],
    '6': ['01110', '10000', '10000', '11110', '10001', '10001', '01110'],
    '7': ['11111', '00001', '00010', '00100', '01000', '01000', '01000'],
}


def export_glb(objs, path):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_apply=False,
                              export_yup=True, export_normals=False, export_texcoords=False,
                              export_materials='NONE', export_vertex_color='ACTIVE',
                              export_cameras=False, export_lights=False, export_extras=False)
