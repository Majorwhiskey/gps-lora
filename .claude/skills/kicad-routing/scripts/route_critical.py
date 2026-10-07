#!/usr/bin/env python3
"""Deterministic routing of critical nets (the ones you must NOT leave to an autorouter).

Sub-commands (KiCad Python):

  pads    board.kicad_pcb --refs U1,C5,Y1 [--net GND]
          -> JSON of pad positions, sizes, layers and nets so you can plan geometry.

  connect board.kicad_pcb "U1:5" "C3:1" --width 0.4 [--layer F.Cu] [--style 45|direct|hv|vh]
          [--net NAME] [--lock] [-o out.kicad_pcb]
          -> short pad-to-pad track with a 45-degree chamfered dog-leg (style 45, default).

  apply   board.kicad_pcb spec.json [--lock] [-o out.kicad_pcb]
          -> add explicit tracks / vias from a JSON spec:
             {"tracks":[{"net":"/XIN","layer":"F.Cu","width":0.2,"points":[[x,y],[x,y],...]}],
              "vias":[{"net":"GND","at":[x,y],"diameter":0.6,"drill":0.3}],
              "pad_vias":[{"pad":"C5:2","net":"GND","offset":[0,0.9],"diameter":0.6,"drill":0.3,
                           "width":0.4,"layer":"F.Cu"}]}
             pad_vias = drop a via next to a pad and stub to it (decoupling / ground pins).

  lock    board.kicad_pcb --nets "/USB_D+,/USB_D-" [--unlock]   -> lock all copper on nets
  clear   board.kicad_pcb --nets "/XIN,/XOUT"                   -> delete tracks/vias on nets

All coordinates are mm in KiCad board coordinates (Y grows downward).
This tool does NOT check clearances - always run drc_report.py afterwards.
Locked copper is protected from the autoroute step (autoroute_freerouting.py
snapshots and restores it).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (all_tracks, backup, find_net, import_pcbnew, layer_id, load_board,  # noqa: E402
                    mm, save_board, set_via_size, vec, write_json)


def get_pad(board, spec):
    ref, _, num = spec.partition(":")
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        sys.exit(f"ERROR: footprint {ref} not found")
    pads = [p for p in fp.Pads() if p.GetNumber() == num]
    if not pads:
        sys.exit(f"ERROR: pad {num} not found on {ref} (have {[p.GetNumber() for p in fp.Pads()]})")
    return pads[0]


def pad_layer_default(pcbnew, board, pad):
    ls = pad.GetLayerSet()
    if ls.Contains(pcbnew.F_Cu):
        return "F.Cu"
    if ls.Contains(pcbnew.B_Cu):
        return "B.Cu"
    return board.GetLayerName(ls.CuStack()[0])


def add_track(pcbnew, board, net, layer, width, p1, p2, lock):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(vec(pcbnew, *p1))
    t.SetEnd(vec(pcbnew, *p2))
    t.SetWidth(int(pcbnew.FromMM(width)))
    t.SetLayer(layer_id(pcbnew, board, layer))
    t.SetNet(net)
    if lock:
        t.SetLocked(True)
    board.Add(t)
    return t


def add_via(pcbnew, board, net, at, diameter, drill, lock):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(vec(pcbnew, *at))
    try:
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
    except Exception:
        pass
    try:
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    except Exception:
        pass
    set_via_size(pcbnew, v, int(pcbnew.FromMM(diameter)), int(pcbnew.FromMM(drill)))
    v.SetNet(net)
    if lock:
        v.SetLocked(True)
    board.Add(v)
    return v


def dogleg(p1, p2, style):
    """Return polyline points from p1 to p2."""
    (x1, y1), (x2, y2) = p1, p2
    dx, dy = x2 - x1, y2 - y1
    if style == "direct" or abs(dx) < 1e-6 or abs(dy) < 1e-6:
        return [p1, p2]
    if style == "hv":
        return [p1, (x2, y1), p2]
    if style == "vh":
        return [p1, (x1, y2), p2]
    # 45-degree: diagonal covers the shorter axis, straight segment covers the rest
    d = min(abs(dx), abs(dy))
    sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    if abs(dx) >= abs(dy):
        mid = (x2 - sx * d, y1)          # straight along X, then 45 into the target
    else:
        mid = (x1, y2 - sy * d)
    return [p1, mid, p2]


# ---------------------------------------------------------------- commands
def cmd_pads(pcbnew, board, a):
    out = []
    refs = [r.strip() for r in a.refs.split(",")] if a.refs else None
    for fp in board.GetFootprints():
        if refs and fp.GetReference() not in refs:
            continue
        for p in fp.Pads():
            if a.net and p.GetNetname() != a.net:
                continue
            pos, size = p.GetPosition(), p.GetSize()
            out.append({"pad": f"{fp.GetReference()}:{p.GetNumber()}", "net": p.GetNetname(),
                        "pos": [mm(pcbnew, pos.x), mm(pcbnew, pos.y)],
                        "size": [mm(pcbnew, size.x), mm(pcbnew, size.y)],
                        "rot": round(p.GetOrientationDegrees(), 1),
                        "layer": pad_layer_default(pcbnew, board, p),
                        "smd": not p.HasHole() if hasattr(p, "HasHole") else None})
    print(write_json(out, None))


def cmd_connect(pcbnew, board, a):
    pa, pb = get_pad(board, a.pad_a), get_pad(board, a.pad_b)
    netname = a.net or pa.GetNetname()
    if pb.GetNetname() != netname or pa.GetNetname() != netname:
        sys.exit(f"ERROR: pads are on different nets ({pa.GetNetname()} vs {pb.GetNetname()})")
    net = find_net(board, netname)
    layer = a.layer or pad_layer_default(pcbnew, board, pa)
    p1 = (mm(pcbnew, pa.GetPosition().x), mm(pcbnew, pa.GetPosition().y))
    p2 = (mm(pcbnew, pb.GetPosition().x), mm(pcbnew, pb.GetPosition().y))
    pts = dogleg(p1, p2, a.style)
    for s, e in zip(pts, pts[1:]):
        add_track(pcbnew, board, net, layer, a.width, s, e, a.lock)
    print(f"connected {a.pad_a} -> {a.pad_b} on {netname} via {len(pts) - 1} segment(s) on {layer}")


def cmd_apply(pcbnew, board, a):
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    n_t = n_v = 0
    for t in spec.get("tracks", []):
        net = find_net(board, t["net"])
        pts = t["points"]
        for s, e in zip(pts, pts[1:]):
            add_track(pcbnew, board, net, t.get("layer", "F.Cu"), t["width"], s, e, a.lock)
            n_t += 1
    for v in spec.get("vias", []):
        add_via(pcbnew, board, find_net(board, v["net"]), v["at"], v.get("diameter", 0.6),
                v.get("drill", 0.3), a.lock)
        n_v += 1
    for pv in spec.get("pad_vias", []):
        pad = get_pad(board, pv["pad"])
        net = find_net(board, pv.get("net") or pad.GetNetname())
        px, py = mm(pcbnew, pad.GetPosition().x), mm(pcbnew, pad.GetPosition().y)
        ox, oy = pv.get("offset", [0, 0])
        at = (px + ox, py + oy)
        add_via(pcbnew, board, net, at, pv.get("diameter", 0.6), pv.get("drill", 0.3), a.lock)
        if ox or oy:
            add_track(pcbnew, board, net, pv.get("layer") or pad_layer_default(pcbnew, board, pad),
                      pv.get("width", 0.4), (px, py), at, a.lock)
            n_t += 1
        n_v += 1
    print(f"added {n_t} track segment(s), {n_v} via(s){' (locked)' if a.lock else ''}")


def nets_arg(s):
    return [n.strip() for n in s.split(",") if n.strip()]


def cmd_lock(pcbnew, board, a):
    nets, n = set(nets_arg(a.nets)), 0
    for t in all_tracks(board):
        if t.GetNetname() in nets:
            t.SetLocked(not a.unlock)
            n += 1
    print(f"{'un' if a.unlock else ''}locked {n} item(s) on {sorted(nets)}")


def cmd_clear(pcbnew, board, a):
    nets = set(nets_arg(a.nets))
    victims = [t for t in all_tracks(board) if t.GetNetname() in nets]
    for t in victims:
        board.Remove(t)
    print(f"removed {len(victims)} item(s) on {sorted(nets)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("pads"); s.add_argument("board"); s.add_argument("--refs"); s.add_argument("--net")
    s = sub.add_parser("connect"); s.add_argument("board"); s.add_argument("pad_a"); s.add_argument("pad_b")
    s.add_argument("--width", type=float, required=True); s.add_argument("--layer"); s.add_argument("--net")
    s.add_argument("--style", choices=["45", "direct", "hv", "vh"], default="45")
    s = sub.add_parser("apply"); s.add_argument("board"); s.add_argument("spec")
    s = sub.add_parser("lock"); s.add_argument("board"); s.add_argument("--nets", required=True)
    s.add_argument("--unlock", action="store_true")
    s = sub.add_parser("clear"); s.add_argument("board"); s.add_argument("--nets", required=True)
    for name in ("connect", "apply", "lock", "clear"):
        p = sub.choices[name]
        p.add_argument("-o", "--output", help="save to this file instead of overwriting the input")
        if name in ("connect", "apply"):
            p.add_argument("--lock", action="store_true", help="lock the new copper (recommended)")

    a = ap.parse_args()
    pcbnew = import_pcbnew()
    board = load_board(pcbnew, a.board)
    if a.cmd == "pads":
        cmd_pads(pcbnew, board, a)
        return
    out = a.output or a.board
    if out == a.board:
        print(f"backup -> {backup(a.board, 'critical-' + a.cmd)}")
    {"connect": cmd_connect, "apply": cmd_apply, "lock": cmd_lock, "clear": cmd_clear}[a.cmd](pcbnew, board, a)
    save_board(pcbnew, board, out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
