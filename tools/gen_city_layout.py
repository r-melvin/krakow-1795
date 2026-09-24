#!/usr/bin/env python3
"""Generates data/city_layout.json: the walkable town round the Rynek, read by scripts/city/outer_city.gd.

Run: python3 tools/gen_city_layout.py [build_log]   (build_log: a build_assets.py log, for the triangle totals)

Godot axes, metres: +X east, +Z south, the Rynek square is +-45 around the origin (greybox_district.gd owns it).
The carriage lanes of data/npcs.json (x=-42.5, z=40.5, x=40, z=-25 NW, z=-10.5 E gap) become streets of this grid
and nothing is built within 4 m of their centre lines. Assets face -Y in Blender = +Z in Godot at rot 0;
rot PI faces north, PI/2 east, -PI/2 west.

Sections of the file:
  streets: [{name, pts: [[x, z], ...], w, surface, gutter: centre|kerb|none, lane}]  (paved or trodden ways)
  ground:  [{rect: [x0, z0, x1, z1], surface, look}]  (extra ground patches: squares, yards, the moat ice, the river)
  place:   [{a: asset, p: [x, z], r: rot_y, s?: scale, k: house|prop|big|far}]
  points:  {name: [[x, z, rot], ...]}  (placement points for other systems, e.g. the Maly Rynek stalls)
  checks:  [[name, x, z]]  (reachability targets, printed by the smoke)
  shots:   [[name, [x, y, z], [x, y, z]]]  (the --outer-shot= captures)
"""
import json, math, os, random, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rng = random.Random(1796)
PI = math.pi

# module catalogue: width along its front, distance origin->front face, origin->back face, kind
MOD = {
    "tenement_a": (10.0, 4.44, 5.2), "tenement_b": (8.0, 4.44, 4.0), "tenement_c": (12.0, 4.66, 4.0),
    "tenement_d": (10.0, 4.44, 5.2), "tenement_e": (8.0, 4.66, 4.0),
    "ten_renaissance": (9.0, 4.5, 4.5), "ten_renaissance_b": (9.0, 4.5, 4.5), "ten_gothic": (6.5, 6.0, 6.0),
    "ten_gothic_b": (6.5, 6.0, 6.0), "ten_baroque": (14.0, 5.0, 5.0), "ten_burgher": (10.0, 5.0, 6.3),
    "ten_burgher_b": (10.0, 5.0, 6.3), "ten_timber": (8.0, 5.4, 5.0), "ten_wooden": (9.0, 3.5, 3.5),
    "kaz_house_a": (9.0, 4.0, 4.0), "kaz_house_b": (7.0, 5.5, 5.5), "klep_house": (10.0, 3.5, 3.5),
    "klep_stable": (12.0, 3.5, 3.5), "garb_house": (8.0, 3.25, 3.25), "garb_workshop": (10.0, 3.5, 3.5),
    "kan_house": (13.0, 5.0, 5.0), "sien_passage": (3.6, 4.3, 4.3),
}
POOL_MAIN = ["tenement_a", "tenement_b", "tenement_d", "tenement_e", "ten_renaissance", "ten_renaissance_b",
             "ten_baroque", "ten_burgher", "ten_burgher_b", "ten_gothic", "ten_gothic_b", "kan_house", "kaz_house_a"]
POOL_BACK = ["ten_gothic", "kaz_house_b", "kaz_house_b", "ten_timber", "klep_house", "klep_house", "garb_house"]
POOL_KAZ = ["kaz_house_a", "kaz_house_b", "kaz_house_a", "ten_gothic", "ten_timber", "klep_house"]
POOL_KLEP = ["klep_house", "klep_stable", "ten_timber", "ten_wooden", "garb_house", "klep_house"]
POOL_GARB = ["garb_house", "garb_house", "ten_wooden", "ten_timber", "garb_workshop"]

streets, ground, place, checks, shots = [], [], [], [], []
points = {}


def P(a, x, z, r=0.0, k="house", s=None):
    e = {"a": a, "p": [round(x, 2), round(z, 2)], "r": round(r, 4), "k": k}
    if s:
        e["s"] = s
    place.append(e)


def street(name, pts, w=8.0, surface="cobbles", gutter="kerb", lane=False):
    streets.append({"name": name, "pts": [[round(a, 2), round(b, 2)] for a, b in pts], "w": w, "surface": surface,
                    "gutter": gutter, "lane": lane})


# edge -> (rotation, inward normal (dx, dz), along axis)
EDGE = {"N": (PI, (0, 1)), "S": (0.0, (0, -1)), "W": (-PI / 2, (1, 0)), "E": (PI / 2, (-1, 0))}


