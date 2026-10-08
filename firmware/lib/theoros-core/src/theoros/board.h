// SPDX-License-Identifier: Apache-2.0
// Pin map for the Theoros board, rev V1.0.
// Checked against the schematic netlist (U301 pins) on 2026-10-07.
// Source of truth: docs/PCB_DESIGN.md, "Pin assignment".
#pragma once

#include <stdint.h>

// GNSS, u-blox SAM-M10Q on UART1. 100 ohm series resistors on both lines.
constexpr int PIN_GNSS_TX      = 17;  // ESP32 TX -> GNSS RXD
constexpr int PIN_GNSS_RX      = 18;  // GNSS TXD -> ESP32 RX
constexpr int PIN_GNSS_PPS     = 15;  // TIMEPULSE. Input, no pull-down: low at
                                      // power-up puts the receiver in safe boot.
constexpr int PIN_GNSS_RESET_N = 7;   // Open drain, recovery only (cold start)

// OLED, bare SSD1306 panel on I2C. 4.7k pull-ups on the board.
constexpr int     PIN_OLED_SDA  = 8;
constexpr int     PIN_OLED_SCL  = 9;
constexpr int     PIN_OLED_RES  = 41;  // RES#, 10k pull-up
constexpr uint8_t OLED_I2C_ADDR = 0x3C;  // D/C# (SA0) tied to GND on J502.15

// microSD on SPI2 (FSPI) IO_MUX pins. 47k pull-ups on CS, MISO, DAT1, DAT2.
constexpr int PIN_SD_CS   = 10;
constexpr int PIN_SD_MOSI = 11;
constexpr int PIN_SD_SCK  = 12;
constexpr int PIN_SD_MISO = 13;

// LoRa, HopeRF RFM95W-868S2 (SX1276) on SPI3 (HSPI).
constexpr int PIN_LORA_NSS   = 14;
constexpr int PIN_LORA_MOSI  = 47;
constexpr int PIN_LORA_SCK   = 16;
constexpr int PIN_LORA_MISO  = 21;
constexpr int PIN_LORA_RESET = 48;  // Only ever low or high-Z, never driven high
constexpr int PIN_LORA_DIO0  = 1;
constexpr int PIN_LORA_DIO1  = 42;

// Misc
constexpr int PIN_EJECT_BTN  = 4;  // To GND, no external pull-up
constexpr int PIN_LED        = 2;  // Green, active high
constexpr int PIN_VBUS_SENSE = 5;  // 10k/15k divider from VBUS, ~3.0 V present

// Do not touch: 0, 3, 45, 46 (strapping), 19/20 (USB), 26-37 (flash/PSRAM),
// 38-40 (driven in USB download mode), 43/44 (UART0 console).
