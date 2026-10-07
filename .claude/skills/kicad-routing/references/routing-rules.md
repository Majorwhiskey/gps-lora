# Routing rules reference

Numbers here are **defaults to start from**, not laws. Each one says where it comes
from so you can tell when to deviate. When a component datasheet or the fab's
published capability conflicts with this file, the datasheet/fab wins.

Contents
1. Current capacity (track width)
2. Clearance and voltage spacing
3. Vias
4. Layer stackups and layer assignment
5. Return paths and reference planes
6. Crosstalk and spacing between signals
7. Ground pours and stitching
8. Controlled impedance and differential pairs
9. Length / timing matching
10. Geometry hygiene (corners, stubs, teardrops, necks)
11. Manufacturing (DFM) defaults
Sources

---

## 1. Current capacity (track width)

IPC-2221 relation (what `scripts/trace_width.py` implements):

    I = k * dT^0.44 * A^0.725      A in mil^2, I in A, dT in degC
    k = 0.048 external, 0.024 internal

- Internal layers dissipate heat worse; for the same current they need roughly 2-2.6x the
  cross-section of an outer-layer track.
- 1 oz/ft^2 copper is about 35 um (1.378 mil). Many fabs make **inner layers 0.5 oz** on
  standard 4-layer stackups - check before sizing internal power traces.
- 10 degC rise is a conservative target; 20 degC is common for general designs.
- IPC-2221 is conservative. IPC-2152 (plane-proximity aware charts) usually allows narrower
  traces. If you are space-limited, say so in the report rather than silently going narrow.

Quick table (IPC-2221, 1 oz external, 10 degC rise, before margin):

| Current | Min width | Use (with ~25% margin, rounded up) |
|---|---|---|
| 0.25 A | ~0.12 mm | 0.20 mm (signal default) |
| 0.5 A | ~0.18 mm | 0.25 mm |
| 1 A | ~0.30 mm | 0.40 mm |
| 2 A | ~0.78 mm | 1.0 mm |
| 3 A | ~1.37 mm | 1.75 mm, or a pour |
| 5 A+ | - | pour / polygon on two layers + via arrays |

Also check **voltage drop**: `trace_width.py --current 3 --length 40` prints resistance and drop.
A 40 mm, 1.75 mm wide 1 oz track at 3 A drops ~34 mV - fine for 12 V, significant for a 1.0 V core.

Rules:
- Size power tracks for the **peak** current the path sees (inrush, motor stall, LED pulses).
- Neck-downs to reach fine-pitch pads are acceptable if short (< ~1 mm) - widen immediately after.
- Ground returns carry the same current as the supply - a pour handles this; a thin GND
  trace does not.

## 2. Clearance and voltage spacing

