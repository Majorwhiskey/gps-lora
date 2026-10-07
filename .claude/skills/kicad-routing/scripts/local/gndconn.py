import pcbnew,sys
b=pcbnew.LoadBoard(sys.argv[1]); OX,OY=50,30
def poly(it,L):
    ps=pcbnew.SHAPE_POLY_SET(); it.TransformShapeToPolygon(ps,L,0,pcbnew.FromMM(0.005),pcbnew.ERROR_INSIDE); return ps
def overlap(a,bb):
    x=pcbnew.SHAPE_POLY_SET(a); x.BooleanIntersection(bb); return x.OutlineCount()>0
nodes=[]; par={}
def find(x):
    while par[x]!=x: par[x]=par[par[x]]; x=par[x]
    return x
def union(a,c): par[find(a)]=find(c)
isl={}
for z in b.Zones():
    if z.GetNetname()!='GND' or z.GetIsRuleArea(): continue
    for L in z.GetLayerSet().Seq():
        fp=z.GetFilledPolysList(L)
        for i in range(fp.OutlineCount()):
            s=pcbnew.SHAPE_POLY_SET(); s.AddOutline(fp.Outline(i))
            for h in range(fp.HoleCount(i)): s.AddHole(fp.Hole(i,h))
            key=(b.GetLayerName(L),i); isl[key]=s; par[key]=key
items=[t for t in b.GetTracks() if t.GetNetname()=='GND']+[p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()=='GND']
for it in items:
    k=it.m_Uuid.AsString(); par[k]=k
    for (ln,i),s in isl.items():
        L=b.GetLayerID(ln)
        if it.IsOnLayer(L) and overlap(poly(it,L),s): union(k,(ln,i))
# track-to-track/pad/via touching on same layer
for a in items:
    for c in items:
        if a is c: continue
        for L in (pcbnew.F_Cu,pcbnew.B_Cu):
            if a.IsOnLayer(L) and c.IsOnLayer(L) and a.GetBoundingBox().Intersects(c.GetBoundingBox()) and overlap(poly(a,L),poly(c,L)): union(a.m_Uuid.AsString(),c.m_Uuid.AsString())
root=find([k for k in isl if k[0]=='GND'][0])
for k,s in isl.items():
    if find(k)!=root:
        bb=s.BBox(); print('DISCONNECTED island',k[0],round(bb.GetX()/1e6-OX,2),round(bb.GetY()/1e6-OY,2),round(bb.GetWidth()/1e6,2),round(bb.GetHeight()/1e6,2),'area',round(s.Area()/1e12,2))
for it in items:
    if find(it.m_Uuid.AsString())!=root:
        n=(it.GetParentFootprint().GetReference()+'.'+it.GetNumber()) if it.GetClass()=='PAD' else it.GetClass()
        print('DISCONNECTED item',n,round(it.GetPosition().x/1e6-OX,2),round(it.GetPosition().y/1e6-OY,2))
