// SPDX-License-Identifier: Apache-2.0
// WiFi service mode: web page for status, log download and OTA update.
//
// WiFi is off by default and switched on on demand (eject button short press
// or the console). In the tracker role LoRa transmit is paused for as long as
// WiFi is on: the supply budget forbids WiFi and LoRa transmitting together
// (PCB_DESIGN, supply requirement), and the WiFi driver transmits whenever it
// likes, so mutually exclusive modes are the only interlock that holds.
// WiFi turns itself off after WIFI_IDLE_OFF_MS without a web request.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace net {

void begin();     // Creates the network task; WiFi stays off
void start();     // Request WiFi on
void stop();      // Request WiFi off
void toggle();

bool radioOn();   // WiFi radio is (or may be) on: block LoRa TX
bool connected();
void statusText(char *out, size_t n);  // Short, for the OLED and console

bool rebootRequested();  // Set after a successful OTA upload

}  // namespace net
