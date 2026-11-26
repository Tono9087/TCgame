"""
ROB AND RUN — Generador procedural del tablero 3D (91 casillas hexagonales).

Uso dentro de Blender (Text Editor o consola de Python):
    p = "/home/Tono/Documents/TCgame/blender/rob_and_run_board.py"
    ns = {"__file__": p, "RUN_MODE": "build"}      # "build" | "render" | "save"
    exec(compile(open(p).read(), p, "exec"), ns)

Fuera de Blender (`python3 rob_and_run_board.py`) solo resuelve y valida el
layout de juego (registro coordenada->rol, muros, navegación) e imprime el informe.

Convenciones
- Coordenadas axiales (q, r), hexágonos flat-top, R = 1 m.
- +Y = Norte (Comisaría en (0,5)), -Y = Sur (Guarida en (0,-5)).
- Los edificios miran al Sur (-Y), hacia la cámara principal.
"""
import math
import json
import os
import random
from collections import Counter, deque

try:
    import bpy
    import bmesh
    from mathutils import Vector, Matrix
    HAS_BPY = True
except ImportError:  # ejecución fuera de Blender
    HAS_BPY = False

# =============================================================================
# 1. PARÁMETROS
# =============================================================================
N = 5                 # radio del tablero en casillas
R = 1.0               # radio exterior de cada hexágono
GAP = 0.96            # escala XY de cada casilla (separación ~4 %)
H_TILE = 0.12
H_SPECIAL = 0.18      # comisaría y guarida
H_BLOCK = 0.85        # manzanas cerradas
TILE_BEVEL = 0.03

ALLEY_WALL_T = 0.14
ALLEY_WALL_H = 0.55
BANK_WALL_T = 0.12
BANK_WALL_H = 0.45

BASE_RADIUS = 10.9    # ver informe: 9.2 m no contiene el panal de radio 5 (mínimo ~9.77 m)
BASE_Z0, BASE_Z1 = -0.16, 0.04

BASE_DIR = os.path.dirname(os.path.abspath(globals().get("__file__", "./x.py")))
RENDER_DIR = os.path.join(BASE_DIR, "renders")
BLEND_PATH = os.path.join(BASE_DIR, "rob_and_run_board.blend")
REPORT_JSON = os.path.join(BASE_DIR, "reporte_tablero.json")
REPORT_MD = os.path.join(BASE_DIR, "reporte_tablero.md")

# =============================================================================
# 2. ESPECIFICACIÓN DE JUEGO (coordenadas iniciales del encargo)
# =============================================================================
SPEC = {
    "comisaria":   [(0, 5)],
    "guarida":     [(0, -5)],
    "botin_bajo":  [(-4, -1), (4, -5), (-4, 3), (4, -1), (-2, -3), (2, -5), (-2, 4), (2, 2)],
    "botin_medio": [(-3, 1), (3, -2), (-2, 0), (2, -2), (-1, 2), (1, 1)],
    "boveda":      [(0, 0)],
    "bonus":       [(-5, 3), (5, -2), (-5, 0), (5, -5), (-2, -1), (2, 1), (0, -3), (0, 3)],
    "bloqueo":     [(-1, -1), (1, -2), (-2, 1), (2, -1), (-3, 2), (3, -2)],
}
# Nombres tal como vienen en el encargo (ver informe: dos etiquetas no coinciden
# con su posición real en el mundo).
ALLEYS_SPEC = {
    "Suroeste": [(-4, 0), (-3, 0), (-2, 0)],
    "Sureste":  [(2, 0), (3, 0), (4, 0)],
    "Noroeste": [(-3, 3), (-2, 2), (-1, 1)],
    "Noreste":  [(1, -1), (2, -2), (3, -3)],
}
BANK_WALLS_SPEC = [((0, 1), (-1, 1)), ((0, 1), (1, 0)), ((0, -1), (-1, 0)), ((0, -1), (1, -1))]
BANK_APPROACHES = [(0, 1), (0, -1)]

EXPECTED_COUNTS = {"comisaria": 1, "guarida": 1, "botin_bajo": 8, "botin_medio": 6, "boveda": 1,
                   "bonus": 8, "callejon": 12, "bloqueo": 6}

# Resolución de conflictos (categoría, original, nueva, motivo).
# Prioridad del encargo: bases > banco > robos > callejones > bonus > bloqueos > calles.
# Un callejón es un elemento indivisible de 3 casillas: mover una sola casilla lo
# rompería, así que en colisiones robo-vs-callejón se reubica el robo (que conserva
# su valor) y el corredor queda intacto. Ningún elemento se elimina.
RELOCATIONS = [
    ("botin_medio", (-2, 0), (-3, -1),
     "Colisiona con el callejón Suroeste. El corredor es indivisible; el robo medio se mueve "
     "al hueco libre adyacente al callejón y conserva su valor."),
    ("botin_medio", (2, -2), (3, -4),
     "Colisiona con el callejón Noreste. Se usa la posición espejo (eje X) de la reubicación "
     "anterior para mantener la simetría Este-Oeste del layout."),
    ("bloqueo", (3, -2), (3, -1),
     "Colisiona con Botín Medio (3,-2), de mayor prioridad. (3,-1) es el espejo exacto del "
     "bloqueo (-3,2)."),
    ("bloqueo", (-2, 1), (-2, 3),
     "Conflicto de navegación: junto al bloqueo (-1,-1), el muro especificado (0,-1)|(-1,0) y "
     "el cierre lateral del banco, dejaba la calle (-1,0) como un bolsillo inalcanzable para la "
     "policía. Se desplaza un anillo hacia fuera dentro del mismo sector Noroeste."),
]

DIRS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def in_grid(c):
    q, r = c
    return max(abs(q), abs(r), abs(q + r)) <= N


def nbrs(c):
    return [add(c, d) for d in DIRS]


def ekey(a, b):
    return tuple(sorted((a, b)))


def axial_xy(q, r):
    return (R * 1.5 * q, R * math.sqrt(3) * (r + q / 2.0))


def dir_angle(di):
    x, y = axial_xy(*DIRS[di])
    return math.atan2(y, x)


def grid_cells():
    return [(q, r) for q in range(-N, N + 1) for r in range(max(-N, -q - N), min(N, -q + N) + 1)]


# =============================================================================
# 3. LAYOUT: registro coordenada -> rol, salidas de callejones, muros
# =============================================================================
def resolve_layout():
    cells = grid_cells()
    rep = {"colisiones_detectadas": [], "reubicaciones": [], "salidas_callejon": [], "muros_log": []}

    claims = {}
    for cat, cs in SPEC.items():
        for c in cs:
            claims.setdefault(c, []).append(cat)
    for name, cs in ALLEYS_SPEC.items():
        for c in cs:
            claims.setdefault(c, []).append("callejon:" + name)
    for c, cl in sorted(claims.items()):
        if not in_grid(c):
            raise ValueError(f"Coordenada fuera del tablero: {c} ({cl})")
        if len(cl) > 1:
            rep["colisiones_detectadas"].append({"coord": list(c), "categorias": cl})

    spec = {k: list(v) for k, v in SPEC.items()}
    for cat, old, new, why in RELOCATIONS:
        spec[cat][spec[cat].index(old)] = new
        rep["reubicaciones"].append({"categoria": cat, "de": list(old), "a": list(new), "motivo": why})

    role, alley_of = {}, {}

    def claim(c, cat):
        if not in_grid(c):
            raise ValueError(f"{cat} fuera del tablero: {c}")
        if c in role:
            raise ValueError(f"Colisión sin resolver en {c}: {role[c]} vs {cat}")
        role[c] = cat

    for cat in ("comisaria", "guarida", "boveda"):
        for c in spec[cat]:
            claim(c, cat)
    for name, cs in ALLEYS_SPEC.items():
        for c in cs:
            claim(c, "callejon")
            alley_of[c] = name
    for cat in ("botin_medio", "botin_bajo", "bonus", "bloqueo"):
        for c in spec[cat]:
            claim(c, cat)
    for c in cells:
        role.setdefault(c, "calle")
    return cells, role, alley_of, spec, rep


def walkable(role, c):
    return c in role and role[c] != "bloqueo"


def alley_openings(role, rep):
    """Una salida por extremo: continuación recta del corredor; si esa casilla es el banco,
    un bloqueo o una arista con muro especificado, se prueba la dirección contigua."""
    spec_keys = {ekey(a, b) for a, b in BANK_WALLS_SPEC}
    openings = {}
    for name, cs in ALLEYS_SPEC.items():
        ops = []
        for end, inner in ((cs[0], cs[1]), (cs[-1], cs[-2])):
            di = DIRS.index(sub(end, inner))
            chosen = None
            for k in (0, 1, -1):
                n = add(end, DIRS[(di + k) % 6])
                if n in cs or not walkable(role, n) or role[n] in ("callejon", "boveda"):
                    continue
                if ekey(end, n) in spec_keys:
                    continue
                chosen = (end, n)
                if k != 0:
                    straight = add(end, DIRS[di])
                    rep["salidas_callejon"].append({
                        "corredor": name, "extremo": list(end), "salida": list(n),
                        "nota": f"La continuación recta {straight} es '{role.get(straight, 'fuera')}'; "
                                f"se abre hacia la dirección contigua."})
                break
            if chosen is None:
                raise ValueError(f"Callejón {name}: extremo {end} sin salida válida")
            ops.append(chosen)
        openings[name] = ops
    return openings


