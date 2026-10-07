# Tool reference

Everything the skill drives, with the exact commands. Verified against KiCad 10.0 CLI docs,
the Freerouting CLI docs and the KiCadRoutingTools README (Oct 2026). Re-check `--help`
when versions move.

## 1. Which Python?

pcbnew (SWIG) is importable only from KiCad's interpreter:
- Windows: `"C:\Program Files\KiCad\10.0\bin\python.exe" script.py`
- macOS: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`
- Linux: system `python3` (distro/PPA KiCad packages install pcbnew there)

`python3 scripts/doctor.py` finds it. **SWIG pcbnew is deprecated since KiCad 9 and removed in
KiCad 11**; on 11+ these scripts must move to the IPC API (`kicad-python` / `kipy`, needs a
running KiCad with *Preferences -> Plugins -> Enable KiCad API*).

Do every pcbnew edit that saves a board in a single process per step, and **close the board in
the KiCad GUI** while scripts edit it (KiCad overwrites the files on its next save).

## 2. kicad-cli (KiCad 8+)

```
kicad-cli pcb drc --format json --units mm --severity-all [--schematic-parity] \
    [--refill-zones [--save-board]] [--exit-code-violations] -o drc.json board.kicad_pcb
kicad-cli pcb export svg --layers F.Cu,B.Cu,Edge.Cuts --mode-single -o board.svg board.kicad_pcb   # visual check
kicad-cli pcb render -o board.png board.kicad_pcb            # 3D render (KiCad 9+)
kicad-cli pcb export gerbers -o gerbers/ board.kicad_pcb
kicad-cli pcb export drill -o gerbers/ board.kicad_pcb
```
`--exit-code-violations`: exit 0 = clean, 5 = violations. There is **no** Specctra DSN/SES
command in kicad-cli; use pcbnew (below).

## 3. pcbnew Python cheat sheet (KiCad 9/10)

```python
import pcbnew
b = pcbnew.LoadBoard("board.kicad_pcb")
mm, MM = pcbnew.ToMM, pcbnew.FromMM
P = lambda x, y: pcbnew.VECTOR2I(int(MM(x)), int(MM(y)))

# read
for fp in b.GetFootprints():
    fp.GetReference(), fp.GetPosition(), fp.IsFlipped()
    for pad in fp.Pads(): pad.GetNumber(), pad.GetNetname(), pad.GetPosition(), pad.GetSize()
for t in b.GetTracks():          # PCB_TRACK, PCB_ARC, PCB_VIA
    t.GetClass(), t.GetNetname(), t.GetLayer(), t.GetWidth(), t.IsLocked()
net = b.FindNet("/USB_D+"); net.GetNetClassName()
b.BuildConnectivity(); b.GetConnectivity().GetUnconnectedCount(False)

# write
t = pcbnew.PCB_TRACK(b); t.SetStart(P(10,10)); t.SetEnd(P(12,10)); t.SetWidth(int(MM(0.25)))
t.SetLayer(b.GetLayerID("F.Cu")); t.SetNet(net); t.SetLocked(True); b.Add(t)
v = pcbnew.PCB_VIA(b); v.SetPosition(P(12,10)); v.SetDrill(int(MM(0.3)))
v.SetWidth(int(MM(0.6)))      # KiCad 9+: may need v.SetWidth(int(MM(0.6)), pcbnew.F_Cu) - see common.set_via_size
v.SetNet(net); b.Add(v)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())

# Specctra round trip (headless overloads exist in KiCad 8+; KiCad 7 has only the GUI versions)
pcbnew.ExportSpecctraDSN(b, "board.dsn")
pcbnew.ImportSpecctraSES(b, "board.ses")      # replaces ALL tracks/vias with the session
pcbnew.SaveBoard("out.kicad_pcb", b)
```
`ImportSpecctraSES` deletes existing tracks. `autoroute_freerouting.py` snapshots locked
copper first and restores it; `ses_import.py` is a built-in importer that keeps locked copper
(used automatically when the headless overload is missing).

## 4. Freerouting (Java JAR) - general autorouter

Download `freerouting-<ver>.jar` from github.com/freerouting/freerouting/releases (needs
Java 21+ for 2.x). Headless:

```
java -jar freerouting.jar -de board.dsn -do board.ses --gui.enabled=false -mp 30 -dct 0 -da
```
| flag | meaning |
|---|---|
| `-de file.dsn[+file.rules]` | input design |
| `-do file.ses` | output session |
| `-mp N` | max autorouter passes |
| `-mt N` | optimizer threads (0 = no optimization) |
| `-oit pct` | optimizer improvement threshold (default 0.1%) |
| `-inc A,B` | **ignore these net classes** (e.g. the GND pour class) |
| `-us greedy/global/hybrid`, `-is sequential/random/prioritized` | optimizer strategies |
| `--router.via_costs=N` | higher = fewer vias |
| `--router.layers.routable=true,false` | per-layer enable, top to bottom |
| `--router.layers.preferred_direction_horizontal=true,false` | per-layer direction |
| `-drc file.json` | write Freerouting's DRC in KiCad JSON schema |
| `--user_data_path=dir` | where freerouting.json / logs go |

What it reads from KiCad: net classes (width, clearance, via), keepouts, board outline,
**locked tracks as fixed wiring**. What it ignores: diff pairs, length matching, custom
.kicad_dru rules, current/impedance intent. Hence: critical nets first, locked.

## 5. KiCadRoutingTools - recommended for diff pairs, planes, fanout, length matching

github.com/drandyhaas/KiCadRoutingTools (MIT, KiCad 9 & 10). Works directly on
`.kicad_pcb` files (no DSN), Rust-accelerated A*, ships its own Claude Code skills.

```
git clone https://github.com/drandyhaas/KiCadRoutingTools && cd KiCadRoutingTools
python build_router.py                   # downloads the prebuilt Rust router
pip install numpy scipy shapely
export KICAD_ROUTING_TOOLS=$PWD

