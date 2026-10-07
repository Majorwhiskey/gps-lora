#!/usr/bin/env python3
"""Environment check for the kicad-routing skill.

Reports: KiCad Python (pcbnew) and version, kicad-cli, Java (>=21 for
Freerouting 2.x), a Freerouting jar, and KiCadRoutingTools if present.
Runs with ANY python3 - it probes the KiCad interpreter itself.

Usage:
  python3 doctor.py [--freerouting-jar PATH] [--krt-dir PATH] [--json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def candidate_pythons():
    c = [sys.executable, shutil.which("python3"), shutil.which("python")]
    c += glob.glob(r"C:\Program Files\KiCad\*\bin\python.exe")
    c += glob.glob("/Applications/KiCad*/KiCad.app/Contents/Frameworks/Python.framework/Versions/*/bin/python3")
    c += ["/usr/bin/python3", "/usr/local/bin/python3"]
    seen, out = set(), []
    for p in c:
        if p and os.path.exists(p) and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def find_kicad_cli():
    c = [shutil.which("kicad-cli")]
    c += glob.glob(r"C:\Program Files\KiCad\*\bin\kicad-cli.exe")
    c += glob.glob("/Applications/KiCad*/KiCad.app/Contents/MacOS/kicad-cli")
    for p in c:
        if p and os.path.exists(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--freerouting-jar", default=os.environ.get("FREEROUTING_JAR"))
    ap.add_argument("--krt-dir", default=os.environ.get("KICAD_ROUTING_TOOLS"),
                    help="Path to a KiCadRoutingTools checkout")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    report = {"ok": True, "checks": {}, "advice": []}

    # --- pcbnew
    probe = "import pcbnew,sys;v=getattr(pcbnew,'FullVersion',None) or pcbnew.GetBuildVersion;print(v())"
    found = None
    for py in candidate_pythons():
        rc, out = run([py, "-c", probe])
        if rc == 0:
            found = {"python": py, "kicad_version": out.splitlines()[-1]}
            break
    report["checks"]["pcbnew"] = found or {"error": "no interpreter can import pcbnew"}
    if not found:
        report["ok"] = False
        report["advice"].append("Install KiCad 9 or 10 and run the scripts with its Python "
                                "(Windows: C:\\Program Files\\KiCad\\10.0\\bin\\python.exe).")
    else:
        m = re.match(r"\(?(\d+)", found["kicad_version"])
        major = int(m.group(1)) if m else 0
        found["major"] = major
        if major and major < 9:
            report["advice"].append(f"KiCad {major} detected. The skill targets 9/10; most scripts work on 8, "
                                    "but kicad-cli DRC JSON and some APIs differ.")
        if major >= 11:
            report["advice"].append("KiCad 11 removed the SWIG pcbnew bindings - these scripts need porting "
                                    "to the IPC API (kicad-python). See references/tool-reference.md.")

    # --- kicad-cli
    cli = find_kicad_cli()
    if cli:
        rc, out = run([cli, "version"])
        report["checks"]["kicad_cli"] = {"path": cli, "version": out.splitlines()[-1] if out else "?"}
    else:
        report["ok"] = False
        report["checks"]["kicad_cli"] = {"error": "kicad-cli not found"}
        report["advice"].append("kicad-cli is required for DRC. It ships with KiCad 8+.")

    # --- java
    java = shutil.which("java")
    if java:
        rc, out = run([java, "-version"])
        m = re.search(r'version "(\d+)', out)
        jv = int(m.group(1)) if m else 0
        report["checks"]["java"] = {"path": java, "major": jv}
        if jv and jv < 21:
            report["advice"].append(f"Java {jv} found; current Freerouting 2.x releases need Java 21+.")
    else:
        report["checks"]["java"] = {"error": "java not found (needed only for Freerouting)"}

    # --- freerouting jar
    jar = a.freerouting_jar
    if not jar:
        hits = sorted(glob.glob(str(HERE.parent / "tools" / "freerouting*.jar")) +
                      glob.glob(os.path.expanduser("~/freerouting*.jar")))
        jar = hits[-1] if hits else None
    report["checks"]["freerouting_jar"] = {"path": jar} if jar and os.path.exists(jar) else {
        "error": "no freerouting jar - download freerouting-<ver>.jar from "
                 "https://github.com/freerouting/freerouting/releases into kicad-routing/tools/ "
                 "or set FREEROUTING_JAR"}

    # --- KiCadRoutingTools
    krt = a.krt_dir
    if krt and (Path(krt) / "route.py").exists():
        report["checks"]["kicad_routing_tools"] = {"path": krt}
    else:
        report["checks"]["kicad_routing_tools"] = {
            "error": "not configured (optional, recommended for diff pairs / planes / fanout): "
                     "git clone https://github.com/drandyhaas/KiCadRoutingTools && python build_router.py; "
                     "then set KICAD_ROUTING_TOOLS"}

    if a.json:
        print(json.dumps(report, indent=2))
    else:
        for k, v in report["checks"].items():
            status = "MISSING" if "error" in v else "ok"
            print(f"[{status:7}] {k}: {v}")
        for line in report["advice"]:
            print("  -> " + line)
        print("\nREADY" if report["ok"] else "\nNOT READY (see above)")
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
