"""add.py board spec.json : spec in BOARD coords (page - 50,30). tracks/vias/moves."""
import pcbnew, json, sys
B, spec = sys.argv[1], json.load(open(sys.argv[2]))
b = pcbnew.LoadBoard(B)
P = lambda x, y: pcbnew.VECTOR2I(pcbnew.FromMM(x + 50), pcbnew.FromMM(y + 30))
for m in spec.get("moves", []):
    f = b.FindFootprintByReference(m["ref"]); f.SetPosition(P(*m["at"]))
    if "rot" in m: f.SetOrientationDegrees(m["rot"])
for t in spec.get("tracks", []):
    net = b.FindNet(t["net"]); assert net, t["net"]
    pts = t["points"]
    for a, c in zip(pts, pts[1:]):
        s = pcbnew.PCB_TRACK(b); s.SetStart(P(*a)); s.SetEnd(P(*c))
        s.SetWidth(pcbnew.FromMM(t.get("width", 0.2))); s.SetLayer(b.GetLayerID(t["layer"])); s.SetNet(net); b.Add(s)
for v in spec.get("vias", []):
    net = b.FindNet(v["net"]); assert net, v["net"]
    o = pcbnew.PCB_VIA(b); o.SetPosition(P(*v["at"])); o.SetDrill(pcbnew.FromMM(v.get("drill", 0.4)))
    o.SetWidth(pcbnew.FromMM(v.get("diameter", 0.8))); o.SetNet(net); o.SetViaType(pcbnew.VIATYPE_THROUGH)
    o.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(o)
b.Save(B)
print("ok")