def fill_edge(x0, z0, x1, z1, edge, pool, depth_max=99.0, gap_ok=True, passage=None):
    """Houses along one edge of the block rect, fronts on the edge line, facing out. Returns max depth used.
    passage: an along-axis coordinate where a sien_passage (3.6 m) cuts through the row instead of a house."""
    rot, (nx, nz) = EDGE[edge]
    if edge in "NS":
        a0, a1 = x0, x1
        line = z0 if edge == "N" else z1
    else:
        a0, a1 = z0, z1
        line = x0 if edge == "W" else x1
    if passage is not None:
        w, fr, bk = MOD["sien_passage"]
        pa = min(max(passage, a0 + 1.8), a1 - 1.8)
        x, z = (pa, line + nz * fr) if edge in "NS" else (line + nx * fr, pa)
        P("sien_passage", x, z, rot)
        d1 = fill_edge(*((x0, z0, pa - 1.8, z1) if edge in "NS" else (x0, z0, x1, pa - 1.8)), edge, pool, depth_max, gap_ok)
        d2 = fill_edge(*((pa + 1.8, z0, x1, z1) if edge in "NS" else (x0, pa + 1.8, x1, z1)), edge, pool, depth_max, gap_ok)
        return max(d1, d2, fr + bk)
    L = a1 - a0
    mods = []
    rem = L
    tries = 0
    while rem > 6.4 and tries < 60:
        tries += 1
        m = rng.choice(pool)
        w, fr, bk = MOD[m]
        if w <= rem + 0.01 and fr + bk <= depth_max + 2.2:
            mods.append(m)
            rem -= w
    if not mods:
        return 0.0
    gap = rem / (len(mods) + 1) if rem < 3.0 * (len(mods) + 1) else 0.0
    order = mods[:]
    rng.shuffle(order)
    a = a0 + (gap if gap else rem / 2)
    dmax = 0.0
    for m in order:
        w, fr, bk = MOD[m]
        ac = a + w / 2
        if edge in "NS":
            x, z = ac, line + nz * fr
        else:
            x, z = line + nx * fr, ac
        # module local +X runs along the front; for N/W edges the order along the axis is mirrored, harmless
        P(m, x, z, rot)
        if rng.random() < 0.55:                         # a snow drift banked against the front
            da = ac + rng.uniform(-w / 2 + 2.2, w / 2 - 2.2)
            dx, dz = (da, line) if edge in "NS" else (line, da)
            points.setdefault("drifts", []).append([round(dx, 2), round(dz, 2), round(rot, 4)])
        dmax = max(dmax, fr + bk)
        a += w + gap
    return dmax


def walls_edge(x0, z0, x1, z1, edge, low=False):
    """Courtyard walls along a block side: tall monastery_wall (8 m pieces) or a vaultable low_wall (6 m)."""
    rot, (nx, nz) = EDGE[edge]
    if edge in "NS":
        a0, a1, line = x0, x1, (z0 if edge == "N" else z1)
    else:
        a0, a1, line = z0, z1, (x0 if edge == "W" else x1)
    seg = 6.0 if low else 8.0
    n = max(1, int(round((a1 - a0) / seg)))
    step = (a1 - a0) / n
    for i in range(n):
        ac = a0 + step * (i + 0.5)
        x, z = (ac, line + nz * 0.5) if edge in "NS" else (line + nx * 0.5, ac)
        P("low_wall" if low else "monastery_wall", x, z, rot, k="prop")


def yard(x0, z0, x1, z1, ax, dead_end):
    """A back yard between the rows: trodden mud, a lean-to shed against a side wall with crates beside it (the
    climb chain crate -> shed roof -> wall top), a water butt, a ladder against the back of the south row, a
    timber stair to a gallery landing, a laundry line. A dead-end yard (passage on one side only) always gets
    the climb chain, so it is a way through over the wall."""
    ground.append({"rect": [x0, z0, x1, z1], "surface": "mud", "look": "mud"})
    sx = x1 - 1.9 if rng.random() < 0.5 or dead_end else x0 + 1.9
    rot = PI / 2 if sx < (x0 + x1) / 2 else -PI / 2
    zc = (z0 + z1) / 2
    if abs(sx - (ax or -999)) > 4.0:
        P("yard_shed", sx, zc, rot, k="prop")
        P("crate_stack", sx + (1.0 if sx < (x0 + x1) / 2 else -2.9), zc - 2.2, 0.0, k="prop")
    if ax is not None:
        P("water_butt", ax + 2.4, z0 + 0.8, 0.0, k="prop")
    lx = rng.uniform(x0 + 2, x1 - 2)
    if ax is None or abs(lx - ax) > 3.0:
        P("ladder", lx, z1 - 0.05, PI, k="prop")
    if z1 - z0 > 7.0 and rng.random() < 0.6:
        tx = x0 + 3.0 if sx > (x0 + x1) / 2 else x1 - 3.0
        if ax is None or abs(tx - ax) > 4.5:
            P("yard_stair", tx, z0 + 0.7, PI, k="prop")
    if rng.random() < 0.5 and x1 - x0 > 8:
        P("laundry_line", (x0 + x1) / 2 + rng.uniform(-2, 2), zc, PI / 2, k="prop")
    points.setdefault("yards", []).append([round((x0 + x1) / 2, 1), round(zc, 1), 0.0])


