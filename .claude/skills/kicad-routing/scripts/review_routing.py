#!/usr/bin/env python3
"""Post-route quality review - the checks DRC does not do.

DRC proves the board is manufacturable and connected. This script looks for
things a senior layout reviewer would flag:
  * unrouted connections
  * diff-pair length mismatch and via-count asymmetry
  * 90-degree and acute corners (acid traps / poor SI on fast nets)
  * power nets narrower than their IPC-2221 requirement (needs current_a in plan)
  * foreign tracks routed under sensitive parts (crystals by default, plus plan
    "sensitive_refs", e.g. SMPS inductor, analog front end, antenna)
  * per-net length / via count table for critical nets

Usage (KiCad Python):
  review_routing.py board.kicad_pcb [--plan routing_plan.json] [-o review.json] [--md review.md]
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import all_tracks, import_pcbnew, is_arc, is_via, load_board, mm, write_json  # noqa: E402
from analyze_board import classify, detect_diff_pairs  # noqa: E402


def ipc_width(current, oz=1.0, rise=10.0, internal=False):
    k = 0.024 if internal else 0.048
    area = (current / (k * rise ** 0.44)) ** (1 / 0.725)
    return area / (oz * 1.378) / 39.3701


def seg_rect_intersect(x1, y1, x2, y2, l, t, r, b):
    """Liang-Barsky clip test."""
    dx, dy = x2 - x1, y2 - y1
    p = [-dx, dx, -dy, dy]
    q = [x1 - l, r - x1, y1 - t, b - y1]
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if pi == 0:
            if qi < 0:
                return False
        else:
            u = qi / pi
            if pi < 0:
                u1 = max(u1, u)
            else:
                u2 = min(u2, u)
            if u1 > u2:
                return False
    return True


def review(path, plan):
    pcbnew = import_pcbnew()
    board = load_board(pcbnew, path)
    res = {"file": str(Path(path).resolve()), "issues": [], "nets": {}}

    def issue(sev, kind, msg, **kw):
        res["issues"].append({"severity": sev, "type": kind, "msg": msg, **kw})

    try:
        board.BuildConnectivity()
        unc = board.GetConnectivity().GetUnconnectedCount(False)
        res["unconnected"] = unc
        if unc:
            issue("error", "unrouted", f"{unc} connection(s) unrouted")
    except Exception:
        res["unconnected"] = None

    segs = defaultdict(list)
    stats = defaultdict(lambda: {"length_mm": 0.0, "vias": 0, "layers": set(), "min_w": None, "max_w": None})
    for t in all_tracks(board):
        nn = t.GetNetname()
        st = stats[nn]
        if is_via(pcbnew, t):
            st["vias"] += 1
            continue
        L = mm(pcbnew, t.GetLength())
        w = mm(pcbnew, t.GetWidth())
        st["length_mm"] += L
        st["layers"].add(board.GetLayerName(t.GetLayer()))
        st["min_w"] = w if st["min_w"] is None else min(st["min_w"], w)
        st["max_w"] = w if st["max_w"] is None else max(st["max_w"], w)
        if not is_arc(t):
            s, e = t.GetStart(), t.GetEnd()
            segs[(nn, t.GetLayer())].append((mm(pcbnew, s.x), mm(pcbnew, s.y), mm(pcbnew, e.x), mm(pcbnew, e.y)))

    # ---- corners
    n90 = nacute = 0
    corner_nets = defaultdict(lambda: [0, 0])
    for (nn, _layer), lst in segs.items():
        ends = defaultdict(list)
        for s in lst:
            ends[(round(s[0], 3), round(s[1], 3))].append((s[2] - s[0], s[3] - s[1]))
            ends[(round(s[2], 3), round(s[3], 3))].append((s[0] - s[2], s[1] - s[3]))
        for pt, dirs in ends.items():
            if len(dirs) != 2:
                continue
            (ax, ay), (bx, by) = dirs
            la, lb = math.hypot(ax, ay), math.hypot(bx, by)
            if la < 1e-6 or lb < 1e-6:
                continue
            ang = math.degrees(math.acos(max(-1, min(1, (ax * bx + ay * by) / (la * lb)))))
            if abs(ang - 90) < 2:
                n90 += 1
                corner_nets[nn][0] += 1
            elif ang < 88:
                nacute += 1
                corner_nets[nn][1] += 1
    res["corners"] = {"right_angle": n90, "acute": nacute,
                      "worst_nets": sorted(([n, *c] for n, c in corner_nets.items()), key=lambda x: -(x[1] + 3 * x[2]))[:10]}
    if nacute:
        issue("warning", "acute_corner", f"{nacute} acute (<90 deg) track corners - acid traps / poor etch; reroute with 45s")
    if n90:
        issue("info", "right_angle", f"{n90} 90-degree corners - acceptable for slow signals, avoid on fast/RF nets")

    # ---- plan-driven checks
    plan = plan or {}
    oz = plan.get("copper_oz", 1.0)
    all_nets = list(stats.keys())
    for nc in plan.get("netclasses", []):
        if not nc.get("current_a"):
            continue
        need = ipc_width(nc["current_a"], oz)
        pats = nc.get("patterns", []) + nc.get("nets", [])
        for nn in all_nets:
            if any(fnmatch.fnmatchcase(nn, p) for p in pats):
                w = stats[nn]["min_w"]
                if w is not None and w + 1e-6 < need:
                    issue("error", "power_width",
                          f"{nn}: narrowest track {w} mm < {need:.2f} mm needed for {nc['current_a']} A "
                          "(neck-downs at fine-pitch pads are OK if short - verify)", net=nn)

    # ---- diff pairs
    pairs = []
    for dp in plan.get("diff_pairs", []):
        if dp.get("p") and dp.get("n"):
            pairs.append({"base": dp.get("name"), "p": dp["p"], "n": dp["n"],
                          "max_skew_mm": dp.get("max_skew_mm")})
    if not pairs:
        pairs = detect_diff_pairs([n for n in all_nets if n])
    res["diff_pairs"] = []
    for dp in pairs:
        sp, sn = stats.get(dp["p"]), stats.get(dp["n"])
        if not sp or not sn:
            continue
        delta = abs(sp["length_mm"] - sn["length_mm"])
        row = {"pair": f"{dp['p']}/{dp['n']}", "len_p": round(sp["length_mm"], 3),
               "len_n": round(sn["length_mm"], 3), "delta_mm": round(delta, 3),
               "vias_p": sp["vias"], "vias_n": sn["vias"]}
        res["diff_pairs"].append(row)
        lim = dp.get("max_skew_mm")
        if lim is not None and delta > lim:
            issue("error", "diff_skew", f"{row['pair']}: length delta {delta:.3f} mm > {lim} mm")
        if sp["vias"] != sn["vias"]:
            issue("warning", "diff_via_asym", f"{row['pair']}: via count {sp['vias']} vs {sn['vias']}")

    # ---- sensitive footprints
    refs = set(plan.get("sensitive_refs", []))
    for fp in board.GetFootprints():
        if re.match(r"^(Y|X)\d", fp.GetReference()):
            refs.add(fp.GetReference())
    for ref in sorted(refs):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            continue
        own = {p.GetNetname() for p in fp.Pads()}
        try:
            bb = fp.GetBoundingBox(False, False)
        except TypeError:
            bb = fp.GetBoundingBox()
        l, t, r, b = mm(pcbnew, bb.GetLeft()), mm(pcbnew, bb.GetTop()), mm(pcbnew, bb.GetRight()), mm(pcbnew, bb.GetBottom())
        intruders = set()
        for (nn, layer), lst in segs.items():
            if nn in own or classify(nn) == "ground":   # ground under a crystal is the guard, not an intruder
                continue
            for s in lst:
                if seg_rect_intersect(*s, l, t, r, b):
                    intruders.add(f"{nn}@{board.GetLayerName(layer)}")
                    break
        if intruders:
            issue("warning", "under_sensitive",
                  f"{ref}: foreign tracks under the part: {', '.join(sorted(intruders)[:8])}", ref=ref)

    # ---- net table (critical-ish nets only to keep it short)
    for nn, st in stats.items():
        res["nets"][nn] = {"length_mm": round(st["length_mm"], 2), "vias": st["vias"],
                           "layers": sorted(st["layers"]), "min_w": st["min_w"], "max_w": st["max_w"]}
    res["totals"] = {"track_length_mm": round(sum(s["length_mm"] for s in stats.values()), 1),
                     "vias": sum(s["vias"] for s in stats.values())}
    order = {"error": 0, "warning": 1, "info": 2}
    res["issues"].sort(key=lambda i: order[i["severity"]])
    return res


def to_markdown(r):
    lines = [f"# Routing review: {Path(r['file']).name}", "",
             f"- Unrouted connections: **{r.get('unconnected')}**",
             f"- Total track length: {r['totals']['track_length_mm']} mm, vias: {r['totals']['vias']}",
             f"- Corners: {r['corners']['right_angle']} at 90 deg, {r['corners']['acute']} acute", ""]
    if r["issues"]:
        lines += ["## Issues", ""] + [f"- **{i['severity']}** `{i['type']}` - {i['msg']}" for i in r["issues"]] + [""]
    if r["diff_pairs"]:
        lines += ["## Differential pairs", "", "| pair | P mm | N mm | delta mm | vias P/N |", "|---|---|---|---|---|"]
        lines += [f"| {d['pair']} | {d['len_p']} | {d['len_n']} | {d['delta_mm']} | {d['vias_p']}/{d['vias_n']} |"
                  for d in r["diff_pairs"]]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("--plan")
    ap.add_argument("-o", "--output")
    ap.add_argument("--md")
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8")) if a.plan else None
    r = review(a.board, plan)
    write_json(r, a.output)
    md = to_markdown(r)
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    print(md)
    sys.exit(4 if any(i["severity"] == "error" for i in r["issues"]) else 0)


if __name__ == "__main__":
    main()
