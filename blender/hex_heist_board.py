"""
Hex Heist Board Game (56 cm x 34 cm) - 3D Blender Model Generator
Recreates the exact board structure, hex grid, special spaces, walls,
and starting tokens from index.html in real-world metric scale (1 unit = 1 m).
"""

import math
import bpy
import bmesh
from mathutils import Vector, Matrix

# =============================================================================
# 1. EXACT GEOMETRY & DATA FROM index.html (1 cm = 0.01 m)
# =============================================================================
CM = 0.01
BOARD_W_CM = 56.0
BOARD_H_CM = 34.0
HEX_W_CM = 5.0
R_CM = HEX_W_CM / math.sqrt(3.0)
DY_CM = 1.5 * R_CM

GRID_H_CM = 6.0 * DY_CM + 2.0 * R_CM
START_Y_CM = (BOARD_H_CM - GRID_H_CM) / 2.0 + R_CM
MARGIN_X_CM = (BOARD_W_CM - 11.0 * HEX_W_CM) / 2.0

ROW_COUNTS = [10, 11, 10, 11, 10, 11, 10]

COMANDANCIA_CELLS = {(2, 0), (3, 0), (4, 0)}

CORNERS = {
    (0, 0): {"color": "orange", "label": "START", "sub": "Thief"},
    (0, 9): {"color": "orange", "label": "START", "sub": "Thief"},
    (6, 0): {"color": "blue",   "label": "START", "sub": "Police"},
    (6, 9): {"color": "blue",   "label": "START", "sub": "Police"},
}

HEISTS = {
    (0, 7):  {"type": "Bank",     "amount": 20000},
    (2, 4):  {"type": "Bank",     "amount": 20000},
    (6, 5):  {"type": "Bank",     "amount": 20000},
    (1, 2):  {"type": "Jewelry",  "amount": 15000},
    (3, 10): {"type": "Jewelry",  "amount": 15000},
    (5, 2):  {"type": "Jewelry",  "amount": 15000},
    (3, 3):  {"type": "Market",   "amount": 10000},
    (6, 7):  {"type": "Market",   "amount": 10000},
    (0, 5):  {"type": "Farmacia", "amount": 5000},
    (3, 8):  {"type": "Farmacia", "amount": 5000},
    (5, 4):  {"type": "Farmacia", "amount": 5000},
    (0, 3):  {"type": "Oxxo",     "amount": 3000},
    (3, 6):  {"type": "Oxxo",     "amount": 3000},
    (5, 9):  {"type": "Oxxo",     "amount": 3000},
}

BALANCED_WALLS = [
    ((0, 1), (0, 2)),
    ((0, 2), (0, 3)),
    ((0, 8), (0, 9)),
    ((0, 8), (1, 9)),
    ((1, 1), (1, 2)),
    ((1, 3), (1, 4)),
    ((1, 5), (2, 5)),
    ((1, 6), (1, 7)),
    ((1, 8), (1, 9)),
    ((1, 8), (2, 7)),
    ((1, 8), (2, 8)),
    ((2, 1), (2, 2)),
    ((2, 4), (3, 4)),
    ((2, 5), (3, 5)),
    ((3, 10), (4, 9)),
    ((3, 2), (4, 2)),
    ((3, 4), (4, 4)),
    ((3, 7), (3, 8)),
    ((4, 1), (4, 2)),
    ((4, 1), (5, 2)),
    ((4, 2), (5, 3)),
    ((4, 4), (4, 5)),
    ((4, 7), (5, 8)),
    ((4, 8), (5, 8)),
    ((4, 8), (5, 9)),
    ((4, 9), (5, 10)),
    ((5, 1), (5, 2)),
    ((5, 1), (6, 1)),
    ((5, 6), (5, 7)),
    ((6, 0), (6, 1)),
]

INITIAL_TOKENS = [
    {"id": "P1", "role": "police", "cell": (6, 0)},
    {"id": "P2", "role": "police", "cell": (6, 9)},
    {"id": "T1", "role": "thief",  "cell": (0, 0)},
    {"id": "T2", "role": "thief",  "cell": (0, 9)},
]