def block(x0, z0, x1, z1, main=("N", "S"), pool=POOL_MAIN, back_pool=POOL_BACK, sides=True):
    """Fill a block: N and S edges with houses (main edges from `pool`, the others from back_pool); if the
    block is deep enough, walls (or houses) close the E and W sides between them."""
    D = z1 - z0
    Wd = x1 - x0
    if D < 15.0:
        e = main[0] if main[0] in "NS" else "S"
        fill_edge(x0, z0, x1, z1, e, pool if e in main else back_pool, depth_max=D)
        return
    through = Wd >= 17 and D >= 22
    ax = rng.uniform(x0 + 5, x1 - 5) if through else None
    dead_end = through and rng.random() < 0.3
    dn = fill_edge(x0, z0, x1, z1, "N", pool if "N" in main else back_pool, depth_max=D / 2, passage=ax)
    ds = fill_edge(x0, z0, x1, z1, "S", pool if "S" in main else back_pool, depth_max=D / 2,
                   passage=None if dead_end else ax)
    zz0, zz1 = z0 + 8.8, z1 - 8.8
    low = rng.random() < 0.5
    if sides and zz1 - zz0 > 6.0:
        for e in ("W", "E"):
            if e in main and Wd > 18:
                fill_edge(x0, zz0, x1, zz1, e, pool, depth_max=Wd / 2)
            elif Wd > 12:
                walls_edge(x0, zz0, x1, zz1, e, low=low and e == "W")
    if zz1 - zz0 > 3.0 and Wd > 12:
        yard(x0 + 1.0, zz0, x1 - 1.0, zz1, ax, dead_end)


# ------------------------------------------------------------------ the walls and gates
WX, WN, WS = 100.0, -100.0, 96.0           # wall centre lines: x=+-WX, z=WN (north), z=WS (south)
GATES = {"N": [(10.0, 10.0, "florian_gate"), (-68.0, 9.0, "wawel_gate")], "S": [(-12.0, 9.0, "wawel_gate")],
         "W": [(0.0, 9.0, "wawel_gate")], "E": [(-10.0, 9.0, "wawel_gate")]}


