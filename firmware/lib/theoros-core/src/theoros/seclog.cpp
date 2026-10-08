// SPDX-License-Identifier: Apache-2.0
#include "seclog.h"

#include <stdio.h>
#include <string.h>

namespace seclog {
namespace {

const char B64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

size_t b64Encode(const uint8_t *in, size_t len, char *out) {
  size_t o = 0;
  for (size_t i = 0; i < len; i += 3) {
    uint32_t v = uint32_t(in[i]) << 16;
    if (i + 1 < len) v |= uint32_t(in[i + 1]) << 8;
    if (i + 2 < len) v |= in[i + 2];
    out[o++] = B64[(v >> 18) & 63];
    out[o++] = B64[(v >> 12) & 63];
    out[o++] = i + 1 < len ? B64[(v >> 6) & 63] : '=';
    out[o++] = i + 2 < len ? B64[v & 63] : '=';
  }
  return o;
}

int b64Value(char c) {
  const char *p = c ? strchr(B64, c) : nullptr;
  return p ? int(p - B64) : -1;
}

// Returns decoded length, or -1 on malformed input.
long b64Decode(const char *in, size_t len, uint8_t *out, size_t outSize) {
  if (len % 4) return -1;
  size_t o = 0;
  for (size_t i = 0; i < len; i += 4) {
    if (in[i + 2] == '=' && in[i + 3] != '=') return -1;
    int pad = (in[i + 3] == '=') + (in[i + 2] == '=');
    if (pad && i + 4 != len) return -1;
    int a = b64Value(in[i]), b = b64Value(in[i + 1]);
    int c = in[i + 2] == '=' ? 0 : b64Value(in[i + 2]);
    int d = in[i + 3] == '=' ? 0 : b64Value(in[i + 3]);
    if (a < 0 || b < 0 || c < 0 || d < 0) return -1;
    uint32_t v = uint32_t(a) << 18 | uint32_t(b) << 12 | uint32_t(c) << 6 | uint32_t(d);
    size_t n = 3 - pad;
    if (o + n > outSize) return -1;
    out[o++] = uint8_t(v >> 16);
    if (n > 1) out[o++] = uint8_t(v >> 8);
    if (n > 2) out[o++] = uint8_t(v);
  }
  return long(o);
}

}  // namespace

size_t sealLine(const uint8_t logKey[crypto::KEY_SIZE], uint16_t node, uint32_t counter,
                const char *plain, char *out, size_t outSize) {
  size_t len = strlen(plain);
  if (len > MAX_PLAIN) return 0;
  size_t b64Len = (len + crypto::TAG_SIZE + 2) / 3 * 4;
  if (9 + b64Len + 2 > outSize) return 0;  // "xxxxxxxx," + b64 + "\n" + NUL

  uint8_t buf[MAX_PLAIN + crypto::TAG_SIZE], nonce[crypto::NONCE_SIZE];
  crypto::makeNonce(counter, node, crypto::DOMAIN_LOG, nonce);
  if (!crypto::ccmEncrypt(logKey, nonce, nullptr, 0, reinterpret_cast<const uint8_t *>(plain),
                          len, buf, buf + len))
    return 0;

  snprintf(out, outSize, "%08lx,", (unsigned long)counter);
  size_t n = 9 + b64Encode(buf, len + crypto::TAG_SIZE, out + 9);
  out[n++] = '\n';
  out[n] = 0;
  crypto::wipe(buf, sizeof(buf));
  return n;
}

bool openLine(const uint8_t logKey[crypto::KEY_SIZE], uint16_t node, const char *line,
              char *plain, size_t plainSize) {
  size_t len = strcspn(line, "\r\n");
  if (len < 10 || line[8] != ',') return false;
  uint32_t counter = 0;
  for (int i = 0; i < 8; i++) {
    char c = line[i];
    int v = (c >= '0' && c <= '9') ? c - '0' : (c >= 'a' && c <= 'f') ? c - 'a' + 10 : -1;
    if (v < 0) return false;
    counter = counter << 4 | uint32_t(v);
  }

  uint8_t buf[MAX_PLAIN + crypto::TAG_SIZE];
  long n = b64Decode(line + 9, len - 9, buf, sizeof(buf));
  if (n < long(crypto::TAG_SIZE)) return false;
  size_t ctLen = size_t(n) - crypto::TAG_SIZE;
  if (ctLen + 1 > plainSize) return false;

  uint8_t nonce[crypto::NONCE_SIZE];
  crypto::makeNonce(counter, node, crypto::DOMAIN_LOG, nonce);
  bool ok = crypto::ccmDecrypt(logKey, nonce, nullptr, 0, buf, ctLen, buf + ctLen,
                               reinterpret_cast<uint8_t *>(plain));
  plain[ok ? ctLen : 0] = 0;
  return ok;
}

}  // namespace seclog
