#!/usr/bin/env python3
"""
fab-export.py - generate fab-ready outputs for the Theoros board (Lion Circuits).

Ported from limen/hardware/roof-v2/tools/fab-export.py and adapted to this project:
4-layer board whose inner layers are named GND/PWR, top-side-only assembly, board
origin set at the bottom-left corner, and parts with nothing to place (test points,
fiducials, mounting holes, the Tag-Connect pads, the OLED panel) kept out of the
assembler's files.

Produces, under hardware/fab/ (gitignored):
  1. theoros-bom.csv            BOM grouped by Value + Footprint (+ MPN once added)
  2. theoros-pos.csv            pick-and-place, top side, mm, origin = board bottom-left
  3. gerbers/*.gbr               Gerbers: F.Cu, In1 (GND), In2 (PWR), B.Cu + mask/silk/paste/edge
  4. gerbers/*.drl + map         Excellon drill files (PTH/NPTH separate) + drill map
  5. theoros-fab-notes.txt      board spec sheet for the order form
  6. theoros-fab-<rev>-<ts>.zip single archive of the above

Before exporting it:
  * runs ERC and DRC (zones refilled, schematic parity) and refuses on any error
    (warnings are listed but allowed). Use --force to export anyway.
  * refills all zones in a temporary copy of the board, so the Gerbers never carry
    stale pours. The board file in the repo is not modified.

Options:
  --force     export even if ERC/DRC report errors
  --release   also copy the archive to production/ (committed release outputs)
  --finish/--mask/--silk/--copper/--thickness   order options written to the fab notes
              (defaults: ENIG, green, white, 1 oz, 1.6 mm)

Requires kicad-cli and KiCad's Python module (pcbnew), KiCad >= 9.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

HW = Path(__file__).resolve().parent.parent          # hardware/
REPO = HW.parent
NAME = "theoros"
PCB = HW / f"{NAME}.kicad_pcb"
SCH = HW / f"{NAME}.kicad_sch"
FAB = HW / "fab"
PROJECT_FILES = [f"{NAME}.kicad_pro", f"{NAME}.kicad_dru", "fp-lib-table", "sym-lib-table"]

# Canonical layer names; kicad-cli maps In1.Cu/In2.Cu to the user names GND/PWR.
LAYERS = ("F.Cu,In1.Cu,In2.Cu,B.Cu,"
          "F.Paste,B.Paste,F.Mask,B.Mask,"
          "F.SilkS,B.SilkS,Edge.Cuts")

# Footprints that have no component for the assembler to place.
NOT_PLACED = ("MountingHole", "Fiducial", "TestPoint", "Tag-Connect", "OLED_ER-OLED0.96")


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"command failed: {cmd[0]}")
    for line in result.stdout.strip().splitlines():
        if line.strip():
            print(f"    {line}")
    return result


def git_rev() -> str:
    try:
        h = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", "hardware"],
                               capture_output=True, text=True).stdout.strip()
        return h + ("-dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "nogit"


# ---------------------------------------------------------------- preparation

def make_work_copy(tmp: Path) -> Path:
    """Copy the project into tmp, refill every zone and set the board origin."""
    for f in [PCB.name, *PROJECT_FILES]:
        if (HW / f).exists():
            shutil.copy2(HW / f, tmp / f)
    for sch in HW.glob("*.kicad_sch"):
        shutil.copy2(sch, tmp / sch.name)
    (tmp / "lib").symlink_to(HW / "lib")

    try:
        import pcbnew
    except ImportError:
        raise SystemExit("pcbnew Python module not found (run with KiCad's python3)")
    work = tmp / PCB.name
    board = pcbnew.LoadBoard(str(work))
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    # Board origin = bottom-left corner of the outline, used for Gerbers, drill and POS.
    bbox = board.GetBoardEdgesBoundingBox()
    origin = pcbnew.VECTOR2I(bbox.GetX(), bbox.GetBottom())
    ds = board.GetDesignSettings()
    ds.SetAuxOrigin(origin)
    board.Save(str(work))
    print(f"  refilled {len(board.Zones())} zone(s); origin at board bottom-left "
          f"({pcbnew.ToMM(origin.x):.2f}, {pcbnew.ToMM(origin.y):.2f}) mm page coords")
    return work


def preflight(work: Path, force: bool) -> list[str]:
    """ERC + DRC gate. Returns warning lines for the notes file."""
    notes = []
    erc_json = work.parent / "erc.json"
    drc_json = work.parent / "drc.json"
    run(["kicad-cli", "sch", "erc", "--format", "json", "--severity-all",
         "--output", str(erc_json), str(work.parent / SCH.name)], check=False)
    run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
         "--schematic-parity", "--refill-zones",
         "--output", str(drc_json), str(work)], check=False)
    erc = json.loads(erc_json.read_text())
    drc = json.loads(drc_json.read_text())
    erc_v = [v for s in erc.get("sheets", []) for v in s.get("violations", [])]
    drc_v = drc.get("violations", []) + drc.get("schematic_parity", [])
    unconnected = drc.get("unconnected_items", [])

    errors = [f"ERC {v['type']}: {v['description']}" for v in erc_v if v["severity"] == "error"]
    errors += [f"DRC {v['type']}: {v['description']}" for v in drc_v if v["severity"] == "error"]
    if unconnected:
        errors.append(f"DRC: {len(unconnected)} unconnected item(s)")
    warnings = [f"ERC {v['type']}: {v['description']}" for v in erc_v if v["severity"] != "error"]
    warnings += [f"DRC {v['type']}: {v['description']}" for v in drc_v if v["severity"] != "error"]

    print(f"  ERC: {len(erc_v)} violation(s), DRC: {len(drc_v)} violation(s), "
          f"{len(unconnected)} unconnected")
    for w in sorted(set(warnings)):
        print(f"    warning: {w}")
        notes.append(w)
    if errors:
        for e in errors:
            print(f"    ERROR: {e}")
        if not force:
            raise SystemExit("  pre-flight failed: fix the errors above or re-run with --force")
        print("  --force given: exporting despite errors")
        notes += [f"EXPORTED WITH ERROR: {e}" for e in errors]
    return notes


# ---------------------------------------------------------------- exports

def export_bom(work: Path) -> Path:
    out = FAB / f"{NAME}-bom.csv"
    run([
        "kicad-cli", "sch", "export", "bom",
        "--output", str(out),
        "--fields",
        "Reference,${QUANTITY},Value,MPN,Manufacturer,Footprint,Datasheet,Description,${DNP}",
        "--labels",
        "Reference,Qty,Value,MPN,Manufacturer,Footprint,Datasheet,Description,DNP",
        "--group-by", "Value,Footprint,MPN",
        "--ref-range-delimiter", "",  # list refs individually, no C1-C5 ranges
        "--exclude-dnp",
        str(work.parent / SCH.name),
    ])
    # Drop rows with nothing to buy/place (test points, fiducials, holes, pads-only parts).
    rows = list(csv.reader(out.open()))
    head, body = rows[0], rows[1:]
    fp = head.index("Footprint")
    keep = [r for r in body if not any(k in r[fp] for k in NOT_PLACED)]
    with out.open("w", newline="") as f:
        csv.writer(f, quoting=csv.QUOTE_ALL).writerows([head] + keep)
    print(f"    {len(keep)} BOM line(s), dropped {len(body) - len(keep)} non-placed line(s)")
    mpn = head.index("MPN")
    missing = [r[0] for r in keep if not r[mpn].strip()]
    if missing:
        print(f"    note: {len(missing)} BOM line(s) have no MPN (add an MPN field before ordering)")
    return out


def export_pos(work: Path) -> Path:
    out = FAB / f"{NAME}-pos.csv"
    run([
        "kicad-cli", "pcb", "export", "pos",
        "--output", str(out),
        "--format", "csv",
        "--units", "mm",
        "--side", "both",
        "--use-drill-file-origin",
        "--exclude-dnp",
        str(work),
    ])
    rows = list(csv.reader(out.open()))
    head, body = rows[0], rows[1:]
    pkg = head.index("Package") if "Package" in head else 2
    side = head.index("Side") if "Side" in head else len(head) - 1
    keep = [r for r in body if not any(k in r[pkg] for k in NOT_PLACED)]
    with out.open("w", newline="") as f:
        csv.writer(f, quoting=csv.QUOTE_ALL).writerows([head] + keep)
    print(f"    {len(keep)} placement(s), dropped {len(body) - len(keep)} non-placed footprint(s)")
    bottom = [r[0] for r in keep if r[side].lower().startswith("b")]
    if bottom:
        raise SystemExit(f"  bottom-side parts found {bottom}: this board is top-side assembly only")
    return out


def export_gerbers(work: Path) -> Path:
    out_dir = FAB / "gerbers"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*"):
        stale.unlink()  # renamed outputs must not leave stale files for the zip
    run([
        "kicad-cli", "pcb", "export", "gerbers",
        "--output", str(out_dir) + "/",
        "--layers", LAYERS,
        "--use-drill-file-origin",
        "--no-protel-ext",
        str(work),
    ])
    return out_dir


def export_drill(work: Path, gerber_dir: Path) -> None:
    run([
        "kicad-cli", "pcb", "export", "drill",
        "--output", str(gerber_dir) + "/",
        "--format", "excellon",
        "--excellon-separate-th",
        "--drill-origin", "plot",
        "--excellon-units", "mm",
        "--generate-map",
        "--map-format", "gerberx2",
        str(work),
    ])


def linearize_profile(gerber_dir: Path) -> None:
    """Replace G02/G03 arcs in all plotted gerbers with chord segments.

    Some fab DFM/preview/CAM engines mis-handle G75 multi-quadrant arcs, which
    breaks outlines. Lines-only output parses everywhere; sagitta < ~2 um.
    """
    for gbr in sorted(gerber_dir.glob("*.gbr")):
        lines = gbr.read_text().splitlines()
        out, cur, arc_dir, n_arcs = [], (None, None), 0, 0
        coord = re.compile(r"^X(-?\d+)Y(-?\d+)(?:I(-?\d+)J(-?\d+))?D0([12])\*$")
        for ln in lines:
            if ln == "G75*":
                continue
            if ln in ("G01*", "G02*", "G03*"):
                arc_dir = {"G01*": 0, "G02*": -1, "G03*": 1}[ln]
                if arc_dir == 0:
                    out.append(ln)
                continue
            m = coord.match(ln)
            if not m:
                out.append(ln)
                continue
            x, y = int(m.group(1)), int(m.group(2))
            if m.group(5) == "2" or arc_dir == 0 or m.group(3) is None:
                out.append(ln)
                cur = (x, y)
                continue
            n_arcs += 1
            i, j = int(m.group(3)), int(m.group(4))
            cx, cy = cur[0] + i, cur[1] + j
            r = math.hypot(cur[0] - cx, cur[1] - cy)
            a0 = math.atan2(cur[1] - cy, cur[0] - cx)
            a1 = math.atan2(y - cy, x - cx)
            sweep = (a1 - a0) % (2 * math.pi)
            if arc_dir < 0:
                sweep -= 2 * math.pi
            if abs(sweep) < 1e-9:
                sweep = arc_dir * 2 * math.pi
            n = max(8, int(abs(sweep) / (2 * math.acos(max(0.0, 1 - 2000 / r))))) if r > 2000 else 8
            for k in range(1, n + 1):
                if k == n:
                    px, py = x, y
                else:
                    a = a0 + sweep * k / n
                    px, py = round(cx + r * math.cos(a)), round(cy + r * math.sin(a))
                out.append(f"X{px}Y{py}D01*")
            out.append("G01*")
            cur = (x, y)
        gbr.write_text("\n".join(out) + "\n")
        if n_arcs:
            print(f"    linearized {n_arcs} arc(s) in {gbr.name}")


def reorder_profile(gerber_dir: Path) -> None:
    """Rewrite the Edge.Cuts gerber as one contiguous closed loop."""
    for gbr in gerber_dir.glob("*Edge_Cuts.gbr"):
        lines = gbr.read_text().splitlines()
        head, segs, cur, tail = [], [], None, []
        coord = re.compile(r"^X(-?\d+)Y(-?\d+)D0([12])\*$")
        for ln in lines:
            m = coord.match(ln)
            if not m:
                (tail if ln == "M02*" else head).append(ln)
                continue
            x, y, d = int(m.group(1)), int(m.group(2)), m.group(3)
            if d == "1" and cur is not None:
                segs.append((cur, (x, y)))
            cur = (x, y)
        if not segs:
            continue
        near = lambda p, q: abs(p[0] - q[0]) <= 10 and abs(p[1] - q[1]) <= 10
        chain = [segs.pop(0)]
        while segs:
            end = chain[-1][1]
            for i, (a, b) in enumerate(segs):
                if near(a, end):
                    chain.append((end, b)); segs.pop(i); break
                if near(b, end):
                    chain.append((end, a)); segs.pop(i); break
            else:
                raise SystemExit(f"  profile not a single closed contour in {gbr.name}")
        if not near(chain[-1][1], chain[0][0]):
            raise SystemExit(f"  profile loop does not close in {gbr.name}")
        chain[-1] = (chain[-1][0], chain[0][0])
        out = head + [f"X{chain[0][0][0]}Y{chain[0][0][1]}D02*"]
        out += [f"X{b[0]}Y{b[1]}D01*" for a, b in chain]
        gbr.write_text("\n".join(out + tail) + "\n")
        print(f"    reordered profile into 1 closed loop ({len(chain)} segments) in {gbr.name}")


def write_notes(work: Path, rev: str, warnings: list[str], spec: argparse.Namespace) -> Path:
    import pcbnew
    board = pcbnew.LoadBoard(str(work))
    bbox = board.GetBoardEdgesBoundingBox()
    ds = board.GetDesignSettings()
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    min_drill = min((v.GetDrillValue() for v in vias), default=0)
    holes = [p.GetDrillSize().x for f in board.GetFootprints() for p in f.Pads() if p.GetDrillSize().x > 0]
    parts = [f for f in board.GetFootprints() if not f.IsDNP()
             and not (f.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_POS_FILES)
             and not any(k in f.GetFPIDAsString() for k in NOT_PLACED)]
    top = sum(1 for f in parts if f.GetLayer() == pcbnew.F_Cu)
    gerbers = sorted(p.name for p in (FAB / "gerbers").iterdir())
    txt = f"""Theoros PCB - fabrication notes
