"""Shared helpers for the kicad-routing skill scripts.

All pcbnew-dependent scripts must be run with a Python interpreter that can
`import pcbnew` (KiCad's bundled Python on Windows/macOS, system python3 on
most Linux installs). Run `doctor.py` to find it.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import shutil
import sys
from pathlib import Path

KICAD_PYTHON_HINTS = {
    "win32": [
        r"C:\Program Files\KiCad\10.0\bin\python.exe",
        r"C:\Program Files\KiCad\9.0\bin\python.exe",
    ],
    "darwin": [
        "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
    ],
    "linux": ["/usr/bin/python3"],
}


def import_pcbnew():
    """Import pcbnew or exit with an actionable message."""
    try:
        import pcbnew  # noqa: F401
        return pcbnew
    except ImportError:
        hints = KICAD_PYTHON_HINTS.get(sys.platform if sys.platform != "linux2" else "linux",
                                       KICAD_PYTHON_HINTS["linux"])
        sys.stderr.write(
            "ERROR: cannot import pcbnew with this interpreter (%s).\n"
            "Run this script with KiCad's Python, e.g.:\n  %s\n"
            "Run scripts/doctor.py to locate it automatically.\n"
            % (sys.executable, "\n  ".join(hints))
        )
        sys.exit(2)


def kicad_version(pcbnew) -> str:
    for attr in ("FullVersion", "GetBuildVersion", "Version"):
        fn = getattr(pcbnew, attr, None)
        if fn:
            try:
                return str(fn())
            except Exception:
                pass
    return "unknown"


def kicad_major(pcbnew) -> int:
    v = kicad_version(pcbnew)
    digits = ""
    for ch in v.lstrip("(v "):
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else 0


# ---------------------------------------------------------------- units
def mm(pcbnew, value_iu) -> float:
    return round(pcbnew.ToMM(value_iu), 4)


def iu(pcbnew, value_mm) -> int:
    return int(pcbnew.FromMM(float(value_mm)))


def vec(pcbnew, x_mm, y_mm):
    ctor = getattr(pcbnew, "VECTOR2I", None) or getattr(pcbnew, "wxPoint")
    return ctor(iu(pcbnew, x_mm), iu(pcbnew, y_mm))


def xy_mm(pcbnew, point):
    return [mm(pcbnew, point.x), mm(pcbnew, point.y)]


# ---------------------------------------------------------------- files
def backup(path: str | Path, tag: str = "bak") -> Path:
    """Copy the board (and .kicad_pro / .kicad_dru siblings) to a timestamped backup folder."""
    path = Path(path)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    dest_dir = path.parent / ".routing_backups" / f"{stamp}-{tag}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for sibling in (path, path.with_suffix(".kicad_pro"), path.with_suffix(".kicad_dru")):
        if sibling.exists():
            shutil.copy2(sibling, dest_dir / sibling.name)
    return dest_dir


def load_board(pcbnew, path: str | Path):
    path = str(Path(path).resolve())
    if not os.path.exists(path):
        sys.exit(f"ERROR: board not found: {path}")
    lock = Path(path).parent / ("~" + Path(path).name + ".lck")
    if lock.exists():
        sys.stderr.write(
            f"WARNING: {lock.name} exists - the board may be open in the KiCad GUI. "
            "Close it before scripting, or edits will be overwritten / lost.\n")
    return pcbnew.LoadBoard(path)


def save_board(pcbnew, board, path: str | Path):
    path = str(Path(path).resolve())
    ok = pcbnew.SaveBoard(path, board)
    if ok is False:
        sys.exit(f"ERROR: SaveBoard failed for {path}")
    return path


def write_json(obj, path: str | Path | None):
    text = json.dumps(obj, indent=2, sort_keys=False, default=str)
    if path:
        Path(path).write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------- board helpers
def layer_id(pcbnew, board, name: str) -> int:
    lid = board.GetLayerID(name)
    if lid < 0:
        sys.exit(f"ERROR: unknown layer '{name}'")
    return lid


def copper_layer_names(pcbnew, board) -> list[str]:
    names = []
    for lid in board.GetEnabledLayers().CuStack():
        names.append(board.GetLayerName(lid))
    return names


def find_net(board, name: str):
    net = board.FindNet(name)
    if net is None or net.GetNetCode() <= 0:
        # Try with/without leading '/', a common source of mismatches
        alt = name[1:] if name.startswith("/") else "/" + name
        net = board.FindNet(alt)
    if net is None or net.GetNetCode() <= 0:
        sys.exit(f"ERROR: net '{name}' not found on board")
    return net


def set_via_size(pcbnew, via, diameter_iu: int, drill_iu: int):
    """Set via diameter across KiCad 7-10 API differences (padstacks arrived in 9)."""
    via.SetDrill(drill_iu)
    try:
        via.SetWidth(diameter_iu)
        return
    except TypeError:
        pass
    # KiCad 9+: SetWidth(width, layer)
    via.SetWidth(diameter_iu, pcbnew.F_Cu)
    try:
        via.SetWidth(diameter_iu, pcbnew.B_Cu)
    except Exception:
        pass


def via_diameter(pcbnew, via) -> int:
    try:
        return via.GetWidth()
    except TypeError:
        return via.GetWidth(pcbnew.F_Cu)


def is_via(pcbnew, item) -> bool:
    return item.GetClass() in ("PCB_VIA", "VIA") or isinstance(item, getattr(pcbnew, "PCB_VIA", ()))


def is_arc(item) -> bool:
    return item.GetClass() in ("PCB_ARC", "ARC")


def seg_angle_deg(ax, ay, bx, by) -> float:
    return math.degrees(math.atan2(by - ay, bx - ax))


def all_tracks(board) -> list:
    """board.GetTracks() that tolerates an empty track list (raises TypeError on some SWIG builds)."""
    try:
        return list(board.GetTracks())
    except TypeError:
        return []
