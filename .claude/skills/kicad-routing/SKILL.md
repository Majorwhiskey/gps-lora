---
name: kicad-routing
description: Professional PCB routing for KiCad 9/10 boards driven by a CLI agent. Use when asked to route, autoroute, finish, clean up or review the copper of a .kicad_pcb (after placement) - power, decoupling, SMPS loops, crystals, USB/diff pairs, ground pours, stitching vias, net classes, custom DRC rules and the DRC fix loop. Not for schematic capture or component placement.
---

# KiCad professional routing

You are the **layout engineer**; routers and scripts are your hands. LLMs are bad at
geometric search (hundreds of nets, clearances, rip-up/retry) and good at the engineering
judgment that separates a professional board from an autorouted one: constraints, routing
order, layer strategy, which nets must never be autorouted, and honest verification.
This skill encodes that split:

1. **You decide** constraints, stackup use, critical-net geometry and routing order.
2. **Scripts and routers execute** - deterministic scripts for critical nets, an autorouter
   (Freerouting / KiCadRoutingTools) for the bulk.
3. **DRC + review prove it** - and you report what still needs a human.

Read this whole file before starting. Open the references when the phase says so:
- `references/routing-rules.md` - numbers with sources (widths, clearances, vias, stackups, stitching, impedance)
- `references/circuit-recipes.md` - how to route buck/boost, decoupling, crystals, USB, Ethernet, analog, RF, mains
- `references/drc-playbook.md` - every DRC violation type: cause, fix, when to escalate
- `references/tool-reference.md` - exact CLI flags and pcbnew/kicad-cli/Freerouting/KiCadRoutingTools usage
- `templates/routing_plan.example.json` - the plan format

---

## 0. Ground rules (always)

- **Work on copies.** Every script backs up to `.routing_backups/` before writing, or writes
  to `-o`. Keep the user's original untouched until they accept the result.
- **The board must be closed in the KiCad GUI** while scripts run (a `~board.kicad_pcb.lck`
  file means it is open). KiCad will overwrite script edits on its next save.
- **Run pcbnew scripts with KiCad's Python** (`scripts/doctor.py` finds it). Pure-Python
  scripts (`apply_constraints.py`, `trace_width.py`, `drc_report.py`, `doctor.py`) run anywhere.
- **Never lower a rule to pass DRC**, never move footprints without saying so, never add
  DRC exclusions to hide real errors, never let the autorouter touch locked critical copper.
- **Stop and ask** (or report, if unattended) when: placement makes good routing impossible,
  a layer-count change is needed, the netlist is out of date (schematic parity), or 5 DRC
  fix iterations did not converge. A clean report of what is blocked beats a bad board.
- Placement quality decides routing quality. A router cannot fix a decoupling cap 15 mm
  from its pin or a crystal across the board.

## 1. Environment check

```
python3 scripts/doctor.py
```
Needs: pcbnew (KiCad 9/10 Python), kicad-cli (DRC), Java 21+ and a Freerouting jar
(`tools/freerouting-<ver>.jar` or `$FREEROUTING_JAR`). Optional but recommended:
KiCadRoutingTools (`$KICAD_ROUTING_TOOLS`) for diff pairs, plane via-connections, BGA/QFN
fanout and length matching. Missing Java? `--engine freeroute-py` (pip `freeroute`) works for
smoke tests only - it ignores net class widths (see tool-reference.md section 6).

Below, `$S` = this skill's `scripts/` folder and `$PY` = KiCad's Python.

## 2. Intake - know the board before touching it

Collect (ask the user only for what you cannot read from the files or datasheets):

| Need | Why | Default if unknown |
|---|---|---|
| Fab + tier | min track/space/drill | `generic_conservative` |
| Layer count + stackup (thickness, copper oz, inner oz) | impedance, current | 2 layers, 1.6 mm, 1 oz |
| Currents per rail (peak) | track widths, vias | ask; never guess for > 1 A |
| Interfaces (USB HS?, Ethernet, RF, ADC precision) | which recipes apply | read schematic / datasheets |
| Voltages > 30 V or mains | creepage/clearance | stop and ask |
| Enclosure keepouts, connector edges | where copper may not go | none |

