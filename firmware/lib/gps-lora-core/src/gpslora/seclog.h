// SPDX-License-Identifier: Apache-2.0
// Encrypted SD log records. Plain C++, unit-tested on the host.
//
// Each CSV record becomes one text line:
//
//   <counter, 8 hex digits>,<base64(AES-128-CCM ciphertext | 8-byte tag)>
//
// Nonce = counter | node | 'L'. One line per record keeps the file usable
// after a power cut: only the line being written can be damaged, and the
// decrypt tool (tools/gps_lora.py) reports it and moves on. Every line is
// authenticated: an altered or forged line fails to decrypt. Whole lines
// could still be deleted unnoticed (counter gaps are normal, since the
// counter is shared with radio packets).
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "crypto.h"

namespace seclog {

constexpr size_t MAX_PLAIN = 160;

// Encrypts plain (no newline) into out, including the trailing "\n".
// Returns the line length, or 0 if out is too small or plain too long.
size_t sealLine(const uint8_t logKey[crypto::KEY_SIZE], uint16_t node, uint32_t counter,
                const char *plain, char *out, size_t outSize);

// Inverse of sealLine (line may end in "\n"). Writes a NUL-terminated record
// to plain. False if the line is malformed or does not authenticate.
bool openLine(const uint8_t logKey[crypto::KEY_SIZE], uint16_t node, const char *line,
              char *plain, size_t plainSize);

}  // namespace seclog
