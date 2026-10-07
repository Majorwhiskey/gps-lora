import pcbnew,sys
b=pcbnew.LoadBoard(sys.argv[1])
r=lambda v:round(v,3)
for n in sys.argv[2:]:
  print('==',n)
  for t in b.GetTracks():
    if t.GetNetname()!=n: continue
    s,e=t.GetStart(),t.GetEnd()
    if t.GetClass()=='PCB_VIA': print('  via',r(s.x/1e6-50),r(s.y/1e6-30))
    else: print('  ',t.GetLayerName(),r(s.x/1e6-50),r(s.y/1e6-30),'->',r(e.x/1e6-50),r(e.y/1e6-30),'w',t.GetWidth()/1e6)
  for fp in b.GetFootprints():
    for p in fp.Pads():
      if p.GetNetname()==n: print('  pad',fp.GetReference()+'.'+p.GetNumber(),r(p.GetPosition().x/1e6-50),r(p.GetPosition().y/1e6-30))
