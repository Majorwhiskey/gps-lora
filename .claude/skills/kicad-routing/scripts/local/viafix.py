"""Move vias that overlap SMD pads to the nearest legal spot; reconnect with F.Cu + B.Cu stubs.
usage: viafix.py board x,y [x,y ...]   (board coords)  -> writes spec json to stdout"""
import sys, json, math
import numpy as np, pcbnew
from matplotlib.path import Path
OX, OY = 50, 30
CLR, VIA, W, R = 0.2, 0.8, 0.2, 0.025
b = pcbnew.LoadBoard(sys.argv[1])
targets = [tuple(map(float, s.split(","))) for s in sys.argv[2:]]

def polys(it, L, infl):
    ps = pcbnew.SHAPE_POLY_SET()
    it.TransformShapeToPolygon(ps, L, pcbnew.FromMM(infl), pcbnew.FromMM(0.005), pcbnew.ERROR_OUTSIDE)
    out = []
    for i in range(ps.OutlineCount()):
        ch = ps.Outline(i)
        out.append(Path([(ch.CPoint(j).x / 1e6 - OX, ch.CPoint(j).y / 1e6 - OY) for j in range(ch.PointCount())]))
    return out

def seg_pts(a, c, step=0.02):
    n = max(int(math.dist(a, c) / step), 1)
    return np.array([(a[0] + (c[0] - a[0]) * k / n, a[1] + (c[1] - a[1]) * k / n) for k in range(n + 1)])

spec = {"tracks": [], "vias": [], "remove_vias": []}
for (vx, vy) in targets:
    via = None
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA" and abs(t.GetPosition().x / 1e6 - OX - vx) < 0.02 and abs(t.GetPosition().y / 1e6 - OY - vy) < 0.02:
            via = t
    net = via.GetNetname()
    # the pad it sits in
    pad = None
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() == net and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                if p.HitTest(via.GetPosition(), pcbnew.FromMM(VIA / 2)): pad = p
    pc = (pad.GetPosition().x / 1e6 - OX, pad.GetPosition().y / 1e6 - OY)
    # obstacles near
    box = pcbnew.BOX2I(pcbnew.VECTOR2I(pcbnew.FromMM(vx - 3 + OX), pcbnew.FromMM(vy - 3 + OY)), pcbnew.VECTOR2I(pcbnew.FromMM(6), pcbnew.FromMM(6)))
    obs = {"F": [], "B": [], "Fv": [], "Bv": []}
    items = [t for t in b.GetTracks() if t != via] + [p for f in b.GetFootprints() for p in f.Pads()]
    for it in items:
        if not it.GetBoundingBox().Intersects(box): continue
        same = it.GetNetname() == net
        for l, L in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)):
            if not it.IsOnLayer(L): continue
            if same:
                if it.GetClass() == "PAD" and it.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                    obs[l + "v"] += polys(it, L, VIA / 2 + 0.15)   # keep via off own pads
                continue
            obs[l] += polys(it, L, CLR + W / 2 + 0.01)
            obs[l + "v"] += polys(it, L, CLR + VIA / 2 + 0.01)
        if it.GetClass() in ("PCB_VIA",) or (it.GetClass() == "PAD" and it.GetDrillSize().x > 0):
            if not same:
                pass
    # B.Cu connection point: where B.Cu tracks of this net touch the old via
    needB = any(t.GetClass() != "PCB_VIA" and t.GetNetname() == net and t.GetLayer() == pcbnew.B_Cu and
                (t.GetStart() == via.GetPosition() or t.GetEnd() == via.GetPosition()) for t in b.GetTracks())
    best = None
    dirs = []
    for t in b.GetTracks():
        if t.GetClass() != "PCB_VIA" and t.GetNetname() == net and t.GetLayer() == pcbnew.B_Cu:
            for a_, c_ in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
                if a_ == via.GetPosition():
                    dx, dy = (c_.x - a_.x) / 1e6, (c_.y - a_.y) / 1e6; L_ = math.hypot(dx, dy)
                    dirs.append((math.degrees(math.atan2(dy, dx)), L_))
    for r in np.arange(0.4, 2.0, R):
        cand = [d for d, L_ in dirs if r <= L_] + list(np.arange(0, 360, 5))
        for ang in cand:
            nx, ny = vx + r * math.cos(math.radians(ang)), vy + r * math.sin(math.radians(ang))
            p = np.array([[nx, ny]])
            if any(P.contains_points(p)[0] for P in obs["Fv"] + obs["Bv"]): continue
            fs = seg_pts(pc, (nx, ny)); bs = seg_pts((vx, vy), (nx, ny))
            if any(P.contains_points(fs).any() for P in obs["F"]): continue
            if needB and any(P.contains_points(bs).any() for P in obs["B"]): continue
            best = (round(nx, 3), round(ny, 3)); break
        if best: break
    print(net, (vx, vy), "->", best, "needB", needB, file=sys.stderr)
    if not best: continue
    spec["remove_vias"].append([vx, vy])
    spec["vias"].append({"net": net, "at": list(best)})
    spec["tracks"].append({"net": net, "layer": "F.Cu", "points": [[round(pc[0], 3), round(pc[1], 3)], list(best)]})
    if needB: spec["tracks"].append({"net": net, "layer": "B.Cu", "points": [[vx, vy], list(best)]})
print(json.dumps(spec))
