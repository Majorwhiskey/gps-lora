// SPDX-License-Identifier: Apache-2.0
#include "crypto.h"

#include <string.h>

namespace crypto {

bool hkdfSha256(const uint8_t *salt, size_t saltLen, const uint8_t *ikm, size_t ikmLen,
                const uint8_t *info, size_t infoLen, uint8_t *out, size_t outLen) {
  if (infoLen > 64 || outLen > 255 * 32) return false;
  static const uint8_t zeros[32] = {};
  uint8_t prk[32];
  if (!salt || !saltLen) {
    salt = zeros;
    saltLen = sizeof(zeros);
  }
  hmacSha256(salt, saltLen, ikm, ikmLen, prk);  // Extract

  uint8_t t[32];
  size_t tLen = 0;
  uint8_t block[32 + 64 + 1];  // T(i-1) | info | i
  for (uint8_t i = 1; outLen; i++) {  // Expand
    size_t n = 0;
    memcpy(block, t, tLen);
    n += tLen;
    memcpy(block + n, info, infoLen);
    n += infoLen;
    block[n++] = i;
    hmacSha256(prk, sizeof(prk), block, n, t);
    tLen = sizeof(t);
    size_t c = outLen < tLen ? outLen : tLen;
    memcpy(out, t, c);
    out += c;
    outLen -= c;
  }
  wipe(prk, sizeof(prk));
  wipe(t, sizeof(t));
  wipe(block, sizeof(block));
  return true;
}

void makeNonce(uint32_t counter, uint16_t node, uint8_t domain, uint8_t out[NONCE_SIZE]) {
  memset(out, 0, NONCE_SIZE);
  for (int i = 0; i < 4; i++) out[i] = uint8_t(counter >> (8 * i));
  out[4] = uint8_t(node);
  out[5] = uint8_t(node >> 8);
  out[6] = domain;
}

void wipe(void *p, size_t n) {
  volatile uint8_t *v = static_cast<volatile uint8_t *>(p);
  while (n--) *v++ = 0;
}

bool selfTest() {
  // RFC 3610 packet vector #1: 13-byte nonce, 8-byte tag, 8 bytes AAD.
  uint8_t key[16], data[31], ct[23], tag[8], pt[23];
  for (int i = 0; i < 16; i++) key[i] = uint8_t(0xC0 + i);
  for (int i = 0; i < 31; i++) data[i] = uint8_t(i);
  const uint8_t nonce[13] = {0x00, 0x00, 0x00, 0x03, 0x02, 0x01, 0x00,
                             0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5};
  const uint8_t expected[31] = {0x58, 0x8C, 0x97, 0x9A, 0x61, 0xC6, 0x63, 0xD2, 0xF0, 0x66, 0xD0,
                                0xC2, 0xC0, 0xF9, 0x89, 0x80, 0x6D, 0x5F, 0x6B, 0x61, 0xDA, 0xC3,
                                0x84, 0x17, 0xE8, 0xD1, 0x2C, 0xFD, 0xF9, 0x26, 0xE0};
  if (!ccmEncrypt(key, nonce, data, 8, data + 8, 23, ct, tag)) return false;
  if (memcmp(ct, expected, 23) != 0 || memcmp(tag, expected + 23, 8) != 0) return false;
  if (!ccmDecrypt(key, nonce, data, 8, ct, 23, tag, pt) || memcmp(pt, data + 8, 23) != 0)
    return false;
  tag[0] ^= 1;  // A forged tag must be rejected
  if (ccmDecrypt(key, nonce, data, 8, ct, 23, tag, pt)) return false;

  // RFC 5869 test case 1 (first 16 bytes of OKM checked).
  uint8_t ikm[22], salt[13], info[10], okm[16];
  memset(ikm, 0x0B, sizeof(ikm));
  for (int i = 0; i < 13; i++) salt[i] = uint8_t(i);
  for (int i = 0; i < 10; i++) info[i] = uint8_t(0xF0 + i);
  const uint8_t okmExpected[16] = {0x3C, 0xB2, 0x5F, 0x25, 0xFA, 0xAC, 0xD5, 0x7A,
                                   0x90, 0x43, 0x4F, 0x64, 0xD0, 0x36, 0x2F, 0x2A};
  if (!hkdfSha256(salt, sizeof(salt), ikm, sizeof(ikm), info, sizeof(info), okm, sizeof(okm)))
    return false;
  return memcmp(okm, okmExpected, sizeof(okm)) == 0;
}

}  // namespace crypto
