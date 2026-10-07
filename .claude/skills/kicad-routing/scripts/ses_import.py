#!/usr/bin/env python3
"""Built-in Specctra SES importer (fallback for KiCad builds whose Python API has no
headless ImportSpecctraSES(board, file), and for engines with unusual SES output).

Behaviour (matches KiCad's importer, but keeps locked copper):
  * removes every UNLOCKED track/via on the board
  * adds every wire path and via from the session's network_out
  * skips items that duplicate existing locked copper
  * detects the coordinate scale automatically by checking which scale makes wire
    end points land on pads (different routers write SES resolution differently)

Library use:  from ses_import import import_ses; stats = import_ses(pcbnew, board, "x.ses")
CLI (KiCad Python):  ses_import.py board.kicad_pcb routed.ses -o out.kicad_pcb
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import all_tracks, is_via, load_board, save_board, set_via_size  # noqa: E402


# ---------------------------------------------------------------- s-expression parser
def tokenize(text):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            yield c
            i += 1
        elif c.isspace():
            i += 1
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 1
            yield text[i + 1:j]
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            yield text[i:j]
            i = j


def parse(text):
    stack, cur = [], []
    for tok in tokenize(text):
        if tok == "(":
            stack.append(cur)
            cur = []
        elif tok == ")":
            done = cur
            cur = stack.pop()
            cur.append(done)
        else:
            cur.append(tok)
    return cur[0] if cur else []


def find(node, key):
    if isinstance(node, list):
        if node and node[0] == key:
            yield node
        for ch in node:
            if isinstance(ch, list):
                yield from find(ch, key)


def first(node, key):
    return next(find(node, key), None)


# ---------------------------------------------------------------- import
UNIT_TO_MM = {"um": 1e-3, "mm": 1.0, "mil": 0.0254, "inch": 25.4, "cm": 10.0}


def read_session(path):
    tree = parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    routes = first(tree, "routes")
    if routes is None:
        raise ValueError("no (routes ...) section in session")
    res = first(routes, "resolution") or first(tree, "resolution") or ["resolution", "um", "1"]
    unit, res_val = res[1].lower(), float(res[2])
    padstacks = {}
    lib = first(routes, "library_out")
    for ps in (find(lib, "padstack") if lib else []):
        name = ps[1]
        dia = None
        for sh in find(ps, "circle"):
            dia = float(sh[2])
        padstacks[name] = dia
    nets = []
    net_out = first(routes, "network_out")
    for net in (n for n in (net_out or [])[1:] if isinstance(n, list) and n and n[0] == "net"):
        name = net[1]
        wires, vias = [], []
        for w in find(net, "wire"):
            path = first(w, "path")
            if path is None:
                continue
            layer, width = path[1], float(path[2])
            nums = [float(v) for v in path[3:] if not isinstance(v, list)]
            pts = list(zip(nums[0::2], nums[1::2]))
            typ = first(w, "type")
            wires.append({"layer": layer, "width": width, "pts": pts, "type": typ[1] if typ else None})
        for v in find(net, "via"):
            if len(v) >= 4 and not isinstance(v[2], list):
                typ = first(v, "type")
                vias.append({"padstack": v[1], "x": float(v[2]), "y": float(v[3]),
                             "type": typ[1] if typ else None})
        nets.append({"name": name, "wires": wires, "vias": vias})
    return {"unit": unit, "res": res_val, "padstacks": padstacks, "nets": nets}


def choose_scale(pcbnew, board, sess):
    """Return mm-per-session-unit, picking the candidate whose wire ends hit the most pads."""
    base = UNIT_TO_MM.get(sess["unit"], 1e-3)
    candidates = sorted({base / sess["res"], base})
    pads = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
            for fp in board.GetFootprints() for p in fp.Pads()]
    ends = [w["pts"][0] for n in sess["nets"] for w in n["wires"] if w["pts"]][:400]
    ends += [w["pts"][-1] for n in sess["nets"] for w in n["wires"] if w["pts"]][:400]
    if not ends or not pads:
        return candidates[0]

    def hits(s):
        h = 0
        for x, y in ends:
            X, Y = x * s, -y * s
            if any(abs(X - px) < 0.05 and abs(Y - py) < 0.05 for px, py in pads):
                h += 1
        return h
    return max(candidates, key=hits)


def via_size_mm(name, dia_units, scale):
    m = re.search(r"_(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)_um", name or "")
    if m:
        return float(m.group(1)) / 1000, float(m.group(2)) / 1000
    dia = dia_units * scale if dia_units else 0.6
    return dia, max(0.2, round(dia / 2, 3))


def import_ses(pcbnew, board, ses_path, remove_unlocked=True):
    sess = read_session(ses_path)
    scale = choose_scale(pcbnew, board, sess)

    def P(x, y):
        return pcbnew.VECTOR2I(int(round(pcbnew.FromMM(x * scale))), int(round(pcbnew.FromMM(-y * scale))))

    removed = 0
    if remove_unlocked:
        for t in [t for t in all_tracks(board) if not t.IsLocked()]:
            board.Remove(t)
            removed += 1

    tol = pcbnew.FromMM(0.002)
    locked_keys = set()
    for t in all_tracks(board):
        if is_via(pcbnew, t):
            p = t.GetPosition()
            locked_keys.add(("v", t.GetNetCode(), round(p.x / tol), round(p.y / tol)))
        else:
            a, b = t.GetStart(), t.GetEnd()
            k = sorted([(round(a.x / tol), round(a.y / tol)), (round(b.x / tol), round(b.y / tol))])
            locked_keys.add(("t", t.GetNetCode(), t.GetLayer(), *k[0], *k[1]))

    added_t = added_v = skipped = 0
    missing_nets = set()
    for net in sess["nets"]:
        ni = board.FindNet(net["name"])
        if ni is None or ni.GetNetCode() <= 0:
            missing_nets.add(net["name"])
            continue
        code = ni.GetNetCode()
        for w in net["wires"]:
            lid = board.GetLayerID(w["layer"])
            if lid < 0:
                continue
            width = int(round(pcbnew.FromMM(w["width"] * scale)))
            for (x1, y1), (x2, y2) in zip(w["pts"], w["pts"][1:]):
                a, b = P(x1, y1), P(x2, y2)
                if a.x == b.x and a.y == b.y:
                    continue
                k = sorted([(round(a.x / tol), round(a.y / tol)), (round(b.x / tol), round(b.y / tol))])
                if ("t", code, lid, *k[0], *k[1]) in locked_keys:
                    skipped += 1
                    continue
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(a)
                t.SetEnd(b)
                t.SetWidth(width)
                t.SetLayer(lid)
                t.SetNetCode(code)
                board.Add(t)
                added_t += 1
        for v in net["vias"]:
            p = P(v["x"], v["y"])
            if ("v", code, round(p.x / tol), round(p.y / tol)) in locked_keys:
                skipped += 1
                continue
            dia, drill = via_size_mm(v["padstack"], sess["padstacks"].get(v["padstack"]), scale)
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(p)
            try:
                via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            except Exception:
                pass
            set_via_size(pcbnew, via, int(pcbnew.FromMM(dia)), int(pcbnew.FromMM(drill)))
            via.SetNetCode(code)
            board.Add(via)
            added_v += 1
    return {"scale_mm_per_unit": scale, "removed_unlocked": removed, "added_tracks": added_t,
            "added_vias": added_v, "skipped_duplicates_of_locked": skipped,
            "nets_not_on_board": sorted(missing_nets)}


def main():
    from common import import_pcbnew
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("ses")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--keep-unlocked", action="store_true", help="do not delete existing unlocked copper")
    a = ap.parse_args()
    pcbnew = import_pcbnew()
    board = load_board(pcbnew, a.board)
    print(import_ses(pcbnew, board, a.ses, remove_unlocked=not a.keep_unlocked))
    save_board(pcbnew, board, a.output)


if __name__ == "__main__":
    main()