Revision: {rev}    generated {datetime.now():%Y-%m-%d %H:%M}

Board
  Size:            {pcbnew.ToMM(bbox.GetWidth()):.2f} x {pcbnew.ToMM(bbox.GetHeight()):.2f} mm, rectangular
  Layers:          4 (L1 F.Cu signals, L2 solid GND plane, L3 3V3 plane with +5V island, L4 B.Cu signals)
  Thickness:       {spec.thickness} mm, FR-4 (fab standard 4-layer stackup; impedance widths pending)
  Copper:          {spec.copper} oz outer (inner per fab standard)
  Finish:          {spec.finish}
  Solder mask:     {spec.mask} both sides, silkscreen {spec.silk} both sides
  Bottom artwork:  intentional solder mask opening (owl logo) over the GND pour on B.Cu;
                   finish it like the pads, do not cover it with mask
  Min track/space: {pcbnew.ToMM(ds.m_TrackMinWidth):.2f} / {pcbnew.ToMM(ds.m_MinClearance):.2f} mm (design rule)
  Min via:         {pcbnew.ToMM(ds.m_ViasMinSize):.2f} mm pad / {pcbnew.ToMM(min_drill):.2f} mm drill, {len(vias)} vias
  Other holes:     {len(holes)} plated/non-plated pad hole(s), smallest {pcbnew.ToMM(min(holes)) if holes else 0:.2f} mm
  Tracks:          {len(tracks)} segments
  Via in pad:      one unfilled via on R504.2 (SD_DAT1 pull-up) - fill/cap if offered