def hex_center_m(row, col):
    """Convert (row, col) to Blender world (x, y) in meters, centered at (0,0)."""
    is_odd_count = (ROW_COUNTS[row] == 10)
    x_offset = 1.0 if is_odd_count else 0.5
    cx_cm = MARGIN_X_CM + (col + x_offset) * HEX_W_CM
    cy_cm = START_Y_CM + row * DY_CM
    # Map SVG top-left to Blender centered (+Y = row 0 top, -Y = row 6 bottom)
    x_m = (cx_cm - BOARD_W_CM / 2.0) * CM
    y_m = (BOARD_H_CM / 2.0 - cy_cm) * CM
    return x_m, y_m


def hex_vertices_2d(cx, cy, radius_m):
    """Pointy-top hex vertices matching index.html (-90 + i*60 deg in SVG -> +90 - i*60 in Blender)."""
    pts = []
    for i in range(6):
        # In SVG, y points down so angle = (-90 + i*60) deg puts i=0 at top (0, -R) -> in Blender +Y is top (0, +R)
        angle = math.radians(90.0 - i * 60.0)
        pts.append((cx + radius_m * math.cos(angle), cy + radius_m * math.sin(angle)))
    return pts


# =============================================================================
# 2. SCENE CLEANUP & COLLECTIONS
# =============================================================================
def clear_scene():
    if bpy.context.active_object and bpy.context.active_object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)


def get_or_create_collection(name, parent=None):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    if parent is None:
        bpy.context.scene.collection.children.link(col)
    else:
        parent.children.link(col)
    return col


# =============================================================================
# 3. MATERIALS
# =============================================================================
def hex_to_rgba(hex_str, alpha=1.0):
    hex_str = hex_str.lstrip("#")
    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    # sRGB to linear approximation for Principled BSDF
    def to_lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (to_lin(r), to_lin(g), to_lin(b), alpha)


def make_material(name, hex_color, roughness=0.45, metallic=0.0):
    if name in bpy.data.materials:
        mat = bpy.data.materials[name]
    else:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = hex_to_rgba(hex_color)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def create_materials():
    return {
        "board_base":     make_material("BoardBase",     "#ebe5d8", roughness=0.6),
        "board_rim":      make_material("BoardRim",      "#334155", roughness=0.4, metallic=0.1),
        "hex_street":     make_material("HexStreet",     "#e5dfd2", roughness=0.55),
        "hex_heist":      make_material("HexHeist",      "#dc2626", roughness=0.4),
        "hex_orange":     make_material("CornerOrange",  "#f97316", roughness=0.35),
        "hex_blue":       make_material("CornerBlue",    "#2563eb", roughness=0.35),
        "comandancia":    make_material("Comandancia",   "#374151", roughness=0.45),
        "hex_border":     make_material("HexBoldBorder", "#1e293b", roughness=0.5),
        "wall_dark":      make_material("WallDark",      "#111827", roughness=0.35),
        "wall_trim":      make_material("WallTrim",      "#f8fafc", roughness=0.5),
        "token_p1":       make_material("TokenP1",       "#2563eb", roughness=0.25),
        "token_p2":       make_material("TokenP2",       "#0284c7", roughness=0.25),
        "token_t1":       make_material("TokenT1",       "#f97316", roughness=0.25),
        "token_t2":       make_material("TokenT2",       "#d97706", roughness=0.25),
        "token_rim":      make_material("TokenRim",      "#0f172a", roughness=0.3),
        "gold":           make_material("GoldAccent",    "#facc15", roughness=0.2, metallic=0.8),
        "white":          make_material("WhiteAccent",   "#f8fafc", roughness=0.3),
        "silver":         make_material("SilverAccent",  "#cbd5e1", roughness=0.25, metallic=0.7),
        "emerald":        make_material("EmeraldAccent", "#22c55e", roughness=0.25),
        "cyan_gem":       make_material("CyanGem",       "#38bdf8", roughness=0.1, metallic=0.1),
    }