def wall_run(side):
    """Wall segments, towers every ~32 m and the gates along one side of the ring."""
    if side in "NS":
        z = WN if side == "N" else WS
        a0, a1 = -WX, WX
        rot = PI if side == "N" else 0.0
    else:
        x = -WX if side == "W" else WX
        a0, a1 = WN, WS
        rot = -PI / 2 if side == "W" else PI / 2
    def pt(a):
        return (a, z) if side in "NS" else (x, a)
    stops = [(a0, 3.5, "city_tower"), (a1, 3.5, "city_tower")]
    for (a, half, asset) in GATES[side]:
        stops.append((a, half / 2 + 0.2, asset))
    stops.sort()
    # towers between the stops
    extra = []
    for (sa, sh, _), (ea, eh, _) in zip(stops, stops[1:]):
        span = (ea - eh) - (sa + sh)
        n = int(span // 34)
        for k in range(1, n + 1):
            extra.append((sa + sh + span * k / (n + 1), 3.5, "city_tower"))
    stops = sorted(stops + extra)
    for (a, h, asset) in stops:
        if asset == "city_tower" and a in (a0, a1) and side in "WE":
            continue                      # corners are placed by the N and S runs
        x_, z_ = pt(a)
        P(asset, x_, z_, rot, k="big")
    for (sa, sh, _), (ea, eh, _) in zip(stops, stops[1:]):
        s0, s1 = sa + sh - 0.3, ea - eh + 0.3
        n = max(1, int(math.ceil((s1 - s0) / 8.0)))
        step = (s1 - s0) / n
        for k in range(n):
            x_, z_ = pt(s0 + step * (k + 0.5))
            P("wawel_wall", x_, z_, rot, k="big")


for s in "NSWE":
    wall_run(s)
# the frozen moat outside the walls (a strip 8 m wide, 5..13 m out) and bridges at the gates
ground += [{"rect": [-WX - 13, WN - 13, WX + 13, WN - 5], "surface": "snow", "look": "ice"},
           {"rect": [-WX - 13, WS + 5, WX + 13, WS + 13], "surface": "snow", "look": "ice"},
           {"rect": [-WX - 13, WN - 5, -WX - 5, WS + 5], "surface": "snow", "look": "ice"},
           {"rect": [WX + 5, WN - 5, WX + 13, WS + 5], "surface": "snow", "look": "ice"}]
for (a, z, r) in ((-68.0, WN - 9, 0.0), (-12.0, WS + 9, 0.0)):
    P("dock_wharf", a, z, PI / 2, k="prop")
for (x, a) in ((-WX - 9, 0.0), (WX + 9, -10.0)):
    P("dock_wharf", x, a, 0.0, k="prop")
P("barbican", 10.0, -122.0, 0.0, k="big")

# ------------------------------------------------------------------ Old Town streets (inside the walls)
# the carriage lanes, kept as they are, with their extensions
street("Lane west (Szewska side)", [[-42.5, -25], [-42.5, 40.5]], lane=True)
street("Lane south", [[-42.5, 40.5], [40, 40.5]], lane=True)
street("Lane east", [[40, 40.5], [40, -10]], lane=True)
street("Lane NW corner", [[-26, -25], [-42.5, -25]], lane=True, gutter="centre")
street("Lane east gap", [[25, -10.5], [40, -10]], lane=True, gutter="centre")
street("Wall street north", [[-94, -94], [94, -94]], w=6, surface="rough", gutter="centre")
street("Wall street south", [[-94, 90], [94, 90]], w=6, surface="rough", gutter="centre")
street("Wall street west", [[-94, -94], [-94, 90]], w=6, surface="rough", gutter="centre")
street("Wall street east", [[94, -94], [94, 90]], w=6, surface="rough", gutter="centre")
street("Szewska north", [[-42.5, -25], [-42.5, -94]])
street("Szewska south", [[-42.5, 40.5], [-42.5, 90]])
street("Slawkowska", [[-68, -94], [-68, 90]])
street("St Anne's", [[-94, 40.5], [-42.5, 40.5]])
street("Sienna / Mikolajska", [[40, 40.5], [94, 40.5]])
street("Kanonicza cross", [[-94, 66], [94, 66]])
street("Szpitalna cross", [[-94, -66], [94, -66]])
street("Back of the north row", [[-94, -40.5], [14, -40.5]])
street("Florianska", [[10, -40.5], [10, -104]])
street("Grodzka", [[-12, 40.5], [-12, 100]])
street("Mikolajska east", [[40, -10], [104, -10]])
street("East alley", [[44, 14], [94, 14]], w=6, surface="rough", gutter="centre")
street("West alley to the Garbary gate", [[-42.5, 0], [-104, 0]], w=6, surface="rough", gutter="centre")
street("Mariacka lane", [[44, -66], [44, -91]], w=6, surface="rough", gutter="centre")
street("Maly Rynek east street", [[76, -94], [76, 90]])
ground.append({"rect": [46.0, -47.0, 72.0, -14.0], "surface": "cobbles", "look": "cobbles"})   # Maly Rynek
points["maly_rynek_stalls"] = [[52.0, -40.0, 0.0], [57.0, -40.0, 0.0], [62.0, -40.0, 0.2], [52.0, -24.0, PI],
                               [58.0, -24.0, PI], [66.0, -30.0, -PI / 2]]
for (x, z, r) in points["maly_rynek_stalls"]:
    P("market_stall", x, z, r, k="prop")
P("water_pump", 62.0, -31.0, PI / 2, k="prop")
P("horse_trough", 62.0, -28.0, 0.0, k="prop")
P("barrel", 55.0, -37.6, 0.0, k="prop")
P("crate_stack", 67.5, -38.0, 0.3, k="prop")
P("lantern_post", 49.0, -20.0, 0.0, k="prop")
P("lantern_post", 69.0, -44.0, 0.0, k="prop")

# blocks (x0, z0, x1, z1) inside street edges
W1, W2 = (-64.0, -46.5), (-91.0, -72.0)
ZB = [(-91.0, -70.0), (-62.0, -44.5), (-36.5, -3.0), (3.0, 36.5), (44.5, 62.0), (70.0, 87.0)]
for (za, zb) in ZB:
    for (xa, xb) in (W2, W1):
        if (xa, xb) == W2 and (za, zb) == (3.0, 36.5):
            P("collegium_maius", -81.5, 16.0, PI, k="big", s=0.93)          # street front on the z=0 alley
            fill_edge(xa, za, xb, zb, "S", POOL_MAIN, depth_max=8.5)
            continue
        main = ("E", "N", "S") if xb == -46.5 else ("N", "S")
        block(xa, za, xb, zb, main=main, pool=POOL_MAIN if xb == -46.5 or za in (-62.0, 44.5) else POOL_BACK)
# north of the square, west of Florianska
block(-38.5, -91.0, 6.0, -70.0, main=("S",), pool=POOL_MAIN)
block(-38.5, -62.0, 6.0, -44.5, main=("N", "S"), pool=POOL_MAIN)
# east of Florianska, north band; St Mary's and the campanile below it
block(14.0, -91.0, 41.0, -70.0, main=("S",), pool=POOL_MAIN)
block(47.0, -91.0, 72.0, -70.0, main=("S",), pool=POOL_MAIN)
P("campanile", 18.0, -50.0, PI / 2, k="big")
fill_edge(47.0, -62.0, 72.0, -50.0, "S", POOL_MAIN, depth_max=12.0)     # north side of Maly Rynek
# east of the Maly Rynek street
for (za, zb) in ((-91.0, -70.0), (-62.0, -14.0), (-6.0, 11.0), (17.0, 36.5), (44.5, 62.0), (70.0, 87.0)):
    fill_edge(80.0, za, 91.0, zb, "W", POOL_MAIN if za in (-62.0, -6.0, 17.0) else POOL_BACK, depth_max=11.0)
for (za, zb) in ((-6.0, 11.0), (17.0, 36.5), (44.5, 62.0), (70.0, 87.0)):
    block(44.0, za, 72.0, zb, main=("W", "N", "S") if za < 40 else ("N", "S"), pool=POOL_MAIN)
fill_edge(72.0, -46.0, 72.5, -18.0, "E", POOL_BACK, depth_max=8.0) if False else None
fill_edge(47.0, -46.0, 72.0, -14.0, "E", POOL_MAIN, depth_max=0) if False else None
# south of the square
block(-38.5, 44.5, -16.0, 62.0, main=("N", "S"), pool=POOL_MAIN)
block(-38.5, 70.0, -16.0, 87.0, main=("N",), pool=POOL_BACK)
block(-8.0, 70.0, 36.0, 87.0, main=("N",), pool=POOL_MAIN)
# the monastery (Franciscans) south of the lane: an enclosure wall with its gate on the street
P("monastery_gate", 14.0, 46.6, PI, k="big")
for x in (-4.0, 2.0, 26.0, 32.0):
    P("monastery_wall", x, 45.5, PI, k="prop")
for z in (50.0, 58.0):
    P("monastery_wall", -7.5, z, -PI / 2, k="prop")
    P("monastery_wall", 35.5, z, PI / 2, k="prop")
for x in (-4.0, 4.0, 12.0, 20.0, 28.0, 32.0):
    P("monastery_wall", x, 61.5, 0.0, k="prop")
P("prayer_house", 14.0, 55.0, 0.0, k="house")     # the friars' hall inside the enclosure (plain, towerless)
P("shrine_column", 14.0, 49.5, 0.0, k="prop")

# ------------------------------------------------------------------ in the Rynek
P("fountain", 4.5, -16.3, 0.2, k="prop", s=0.85)
P("pillory", -26.0, 19.5, 0.0, k="prop")
P("water_pump", -38.4, 3.0, -PI / 2, k="prop")
P("horse_trough", -38.6, 7.0, PI / 2, k="prop")

# ------------------------------------------------------------------ Kleparz, north beyond the Barbican
street("Kleparz road", [[10, -137], [10, -150]], surface="dirt", gutter="none")
ground.append({"rect": [-12.0, -182.0, 36.0, -150.0], "surface": "mud", "look": "mud"})       # the market square
street("Kleparz west road", [[-12, -166], [-70, -166]], w=6, surface="dirt", gutter="none")
street("Kleparz east road", [[36, -166], [80, -166]], w=6, surface="dirt", gutter="none")
street("Moat road north west", [[-114, -116], [-6, -116]], w=6, surface="dirt", gutter="none")
street("Moat road north east", [[26, -116], [114, -116]], w=6, surface="dirt", gutter="none")
street("Slawkowska outer road", [[-68, -104], [-68, -137], [-40, -137]], w=6, surface="dirt", gutter="none")
street("Kleparz lane", [[10, -137], [-40, -137], [-40, -166]], w=6, surface="dirt", gutter="none")
fill_edge(-12.0, -196.0, 36.0, -182.0, "S", POOL_KLEP, depth_max=14)
fill_edge(-30.0, -182.0, -12.0, -150.0, "E", POOL_KLEP, depth_max=14)
fill_edge(36.0, -182.0, 54.0, -150.0, "W", POOL_KLEP, depth_max=14)
fill_edge(-12.0, -150.0, 4.0, -141.0, "N", POOL_KLEP, depth_max=9)
fill_edge(16.0, -150.0, 36.0, -141.0, "N", POOL_KLEP, depth_max=9)
points["kleparz_stalls"] = [[0.0, -160.0, 0.0], [6.0, -160.0, 0.0], [20.0, -160.0, 0.0], [26.0, -170.0, PI], [2.0, -172.0, PI]]
for (x, z, r) in points["kleparz_stalls"]:
    P("market_stall", x, z, r, k="prop")
P("cart", 14.0, -176.0, 0.5, k="prop")
P("well", 12.0, -166.0, 0.0, k="prop")
P("brewery", 66.0, -150.0, PI, k="big")                  # propination brewhouse on the east road
P("windmill", -60.0, -186.0, 0.4, k="big")
P("carpenter_yard", -56.0, -150.0, PI / 2, k="big")
P("farm_haystack", -48.0, -180.0, 0.0, k="prop")
P("farm_shrine", -44.0, -143.0, PI / 2, k="prop")

# ------------------------------------------------------------------ Garbary, west beyond the gate
street("Garbary road", [[-104, 0], [-180, 0]], surface="dirt", gutter="none")
street("Mill lane", [[-140, 0], [-140, 40]], w=6, surface="dirt", gutter="none")
fill_edge(-178.0, -18.0, -118.0, -4.0, "S", POOL_GARB, depth_max=14)
fill_edge(-136.0, 4.0, -118.0, 18.0, "N", POOL_GARB, depth_max=14)
P("forge", -126.0, -12.0, 0.0, k="big") if False else None
P("bell_foundry", -160.0, 12.0, PI, k="big")
P("tannery_frame", -150.0, 10.0, 0.0, k="prop")
P("cooper_yard", -124.0, 30.0, PI / 2, k="big")
P("watermill", -152.0, 34.0, 0.0, k="big")              # race along x~-146 from z 23 to 45 (the Mlynowka)
P("forge", -128.0, 9.5, PI, k="big")
checks.append(["garbary", -170.0, 0.0])

# ------------------------------------------------------------------ the road south: Grodzka gate, the castle, the docks, Kazimierz
street("Road to Wawel and Kazimierz", [[-12, 100], [-12, 118], [24, 118], [24, 142]], surface="gravel", gutter="kerb")
street("Wawel approach", [[-12, 118], [-45, 118]], w=6, surface="gravel", gutter="none")
street("Riverside", [[-45, 118], [-160, 118]], w=6, surface="dirt", gutter="none")
P("castle_gate", -45.0, 126.0, PI, k="big")
P("wawel_far", -60.0, 225.0, math.atan2(60.0, -225.0), k="far")
# the frozen Vistula west of the castle rock, the Old Vistula arm between Stradom and Kazimierz
ground.append({"rect": [-230.0, 146.0, -60.0, 190.0], "surface": "snow", "look": "ice"})
ground.append({"rect": [-60.0, 128.0, 140.0, 140.0], "surface": "snow", "look": "ice"})
ground.append({"rect": [-160.0, 122.0, -62.0, 146.0], "surface": "gravel", "look": "mud"})     # the quays
for i in range(8):
    P("dock_wharf", -150.0 + i * 8.0, 148.0, 0.0, k="prop")
P("salt_barge", -118.0, 155.0, 0.1, k="prop")
P("kingpin_warehouse", -165.0, 131.0, 0.0, k="big")      # on the quay, back door onto the riverside road
P("bathhouse", -75.0, 129.0, PI, k="big")                 # by the water, its door on the riverside road
points["kingpin_warehouse"] = [[-165.0, 131.0, 0.0]]
points["bathhouse"] = [[-75.0, 129.0, PI]]
P("salt_barge", -86.0, 157.0, -0.08, k="prop")
P("dock_granary", -140.0, 130.0, 0.0, k="big")
P("dock_granary", -126.0, 130.0, 0.0, k="big")
points["fish_market_stalls"] = [[-104.0, 131.0, 0.0], [-98.0, 131.0, 0.0], [-92.0, 131.0, 0.0], [-100.0, 140.0, PI]]
for (x, z, r) in points["fish_market_stalls"]:
    P("market_stall", x, z, r, k="prop")
for (x, z) in ((-102.0, 136.0), (-95.0, 136.5), (-88.0, 135.0)):
    P("barrel", x, z, 0.0, k="prop")
P("crate_stack", -84.0, 131.0, 0.6, k="prop")
P("sacks_crates", -110.0, 142.0, 0.0, k="prop")
# bridge (a timber causeway on the wharf pieces) over the arm into Kazimierz
for z in (130.0, 134.0, 138.0):
    P("dock_wharf", 24.0, z, 0.0, k="prop")
street("Kazimierz Szeroka", [[24, 142], [24, 198]])
street("Kazimierz Jozefa", [[0, 172], [100, 172]], surface="dirt", gutter="none")
ground.append({"rect": [36.0, 144.0, 100.0, 168.0], "surface": "cobbles", "look": "cobbles"})
block(-2.0, 146.0, 20.0, 168.0, main=("E", "S"), pool=POOL_KAZ, back_pool=POOL_KAZ)
block(-2.0, 176.0, 20.0, 198.0, main=("E", "N"), pool=POOL_KAZ, back_pool=POOL_KAZ)
fill_edge(28.0, 176.0, 44.0, 198.0, "W", POOL_KAZ, depth_max=14)
P("kaz_synagogue", 60.0, 186.0, PI, k="big")
P("synagogue_wooden", 84.0, 184.0, PI, k="big")
P("uniate_church", 64.0, 152.5, 0.0, k="big")       # by the road into Kazimierz, facing the square
# the kingpin's townhouse fronts Szeroka: gate on the street, courtyard and back gate towards the Uniate church
P("kingpin_house", 40.0, 156.0, -PI / 2, k="big")
points["kingpin_house"] = [[40.0, 156.0, -PI / 2]]
P("well", 32.0, 163.0, 0.0, k="prop") if False else None
P("fountain", 86.0, 158.0, 0.0, k="prop", s=0.7)
checks += [["kazimierz", 24.0, 190.0], ["docks", -100.0, 136.0], ["castle_gate", -45.0, 118.0]]

# ------------------------------------------------------------------ farmland east beyond the gate
street("Road east", [[104, -10], [200, -10]], surface="dirt", gutter="none")
for i in range(4):
    P("farm_field", 124.0 + i * 8.0, -22.0, 0.0, k="prop")
    P("farm_field", 124.0 + i * 8.0, 4.0, 0.0, k="prop")
for i in range(4):
    P("farm_fence", 124.0 + i * 8.0 - 2.0, -16.5, 0.0, k="prop")
    P("farm_fence", 124.0 + i * 8.0 + 2.0, -16.5, 0.0, k="prop")
    P("farm_fence", 124.0 + i * 8.0 - 2.0, -1.5, 0.0, k="prop")
    P("farm_fence", 124.0 + i * 8.0 + 2.0, -1.5, 0.0, k="prop")
P("farm_cottage", 168.0, 2.0, PI, k="house")
P("farm_barn", 172.0, 16.0, -PI / 2, k="house")
P("farm_haystack", 160.0, 20.0, 0.0, k="prop")
P("farm_haystack_small", 164.0, 26.0, 0.0, k="prop")
P("farm_manor", 172.0, -32.0, 0.0, k="house")
P("farm_shrine", 116.0, -16.0, 0.0, k="prop")
P("gallows", 150.0, -19.0, 0.0, k="prop")
P("windmill", 190.0, 30.0, 1.2, k="big")
checks += [["farmland", 180.0, -10.0], ["kleparz", 10.0, -165.0], ["maly_rynek", 60.0, -30.0],
           ["collegium", -81.0, 0.0], ["grodzka_gate", -12.0, 104.0], ["florian_barbican", 10.0, -140.0]]

# ------------------------------------------------------------------ flagstones and eavesdropping perches in the Rynek
# flagstone strips: St Mary's steps, under the Cloth Hall loggias, in front of the Town Hall, St Adalbert's steps
ground += [{"rect": [27.0, -17.2, 41.0, -14.0], "surface": "cobbles", "look": "flags"},
           {"rect": [16.4, -5.6, 21.6, 5.6], "surface": "cobbles", "look": "flags"},
           {"rect": [-21.6, -5.6, -16.4, 5.6], "surface": "cobbles", "look": "flags"},
           {"rect": [-33.0, 16.1, -17.6, 19.0], "surface": "cobbles", "look": "flags"},
           {"rect": [17.5, 22.5, 24.5, 24.2], "surface": "cobbles", "look": "flags"}]
# perches between first-floor windows (wall face, rot so the perch faces the street), a ladder beside each
for (name, x, z, r, lx, lz) in (("cafe", -12.67, 27.78, PI, -14.3, 27.78), ("brothel_door", -27.78, -4.0, PI / 2, -27.78, -2.3),
                                ("guard_post", -2.0, -27.78, 0.0, -3.7, -27.78)):
    P("perch_ledge", x, z, r, k="prop")
    P("ladder", lx, lz, r, k="prop")
    points.setdefault("perches", []).append([x, z, r])
    points.setdefault("perch_names", []).append(name)

# ------------------------------------------------------------------ underground entrances (culverts and cellars)
# Provisional drain grates at the four corners of the carriage loop round the square, on the outside of each bend,
# 1 m off the kerb (3 m from the lane centre line); they move to the interiors set's Exit_ positions once reported.
points["drain_grates"] = [[-45.5, -28.0, 0.0], [-45.5, 43.5, 0.0], [43.0, 43.5, 0.0], [43.0, -7.0, 0.0]]
for (x, z, r) in points["drain_grates"]:
    P("drain_grate", x, z, r, k="prop")
# culvert outfalls at the foot of the walls into the moat, and one in the river bank below the quays
points["outfalls"] = [[-40.0, -104.2, PI], [40.0, 100.2, 0.0], [-60.0, 146.2, 0.0]]
for (x, z, r) in points["outfalls"]:
    P("outfall_arch", x, z, r, k="big")
P("well_shaft_cap", 12.0, -166.0, 0.0, k="prop") if False else None
# cosmetic stone manhole covers every ~30 m along the cobbled streets, 1.5 m off the centre line
for s_ in streets:
    if s_["surface"] != "cobbles" or s_.get("lane"):
        continue
    for a, b in zip(s_["pts"], s_["pts"][1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        for k in range(int(L // 30)):
            t = (15.0 + 30.0 * k) / L
            dx, dz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            x, z = a[0] + (b[0] - a[0]) * t - dz * 1.5, a[1] + (b[1] - a[1]) * t + dx * 1.5
            if abs(x) < 46 and abs(z) < 46:
                continue
            P("manhole_stone", x, z, 0.0, k="prop")

# ------------------------------------------------------------------ shots
shots = [
    ["city_overhead", [0.0, 330.0, 120.0], [0.0, 0.0, 5.0]],
    ["old_town_north", [10.0, 7.0, -48.0], [10.0, 6.0, -100.0]],
    ["florianska_gate", [10.0, 5.0, -80.0], [10.0, 12.0, -104.0]],
    ["barbican", [30.0, 12.0, -150.0], [10.0, 6.0, -122.0]],
    ["kleparz", [10.0, 6.0, -140.0], [10.0, 3.0, -175.0]],
    ["maly_rynek", [50.0, 6.0, -18.0], [62.0, 3.0, -40.0]],
    ["west_street", [-68.0, 6.0, -60.0], [-68.0, 4.0, 20.0]],
    ["collegium", [-72.0, 5.0, -6.0], [-81.5, 6.0, 8.0]],
    ["grodzka", [-12.0, 6.0, 48.0], [-12.0, 5.0, 100.0]],
    ["garbary", [-106.0, 5.0, -4.0], [-160.0, 3.0, 8.0]],
    ["docks", [-80.0, 8.0, 120.0], [-120.0, 2.0, 150.0]],
    ["castle_gate", [-30.0, 6.0, 112.0], [-45.0, 7.0, 126.0]],
    ["kazimierz", [24.0, 6.0, 144.0], [60.0, 6.0, 180.0]],
    ["farmland", [110.0, 10.0, -12.0], [170.0, 2.0, 0.0]],
    ["wall_moat", [-120.0, 8.0, -110.0], [-100.0, 6.0, -60.0]],
    ["east_street", [44.0, 5.0, 40.5], [76.0, 4.0, -60.0]],
]


def main():
    tri = {}
    log = sys.argv[1] if len(sys.argv) > 1 else None
    if log and os.path.exists(log):
        for line in open(log):
            if line.startswith("[assets] tris"):
                for k, v in re.findall(r"(\w+)=(\d+)", line):
                    tri[k] = int(v)
    total = sum(tri.get(e["a"], 0) for e in place)
    out = {"streets": streets, "ground": ground, "place": place, "points": points, "checks": checks, "shots": shots,
           "stats": {"placed": len(place), "tris_placed": total}}
    with open(os.path.join(ROOT, "data", "city_layout.json"), "w") as f:
        json.dump(out, f, indent=1)
    kinds = {}
    for e in place:
        kinds[e["a"]] = kinds.get(e["a"], 0) + 1
    print("placed %d assets, %d streets, placed tris %d" % (len(place), len(streets), total))
    print(" ".join("%s=%d" % kv for kv in sorted(kinds.items())))


if __name__ == "__main__":
    main()
