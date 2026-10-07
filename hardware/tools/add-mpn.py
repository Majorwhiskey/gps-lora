#!/usr/bin/env python3
"""Add/refresh hidden "MPN" and "Manufacturer" fields on every schematic symbol.

Specific parts come from docs/PCB_DESIGN.md "Selected parts". Generic passives are
widely stocked equivalents (verify stock with the assembler before ordering).
Re-runnable: existing MPN/Manufacturer fields are replaced.
"""
import re
import sys
from pathlib import Path

HW = Path(__file__).resolve().parent.parent

# (Value, footprint-substring) -> (Manufacturer, MPN); footprint substring "" matches any.
BY_VALUE = {
    # resistors, 0402 1% (0R: jumper)
    ("5.1k", "R_0402"): ("Yageo", "RC0402FR-075K1L"),
    ("1M", "R_0402"): ("Yageo", "RC0402FR-071ML"),
    ("10k", "R_0402"): ("Yageo", "RC0402FR-0710KL"),
    ("15k", "R_0402"): ("Yageo", "RC0402FR-0715KL"),
    ("1k", "R_0402"): ("Yageo", "RC0402FR-071KL"),
    ("0R", "R_0402"): ("Yageo", "RC0402JR-070RL"),
    ("499R", "R_0402"): ("Yageo", "RC0402FR-07499RL"),
    ("100R", "R_0402"): ("Yageo", "RC0402FR-07100RL"),
    ("47k", "R_0402"): ("Yageo", "RC0402FR-0747KL"),
    ("4.7k", "R_0402"): ("Yageo", "RC0402FR-074K7L"),
    ("390k", "R_0402"): ("Yageo", "RC0402FR-07390KL"),
    ("59k", "R_0402"): ("Yageo", "RC0402FR-0759KL"),
    ("0R", "R_0805"): ("Yageo", "RC0805JR-070RL"),
    # capacitors
    ("4.7nF", "C_0402"): ("Murata", "GRM155R71H472KA01D"),      # 50V X7R, USB shield
    ("100nF", "C_0402"): ("Samsung", "CL05B104KO5NNNC"),        # 16V X7R
    ("1uF", "C_0402"): ("Samsung", "CL05A105KA5NQNC"),          # 25V X5R
    ("22uF", "C_0805"): ("Samsung", "CL21A226MAQNNNE"),         # 25V X5R
    ("10uF", "C_0805"): ("Samsung", "CL21A106KAYNNNE"),         # 25V X5R
    ("100uF", "C_1210"): ("Murata", "GRM32ER61A107ME20L"),      # 10V X5R
    ("2.2uF", "C_0603"): ("Murata", "GRM188R61E225KA12D"),      # 25V X5R, OLED VCC (>=16V)
    ("4.7uF", "C_0603"): ("TDK", "C1608X7R1C475K080AC"),        # 16V X7R, OLED VCOMH (X7R per panel)
    ("0.22F 3.3V", ""): ("Elna", "DSK-3R3H224U-HL"),
    # semiconductors / modules / connectors (docs/PCB_DESIGN.md "Selected parts")
    ("SMF5.0A", ""): ("Littelfuse", "SMF5.0A"),
    ("Green", "LED_0603"): ("Lite-On", "LTST-C191KGKT"),
    ("BAT54", "SOD-323"): ("Diodes Inc", "BAT54WS-7-F"),
    ("Schottky", "D_SMA"): ("Diodes Inc", "B340A-13-F"),
    ("0.75A PTC", ""): ("Littelfuse", "1206L075THYR"),
    ("TYPE-C-31-M-12", ""): ("Korean Hroparts (HRO)", "TYPE-C-31-M-12"),
    ("U.FL", ""): ("Hirose", "U.FL-R-SMT-1(10)"),
    ("DM3AT-SF-PEJM5", ""): ("Hirose", "DM3AT-SF-PEJM5"),
    ("FH12-30S-0.5SH(55)", ""): ("Hirose", "FH12-30S-0.5SH(55)"),
    ("RESET", "PTS810"): ("C&K", "PTS810 SJM 250 SMTR LFS"),
    ("BOOT", "PTS810"): ("C&K", "PTS810 SJM 250 SMTR LFS"),
    ("EJECT", "PTS810"): ("C&K", "PTS810 SJM 250 SMTR LFS"),
    ("USBLC6-2SC6", ""): ("STMicroelectronics", "USBLC6-2SC6"),
    ("AP7361C-33E", ""): ("Diodes Inc", "AP7361C-33E-13"),
    ("ESP32-S3-WROOM-1-N8", ""): ("Espressif", "ESP32-S3-WROOM-1-N8"),
    ("MCP120T-300I/TT", ""): ("Microchip", "MCP120T-300I/TT"),
    ("SAM-M10Q", ""): ("u-blox", "SAM-M10Q-00B"),
    ("RFM95W-868S2", ""): ("HopeRF", "RFM95W-868S2"),
    ("TLV75801PDBV", ""): ("Texas Instruments", "TLV75801PDBVR"),
    ("ER-OLED0.96-1.1W", ""): ("EastRising (BuyDisplay)", "ER-OLED0.96-1.1W"),
}
# 2200uF holdup capacitor (DNP, holdup option): value chosen with that option.
SKIP = {"TestPoint", "SAFEBOOT", "VBAT", "DNP", "2200uF", "MountingHole_Pad", "Fiducial", "TC2030-NL"}