# =============================================================================
# 4. MESH HELPERS
# =============================================================================
def create_prism_from_2d(name, pts_2d, z0, z1, collection, material=None, bevel_width=0.0):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()

    bot_verts = [bm.verts.new((x, y, z0)) for (x, y) in pts_2d]
    top_verts = [bm.verts.new((x, y, z1)) for (x, y) in pts_2d]

    bm.faces.new(list(reversed(bot_verts)))
    bm.faces.new(top_verts)

    n = len(pts_2d)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([bot_verts[i], bot_verts[j], top_verts[j], top_verts[i]])

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)

    if bevel_width > 0:
        bev = obj.modifiers.new(name="Bevel", type="BEVEL")
        bev.width = bevel_width
        bev.segments = 2
        bev.limit_method = "ANGLE"

    return obj


def create_box(name, cx, cy, z0, sx, sy, sz, collection, material, rot_z=0.0, bevel=0.0):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    obj.location = (cx, cy, z0 + sz / 2.0)
    obj.rotation_euler = (0.0, 0.0, rot_z)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    if bevel > 0:
        bev = obj.modifiers.new(name="Bevel", type="BEVEL")
        bev.width = bevel
        bev.segments = 2
    return obj


def create_cylinder(name, cx, cy, z0, radius, height, segments, collection, material, rot_z=0.0):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=height,
    )
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    obj.location = (cx, cy, z0 + height / 2.0)
    obj.rotation_euler = (0.0, 0.0, rot_z)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


# =============================================================================
# 5. BUILD BOARD COMPONENTS
# =============================================================================
def build_board_base(col, mats):
    w = BOARD_W_CM * CM
    h = BOARD_H_CM * CM
    rx = (10.0 / 18.0) * CM  # 10px @ 18px/cm
    base_h = 0.010

    # Rounded rectangle 2D profile
    pts = []
    segs = 6
    corners = [
        ( w / 2 - rx,  h / 2 - rx, 0),
        (-w / 2 + rx,  h / 2 - rx, math.pi / 2),
        (-w / 2 + rx, -h / 2 + rx, math.pi),
        ( w / 2 - rx, -h / 2 + rx, 3 * math.pi / 2),
    ]
    for cx, cy, a0 in corners:
        for i in range(segs + 1):
            a = a0 + (math.pi / 2) * (i / segs)
            pts.append((cx + rx * math.cos(a), cy + rx * math.sin(a)))

    base = create_prism_from_2d(
        "GameBoardBase", pts, 0.0, base_h, col, mats["board_base"], bevel_width=0.0008
    )

    # Outer rim frame slightly wider & taller edge
    rim_t = 0.006
    rim_h = 0.0115
    w_out = w + 2 * rim_t
    h_out = h + 2 * rim_t
    rx_out = rx + rim_t

    mesh = bpy.data.meshes.new("GameBoardRim")
    bm = bmesh.new()

    outer_pts = []
    corners_out = [
        ( w_out / 2 - rx_out,  h_out / 2 - rx_out, 0),
        (-w_out / 2 + rx_out,  h_out / 2 - rx_out, math.pi / 2),
        (-w_out / 2 + rx_out, -h_out / 2 + rx_out, math.pi),
        ( w_out / 2 - rx_out, -h_out / 2 + rx_out, 3 * math.pi / 2),
    ]
    for cx, cy, a0 in corners_out:
        for i in range(segs + 1):
            a = a0 + (math.pi / 2) * (i / segs)
            outer_pts.append((cx + rx_out * math.cos(a), cy + rx_out * math.sin(a)))

    n = len(pts)
    ob = [bm.verts.new((x, y, 0.0)) for (x, y) in outer_pts]
    ot = [bm.verts.new((x, y, rim_h)) for (x, y) in outer_pts]
    ib = [bm.verts.new((x, y, 0.0)) for (x, y) in pts]
    it = [bm.verts.new((x, y, rim_h)) for (x, y) in pts]

    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([ob[i], ob[j], ot[j], ot[i]])
        bm.faces.new([it[i], it[j], ib[j], ib[i]])
        bm.faces.new([ot[i], ot[j], it[j], it[i]])
        bm.faces.new([ib[i], ib[j], ob[j], ob[i]])

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()

    rim = bpy.data.objects.new("GameBoardRim", mesh)
    col.objects.link(rim)
    rim.data.materials.append(mats["board_rim"])
    bev = rim.modifiers.new(name="Bevel", type="BEVEL")
    bev.width = 0.0006
    bev.segments = 2

    return base_h


