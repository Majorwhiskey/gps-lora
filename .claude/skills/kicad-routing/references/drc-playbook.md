# DRC playbook

`drc_report.py` groups violations by type, sorts them by priority and prints a first-line
fix. This file is the longer version: **cause -> diagnosis -> fix -> when to escalate**.

Work in priority order. Re-run DRC after each class of fix, not after each item.
Hard cap: **5 fix-and-recheck iterations**, then stop and report what remains.

## Golden rules for fixing

1. Never "fix" DRC by lowering rules below what the design needs (clearance, widths, fab mins).
   If a rule seems wrong, the plan was wrong - change the plan, re-apply, and say so.
2. Never move a footprint to fix DRC without telling the user - placement is a design decision.
3. Never delete or modify **locked** copper (the critical routing) to make the autorouter happy;
   unlock deliberately, re-route that net properly, re-lock.
4. Never add exclusions to silence real errors. Exclusions are only for documented, accepted
   cases (e.g. a solder-mask bridge the fab confirmed is fine), listed in the report.
5. Fix the cause, not the instance: 40 clearance errors on one netclass usually means the class
   clearance is larger than the gaps the placement allows, not 40 separate problems.

## P1 - Shorts (`shorting_items`, `tracks_crossing`)

Cause: two nets touching - usually a scripted/hand track drawn through another net, a
stitching via on top of a track, or a bad SES import.
Fix: delete the offending item(s) (`route_critical.py clear --nets X` for a whole net), re-route.
If shorts appear right after autorouting: the import/scale is wrong - re-run with
`--importer builtin` or the other engine, and compare pad hits.
Escalate: never ship with a short.

## P2 - Unconnected (`unconnected_items`)

Cause: router could not complete, nets ignored on purpose (pour nets before pouring), or
a pour island did not reach a pad.
Diagnose: which nets? If they are the pour net (GND), pour + stitch first, then re-check.
For signals:
1. Re-run the autorouter with more passes (`--passes 60`) and lower via cost.
2. Free space: remove unnecessary pour on signal layers during routing (pour after).
3. Route the stuck nets manually with a spec, lock, re-run autorouter for the rest.
4. Check the placement: a part rotated the wrong way often blocks a whole bus (escalate).
5. On 2-layer boards with > ~8 pads/cm^2 consider recommending 4 layers.
Escalate when the remaining connections need placement changes or a layer count change.

## P3 - Clearance (`clearance`, `hole_clearance`, `copper_edge_clearance`, `hole_to_hole`)

- Many on the same netclass -> class clearance unrealistic for the placement (fine-pitch pads
  are closer than the class clearance). Use a custom rule to relax clearance **only at the
  footprint** (`A.intersectsCourtyard('U1')`) instead of globally, or neck down widths there.
- Track vs pad of fine-pitch IC -> track entered between pins; re-route outside.
- `hole_to_hole` / `hole_clearance` after stitching -> stitching via too close to an existing
  via/track; delete that stitching via (they are disposable) or re-run stitch with larger
  `--hole-gap` / `--clearance`.
- `copper_edge_clearance` -> track/pour too close to edge: re-route; zones obey the board's
  min edge clearance automatically after refill.
- Zone vs track clearance after editing tracks -> stale fill; refill (`pours.py fill`) and re-check.

## P4 - Rule / fab / signal integrity

- `track_width`: track narrower than its netclass/rule. Usually the autorouter used Default
  width for a net whose class assignment is wrong -> fix patterns in the plan, re-apply,
  re-route that net.
- `annular_width`, `drill_out_of_range`, `via_diameter`: via size below fab/rules - set
  the netclass via size correctly; replace vias.
- `diff_pair_*`, `skew`, `length_out_of_range`, `via_count`: SI constraints from the plan.
  Re-route the pair together; add meanders on the shorter member; reduce vias.
  If the constraint is unachievable with the placement, escalate with the numbers.

## P5 - Power / pours

- `starved_thermal`: pad gets fewer than the required spokes -> clear tracks around the pad,
  enlarge spoke width, or use solid connection for that pad/zone.
- `isolated_copper`: set island removal to always (the `pour` command does) or stitch it.
- `zones_intersect`: overlapping zones of different nets with equal priority -> set priorities.

## P6 - Cleanup

- `track_dangling`: stub. Delete it. (Antenna, and looks amateur.)
- `via_dangling`: via connected on one layer only. A stitching via that only touches pour on
  one layer = the pour is missing on the other layer there; delete it. A GND via from
  `pad_vias` before the plane exists is expected - it resolves after the pour.

## P7 - Placement (`courtyards_overlap`, `footprint` placement issues)

Not a routing problem. Report to the user; do not move parts silently.

## P8/P9 - Cosmetic and library (`silk_*`, `solder_mask_bridge`, `lib_footprint_*`, text)

Do not block routing sign-off on these, but list them. Silkscreen over pads gets clipped by
the fab. Solder mask bridges between fine-pitch pads are normal for many fabs (they cannot
hold a dam that thin) - mention it.

## Schematic parity (`--parity`)

Footprints/nets differ from the schematic -> the board is out of date. Stop and tell the user
to Update PCB from Schematic; routing on an out-of-date netlist is wasted work.

## Reading KiCad DRC JSON yourself

`kicad-cli pcb drc --format json --severity-all --units mm -o drc.json board.kicad_pcb`

Top-level keys: `violations[]` (each with `type`, `severity`, `description`,
`items[] {description, pos{x,y}, uuid}`), `unconnected_items[]`, `schematic_parity[]`.
Exit code with `--exit-code-violations`: 0 clean, 5 violations present.
