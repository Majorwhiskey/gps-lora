"""Grid maze router on F.Cu/B.Cu using the board's real copper (inflated by clearance).
usage: maze.py board net  A=x,y,layer  B=x,y,layer  [--rip NET,NET:cost] [--box x0,y0,x1,y1] [--out spec.json]
coords are BOARD coords (page - 50,30). layer F or B. Prints path + which rip nets were crossed."""
import sys, json, heapq, math, argparse
import numpy as np, pcbnew
from matplotlib.path import Path

ap = argparse.ArgumentParser()
ap.add_argument("board"); ap.add_argument("net"); ap.add_argument("a"); ap.add_argument("b")
ap.add_argument("--rip", default=""); ap.add_argument("--box", default="0,50,60,120")
ap.add_argument("--res", type=float, default=0.05); ap.add_argument("--width", type=float, default=0.2)
ap.add_argument("--clr", type=float, default=0.2); ap.add_argument("--via", type=float, default=0.8)
ap.add_argument("--viacost", type=float, default=3.0); ap.add_argument("--bend", type=float, default=0.3)
ap.add_argument("--out"); ap.add_argument("--avoid", default="", help="x0,y0,x1,y1:L;... extra keepouts")
a = ap.parse_args()
OX, OY = 50, 30
R = a.res
x0, y0, x1, y1 = map(float, a.box.split(","))
W, H = int((x1 - x0) / R) + 1, int((y1 - y0) / R) + 1
b = pcbnew.LoadBoard(a.board)
LAY = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu}
rip = {}
for r in filter(None, a.rip.split(",")):
    n, _, c = r.partition(":"); rip[n] = float(c or 20)
# block[l]: 0 free, inf blocked, else rip cost ; owner for reporting
trk = {l: np.zeros((H, W), np.float32) for l in "FB"}
via = np.zeros((H, W), np.float32)
own = {l: {} for l in "FBV"}
xs = x0 + np.arange(W) * R; ys = y0 + np.arange(H) * R

def raster(poly_set, grid, val, key, name):
    for i in range(poly_set.OutlineCount()):
        ch = poly_set.Outline(i)
        pts = np.array([(ch.CPoint(j).x / 1e6 - OX, ch.CPoint(j).y / 1e6 - OY) for j in range(ch.PointCount())])
        if len(pts) < 3: continue
        bx0, by0 = pts.min(0); bx1, by1 = pts.max(0)
        i0 = max(int((bx0 - x0) / R) - 1, 0); i1 = min(int((bx1 - x0) / R) + 2, W)
        j0 = max(int((by0 - y0) / R) - 1, 0); j1 = min(int((by1 - y0) / R) + 2, H)
        if i0 >= i1 or j0 >= j1: continue
        gx, gy = np.meshgrid(xs[i0:i1], ys[j0:j1])
        m = Path(pts).contains_points(np.c_[gx.ravel(), gy.ravel()]).reshape(gx.shape)
        sub = grid[j0:j1, i0:i1]
        if val == np.inf: sub[m] = np.inf
        else: sub[m & (sub != np.inf)] = np.maximum(sub[m & (sub != np.inf)], val)
        if m.any(): own[key].setdefault(name, 0); own[key][name] += int(m.sum())

def item_poly(it, layer, infl):
    ps = pcbnew.SHAPE_POLY_SET()
    it.TransformShapeToPolygon(ps, layer, pcbnew.FromMM(infl), pcbnew.FromMM(0.005), pcbnew.ERROR_OUTSIDE)
    return ps

tr_infl = a.clr + a.width / 2
via_infl = a.clr + a.via / 2
items = list(b.GetTracks())
for f in b.GetFootprints(): items += list(f.Pads())
for it in items:
    n = it.GetNetname()
    if n == a.net:
        if it.GetClass() == "PAD" and it.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
            raster(item_poly(it, it.GetLayerSet().Seq()[0], a.via / 2 + 0.15), via, np.inf, "V", "own pad")
        continue
    v = rip.get(n, np.inf)
    for l, L in LAY.items():
        if not it.IsOnLayer(L): continue
        raster(item_poly(it, L, tr_infl), trk[l], v, l, n)
        raster(item_poly(it, L, via_infl + 0.05), via, v, "V", n)
    # drilled items also block vias by hole clearance on every layer
# keepout / rule areas: GNSS_zone forbids non-GND vias; GNSS U401 courtyard forbids B.Cu tracks
for z in b.Zones():
    if z.GetIsRuleArea() and z.GetZoneName() in ("GNSS_zone",):
        raster(z.Outline(), via, np.inf, "V", "GNSS_zone")
f401 = b.FindFootprintByReference("U401")
if f401:
    cy = f401.GetCourtyard(pcbnew.F_CrtYd)
    if cy.OutlineCount(): raster(cy, trk["B"], np.inf, "B", "U401 courtyard")
