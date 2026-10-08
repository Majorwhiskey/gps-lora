// SPDX-License-Identifier: Apache-2.0
// Device-side security: key storage, power-on self-test, the message
// counter, and the receiver's replay protection. See keys.h for the key
// hierarchy and firmware/README.md, "Security", for the threat model.
//
// The one key slot holds the tracker's device key, or the receiver's master
// key. Without a key the tracker does not transmit at all and logs plaintext;
// the receiver cannot read packets.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "packet.h"

namespace security {

void begin(uint16_t node);  // Self-test and key load. Call before storage/LoRa
bool ready();               // Self-test passed and a key is installed
bool selfTestPassed();
const char *keyFingerprint();  // 8 hex digits, or "none"

// Console. Validates 32 hex digits; the caller reboots to apply.
bool setKey(const char *hex);
void clearKey();

// --- Tracker ---
// Next message counter. Never repeats, also across reboots and a flash
// erase (see security.cpp). False while it cannot guarantee that yet: on a
// board with no stored counter, until the clock has been set from GNSS/NTP.
bool nextCounter(uint32_t &out);
const uint8_t *radioKey();  // nullptr unless ready()
const uint8_t *logKey();

// --- Receiver ---
enum class Rx : uint8_t { Ok, NoKey, Malformed, BadAuth, Replay, Stale };
Rx openPacket(const uint8_t *data, size_t len, packet::Header &h, packet::Position &p);
const char *rxName(Rx r);
uint32_t rejectedCount();

}  // namespace security
