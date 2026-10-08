// SPDX-License-Identifier: Apache-2.0
// Device backend for crypto.h: mbedTLS from ESP-IDF, which uses the
// ESP32-S3 AES accelerator (CONFIG_MBEDTLS_HARDWARE_AES).
#if defined(ARDUINO)

#include <mbedtls/ccm.h>
#include <mbedtls/md.h>
#include <string.h>

#include "crypto.h"

namespace crypto {

bool ccmEncrypt(const uint8_t key[KEY_SIZE], const uint8_t nonce[NONCE_SIZE],
                const uint8_t *aad, size_t aadLen, const uint8_t *in, size_t len,
                uint8_t *out, uint8_t tag[TAG_SIZE]) {
  mbedtls_ccm_context ctx;
  mbedtls_ccm_init(&ctx);
  bool ok = mbedtls_ccm_setkey(&ctx, MBEDTLS_CIPHER_ID_AES, key, KEY_SIZE * 8) == 0 &&
            mbedtls_ccm_encrypt_and_tag(&ctx, len, nonce, NONCE_SIZE, aad, aadLen, in, out,
                                        tag, TAG_SIZE) == 0;
  mbedtls_ccm_free(&ctx);
  return ok;
}

bool ccmDecrypt(const uint8_t key[KEY_SIZE], const uint8_t nonce[NONCE_SIZE],
                const uint8_t *aad, size_t aadLen, const uint8_t *in, size_t len,
                const uint8_t tag[TAG_SIZE], uint8_t *out) {
  mbedtls_ccm_context ctx;
  mbedtls_ccm_init(&ctx);
  // auth_decrypt compares the tag in constant time and zeroes out on failure.
  bool ok = mbedtls_ccm_setkey(&ctx, MBEDTLS_CIPHER_ID_AES, key, KEY_SIZE * 8) == 0 &&
            mbedtls_ccm_auth_decrypt(&ctx, len, nonce, NONCE_SIZE, aad, aadLen, in, out, tag,
                                     TAG_SIZE) == 0;
  mbedtls_ccm_free(&ctx);
  if (!ok) memset(out, 0, len);
  return ok;
}

void hmacSha256(const uint8_t *key, size_t keyLen, const uint8_t *msg, size_t msgLen,
                uint8_t out[32]) {
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), key, keyLen, msg, msgLen, out);
}

}  // namespace crypto

#endif  // ARDUINO
