#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Theoros key management and decryption.

Needs Python 3.9+ and the 'cryptography' package (pip install cryptography).

  new-master MASTER_FILE           create the master key (keep it secret!)
  provision MASTER_FILE NODE       console command for tracker NODE (e.g. ab12)
  provision MASTER_FILE receiver   console command for a receiver
  decrypt-log MASTER_FILE LOG.CSV  decrypt a tracker's SD log to CSV on stdout
  decode MASTER_FILE HEX...        decrypt captured LoRa packets
  self-test < vectors.json         cross-check the firmware (make -C firmware/tests)

Keys are read from a file rather than the command line so they don't end up
in shell history. Key hierarchy and formats: docs/SECURITY.md.
"""

import base64
import json
import os
import struct
import sys
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SALT = b"theoros"
TAG = 8
HEADER = struct.Struct("<BHI")             # version, node, counter
BODY = struct.Struct("<IiihHBBB")          # time, lat, lon, alt, speed, sats, hdop, flags
PACKET_VERSION = 2
PACKET_SIZE = HEADER.size + BODY.size + TAG  # 34
FLAG_FIX_VALID, FLAG_SD_LOG, FLAG_PPS = 0x01, 0x02, 0x04
LOG_MAGIC = "# theoros encrypted log v1"
LOG_COLUMNS = "utc_date,utc_time,lat,lon,alt_m,speed_kmh,course_deg,sats,hdop"


# --- Keys (mirror of keys.cpp) ---

def hkdf(ikm: bytes, info: bytes, length: int = 16) -> bytes:
    return HKDF(hashes.SHA256(), length, SALT, info).derive(ikm)


def device_key(master: bytes, node: int) -> bytes:
    return hkdf(master, b"device v1" + struct.pack("<H", node))


def radio_key(device: bytes) -> bytes:
    return hkdf(device, b"radio v1")


def log_key(device: bytes) -> bytes:
    return hkdf(device, b"log v1")


def fingerprint(key: bytes) -> str:
    return hkdf(key, b"fingerprint v1", 4).hex()


def nonce(counter: int, node: int, domain: bytes) -> bytes:
    return struct.pack("<IH", counter, node) + domain + bytes(6)


def read_master(path: str) -> bytes:
    with open(path) as f:
        key = bytes.fromhex(f.read().strip())
    if len(key) != 16:
        sys.exit(f"{path}: expected 32 hex digits (a 128-bit key)")
    return key


# --- Packets (mirror of packet.cpp) ---

def open_packet(master: bytes, data: bytes) -> dict:
    if len(data) != PACKET_SIZE or data[0] != PACKET_VERSION:
        raise ValueError(f"not a v{PACKET_VERSION} packet ({len(data)} bytes)")
    _, node, counter = HEADER.unpack_from(data)
    key = radio_key(device_key(master, node))
    body = AESCCM(key, TAG).decrypt(nonce(counter, node, b"R"),
                                    data[HEADER.size:], data[:HEADER.size])
    t, lat, lon, alt, speed, sats, hdop, flags = BODY.unpack(body)
    fix = bool(flags & FLAG_FIX_VALID)
    return {
        "node": f"{node:04x}", "counter": counter, "unix_time": t,
        "time": datetime.fromtimestamp(t, timezone.utc).isoformat() if t else None,
        "fix": fix,
        "lat": lat / 1e7 if fix else None, "lon": lon / 1e7 if fix else None,
        "alt_m": alt if fix else None, "speed_kmh": speed / 10 if fix else None,
        "sats": sats, "hdop": hdop / 10,
        "sd_logging": bool(flags & FLAG_SD_LOG), "pps": bool(flags & FLAG_PPS),
    }


# --- Log lines (mirror of seclog.cpp) ---

def open_log_line(key: bytes, node: int, line: str) -> str:
    ctr_hex, _, b64 = line.strip().partition(",")
    if len(ctr_hex) != 8:
        raise ValueError("malformed line")
    blob = base64.b64decode(b64, validate=True)
    pt = AESCCM(key, TAG).decrypt(nonce(int(ctr_hex, 16), node, b"L"), blob, None)
    return pt.decode()


def seal_log_line(key: bytes, node: int, counter: int, plain: str) -> str:
    ct = AESCCM(key, TAG).encrypt(nonce(counter, node, b"L"), plain.encode(), None)
    return f"{counter:08x},{base64.b64encode(ct).decode()}"


# --- Commands ---

def cmd_new_master(path: str) -> None:
    if os.path.exists(path):
        sys.exit(f"{path} exists; refusing to overwrite a master key")
    key = os.urandom(16)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key.hex() + "\n")
    print(f"master key written to {path} (fingerprint {fingerprint(key)})")
    print("Keep it offline and backed up: without it, logs and packets cannot be read.")


def cmd_provision(path: str, target: str) -> None:
    master = read_master(path)
    if target == "receiver":
        print(f"# receiver, master key fingerprint {fingerprint(master)}")
        print(f"key set {master.hex()}")
        return
    node = int(target, 16)
    dev = device_key(master, node)
    print(f"# tracker {node:04x}, device key fingerprint {fingerprint(dev)}")
    print(f"key set {dev.hex()}")


def cmd_decrypt_log(path: str, log_path: str) -> None:
    master = read_master(path)
    with open(log_path) as f:
        lines = f.read().splitlines()
    if not lines or not lines[0].startswith(LOG_MAGIC):
        sys.exit(f"{log_path}: not an encrypted theoros log")
    fields = dict(kv.split("=", 1) for kv in lines[0][len(LOG_MAGIC):].split() if "=" in kv)
    node = int(fields["node"], 16)
    dev = device_key(master, node)
    if fields.get("key") and fields["key"] != fingerprint(dev):
        sys.exit(f"{log_path}: written with key {fields['key']}, but this master gives "
                 f"{fingerprint(dev)} for node {node:04x}. Wrong master file?")
    key = log_key(dev)
    print(LOG_COLUMNS)
    bad = 0
    last = -1
    for n, line in enumerate(lines[1:], start=2):
        if not line or line.startswith("#"):
            continue
        try:
            record = open_log_line(key, node, line)
        except (ValueError, InvalidTag):
            bad += 1
            print(f"{log_path}:{n}: damaged or altered line skipped", file=sys.stderr)
            continue
        # Authentic but out of order: the firmware's counter only increases,
        # so this line was copied or moved after it was written.
        counter = int(line[:8], 16)
        if counter <= last:
            bad += 1
            print(f"{log_path}:{n}: duplicated or reordered line skipped", file=sys.stderr)
            continue
        last = counter
        print(record)
    if bad:
        print(f"{bad} line(s) skipped (a power cut damages at most the last one)",
              file=sys.stderr)


def cmd_decode(path: str, hexes: list) -> None:
    master = read_master(path)
    for h in hexes:
        try:
            print(json.dumps(open_packet(master, bytes.fromhex(h))))
        except (ValueError, InvalidTag) as e:
            print(json.dumps({"error": str(e) or "authentication failed", "hex": h}))


def cmd_self_test() -> None:
    """Re-derives and re-encrypts the C++ test vectors independently."""
    v = json.load(sys.stdin)
    master, node, ctr = bytes.fromhex(v["master"]), v["node"], v["counter"]
    dev = device_key(master, node)
    checks = {
        "device key": dev.hex() == v["device_key"],
        "radio key": radio_key(dev).hex() == v["radio_key"],
        "log key": log_key(dev).hex() == v["log_key"],
        "fingerprint": fingerprint(dev) == v["fingerprint"],
    }
    p = open_packet(master, bytes.fromhex(v["packet"]))
    checks["packet decrypts"] = (p["counter"] == ctr and p["lat"] == 12.9715987 and
                                 p["lon"] == -77.5945627 and p["alt_m"] == -12 and
                                 p["speed_kmh"] == 123.4 and p["sats"] == 14 and
                                 p["hdop"] == 0.8 and p["pps"] and not p["sd_logging"] and
                                 p["time"] == "2026-10-07T09:12:44+00:00")
    # CCM is deterministic for a given nonce: re-encrypting must reproduce
    # the firmware's packet byte for byte.
    hdr = HEADER.pack(PACKET_VERSION, node, ctr)
    body = BODY.pack(1791364364, 129715987, -775945627, -12, 1234, 14, 8,
                     FLAG_FIX_VALID | FLAG_PPS)
    ours = hdr + AESCCM(radio_key(dev), TAG).encrypt(nonce(ctr, node, b"R"), body, hdr)
    checks["packet bytes"] = ours.hex() == v["packet"]
    lk = log_key(dev)
    checks["log decrypts"] = open_log_line(lk, node, v["log_line"]) == v["log_plain"]
    checks["log bytes"] = seal_log_line(lk, node, ctr, v["log_plain"]) == v["log_line"]
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        sys.exit("theoros.py self-test FAILED: " + ", ".join(bad))
    print(f"theoros.py: self-test passed ({len(checks)} checks against Python cryptography)")


def main() -> None:
    a = sys.argv[1:]
    if a[:1] == ["new-master"] and len(a) == 2:
        cmd_new_master(a[1])
    elif a[:1] == ["provision"] and len(a) == 3:
        cmd_provision(a[1], a[2])
    elif a[:1] == ["decrypt-log"] and len(a) == 3:
        cmd_decrypt_log(a[1], a[2])
    elif a[:1] == ["decode"] and len(a) >= 3:
        cmd_decode(a[1], a[2:])
    elif a == ["self-test"]:
        cmd_self_test()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