def build_hex_grid(col, mats, z_base):
    r_m = R_CM * CM
    gap_scale = 0.965

    for r in range(len(ROW_COUNTS)):
        for c in range(ROW_COUNTS[r]):
            cell = (r, c)
            if cell in COMANDANCIA_CELLS:
                continue

            cx, cy = hex_center_m(r, c)
            name = f"Hex_r{r:02d}_c{c:02d}"

            if cell in CORNERS:
                corner = CORNERS[cell]
                mat = mats["hex_orange"] if corner["color"] == "orange" else mats["hex_blue"]
                pts = hex_vertices_2d(cx, cy, r_m * 1.15 * gap_scale)
                create_prism_from_2d(name, pts, z_base, z_base + 0.0040, col, mat, bevel_width=0.0005)
            elif cell in HEISTS:
                pts = hex_vertices_2d(cx, cy, r_m * gap_scale)
                create_prism_from_2d(name, pts, z_base, z_base + 0.0030, col, mats["hex_heist"], bevel_width=0.0004)
            else:
                pts = hex_vertices_2d(cx, cy, r_m * gap_scale)
                create_prism_from_2d(name, pts, z_base, z_base + 0.0020, col, mats["hex_street"], bevel_width=0.0003)

    # Comandancia merged polygon: (2,0), (3,0), (4,0)
    c20 = hex_center_m(2, 0)
    c30 = hex_center_m(3, 0)
    c40 = hex_center_m(4, 0)
    v20 = hex_vertices_2d(c20[0], c20[1], r_m)
    v30 = hex_vertices_2d(c30[0], c30[1], r_m)
    v40 = hex_vertices_2d(c40[0], c40[1], r_m)

    com_pts = [
        v20[0], v20[1], v20[2], v20[3],
        v30[2],
        v40[1], v40[2], v40[3], v40[4], v40[5],
        v30[4], v30[5], v30[0],
        v20[5],
    ]
    create_prism_from_2d("Comandancia", com_pts, z_base, z_base + 0.0045, col, mats["comandancia"], bevel_width=0.0006)


def add_ring_to_bmesh(bm, pts_2d, half_width, z0, z1):
    """Add a closed 3D border ring around a 2D polygon into an existing bmesh."""
    n = len(pts_2d)
    cx = sum(p[0] for p in pts_2d) / n
    cy = sum(p[1] for p in pts_2d) / n

    # Compute inward/outward offset along vertex normals (or radial for convex, edge-normal for general)
    outer_pts = []
    inner_pts = []
    for i in range(n):
        p_prev = Vector(pts_2d[(i - 1) % n])
        p_curr = Vector(pts_2d[i])
        p_next = Vector(pts_2d[(i + 1) % n])

        e1 = (p_curr - p_prev).normalized()
        e2 = (p_next - p_curr).normalized()
        # Outward normals for CCW polygon in XY: (dy, -dx)
        n1 = Vector((e1.y, -e1.x))
        n2 = Vector((e2.y, -e2.x))
        bis = n1 + n2
        if bis.length < 1e-6:
            bis = n1
        else:
            bis.normalize()
        # Ensure bis points outward relative to centroid
        if bis.dot(p_curr - Vector((cx, cy))) < 0 and n == 6:
            bis = -bis
        denom = max(0.35, bis.dot(n1))
        offset = bis * (half_width / denom)
        outer_pts.append((p_curr.x + offset.x, p_curr.y + offset.y))
        inner_pts.append((p_curr.x - offset.x, p_curr.y - offset.y))

    ob = [bm.verts.new((x, y, z0)) for (x, y) in outer_pts]
    ot = [bm.verts.new((x, y, z1)) for (x, y) in outer_pts]
    ib = [bm.verts.new((x, y, z0)) for (x, y) in inner_pts]
    it = [bm.verts.new((x, y, z1)) for (x, y) in inner_pts]

    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([ob[i], ob[j], ot[j], ot[i]])
        bm.faces.new([it[i], it[j], ib[j], ib[i]])
        bm.faces.new([ot[i], ot[j], it[j], it[i]])
        bm.faces.new([ib[i], ib[j], ob[j], ob[i]])


