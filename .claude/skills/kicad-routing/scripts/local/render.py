"""Render a board region (board coords = page - (50,30)) with pads, tracks, vias, ratsnest.
usage: render.py board.kicad_pcb out.png x0 y0 x1 y1 [drc.json]"""
import sys, json, re, pcbnew
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Polygon
from matplotlib.transforms import Affine2D

pcb, out = sys.argv[1], sys.argv[2]
x0, y0, x1, y1 = map(float, sys.argv[3:7])
drc = sys.argv[7] if len(sys.argv) > 7 else None
OX, OY = 50, 30
b = pcbnew.LoadBoard(pcb)
mm = lambda v: v / 1e6
w = x1 - x0; h = y1 - y0
sc = 22 / max(w, h)
FS = max(2.5, min(7, sc * 1.2))
fig, ax = plt.subplots(figsize=(max(w * sc, 4), max(h * sc, 4)), dpi=110)
ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect("equal")
ax.set_facecolor("#111")
inside = lambda x, y, m=2: x0 - m < x < x1 + m and y0 - m < y < y1 + m

# zones outlines (rule areas dashed)
for z in b.Zones():
    o = z.Outline()
    for i in range(o.OutlineCount()):
        ch = o.Outline(i)
        pts = [(mm(ch.CPoint(j).x) - OX, mm(ch.CPoint(j).y) - OY) for j in range(ch.PointCount())]
        if z.GetIsRuleArea():
            ax.add_patch(Polygon(pts, closed=True, fill=False, ec="yellow", ls="--", lw=0.8))
# courtyards
for f in b.GetFootprints():
    p = f.GetPosition(); fx, fy = mm(p.x) - OX, mm(p.y) - OY
    bb = f.GetBoundingBox(False)
    bx, by = mm(bb.GetX()) - OX, mm(bb.GetY()) - OY
    if not (inside(bx, by, 30)): continue
    ax.add_patch(Rectangle((bx, by), mm(bb.GetWidth()), mm(bb.GetHeight()), fill=False, ec="#555", lw=0.5))
    ax.text(fx, fy, f.GetReference(), color="#aaa", fontsize=6, ha="center", va="center", zorder=9, clip_on=True)
    for pad in f.Pads():
        q = pad.GetPosition(); px, py = mm(q.x) - OX, mm(q.y) - OY
        if not inside(px, py): continue
        sx, sy = mm(pad.GetSize(pcbnew.F_Cu).x), mm(pad.GetSize(pcbnew.F_Cu).y)
        ang = pad.GetOrientation().AsDegrees()
        th = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH or pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
        col = "#d4a017" if th else ("#c33" if pad.IsOnLayer(pcbnew.F_Cu) else "#36c")
        r = Rectangle((px - sx / 2, py - sy / 2), sx, sy, color=col, alpha=0.75, lw=0)
        r.set_transform(Affine2D().rotate_deg_around(px, py, -ang) + ax.transData)
        ax.add_patch(r)
        net = pad.GetNetname().split("/")[-1]
        ax.text(px, py, f"{pad.GetNumber()}\n{net[:10]}", color="w", fontsize=FS, ha="center", va="center", zorder=10, clip_on=True)
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        p = t.GetPosition(); vx, vy = mm(p.x) - OX, mm(p.y) - OY
        if inside(vx, vy):
            ax.add_patch(Circle((vx, vy), mm(t.GetWidth(pcbnew.F_Cu)) / 2, color="#ccc", zorder=6))
            ax.add_patch(Circle((vx, vy), mm(t.GetDrillValue()) / 2, color="#222", zorder=7))
        continue
    s, e = t.GetStart(), t.GetEnd()
    xs = [mm(s.x) - OX, mm(e.x) - OX]; ys = [mm(s.y) - OY, mm(e.y) - OY]
    if not (inside(xs[0], ys[0], 10) or inside(xs[1], ys[1], 10)): continue
    col = {pcbnew.F_Cu: "#f55", pcbnew.B_Cu: "#59f"}.get(t.GetLayer(), "#5f5")
    lw = mm(t.GetWidth()) * sc * 72
    ax.plot(xs, ys, color=col, lw=max(lw, 0.3), alpha=0.7 if t.GetLayer() == pcbnew.F_Cu else 0.6,
            solid_capstyle="round", zorder=5 if t.GetLayer() == pcbnew.F_Cu else 4)
if drc:
    for u in json.load(open(drc))["unconnected_items"]:
        it = u["items"]
        xs = [i["pos"]["x"] - OX for i in it]; ys = [i["pos"]["y"] - OY for i in it]
        ax.plot(xs, ys, color="#0ff", lw=0.6, ls=":", zorder=11)
ax.grid(True, color="#333", lw=0.3)
ax.set_xticks([x for x in range(int(x0), int(x1) + 1)]); ax.set_yticks([y for y in range(int(y0), int(y1) + 1)])
ax.tick_params(labelsize=4)
plt.savefig(out, bbox_inches="tight", facecolor="#111")
