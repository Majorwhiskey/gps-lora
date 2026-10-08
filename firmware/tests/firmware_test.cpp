// SPDX-License-Identifier: Apache-2.0
// Host tests for the firmware's portable code: crypto, key derivation,
// encrypted LoRa packets and encrypted log lines. Run: make -C firmware/tests
//
// With --vectors, prints test vectors as JSON for tools/theoros.py, which
// re-derives and re-encrypts them with an independent implementation (Python
// cryptography) and requires byte-for-byte agreement.
#include <cstdio>
#include <cstring>

#include "../lib/theoros-core/src/theoros/crypto.h"
#include "../lib/theoros-core/src/theoros/keys.h"
#include "../lib/theoros-core/src/theoros/packet.h"
#include "../lib/theoros-core/src/theoros/seclog.h"

static int failures = 0;
#define CHECK(c)                                                  \
  do {                                                            \
    if (!(c)) {                                                   \
      std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c);    \
      failures++;                                                 \
    }                                                             \
  } while (0)

static bool contains(const uint8_t *hay, size_t n, const uint8_t *needle, size_t m) {
  for (size_t i = 0; i + m <= n; i++)
    if (std::memcmp(hay + i, needle, m) == 0) return true;
  return false;
}

static void hex(const uint8_t *p, size_t n, char *out) {
  for (size_t i = 0; i < n; i++) std::sprintf(out + 2 * i, "%02x", p[i]);
}

static const uint8_t MASTER[16] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
                                   0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff};
static const uint16_t NODE = 0xab12;
static const uint32_t COUNTER = 0x01020304;
static const char LOG_PLAIN[] = "2026-10-07,09:12:44,12.9715987,-77.5945627,-12.0,123.40,87.5,14,0.8";

static packet::Position samplePosition() {
  packet::Position p;
  p.unixTime = 1791364364;  // 2026-10-07T09:12:44Z
  p.latE7 = 129715987;
  p.lonE7 = -775945627;     // negative to exercise sign handling
  p.altM = -12;
  p.speedDkmh = 1234;
  p.sats = 14;
  p.hdopX10 = 8;
  p.flags = packet::FLAG_FIX_VALID | packet::FLAG_PPS;
  return p;
}

