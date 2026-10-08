// SPDX-License-Identifier: Apache-2.0
// Cryptographic primitives: AES-128-CCM (RFC 3610) and HMAC/HKDF-SHA256
// (RFC 5869). The backend is mbedTLS on the device (crypto_mbedtls.cpp,
// hardware AES) and OpenSSL in the host tests; everything else is portable.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace crypto {

constexpr size_t KEY_SIZE = 16;    // AES-128
constexpr size_t NONCE_SIZE = 13;  // CCM with L = 2 (messages < 64 KiB)
constexpr size_t TAG_SIZE = 8;     // 64-bit authentication tag

// Nonce domains. Each key is already used for one purpose only; the domain
// byte keeps nonces distinct even if that ever changes.
constexpr uint8_t DOMAIN_RADIO = 'R';
constexpr uint8_t DOMAIN_LOG = 'L';

// --- Backend (crypto_mbedtls.cpp on the device) ---

bool ccmEncrypt(const uint8_t key[KEY_SIZE], const uint8_t nonce[NONCE_SIZE],
                const uint8_t *aad, size_t aadLen, const uint8_t *in, size_t len,
                uint8_t *out, uint8_t tag[TAG_SIZE]);

// Returns false, and zeroes out, if the tag does not verify.
bool ccmDecrypt(const uint8_t key[KEY_SIZE], const uint8_t nonce[NONCE_SIZE],
                const uint8_t *aad, size_t aadLen, const uint8_t *in, size_t len,
                const uint8_t tag[TAG_SIZE], uint8_t *out);

void hmacSha256(const uint8_t *key, size_t keyLen, const uint8_t *msg, size_t msgLen,
                uint8_t out[32]);

// --- Portable (crypto.cpp) ---

// RFC 5869. Returns false (and derives nothing) if infoLen > 64 or
// outLen > 255 * 32; the labels used here are far shorter.
bool hkdfSha256(const uint8_t *salt, size_t saltLen, const uint8_t *ikm, size_t ikmLen,
                const uint8_t *info, size_t infoLen, uint8_t *out, size_t outLen);

// counter (LE) | node (LE) | domain | 6 zero bytes. Unique as long as the
// counter never repeats for a given key.
void makeNonce(uint32_t counter, uint16_t node, uint8_t domain, uint8_t out[NONCE_SIZE]);

// Zeroes memory in a way the compiler cannot optimise away.
void wipe(void *p, size_t n);

// Known-answer tests: RFC 3610 packet vector #1 and RFC 5869 test case 1.
// Run at boot; encryption is refused if they fail.
bool selfTest();

}  // namespace crypto