def build_hex_bold_borders(col, mats, z_base):
    """Create bold dark border lines around every hex tile and Comandancia for clear upper-view visibility."""
    r_m = R_CM * CM
    gap_scale = 0.965
    half_w = 0.0009  # 1.8 mm total bold line thickness

    mesh = bpy.data.meshes.new("HexGrid_BoldBorders")
    bm = bmesh.new()

    for r in range(len(ROW_COUNTS)):
        for c in range(ROW_COUNTS[r]):
            cell = (r, c)
            if cell in COMANDANCIA_CELLS:
                continue
            cx, cy = hex_center_m(r, c)
            if cell in CORNERS:
                pts = hex_vertices_2d(cx, cy, r_m * 1.15 * gap_scale)
                z_top = z_base + 0.0040
            elif cell in HEISTS:
                pts = hex_vertices_2d(cx, cy, r_m * gap_scale)
                z_top = z_base + 0.0030
            else:
                pts = hex_vertices_2d(cx, cy, r_m * gap_scale)
                z_top = z_base + 0.0020

            add_ring_to_bmesh(bm, pts, half_w, z_top - 0.0002, z_top + 0.0007)

    # Comandancia bold border
    c20 = hex_center_m(2, 0)
    c30 = hex_center_m(3, 0)
    c40 = hex_center_m(4, 0)
    v20 = hex_vertices_2d(c20[0], c20[1], r_m)
    v30 = hex_vertices_2d(c30[0], c30[1], r_m)
    v40 = hex_vertices_2d(c40[0], c40[1], r_m)
    com_pts = [
        v20[0], v20[1], v20[2], v20[3],
        v30[2],
        v40[1], v40[2], v40[3], v40[4], v40[5],
        v30[4], v30[5], v30[0],
        v20[5],
    ]
    add_ring_to_bmesh(bm, com_pts, half_w * 1.15, z_base + 0.0043, z_base + 0.0052)

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("HexGrid_BoldBorders", mesh)
    col.objects.link(obj)
    obj.data.materials.append(mats["hex_border"])


def build_heist_and_comandancia_structures(col, mats, z_base):
    """Add miniature 3D architectural markers on Comandancia and the 14 Heist spaces."""
    # Comandancia jail structure at center of (2,0), (3,0), (4,0)
    c20 = hex_center_m(2, 0)
    c30 = hex_center_m(3, 0)
    c40 = hex_center_m(4, 0)
    com_x = (c20[0] + c30[0] + c40[0]) / 3.0
    com_y = (c20[1] + c30[1] + c40[1]) / 3.0
    z_com = z_base + 0.0045

    create_box("Comandancia_Building", com_x, com_y, z_com, 0.032, 0.056, 0.010, col, mats["wall_dark"], bevel=0.0006)
    create_box("Comandancia_Roof", com_x, com_y, z_com + 0.010, 0.035, 0.059, 0.0025, col, mats["hex_blue"], bevel=0.0005)
    # Jail bars accent on front
    for dy in (-0.018, -0.009, 0.0, 0.009, 0.018):
        create_cylinder(f"Comandancia_Bar_{dy:+.3f}", com_x + 0.0165, com_y + dy, z_com, 0.0009, 0.010, 8, col, mats["silver"])

    # Heist miniature buildings
    z_h = z_base + 0.0030
    for (r, c), info in HEISTS.items():
        cx, cy = hex_center_m(r, c)
        htype = info["type"]
        prefix = f"Heist_{htype}_r{r:02d}_c{c:02d}"

        if htype == "Bank":
            # Classical bank with plinth, body, columns, and gold pediment
            create_box(f"{prefix}_Base", cx, cy, z_h, 0.028, 0.024, 0.003, col, mats["white"], bevel=0.0004)
            create_box(f"{prefix}_Body", cx, cy + 0.002, z_h + 0.003, 0.022, 0.016, 0.011, col, mats["silver"], bevel=0.0004)
            for dx in (-0.008, 0.0, 0.008):
                create_cylinder(f"{prefix}_Col_{dx:+.3f}", cx + dx, cy - 0.008, z_h + 0.003, 0.0016, 0.011, 10, col, mats["white"])
            create_box(f"{prefix}_Roof", cx, cy, z_h + 0.014, 0.026, 0.022, 0.003, col, mats["gold"], bevel=0.0004)

        elif htype == "Jewelry":
            # Display pedestal + diamond octahedron
            create_cylinder(f"{prefix}_Pedestal", cx, cy, z_h, 0.011, 0.005, 8, col, mats["token_rim"])
            mesh = bpy.data.meshes.new(f"{prefix}_Gem")
            bm = bmesh.new()
            bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.0075)
            bmesh.ops.scale(bm, vec=(1.0, 1.0, 1.3), verts=bm.verts)
            bm.to_mesh(mesh)
            bm.free()
            gem = bpy.data.objects.new(f"{prefix}_Gem", mesh)
            gem.location = (cx, cy, z_h + 0.012)
            col.objects.link(gem)
            gem.data.materials.append(mats["cyan_gem"])

        elif htype == "Market":
            # Wide market hall with striped awning
            create_box(f"{prefix}_Body", cx, cy, z_h, 0.024, 0.018, 0.008, col, mats["white"], bevel=0.0004)
            create_box(f"{prefix}_Awning", cx, cy - 0.006, z_h + 0.007, 0.026, 0.010, 0.002, col, mats["emerald"], bevel=0.0003)

        elif htype == "Farmacia":
            # Pharmacy box + green cross on top
            create_box(f"{prefix}_Body", cx, cy, z_h, 0.020, 0.018, 0.008, col, mats["white"], bevel=0.0004)
            create_box(f"{prefix}_CrossH", cx, cy, z_h + 0.008, 0.012, 0.004, 0.0025, col, mats["emerald"])
            create_box(f"{prefix}_CrossV", cx, cy, z_h + 0.008, 0.004, 0.012, 0.0025, col, mats["emerald"])

        elif htype == "Oxxo":
            # Compact convenience store with orange/yellow sign band
            create_box(f"{prefix}_Body", cx, cy, z_h, 0.018, 0.014, 0.007, col, mats["white"], bevel=0.0003)
            create_box(f"{prefix}_Sign", cx, cy, z_h + 0.007, 0.019, 0.015, 0.0025, col, mats["hex_orange"], bevel=0.0003)


