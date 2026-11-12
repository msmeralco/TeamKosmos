"""Render a quick contact sheet of Vox models inside Blender for visual QA."""
import bpy, math
from mathutils import Vector
import voxlib


def setup(res=(1600, 900), sky='#cfe3f2', sun_e=3.2):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.image_settings.file_format = 'PNG'
    try:
        sc.view_settings.view_transform = 'Standard'
    except Exception:
        pass
    w = sc.world or bpy.data.worlds.new('W')
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    r = voxlib.rgb(sky)
    bg.inputs['Color'].default_value = (r[0], r[1], r[2], 1)
    bg.inputs['Strength'].default_value = 1.0
    for o in [o for o in bpy.data.objects if o.type in ('LIGHT', 'CAMERA')]:
        bpy.data.objects.remove(o, do_unlink=True)
    ld = bpy.data.lights.new('sun', 'SUN')
    ld.energy = sun_e
    ld.angle = math.radians(2)
    lo = bpy.data.objects.new('sun', ld)
    bpy.context.scene.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(52), math.radians(8), math.radians(-35))
    return sc


def shoot(center, size, path, yaw=-35, pitch=58, res=(1600, 900), persp=0):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new('cam')
    cd.type = 'ORTHO'
    cd.ortho_scale = size
    cd.clip_end = 5000
    co = bpy.data.objects.new('cam', cd)
    sc.collection.objects.link(co)
    d = 900
    yw, pt = math.radians(yaw), math.radians(pitch)
    off = Vector((math.sin(yw) * math.cos(pt), -math.cos(yw) * math.cos(pt), math.sin(pt))) * d
    co.location = Vector(center) + off
    co.rotation_euler = (-(Vector(center) - co.location)).to_track_quat('Z', 'Y').to_euler()
    sc.camera = co
    sc.render.filepath = path
    sc.render.resolution_x, sc.render.resolution_y = res
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(co, do_unlink=True)
    bpy.data.cameras.remove(cd)