def compute_walls(role, openings, rep):
    walls = {}
    open_set = {op for ops in openings.values() for op in ops}
    for name, cs in ALLEYS_SPEC.items():
        for t in cs:
            for di, d in enumerate(DIRS):
                n = add(t, d)
                if n in cs or (t, n) in open_set:
                    continue
                k = ekey(t, n)
                if k in walls:
                    rep["muros_log"].append({"accion": "duplicado_evitado", "arista": [list(t), list(n)]})
                    continue
                walls[k] = {"tipo": "callejon", "casilla": t, "vecino": n, "dir": di, "corredor": name}
    for a, b in BANK_WALLS_SPEC:
        if b not in nbrs(a):
            raise ValueError(f"Muro de banco entre casillas no adyacentes: {a} {b}")
        k = ekey(a, b)
        if k in walls:
            rep["muros_log"].append({"accion": "fusionado", "arista": [list(a), list(b)],
                                     "motivo": "La arista ya tiene el muro del callejón (mismo cierre); "
                                               "no se duplica geometría."})
            continue
        walls[k] = {"tipo": "banco", "a": a, "b": b, "origen": "especificado"}
    bank = SPEC["boveda"][0]
    for n in nbrs(bank):
        k = ekey(bank, n)
        if n in BANK_APPROACHES or k in walls or not walkable(role, n):
            continue
        walls[k] = {"tipo": "banco", "a": bank, "b": n, "origen": "añadido"}
        rep["muros_log"].append({"accion": "añadido", "arista": [list(bank), list(n)],
                                 "motivo": "Sin este muro la casilla sería un tercer acceso directo al banco."})
    return walls


def can_step(a, b, role, walls, team):
    if not (walkable(role, a) and walkable(role, b)):
        return False
    if team == "policia" and "callejon" in (role[a], role[b]):
        return False
    return ekey(a, b) not in walls


def reach(start, role, walls, team):
    seen, dq = {start}, deque([start])
    while dq:
        c = dq.popleft()
        for n in nbrs(c):
            if n in role and n not in seen and can_step(c, n, role, walls, team):
                seen.add(n)
                dq.append(n)
    return seen


def validate_layout(cells, role, openings, walls):
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detalle": detail})

    chk("Grilla: 91 coordenadas axiales únicas", len(cells) == 91 and len(set(cells)) == 91, len(cells))
    chk("Grilla: todas dentro de radio 5", all(in_grid(c) for c in cells))
    chk("Grilla: sin casillas faltantes (3N(N+1)+1)", len(cells) == 3 * N * (N + 1) + 1)
    cnt = Counter(role.values())
    for k, v in EXPECTED_COUNTS.items():
        chk(f"Juego: {k} = {v}", cnt[k] == v, cnt[k])
    n_streets = 91 - sum(EXPECTED_COUNTS.values())
    chk(f"Juego: calles normales = {n_streets} (resto)", cnt["calle"] == n_streets, cnt["calle"])
    chk("Juego: cada coordenada tiene exactamente un rol", len(role) == 91 and set(role) == set(cells))

    for name, cs in ALLEYS_SPEC.items():
        consec = all(sub(cs[i + 1], cs[i]) in DIRS for i in range(2))
        chk(f"Callejón {name}: 3 casillas consecutivas adyacentes", consec and len(cs) == 3)
        ops = openings[name]
        chk(f"Callejón {name}: 2 salidas abiertas a calle transitable",
            len(ops) == 2 and all(walkable(role, n) and role[n] != "callejon" for _, n in ops),
            [[list(t), list(n)] for t, n in ops])
        interior_ok = all(ekey(cs[i], cs[i + 1]) not in walls for i in range(2))
        chk(f"Callejón {name}: continuidad interior sin muros", interior_ok)
        exp_walls = sum(6 - sum(1 for n in nbrs(t) if n in cs) - sum(1 for (a, _) in ops if a == t) for t in cs)
        got = sum(1 for w in walls.values() if w["tipo"] == "callejon" and w["corredor"] == name)
        chk(f"Callejón {name}: muro en cada arista expuesta ({exp_walls})", got == exp_walls, got)

    bank = SPEC["boveda"][0]
    acc = sorted(n for n in nbrs(bank) if can_step(bank, n, role, walls, "ladron"))
    chk("Banco: exactamente 2 accesos directos (N y S)", acc == sorted(BANK_APPROACHES), acc)

    street_walls = [k for k, w in walls.items() if w["tipo"] != "callejon"]
    chk("Muros: los únicos muros entre casillas no-callejón son los del banco",
        all(walls[k]["tipo"] == "banco" for k in street_walls), len(street_walls))
    chk("Muros: sin aristas duplicadas", len(walls) == len(set(walls)))

    pol = reach(SPEC["comisaria"][0], role, walls, "policia")
    pol_all = {c for c in cells if walkable(role, c) and role[c] != "callejon"}
    chk("Navegación: la policía alcanza todas las casillas no-callejón", pol == pol_all,
        sorted(pol_all - pol))
    rob = reach(SPEC["guarida"][0], role, walls, "ladron")
    rob_all = {c for c in cells if walkable(role, c)}
    chk("Navegación: los ladrones alcanzan todas las casillas transitables", rob == rob_all,
        sorted(rob_all - rob))
    chk("Navegación: la policía no puede entrar en ningún callejón",
        not any(role[c] == "callejon" for c in pol))
    chk("Navegación: todas las salidas de callejón conectan con la red de calles",
        all(n in pol for ops in openings.values() for _, n in ops))
    return checks


def layout_pipeline():
    cells, role, alley_of, spec, rep = resolve_layout()
    openings = alley_openings(role, rep)
    walls = compute_walls(role, openings, rep)
    checks = validate_layout(cells, role, openings, walls)
    return cells, role, alley_of, spec, rep, openings, walls, checks