Assembly
  Side:            top only ({top} placements in POS file)
  Origin:          board bottom-left corner (Gerbers, drill and POS share it)
  Not assembled:   OLED panel DS501 (plugged in at final assembly), test points,
                   fiducials, mounting holes, Tag-Connect J301 pads, DNP parts

Files
""" + "".join(f"  gerbers/{g}\n" for g in gerbers) + f"""  {NAME}-bom.csv
  {NAME}-pos.csv
"""
    if warnings:
        txt += "\nPre-flight warnings (reviewed, not errors)\n" + "".join(f"  - {w}\n" for w in sorted(set(warnings)))
    out = FAB / f"{NAME}-fab-notes.txt"
    out.write_text(txt)
    return out


def zip_fab(rev: str, ts: str) -> Path:
    out = FAB / f"{NAME}-fab-{rev}-{ts}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(FAB.rglob("*")):
            if f.is_file() and f.suffix != ".zip":
                zf.write(f, f.relative_to(FAB))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--force", action="store_true", help="export despite ERC/DRC errors")
    ap.add_argument("--release", action="store_true", help="also copy the zip to production/")
    ap.add_argument("--finish", default="ENIG (preferred: 0.5 mm FH12 pitch, module castellations)",
                    help="surface finish written to the fab notes")
    ap.add_argument("--mask", default="green", help="solder mask colour")
    ap.add_argument("--silk", default="white", help="silkscreen colour")
    ap.add_argument("--copper", default="1", help="outer copper weight, oz")
    ap.add_argument("--thickness", default="1.6", help="board thickness, mm")
    args = ap.parse_args()

    if not shutil.which("kicad-cli"):
        sys.exit("kicad-cli not found in PATH (install KiCad >= 9)")
    if not PCB.exists():
        sys.exit(f"{PCB} not found")
    if list(HW.glob("~*.lck")) or list(HW.glob("*.lck")):
        print("  warning: a KiCad lock file exists - unsaved GUI edits will not be exported")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rev = git_rev()
    FAB.mkdir(parents=True, exist_ok=True)
    print(f"\n=== {NAME} ({rev}) ===")
    with tempfile.TemporaryDirectory(prefix="theoros-fab-") as tmp:
        work = make_work_copy(Path(tmp))
        warnings = preflight(work, args.force)
        bom = export_bom(work)
        pos = export_pos(work)
        gerbers = export_gerbers(work)
        export_drill(work, gerbers)
        linearize_profile(gerbers)  # after drill: the drill map gerber has arcs too
        reorder_profile(gerbers)
        notes = write_notes(work, rev, warnings, args)
    archive = zip_fab(rev, ts)

    print(f"  BOM:      {bom.relative_to(REPO)}")
    print(f"  POS:      {pos.relative_to(REPO)}")
    print(f"  Gerbers:  {gerbers.relative_to(REPO)}/")
    print(f"  Notes:    {notes.relative_to(REPO)}")
    print(f"  Archive:  {archive.relative_to(REPO)}")
    if args.release:
        dest = REPO / "production" / archive.name
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(archive, dest)
        print(f"  Release:  {dest.relative_to(REPO)}")
    print("\nDone.")


if __name__ == "__main__":
    main()
