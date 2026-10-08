// SPDX-License-Identifier: Apache-2.0
// Copies of live state for readers outside the main loop's logic (display,
// web task). TinyGPSPlus is not safe to read from another task, and reading
// its values clears the "updated" flags the logger depends on.
#pragma once

#include <stdint.h>

#include "packet.h"

namespace snapshot {

struct Gnss {
  uint32_t epochMs = 0;  // millis() when published, 0 = never
  bool fix = false;      // Passed the logging criteria (HDOP, age)
  bool timeValid = false;
  uint8_t hour = 0, minute = 0, second = 0;
  uint32_t unixTime = 0;  // 0 if the fix carries no usable date
  uint32_t sats = 0;
  float hdop = 0;
  double lat = 0, lon = 0;
  float altM = 0, speedKmh = 0, courseDeg = 0;
};

// Last authenticated, decrypted packet (receiver).
struct Rx {
  uint32_t atMs = 0;  // millis() when received, 0 = never
  packet::Header hdr;
  packet::Position pos;
  float rssi = 0;
  float snr = 0;
};

void publishGnss(const Gnss &g);
Gnss gnss();
bool fixFresh(const Gnss &g);  // Fix and published within the last 2.5 s

void publishRx(const Rx &r);
Rx rx();

}  // namespace snapshot
