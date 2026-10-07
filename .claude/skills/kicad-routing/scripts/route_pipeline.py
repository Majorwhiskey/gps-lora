#!/usr/bin/env python3
"""One-command route pass: constraints -> autoroute -> pours -> stitching -> DRC -> review.

Use this AFTER critical nets are routed and locked (SKILL.md phases 4-5). It never
touches the input board: it copies it to --output and works on the copy.

Usage (KiCad Python):
  route_pipeline.py board.kicad_pcb --plan routing_plan.json -o board_routed.kicad_pcb \
      [--jar freerouting.jar] [--skip-constraints] [--skip-autoroute] [--skip-pours] [--skip-stitch]

Reads from the plan:
  autoroute: {"passes":30, "ignore_netclasses":["GND_POUR"], "via_cost":80, "threads":4,
              "routable_layers":"true,true", "timeout":1800}
  pours:     [{"net":"GND","layers":["F.Cu","B.Cu"],"clearance":0.3,"min_width":0.25,
               "thermal_gap":0.5,"spoke":0.5,"connection":"thermal","priority":0}]
  stitching: {"net":"GND","pitch":5,"via":"0.6/0.3","edge_pitch":3,"layers":["F.Cu","B.Cu"],
              "keep_out_courtyards":true}
Writes <output>.pipeline.json with every stage's result and exit code.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable


def run(stage, args, log):
    cmd = [PY, str(HERE / args[0])] + [str(x) for x in args[1:]]
    print(f"\n=== {stage}: {' '.join(cmd)}")
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout + ("\n" + p.stderr if p.stderr.strip() else "")).strip()
    print(out[-4000:])
    log.append({"stage": stage, "rc": p.returncode, "seconds": round(time.time() - t0, 1), "tail": out[-1500:]})
    return p.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("--plan", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--jar")
    ap.add_argument("--skip-constraints", action="store_true")
    ap.add_argument("--skip-autoroute", action="store_true")
    ap.add_argument("--skip-pours", action="store_true")
    ap.add_argument("--skip-stitch", action="store_true")
    a = ap.parse_args()

    src, out = Path(a.board).resolve(), Path(a.output).resolve()
    if src == out:
        sys.exit("ERROR: --output must differ from the input board")
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    for ext in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
        s = src.with_suffix(ext)
        if s.exists():
            shutil.copy2(s, out.with_suffix(ext))
    log = []

    if not a.skip_constraints:
        if run("constraints", ["apply_constraints.py", a.plan, out], log):
            return finish(out, log, "constraint validation failed - fix the plan first")

    if not a.skip_autoroute:
        ar = plan.get("autoroute", {})
        args = ["autoroute_freerouting.py", out, "-o", out, "--passes", ar.get("passes", 30),
                "--timeout", ar.get("timeout", 1800)]
        if a.jar:
            args += ["--jar", a.jar]
        if ar.get("engine") in ("freerouting", "freeroute-py"):
            args += ["--engine", ar["engine"]]
        if ar.get("ignore_netclasses"):
            args += ["--ignore-netclasses", ",".join(ar["ignore_netclasses"])]
        for key, flag in (("via_cost", "--via-cost"), ("threads", "--threads"),
                          ("routable_layers", "--routable-layers"),
                          ("preferred_horizontal", "--preferred-horizontal")):
            if ar.get(key) is not None:
                args += [flag, ar[key]]
        if run("autoroute", args, log):
            return finish(out, log, "autoroute failed")

    if not a.skip_pours:
        for p in plan.get("pours", []):
            args = ["pours.py", "pour", out, "--net", p["net"], "--layers", ",".join(p["layers"])]
            for key, flag in (("clearance", "--clearance"), ("min_width", "--min-width"),
                              ("thermal_gap", "--thermal-gap"), ("spoke", "--spoke"),
                              ("connection", "--connection"), ("priority", "--priority")):
                if p.get(key) is not None:
                    args += [flag, p[key]]
            run(f"pour {p['net']}", args, log)

    st = plan.get("stitching")
    if st and not a.skip_stitch:
        args = ["pours.py", "stitch", out, "--net", st["net"], "--pitch", st.get("pitch", 5),
                "--via", st.get("via", "0.6/0.3")]
        if st.get("layers"):
            args += ["--layers", ",".join(st["layers"])]
        if st.get("edge_pitch"):
            args += ["--edge-pitch", st["edge_pitch"], "--edge-inset", st.get("edge_inset", 1.0)]
        if st.get("keep_out_courtyards"):
            args.append("--keep-out-courtyards")
        if st.get("stagger"):
            args.append("--stagger")
        run("stitch", args, log)

    drc_json = out.with_suffix(".drc_summary.json")
    rc_drc = run("drc", ["drc_report.py", out, "-o", drc_json], log)
    rc_rev = run("review", ["review_routing.py", out, "--plan", a.plan,
                            "-o", out.with_suffix(".review.json"), "--md", out.with_suffix(".review.md")], log)
    verdict = "CLEAN" if rc_drc == 0 and rc_rev == 0 else "NEEDS WORK (see drc/review output)"
    return finish(out, log, verdict)


def finish(out, log, verdict):
    rep = {"output": str(out), "verdict": verdict, "stages": log}
    Path(str(out) + ".pipeline.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"\nVERDICT: {verdict}\npipeline log: {out}.pipeline.json")
    sys.exit(0 if verdict == "CLEAN" else 1)


if __name__ == "__main__":
    main()
