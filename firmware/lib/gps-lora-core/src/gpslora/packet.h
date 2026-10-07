// SPDX-License-Identifier: Apache-2.0
// LoRa position packet, version 2: AES-128-CCM authenticated encryption.
// Plain C++, no Arduino dependencies, unit-tested on the host
// (firmware/tests). Format table in firmware/README.md.
//
//   [ver 1][node 2][counter 4]   header: in clear, authenticated (CCM AAD)
//   [body 19]                    encrypted Position
//   [tag 8]                      CCM authentication tag
//
// Nonce = counter | node | 'R' (crypto::makeNonce). The counter never
// repeats for a tracker (security.cpp persists it), and the receiver rejects
// counters it has already seen, which stops replays.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "crypto.h"

namespace packet {

constexpr uint8_t VERSION = 2;
constexpr size_t HEADER_SIZE = 7;
constexpr size_t BODY_SIZE = 19;
constexpr size_t SIZE = HEADER_SIZE + BODY_SIZE + crypto::TAG_SIZE;  // 34

constexpr uint8_t FLAG_FIX_VALID = 0x01;
constexpr uint8_t FLAG_SD_LOG    = 0x02;
constexpr uint8_t FLAG_PPS       = 0x04;

struct Header {
  uint16_t node = 0;
  uint32_t counter = 0;
};

struct Position {
  uint32_t unixTime = 0;     // 0 = unknown
  int32_t latE7 = 0;         // 1e-7 degrees
  int32_t lonE7 = 0;
  int16_t altM = 0;
  uint16_t speedDkmh = 0;    // 0.1 km/h
  uint8_t sats = 0;
  uint8_t hdopX10 = 0;       // Saturates at 255
  uint8_t flags = 0;
};

// Encrypts into out[SIZE]. Returns SIZE, or 0 on failure.
size_t seal(const uint8_t radioKey[crypto::KEY_SIZE], const Header &h, const Position &p,
            uint8_t out[SIZE]);

// Parses the clear header only, so the receiver can pick the tracker's key.
// False if the length or version is wrong. Nothing here is trusted yet.
bool readHeader(const uint8_t *in, size_t len, Header &h);

// Verifies and decrypts. False if anything was altered or the key is wrong;
// p is then left zeroed.
bool open(const uint8_t radioKey[crypto::KEY_SIZE], const uint8_t *in, size_t len, Header &h,
          Position &p);

}  // namespace packet
