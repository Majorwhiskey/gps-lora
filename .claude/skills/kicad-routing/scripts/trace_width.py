#!/usr/bin/env python3
"""IPC-2221 trace width / via current calculator (pure Python, no KiCad needed).

IPC-2221:  I = k * dT^0.44 * A^0.725   (A in mil^2, I in A, dT in degC)
           k = 0.048 external layers, 0.024 internal layers
IPC-2221 is conservative for most cases; IPC-2152 (charts, plane-proximity aware)
usually allows narrower traces. Treat results as minimums and round UP.

Usage:
  trace_width.py --current 2 [--rise 10] [--oz 1] [--internal] [--margin 0.25]
  trace_width.py --current 1.5 --via-drill 0.3 [--plating-um 25]
  trace_width.py --width 0.5 --oz 1            # reverse: max current for a width
  trace_width.py --current 3 --length 40       # also prints resistance / drop
"""
from __future__ import annotations

import argparse
import json
import math

MIL_PER_MM = 39.3701
OZ_TO_MIL = 1.378          # 1 oz/ft^2 copper ~ 35 um ~ 1.378 mil
RHO_CU = 1.724e-8          # ohm*m at 20 C


def k_factor(internal: bool) -> float:
    return 0.024 if internal else 0.048


def area_for_current(current: float, rise: float, internal: bool) -> float:
    return (current / (k_factor(internal) * rise ** 0.44)) ** (1 / 0.725)


def current_for_area(area_mil2: float, rise: float, internal: bool) -> float:
    return k_factor(internal) * rise ** 0.44 * area_mil2 ** 0.725


def width_mm(current, rise=10.0, oz=1.0, internal=False, margin=0.0) -> float:
    area = area_for_current(current, rise, internal)
    w_mil = area / (oz * OZ_TO_MIL)
    return w_mil / MIL_PER_MM * (1 + margin)


def round_up(x: float, step: float = 0.05) -> float:
    return round(math.ceil(x / step - 1e-9) * step, 3)


def via_capacity(drill_mm: float, plating_um: float = 25.0, rise: float = 10.0) -> float:
    """Approximate a via barrel as a trace whose width = hole circumference."""
    circ_mil = math.pi * drill_mm * MIL_PER_MM
    t_mil = plating_um / 25.4
    return current_for_area(circ_mil * t_mil, rise, internal=False)


def resistance_ohm(width_mm_: float, length_mm: float, oz: float) -> float:
    t_m = oz * 35e-6
    return RHO_CU * (length_mm / 1000) / ((width_mm_ / 1000) * t_m)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--current", type=float, help="current in A")
    ap.add_argument("--width", type=float, help="reverse mode: track width in mm")
    ap.add_argument("--rise", type=float, default=10.0, help="allowed temperature rise degC (default 10)")
    ap.add_argument("--oz", type=float, default=1.0, help="copper weight oz/ft^2 (default 1; inner layers often 0.5)")
    ap.add_argument("--internal", action="store_true", help="inner layer (k=0.024)")
    ap.add_argument("--margin", type=float, default=0.25, help="extra width fraction (default 0.25)")
    ap.add_argument("--length", type=float, help="track length mm -> resistance and drop")
    ap.add_argument("--via-drill", type=float, help="via drill mm -> per-via current and vias needed")
    ap.add_argument("--plating-um", type=float, default=25.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    out = {"standard": "IPC-2221", "rise_C": a.rise, "copper_oz": a.oz,
           "layer": "internal" if a.internal else "external"}
    if a.width is not None:
        area = a.width * MIL_PER_MM * a.oz * OZ_TO_MIL
        out["width_mm"] = a.width
        out["max_current_A"] = round(current_for_area(area, a.rise, a.internal), 3)
    if a.current is not None:
        raw = width_mm(a.current, a.rise, a.oz, a.internal, 0.0)
        rec = round_up(max(raw * (1 + a.margin), 0.15))
        out.update({"current_A": a.current, "min_width_mm": round(raw, 3),
                    "recommended_width_mm": rec})
        if a.length:
            r = resistance_ohm(rec, a.length, a.oz)
            out["resistance_mOhm"] = round(r * 1000, 2)
            out["voltage_drop_mV"] = round(r * a.current * 1000, 1)
            out["power_loss_mW"] = round(r * a.current ** 2 * 1000, 1)
    if a.via_drill:
        cap = via_capacity(a.via_drill, a.plating_um, a.rise)
        out["via_drill_mm"] = a.via_drill
        out["via_capacity_A_approx"] = round(cap, 2)
        if a.current:
            # derate 50% - plating thickness varies and vias run hot in groups
            out["vias_needed_derated"] = max(1, math.ceil(a.current / (cap * 0.5)))
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for k, v in out.items():
            print(f"{k:24} {v}")
        print("note: IPC-2221 is conservative; check IPC-2152 for planes nearby. Round up, never down.")


if __name__ == "__main__":
    main()