def build_walls(col, mats, z_base):
    r_m = R_CM * CM
    wall_len = r_m * 0.96
    wall_thick = 0.0036
    wall_h = 0.012

    for idx, (a, b) in enumerate(BALANCED_WALLS):
        ax, ay = hex_center_m(*a)
        bx, by = hex_center_m(*b)
        mx = (ax + bx) / 2.0
        my = (ay + by) / 2.0
        dx = bx - ax
        dy = by - ay
        # Edge is perpendicular to vector (dx, dy)
        edge_angle = math.atan2(dy, dx) + math.pi / 2.0

        # Light base strip + dark wall barrier matching index.html
        create_box(
            f"Wall_{idx:02d}_Base", mx, my, z_base + 0.002,
            wall_len + 0.002, wall_thick + 0.002, 0.002,
            col, mats["wall_trim"], rot_z=edge_angle, bevel=0.0003
        )
        create_box(
            f"Wall_{idx:02d}", mx, my, z_base + 0.004,
            wall_len, wall_thick, wall_h,
            col, mats["wall_dark"], rot_z=edge_angle, bevel=0.0005
        )


def build_tokens(col, mats, z_base):
    z_t = z_base + 0.0040
    for tok in INITIAL_TOKENS:
        tid = tok["id"]
        cx, cy = hex_center_m(*tok["cell"])

        if tid == "P1":
            # Octagon shield + gold star cap
            create_cylinder("Token_P1_Rim", cx, cy, z_t, 0.013, 0.004, 8, col, mats["token_rim"], rot_z=math.pi / 8)
            create_cylinder("Token_P1_Body", cx, cy, z_t + 0.004, 0.011, 0.008, 8, col, mats["token_p1"], rot_z=math.pi / 8)
            create_cylinder("Token_P1_Star", cx, cy, z_t + 0.012, 0.005, 0.002, 5, col, mats["gold"])
        elif tid == "P2":
            # Hexagon badge + silver chevron cap
            create_cylinder("Token_P2_Rim", cx, cy, z_t, 0.013, 0.004, 6, col, mats["token_rim"])
            create_cylinder("Token_P2_Body", cx, cy, z_t + 0.004, 0.011, 0.008, 6, col, mats["token_p2"])
            create_cylinder("Token_P2_Cap", cx, cy, z_t + 0.012, 0.005, 0.002, 6, col, mats["silver"])
        elif tid == "T1":
            # Cylinder + dark bandit mask band
            create_cylinder("Token_T1_Rim", cx, cy, z_t, 0.013, 0.004, 24, col, mats["token_rim"])
            create_cylinder("Token_T1_Body", cx, cy, z_t + 0.004, 0.011, 0.009, 24, col, mats["token_t1"])
            create_cylinder("Token_T1_Mask", cx, cy, z_t + 0.010, 0.0114, 0.0025, 24, col, mats["token_rim"])
        elif tid == "T2":
            # Rounded square / box + hood accent
            create_box("Token_T2_Rim", cx, cy, z_t, 0.023, 0.023, 0.004, col, mats["token_rim"], bevel=0.003)
            create_box("Token_T2_Body", cx, cy, z_t + 0.004, 0.019, 0.019, 0.009, col, mats["token_t2"], bevel=0.0025)
            create_box("Token_T2_Hood", cx, cy, z_t + 0.013, 0.012, 0.012, 0.0025, col, mats["token_rim"], bevel=0.001)