int main(int argc, char **argv) {
  CHECK(crypto::selfTest());  // RFC 3610 and RFC 5869 through the real code path

  uint8_t dev[16], radio[16], logk[16], dev2[16];
  CHECK(keys::deviceKey(MASTER, NODE, dev));
  CHECK(keys::radioKey(dev, radio));
  CHECK(keys::logKey(dev, logk));
  CHECK(keys::deviceKey(MASTER, NODE + 1, dev2));
  CHECK(std::memcmp(dev, dev2, 16) != 0);    // Per-node keys differ
  CHECK(std::memcmp(radio, logk, 16) != 0);  // Per-purpose keys differ
  CHECK(keys::fingerprint(dev) != keys::fingerprint(dev2));

  // Packet: seal, open, reject every single-byte change.
  packet::Header h;
  h.node = NODE;
  h.counter = COUNTER;
  packet::Position pos = samplePosition();
  uint8_t pkt[packet::SIZE];
  CHECK(packet::seal(radio, h, pos, pkt) == packet::SIZE);
  CHECK(packet::SIZE == 34);

  packet::Header h2;
  packet::Position q;
  CHECK(packet::open(radio, pkt, sizeof(pkt), h2, q));
  CHECK(h2.node == NODE && h2.counter == COUNTER);
  CHECK(q.unixTime == pos.unixTime && q.latE7 == pos.latE7 && q.lonE7 == pos.lonE7);
  CHECK(q.altM == pos.altM && q.speedDkmh == pos.speedDkmh && q.sats == pos.sats);
  CHECK(q.hdopX10 == pos.hdopX10 && q.flags == pos.flags);

  // The body must not appear in clear: latitude bytes are absent.
  const uint8_t latLe[4] = {0x13, 0x5b, 0xbb, 0x07};
  CHECK(!contains(pkt, sizeof(pkt), latLe, sizeof(latLe)));

  int tamperRejected = 0;
  for (size_t i = 0; i < packet::SIZE; i++) {
    uint8_t t[packet::SIZE];
    std::memcpy(t, pkt, sizeof(t));
    t[i] ^= 0x01;
    if (!packet::open(radio, t, sizeof(t), h2, q)) tamperRejected++;
    CHECK(q.latE7 == 0);  // Nothing leaks from a rejected packet
  }
  CHECK(tamperRejected == int(packet::SIZE));

  uint8_t otherRadio[16];
  CHECK(keys::radioKey(dev2, otherRadio));
  CHECK(!packet::open(otherRadio, pkt, sizeof(pkt), h2, q));  // Other tracker's key
  CHECK(!packet::open(radio, pkt, sizeof(pkt) - 1, h2, q));   // Truncated

  // Same position, next counter: completely different ciphertext.
  uint8_t pkt2[packet::SIZE];
  h.counter = COUNTER + 1;
  CHECK(packet::seal(radio, h, pos, pkt2) == packet::SIZE);
  CHECK(std::memcmp(pkt + packet::HEADER_SIZE, pkt2 + packet::HEADER_SIZE,
                    packet::BODY_SIZE) != 0);

  // Log lines
  char line[256], plain[seclog::MAX_PLAIN + 1];
  size_t n = seclog::sealLine(logk, NODE, COUNTER, LOG_PLAIN, line, sizeof(line));
  CHECK(n > 0 && line[n - 1] == '\n' && !std::strstr(line, "12.97"));
  CHECK(seclog::openLine(logk, NODE, line, plain, sizeof(plain)));
  CHECK(std::strcmp(plain, LOG_PLAIN) == 0);
  CHECK(!seclog::openLine(logk, NODE + 1, line, plain, sizeof(plain)));  // Wrong node
  CHECK(!seclog::openLine(radio, NODE, line, plain, sizeof(plain)));     // Radio key
  char bad[256];
  std::strcpy(bad, line);
  bad[20] = bad[20] == 'A' ? 'B' : 'A';
  CHECK(!seclog::openLine(logk, NODE, bad, plain, sizeof(plain)));  // Altered
  std::strcpy(bad, line);
  bad[n / 2] = 0;
  CHECK(!seclog::openLine(logk, NODE, bad, plain, sizeof(plain)));  // Power cut mid-line
  CHECK(!seclog::openLine(logk, NODE, "garbage", plain, sizeof(plain)));
  CHECK(seclog::sealLine(logk, NODE, COUNTER, LOG_PLAIN, line, 40) == 0);  // Too small

  if (argc > 1 && !std::strcmp(argv[1], "--vectors")) {
    char m[33], d[33], r[33], l[33], p[2 * packet::SIZE + 1];
    hex(MASTER, 16, m);
    hex(dev, 16, d);
    hex(radio, 16, r);
    hex(logk, 16, l);
    h.counter = COUNTER;
    packet::seal(radio, h, pos, pkt);
    hex(pkt, sizeof(pkt), p);
    seclog::sealLine(logk, NODE, COUNTER, LOG_PLAIN, line, sizeof(line));
    line[std::strcspn(line, "\n")] = 0;
    std::printf("{\"master\":\"%s\",\"node\":%u,\"counter\":%u,\"device_key\":\"%s\","
                "\"radio_key\":\"%s\",\"log_key\":\"%s\",\"fingerprint\":\"%08x\","
                "\"packet\":\"%s\",\"log_plain\":\"%s\",\"log_line\":\"%s\"}\n",
                m, NODE, COUNTER, d, r, l, keys::fingerprint(dev), p, LOG_PLAIN, line);
    return failures != 0;
  }

  std::printf(failures ? "%d failure(s)\n" : "firmware_test: all passed\n", failures);
  return failures != 0;
}
