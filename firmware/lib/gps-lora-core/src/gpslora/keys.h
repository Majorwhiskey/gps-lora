// SPDX-License-Identifier: Apache-2.0
// Key hierarchy, all HKDF-SHA256 with salt "gps-lora":
//
//   master (16 B, receiver only, generated on a PC)
//     └ device key = HKDF(master, "device v1" | node)   one per tracker
//         ├ radio key = HKDF(device, "radio v1")          LoRa packets
//         └ log key   = HKDF(device, "log v1")            SD log records
//
// A tracker holds only its own device key, so a captured tracker exposes
// that tracker's data and nothing else. tools/gps_lora.py derives the same
// keys on a PC.
#pragma once

#include <stdint.h>

#include "crypto.h"

namespace keys {

using Key = uint8_t[crypto::KEY_SIZE];

bool deviceKey(const Key master, uint16_t node, Key out);
bool radioKey(const Key device, Key out);
bool logKey(const Key device, Key out);

// Public 32-bit identifier of a key, safe to display: lets you check which
// key a board holds without revealing it.
uint32_t fingerprint(const Key k);

}  // namespace keys
