// SPDX-License-Identifier: Apache-2.0
// Host backend for crypto.h, used only by the tests. The device uses
// lib/gps-lora-core/src/gpslora/crypto_mbedtls.cpp.
#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <string.h>

#include "../lib/gps-lora-core/src/gpslora/crypto.h"

namespace crypto {
namespace {

// CCM in OpenSSL: lengths and tag size must be set before the data.
bool ccm(bool enc, const uint8_t *key, const uint8_t *nonce, const uint8_t *aad, size_t aadLen,
         const uint8_t *in, size_t len, uint8_t *out, uint8_t *tag) {
  EVP_CIPHER_CTX *c = EVP_CIPHER_CTX_new();
  int n = 0;
  bool ok = c && EVP_CipherInit_ex(c, EVP_aes_128_ccm(), nullptr, nullptr, nullptr, enc) &&
            EVP_CIPHER_CTX_ctrl(c, EVP_CTRL_AEAD_SET_IVLEN, NONCE_SIZE, nullptr) &&
            EVP_CIPHER_CTX_ctrl(c, EVP_CTRL_AEAD_SET_TAG, TAG_SIZE, enc ? nullptr : tag) &&
            EVP_CipherInit_ex(c, nullptr, nullptr, key, nonce, enc) &&
            EVP_CipherUpdate(c, nullptr, &n, nullptr, int(len)) &&
            (!aadLen || EVP_CipherUpdate(c, nullptr, &n, aad, int(aadLen))) &&
            // For decryption this update is where the tag is verified.
            EVP_CipherUpdate(c, out, &n, in, int(len)) > 0;
  if (ok && enc) {
    ok = EVP_CipherFinal_ex(c, out + n, &n) &&
         EVP_CIPHER_CTX_ctrl(c, EVP_CTRL_AEAD_GET_TAG, TAG_SIZE, tag);
  }
  EVP_CIPHER_CTX_free(c);
  return ok;
}

}  // namespace

bool ccmEncrypt(const uint8_t key[KEY_SIZE], const uint8_t nonce[NONCE_SIZE],
                const uint8_t *aad, size_t aadLen, const uint8_t *in, size_t len,
                uint8_t *out, uint8_t tag[TAG_SIZE]) {
  return ccm(true, key, nonce, aad, aadLen, in, len, out, tag);
}

bool ccmDecrypt(const uint8_t key[KEY_SIZE], const uint8_t nonce[NONCE_SIZE],
                const uint8_t *aad, size_t aadLen, const uint8_t *in, size_t len,
                const uint8_t tag[TAG_SIZE], uint8_t *out) {
  uint8_t t[TAG_SIZE];
  memcpy(t, tag, TAG_SIZE);
  bool ok = ccm(false, key, nonce, aad, aadLen, in, len, out, t);
  if (!ok) memset(out, 0, len);
  return ok;
}

void hmacSha256(const uint8_t *key, size_t keyLen, const uint8_t *msg, size_t msgLen,
                uint8_t out[32]) {
  unsigned int n = 32;
  HMAC(EVP_sha256(), key, int(keyLen), msg, msgLen, out, &n);
}

}  // namespace crypto
