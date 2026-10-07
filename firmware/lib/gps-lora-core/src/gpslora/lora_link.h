// SPDX-License-Identifier: Apache-2.0
// RFM95W (SX1276) via RadioLib on SPI3: a byte transport. It only ever sees
// sealed packets; encryption is in packet.* and security.*.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace lora_link {

bool begin();
void service();  // Call every loop: completes TX, collects RX

// Tracker. canSend() is false while the radio is busy, absent or the
// duty-cycle limit says wait; check it before spending a message counter.
bool canSend();
bool send(const uint8_t *data, size_t len);  // False if !canSend() or TX fails
bool transmitting();  // TX in progress (read from other tasks)

// Receiver
bool startReceive();
struct Frame {
  uint8_t data[64];
  size_t len;
  float rssi;
  float snr;
};
bool takeFrame(Frame &out);  // True once per frame with a valid LoRa CRC

bool ready();
uint16_t nodeId();
uint32_t sentCount();
uint32_t frameCount();   // Frames with a valid LoRa CRC
uint32_t crcErrors();
uint32_t lastAirtimeMs();

}  // namespace lora_link