# board edge
edge = b.GetBoardEdgesBoundingBox()
ex0, ey0 = edge.GetX() / 1e6 - OX, edge.GetY() / 1e6 - OY
ex1, ey1 = ex0 + edge.GetWidth() / 1e6, ey0 + edge.GetHeight() / 1e6
m = 0.5 + a.width / 2
for g in (trk["F"], trk["B"], via):
    g[:, (xs < ex0 + m) | (xs > ex1 - m)] = np.inf
    g[(ys < ey0 + m) | (ys > ey1 - m), :] = np.inf
for k in filter(None, a.avoid.split(";")):
    bb, _, L = k.partition(":")
    q0, r0, q1, r1 = map(float, bb.split(","))
    msk = (slice(int((r0 - y0) / R), int((r1 - y0) / R) + 1), slice(int((q0 - x0) / R), int((q1 - x0) / R) + 1))
    for l in (L or "FB"):
        trk[l][msk] = np.inf
    via[msk] = np.inf

def cell(s):
    x, y, l = s.split(","); return (l, int(round((float(y) - y0) / R)), int(round((float(x) - x0) / R)))
S, T = cell(a.a), cell(a.b)
# endpoints: clear a small disk so the pad/via itself is reachable
for (l, j, i) in (S, T):
    rr = int(0.35 / R)
    for g in (trk[l],):
        g[max(j - rr, 0):j + rr + 1, max(i - rr, 0):i + rr + 1] = np.minimum(g[max(j - rr, 0):j + rr + 1, max(i - rr, 0):i + rr + 1], 0)
DIRS = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]
VC = a.viacost / R; BP = a.bend / R
def h(l, j, i):
    dj, di = abs(j - T[1]), abs(i - T[2]); return (max(dj, di) + (math.sqrt(2) - 1) * min(dj, di)) + (VC if l != T[0] else 0)
start = (S[0], S[1], S[2], -1)
g = {start: 0.0}; prev = {}
pq = [(h(*S), 0.0, start)]
done = None; n = 0
while pq:
    f_, gc, st = heapq.heappop(pq)
    if g.get(st, 1e18) < gc - 1e-9: continue
    l, j, i, d = st
    if (l, j, i) == T: done = st; break
    n += 1
    if n > 6_000_000: break
    for k, (dj, di) in enumerate(DIRS):
        nj, ni = j + dj, i + di
        if not (0 <= nj < H and 0 <= ni < W): continue
        c = trk[l][nj, ni]
        if c == np.inf: continue
        step = (math.sqrt(2) if dj and di else 1.0) * (1 + c) + (BP if d not in (-1, k) else 0)
        ns = (l, nj, ni, k); ng = gc + step
        if ng < g.get(ns, 1e18):
            g[ns] = ng; prev[ns] = st; heapq.heappush(pq, (ng + h(l, nj, ni), ng, ns))
    if via[j, i] != np.inf:
        ol = "B" if l == "F" else "F"
        if trk[ol][j, i] != np.inf:
            ns = (ol, j, i, -1); ng = gc + VC * (1 + via[j, i])
            if ng < g.get(ns, 1e18):
                g[ns] = ng; prev[ns] = st; heapq.heappush(pq, (ng + h(ol, j, i), ng, ns))
if not done:
    print("NO PATH", n); sys.exit(1)
path = []; st = done
while st in prev or st == start:
    path.append(st)
    if st == start: break
    st = prev[st]
path.reverse()
# crossed rip nets
crossed = set()
for (l, j, i, d) in path:
    if 0 < trk[l][j, i] < np.inf: crossed.add((l, round(xs[i], 2), round(ys[j], 2)))
# compress into segments per layer
segs = []; vias = []
cur = [path[0]]
def P(st): return [round(x0 + st[2] * R, 3), round(y0 + st[1] * R, 3)]
for st in path[1:]:
    if st[0] != cur[-1][0]:
        segs.append((cur[0][0], cur)); vias.append(P(st)); cur = [st]
    else: cur.append(st)
segs.append((cur[0][0], cur))
tracks = []
for l, pts in segs:
    if len(pts) < 2: continue
    out = [P(pts[0])]
    for k in range(1, len(pts) - 1):
        if pts[k][3] != pts[k + 1][3]: out.append(P(pts[k]))
    out.append(P(pts[-1]))
    tracks.append({"net": a.net, "layer": l + ".Cu", "width": a.width, "points": out})
spec = {"tracks": tracks, "vias": [{"net": a.net, "at": v, "diameter": a.via, "drill": 0.4} for v in vias]}
print(json.dumps(spec))
if crossed:
    near = {}
    for l, x, y in crossed: near.setdefault(l, []).append((x, y))
    print("CROSSES rip-able copper at", {l: v[:6] for l, v in near.items()})
if a.out: json.dump(spec, open(a.out, "w"), indent=1)
