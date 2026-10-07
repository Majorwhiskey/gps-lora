# Circuit routing recipes

How to route the circuits that autorouters ruin. Each recipe:
**Prereq** (placement that must already be true - if not, stop and report),
**Route** (in order), **Check** (what to verify after).
Route these BEFORE the autorouter, then lock them (`route_critical.py lock`).

Use `route_critical.py pads --refs ...` to get exact pad coordinates, plan the geometry,
then `route_critical.py apply spec.json --lock` or `connect ... --lock`.

---

## A. Decoupling capacitors (every IC)

Prereq: each 100 nF (or smallest value) cap within ~1-3 mm of the power pin it serves, on the
same side as the IC where possible. Bulk caps (1-10 uF) nearby per rail.

Route:
1. Power pin -> cap pad: shortest possible track (0.3-0.5 mm wide), same layer, no via between pin and cap.
2. Cap GND pad -> its **own** GND via right at the pad (within ~0.5 mm), into the GND plane.
   Do not share one via between two caps. (`pad_vias` in the spec JSON.)
3. Supply reaches the cap first, then the pin (the cap sits between the source and the pin),
   or with a via from the power plane landing at the cap pad.
4. Smallest value cap closest to the pin.

Check: loop pin -> cap -> via -> plane -> IC GND pin is tiny. No signal track squeezed between cap and pin.

## B. Buck converter (the most important recipe)

Prereq (from datasheet layout section - read it): input ceramic cap directly across VIN and
PGND pins (< 2-3 mm), inductor next to SW pin, output caps next to inductor, feedback divider
near the FB pin. Same layer for the whole power stage.

Route:
1. **Hot loop**: CIN+ -> VIN pin and PGND pin -> CIN- with wide, short copper on the top layer.
   **No vias in this loop.** For buck the hot loop is input cap -> high-side switch -> low-side
   switch -> back to input cap ground; this is the highest di/dt path on the board.
2. **SW node**: SW pin -> inductor with a short, wide (current-rated) copper shape. Keep the
   area small - it is the noisiest node (high dV/dt, it is an E-field antenna) - but large
   enough to carry the current and heat.
3. Bootstrap cap: BST pin -> cap -> SW, tight loop next to the IC.
4. Output: inductor -> COUT -> load, wide. COUT ground returns to the same PGND area,
   but not through the input loop's path.
5. **Feedback**: tap VOUT at the output cap (remote sense point), route the FB trace thin and
   away from SW/inductor, divider resistors at the FB pin, divider ground to quiet AGND/GND
   near the IC. Never route FB under the inductor or alongside SW.
6. PGND/AGND: follow the datasheet. Typically one solid ground with PGND vias at the input
   and output caps and IC thermal pad; AGND pins tie to the plane at one point near the IC.
7. Thermal pad: via array to the GND plane.
8. Nothing else routed under the inductor or SW node on any layer (add a rule area keepout
   for tracks on other layers if needed; plan `keepaways` adds clearance around the SW net).

Check: trace the hot loop with your finger - it should be a few mm^2. `review_routing.py`
flags foreign tracks under `sensitive_refs` (put the inductor and regulator there).

## C. Boost converter

Same as buck but the hot loop is on the **output** side: switch -> diode/high-side FET ->
output cap -> ground back to switch. Put the output ceramic cap tight across that loop.
Input cap still close. SW node small, FB from the output cap.

## D. LDO

Input and output caps at the pins (datasheet stability depends on ESR + distance).
Thermal pad / tab copper area for dissipation (P = (Vin-Vout) * I). Feedback (adjustable) as in B.5.

## E. Crystal oscillator (MCU HSE/LSE)

Prereq: crystal within a few mm of OSC_IN/OSC_OUT; load caps adjacent to the crystal pads.

Route:
1. OSC_IN/OSC_OUT -> crystal -> load caps: short, direct, **symmetric**, on the top layer,
   no vias. 0.2-0.25 mm width is fine.