python route_planes.py board.kicad_pcb --nets GND --plane-layers B.Cu          # GND plane + pad vias
python route_diff.py  board.kicad_pcb -O --nets "*USB_D*" --diff-pair-gap 0.15 # coupled pairs
python route.py       board.kicad_pcb -O --nets "*" "!GND" "!VCC" \
       --power-nets "+3V3" "VBUS" --power-nets-widths 0.5 0.8 --track-width 0.2
python bga_fanout.py  board.kicad_pcb -c U1 -o fanned.kicad_pcb --clearance 0.1
python qfn_fanout.py  ...                                                       # QFN/QFP escapes
python route_disconnected_planes.py board.kicad_pcb -O                          # repair plane islands
python check_drc.py board.kicad_pcb ; python check_connected.py board.kicad_pcb
python check_orphan_stubs.py board.kicad_pcb
```
`-O` / `--overwrite` writes in place (without it: `<name>_routed.kicad_pcb`). Net patterns are
fnmatch with `!` exclusions. Limitations (from its README): no push-and-shove, no blind/buried
vias. `--help` on every tool; full options in its docs/configuration.md.

Its router does not see locked status the way Freerouting does, so run it on the nets you
choose with `--nets`, and verify locked nets were untouched (`review_routing.py` / DRC).

## 6. freeroute (pip) - Java-free fallback

`pip install freeroute` - Python port of the Freerouting engine, DSN in / SES out.
`autoroute_freerouting.py --engine freeroute-py`. Lower density than the JAR and, in testing,
it did **not** honour net class widths/clearances - expect DRC clearance errors. Use it only to
smoke-test the pipeline or when Java is impossible.

## 7. Custom rules (.kicad_dru) cheat sheet

```
(version 1)
(rule "USB skew"        (condition "A.inDiffPair('/USB_D*')") (constraint skew (max 0.15mm)))
(rule "USB uncoupled"   (condition "A.inDiffPair('/USB_D*')") (constraint diff_pair_uncoupled (max 3mm)))
(rule "USB vias"        (condition "A.inDiffPair('/USB_D*')") (constraint via_count (max 2)))
(rule "Power width"     (condition "A.hasNetclass('PWR')")    (constraint track_width (min 0.5mm) (opt 0.8mm)))
(rule "SW keepaway"     (condition "A.NetName == '/SW' && B.NetName != '/SW'") (constraint clearance (min 0.5mm)))
(rule "Fine pitch U1"   (condition "A.intersectsCourtyard('U1')") (constraint clearance (min 0.12mm)))
(rule "No vias under Y1"(condition "A.Type == 'Via' && A.intersectsCourtyard('Y1')") (constraint disallow via))
(rule "Bus length"      (condition "A.hasNetclass('DDR_DQ')") (constraint length (min 40mm) (max 42mm)))
(rule "Mains creepage"  (condition "A.hasNetclass('MAINS') && !B.hasNetclass('MAINS')")
                        (constraint creepage (min 6mm)))          # KiCad 9+
```
Constraints: clearance, hole_clearance, edge_clearance, track_width, via_diameter, hole_size,
annular_width, diff_pair_gap, diff_pair_uncoupled, skew, length, via_count, disallow,
creepage (9+), zone_connection, thermal_spoke_width. `apply_constraints.py` writes its rules
between `# BEGIN kicad-routing` / `# END kicad-routing` and preserves everything else.

## 8. .kicad_pro net classes (what apply_constraints.py edits)

```json
"net_settings": {
  "classes": [{"name": "PWR", "priority": 1, "track_width": 0.5, "clearance": 0.2,
               "via_diameter": 0.6, "via_drill": 0.3, "diff_pair_width": 0.2, "diff_pair_gap": 0.25, ...}],
  "netclass_patterns": [{"netclass": "PWR", "pattern": "+3V3"}, {"netclass": "PWR", "pattern": "/VDD*"}]
}
"board": {"design_settings": {"rules": {"min_clearance": 0.15, "min_track_width": 0.15,
          "min_via_diameter": 0.6, "min_through_hole_diameter": 0.3, "min_via_annular_width": 0.15,
          "min_copper_edge_clearance": 0.4, "min_hole_to_hole": 0.5, "min_hole_clearance": 0.25}}}
```
Lower `priority` number wins when a net matches several patterns. Netclasses set in the
schematic (net class directives) also land here.
