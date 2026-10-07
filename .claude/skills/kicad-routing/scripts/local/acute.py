import pcbnew,sys,math,collections
b=pcbnew.LoadBoard(sys.argv[1]); OX,OY=50,30
ends=collections.defaultdict(list)
for t in b.GetTracks():
    if t.GetClass()=='PCB_VIA': continue
    s=(t.GetStart().x,t.GetStart().y,t.GetLayer()); e=(t.GetEnd().x,t.GetEnd().y,t.GetLayer())
    if s[:2]==e[:2]: continue
    ends[s].append((e,t.GetNetname())); ends[e].append((s,t.GetNetname()))
out=set()
for p,lst in ends.items():
    if len(lst)!=2: continue
    (a,n),(c,_)=lst
    v1=(a[0]-p[0],a[1]-p[1]); v2=(c[0]-p[0],c[1]-p[1])
    ang=math.degrees(math.acos(max(-1,min(1,(v1[0]*v2[0]+v1[1]*v2[1])/(math.hypot(*v1)*math.hypot(*v2))))))
    if ang<89: out.add((n,round(p[0]/1e6-OX,2),round(p[1]/1e6-OY,2),round(ang)))
for o in sorted(out): print(o)