2. Load cap GND pads: short dedicated GND via each (or a local GND copper area under the
   crystal connected to the MCU's GND pin, per ST AN2867).
3. Surround the crystal + caps with GND copper (guard ring) stitched to the plane every few mm.
4. **No other signals under or near the crystal on any layer.** Keep clocks, SMPS, UART, USB
   away. The plane directly under it stays solid.
5. 32.768 kHz crystals are extremely high impedance - even more sensitive to coupling and leakage.

Check: `review_routing.py` treats Y*/X* as sensitive and lists any foreign track under them.

## F. USB 2.0 (Full / High speed) and USB-C

Prereq: connector -> ESD array -> (optional common mode choke) -> MCU/PHY in a straight line,
ESD close to the connector. Net names end in `+/-` or `_P/_N` (rename `DP/DM`).

Route:
1. Define a netclass with diff_pair_width/gap for **90 ohm differential** from the fab's
   calculator (2-layer: coplanar with ground pour; 4-layer: microstrip over L2 GND).
2. Route D+/D- as a coupled pair, same layer, constant gap, through the ESD pads in-line (no stubs).
3. Minimise vias (0-2 per pair, equal on both). Solid GND underneath the full length.
4. Length match within the pair (design to ~0.15 mm for HS; full-speed is far more tolerant).
5. Keep >= ~1.3 mm (50 mil) from clocks and other fast signals.
6. USB-C: CC1/CC2 are slow (5.1 k pull-downs near the connector). VBUS: current-rated width
   + TVS near the connector. Shield: per your EMC strategy (often RC to GND or direct).
7. Use KiCadRoutingTools `route_diff.py` or KiCad's interactive diff-pair router - never Freerouting.

Check: `review_routing.py` diff table (delta, via symmetry); DRC skew / uncoupled rules from the plan.

## G. Ethernet (10/100 PHY)

- MDI pairs (TX+/-, RX+/-): 100 ohm differential, PHY -> magnetics -> RJ45 short and direct,
  matched within each pair.
- Under the magnetics/RJ45 isolation area: no planes crossing the isolation (chassis vs
  circuit ground split as the PHY/magnetics app note shows); Bob-Smith termination per reference.
- RMII/RGMII: 50 ohm single-ended, short, length-matched per PHY datasheet, series resistors
  at the source. REF_CLK treated as a clock (routing-rules.md section 6 spacing).

## H. CAN / RS-485 / long-cable differential

Slow-ish but noise-exposed. Route H/L (A/B) as a pair to the transceiver, termination
resistor near the connector, TVS at the connector. Rename `CANH/CANL` to `CAN_P/CAN_N` only if
you want KiCad's diff router; not required electrically.

## I. I2C / SPI / UART / GPIO

Autorouter territory, but:
- SPI SCK and any clock > ~10 MHz: treat as a clock - short, minimal vias, away from analog.
- Series termination resistors (22-33 ohm) at the **driver** end.
- I2C pull-ups near the master; bus can be daisy-chained.

## J. SWD / JTAG / debug headers

Short as practical, keep SWCLK/TCK away from analog and crystal. Not critical otherwise.

## K. ADC inputs, references, op-amps, sensors

- Analog section placed in its own area; route analog traces only over solid GND in that area.
- VREF: decouple at the pin, route as a quiet net, never parallel to digital.
- Op-amp feedback networks tight at the pins (the inverting node is very sensitive).
- Thermistors/bridges/long sensor lines: route signal and its return together.

## L. Current sense (shunt resistors)

**Kelvin connections**: sense traces start from the inner edge of the shunt pads (not the
current path), route as a tight pair to the amplifier, filter caps at the amplifier.
The high-current path uses separate wide copper.

## M. MOSFET gate drive / motor drivers / half bridges

- Gate drive loop (driver -> gate resistor -> gate, source -> driver return) small; route the
  return alongside the gate trace.
- Half-bridge: same hot-loop thinking as the buck - decoupling caps across the bridge supply
  right at the high-side drain / low-side source.
- Motor currents: pours, multiple vias, IPC sizing for stall current.

## N. RF / antennas (2.4 GHz modules, chip antennas, SMA)

- 50 ohm trace (grounded coplanar on 2-layer) from the fab's calculator, as short as possible,
  matching network footprints in line with no stubs.
- Via fence along both sides of the RF trace at lambda/20 (~1-1.5 mm at 2.4-6 GHz).
- Antenna keepout: **no copper on any layer** in the antenna clearance area from the
  module/antenna datasheet - add a rule area that forbids tracks, vias and pours.
- Module RF pads on the board edge as the datasheet shows.

## O. Connectors and ESD/EMC

- ESD/TVS parts as close to the connector as possible; the line goes connector -> TVS -> rest.
  TVS ground via short and directly into the plane.
- Cable shields per strategy; keep fast signals away from connector pins that leave the board.

## P. Batteries, chargers, high current

- Size for peak (stall/charge) current; use pours on both layers with via arrays.
- Charger sense resistors with Kelvin routing (L).
- Fuse/protection first in the path from the connector.

## Q. Mains / isolation

- Hard creepage/clearance distances from the applicable safety standard; slots under
  optocouplers/isolators/transformers if required.
- Rule area keepout across the barrier for tracks, vias and pours on **all** layers.
- Never autoroute the primary side. Route it by hand / scripted spec and lock it.
