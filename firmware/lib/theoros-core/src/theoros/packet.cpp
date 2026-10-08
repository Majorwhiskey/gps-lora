// SPDX-License-Identifier: Apache-2.0
#include "packet.h"

#include <string.h>

namespace packet {
namespace {

template <typename T>
void put(uint8_t *&p, T v) {
  for (size_t i = 0; i < sizeof(T); i++) *p++ = uint8_t(uint64_t(v) >> (8 * i));
}

template <typename T>
T get(const uint8_t *&p) {
  uint64_t v = 0;
  for (size_t i = 0; i < sizeof(T); i++) v |= uint64_t(*p++) << (8 * i);
  return T(v);
}

void encodeBody(const Position &pos, uint8_t *p) {
  put<uint32_t>(p, pos.unixTime);
  put<int32_t>(p, pos.latE7);
  put<int32_t>(p, pos.lonE7);
  put<int16_t>(p, pos.altM);
  put<uint16_t>(p, pos.speedDkmh);
  put<uint8_t>(p, pos.sats);
  put<uint8_t>(p, pos.hdopX10);
  put<uint8_t>(p, pos.flags);
}

void decodeBody(const uint8_t *p, Position &pos) {
  pos.unixTime = get<uint32_t>(p);
  pos.latE7 = get<int32_t>(p);
  pos.lonE7 = get<int32_t>(p);
  pos.altM = get<int16_t>(p);
  pos.speedDkmh = get<uint16_t>(p);
  pos.sats = get<uint8_t>(p);
  pos.hdopX10 = get<uint8_t>(p);
  pos.flags = get<uint8_t>(p);
}

}  // namespace

size_t seal(const uint8_t radioKey[crypto::KEY_SIZE], const Header &h, const Position &pos,
            uint8_t out[SIZE]) {
  uint8_t *p = out;
  put<uint8_t>(p, VERSION);
  put<uint16_t>(p, h.node);
  put<uint32_t>(p, h.counter);

  uint8_t body[BODY_SIZE], nonce[crypto::NONCE_SIZE];
  encodeBody(pos, body);
  crypto::makeNonce(h.counter, h.node, crypto::DOMAIN_RADIO, nonce);
  bool ok = crypto::ccmEncrypt(radioKey, nonce, out, HEADER_SIZE, body, BODY_SIZE,
                               out + HEADER_SIZE, out + HEADER_SIZE + BODY_SIZE);
  crypto::wipe(body, sizeof(body));
  return ok ? SIZE : 0;
}

bool readHeader(const uint8_t *in, size_t len, Header &h) {
  if (len != SIZE || in[0] != VERSION) return false;
  const uint8_t *p = in + 1;
  h.node = get<uint16_t>(p);
  h.counter = get<uint32_t>(p);
  return true;
}

bool open(const uint8_t radioKey[crypto::KEY_SIZE], const uint8_t *in, size_t len, Header &h,
          Position &pos) {
  pos = Position();
  if (!readHeader(in, len, h)) return false;
  uint8_t body[BODY_SIZE], nonce[crypto::NONCE_SIZE];
  crypto::makeNonce(h.counter, h.node, crypto::DOMAIN_RADIO, nonce);
  bool ok = crypto::ccmDecrypt(radioKey, nonce, in, HEADER_SIZE, in + HEADER_SIZE, BODY_SIZE,
                               in + HEADER_SIZE + BODY_SIZE, body);
  if (ok) decodeBody(body, pos);
  crypto::wipe(body, sizeof(body));
  return ok;
}

}  // namespace packet
