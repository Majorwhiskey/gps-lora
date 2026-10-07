#!/usr/bin/env python3
"""Board inventory + net classification + placement pre-flight.

Produces a JSON report the agent uses to write routing_plan.json:
  * board: outline size, copper layers, stackup thickness if present
  * footprints: ref, value, footprint, side, position, pad count
  * nets: name, pad count, connected refs, existing routed length, guessed role
  * diff_pairs: detected P/N pairs + whether KiCad will recognise them
  * preflight: placement problems a router cannot fix (decoupling caps far
    from their IC, crystals far from the MCU, unplaced parts off-board)
  * netclasses already defined in the project

Usage (KiCad Python):
  analyze_board.py board.kicad_pcb [-o analysis.json] [--decap-max-mm 3] [--xtal-max-mm 5]
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (all_tracks, copper_layer_names, import_pcbnew, is_via, kicad_version,  # noqa: E402
                    load_board, mm, write_json)

# ---------------------------------------------------------------- name heuristics
GROUND_RE = re.compile(r"^/?(.*/)?(A|D|P|S|CHASSIS_|EARTH_)?(GND|VSS|GROUND|0V|EARTH|CHASSIS)[A-Z0-9_]*$|GNDA|GNDD|GNDPWR", re.I)
POWER_RE = re.compile(
    r"^/?(.*/)?(\+|-)?(\d+V\d*|\d+V|V\d+V\d*|\d+V\d+|VCC|VDD|VBUS|VIN|VBAT|VSYS|VOUT|VMOT|VM|VCORE|VCCIO|VDDIO|AVCC|AVDD|DVDD|DVCC|PVIN|VPP|VLED|PWR|\+?VREG)[A-Z0-9_]*$",
    re.I)
SWITCH_RE = re.compile(r"(^|[/_])(SW|LX|PH|SW_NODE|SWNODE|SWITCH)(\d*)$", re.I)
BOOT_RE = re.compile(r"(^|[/_])(BST|BOOT|CBOOT|BOOTSTRAP)\d*$", re.I)
FB_RE = re.compile(r"(^|[/_])(V?FB|FEEDBACK|SENSE[PN+-]?|ISENSE|ISNS|CS[PN+-]?|COMP|ILIM|RT|SS)\d*$", re.I)
XTAL_RE = re.compile(r"(XTAL|XIN|XOUT|XI$|XO$|OSC_?(IN|OUT)|OSC\d|HSE|LSE|X32|32K|CRYSTAL)", re.I)
CLOCK_RE = re.compile(r"(CLK|SCLK|MCLK|BCLK|LRCLK|REFCLK|CLKOUT|SCK)", re.I)
USB_RE = re.compile(r"(USB|^/?D[+-]$|[/_]D[PMN+-]$|DP$|DM$|CC[12]$)", re.I)
HS_RE = re.compile(r"(ETH|RGMII|RMII|MDI|TXP|TXN|RXP|RXN|TX[+-]|RX[+-]|SDIO|SD_D|SDMMC|EMMC|QSPI|OSPI|HDMI|LVDS|MIPI|CSI|DSI|PCIE|SATA|DDR|DQ\d|DQS|DQM|^/?A\d+$|BA\d|RAS|CAS|SDRAM)", re.I)
ANALOG_RE = re.compile(r"(AIN|ADC|VREF|REF$|AN\d|ANALOG|MIC|AUDIO|HP_|LINE|THERM|NTC|SENSE|BRIDGE|STRAIN)", re.I)
RF_RE = re.compile(r"(RF|ANT|ANTENNA|LNA|PA_|BALUN|SMA)", re.I)
CAN_RS485_RE = re.compile(r"(CANH|CANL|CAN_H|CAN_L|RS485|485_[AB]|^/?[AB]$)", re.I)
I2C_SPI_RE = re.compile(r"(SDA|SCL|MOSI|MISO|CIPO|COPI|SPI|I2C|UART|TXD|RXD|SWDIO|SWCLK|JTAG|TDI|TDO|TMS|TCK)", re.I)

DIFF_SUFFIXES = [  # (p, n, recognised_by_kicad)
    ("_P", "_N", True), ("+", "-", True), ("P", "N", True),
    ("_DP", "_DM", False), ("DP", "DM", False), ("_H", "_L", False), ("H", "L", False),
    ("_POS", "_NEG", False),
]


def classify(name: str) -> str:
    base = name.split("/")[-1]
    if base.lower().startswith("unconnected-") or base.lower().startswith("net-("):
        generic = True
    else:
        generic = False
    if GROUND_RE.search(base):
        return "ground"
    if SWITCH_RE.search(base):
        return "smps_switch_node"
    if BOOT_RE.search(base):
        return "smps_boot"
    if POWER_RE.search(base):
        return "power"
    if XTAL_RE.search(base):
        return "crystal"
    if RF_RE.search(base):
        return "rf"
    if USB_RE.search(base):
        return "usb"
    if HS_RE.search(base):
        return "high_speed"
    if CAN_RS485_RE.search(base):
        return "diff_low_speed"
    if CLOCK_RE.search(base):
        return "clock"
    if FB_RE.search(base):
        return "feedback_sense"
    if ANALOG_RE.search(base):
        return "analog"
    if I2C_SPI_RE.search(base):
        return "digital_bus"
    return "generic_unnamed" if generic else "signal"


def detect_diff_pairs(net_names):
    names = set(net_names)
    pairs, used = [], set()
    for n in sorted(names):
        for p_suf, n_suf, recognised in DIFF_SUFFIXES:
            if n.endswith(p_suf) and n not in used:
                base = n[: -len(p_suf)]
                partner = base + n_suf
                if partner in names and partner not in used and base:
                    pairs.append({"base": base, "p": n, "n": partner,
                                  "kicad_recognises": recognised})
                    used.update([n, partner])
                    break
    return pairs


# ---------------------------------------------------------------- main analysis
def analyze(path, decap_max, xtal_max):
    pcbnew = import_pcbnew()
    board = load_board(pcbnew, path)
    try:
        board.BuildConnectivity()
    except Exception:
        pass

    bbox = board.GetBoardEdgesBoundingBox()
    report = {
        "file": str(Path(path).resolve()),
        "kicad_version": kicad_version(pcbnew),
        "board": {
            "width_mm": mm(pcbnew, bbox.GetWidth()),
            "height_mm": mm(pcbnew, bbox.GetHeight()),
            "origin_mm": [mm(pcbnew, bbox.GetX()), mm(pcbnew, bbox.GetY())],
            "copper_layers": copper_layer_names(pcbnew, board),
            "thickness_mm": mm(pcbnew, board.GetDesignSettings().GetBoardThickness()),
        },
    }

    # -------- footprints & pads
    fps, net_pads, net_refs = [], defaultdict(list), defaultdict(set)
    off_board = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        side = "bottom" if fp.IsFlipped() else "top"
        fps.append({"ref": ref, "value": fp.GetValue(),
                    "footprint": str(fp.GetFPID().GetLibItemName()),
                    "side": side, "pos_mm": [mm(pcbnew, pos.x), mm(pcbnew, pos.y)],
                    "rot_deg": round(fp.GetOrientationDegrees(), 1),
                    "locked": fp.IsLocked(), "pads": len(fp.Pads())})
        if not bbox.Contains(pos):
            off_board.append(ref)
        for pad in fp.Pads():
            nn = pad.GetNetname()
            if nn:
                p = pad.GetPosition()
                net_pads[nn].append({"ref": ref, "pad": pad.GetNumber(),
                                     "pos": (mm(pcbnew, p.x), mm(pcbnew, p.y))})
                net_refs[nn].add(ref)
    report["footprints"] = fps
    report["counts"] = {"footprints": len(fps), "nets": len(net_pads)}

    # -------- existing copper
    routed_len, via_count = defaultdict(float), defaultdict(int)
    n_tracks = n_vias = 0
    for t in all_tracks(board):
        nn = t.GetNetname()
        if is_via(pcbnew, t):
            via_count[nn] += 1
            n_vias += 1
        else:
            routed_len[nn] += mm(pcbnew, t.GetLength())
            n_tracks += 1
    report["existing_copper"] = {"tracks": n_tracks, "vias": n_vias,
                                 "zones": [{"net": z.GetNetname(),
                                            "layers": [board.GetLayerName(l) for l in z.GetLayerSet().Seq()]}
                                           for z in board.Zones()]}
    try:
        report["existing_copper"]["unrouted_connections"] = board.GetConnectivity().GetUnconnectedCount(False)
    except Exception:
        pass

    # -------- nets
    nets = []
    roles = defaultdict(list)
    for nn, pads in sorted(net_pads.items()):
        role = classify(nn)
        if len(pads) < 2:
            role_note = "single-pad (nothing to route)"
        else:
            role_note = ""
        try:
            ncname = board.FindNet(nn).GetNetClassName()
        except Exception:
            ncname = None
        nets.append({"name": nn, "role": role, "pads": len(pads), "netclass": ncname,
                     "refs": sorted(net_refs[nn])[:12],
                     "routed_mm": round(routed_len[nn], 2), "vias": via_count[nn],
                     **({"note": role_note} if role_note else {})})
        roles[role].append(nn)
    report["nets"] = nets
    report["nets_by_role"] = {k: v for k, v in sorted(roles.items())}

    # -------- diff pairs
    pairs = detect_diff_pairs(net_pads.keys())
    report["diff_pairs"] = pairs
    bad = [p for p in pairs if not p["kicad_recognises"]]
    if bad:
        report.setdefault("warnings", []).append(
            "Diff pairs whose names KiCad will NOT treat as pairs (needs _P/_N, +/-, or P/N suffix): "
            + ", ".join(f"{p['p']}/{p['n']}" for p in bad)
            + ". Rename in the schematic (e.g. USB_D+/USB_D-) and update PCB from schematic.")

    # -------- existing netclasses
    # (per-net class names are in nets[].netclass; definitions live in the .kicad_pro)
    pro = Path(path).with_suffix(".kicad_pro")
    try:
        import json as _json
        ns = _json.loads(pro.read_text(encoding="utf-8")).get("net_settings", {})
        report["netclasses"] = {c.get("name"): {k: c.get(k) for k in ("track_width", "clearance", "via_diameter",
                                                                     "via_drill", "diff_pair_width", "diff_pair_gap")}
                                for c in ns.get("classes", [])}
        report["netclass_patterns"] = ns.get("netclass_patterns", [])
    except Exception as e:  # not fatal
        report["netclasses"] = {"note": f"could not read {pro.name}: {e}"}

    # -------- placement pre-flight
    pre = []
    ref_type = lambda r: re.match(r"[A-Z]+", r).group(0) if re.match(r"[A-Z]+", r) else ""

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # Decoupling caps: C with one pad on ground and one on a power net -> nearest IC pin of that rail
    for f in fps:
        if ref_type(f["ref"]) != "C" or f["pads"] != 2:
            continue
        fp = board.FindFootprintByReference(f["ref"])
        pnets = [p.GetNetname() for p in fp.Pads()]
        if len(pnets) != 2:
            continue
        gnd = [n for n in pnets if classify(n) == "ground"]
        pwr = [n for n in pnets if classify(n) == "power"]
        if not (gnd and pwr):
            continue
        rail = pwr[0]
        cpos = [p.GetPosition() for p in fp.Pads() if p.GetNetname() == rail][0]
        cpos = (mm(pcbnew, cpos.x), mm(pcbnew, cpos.y))
        ic_pins = [p for p in net_pads[rail] if ref_type(p["ref"]) in ("U", "IC")]
        if not ic_pins:
            continue
        nearest = min(ic_pins, key=lambda p: dist(p["pos"], cpos))
        d = dist(nearest["pos"], cpos)
        if d > decap_max:
            pre.append({"severity": "warning", "type": "decap_far",
                        "msg": f"{f['ref']} ({f['value']}) on {rail} is {d:.1f} mm from nearest "
                               f"{nearest['ref']} pin {nearest['pad']} (target <= {decap_max} mm)",
                        "ref": f["ref"], "distance_mm": round(d, 2)})

    # Crystals: Y/X refs -> distance to the IC they connect to
    for f in fps:
        if ref_type(f["ref"]) not in ("Y", "X", "XTAL"):
            continue
        fp = board.FindFootprintByReference(f["ref"])
        for pad in fp.Pads():
            nn = pad.GetNetname()
            if not nn or classify(nn) == "ground":
                continue
            p = pad.GetPosition()
            pp = (mm(pcbnew, p.x), mm(pcbnew, p.y))
            ics = [q for q in net_pads[nn] if ref_type(q["ref"]) in ("U", "IC")]
            for q in ics:
                d = dist(q["pos"], pp)
                if d > xtal_max:
                    pre.append({"severity": "warning", "type": "crystal_far",
                                "msg": f"{f['ref']} pad {pad.GetNumber()} ({nn}) is {d:.1f} mm from "
                                       f"{q['ref']} (target <= {xtal_max} mm)",
                                "ref": f["ref"], "distance_mm": round(d, 2)})

    for r in off_board:
        pre.append({"severity": "error", "type": "off_board",
                    "msg": f"{r} is outside the board outline - place it before routing", "ref": r})
    if not report["board"]["width_mm"]:
        pre.append({"severity": "error", "type": "no_outline", "msg": "No Edge.Cuts outline found"})

    # Rough density estimate: pads per cm^2
    area_cm2 = max(report["board"]["width_mm"] * report["board"]["height_mm"] / 100.0, 0.01)
    total_pads = sum(f["pads"] for f in fps)
    report["density"] = {"pads_per_cm2": round(total_pads / area_cm2, 2),
                         "hint": ("dense - expect 4+ layers" if total_pads / area_cm2 > 8 else
                                  "moderate" if total_pads / area_cm2 > 4 else "sparse")}
    report["preflight"] = pre
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("-o", "--output", help="write JSON here (default: print)")
    ap.add_argument("--decap-max-mm", type=float, default=3.0)
    ap.add_argument("--xtal-max-mm", type=float, default=5.0)
    ap.add_argument("--summary", action="store_true", help="print a short human summary too")
    a = ap.parse_args()
    rep = analyze(a.board, a.decap_max_mm, a.xtal_max_mm)
    text = write_json(rep, a.output)
    if not a.output:
        print(text)
    if a.summary or a.output:
        b = rep["board"]
        print(f"Board {b['width_mm']} x {b['height_mm']} mm, layers {b['copper_layers']}, "
              f"{rep['counts']['footprints']} footprints, {rep['counts']['nets']} nets, density {rep['density']}")
        for role, names in rep["nets_by_role"].items():
            print(f"  {role:18} {len(names):4}  e.g. {', '.join(names[:4])}")
        for p in rep["diff_pairs"]:
            print(f"  diff pair: {p['p']} / {p['n']}{'' if p['kicad_recognises'] else '  (RENAME!)'}")
        for w in rep.get("warnings", []):
            print("  WARNING:", w)
        for p in rep["preflight"]:
            print(f"  PREFLIGHT {p['severity']}: {p['msg']}")


if __name__ == "__main__":
    main()
