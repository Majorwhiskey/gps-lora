#!/usr/bin/env python3
"""Autoroute the remaining nets with Freerouting (headless), protecting critical copper.

Pipeline (one pcbnew session, as recommended for SWIG scripting):
  1. load board, snapshot every LOCKED track/via (your hand/critical routing)
  2. pcbnew.ExportSpecctraDSN(board, dsn)       - net classes go into the DSN
  3. java -jar freerouting.jar -de dsn -do ses --gui.enabled=false ...
  4. pcbnew.ImportSpecctraSES(board, ses)       - replaces tracks/vias
  5. restore any snapshot item that went missing, re-lock it
  6. refill zones, save to --output (never overwrites input unless -o == input)

Usage (KiCad Python):
  autoroute_freerouting.py board.kicad_pcb -o board_routed.kicad_pcb \
      --jar tools/freerouting-2.x.jar [--passes 30] [--threads 4] \
      [--ignore-netclasses GND,PWR_POUR] [--via-cost 50] [--routable-layers true,false,false,true] \
      [--timeout 900] [--keep-files]

Tips:
  * Put nets that will be connected by pours (GND, sometimes big power nets) into a
    net class and pass it via --ignore-netclasses, then pour + stitch afterwards.
  * Route and LOCK diff pairs, crystals, SMPS loops first (route_critical.py / KiCadRoutingTools).
  * Freerouting has no diff-pair or length-matching awareness. Never let it route those.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (all_tracks, backup, import_pcbnew, is_via, load_board, save_board,  # noqa: E402
                    set_via_size, via_diameter)


def snapshot_locked(pcbnew, board):
    snap = []
    for t in all_tracks(board):
        if not t.IsLocked():
            continue
        if is_via(pcbnew, t):
            snap.append({"kind": "via", "net": t.GetNetCode(), "pos": (t.GetPosition().x, t.GetPosition().y),
                         "diameter": via_diameter(pcbnew, t), "drill": t.GetDrillValue()})
        elif t.GetClass() == "PCB_TRACK":
            snap.append({"kind": "track", "net": t.GetNetCode(), "layer": t.GetLayer(),
                         "start": (t.GetStart().x, t.GetStart().y), "end": (t.GetEnd().x, t.GetEnd().y),
                         "width": t.GetWidth()})
    return snap


def restore_locked(pcbnew, board, snap, tol=2000):  # tol in nm
    def close(a, b):
        return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol

    tracks = [t for t in all_tracks(board)]
    restored = relocked = 0
    for s in snap:
        match = None
        for t in tracks:
            if t.GetNetCode() != s["net"]:
                continue
            if s["kind"] == "via" and is_via(pcbnew, t) and close((t.GetPosition().x, t.GetPosition().y), s["pos"]):
                match = t
                break
            if s["kind"] == "track" and not is_via(pcbnew, t) and t.GetLayer() == s["layer"]:
                a, b = (t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)
                if (close(a, s["start"]) and close(b, s["end"])) or (close(a, s["end"]) and close(b, s["start"])):
                    match = t
                    break
        if match is not None:
            if not match.IsLocked():
                match.SetLocked(True)
                relocked += 1
            continue
        net = board.FindNet(s["net"])
        if s["kind"] == "via":
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(*s["pos"]))
            try:
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            except Exception:
                pass
            set_via_size(pcbnew, v, s["diameter"], s["drill"])
            v.SetNet(net)
            v.SetLocked(True)
            board.Add(v)
        else:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(*s["start"]))
            t.SetEnd(pcbnew.VECTOR2I(*s["end"]))
            t.SetWidth(s["width"])
            t.SetLayer(s["layer"])
            t.SetNet(net)
            t.SetLocked(True)
            board.Add(t)
        restored += 1
    return restored, relocked


def count_copper(pcbnew, board):
    n_t = n_v = 0
    for t in all_tracks(board):
        if is_via(pcbnew, t):
            n_v += 1
        else:
            n_t += 1
    return n_t, n_v


def unconnected(board):
    try:
        board.BuildConnectivity()
        return board.GetConnectivity().GetUnconnectedCount(False)
    except Exception:
        return None


def run_freeroute_py(a, dsn, ses, log_path):
    """Java-free Python port (pip install freeroute). Lower density than the JAR."""
    exe = shutil.which("freeroute")
    cmd = [exe] if exe else [sys.executable, "-m", "freeroute"]
    cmd += ["-de", str(dsn), "-do", str(ses), "-mp", str(a.passes)]
    print("running:", " ".join(cmd))
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout)
        except subprocess.TimeoutExpired:
            pass
    if not Path(ses).exists():
        sys.exit("ERROR: freeroute produced no session. Log tail:\n" + Path(log_path).read_text(errors="replace")[-2000:])
    return time.time() - t0


def run_freerouting(a, dsn, ses, log_path):
    if a.engine == "freeroute-py":
        return run_freeroute_py(a, dsn, ses, log_path)
    java = shutil.which("java")
    if not java:
        sys.exit("ERROR: java not found (Freerouting 2.x needs Java 21+)")
    jar = a.jar or os.environ.get("FREEROUTING_JAR")
    if not jar or not os.path.exists(jar):
        sys.exit("ERROR: freerouting jar not found; pass --jar or set FREEROUTING_JAR")
    cmd = [java, "-jar", jar, "-de", str(dsn), "-do", str(ses),
           "-mp", str(a.passes), "--gui.enabled=false", "-dct", "0", "-da"]
    if a.threads is not None:
        cmd += ["-mt", str(a.threads)]
    if a.ignore_netclasses:
        cmd += ["-inc", a.ignore_netclasses]
    if a.via_cost is not None:
        cmd += [f"--router.via_costs={a.via_cost}"]
    if a.routable_layers:
        cmd += [f"--router.layers.routable={a.routable_layers}"]
    if a.preferred_horizontal:
        cmd += [f"--router.layers.preferred_direction_horizontal={a.preferred_horizontal}"]
    for extra in a.fr_arg or []:
        cmd.append(extra)
    print("running:", " ".join(cmd))
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    dt = time.time() - t0
    print(f"freerouting finished rc={rc} in {dt:.0f}s (log: {log_path})")
    if not Path(ses).exists():
        tail = Path(log_path).read_text(errors="replace")[-2000:]
        sys.exit(f"ERROR: no session file produced. Log tail:\n{tail}")
    return dt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("-o", "--output", help="output board (default <name>_routed.kicad_pcb)")
    ap.add_argument("--jar")
    ap.add_argument("--engine", choices=["freerouting", "freeroute-py"], default="freerouting",
                    help="freerouting = Java JAR (best); freeroute-py = pip 'freeroute' (no Java, lower density)")
    ap.add_argument("--passes", type=int, default=30, help="max autorouter passes (-mp)")
    ap.add_argument("--threads", type=int, help="optimizer threads (-mt); 0 disables optimization")
    ap.add_argument("--ignore-netclasses", help="comma list of netclasses NOT to route (-inc)")
    ap.add_argument("--via-cost", type=int, help="higher = fewer vias (e.g. 50..200)")
    ap.add_argument("--routable-layers", help="per-layer true/false list, top->bottom")
    ap.add_argument("--preferred-horizontal", help="per-layer true/false list, top->bottom")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds")
    ap.add_argument("--fr-arg", action="append", help="extra raw Freerouting arg (repeatable)")
    ap.add_argument("--importer", choices=["auto", "kicad", "builtin"], default="auto",
                    help="SES importer: KiCad's (needs KiCad 8+ headless API) or the built-in one")
    ap.add_argument("--no-fill", action="store_true", help="skip zone refill")
    ap.add_argument("--keep-files", action="store_true", help="keep .dsn/.ses/log next to the board")
    a = ap.parse_args()

    pcbnew = import_pcbnew()
    src = Path(a.board).resolve()
    out = Path(a.output).resolve() if a.output else src.with_name(src.stem + "_routed.kicad_pcb")
    if out == src:
        print(f"backup -> {backup(src, 'pre-autoroute')}")
    work = src.parent / ".routing_work"
    work.mkdir(exist_ok=True)
    dsn, ses, log = work / (src.stem + ".dsn"), work / (src.stem + ".ses"), work / (src.stem + "_freerouting.log")
    for f in (dsn, ses):
        if f.exists():
            f.unlink()

    board = load_board(pcbnew, src)
    before_t, before_v = count_copper(pcbnew, board)
    before_unc = unconnected(board)
    snap = snapshot_locked(pcbnew, board)
    print(f"before: {before_t} tracks, {before_v} vias, {before_unc} unconnected, {len(snap)} locked items protected")

    ok = pcbnew.ExportSpecctraDSN(board, str(dsn))
    if ok is False or not dsn.exists():
        sys.exit("ERROR: DSN export failed. Common causes: footprints without courtyard/duplicate refs, "
                 "missing board outline, pads with unsupported shapes. Fix DRC errors first.")
    elapsed = run_freerouting(a, dsn, ses, log)

    importer = a.importer
    if importer in ("auto", "kicad"):
        try:
            ok = pcbnew.ImportSpecctraSES(board, str(ses))
            if ok is False:
                raise RuntimeError("ImportSpecctraSES returned False")
            importer = "kicad"
        except (TypeError, RuntimeError) as e:
            if a.importer == "kicad":
                sys.exit(f"ERROR: KiCad SES import failed: {e}")
            print(f"KiCad headless SES import unavailable ({e.__class__.__name__}); using built-in importer")
            importer = "builtin"
    if importer == "builtin":
        from ses_import import import_ses
        print("builtin import:", import_ses(pcbnew, board, str(ses)))
    restored, relocked = restore_locked(pcbnew, board, snap)
    zones = board.Zones()
    if not a.no_fill and len(list(zones)) > 0:
        pcbnew.ZONE_FILLER(board).Fill(zones)
    after_t, after_v = count_copper(pcbnew, board)
    after_unc = unconnected(board)
    save_board(pcbnew, board, out)

    summary = {"output": str(out), "elapsed_s": round(elapsed), "tracks": after_t, "vias": after_v,
               "unconnected_before": before_unc, "unconnected_after": after_unc,
               "importer": importer, "locked_restored": restored, "locked_relocked": relocked,
               "dsn": str(dsn), "ses": str(ses), "log": str(log)}
    print(json.dumps(summary, indent=2))
    if not a.keep_files:
        for f in (dsn, ses):
            try:
                f.unlink()
            except OSError:
                pass
    if after_unc:
        print(f"NOTE: {after_unc} connections still unrouted - see SKILL.md Phase 6 'when the router fails'.")


if __name__ == "__main__":
    main()
