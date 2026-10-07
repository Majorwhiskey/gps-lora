#!/usr/bin/env python3
"""Generate a small synthetic test board (no footprint libraries needed) for smoke-testing
the skill: MCU-like SOIC, crystal + load caps, decoupling caps, a USB pair, an I2C bus,
a buck switch node, and a 4-pin header. 2 layers, 40 x 30 mm.

Usage (KiCad Python):  make_test_board.py out_dir/test_board.kicad_pcb
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from common import import_pcbnew  # noqa: E402

pcbnew = import_pcbnew()
MM = pcbnew.FromMM


def V(x, y):
    return pcbnew.VECTOR2I(int(MM(x)), int(MM(y)))


def add_line(board, a, b):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(V(*a)); s.SetEnd(V(*b))
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(int(MM(0.1)))
    board.Add(s)


def net(board, name):
    n = board.FindNet(name)
    if n is None:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
    return n


def footprint(board, ref, value, at, pads, smd=True, rot=0):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref); fp.SetValue(value)
    fp.SetPosition(V(0, 0))  # build at origin, move at the end so pad offsets are footprint-relative
    for num, (dx, dy), (w, h), netname in pads:
        p = pcbnew.PAD(fp)
        p.SetNumber(str(num))
        p.SetShape(pcbnew.PAD_SHAPE_RECT if smd else pcbnew.PAD_SHAPE_CIRCLE)
        p.SetSize(pcbnew.VECTOR2I(int(MM(w)), int(MM(h))))
        if smd:
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.SMDMask())
        else:
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            p.SetLayerSet(pcbnew.PAD.PTHMask())
            p.SetDrillSize(pcbnew.VECTOR2I(int(MM(1.0)), int(MM(1.0))))
        p.SetPosition(V(dx, dy))
        if hasattr(p, "SetPos0"):            # KiCad 7 keeps a separate footprint-relative position
            p.SetPos0(V(dx, dy))
        if netname:
            p.SetNet(net(board, netname))
        fp.Add(p)
    # courtyard rectangle
    xs = [d[0] for _, d, _, _ in pads]; ys = [d[1] for _, d, _, _ in pads]
    l, r, t, b = min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1
    for a, c in (((l, t), (r, t)), ((r, t), (r, b)), ((r, b), (l, b)), ((l, b), (l, t))):
        s = pcbnew.FP_SHAPE(fp) if hasattr(pcbnew, "FP_SHAPE") else pcbnew.PCB_SHAPE(fp)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*a)); s.SetEnd(V(*c))
        if hasattr(s, "SetStart0"):
            s.SetStart0(V(*a)); s.SetEnd0(V(*c))
        s.SetLayer(pcbnew.F_CrtYd); s.SetWidth(int(MM(0.05)))
        fp.Add(s)
    fp.SetPosition(V(*at))
    board.Add(fp)
    return fp


def two_pad(board, ref, val, at, n1, n2, horizontal=True):
    off = 0.8
    pads = [(1, (-off, 0) if horizontal else (0, -off), (0.9, 0.95), n1),
            (2, (off, 0) if horizontal else (0, off), (0.9, 0.95), n2)]
    return footprint(board, ref, val, at, pads)


def main(out):
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    board = pcbnew.CreateEmptyBoard() if hasattr(pcbnew, "CreateEmptyBoard") else pcbnew.BOARD()
    for a, b in (((100, 100), (140, 100)), ((140, 100), (140, 130)), ((140, 130), (100, 130)), ((100, 130), (100, 100))):
        add_line(board, a, b)

    # U1: SOIC-16-ish MCU at center
    left = ["+3V3", "GND", "/XIN", "/XOUT", "/USB_D+", "/USB_D-", "/SDA", "/SCL"]
    right = ["/LED", "/NRST", "/FB", "+3V3", "GND", "/EN", "/TX", "/RX"]
    pads = [(i + 1, (-3.0, -4.445 + i * 1.27), (1.5, 0.6), n) for i, n in enumerate(left)]
    pads += [(16 - i, (3.0, -4.445 + i * 1.27), (1.5, 0.6), n) for i, n in enumerate(right)]
    footprint(board, "U1", "MCU", (120, 115), pads)

    # Crystal + load caps (left of U1)
    footprint(board, "Y1", "8MHz", (110, 113.5), [(1, (0, -1.1), (1.2, 1.0), "/XIN"), (2, (0, 1.1), (1.2, 1.0), "/XOUT")])
    two_pad(board, "C1", "18p", (107, 112.4), "/XIN", "GND")
    two_pad(board, "C2", "18p", (107, 114.6), "/XOUT", "GND")
    # decoupling
    two_pad(board, "C3", "100n", (114.5, 109), "+3V3", "GND")
    two_pad(board, "C4", "100n", (126, 120), "+3V3", "GND")
    # buck: U2 SOT-23-6, L1, C5 in, C6 out
    footprint(board, "U2", "BUCK", (130, 106), [
        (1, (-1.0, -0.95), (0.6, 1.0), "/BST"), (2, (-1.0, 0), (0.6, 1.0), "GND"), (3, (-1.0, 0.95), (0.6, 1.0), "/FB"),
        (4, (1.0, 0.95), (0.6, 1.0), "/EN"), (5, (1.0, 0), (0.6, 1.0), "VBUS"), (6, (1.0, -0.95), (0.6, 1.0), "/SW")])
    two_pad(board, "C5", "10u", (134, 106), "VBUS", "GND", horizontal=False)
    footprint(board, "L1", "4.7u", (130, 102.5), [(1, (-1.6, 0), (1.4, 2.0), "/SW"), (2, (1.6, 0), (1.4, 2.0), "+3V3")])
    two_pad(board, "C6", "22u", (135.5, 102.5), "+3V3", "GND")
    two_pad(board, "C7", "100n", (127, 104.5), "/BST", "/SW")
    two_pad(board, "R1", "100k", (126, 109), "+3V3", "/FB")
    two_pad(board, "R2", "22k", (126, 111), "/FB", "GND")
    # USB connector-ish J1 (TH 5 pins) at left edge
    footprint(board, "J1", "USB", (103, 122), [
        (1, (0, -5.08), (1.6, 1.6), "VBUS"), (2, (0, -2.54), (1.6, 1.6), "/USB_D-"), (3, (0, 0), (1.6, 1.6), "/USB_D+"),
        (4, (0, 2.54), (1.6, 1.6), "GND"), (5, (0, 5.08), (1.6, 1.6), "GND")], smd=False)
    # I2C header J2 + pullups + LED
    footprint(board, "J2", "I2C", (137, 122), [
        (1, (0, -3.81), (1.6, 1.6), "+3V3"), (2, (0, -1.27), (1.6, 1.6), "/SDA"), (3, (0, 1.27), (1.6, 1.6), "/SCL"),
        (4, (0, 3.81), (1.6, 1.6), "GND")], smd=False)
    two_pad(board, "R3", "4k7", (130, 125), "+3V3", "/SDA")
    two_pad(board, "R4", "4k7", (130, 127.5), "+3V3", "/SCL")
    two_pad(board, "D1", "LED", (114, 126), "/LED", "GND")
    two_pad(board, "R5", "10k", (126, 124), "+3V3", "/NRST")
    two_pad(board, "R6", "100k", (134, 112), "VBUS", "/EN")

    pcbnew.SaveBoard(str(out), board)
    pro = out.with_suffix(".kicad_pro")
    if not pro.exists():
        pro.write_text(json.dumps({"board": {"design_settings": {"rules": {}}},
                                   "meta": {"filename": pro.name, "version": 1},
                                   "net_settings": {"classes": [{"name": "Default", "clearance": 0.2,
                                                                 "track_width": 0.25, "via_diameter": 0.6,
                                                                 "via_drill": 0.3}],
                                                    "meta": {"version": 3}, "netclass_patterns": []}}, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "test_board/test_board.kicad_pcb")
