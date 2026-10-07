// SPDX-License-Identifier: Apache-2.0
// Tunable settings. Hardware facts live in board.h.
#pragma once

#include <stdint.h>

#define FW_VERSION "0.2.0-dev"

// GNSS
constexpr uint32_t GNSS_BAUD_DEFAULT = 9600;    // Receiver default (SAM-DS Table 18)
constexpr uint32_t GNSS_BAUD         = 115200;  // Set in RAM layer at every boot
constexpr uint32_t GNSS_SILENT_MS    = 3000;    // No NMEA for this long = link lost
constexpr uint8_t  GNSS_RETRIES_BEFORE_HW_RESET = 3;

// Logging
constexpr float    LOG_MAX_HDOP     = 5.0f;   // Reject fixes worse than this
constexpr uint32_t LOG_MAX_FIX_AGE  = 1500;   // ms
constexpr uint32_t SD_SPI_HZ        = 10000000;  // Kept low for EMC (PCB_DESIGN, EMC)
constexpr uint32_t SD_RETRY_MS      = 5000;
constexpr uint32_t EJECT_HOLD_MS    = 1000;

// LoRa. India delicensed band is 865-867 MHz; set these for your region.
constexpr float    LORA_FREQ_MHZ    = 866.0f;
constexpr float    LORA_BW_KHZ      = 125.0f;
constexpr uint8_t  LORA_SF          = 9;
constexpr uint8_t  LORA_CR          = 5;      // 4/5
constexpr uint8_t  LORA_SYNC_WORD   = 0x12;   // Private network
constexpr int8_t   LORA_POWER_DBM   = 14;     // PA_BOOST, 2..17 or 20
constexpr uint32_t LORA_SPI_HZ      = 8000000;  // Module max 10 MHz (RFM Table 10)
constexpr uint32_t LORA_INTERVAL_MS = 10000;

// RFM95W: +20 dBm only at <=1% duty cycle; up to +17 dBm continuous
// (RFM Tables 33-34). Below that we still cap airtime at 10% by choice.
constexpr float LORA_MAX_DUTY = (LORA_POWER_DBM > 17) ? 0.01f : 0.10f;

static_assert((LORA_POWER_DBM >= 2 && LORA_POWER_DBM <= 17) || LORA_POWER_DBM == 20,
              "SX1276 PA_BOOST supports 2..17 dBm or 20 dBm");
// Each log record (1/s) and each packet uses one message counter value. The
// counter's restart-after-flash-erase guarantee assumes fewer than 4 per
// second in total (security.cpp, COUNTER_RATE; docs/SECURITY.md).
static_assert(1000.0f + 1000000.0f / LORA_INTERVAL_MS < 4000.0f,
              "LoRa interval too short for the message counter budget");
static_assert(LORA_FREQ_MHZ >= 865.0f && LORA_FREQ_MHZ <= 867.0f,
              "Outside India's 865-867 MHz band; change this check for your region");

// WiFi service mode (LoRa TX paused while on)
constexpr uint32_t WIFI_CONNECT_TIMEOUT_MS = 30000;
constexpr uint32_t WIFI_IDLE_OFF_MS        = 10 * 60 * 1000;  // No web request

// A new OTA image must run this long before it is marked good. A crash or
// watchdog reset before then rolls back to the previous image.
constexpr uint32_t OTA_CONFIRM_MS = 60000;

// Display
constexpr uint32_t DISPLAY_PERIOD_MS = 500;
