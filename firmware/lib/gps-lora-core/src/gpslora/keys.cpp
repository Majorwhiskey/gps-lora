// SPDX-License-Identifier: Apache-2.0
#include "keys.h"

#include <string.h>

namespace keys {
namespace {

const uint8_t SALT[] = {'g', 'p', 's', '-', 'l', 'o', 'r', 'a'};

bool derive(const Key ikm, const char *label, const uint8_t *extra, size_t extraLen,
            uint8_t *out, size_t outLen) {
  uint8_t info[32];
  size_t n = strlen(label);
  if (n + extraLen > sizeof(info)) return false;
  memcpy(info, label, n);
  if (extraLen) memcpy(info + n, extra, extraLen);
  return crypto::hkdfSha256(SALT, sizeof(SALT), ikm, crypto::KEY_SIZE, info, n + extraLen,
                            out, outLen);
}

}  // namespace

bool deviceKey(const Key master, uint16_t node, Key out) {
  const uint8_t n[2] = {uint8_t(node), uint8_t(node >> 8)};
  return derive(master, "device v1", n, sizeof(n), out, crypto::KEY_SIZE);
}

bool radioKey(const Key device, Key out) {
  return derive(device, "radio v1", nullptr, 0, out, crypto::KEY_SIZE);
}

bool logKey(const Key device, Key out) {
  return derive(device, "log v1", nullptr, 0, out, crypto::KEY_SIZE);
}

uint32_t fingerprint(const Key k) {
  uint8_t fp[4];
  if (!derive(k, "fingerprint v1", nullptr, 0, fp, sizeof(fp))) return 0;
  return uint32_t(fp[0]) << 24 | uint32_t(fp[1]) << 16 | uint32_t(fp[2]) << 8 | fp[3];
}

}  // namespace keys
