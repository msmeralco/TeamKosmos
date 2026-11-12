"""Run inside Blender (MCP): meshes the whole kit, lays it out as a catalogue, exports world/kit.glb and saves the .blend.

    exec(open('<repo>/deck/blender/kit/build_kit.py').read())
"""
import sys, importlib, os, time
import bpy

K = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else '/Users/shimijallores/Downloads/competitions/sol/deck/blender/kit'
DECK = os.path.dirname(os.path.dirname(K))
if K not in sys.path:
    sys.path.insert(0, K)
import voxlib, models_a, models_b, models_c, models_d, catalog
for mod in (voxlib, models_a, models_b, models_c, models_d, catalog):
    importlib.reload(mod)


def build(only=None):
    t0 = time.time()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    col = bpy.data.collections.get('KIT') or bpy.data.collections.new('KIT')
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    mats = voxlib.make_materials()
    stats, objs, rows = {}, [], {}
    y = 0
    for gname, models in catalog.groups().items():
        if only and gname not in only:
            continue
        x, rowh = 0, 0
        for m in models:
            cells = list(m.v) + list(m.e) + list(m.g)
            if not cells:
                continue
            s = m.scale
            x0 = min(c[0] for c in cells) * s
            x1 = (max(c[0] for c in cells) + 1) * s
            y0 = min(c[1] for c in cells) * s
            y1 = (max(c[1] for c in cells) + 1) * s
            if gname in ('ground', 'far') and x > 400:
                y += rowh + 20
                x, rowh = 0, 0
            made = m.objects(col, mats, (x - x0, y - y0, 0))
            objs += made
            stats[m.name] = m.count()
            rows.setdefault(gname, []).append((m.name, x, y, x1 - x0, y1 - y0))
            x += (x1 - x0) + 14
            rowh = max(rowh, y1 - y0)
        y += rowh + 24
    return objs, stats, rows, time.time() - t0


def export(objs, name='kit.glb'):
    out = os.path.join(DECK, 'world')
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name)
    voxlib.export_glb(objs, path)
    return path, os.path.getsize(path)