def lookup(value, footprint):
    for (v, fp), mm in BY_VALUE.items():
        if v == value and fp in footprint:
            return mm
    return None


def prop(name, val, x, y, ind="\t\t"):
    return (f'{ind}(property "{name}" "{val}"\n{ind}\t(at {x} {y} 0)\n{ind}\t(hide yes)\n'
            f'{ind}\t(show_name no)\n{ind}\t(do_not_autoplace no)\n{ind}\t(effects\n'
            f'{ind}\t\t(font\n{ind}\t\t\t(size 1.27 1.27)\n{ind}\t\t)\n{ind}\t)\n{ind})\n')


def process(path: Path, missing: list):
    s = path.read_text()
    ls = s.find("(lib_symbols")
    le = s.find("\n\t)\n", ls) + 4
    head, body = s[:le], s[le:]
    out, pos, n = [], 0, 0
    for m in re.finditer(r"\n\t\(symbol\n.*?\n\t\)", body, re.S):
        blk = m.group(0)
        out.append(body[pos:m.start()])
        pos = m.end()
        lib = re.search(r'\(lib_id "([^"]+)"', blk).group(1)
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk)
        if lib.startswith("power:") or not ref:
            out.append(blk); continue
        val = re.search(r'\(property "Value" "([^"]*)"', blk).group(1)
        fp = re.search(r'\(property "Footprint" "([^"]*)"', blk).group(1)
        # drop old fields
        blk = re.sub(r'\n\t\t\(property "(MPN|Manufacturer)" .*?\n\t\t\)', "", blk, flags=re.S)
        mm = lookup(val, fp)
        if mm is None:
            if val not in SKIP:
                missing.append(f"{ref.group(1)} {val} {fp}")
            out.append(blk); continue
        at = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", blk)
        x, y = at.group(1), at.group(2)
        anchor = blk.find('\n\t\t(property "Description"')
        anchor = blk.find("\n\t\t)\n", anchor) + 5 if anchor > 0 else blk.find("\n\t\t(pin ")
        blk = blk[:anchor] + prop("Manufacturer", mm[0], x, y) + prop("MPN", mm[1], x, y) + blk[anchor:]
        out.append(blk); n += 1
    out.append(body[pos:])
    path.write_text(head + "".join(out))
    return n


if __name__ == "__main__":
    missing = []
    for p in sorted(HW.glob("*.kicad_sch")):
        n = process(p, missing)
        print(f"{p.name}: {n} symbol(s) tagged")
    if missing:
        print("no MPN mapping for:", *missing, sep="\n  ")
        sys.exit(1)
