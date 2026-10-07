// SPDX-License-Identifier: Apache-2.0
// System clock, kept in UTC. Set from GNSS whenever a fix carries a date,
// and from NTP while WiFi is up. Used for SD file timestamps.
#pragma once

#include <stdint.h>

#include <TinyGPSPlus.h>

namespace timekeeping {

void begin();                       // Installs the SD timestamp callback
void updateFromGnss(TinyGPSPlus &g);  // Call once per GNSS epoch
void startNtp();                    // Call once WiFi has an IP

bool valid();                       // Clock has been set from any source
const char *source();               // "gnss", "ntp" or "none"
uint32_t gnssUnixTime(TinyGPSPlus &g);  // 0 if the fix has no usable date

}  // namespace timekeeping