- Signal clearance default: **0.15-0.2 mm** (fab minimums are lower; don't design at the limit).
- Power nets: 0.2-0.3 mm. Switch nodes: 0.3-0.5 mm from everything (EMI, not voltage).
- Copper to board edge: >= 0.3-0.5 mm (V-score panels need more; check the fab).
- **Higher voltages**: use IPC-2221 Table 6-1 spacing (by voltage, internal vs external, coated
  vs uncoated). For mains / isolation barriers use the safety standard's **creepage and
  clearance** (e.g. IEC 62368-1) - typically several mm, plus slots. KiCad 9+ has a `creepage`
  constraint in custom rules. Never let an autorouter cross an isolation barrier: add a
  rule area keepout over the barrier before autorouting.

## 3. Vias

- Standard through via: 0.6 mm pad / 0.3 mm drill (cheap everywhere). 0.45/0.2 for denser
  4-layer boards if the fab tier supports it.
- Annular ring = (pad - drill) / 2. Keep >= 0.15 mm on 2-layer, >= 0.125 mm on standard multilayer.
- Via current (rough): a 0.3 mm drill, 25 um plated barrel behaves like a ~0.94 mm wide trace of
  25 um copper -> on the order of 1-2 A at 10 degC. Derate 50% and **use multiple vias** for power
  (`trace_width.py --current 3 --via-drill 0.3` prints how many).
- Each signal via adds inductance (~0.5-1 nH) and capacitance (~0.3-1 pF). Minimise vias on
  fast nets; keep P/N via counts equal on diff pairs.
- Every signal via that changes reference plane needs a **return (stitching) via** nearby
  (see section 5).
- Via-in-pad only with filled/capped vias (costs extra). Otherwise keep vias off SMD pads
  (solder wicking) - put them just outside the pad with a short stub.
- Thermal pads (QFN exposed pad, power packages): array of vias (e.g. 0.3 mm drill, 1.0-1.2 mm
  pitch) into the ground plane; follow the datasheet pattern.

## 4. Layer stackups and layer assignment

**2-layer (1.6 mm)** - the most common hobby/low-cost case.
- Make B.Cu as close to a solid GND plane as possible. Route signals on F.Cu; use B.Cu only
  for short jumpers, routed **perpendicular** and short so the plane is not cut into islands.
- Pour GND on F.Cu too, stitched to B.Cu.
- Controlled impedance is hard on 1.6 mm 2-layer (the plane is ~1.5 mm away -> very wide
  traces). Use **coplanar waveguide with ground** (ground pour beside the trace) for USB/RF;
  get width/gap from the fab's impedance calculator.

**4-layer (recommended for anything with USB HS, Ethernet, SMPS > 1 A, RF, or dense MCU)**
- Default: **L1 SIG / L2 GND / L3 PWR (or SIG+PWR pours) / L4 SIG**.
- L2 is a solid, unbroken ground. Fast signals on L1 reference L2.
- Signals on L4 reference L3; if L3 is a power plane, stitch L3 to GND with caps near layer
  transitions, or make L3 GND too (SIG/GND/GND/SIG is excellent for EMC on dense boards,
  with power routed as pours on L1/L4).
- Route L1 and L4 orthogonally where they overlap (horizontal vs vertical preference).

**6-layer**: SIG / GND / SIG / PWR / GND / SIG (or SIG/GND/SIG/SIG/GND/SIG with power pours).
Every signal layer adjacent to a ground plane.

Assignment rules:
- Critical/fast nets on the layer adjacent to solid GND, with the fewest layer changes.
- Never route fast signals over a split or a gap in the reference plane.
- Power distribution: pours/planes first, traces only for low current branches.

## 5. Return paths and reference planes

- Every signal current returns directly underneath the trace (at high frequency) on the
  nearest plane. **Breaking that plane under a signal = loop antenna + crosstalk.**
- Do not split the ground plane into AGND/DGND under a mixed-signal part unless the datasheet
  demands it; prefer one solid GND with careful **partitioning by placement** (analog parts and
  their returns kept in one area, digital in another).
- When a signal via moves from L1 (ref L2 GND) to L4 (ref L3), place a GND via (or a cap
  between the two planes) within ~1-2 mm of the signal via so return current can follow.
- Slots, rows of vias with merged antipads, and long tracks on the plane layer all cut planes.
  After routing a 2-layer board, look at B.Cu: islands and long slots are the first EMC problem.

## 6. Crosstalk and spacing between signals

- **3W rule**: centre-to-centre spacing >= 3x track width between parallel aggressive signals
  (clocks, fast edges) and victims; for critical clocks use >= 5W or a grounded guard.
- Minimise parallel run length between unrelated fast nets, especially on adjacent layers
  (broadside coupling) - route adjacent signal layers orthogonally.
- Keep clocks, SMPS switch nodes and fast digital away from analog inputs, crystal pins, RF and
  board-edge connectors.
- Diff pairs to other signals: >= 3x pair gap, more for clocks; TI's guideline for USB2 pairs is
  >= 50 mil (1.27 mm) to clocks/periodic signals.

## 7. Ground pours and stitching

- Pour GND on free areas of signal layers and **stitch** to the main GND plane. An un-stitched
  copper island is an antenna.
- Stitching via pitch: **<= lambda/20 at the highest frequency of concern** (lambda in FR-4
  = c / (f * sqrt(er_eff)), er_eff ~ 3.5-4.2). Practical values:
  - general digital/MCU boards: 5-8 mm grid
  - board-edge fence: 3-5 mm pitch, 1-2.5 mm in from the edge
  - RF sections / along RF traces: 1-2 mm (lambda/20 at 6 GHz is ~1.2 mm)
- Place a GND via next to every decoupling cap GND pad and every IC GND pin (one per pad,
  not shared) - short loop = low inductance.
- Remove isolated copper islands (zone island removal = always) unless you stitch them.
- Thermal reliefs on pour connections for hand-solderable / wave-soldered pads; solid
  connections for high-current pads and thermal pads.

## 8. Controlled impedance and differential pairs

- Common targets: USB 2.0 = 90 ohm differential (+-15%); Ethernet MDI = 100 ohm diff;
  LVDS/MIPI = 100 ohm diff; PCIe = 85 ohm (gen 3+)/100 ohm diff; single-ended high speed
  and RF = 50 ohm.
- **Width and gap come from the fab's stackup + impedance calculator**, not from a rule of thumb.
  Put the result in the netclass (`diff_pair_width`, `diff_pair_gap`) and ask the fab for
  impedance control if margins are tight.
- KiCad only treats nets as a pair if names end in `_P/_N`, `+/-`, or `P/N`. `USB_DP/USB_DM`
  is **not** a pair to KiCad - rename to `USB_D+/USB_D-` in the schematic.
- Route the pair together: same layer, constant gap, symmetrical around obstacles, equal via
  count, no stubs (series resistors/ESD parts placed in-line with the pair).
- Keep the pair over solid ground for its whole length; no plane splits; >= ~2 mm (90 mil per
  TI) from the reference plane edge.
- Uncoupled length (pad fan-out, connector breakout) as short as possible (target < 2-3 mm
  for USB2, much less for multi-Gb links).

## 9. Length / timing matching

- Propagation ~ 6-7 ps/mm on outer layers (microstrip), ~7 ps/mm inner (stripline) on FR-4.
- USB 2.0 HS: intra-pair skew budget is ~100-150 ps at the spec level; design to a few mm
  (many layouts target <= 0.15 mm because it costs nothing); no inter-pair matching needed.
- Ethernet RGMII / DDR / parallel buses: match within the group to the controller datasheet's
  numbers (often +-0.5-5 mm depending on speed). Write them as `length_groups` in the plan.
- Add meanders on the **shorter** trace, near the source of the mismatch, with amplitude
  <= 3x track width spacing between meander segments to avoid self-coupling.

## 10. Geometry hygiene

- 45-degree corners or arcs. 90-degree corners are harmless at low speed but look
  unprofessional and should be avoided on fast/RF nets. **Acute angles (< 90 deg) must be
  removed** (acid traps, etching defects).
- No dangling stubs (DRC `track_dangling`). Stubs on fast nets = reflections.
- No T-junction stubs on clocks/fast nets - daisy-chain or point-to-point.
- Teardrops on small vias/pads improve yield (KiCad 9+ can add them; GUI Edit -> Add teardrops).
- Track entering a pad: from the pad's short edge, centred, no wider than the pad.
- Avoid routing between fine-pitch pads (0.5 mm pitch QFP/QFN) unless the clearance allows it.

## 11. Manufacturing (DFM) defaults

`apply_constraints.py --list-fabs` prints the presets. Design comfortably above them:

| Preset | min track/space | via pad/drill | annular | note |
|---|---|---|---|---|
| generic_conservative | 0.15/0.15 | 0.6/0.3 | 0.15 | works almost anywhere |
| jlcpcb_2layer | 0.127/0.127 | 0.6/0.3 | 0.15 | smaller drills cost extra |
| jlcpcb_4layer | 0.10/0.10 | 0.45/0.2 | 0.125 | check current site |
| pcbway_standard | 0.15/0.15 | 0.6/0.3 | 0.15 | |
| oshpark_2layer | 6 mil / 6 mil | 20/10 mil | 5 mil | |
| oshpark_4layer | 5 mil / 5 mil | 18/10 mil | 4 mil | |

Fab capability pages change and different sources quote different minimums for the same fab -
**confirm the current numbers on the fab's own capabilities page** before committing.

---

## Sources
- IPC-2221 trace current formula and k constants: standardclarity.com/standards/ipc-2221,
  salitronic.com/pcb-trace-width-calculator (also gives the IPC-2152 curve fit), atlaspcb.com tools.
- DC-DC hot loop, input cap and switch node: TI SLVAFJ3 (LM5177 layout), TI AN-1149 / SNVA021
  (switching supply layout), pcbsync.com SMPS layout articles, atlaspcb.com DC-DC layout.
- USB 2.0 layout: Microchip AN13.10 (USB3300), TI SPRAAR7 (high-speed interface layout:
  81-99 ohm, 50 mil skew, 50 mil to clocks, 90 mil from plane edge), Altium "USB on a 2-layer PCB".
- Crystal layout: ST AN2867 (oscillator design guide for STM32), Renesas DA14580 checklist.
- Via stitching lambda/20: Altium via stitching docs, atlaspcb.com RF via stitching, flux.ai guide.
- Fab capabilities: jlcpcb.com/capabilities/pcb-capabilities and fab blogs (values vary by tier).
