// SPDX-License-Identifier: Apache-2.0
// Persistent settings in NVS, set from the USB serial console.
// Stored in plain text: flash encryption is not enabled on this board.
#pragma once

#include <Arduino.h>

namespace settings {

void begin();

String wifiSsid();
String wifiPass();
String webPass();

void setWifiSsid(const String &v);
void setWifiPass(const String &v);
void setWebPass(const String &v);

}  // namespace settings
