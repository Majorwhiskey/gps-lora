// SPDX-License-Identifier: Apache-2.0
// u-blox SAM-M10Q on UART1: configuration, NMEA parsing, PPS, recovery.
#pragma once

#include <TinyGPSPlus.h>

namespace gnss {

void begin();
void poll();  // Call every loop: feeds the parser and watches the link

TinyGPSPlus &fix();
bool linkAlive();       // Valid NMEA seen within GNSS_SILENT_MS
bool ppsRecent();       // TIMEPULSE edge within the last 1.5 s
uint32_t ppsCount();
uint32_t lastPpsMicros();

void softReset();       // UBX-CFG-RST, keeps orbit data (hot start)
void hardReset();       // RESET_N pulse. Clears BBR: forces a cold start

}  // namespace gnss
