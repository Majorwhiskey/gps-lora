#!/usr/bin/env python3
"""Run KiCad DRC headless and turn the JSON into an actionable, prioritised summary.

Usage (any python3; needs kicad-cli on PATH or --kicad-cli):
  drc_report.py board.kicad_pcb [--parity] [--refill] [-o drc_summary.json] [--max-items 15]
  drc_report.py --from-json existing_drc.json          # summarise a report you already have

Exit codes: 0 = clean (no errors, no unconnected), 3 = only warnings, 4 = errors/unrouted remain.

Each violation type is mapped to a category and a first-line fix from
references/drc-playbook.md so the agent can act on it without guessing.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

# type-substring -> (category, priority 1=fix first, first-line fix)
PLAYBOOK = [
    ("shorting_items", ("SHORT", 1, "Two nets touch. Delete the offending track/via and re-route; never 'fix' by moving pads.")),
    ("tracks_crossing", ("SHORT", 1, "Tracks of different nets cross on one layer: rip up the newer one and re-route.")),
    ("unconnected", ("UNROUTED", 2, "Route remaining connections (Phase 6). If Freerouting gave up, free space or add a layer.")),
    ("hole_clearance", ("CLEARANCE", 3, "Track/copper too close to a hole: re-route around or move the via.")),
    ("hole_to_hole", ("FAB", 3, "Drill holes too close: move one via (stitching vias are the usual culprit).")),
    ("copper_edge_clearance", ("FAB", 3, "Copper too close to board edge: re-route away or increase zone edge clearance.")),
    ("edge_clearance", ("FAB", 3, "Copper too close to board edge: re-route away or increase zone edge clearance.")),
    ("clearance", ("CLEARANCE", 3, "Nudge/re-route the track; if many, the netclass clearance is wider than the gaps placement allows.")),
    ("track_width", ("RULE", 4, "Track narrower than its rule: fix the netclass assignment or re-route with the class width.")),
    ("annular", ("FAB", 4, "Via/pad ring too thin for fab: enlarge via diameter or use the netclass via.")),
    ("drill_out_of_range", ("FAB", 4, "Drill smaller than fab min: use larger via drill.")),
    ("via_diameter", ("FAB", 4, "Via diameter below rule: use the netclass/fab via size.")),
    ("diff_pair", ("SI", 4, "Diff pair coupling/gap broken: re-route the pair together (route_diff / interactive diff router).")),
    ("skew", ("SI", 4, "Length mismatch: add tuning meanders on the SHORTER trace near the mismatch source.")),
    ("length_out_of_range", ("SI", 4, "Net length outside rule: shorten route or add tuning; check the rule is realistic.")),
    ("via_count", ("SI", 4, "Too many vias on a constrained net: re-route on fewer layers.")),
    ("starved_thermal", ("POWER", 5, "Too few thermal spokes reach the pad: clear tracks around it or make the pad connection solid.")),
    ("isolated_copper", ("POUR", 5, "Floating copper island: enable island removal or stitch it to GND with a via.")),
    ("zones_intersect", ("POUR", 5, "Overlapping zones of different nets with same priority: set priorities.")),
    ("track_dangling", ("CLEANUP", 6, "Stub track: delete it (cleanup), it is an antenna.")),
    ("via_dangling", ("CLEANUP", 6, "Via connected on one layer only: delete it, or connect it if it is a stitching via in a pour.")),
    ("courtyard", ("PLACEMENT", 7, "Courtyards overlap: placement issue - report to user, do not move parts silently.")),
    ("silk", ("COSMETIC", 8, "Silkscreen over pad/copper/edge: move or shrink the text; fab will clip it otherwise.")),
    ("solder_mask", ("COSMETIC", 8, "Solder mask bridge between pads: usually fine for fine-pitch ICs; check with fab.")),
    ("lib_footprint", ("LIBRARY", 9, "Footprint differs from library: ignore for routing; mention in report.")),
    ("footprint", ("LIBRARY", 9, "Footprint issue: review, usually not a routing problem.")),
    ("text_height", ("COSMETIC", 9, "Text too small for fab: increase size.")),
    ("text_thickness", ("COSMETIC", 9, "Text stroke too thin: increase thickness.")),
]


def classify(vtype: str):
    t = vtype.lower()
    for key, val in PLAYBOOK:
        if key in t:
            return val
    return ("OTHER", 7, "See references/drc-playbook.md")


def find_cli(explicit):
    if explicit:
        return explicit
    p = shutil.which("kicad-cli")
    if p:
        return p
    import glob
    for c in glob.glob(r"C:\Program Files\KiCad\*\bin\kicad-cli.exe") + \
            glob.glob("/Applications/KiCad*/KiCad.app/Contents/MacOS/kicad-cli"):
        return c
    sys.exit("ERROR: kicad-cli not found; pass --kicad-cli")


def run_drc(board, cli, parity, refill, out_json):
    cmd = [cli, "pcb", "drc", "--format", "json", "--units", "mm", "--severity-all",
           "-o", str(out_json)]
    if parity:
        cmd.append("--schematic-parity")
    if refill:
        cmd += ["--refill-zones"]
    cmd.append(str(board))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if not Path(out_json).exists():
        fb = drc_via_pcbnew(board, refill)
        if fb is not None:
            print("note: kicad-cli has no usable 'pcb drc' (KiCad < 8?) - used pcbnew.WriteDRCReport fallback")
            return fb
        sys.exit(f"ERROR: kicad-cli produced no report (rc={p.returncode}):\n{p.stdout}\n{p.stderr}")
    return json.loads(Path(out_json).read_text(encoding="utf-8"))


def drc_via_pcbnew(board, refill):
    """Fallback for KiCad 7: run DRC through pcbnew and convert the text report to the JSON schema."""
    try:
        import pcbnew  # noqa: F401
    except ImportError:
        return None
    import re
    import tempfile
    b = pcbnew.LoadBoard(str(board))
    if refill and len(list(b.Zones())):
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    rpt = Path(tempfile.mkstemp(suffix=".rpt")[1])
    pcbnew.WriteDRCReport(b, str(rpt), pcbnew.EDA_UNITS_MILLIMETRES, True)
    v, cur = [], None
    for line in rpt.read_text(errors="replace").splitlines():
        m = re.match(r"\[(\w+)\]: (.*)", line)
        if m:
            cur = {"type": m.group(1), "description": m.group(2), "severity": "error", "items": []}
            v.append(cur)
            continue
        m = re.match(r"\s+@\(([-\d.]+) mm, ([-\d.]+) mm\): (.*)", line)
        if m and cur:
            cur["items"].append({"description": m.group(3), "pos": {"x": float(m.group(1)), "y": float(m.group(2))}})
        elif cur and "Severity: warning" in line:
            cur["severity"] = "warning"
    unc = [x for x in v if x["type"] == "unconnected_items"]
    return {"violations": [x for x in v if x["type"] != "unconnected_items"], "unconnected_items": unc,
            "schematic_parity": [], "kicad_version": "pcbnew-fallback", "source": str(board)}


def item_desc(v):
    parts = []
    for it in v.get("items", [])[:2]:
        pos = it.get("pos", {})
        parts.append(f"{it.get('description', '?')} @({pos.get('x', '?')},{pos.get('y', '?')})")
    return " | ".join(parts)


def summarise(rep, max_items):
    violations = rep.get("violations", [])
    unconnected = rep.get("unconnected_items", [])
    parity = rep.get("schematic_parity", [])
    by_type = defaultdict(list)
    for v in violations:
        by_type[v.get("type", "unknown")].append(v)
    if unconnected:
        by_type["unconnected_items"] = unconnected

    groups = []
    for vtype, items in by_type.items():
        cat, prio, fix = classify(vtype)
        sev = Counter(i.get("severity", "error") for i in items)
        nets = Counter()
        for i in items:
            for it in i.get("items", []):
                d = it.get("description", "")
                if "[" in d and "]" in d:
                    nets[d[d.find("[") + 1: d.find("]")]] += 1
        groups.append({"type": vtype, "category": cat, "priority": prio, "count": len(items),
                       "severity": dict(sev), "fix": fix,
                       "top_nets": [n for n, _ in nets.most_common(6)],
                       "examples": [item_desc(i) for i in items[:max_items]]})
    groups.sort(key=lambda g: (g["priority"], -g["count"]))
    n_err = sum(g["severity"].get("error", 0) for g in groups)
    n_warn = sum(g["severity"].get("warning", 0) for g in groups)
    return {"errors": n_err, "warnings": n_warn, "unconnected": len(unconnected),
            "schematic_parity_issues": len(parity), "groups": groups,
            "kicad_version": rep.get("kicad_version"), "source": rep.get("source")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board", nargs="?")
    ap.add_argument("--from-json")
    ap.add_argument("--kicad-cli")
    ap.add_argument("--parity", action="store_true", help="also check schematic parity")
    ap.add_argument("--refill", action="store_true", help="refill zones before DRC (not saved)")
    ap.add_argument("-o", "--output", help="write summary JSON")
    ap.add_argument("--max-items", type=int, default=10)
    a = ap.parse_args()

    if a.from_json:
        rep = json.loads(Path(a.from_json).read_text(encoding="utf-8"))
    elif a.board:
        board = Path(a.board).resolve()
        raw = board.parent / ".routing_work" / (board.stem + "_drc.json")
        raw.parent.mkdir(exist_ok=True)
        rep = run_drc(board, find_cli(a.kicad_cli), a.parity, a.refill, raw)
    else:
        ap.error("board or --from-json required")

    s = summarise(rep, a.max_items)
    if a.output:
        Path(a.output).write_text(json.dumps(s, indent=2), encoding="utf-8")
    print(f"DRC: {s['errors']} errors, {s['warnings']} warnings, {s['unconnected']} unconnected, "
          f"{s['schematic_parity_issues']} parity issues")
    for g in s["groups"]:
        print(f"\n[P{g['priority']} {g['category']}] {g['type']} x{g['count']} {g['severity']}")
        print(f"   fix: {g['fix']}")
        if g["top_nets"]:
            print(f"   nets: {', '.join(g['top_nets'])}")
        for e in g["examples"][:5]:
            print(f"   - {e}")
    if s["errors"] or s["unconnected"]:
        sys.exit(4)
    if s["warnings"]:
        sys.exit(3)


if __name__ == "__main__":
    main()