# =============================================================================
# 4. BLENDER: utilidades
# =============================================================================
if HAS_BPY:

    def hexrgb(h):
        h = h.lstrip("#")
        s = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in s) + (1.0,)

    MAT = {}

    def make_mat(key, name, color, rough=0.5, metal=0.0, emit=0.0, bump=0.0, bump_scale=60.0,
                 var=0.0, brick=None, wave=0.0, coat=0.0):
        m = bpy.data.materials.new(name)
        try:
            m.use_nodes = True
        except Exception:
            pass
        nt = m.node_tree
        nodes, links = nt.nodes, nt.links
        bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
        base = hexrgb(color)
        bsdf.inputs["Base Color"].default_value = base
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        if coat and "Coat Weight" in bsdf.inputs:
            bsdf.inputs["Coat Weight"].default_value = coat
        if emit:
            bsdf.inputs["Emission Color"].default_value = base
            bsdf.inputs["Emission Strength"].default_value = emit
        tc = nodes.new("ShaderNodeTexCoord")
        col_out, height_out = None, None
        if brick:
            c2, mortar, scale = brick
            sep = nodes.new("ShaderNodeSeparateXYZ")
            addn = nodes.new("ShaderNodeMath")
            addn.operation = "ADD"
            comb = nodes.new("ShaderNodeCombineXYZ")
            br = nodes.new("ShaderNodeTexBrick")
            links.new(tc.outputs["Object"], sep.inputs[0])
            links.new(sep.outputs[0], addn.inputs[0])
            links.new(sep.outputs[1], addn.inputs[1])
            links.new(addn.outputs[0], comb.inputs[0])
            links.new(sep.outputs[2], comb.inputs[1])
            links.new(comb.outputs[0], br.inputs["Vector"])
            br.inputs["Color1"].default_value = base
            br.inputs["Color2"].default_value = hexrgb(c2)
            br.inputs["Mortar"].default_value = hexrgb(mortar)
            br.inputs["Scale"].default_value = scale
            br.inputs["Mortar Size"].default_value = 0.025
            col_out, height_out = br.outputs["Color"], br.outputs["Fac"]
        if var:
            oi = nodes.new("ShaderNodeObjectInfo")
            mr = nodes.new("ShaderNodeMapRange")
            mr.inputs["To Min"].default_value = 1.0 - var
            mr.inputs["To Max"].default_value = 1.0 + var
            links.new(oi.outputs["Random"], mr.inputs["Value"])
            hsv = nodes.new("ShaderNodeHueSaturation")
            if col_out is not None:
                links.new(col_out, hsv.inputs["Color"])
            else:
                hsv.inputs["Color"].default_value = base
            links.new(mr.outputs["Result"], hsv.inputs["Value"])
            col_out = hsv.outputs["Color"]
        if col_out is not None:
            links.new(col_out, bsdf.inputs["Base Color"])
        if bump or wave:
            bp = nodes.new("ShaderNodeBump")
            bp.inputs["Strength"].default_value = bump if bump else wave
            bp.inputs["Distance"].default_value = 0.01
            if wave:
                wv = nodes.new("ShaderNodeTexWave")
                wv.wave_type = "BANDS"
                wv.bands_direction = "X"
                wv.inputs["Scale"].default_value = 60.0
                links.new(tc.outputs["Object"], wv.inputs["Vector"])
                links.new(wv.outputs["Fac"], bp.inputs["Height"])
            elif height_out is not None:
                links.new(height_out, bp.inputs["Height"])
            else:
                nz = nodes.new("ShaderNodeTexNoise")
                nz.inputs["Scale"].default_value = bump_scale
                nz.inputs["Detail"].default_value = 6.0
                links.new(tc.outputs["Object"], nz.inputs["Vector"])
                links.new(nz.outputs["Fac"], bp.inputs["Height"])
            links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
        m.diffuse_color = base
        MAT[key] = m
        return m

    def build_materials():
        mk = make_mat
        # Casillas
        mk("calle", "M_Asfalto", "#9CA3AF", 0.88, bump=0.25, bump_scale=55, var=0.05)
        mk("comisaria", "M_Casilla_Comisaria", "#1E3A8A", 0.5, bump=0.05)
        mk("guarida", "M_Casilla_Guarida", "#6D28D9", 0.5, bump=0.05)
        mk("botin_bajo", "M_Casilla_BotinBajo_Verde", "#10B981", 0.5, bump=0.05)
        mk("botin_medio", "M_Casilla_BotinMedio_Ambar", "#F59E0B", 0.45, bump=0.05)
        mk("boveda", "M_Casilla_Boveda_Oro", "#EAB308", 0.28, metal=0.8, emit=0.35)
        mk("bonus", "M_Casilla_Bonus_Cian", "#06B6D4", 0.4, bump=0.05)
        mk("callejon", "M_Casilla_Callejon_Terracota", "#DC2626", 0.75,
           brick=("#C81E1E", "#7F1D1D", 9.0), bump=0.15)
        mk("bloqueo", "M_Bloque_Ladrillo_Oscuro", "#1F2937", 0.85,
           brick=("#273244", "#111827", 14.0), bump=0.2)
        # Genéricos reutilizables
        mk("base", "M_Base_Marco", "#111827", 0.55, coat=0.3)
        mk("concreto", "M_Concreto", "#D1D5DB", 0.9, bump=0.2, bump_scale=90, var=0.06)
        mk("concreto_oscuro", "M_Concreto_Oscuro", "#6B7280", 0.9, bump=0.2, bump_scale=90, var=0.05)
        mk("techo", "M_Techo_Alquitran", "#374151", 0.9, bump=0.15, bump_scale=70)
        mk("ladrillo_muro", "M_Ladrillo_Callejon", "#7F1D1D", 0.85,
           brick=("#6B1818", "#3F0F0F", 16.0), bump=0.25)
        mk("ladrillo_claro", "M_Ladrillo_Fachada", "#B4533A", 0.85,
           brick=("#9A4430", "#E5D5C5", 22.0), bump=0.2, var=0.06)
        mk("fachada_crema", "M_Fachada_Crema", "#F2E3C6", 0.8, var=0.05)
        mk("fachada_menta", "M_Fachada_Menta", "#CFE8DA", 0.8, var=0.05)
        mk("fachada_blanca", "M_Fachada_Blanca", "#F3F4F6", 0.7)
        mk("marmol", "M_Marmol", "#F1EDE4", 0.32, bump=0.03, bump_scale=20)
        mk("metal_oscuro", "M_Metal_Oscuro", "#374151", 0.35, metal=0.9)
        mk("metal_corrugado", "M_Metal_Corrugado", "#4C3D6B", 0.45, metal=0.7, wave=0.3)
        mk("metal_guarida", "M_Metal_Guarida", "#3B2F5C", 0.4, metal=0.75, wave=0.25)
        mk("puerta_reforzada", "M_Puerta_Reforzada", "#2D2A3A", 0.4, metal=0.85)
        mk("plata", "M_Metal_Plata", "#C0C4CC", 0.28, metal=1.0)
        mk("oro", "M_Oro", "#F5C542", 0.22, metal=1.0)
        mk("oro_luz", "M_Oro_Luminoso", "#FBBF24", 0.25, metal=0.6, emit=3.0)
        mk("madera", "M_Madera", "#8B5A2B", 0.7, bump=0.2, bump_scale=30)
        mk("vidrio", "M_Vidrio", "#1E293B", 0.06, coat=1.0)
        mk("ventana_luz", "M_Ventana_Iluminada", "#FDE68A", 0.3, emit=1.6)
        mk("vidrio_tienda", "M_Escaparate_Tienda", "#FDE7B0", 0.2, emit=0.9)
        mk("vidrio_vitrina", "M_Vitrina_Joyeria", "#FFF3C4", 0.08, emit=1.4, coat=1.0)
        mk("azul_policia", "M_Acento_Policia", "#1D4ED8", 0.4)
        mk("negro", "M_Negro_Mate", "#18181B", 0.8)
        mk("amarillo", "M_Amarillo_Peligro", "#FACC15", 0.6)
        mk("baliza_azul", "M_Baliza_Azul", "#3B82F6", 0.3, emit=7.0)
        mk("baliza_roja", "M_Baliza_Roja", "#EF4444", 0.3, emit=7.0)
        mk("luz_morada", "M_Luz_Morada", "#A855F7", 0.3, emit=5.0)
        mk("ambar_metal", "M_Ambar_Metal", "#D97706", 0.3, metal=0.6)
        mk("ambar_luz", "M_Letrero_Ambar", "#FBBF24", 0.3, emit=2.2)
        mk("gema", "M_Gema_Ambar", "#F59E0B", 0.1, emit=2.0, coat=1.0)
        mk("cristal_bonus", "M_Cristal_Bonus", "#22D3EE", 0.08, emit=2.6, coat=1.0)
        mk("anillo_bonus", "M_Anillo_Bonus", "#67E8F9", 0.2, emit=5.0)
        mk("toldo_verde", "M_Toldo_Verde", "#059669", 0.75)
        mk("toldo_blanco", "M_Toldo_Blanco", "#F8FAFC", 0.75)
        mk("letrero_verde", "M_Letrero_Verde", "#34D399", 0.4, emit=1.4)
        mk("muro_banco", "M_Muro_Banco", "#374151", 0.8, bump=0.2, bump_scale=80)
        mk("billete", "M_Billetes", "#15803D", 0.7)
        mk("blanco", "M_Blanco", "#F9FAFB", 0.6)
        mk("cartel", "M_Cartel_Publicitario", "#0E7490", 0.5, emit=0.6)
        mk("texto_blanco", "M_Texto_Blanco", "#FFFFFF", 0.4, emit=2.0)
        # Fichas
        mk("ficha_policia", "M_Ficha_Policia", "#2563EB", 0.3, coat=0.6)
        mk("ficha_ladron", "M_Ficha_Ladron", "#EF4444", 0.3, coat=0.6)
        mk("ficha_gorra", "M_Ficha_Gorra", "#1E3A8A", 0.45)
        mk("ficha_mascara", "M_Ficha_Mascara", "#111111", 0.6)

    # ---------------------------------------------------------------- Builder
    class Builder:
        """Acumula primitivas en un único bmesh con varios slots de material."""

        def __init__(self, name):
            self.name = name
            self.bm = bmesh.new()
            self.mats = []

        def _mi(self, m):
            if m not in self.mats:
                self.mats.append(m)
            return self.mats.index(m)

        def _tag(self, verts, m, smooth=False, all_smooth=False):
            idx = self._mi(m)
            faces = set()
            for v in verts:
                faces.update(v.link_faces)
            for f in faces:
                f.material_index = idx
                f.normal_update()
                f.smooth = all_smooth or (smooth and abs(f.normal.z) < 0.7)

        @staticmethod
        def _rot(rz=0.0, ry=0.0, rx=0.0):
            return Matrix.Rotation(rz, 4, "Z") @ Matrix.Rotation(ry, 4, "Y") @ Matrix.Rotation(rx, 4, "X")

        def box(self, c, s, m, rz=0.0, ry=0.0, rx=0.0):
            M = Matrix.Translation(Vector(c)) @ self._rot(rz, ry, rx) @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))
            res = bmesh.ops.create_cube(self.bm, size=1.0, matrix=M)
            self._tag(res["verts"], m)

        def cyl(self, c, r, h, m, segs=24, r2=None, rz=0.0, ry=0.0, rx=0.0, smooth=True):
            M = Matrix.Translation(Vector(c)) @ self._rot(rz, ry, rx)
            res = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=segs,
                                        radius1=r, radius2=(r if r2 is None else r2), depth=h, matrix=M)
            self._tag(res["verts"], m, smooth)

        def sphere(self, c, r, m, sz=1.0):
            M = Matrix.Translation(Vector(c)) @ Matrix.Diagonal((1.0, 1.0, sz, 1.0))
            res = bmesh.ops.create_uvsphere(self.bm, u_segments=24, v_segments=14, radius=r, matrix=M)
            self._tag(res["verts"], m, all_smooth=True)

        def poly(self, verts, faces, m, M=None, smooth=False):
            M = M if M is not None else Matrix.Identity(4)
            vs = [self.bm.verts.new(M @ Vector(v)) for v in verts]
            for f in faces:
                self.bm.faces.new([vs[i] for i in f])
            self._tag(vs, m, all_smooth=smooth)

        def quad_prism(self, pts, z0, z1, m):
            verts = [(x, y, z0) for x, y in pts] + [(x, y, z1) for x, y in pts]
            faces = [(3, 2, 1, 0), (4, 5, 6, 7)] + [(i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i) for i in range(4)]
            self.poly(verts, faces, m)

        def hex_prism(self, c, radius, z0, z1, m, rot=0.0):
            pts = [(c[0] + radius * math.cos(rot + math.radians(60 * i)),
                    c[1] + radius * math.sin(rot + math.radians(60 * i))) for i in range(6)]
            verts = [(x, y, z0) for x, y in pts] + [(x, y, z1) for x, y in pts]
            faces = [tuple(range(5, -1, -1)), tuple(range(6, 12))] + \
                    [(i, (i + 1) % 6, 6 + (i + 1) % 6, 6 + i) for i in range(6)]
            self.poly(verts, faces, m)

        def hex_ring(self, ro, ri, z0, z1, m, rot=0.0):
            for i in range(6):
                a0 = rot + math.radians(60 * i)
                a1 = rot + math.radians(60 * (i + 1))
                pts = [(ro * math.cos(a0), ro * math.sin(a0)), (ro * math.cos(a1), ro * math.sin(a1)),
                       (ri * math.cos(a1), ri * math.sin(a1)), (ri * math.cos(a0), ri * math.sin(a0))]
                self.quad_prism(pts, z0, z1, m)

        def torus(self, c, R1, r1, m, M_rot=None, segs=36, rsegs=10):
            M = Matrix.Translation(Vector(c)) @ (M_rot if M_rot is not None else Matrix.Identity(4))
            verts, faces = [], []
            for i in range(segs):
                a = 2 * math.pi * i / segs
                for j in range(rsegs):
                    b = 2 * math.pi * j / rsegs
                    verts.append(((R1 + r1 * math.cos(b)) * math.cos(a),
                                  (R1 + r1 * math.cos(b)) * math.sin(a), r1 * math.sin(b)))
            for i in range(segs):
                for j in range(rsegs):
                    i2, j2 = (i + 1) % segs, (j + 1) % rsegs
                    faces.append((i * rsegs + j, i2 * rsegs + j, i2 * rsegs + j2, i * rsegs + j2))
            self.poly(verts, faces, m, M, smooth=True)

        def octa(self, c, a, h, m, rz=math.pi / 4):
            M = Matrix.Translation(Vector(c)) @ Matrix.Rotation(rz, 4, "Z")
            v = [(a, 0, 0), (0, a, 0), (-a, 0, 0), (0, -a, 0), (0, 0, h), (0, 0, -h)]
            f = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (1, 0, 5), (2, 1, 5), (3, 2, 5), (0, 3, 5)]
            self.poly(v, f, m, M)

        def gable(self, c, w, d, h, m):
            v = [(-w, -d, 0), (w, -d, 0), (0, -d, h), (-w, d, 0), (w, d, 0), (0, d, h)]
            f = [(0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (3, 0, 2, 5)]
            self.poly(v, f, m, Matrix.Translation(Vector(c)))

        def finish(self, coll, loc=(0, 0, 0), bevel=0.0, props=None):
            bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces[:])
            me = bpy.data.meshes.new(self.name)
            self.bm.to_mesh(me)
            self.bm.free()
            for m in self.mats:
                me.materials.append(m)
            ob = bpy.data.objects.new(self.name, me)
            ob.location = loc
            coll.objects.link(ob)
            if bevel > 0:
                md = ob.modifiers.new("Bisel", "BEVEL")
                md.width = bevel
                md.segments = 2
                md.limit_method = "ANGLE"
                md.angle_limit = math.radians(35)
            for k, v in (props or {}).items():
                ob[k] = v
            return ob

    def hex_tile(name, cx, cy, h, mat, coll, radius=R * GAP, bevel=TILE_BEVEL, z0=0.0, rot=0.0):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bot, top = [], []
        for i in range(6):
            a = rot + math.radians(60 * i)
            x, y = radius * math.cos(a), radius * math.sin(a)
            bot.append(bm.verts.new((x, y, z0)))
            top.append(bm.verts.new((x, y, h)))
        bm.faces.new(top)
        bm.faces.new(list(reversed(bot)))
        for i in range(6):
            j = (i + 1) % 6
            bm.faces.new((bot[i], bot[j], top[j], top[i]))
        bm.normal_update()
        if bevel > 0:
            bw = bm.edges.layers.float.new("bevel_weight_edge")
            ts = set(top)
            for e in bm.edges:
                if all(v in ts for v in e.verts):
                    e[bw] = 1.0
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = (cx, cy, 0.0)
        coll.objects.link(ob)
        if bevel > 0:
            md = ob.modifiers.new("Bisel", "BEVEL")
            md.width = bevel
            md.segments = 3
            md.limit_method = "WEIGHT"
        return ob

    def text_obj(name, body, loc, rot, size, mat, coll, extrude=0.004):
        cu = bpy.data.curves.new(name, "FONT")
        cu.body = body
        cu.size = size
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.extrude = extrude
        cu.materials.append(mat)
        ob = bpy.data.objects.new(name, cu)
        ob.location = loc
        ob.rotation_euler = rot
        coll.objects.link(ob)
        return ob

    # =========================================================================
    # 5. EDIFICIOS (coordenadas locales; z = 0 es la superficie de la casilla)
    # =========================================================================
    def build_comisaria(name):
        b, M = Builder(name), MAT
        b.box((0.12, 0.30, 0.21), (0.62, 0.40, 0.42), M["fachada_blanca"])
        b.box((0.12, 0.30, 0.39), (0.64, 0.42, 0.06), M["azul_policia"])
        b.box((0.12, 0.30, 0.43), (0.66, 0.44, 0.02), M["techo"])
        b.box((0.12, 0.06, 0.01), (0.30, 0.10, 0.02), M["concreto"])                 # escalón
        b.box((0.12, 0.095, 0.11), (0.15, 0.012, 0.20), M["vidrio"])                 # puerta
        b.box((0.12, 0.092, 0.215), (0.19, 0.016, 0.02), M["azul_policia"])
        b.box((0.12, 0.04, 0.235), (0.26, 0.12, 0.02), M["azul_policia"])            # marquesina
        for sx in (-0.11, 0.11):
            b.cyl((0.12 + sx, -0.005, 0.1125), 0.008, 0.225, M["metal_oscuro"], 8)
        for x in (-0.10, 0.34):
            for z in (0.14, 0.29):
                b.box((x, 0.096, z), (0.11, 0.012, 0.09), M["ventana_luz"])
        b.box((0.12, 0.096, 0.29), (0.11, 0.012, 0.07), M["ventana_luz"])
        # baliza
        b.box((0.12, 0.30, 0.465), (0.22, 0.09, 0.03), M["metal_oscuro"])
        for x, m in ((0.06, M["baliza_azul"]), (0.18, M["baliza_roja"])):
            b.cyl((x, 0.30, 0.51), 0.035, 0.06, m, 16)
            b.sphere((x, 0.30, 0.54), 0.035, m)
        b.cyl((0.38, 0.44, 0.56), 0.008, 0.26, M["metal_oscuro"], 8)
        b.sphere((0.38, 0.44, 0.69), 0.015, M["baliza_roja"])
        # ala de la cárcel
        b.box((-0.36, 0.30, 0.15), (0.34, 0.36, 0.30), M["concreto_oscuro"])
        b.box((-0.36, 0.30, 0.31), (0.36, 0.38, 0.02), M["azul_policia"])
        b.box((-0.36, 0.116, 0.12), (0.26, 0.012, 0.18), M["negro"])
        for i in range(7):
            b.cyl((-0.47 + i * 0.0367, 0.105, 0.12), 0.007, 0.19, M["metal_oscuro"], 8)
        for z in (0.03, 0.21):
            b.box((-0.36, 0.105, z), (0.27, 0.012, 0.012), M["metal_oscuro"])
        return b

    def build_guarida(name):
        b, M = Builder(name), MAT
        b.box((0, 0.30, 0.14), (0.78, 0.40, 0.28), M["metal_corrugado"])
        b.cyl((0, 0.30, 0.28), 0.20, 0.80, M["metal_guarida"], 28, ry=math.pi / 2)   # techo abovedado
        b.box((0, 0.093, 0.12), (0.44, 0.014, 0.24), M["metal_oscuro"])               # marco
        b.box((0, 0.087, 0.115), (0.38, 0.012, 0.21), M["puerta_reforzada"])          # portón
        for z in (0.04, 0.09, 0.14, 0.19):
            b.box((0, 0.079, z), (0.38, 0.01, 0.012), M["metal_oscuro"])              # refuerzos
        for i in range(9):
            b.box((-0.20 + i * 0.05, 0.088, 0.255), (0.05, 0.02, 0.028),
                  M["amarillo"] if i % 2 == 0 else M["negro"])                        # franja de peligro
        for sx in (-0.29, 0.29):
            b.box((sx, 0.094, 0.20), (0.05, 0.012, 0.03), M["luz_morada"])
        # marcador dorado sobre mástil
        b.cyl((0, 0.30, 0.57), 0.012, 0.20, M["metal_oscuro"], 10)
        b.torus((0, 0.30, 0.79), 0.11, 0.022, M["oro_luz"], Matrix.Rotation(math.pi / 2, 4, "X"))
        # cajas, barriles y escotilla subterránea
        b.box((0.52, 0.20, 0.05), (0.10, 0.10, 0.10), M["madera"])
        b.box((0.52, 0.31, 0.05), (0.10, 0.10, 0.10), M["madera"])
        b.box((0.52, 0.255, 0.15), (0.10, 0.10, 0.10), M["madera"], rz=0.3)
        for y in (0.22, 0.34):
            b.cyl((-0.50, y, 0.06), 0.05, 0.12, M["metal_guarida"], 16)
        b.cyl((-0.48, -0.25, 0.006), 0.09, 0.012, M["metal_oscuro"], 24)
        b.box((-0.48, -0.25, 0.014), (0.14, 0.02, 0.006), M["amarillo"])
        return b

    def build_banco(name):
        b, M = Builder(name), MAT
        for i, (w, d) in enumerate(((0.88, 0.70), (0.82, 0.64), (0.76, 0.58))):
            b.box((0, 0, 0.02 + 0.04 * i), (w, d, 0.04), M["marmol"])
        b.box((0, 0.07, 0.37), (0.64, 0.40, 0.50), M["marmol"])                       # cella .12-.62
        # puerta de bóveda
        b.cyl((0, -0.137, 0.33), 0.14, 0.016, M["metal_oscuro"], 36, rx=math.pi / 2)
        b.torus((0, -0.147, 0.33), 0.135, 0.014, M["oro"], Matrix.Rotation(math.pi / 2, 4, "X"))
        for k in range(3):
            b.box((0, -0.152, 0.33), (0.20, 0.008, 0.014), M["oro"], ry=k * math.pi / 3)
        b.cyl((0, -0.155, 0.33), 0.025, 0.012, M["oro"], 16, rx=math.pi / 2)
        # columnas
        for x in (-0.33, -0.21, 0.21, 0.33):
            b.box((x, -0.22, 0.13), (0.075, 0.075, 0.02), M["marmol"])
            b.cyl((x, -0.22, 0.37), 0.032, 0.46, M["marmol"], 16)
            b.box((x, -0.22, 0.61), (0.08, 0.08, 0.02), M["oro"])
        b.box((0, 0.0, 0.627), (0.80, 0.62, 0.014), M["oro_luz"])                     # filete luminoso
        b.box((0, 0.0, 0.66), (0.78, 0.60, 0.05), M["oro"])                           # entablamento
        b.gable((0, 0.0, 0.685), 0.39, 0.30, 0.24, M["oro"])                           # frontón
        for x, z in ((-0.37, 0.70), (0.37, 0.70), (0.0, 0.93)):                        # acroteras
            b.sphere((x, -0.30, z), 0.03, M["oro_luz"])
        # emblema: moneda dorada sobre la cumbrera
        b.cyl((0, 0.05, 0.94), 0.012, 0.06, M["oro"], 8)
        b.cyl((0, 0.05, 1.07), 0.11, 0.025, M["oro_luz"], 36, rx=math.pi / 2)
        b.torus((0, 0.05, 1.07), 0.11, 0.014, M["oro"], Matrix.Rotation(math.pi / 2, 4, "X"))
        # lingotes (izq.) y fajos de billetes (der.)
        for lvl, xs in enumerate(((-0.075, 0.0, 0.075), (-0.0375, 0.0375), (0.0,))):
            for x in xs:
                b.box((-0.38 + x, -0.47, 0.0125 + 0.025 * lvl), (0.07, 0.035, 0.025), M["oro"])
        for i, hgt in enumerate((0.06, 0.09, 0.045)):
            x = 0.31 + i * 0.05
            b.box((x, -0.47, hgt / 2), (0.045, 0.08, hgt), M["billete"])
            b.box((x, -0.47, hgt / 2), (0.047, 0.02, hgt + 0.002), M["blanco"])
        return b

    def build_tienda(name, rng, idx):
        b, M = Builder(name), MAT
        w, d, h = rng.uniform(0.54, 0.66), rng.uniform(0.40, 0.48), rng.uniform(0.24, 0.32)
        cy = 0.10
        yf = cy - d / 2
        facade = [M["fachada_crema"], M["ladrillo_claro"], M["fachada_menta"], M["concreto"]][idx % 4]
        b.box((0, cy, 0.01), (w + 0.03, d + 0.03, 0.02), M["concreto"])
        b.box((0, cy, 0.02 + h / 2), (w, d, h), facade)
        side = 1 if idx % 2 else -1
        b.box((-side * w * 0.17, yf - 0.006, 0.02 + h * 0.38), (w * 0.5, 0.012, h * 0.42), M["vidrio_tienda"])
        b.box((side * w * 0.31, yf - 0.007, 0.02 + h * 0.28), (0.10, 0.014, h * 0.56), M["madera"])
        # toldo inclinado
        n, aw, depth, ang = 6, w + 0.02, 0.15, math.radians(28)
        zt = 0.02 + h * 0.80
        solid = (idx % 3 == 2)
        for i in range(n):
            x = -aw / 2 + aw / n * (i + 0.5)
            c = (x, yf - depth / 2 * math.cos(ang), zt - depth / 2 * math.sin(ang))
            m = M["toldo_verde"] if (solid or i % 2 == 0) else M["toldo_blanco"]
            b.box(c, (aw / n, depth, 0.012), m, rx=ang)
        b.box((0, yf - depth * math.cos(ang), zt - depth * math.sin(ang) - 0.015), (aw, 0.01, 0.03),
              M["toldo_verde"])
        top = 0.02 + h + 0.02
        b.box((0, cy, top - 0.01), (w + 0.02, d + 0.02, 0.02), M["techo"])
        b.box((0, yf + 0.03, top + 0.04), (w * 0.7, 0.025, 0.08), M["letrero_verde"])   # letrero
        v = idx % 4
        if v == 0:
            b.box((w * 0.25, cy + d * 0.25, top + 0.035), (0.13, 0.10, 0.07), M["metal_oscuro"])
        elif v == 1:
            b.cyl((-w * 0.25, cy + d * 0.22, top + 0.06), 0.06, 0.12, M["concreto_oscuro"], 16)
        elif v == 2:
            for sx in (-0.12, 0.12):
                b.cyl((sx, cy + d * 0.25, top + 0.04), 0.025, 0.08, M["metal_oscuro"], 12)
        else:
            b.box((-w * 0.22, cy + d * 0.25, top + 0.035), (0.12, 0.10, 0.07), M["metal_oscuro"])
            b.cyl((w * 0.3, cy + d * 0.3, top + 0.12), 0.006, 0.24, M["metal_oscuro"], 8)
        return b

    def build_joyeria(name, rng, idx):
        b, M = Builder(name), MAT
        w, d = 0.70 + rng.uniform(-0.04, 0.03), 0.48 + rng.uniform(-0.03, 0.03)
        cy, h1 = 0.06, 0.26
        yf = cy - d / 2
        facade = [M["fachada_crema"], M["ladrillo_claro"], M["concreto"]][idx % 3]
        facade2 = [M["fachada_blanca"], M["fachada_crema"], M["ladrillo_claro"]][idx % 3]
        b.box((0, cy, 0.01), (w + 0.03, d + 0.03, 0.02), M["concreto"])
        b.box((0, cy, 0.02 + h1 / 2), (w, d, h1), facade)
        for sx in (-1, 1):
            b.box((sx * w * 0.27, yf - 0.006, 0.13), (w * 0.32, 0.012, 0.17), M["vidrio_vitrina"])
            b.box((sx * w * 0.27, yf - 0.010, 0.222), (w * 0.34, 0.012, 0.016), M["ambar_metal"])
            b.box((sx * w * 0.27, yf - 0.010, 0.040), (w * 0.34, 0.012, 0.016), M["ambar_metal"])
        b.box((0, yf - 0.008, 0.12), (0.11, 0.016, 0.20), M["puerta_reforzada"])
        for sx in (-0.03, 0.0, 0.03):
            b.box((sx, yf - 0.018, 0.12), (0.006, 0.006, 0.19), M["oro"])                # rejas
        b.box((0, yf - 0.012, 0.255), (w * 0.7, 0.024, 0.04), M["ambar_luz"])            # letrero
        b.box((0, cy, 0.295), (w + 0.04, d + 0.04, 0.03), M["ambar_metal"])              # cornisa
        w2, d2 = w * rng.uniform(0.74, 0.86), d * rng.uniform(0.72, 0.82)
        h2 = rng.uniform(0.18, 0.24)
        cy2 = cy + (d - d2) / 2 - 0.01
        yf2 = cy2 - d2 / 2
        b.box((0, cy2, 0.31 + h2 / 2), (w2, d2, h2), facade2)
        for i in range(3):
            b.box(((i - 1) * w2 * 0.3, yf2 - 0.005, 0.31 + h2 * 0.5), (w2 * 0.18, 0.01, h2 * 0.5),
                  M["ventana_luz"] if (i + idx) % 2 else M["vidrio"])
        b.box((0, cy2, 0.31 + h2 + 0.0125), (w2 + 0.03, d2 + 0.03, 0.025), M["ambar_metal"])
        top = 0.31 + h2 + 0.025
        v = idx % 3
        if v == 0:
            b.box((0, cy2, top + 0.02), (0.12, 0.12, 0.04), M["ambar_metal"])
            b.octa((0, cy2, top + 0.14), 0.08, 0.10, M["gema"])
        elif v == 1:
            b.sphere((0, cy2, top), 0.12, M["oro"], sz=0.8)
            b.cyl((0, cy2, top + 0.13), 0.008, 0.08, M["oro"], 8)
        else:
            b.box((0, cy2, top + 0.07), (0.16, 0.16, 0.14), facade2)
            b.box((0, cy2, top + 0.145), (0.18, 0.18, 0.015), M["ambar_metal"])
            b.octa((0, cy2, top + 0.21), 0.05, 0.06, M["gema"])
        return b

    def build_bloque(name, rng, idx):
        """Detalles de la manzana cerrada (coordenadas del mundo en Z; la casilla de 0.85 m
        es el volumen del edificio)."""
        b, M = Builder(name), MAT
        ap = R * GAP * math.cos(math.radians(30)) + 0.002
        for f in range(6):
            na = math.radians(60 * f + 30)
            nx, ny = math.cos(na), math.sin(na)
            tx, ty = -ny, nx
            for z in (0.20, 0.40, 0.60):
                for t in (-0.27, 0.0, 0.27):
                    m = M["ventana_luz"] if rng.random() < 0.33 else M["vidrio"]
                    b.box((ap * nx + t * tx, ap * ny + t * ty, z), (0.13, 0.016, 0.12), m, rz=na + math.pi / 2)
            for z in (0.30, 0.50):
                b.box((ap * nx, ap * ny, z), (0.90, 0.012, 0.018), M["concreto_oscuro"], rz=na + math.pi / 2)
        T = H_BLOCK
        b.hex_prism((0, 0), 0.90, T - 0.002, T + 0.006, M["techo"])
        b.hex_ring(0.935, 0.87, T - 0.01, T + 0.05, M["concreto_oscuro"])
        T += 0.006
        v = idx % 6
        if v == 0:                                     # depósito de agua
            for sx in (-0.09, 0.09):
                for sy in (-0.09, 0.09):
                    b.cyl((sx, sy, T + 0.07), 0.012, 0.14, M["metal_oscuro"], 8)
            b.cyl((0, 0, T + 0.22), 0.13, 0.16, M["madera"], 24)
            b.cyl((0, 0, T + 0.335), 0.14, 0.07, M["metal_oscuro"], 24, r2=0.01)
        elif v == 1:                                   # torre superior
            b.box((0, 0.08, T + 0.16), (0.50, 0.42, 0.32), M["concreto_oscuro"])
            for t in (-0.15, 0.0, 0.15):
                b.box((t, 0.08 - 0.215, T + 0.18), (0.09, 0.012, 0.12), M["ventana_luz"] if t == 0 else M["vidrio"])
            b.box((0, 0.08, T + 0.33), (0.52, 0.44, 0.02), M["techo"])
            b.cyl((0.15, 0.15, T + 0.47), 0.008, 0.26, M["metal_oscuro"], 8)
        elif v == 2:                                   # climatizadores + caseta
            for i, (x, y) in enumerate(((-0.3, -0.2), (-0.05, -0.32), (0.25, -0.25))):
                b.box((x, y, T + 0.035), (0.14, 0.10, 0.07), M["plata"], rz=0.1 * i)
            b.box((0.1, 0.3, T + 0.07), (0.20, 0.16, 0.14), M["concreto"])
        elif v == 3:                                   # segundo cuerpo hexagonal
            b.hex_prism((0, 0), 0.55, T - 0.005, T + 0.24, M["bloqueo"])
            b.hex_ring(0.57, 0.52, T + 0.24, T + 0.27, M["concreto_oscuro"])
            b.box((0.2, 0.1, T + 0.275), (0.12, 0.10, 0.06), M["plata"])
        elif v == 4:                                   # valla publicitaria
            for sx in (-0.25, 0.25):
                b.cyl((sx, 0.1, T + 0.14), 0.012, 0.28, M["metal_oscuro"], 8)
            b.box((0, 0.1, T + 0.36), (0.62, 0.02, 0.20), M["cartel"])
            b.box((0, 0.1, T + 0.36), (0.66, 0.03, 0.24), M["metal_oscuro"])
        else:                                          # chimeneas + tanque horizontal
            for x in (-0.25, -0.12):
                b.box((x, 0.3, T + 0.10), (0.08, 0.08, 0.20), M["ladrillo_claro"])
            b.cyl((0.15, -0.1, T + 0.08), 0.07, 0.36, M["plata"], 20, rz=0.4, ry=math.pi / 2)
        return b

    def build_bonus(name):
        b, M = Builder(name), MAT
        b.cyl((0, 0, 0.02), 0.26, 0.04, M["metal_oscuro"], 32)
        b.torus((0, 0, 0.042), 0.215, 0.018, M["anillo_bonus"])
        b.cyl((0, 0, 0.17), 0.03, 0.26, M["plata"], 16, r2=0.015)
        b.octa((0, 0, 0.52), 0.16, 0.22, M["cristal_bonus"])
        return b

    def build_ficha(name, team):
        b, M = Builder(name), MAT
        body = M["ficha_policia"] if team == "policia" else M["ficha_ladron"]
        b.cyl((0, 0, 0.025), 0.15, 0.05, body, 32)
        b.cyl((0, 0, 0.065), 0.125, 0.03, body, 32)
        b.cyl((0, 0, 0.24), 0.10, 0.32, body, 32, r2=0.055)
        b.cyl((0, 0, 0.415), 0.085, 0.03, body, 32)
        b.sphere((0, 0, 0.525), 0.11, body)
        if team == "policia":
            b.cyl((0, 0, 0.62), 0.103, 0.035, M["ficha_gorra"], 32)
            b.cyl((0, 0, 0.645), 0.115, 0.02, M["ficha_gorra"], 32)
            b.box((0, -0.1, 0.608), (0.12, 0.07, 0.012), M["negro"], rx=-0.25)
            b.box((0, -0.112, 0.632), (0.03, 0.012, 0.025), M["oro"])
        else:
            b.torus((0, 0, 0.545), 0.104, 0.024, M["ficha_mascara"])
            b.sphere((0, 0, 0.575), 0.102, M["ficha_mascara"], sz=0.75)
            b.sphere((0, 0, 0.65), 0.025, M["ficha_mascara"])
        return b

    # =========================================================================
    # 6. CONSTRUCCIÓN DE LA ESCENA
    # =========================================================================
    def clean_scene():
        before = {"objetos": len(bpy.data.objects), "colecciones": [c.name for c in bpy.data.collections],
                  "materiales": len(bpy.data.materials), "mallas": len(bpy.data.meshes)}
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for c in list(bpy.data.collections):
            bpy.data.collections.remove(c)
        for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.cameras,
                    bpy.data.lights, bpy.data.images, bpy.data.node_groups):
            for d in list(blk):
                if d.users == 0:
                    blk.remove(d)
        try:
            bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        except Exception:
            pass
        return before

    def make_collections():
        sc = bpy.context.scene
        main = bpy.data.collections.new("Tablero_RobAndRun_91")
        sc.collection.children.link(main)
        subs = {}
        for n in ("Casillas", "Edificios", "Paredes_Callejones", "Fichas", "Decoracion",
                  "Iluminacion", "Camaras"):
            c = bpy.data.collections.new(n)
            main.children.link(c)
            subs[n] = c
        return main, subs

    def build_all():
        cells, role, alley_of, spec, rep, openings, walls, checks = layout_pipeline()
        failed = [c for c in checks if not c["ok"]]
        if failed:
            raise RuntimeError("El layout no pasa la validación: " + json.dumps(failed, ensure_ascii=False))

        before = clean_scene()
        build_materials()
        main, C = make_collections()
        top = {}

        # ---- casillas
        for (q, r) in cells:
            t = role[(q, r)]
            h = {"comisaria": H_SPECIAL, "guarida": H_SPECIAL, "bloqueo": H_BLOCK}.get(t, H_TILE)
            x, y = axial_xy(q, r)
            suf = f"_{alley_of[(q, r)]}" if t == "callejon" else ""
            ob = hex_tile(f"Casilla_{t}{suf}_q{q}_r{r}", x, y, h, MAT[t], C["Casillas"])
            ob["q"], ob["r"], ob["rol"] = q, r, t
            top[(q, r)] = h

        def place(builder, c, coll, bevel=0.006, extra=None):
            x, y = axial_xy(*c)
            props = {"q": c[0], "r": c[1]}
            props.update(extra or {})
            return builder.finish(coll, (x, y, top[c]), bevel, props)

        E = C["Edificios"]
        # ---- edificios principales
        place(build_comisaria("Edificio_Comisaria_Carcel"), (0, 5), E)
        place(build_guarida("Edificio_Guarida_Deposito"), (0, -5), E)
        place(build_banco("Edificio_Banco_Central_Boveda"), (0, 0), E)
        for i, c in enumerate(spec["botin_bajo"]):
            rng = random.Random(1000 + c[0] * 37 + c[1] * 101)
            place(build_tienda(f"Edificio_Tienda_{i + 1}_q{c[0]}_r{c[1]}", rng, i), c, E)
        for i, c in enumerate(spec["botin_medio"]):
            rng = random.Random(2000 + c[0] * 37 + c[1] * 101)
            place(build_joyeria(f"Edificio_Joyeria_{i + 1}_q{c[0]}_r{c[1]}", rng, i), c, E)
        for i, c in enumerate(spec["bloqueo"]):
            rng = random.Random(3000 + c[0] * 37 + c[1] * 101)
            x, y = axial_xy(*c)
            build_bloque(f"Edificio_Manzana_{i + 1}_q{c[0]}_r{c[1]}", rng, i).finish(
                E, (x, y, 0.0), 0.004, {"q": c[0], "r": c[1]})

        # ---- rótulos
        x, y = axial_xy(0, 5)
        text_obj("Rotulo_Comisaria_POLICIA", "POLICÍA", (x + 0.12, y + 0.086, top[(0, 5)] + 0.39),
                 (math.pi / 2, 0, 0), 0.075, MAT["texto_blanco"], E)
        text_obj("Rotulo_Carcel", "CÁRCEL", (x - 0.36, y + 0.112, top[(0, 5)] + 0.255),
                 (math.pi / 2, 0, 0), 0.05, MAT["texto_blanco"], E)
        x, y = axial_xy(0, -5)
        text_obj("Rotulo_Guarida_Dolar", "$", (x, y + 0.30, top[(0, -5)] + 0.79),
                 (math.pi / 2, 0, 0), 0.14, MAT["oro_luz"], E, extrude=0.006)
        text_obj("Rotulo_Banco_Dolar", "$", (0, -0.306, top[(0, 0)] + 0.78),
                 (math.pi / 2, 0, 0), 0.14, MAT["oro_luz"], E)
        text_obj("Rotulo_Banco_Moneda", "$", (0, 0.05 - 0.017, top[(0, 0)] + 1.07),
                 (math.pi / 2, 0, 0), 0.15, MAT["metal_oscuro"], E, extrude=0.003)

        # ---- bonus
        for i, c in enumerate(spec["bonus"]):
            place(build_bonus(f"Marcador_Bonus_{i + 1}_q{c[0]}_r{c[1]}"), c, C["Decoracion"], 0.0)

        # ---- muros de callejón (dentro de la casilla del callejón, con inglete)
        P = C["Paredes_Callejones"]
        ro = R * GAP - 0.01
        ri = ro - ALLEY_WALL_T / math.cos(math.radians(30))
        for k, w in sorted(walls.items()):
            if w["tipo"] != "callejon":
                continue
            t, n, di = w["casilla"], w["vecino"], w["dir"]
            th = dir_angle(di)
            a0, a1 = th - math.radians(30), th + math.radians(30)
            pts = [(ro * math.cos(a0), ro * math.sin(a0)), (ro * math.cos(a1), ro * math.sin(a1)),
                   (ri * math.cos(a1), ri * math.sin(a1)), (ri * math.cos(a0), ri * math.sin(a0))]
            b = Builder(f"Muro_Callejon_{w['corredor']}_q{t[0]}_r{t[1]}_hacia_q{n[0]}_r{n[1]}")
            b.quad_prism(pts, -0.02, ALLEY_WALL_H - 0.03, MAT["ladrillo_muro"])
            pts2 = [(ro * math.cos(a0) * 1.0, ro * math.sin(a0) * 1.0), (ro * math.cos(a1), ro * math.sin(a1)),
                    ((ri - 0.01) * math.cos(a1), (ri - 0.01) * math.sin(a1)),
                    ((ri - 0.01) * math.cos(a0), (ri - 0.01) * math.sin(a0))]
            b.quad_prism(pts2, ALLEY_WALL_H - 0.03, ALLEY_WALL_H, MAT["concreto"])
            x, y = axial_xy(*t)
            fp = [[x + px, y + py] for px, py in pts]
            b.finish(P, (x, y, top[t]), 0.004, {"tipo_muro": "callejon", "arista": json.dumps([t, n]),
                                                "footprint": json.dumps(fp),
                                                "zmin": top[t] - 0.02, "zmax": top[t] + ALLEY_WALL_H})

        # ---- muros del banco (centrados sobre la arista compartida) + postes
        posts = {}
        for k, w in sorted(walls.items()):
            if w["tipo"] != "banco":
                continue
            a, c2 = w["a"], w["b"]
            pa, pb = Vector(axial_xy(*a)), Vector(axial_xy(*c2))
            mid = (pa + pb) / 2
            u = (pb - pa).normalized()
            tv = Vector((-u.y, u.x))
            ang = math.atan2(tv.y, tv.x)
            L = R
            b = Builder(f"Muro_Banco_q{a[0]}_r{a[1]}__q{c2[0]}_r{c2[1]}")
            z0, z1 = BASE_Z1, H_TILE + BANK_WALL_H
            b.box((0, 0, (z0 + z1 - 0.03) / 2), (L, BANK_WALL_T, z1 - 0.03 - z0), MAT["muro_banco"])
            b.box((0, 0, z1 - 0.015), (L, BANK_WALL_T + 0.03, 0.03), MAT["concreto"])
            ob = b.finish(P, (mid.x, mid.y, 0.0), 0.004, {"tipo_muro": "banco", "origen": w["origen"],
                                                          "arista": json.dumps([a, c2])})
            ob.rotation_euler[2] = ang
            hl, ht = L / 2, BANK_WALL_T / 2
            fp = [mid + tv * sx * hl + u * sy * ht for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            ob["footprint"] = json.dumps([[p.x, p.y] for p in fp])
            ob["zmin"], ob["zmax"] = z0, z1
            for s in (-1, 1):
                p = mid + tv * s * hl
                posts.setdefault((round(p.x, 3), round(p.y, 3)), p)
        for i, (kk, p) in enumerate(sorted(posts.items())):
            b = Builder(f"Poste_Muro_Banco_{i + 1}")
            b.cyl((0, 0, (BASE_Z1 + H_TILE + BANK_WALL_H + 0.04) / 2), 0.075,
                  H_TILE + BANK_WALL_H + 0.04 - BASE_Z1, MAT["metal_oscuro"], 20)
            b.sphere((0, 0, H_TILE + BANK_WALL_H + 0.045), 0.05, MAT["oro"])
            b.finish(P, (p.x, p.y, 0.0), 0.0, {"tipo_muro": "poste"})

        # ---- señales "solo ladrones" en cada salida de callejón
        D = C["Decoracion"]
        for name, ops in openings.items():
            for j, (t, n) in enumerate(ops):
                pt, pn = Vector(axial_xy(*t)), Vector(axial_xy(*n))
                u = (pn - pt).normalized()
                tv = Vector((-u.y, u.x))
                pos = u * 0.55 + tv * 0.30
                th = math.atan2(u.y, u.x)
                b = Builder(f"Senal_SoloLadrones_{name}_{j + 1}")
                zs, rs = 0.50, 0.12
                b.cyl((pos.x, pos.y, (zs - rs) / 2 + 0.01), 0.012, zs - rs + 0.02, MAT["metal_oscuro"], 8)
                b.cyl((pos.x + u.x * 0.012, pos.y + u.y * 0.012, zs), rs, 0.012, MAT["azul_policia"], 28,
                      rz=th, ry=math.pi / 2)
                rot = Matrix.Rotation(th, 4, "Z") @ Matrix.Rotation(math.pi / 2, 4, "Y")
                b.torus((pos.x + u.x * 0.02, pos.y + u.y * 0.02, zs), rs, 0.018, MAT["baliza_roja"], rot,
                        segs=28, rsegs=8)
                bar = Matrix.Rotation(th, 4, "Z") @ Matrix.Rotation(math.radians(45), 4, "X")
                hb = rs * 0.9
                b.poly([(0.0, -hb, -0.016), (0.0, hb, -0.016), (0.0, hb, 0.016), (0.0, -hb, 0.016),
                        (0.01, -hb, -0.016), (0.01, hb, -0.016), (0.01, hb, 0.016), (0.01, -hb, 0.016)],
                       [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)],
                       MAT["baliza_roja"],
                       Matrix.Translation(Vector((pos.x + u.x * 0.02, pos.y + u.y * 0.02, zs))) @ bar)
                x, y = axial_xy(*t)
                b.finish(D, (x, y, top[t]), 0.0)

        # ---- pasos de peatones en los accesos al banco
        for c in BANK_APPROACHES:
            b = Builder(f"Paso_Peatonal_q{c[0]}_r{c[1]}")
            for i in range(5):
                b.box((0, -0.28 + 0.14 * i, 0.0015), (0.46, 0.07, 0.004), MAT["blanco"])
            place(b, c, D, 0.0)

        # ---- base y marco
        hex_tile("Base_Marco_Hexagonal", 0.0, 0.0, BASE_Z1, MAT["base"], D, radius=BASE_RADIUS,
                 bevel=0.04, z0=BASE_Z0, rot=math.radians(30))
        b = Builder("Base_Moldura_Metalica")
        b.hex_ring(BASE_RADIUS - 0.03, BASE_RADIUS - 0.17, BASE_Z1 - 0.005, BASE_Z1 + 0.022, MAT["plata"],
                   rot=math.radians(30))
        ap_mid = (BASE_RADIUS - 0.10) * math.cos(math.radians(30))
        for e in range(6):
            na = math.radians(60 * e)
            nx, ny = math.cos(na), math.sin(na)
            for t in (-3.6, -1.2, 1.2, 3.6):
                b.cyl((ap_mid * nx - t * ny, ap_mid * ny + t * nx, BASE_Z1 + 0.03), 0.025, 0.016,
                      MAT["metal_oscuro"], 12)
        for vtx in range(6):
            va = math.radians(30 + 60 * vtx)
            rc = BASE_RADIUS - 0.62
            b.cyl((rc * math.cos(va), rc * math.sin(va), BASE_Z1 + 0.006), 0.16, 0.012, MAT["oro"], 6,
                  rz=va)
        b.finish(D, (0, 0, 0), 0.0)
        board_edge = 1.5 * N * R + R * GAP                     # apotema exterior del panal
        ap_txt = (board_edge + (BASE_RADIUS - 0.17) * math.cos(math.radians(30))) / 2
        for txt, ang, size, mat, nm in (("ROB AND RUN", 300, 0.58, MAT["oro_luz"], "Titulo_RobAndRun"),
                                        ("POLICÍAS vs LADRONES  ·  META $50.000", 240, 0.30, MAT["texto_blanco"],
                                         "Subtitulo_RobAndRun")):
            na = math.radians(ang)
            text_obj(nm, txt, (ap_txt * math.cos(na), ap_txt * math.sin(na), BASE_Z1 + 0.006),
                     (0, 0, na + math.pi / 2), size, mat, D, extrude=0.006)

        # ---- fichas
        F = C["Fichas"]
        for team, c, nm in (("policia", (0, 5), "Ficha_Policia"), ("ladron", (0, -5), "Ficha_Ladron")):
            x, y = axial_xy(*c)
            for i, sx in enumerate((-0.25, 0.25)):
                build_ficha(f"{nm}_{i + 1}", team).finish(F, (x + sx, y - 0.40, top[c]), 0.004,
                                                          {"q": c[0], "r": c[1], "equipo": team})

        setup_lights_cameras(C)
        setup_viewport()
        geo = validate_geometry(top, walls)
        write_reports(cells, role, spec, rep, openings, walls, checks, geo, before)
        return {"antes": before, "objetos": len(main.all_objects),
                "layout_ok": all(c["ok"] for c in checks), "geometria": geo}

    # =========================================================================
    # 7. LUCES, CÁMARAS, RENDER
    # =========================================================================
    def setup_lights_cameras(C):
        sc = bpy.context.scene
        L = C["Iluminacion"]
        sun = bpy.data.lights.new("Sol_Principal", "SUN")
        sun.energy = 3.2
        sun.angle = math.radians(10)
        o = bpy.data.objects.new("Sol_Principal", sun)
        o.rotation_euler = (math.radians(48), 0, math.radians(25))
        L.objects.link(o)
        fill = bpy.data.lights.new("Sol_Relleno", "SUN")
        fill.energy = 0.6
        fill.angle = math.radians(30)
        try:
            fill.use_shadow = False
        except Exception:
            pass
        o = bpy.data.objects.new("Sol_Relleno", fill)
        o.rotation_euler = (math.radians(60), 0, math.radians(-150))
        L.objects.link(o)
        w = sc.world or bpy.data.worlds.new("World")
        sc.world = w
        try:
            w.use_nodes = True
        except Exception:
            pass
        bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg:
            bg.inputs[0].default_value = hexrgb("#3A4252")
            bg.inputs[1].default_value = 1.0

        K = C["Camaras"]
        cd = bpy.data.cameras.new("Camara_Principal")
        cd.type = "ORTHO"
        cd.clip_end = 300
        cam = bpy.data.objects.new("Camara_Principal", cd)
        az, el, dist = math.radians(12), math.radians(50), 60.0   # desde el Sur, girada 12° al Este
        cam.location = (dist * math.cos(el) * math.sin(az), -dist * math.cos(el) * math.cos(az),
                        dist * math.sin(el))
        cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        K.objects.link(cam)
        td = bpy.data.cameras.new("Camara_Cenital")
        td.type = "ORTHO"
        td.ortho_scale = 2 * BASE_RADIUS + 0.6
        td.clip_end = 300
        top_cam = bpy.data.objects.new("Camara_Cenital", td)
        top_cam.location = (0, 0, 50)
        K.objects.link(top_cam)
        sc.camera = cam
        sc.render.resolution_x, sc.render.resolution_y = 1920, 1440
        sc.render.resolution_percentage = 100
        try:
            sc.eevee.taa_render_samples = 64
            sc.eevee.use_raytracing = True
        except Exception:
            pass
        try:
            sc.view_settings.view_transform = "AgX"
            sc.view_settings.look = "AgX - Medium High Contrast"
        except Exception:
            pass
        fit_ortho(cam)

    def fit_ortho(cam, margin=1.05):
        sc = bpy.context.scene
        bpy.context.view_layer.update()
        inv = cam.matrix_world.inverted()
        xs, ys = [], []
        for o in sc.objects:
            if o.type in ("CAMERA", "LIGHT"):
                continue
            for corner in o.bound_box:
                p = inv @ (o.matrix_world @ Vector(corner))
                xs.append(p.x)
                ys.append(p.y)
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        aspect = sc.render.resolution_x / sc.render.resolution_y
        scale = max(w, h * aspect) * margin
        cam.data.ortho_scale = scale
        cam.data.shift_x = ((max(xs) + min(xs)) / 2) / scale
        cam.data.shift_y = ((max(ys) + min(ys)) / 2) / scale

    def setup_viewport():
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    sp = area.spaces.active
                    sp.region_3d.view_perspective = "CAMERA"
                    sp.shading.type = "MATERIAL"

    def render_all():
        sc = bpy.context.scene
        os.makedirs(RENDER_DIR, exist_ok=True)
        cam, top_cam = bpy.data.objects["Camara_Principal"], bpy.data.objects["Camara_Cenital"]
        out = {}
        sc.camera = cam
        sc.render.resolution_x, sc.render.resolution_y = 1920, 1440
        sc.render.filepath = os.path.join(RENDER_DIR, "rob_and_run_vista_isometrica.png")
        bpy.ops.render.render(write_still=True)
        out["isometrica"] = sc.render.filepath
        sc.camera = top_cam
        sc.render.resolution_x, sc.render.resolution_y = 1600, 1600
        sc.render.filepath = os.path.join(RENDER_DIR, "rob_and_run_vista_cenital.png")
        bpy.ops.render.render(write_still=True)
        out["cenital"] = sc.render.filepath
        sc.camera = cam
        sc.render.resolution_x, sc.render.resolution_y = 1920, 1440
        return out

    # =========================================================================
    # 8. VALIDACIÓN GEOMÉTRICA
    # =========================================================================
    def xy_to_axial(x, y):
        qf = (2.0 / 3.0 * x) / R
        rf = (-1.0 / 3.0 * x + math.sqrt(3) / 3.0 * y) / R
        sf = -qf - rf
        q, r, s = round(qf), round(rf), round(sf)
        dq, dr, ds = abs(q - qf), abs(r - rf), abs(s - sf)
        if dq > dr and dq > ds:
            q = -r - s
        elif dr > ds:
            r = -q - s
        return (int(q), int(r))

    def point_in_convex(p, poly, shrink=0.001):
        n = len(poly)
        sign = 0
        for i in range(n):
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % n]
            cr = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
            ln = math.hypot(bx - ax, by - ay)
            d = cr / ln
            if abs(d) < shrink:
                return False
            s = 1 if d > 0 else -1
            if sign == 0:
                sign = s
            elif s != sign:
                return False
        return True

    def validate_geometry(top, walls):
        sc = bpy.context.scene
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        res = []

        def chk(name, ok, detail=""):
            res.append({"check": name, "ok": bool(ok), "detalle": detail})

        objs = [o for o in sc.objects if o.type in ("MESH", "FONT", "CURVE")]

        def wbb(o):
            return [o.matrix_world @ Vector(c) for c in o.bound_box]

        # dentro de la base
        ap = BASE_RADIUS * math.cos(math.radians(30))
        outside = []
        for o in objs:
            if o.type == "MESH":
                ev = o.evaluated_get(dg)
                me = ev.to_mesh()
                pts = [o.matrix_world @ v.co for v in me.vertices]
                ev.to_mesh_clear()
            else:
                pts = wbb(o)
            for p in pts:
                if any(p.x * math.cos(math.radians(a)) + p.y * math.sin(math.radians(a)) > ap + 1e-3
                       for a in range(0, 360, 60)):
                    outside.append(o.name)
                    break
        chk("Ningún objeto fuera del tablero", not outside, outside)

        # materiales
        missing = [o.name for o in objs if len(o.data.materials) == 0 or any(m is None for m in o.data.materials)]
        chk("Sin materiales faltantes", not missing, missing)

        # muros duplicados
        wall_objs = [o for o in objs if o.get("tipo_muro") in ("callejon", "banco")]
        keys = [o["arista"] for o in wall_objs]
        norm = [json.dumps(sorted(json.loads(k))) for k in keys]
        chk("Muros: sin geometría duplicada (1 objeto por arista)", len(norm) == len(set(norm)) == len(walls),
            {"objetos": len(norm), "aristas": len(walls)})

        # edificios/marcadores/fichas apoyados en su casilla
        floating = []
        support = [o for o in objs if (o.name.startswith(("Edificio_", "Marcador_", "Ficha_", "Senal_",
                                                          "Paso_Peatonal_")))]
        for o in support:
            zs = [p.z for p in wbb(o)]
            c = xy_to_axial(o.location.x, o.location.y)
            t = top.get(c)
            if t is None or min(zs) < -1e-3 or min(zs) > t + 0.003:
                floating.append({"obj": o.name, "zmin": round(min(zs), 4), "casilla": c, "top": t})
        chk("Sin edificios/marcadores/fichas flotando", not floating, floating)

        # intersección muros vs edificios/marcadores/fichas
        hits = []
        for wo in wall_objs:
            fp = json.loads(wo["footprint"])
            cx = sum(p[0] for p in fp) / len(fp)
            cy = sum(p[1] for p in fp) / len(fp)
            for o in support:
                if (o.location.x - cx) ** 2 + (o.location.y - cy) ** 2 > 2.2 ** 2:
                    continue
                ev = o.evaluated_get(dg)
                me = ev.to_mesh()
                mw = o.matrix_world
                inside = 0
                for v in me.vertices:
                    p = mw @ v.co
                    if wo["zmin"] < p.z < wo["zmax"] and point_in_convex((p.x, p.y), fp):
                        inside += 1
                ev.to_mesh_clear()
                if inside:
                    hits.append({"muro": wo.name, "obj": o.name, "vertices": inside})
        chk("Sin intersecciones muro-edificio/ficha", not hits, hits)

        # fichas
        fichas = [o for o in objs if o.name.startswith("Ficha_")]
        tok = []
        for o in fichas:
            zs = [p.z for p in wbb(o)]
            c = xy_to_axial(o.location.x, o.location.y)
            tok.append({"ficha": o.name, "casilla": list(c), "zmin": round(min(zs), 4), "top": top[c],
                        "altura": round(max(zs) - min(zs), 3)})
        ok_t = (len(fichas) == 4 and all(abs(t["zmin"] - t["top"]) < 0.003 for t in tok)
                and sum(1 for t in tok if t["casilla"] == [0, 5]) == 2
                and sum(1 for t in tok if t["casilla"] == [0, -5]) == 2)
        chk("Fichas: 4, apoyadas en su casilla de inicio", ok_t, tok)
        min_d = min((a.location - b.location).length for i, a in enumerate(fichas) for b in fichas[i + 1:])
        chk("Fichas: sin solapamiento (dist. mínima > 2 x radio base 0.15)", min_d > 0.30, round(min_d, 3))

        # casillas
        tiles = [o for o in objs if o.name.startswith("Casilla_")]
        chk("Casillas: 91 objetos", len(tiles) == 91, len(tiles))
        return res

    # =========================================================================
    # 9. INFORMES
    # =========================================================================
    def write_reports(cells, role, spec, rep, openings, walls, checks, geo, before):
        registry = {f"{q},{r}": role[(q, r)] for (q, r) in sorted(cells)}
        data = {
            "escena_previa": before,
            "registro_coordenadas": registry,
            "conteo": dict(Counter(role.values())),
            "colisiones_detectadas": rep["colisiones_detectadas"],
            "reubicaciones": rep["reubicaciones"],
            "salidas_callejon": {k: [[list(t), list(n)] for t, n in v] for k, v in openings.items()},
            "ajustes_salidas": rep["salidas_callejon"],
            "muros": [{"arista": [list(k[0]), list(k[1])],
                       **{kk: (list(vv) if isinstance(vv, tuple) else vv) for kk, vv in w.items()}}
                      for k, w in sorted(walls.items())],
            "muros_log": rep["muros_log"],
            "validacion_layout": checks,
            "validacion_geometria": geo,
        }
        with open(REPORT_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        L = ["# Rob and Run — Informe del tablero (91 casillas)", ""]
        L += ["## Conteo por rol", "", "| Rol | Casillas |", "|---|---|"]
        L += [f"| {k} | {v} |" for k, v in sorted(Counter(role.values()).items())]
        L += ["", "## Colisiones detectadas en la especificación", ""]
        L += [f"- {tuple(c['coord'])}: {', '.join(c['categorias'])}" for c in rep["colisiones_detectadas"]]
        L += ["", "## Reubicaciones", ""]
        L += [f"- **{r['categoria']}** {tuple(r['de'])} → {tuple(r['a'])}: {r['motivo']}" for r in rep["reubicaciones"]]
        L += ["", "## Salidas de callejones", ""]
        for k, v in openings.items():
            L.append(f"- {k}: " + "; ".join(f"{t} → {n}" for t, n in v))
        L += [f"  - Nota {a['corredor']}: {a['nota']}" for a in rep["salidas_callejon"]]
        L += ["", "## Muros", "",
              f"- Callejón: {sum(1 for w in walls.values() if w['tipo'] == 'callejon')} segmentos",
              f"- Banco: {sum(1 for w in walls.values() if w['tipo'] == 'banco')} segmentos"]
        L += [f"- {m['accion']}: {m['arista']} — {m.get('motivo', '')}" for m in rep["muros_log"]]
        L += ["", "## Validación de layout", ""]
        L += [f"- {'✅' if c['ok'] else '❌'} {c['check']}" + (f" — {c['detalle']}" if c['detalle'] not in ("", [], None) else "")
              for c in checks]
        L += ["", "## Validación geométrica", ""]
        L += [f"- {'✅' if c['ok'] else '❌'} {c['check']}" for c in geo]
        L += ["", "## Registro coordenada → rol", "", "| q | r | rol |", "|---|---|---|"]
        L += [f"| {q} | {r} | {role[(q, r)]} |" for (q, r) in sorted(cells)]
        with open(REPORT_MD, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")


# =============================================================================
# 10. PUNTO DE ENTRADA
# =============================================================================
_MODE = globals().get("RUN_MODE", "build" if HAS_BPY else "standalone")
RESULT = None
if _MODE == "standalone":
    _cells, _role, _alley_of, _spec, _rep, _ops, _walls, _checks = layout_pipeline()
    print(json.dumps({"conteo": Counter(_role.values()), "reubicaciones": _rep["reubicaciones"],
                      "salidas": {k: [[t, n] for t, n in v] for k, v in _ops.items()},
                      "ajustes_salidas": _rep["salidas_callejon"], "muros_log": _rep["muros_log"],
                      "n_muros": len(_walls),
                      "fallos": [c for c in _checks if not c["ok"]],
                      "checks_ok": sum(c["ok"] for c in _checks), "checks_total": len(_checks)},
                     ensure_ascii=False, indent=1, default=list))
elif _MODE == "build":
    RESULT = build_all()
elif _MODE == "render":
    RESULT = render_all()
elif _MODE == "save":
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    RESULT = {"guardado": BLEND_PATH}
