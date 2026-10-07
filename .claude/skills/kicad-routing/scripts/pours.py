#!/usr/bin/env python3
"""Copper pours and ground stitching vias.

  pour   board.kicad_pcb --net GND --layers F.Cu,B.Cu [--clearance 0.3] [--min-width 0.25]
         [--thermal-gap 0.5] [--spoke 0.5] [--connection thermal|solid] [--priority 0] [-o out]
         -> one zone per layer covering the board (fill is clipped to Edge.Cuts automatically)

  stitch board.kicad_pcb --net GND --pitch 5 [--layers F.Cu,B.Cu] [--via 0.6/0.3]
         [--clearance 0.25] [--edge-pitch 3 --edge-inset 1.0] [--keep-out-courtyards] [--max 2000] [-o out]
         -> grid of through vias, placed ONLY where the filled GND copper fully covers the via
            (plus clearance) on every listed layer, so they can never short another net.
            --edge-pitch adds a perimeter fence. Pitch rule of thumb: <= lambda/20 at the highest
            frequency of concern (references/routing-rules.md section 7).

  fill   board.kicad_pcb [-o out]   -> refill all zones and save

Run after routing (pours need the tracks in place to flow around them).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (all_tracks, backup, find_net, import_pcbnew, is_via, layer_id, load_board,  # noqa: E402
                    save_board, set_via_size)


def try_call(obj, name, *args):
    fn = getattr(obj, name, None)
    if fn is None:
        return False
    try:
        fn(*args)
        return True
    except Exception:
        return False


def fill(pcbnew, board):
    zones = board.Zones()
    if len(list(zones)):
        pcbnew.ZONE_FILLER(board).Fill(zones)


def cmd_pour(pcbnew, board, a):
    net = find_net(board, a.net)
    bb = board.GetBoardEdgesBoundingBox()
    if bb.GetWidth() == 0:
        sys.exit("ERROR: no Edge.Cuts outline")
    m = pcbnew.FromMM(1.0)
    corners = [(bb.GetLeft() - m, bb.GetTop() - m), (bb.GetRight() + m, bb.GetTop() - m),
               (bb.GetRight() + m, bb.GetBottom() + m), (bb.GetLeft() - m, bb.GetBottom() + m)]
    made = 0
    for lname in [s.strip() for s in a.layers.split(",")]:
        lid = layer_id(pcbnew, board, lname)
        # skip if an equivalent zone exists
        if any(z.GetNetname() == net.GetNetname() and z.IsOnLayer(lid) for z in board.Zones()):
            print(f"zone for {net.GetNetname()} already on {lname} - skipped")
            continue
        z = pcbnew.ZONE(board)
        z.SetLayer(lid)
        z.SetNetCode(net.GetNetCode())
        for x, y in corners:
            z.AppendCorner(pcbnew.VECTOR2I(int(x), int(y)), -1)
        try_call(z, "SetLocalClearance", int(pcbnew.FromMM(a.clearance)))
        try_call(z, "SetMinThickness", int(pcbnew.FromMM(a.min_width)))
        try_call(z, "SetThermalReliefGap", int(pcbnew.FromMM(a.thermal_gap)))
        try_call(z, "SetThermalReliefSpokeWidth", int(pcbnew.FromMM(a.spoke)))
        conn = pcbnew.ZONE_CONNECTION_FULL if a.connection == "solid" else pcbnew.ZONE_CONNECTION_THERMAL
        try_call(z, "SetPadConnection", conn)
        if not try_call(z, "SetAssignedPriority", a.priority):
            try_call(z, "SetPriority", a.priority)
        if hasattr(pcbnew, "ISLAND_REMOVAL_MODE_ALWAYS"):
            try_call(z, "SetIslandRemovalMode", pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        try_call(z, "SetZoneName", f"{net.GetNetname()}_{lname}")
        board.Add(z)
        made += 1
    fill(pcbnew, board)
    print(f"added {made} zone(s) for {net.GetNetname()} and filled")


def courtyard_boxes(pcbnew, board, margin):
    boxes = []
    for fp in board.GetFootprints():
        try:
            bb = fp.GetBoundingBox(False, False)
        except TypeError:
            bb = fp.GetBoundingBox()
        boxes.append((bb.GetLeft() - margin, bb.GetTop() - margin, bb.GetRight() + margin, bb.GetBottom() + margin))
    return boxes


def cmd_stitch(pcbnew, board, a):
    net = find_net(board, a.net)
    code = net.GetNetCode()
    dia_mm, drill_mm = (float(v) for v in a.via.split("/"))
    dia, drill = int(pcbnew.FromMM(dia_mm)), int(pcbnew.FromMM(drill_mm))
    clr = int(pcbnew.FromMM(a.clearance))
    fill(pcbnew, board)

    layers = [layer_id(pcbnew, board, s.strip()) for s in (a.layers or "F.Cu,B.Cu").split(",")]
    zones_by_layer = {}
    for lid in layers:
        zs = [z for z in board.Zones() if z.GetNetCode() == code and z.IsOnLayer(lid) and z.IsFilled()]
        if not zs:
            sys.exit(f"ERROR: no filled {net.GetNetname()} zone on {board.GetLayerName(lid)} - run 'pour' first")
        zones_by_layer[lid] = zs

    r = dia // 2 + clr
    ring = [(0, 0)] + [(int(r * math.cos(t)), int(r * math.sin(t))) for t in [k * math.pi / 4 for k in range(8)]]

    def covered(x, y):
        for lid, zs in zones_by_layer.items():
            for dx, dy in ring:
                p = pcbnew.VECTOR2I(x + dx, y + dy)
                if not any(z.HitTestFilledArea(lid, p, 0) for z in zs):
                    return False
        return True

    # existing holes (vias + drilled pads) for hole-to-hole spacing
    min_hole_gap = int(pcbnew.FromMM(a.hole_gap))
    holes = []
    for t in all_tracks(board):
        if is_via(pcbnew, t):
            holes.append((t.GetPosition().x, t.GetPosition().y, t.GetDrillValue()))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            ds = p.GetDrillSize()
            if ds.x > 0:
                holes.append((p.GetPosition().x, p.GetPosition().y, max(ds.x, ds.y)))

    def hole_ok(x, y):
        for hx, hy, hd in holes:
            if math.hypot(hx - x, hy - y) < (hd + drill) / 2 + min_hole_gap:
                return False
        return True

    boxes = courtyard_boxes(pcbnew, board, r) if a.keep_out_courtyards else []

    def box_ok(x, y):
        return not any(l <= x <= rr and t <= y <= b for l, t, rr, b in boxes)

    bb = board.GetBoardEdgesBoundingBox()
    cands = []
    pitch = int(pcbnew.FromMM(a.pitch)) if a.pitch else 0
    if pitch:
        y = bb.GetTop() + pitch // 2
        row = 0
        while y < bb.GetBottom():
            x = bb.GetLeft() + pitch // 2 + (pitch // 2 if (a.stagger and row % 2) else 0)
            while x < bb.GetRight():
                cands.append((x, y))
                x += pitch
            y += pitch
            row += 1
    if a.edge_pitch:
        ep, inset = int(pcbnew.FromMM(a.edge_pitch)), int(pcbnew.FromMM(a.edge_inset))
        l, t, rr, b = bb.GetLeft() + inset, bb.GetTop() + inset, bb.GetRight() - inset, bb.GetBottom() - inset
        x = l
        while x <= rr:
            cands += [(x, t), (x, b)]
            x += ep
        y = t + ep
        while y < b:
            cands += [(l, y), (rr, y)]
            y += ep

    placed = 0
    for x, y in cands:
        if placed >= a.max:
            break
        if not box_ok(x, y) or not hole_ok(x, y) or not covered(x, y):
            continue
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
        try:
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        except Exception:
            pass
        set_via_size(pcbnew, v, dia, drill)
        v.SetNetCode(code)
        board.Add(v)
        holes.append((x, y, drill))
        placed += 1
    fill(pcbnew, board)
    print(f"placed {placed} stitching via(s) on {net.GetNetname()} from {len(cands)} candidates "
          f"({dia_mm}/{drill_mm} mm)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pour"); p.add_argument("board"); p.add_argument("--net", required=True)
    p.add_argument("--layers", required=True); p.add_argument("--clearance", type=float, default=0.3)
    p.add_argument("--min-width", type=float, default=0.25); p.add_argument("--thermal-gap", type=float, default=0.5)
    p.add_argument("--spoke", type=float, default=0.5)
    p.add_argument("--connection", choices=["thermal", "solid"], default="thermal")
    p.add_argument("--priority", type=int, default=0)
    s = sub.add_parser("stitch"); s.add_argument("board"); s.add_argument("--net", required=True)
    s.add_argument("--pitch", type=float, default=5.0, help="grid pitch mm (0 = no grid)")
    s.add_argument("--stagger", action="store_true", help="offset alternate rows by half a pitch")
    s.add_argument("--layers", help="layers where the net's pour must cover the via (default F.Cu,B.Cu)")
    s.add_argument("--via", default="0.6/0.3", help="diameter/drill mm")
    s.add_argument("--clearance", type=float, default=0.25, help="extra copper margin around via")
    s.add_argument("--hole-gap", type=float, default=0.5, help="min hole-to-hole edge gap mm")
    s.add_argument("--edge-pitch", type=float, help="add perimeter fence with this pitch")
    s.add_argument("--edge-inset", type=float, default=1.0)
    s.add_argument("--keep-out-courtyards", action="store_true", help="never place under footprints")
    s.add_argument("--max", type=int, default=2000)
    f = sub.add_parser("fill"); f.add_argument("board")
    for sp in (p, s, f):
        sp.add_argument("-o", "--output")
    a = ap.parse_args()

    pcbnew = import_pcbnew()
    board = load_board(pcbnew, a.board)
    out = a.output or a.board
    if out == a.board:
        print(f"backup -> {backup(a.board, a.cmd)}")
    {"pour": cmd_pour, "stitch": cmd_stitch, "fill": lambda pc, b, _: (fill(pc, b), print("filled"))}[a.cmd](pcbnew, board, a)
    save_board(pcbnew, board, out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