def setup_camera_and_lighting(col):
    # Main Studio Key Light
    light_data = bpy.data.lights.new(name="KeyLight", type="AREA")
    light_data.energy = 80.0
    light_data.size = 0.8
    key_light = bpy.data.objects.new(name="KeyLight", object_data=light_data)
    key_light.location = (0.35, -0.35, 0.75)
    key_light.rotation_euler = (math.radians(28), math.radians(20), 0.0)
    col.objects.link(key_light)

    # Fill Light
    fill_data = bpy.data.lights.new(name="FillLight", type="AREA")
    fill_data.energy = 35.0
    fill_data.size = 1.0
    fill_light = bpy.data.objects.new(name="FillLight", object_data=fill_data)
    fill_light.location = (-0.45, 0.35, 0.65)
    fill_light.rotation_euler = (math.radians(-25), math.radians(-25), 0.0)
    col.objects.link(fill_light)

    # Camera angled top-down 3/4 view showing entire 56x34 cm board
    cam_data = bpy.data.cameras.new(name="Camera")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new(name="Camera", object_data=cam_data)
    cam.location = (0.0, -0.38, 0.68)
    # Point at (0, 0, 0.01)
    direction = Vector((0.0, 0.0, 0.01)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    col.objects.link(cam)
    bpy.context.scene.camera = cam

    # Render settings
    bpy.context.scene.render.resolution_x = 1600
    bpy.context.scene.render.resolution_y = 1000
    available_engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    if "BLENDER_EEVEE" in available_engines:
        bpy.context.scene.render.engine = "BLENDER_EEVEE"
    elif "CYCLES" in available_engines:
        bpy.context.scene.render.engine = "CYCLES"
        bpy.context.scene.cycles.samples = 32


def build_all():
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0

    clear_scene()
    mats = create_materials()

    col_setup = get_or_create_collection("SceneSetup")
    col_base = get_or_create_collection("BoardBase")
    col_hex = get_or_create_collection("HexGrid")
    col_heists = get_or_create_collection("HeistStructures")
    col_walls = get_or_create_collection("Walls")
    col_tokens = get_or_create_collection("Tokens")

    z_base = build_board_base(col_base, mats)
    build_hex_grid(col_hex, mats, z_base)
    build_hex_bold_borders(col_hex, mats, z_base)
    build_heist_and_comandancia_structures(col_heists, mats, z_base)
    build_walls(col_walls, mats, z_base)
    build_tokens(col_tokens, mats, z_base)
    setup_camera_and_lighting(col_setup)

    return {
        "hex_tiles": sum(ROW_COUNTS) - len(COMANDANCIA_CELLS),
        "comandancia": 1,
        "heist_spots": len(HEISTS),
        "walls": len(BALANCED_WALLS),
        "tokens": len(INITIAL_TOKENS),
        "total_objects": len(bpy.data.objects),
    }


if __name__ == "__main__":
    summary = build_all()
    print("Built Hex Heist Board:", summary)
