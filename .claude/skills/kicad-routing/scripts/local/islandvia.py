import pcbnew,sys,json,math
import numpy as np
from scipy import ndimage
from matplotlib.path import Path
b=pcbnew.LoadBoard(sys.argv[1]); OX,OY=50,30; R=0.025
gv=[t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()=='GND']
thp=[p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()=='GND' and p.GetDrillSize().x>0]
holes=[(v.GetPosition().x/1e6-OX,v.GetPosition().y/1e6-OY) for v in b.GetTracks() if v.GetClass()=='PCB_VIA']+[(p.GetPosition().x/1e6-OX,p.GetPosition().y/1e6-OY) for f in b.GetFootprints() for p in f.Pads() if p.GetDrillSize().x>0]
def ol_pts(ol): return np.array([(ol.CPoint(j).x/1e6-OX,ol.CPoint(j).y/1e6-OY) for j in range(ol.PointCount())])
# B.Cu obstacle test (other nets) and B.Cu GND fill
bobs=[]
for it in list(b.GetTracks())+[p for f in b.GetFootprints() for p in f.Pads()]:
    if it.GetNetname()=='GND' or not it.IsOnLayer(pcbnew.B_Cu): continue
    ps=pcbnew.SHAPE_POLY_SET(); it.TransformShapeToPolygon(ps,pcbnew.B_Cu,pcbnew.FromMM(0.62),pcbnew.FromMM(0.005),pcbnew.ERROR_OUTSIDE)
    for i in range(ps.OutlineCount()): bobs.append(Path(ol_pts(ps.Outline(i))))
# own-net SMD pads on F (keep via off pads)
fpads=[]
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and p.IsOnLayer(pcbnew.F_Cu):
            ps=pcbnew.SHAPE_POLY_SET(); p.TransformShapeToPolygon(ps,pcbnew.F_Cu,pcbnew.FromMM(0.55),pcbnew.FromMM(0.005),pcbnew.ERROR_OUTSIDE)
            for i in range(ps.OutlineCount()): fpads.append(Path(ol_pts(ps.Outline(i))))
u301=b.FindFootprintByReference('U301'); ant_x=None
spec={"vias":[]}; placed=[]
for z in b.Zones():
    if z.GetNetname()!='GND' or z.GetIsRuleArea() or b.GetLayerName(z.GetLayerSet().Seq()[0])!='F.Cu': continue
    fp=z.GetFilledPolysList(pcbnew.F_Cu)
    for i in range(fp.OutlineCount()):
        ol=fp.Outline(i)
        if any(ol.PointInside(v.GetPosition()) for v in gv) or any(ol.PointInside(p.GetPosition()) for p in thp): continue
        pts=ol_pts(ol); x0,y0=pts.min(0)-0.1; x1,y1=pts.max(0)+0.1
        xs=np.arange(x0,x1,R); ys=np.arange(y0,y1,R); gx,gy=np.meshgrid(xs,ys)
        P=np.c_[gx.ravel(),gy.ravel()]
        m=Path(pts).contains_points(P).reshape(gx.shape)
        for h in range(fp.HoleCount(i)):
            m&=~Path(ol_pts(fp.Hole(i,h))).contains_points(P).reshape(gx.shape)
        d=ndimage.distance_transform_edt(m)*R
        order=np.argsort(-d.ravel())
        got=None; rej={"hole":0,"pad":0,"bcu":0}
        for k in order[:4000]:
            if d.ravel()[k]<0.43: break
            q=(P[k][0],P[k][1])
            if any(math.dist(q,h)<1.0 for h in holes+placed): rej["hole"]+=1; continue
            if any(pp.contains_point(q) for pp in fpads): rej["pad"]+=1; continue
            if any(pp.contains_point(q) for pp in bobs): rej["bcu"]+=1; continue
            got=(round(q[0],3),round(q[1],3)); break
        bb=(round(x0,1),round(y0,1),round(x1,1),round(y1,1))
        print("island",bb,"area",round(ol.Area()/1e12,2),"maxd",round(d.max(),2),"->",got,rej,file=sys.stderr)
        if got: placed.append(got); spec["vias"].append({"net":"GND","at":list(got)})
print(json.dumps(spec))
