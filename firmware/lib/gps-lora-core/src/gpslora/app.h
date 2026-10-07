// SPDX-License-Identifier: Apache-2.0
// Runtime shared by the tracker and receiver firmware: start-up, GNSS epoch
// handling, SD, console, eject button, VBUS sense, status LED, display,
// watchdog and OTA confirmation. Each sketch adds only its own role logic.
#pragma once

#include <TinyGPSPlus.h>

#include "role.h"

namespace app {

// Called once per GNSS epoch, after the snapshot has been published.
// usable: the fix passes the logging criteria (HDOP, age, date).
using EpochHandler = void (*)(TinyGPSPlus &g, bool usable);

// Returns the SD file's header. Called after security::begin(), so it can
// depend on whether a key is installed.
using HeaderFn = const char *(*)();

// logPrefix: SD file name prefix ("LOG", "RX").
void begin(role::Role r, const char *logPrefix, HeaderFn logHeader, EpochHandler onEpoch);
void service();  // Call first in every loop()

void ledBlip(uint32_t ms);  // Status LED: one record written

}  // namespace app
