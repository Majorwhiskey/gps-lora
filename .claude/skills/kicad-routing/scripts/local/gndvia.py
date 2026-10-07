"""For each REF.PAD (GND SMD pad) find the nearest legal GND via spot + F.Cu stub. usage: gndvia.py board REF.PAD ..."""
import sys, json, math
import numpy as np, pcbnew
from matplotlib.path import Path
OX, OY = 50, 30
CLR, VIA, W = 0.2, 0.8, 0.25
b = pcbnew.LoadBoard(sys.argv[1])
def polys(it, L, infl):
    ps = pcbnew.SHAPE_POLY_SET()
    it.TransformShapeToPolygon(ps, L, pcbnew.FromMM(infl), pcbnew.FromMM(0.005), pcbnew.ERROR_OUTSIDE)
    return [Path([(ps.Outline(i).CPoint(j).x / 1e6 - OX, ps.Outline(i).CPoint(j).y / 1e6 - OY) for j in range(ps.Outline(i).PointCount())]) for i in range(ps.OutlineCount())]
def seg(a, c, step=0.02):
    n = max(int(math.dist(a, c) / step), 1)
    return np.array([(a[0] + (c[0] - a[0]) * k / n, a[1] + (c[1] - a[1]) * k / n) for k in range(n + 1)])
edge = b.GetBoardEdgesBoundingBox()
ex0, ey0 = edge.GetX() / 1e6 - OX, edge.GetY() / 1e6 - OY; ex1, ey1 = ex0 + edge.GetWidth() / 1e6, ey0 + edge.GetHeight() / 1e6
placed = []
spec = {"tracks": [], "vias": []}
for rp in sys.argv[2:]:
    ref, pn = rp.split(".")
    pad = [p for p in b.FindFootprintByReference(ref).Pads() if p.GetNumber() == pn][0]
    pc = (pad.GetPosition().x / 1e6 - OX, pad.GetPosition().y / 1e6 - OY)
    box = pcbnew.BOX2I(pcbnew.VECTOR2I(pcbnew.FromMM(pc[0] - 4.5 + OX), pcbnew.FromMM(pc[1] - 4.5 + OY)), pcbnew.VECTOR2I(pcbnew.FromMM(9), pcbnew.FromMM(9)))
    F, V = [], []
    for it in list(b.GetTracks()) + [p for f in b.GetFootprints() for p in f.Pads()]:
        if not it.GetBoundingBox().Intersects(box): continue
        same = it.GetNetname() == "GND"
        for L in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not it.IsOnLayer(L): continue
            if same:
                if it.GetClass() == "PAD" and it.GetAttribute() == pcbnew.PAD_ATTRIB_SMD: V += polys(it, L, VIA / 2 + 0.15)
                elif it.GetClass() == "PCB_VIA" or (it.GetClass() == "PAD"): V += polys(it, L, VIA / 2 + 0.2)
                continue
            if L == pcbnew.F_Cu: F += polys(it, L, CLR + W / 2 + 0.01)
            V += polys(it, L, CLR + VIA / 2 + 0.01)
    best = None
    for r in np.arange(0.5, 3.0, 0.025):
        for ang in range(0, 360, 5):
            nx, ny = pc[0] + r * math.cos(math.radians(ang)), pc[1] + r * math.sin(math.radians(ang))
            if not (ex0 + 1 < nx < ex1 - 1 and ey0 + 1 < ny < ey1 - 1): continue
            if any(math.dist((nx, ny), q) < VIA + 0.25 for q in placed): continue
            if any(P.contains_point((nx, ny)) for P in V): continue
            if any(P.contains_points(seg(pc, (nx, ny))).any() for P in F): continue
            best = (round(nx, 3), round(ny, 3)); break
        if best: break
    print(rp, pc, "->", best, file=sys.stderr)
    if best:
        placed.append(best)
        spec["vias"].append({"net": "GND", "at": list(best)})
        spec["tracks"].append({"net": "GND", "layer": "F.Cu", "width": W, "points": [[round(pc[0], 3), round(pc[1], 3)], list(best)]})
print(json.dumps(spec))