Then analyse:
```
$PY $S/analyze_board.py board.kicad_pcb -o analysis.json
```
It prints board size, layers, pad density, nets grouped by **role** (ground, power,
smps_switch_node, smps_boot, feedback_sense, crystal, usb, high_speed, rf, analog, clock,
digital_bus, signal), detected diff pairs (flags names KiCad will not pair), current net
classes, and a **placement pre-flight**:
- `decap_far` - decoupling cap farther than 3 mm from its IC rail pin
- `crystal_far` - crystal farther than 5 mm from its IC
- `off_board` / `no_outline`

Role guesses come from net names - confirm them against the schematic. Unnamed
`Net-(U1-Pad5)` nets: look up the pin function in the datasheet before deciding they are boring.

**Pre-flight gate:** if there are `error` items, or warnings on SMPS input caps / crystals /
decoupling for high-speed ICs, report them and ask whether to proceed. Routing around bad
placement produces a board that DRCs clean and still fails EMC or does not oscillate.
Also run `drc_report.py board.kicad_pcb --parity` - parity issues mean "Update PCB from
Schematic" first.

## 3. Strategy - layers and order

Decide and **write down** (in the plan's `stackup` and `critical_order`):

1. **Layer roles** (routing-rules.md section 4).
   - 2-layer: B.Cu = ground plane (keep it solid; only short perpendicular jumpers),
     F.Cu = parts + signals, GND pour on both, stitched.
   - 4-layer: SIG / GND / PWR / SIG (or SIG / GND / GND / SIG with power pours).
   - 6-layer: SIG / GND / SIG / PWR / GND / SIG.
   - Density > ~8 pads/cm^2 on 2 layers: recommend 4 layers before you start, not after failing.
2. **Routing order** (most constrained first):
   1. Power stage hot loops (SMPS input caps, switch node, boot cap) - recipe B/C
   2. Decoupling caps + their GND vias - recipe A
   3. Crystals / clock sources - recipe E
   4. Differential pairs and impedance-controlled nets (USB, Ethernet, LVDS, RF) - F, G, N
   5. Sensitive analog, sense lines, feedback (Kelvin) - K, L, B.5
   6. Power distribution (pours/planes, then wide traces for branches)
   7. Clocks and fast single-ended buses
   8. Everything else -> autorouter
   9. Ground pours, stitching, cleanup
3. **What the autorouter may touch**: only step 7-8 nets. Everything above is scripted/
   hand-specified and **locked**.

## 4. Constraints - the plan file

Copy `templates/routing_plan.example.json` to `routing_plan.json` next to the board and
fill it in. Every number must be justified:

- **Power widths**: `python3 $S/trace_width.py --current <peak A> [--internal] [--oz 0.5]`
  -> `recommended_width_mm`. Put `current_a` on the class; validation and review re-check it.
- **Impedance-controlled pairs**: width/gap from the fab's impedance calculator for the
  actual stackup (say so in the report if you used placeholders).
- **Clearances**: signal 0.15-0.2 mm, power 0.2-0.3 mm, SW node keep-away 0.5 mm via `keepaways`.
- **Fab preset**: `python3 $S/apply_constraints.py --list-fabs`; override with `fab_overrides`.
- Netclass membership by `patterns` (wildcards on full net names, e.g. `/VDD*`, `+3V3`) or
  exact `nets`. Lower `priority` wins on overlap. Put the pour net (GND) in its own class
  so the autorouter can ignore it.
- `diff_pairs` -> skew / uncoupled-length / gap / via-count DRC rules. `length_groups`
  -> length/skew rules. `custom_rules` -> raw `.kicad_dru` rules (cheat sheet in
  tool-reference.md section 7). `sensitive_refs` -> review flags foreign tracks under them.

Apply (board closed in KiCad):
```
python3 $S/apply_constraints.py routing_plan.json board.kicad_pcb --dry-run   # read it
python3 $S/apply_constraints.py routing_plan.json board.kicad_pcb
```
It refuses plans that violate the fab (ring, drill, width) or IPC current. Then confirm
KiCad parses the rules: `drc_report.py` on the unrouted board must not report rule-syntax
errors, and `analyze_board.py` shows each net's `netclass`.

## 5. Critical routing (scripted, then locked)

For each recipe in your `critical_order`:

1. Get geometry: `$PY $S/route_critical.py pads board.kicad_pcb --refs U3,C10,L1`
   (pad centres, sizes, layer, net - all mm, Y grows downward).
2. Plan the copper on paper first: which layer, width (= netclass width or the recipe's),
   path points with 45-degree bends, where vias go. Keep paths short and direct; do not cross
   other pads; leave clearance >= class clearance + half widths.
3. Draw it:
   - single short link: `$PY $S/route_critical.py connect board.kicad_pcb "U3:5" "C10:1" --width 0.8 --lock`
     (`--style 45|direct|hv|vh`)
   - anything more: write a spec and `$PY $S/route_critical.py apply board.kicad_pcb spec.json --lock`
     ```json
     {"tracks":[{"net":"/SW","layer":"F.Cu","width":1.0,"points":[[131.0,105.05],[131.0,104.2],[128.4,104.2],[128.4,102.5]]}],
      "vias":[{"net":"GND","at":[129.0,108.2],"diameter":0.6,"drill":0.3}],
      "pad_vias":[{"pad":"C10:2","offset":[0,0.9],"diameter":0.6,"drill":0.3,"width":0.4}]}
     ```
     `pad_vias` = a via beside a pad with a stub to it: use for every decoupling/bypass GND pad.
4. **Diff pairs**: prefer KiCadRoutingTools
   `python route_diff.py board.kicad_pcb -O --nets "*USB_D*" --diff-pair-gap <gap>`
   then lock: `$PY $S/route_critical.py lock board.kicad_pcb --nets "/USB_D+,/USB_D-"`.
   Without it, script the pair as two parallel polylines at constant centre spacing
   (width + gap), same bends, same via count.
5. Check each stage before moving on: `python3 $S/drc_report.py board.kicad_pcb` - at this
   point only `unconnected` (not yet routed nets) and expected `via_dangling` on GND pad-vias
   (resolved by the pour) are acceptable. Fix shorts/clearance now; they get harder later.
6. Wrong? `route_critical.py clear --nets X` removes that net's copper; redo.

## 6. Bulk routing (autorouter)

Pick the engine:

| Situation | Engine |
|---|---|
| General signals, 2-4 layers, after critical nets locked | Freerouting JAR via `autoroute_freerouting.py` |
| Diff pairs, length matching, plane via connections, BGA/QFN fanout | KiCadRoutingTools (`route_diff.py`, `route_planes.py`, `bga_fanout.py`, `route.py --nets ...`) |
| No Java available, smoke test only | `--engine freeroute-py` |

Freerouting run:
```
$PY $S/autoroute_freerouting.py board.kicad_pcb -o board_routed.kicad_pcb \
    --jar tools/freerouting.jar --passes 40 --ignore-netclasses GND_POUR --via-cost 80
```
It snapshots locked copper, exports DSN (net classes included), runs Freerouting headless,
imports the SES (KiCad's importer, or the built-in `ses_import.py` fallback that keeps locked
copper), restores/re-locks anything lost, refills zones, prints unconnected before/after.
On 2-layer boards consider `--preferred-horizontal true,false` (top horizontal, bottom vertical)
so B.Cu jumpers run one way and the plane stays in one piece.

**When the router fails** (`unconnected_after` > 0):
1. More passes / lower via cost; then optimize harder with `--fr-arg=-oit --fr-arg=0`.
2. Route the stuck nets yourself (spec), lock, rerun for the remainder.
3. Look at *where* it failed - a blocked channel next to a mis-rotated part is a placement issue -> report.
4. Still failing at > 8 pads/cm^2 on 2 layers -> recommend 4 layers.
Never accept "almost routed". Every unconnected item is listed in the final report.

One-command pass for steps 6-8 (after critical nets are locked):
```
$PY $S/route_pipeline.py board.kicad_pcb --plan routing_plan.json -o board_routed.kicad_pcb --jar tools/freerouting.jar
```
(constraints -> autoroute -> pours -> stitching -> DRC -> review; log in `<output>.pipeline.json`).

## 7. Pours, planes, stitching

```
$PY $S/pours.py pour   board_routed.kicad_pcb --net GND --layers B.Cu,F.Cu --clearance 0.3
$PY $S/pours.py stitch board_routed.kicad_pcb --net GND --pitch 5 --edge-pitch 3 --edge-inset 1.2 --keep-out-courtyards
$PY $S/pours.py fill   board_routed.kicad_pcb
```
- `stitch` places a via only where the filled GND copper covers the whole via plus margin on
  every listed layer, so stitching can never short another net; it also respects hole-to-hole.
- Pitch from routing-rules.md section 7 (lambda/20 at the highest frequency of concern):
  5-8 mm general digital, 3-5 mm board-edge fence, 1-2 mm around RF.
- 4-layer: GND/PWR planes are zones on In1.Cu/In2.Cu covering the board; use KiCadRoutingTools
  `route_planes.py` to drop pad-to-plane vias for SMD pads, or `pad_vias` specs.
- Look at the result (render below). On 2-layer boards check that B.Cu GND is not chopped into
  islands by jumpers; re-route jumpers that cut it.

## 8. Verify - DRC loop and engineering review

```
python3 $S/drc_report.py board_routed.kicad_pcb --refill -o drc_summary.json
$PY $S/review_routing.py board_routed.kicad_pcb --plan routing_plan.json --md review.md
```
- `drc_report.py` exit: 0 clean, 3 warnings only, 4 errors/unrouted. It groups by type,
  sorted P1 (shorts) -> P9 (cosmetic) with a first-line fix; details in `drc-playbook.md`.
- `review_routing.py` checks what DRC does not: unrouted count, diff-pair delta and via symmetry,
  power nets narrower than their IPC width, 90-degree and acute corners, foreign tracks under
  crystals / `sensitive_refs` (SMPS inductor, analog front end, antenna).

Loop: fix the highest-priority group -> refill -> re-run both -> repeat. **Max 5 iterations.**
Fix causes, not instances (drc-playbook "Golden rules").

Visual check (always look at the board before claiming success):
```
kicad-cli pcb export svg --layers F.Cu,B.Cu,Edge.Cuts --mode-single -o board.svg board_routed.kicad_pcb
```
Convert to PNG if your tools need it (e.g. `cairosvg`) and inspect: long detours, tracks
under the inductor/crystal, chopped planes, unstitched islands, spaghetti around connectors.

## 9. Report and hand-off

Deliver `board_routed.kicad_pcb` (+ .kicad_pro/.kicad_dru) and a short report:
- What was routed how (critical nets by script, bulk by which engine), layer strategy.
- Constraint table (net classes, widths with the current they were sized for, diff pair rules).
- DRC result (errors/warnings/unconnected) and review issues still open, with locations.
- **Needs human review**: impedance assumptions (placeholder widths?), SMPS loop, any neck-downs,
  anything the datasheet layout guide specifies that you could not verify, cosmetic DRC items left.
- Placement problems found and not fixed.
Recommend the user open the board in KiCad, run DRC there, and inspect in 3D before ordering.

---

## Anti-patterns (do not do these)

- Autorouting everything in one shot, including power, USB and crystals.
- Using Default 0.25 mm width for a 2 A rail because "DRC passed".
- Letting Freerouting route a diff pair (it treats P and N as unrelated nets).
- Splitting the ground plane "for analog" without a datasheet reason.
- Routing on B.Cu of a 2-layer board as if it were a free signal layer (plane destroyed).
- Stitching vias by hand-guessed coordinates (shorts) - use `pours.py stitch`.
- Fixing clearance errors by reducing clearance globally.
- Declaring success from DRC alone without `review_routing.py` and a visual check.
- Reporting "routed" with unconnected items remaining.

## Script index

| Script | Python | Purpose |
|---|---|---|
| `doctor.py` | any | environment check |
| `analyze_board.py` | KiCad | inventory, net roles, diff pairs, placement pre-flight |
| `trace_width.py` | any | IPC-2221 width / via current / voltage drop |
| `apply_constraints.py` | any | plan -> .kicad_pro net classes, patterns, fab rules, .kicad_dru |
| `route_critical.py` | KiCad | pads query, pad-to-pad connect, JSON spec tracks/vias, lock, clear |
| `autoroute_freerouting.py` | KiCad | DSN -> Freerouting/freeroute -> SES, locked copper protected |
| `ses_import.py` | KiCad | built-in SES importer (fallback, keeps locked copper) |
| `pours.py` | KiCad | zones, safe GND stitching grid + edge fence, refill |
| `drc_report.py` | any (+KiCad fallback) | kicad-cli DRC -> prioritised summary |
| `review_routing.py` | KiCad | post-route engineering review |
| `route_pipeline.py` | KiCad | constraints -> autoroute -> pours -> stitch -> DRC -> review |
| `tests/make_test_board.py` | KiCad | synthetic board to smoke-test the toolchain |

Smoke test after install (builds a synthetic board, runs the full pipeline, prints the verdict):
```
bash tests/smoke_test.sh            # uses $FREEROUTING_JAR if set, else pip 'freeroute'
```
The synthetic board's routing will not be clean with freeroute-py - the test proves the
toolchain runs end to end, not routing quality.
