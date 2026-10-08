// SPDX-License-Identifier: Apache-2.0
#include "security.h"

#include <Arduino.h>
#include <Preferences.h>
#include <time.h>

#include "crypto.h"
#include "keys.h"
#include "role.h"
#include "timekeeping.h"

namespace security {
namespace {

Preferences prefs;  // Namespace "theoros-sec": key, counter, peer counters
bool testOk = false;
bool haveKey = false;
uint8_t key[16];        // Device key (tracker) or master key (receiver)
uint8_t radio[16], logk[16];
char fp[9] = "none";

// --- Counter ---
// Persisted in blocks: NVS holds the first value not yet handed out, and is
// rewritten once per COUNTER_BLOCK values (~1 h at 1.1 values/s). After a
// reboot we continue from there, skipping the unused rest of the block.
constexpr uint32_t COUNTER_BLOCK = 4096;
// No stored counter (new board, or flash erased): start from the clock at
// COUNTER_RATE per second since COUNTER_EPOCH. The board uses ~1.1 values/s
// (1 log record + 0.1 packet), so this is above anything used before an
// erase, and nonces never repeat even if the same key is re-entered.
// 32-bit range lasts until 2060.
constexpr uint32_t COUNTER_RATE = 4;
constexpr time_t COUNTER_EPOCH = 1767225600;  // 2026-01-01T00:00:00Z
bool counterKnown = false;
uint32_t counter = 0, reserved = 0;

// --- Receiver peers ---
// Highest counter accepted per tracker. Persisted at most every
// PEER_PERSIST_MS, so after a receiver reboot a packet up to that old could
// be replayed once; the timestamp check (STALE_S) narrows that further.
constexpr int MAX_PEERS = 16;
constexpr uint32_t PEER_PERSIST_MS = 10 * 60 * 1000;
constexpr long STALE_S = 10 * 60;
struct Peer {
  bool used = false;
  uint16_t node = 0;
  uint32_t last = 0;
  bool persisted = false;
  uint32_t persistedMs = 0;
  uint32_t seenMs = 0;
};
Peer peers[MAX_PEERS];
uint32_t rejected = 0;

void peerKeyName(uint16_t node, char out[8]) { snprintf(out, 8, "p%04x", node); }

Peer &peerFor(uint16_t node) {
  Peer *victim = &peers[0];
  for (Peer &p : peers) {
    if (p.used && p.node == node) return p;
    if (!p.used) victim = &p;
    else if (victim->used && p.seenMs < victim->seenMs) victim = &p;
  }
  // New, or evict the least recently heard. Its counter is in NVS already
  // unless it was evicted within PEER_PERSIST_MS of its last write.
  *victim = Peer();
  victim->used = true;
  victim->node = node;
  char k[8];
  peerKeyName(node, k);
  victim->last = prefs.getUInt(k, 0);
  victim->persisted = prefs.isKey(k);  // "last" holds a real value
  // Due now: the first accepted packet after loading is always saved.
  // (Unsigned wrap-around makes this work even when millis() is small.)
  victim->persistedMs = millis() - PEER_PERSIST_MS;
  return *victim;
}

}  // namespace

void begin(uint16_t node) {
  prefs.begin("theoros-sec", false);
  testOk = crypto::selfTest();
  if (!testOk) Serial.println("security: CRYPTO SELF-TEST FAILED, encryption disabled");

  haveKey = prefs.getBytes("key", key, sizeof(key)) == sizeof(key);
  if (haveKey) snprintf(fp, sizeof(fp), "%08lx", (unsigned long)keys::fingerprint(key));

  if (prefs.isKey("ctr")) {
    counter = reserved = prefs.getUInt("ctr", 0);
    counterKnown = true;
  }

  if (haveKey && !role::receiver()) {
    haveKey = keys::radioKey(key, radio) && keys::logKey(key, logk);
  }
  Serial.printf("security: %s, key %s%s\n", testOk ? "self-test passed" : "SELF-TEST FAILED",
                fp, haveKey ? (role::receiver() ? " (master)" : " (device)") : "");
  if (!haveKey) {
    if (role::receiver())
      Serial.println("security: NO KEY, packets cannot be read. Console: key set <master>");
    else
      Serial.printf("security: NO KEY, LoRa off and log UNENCRYPTED. Provision node %04x "
                    "with tools/theoros.py\n", node);
  }
}

bool ready() { return testOk && haveKey; }

bool selfTestPassed() { return testOk; }

const char *keyFingerprint() { return fp; }

bool setKey(const char *hex) {
  uint8_t k[16];
  if (strlen(hex) != 32) return false;
  for (int i = 0; i < 16; i++) {
    unsigned v;
    if (sscanf(hex + 2 * i, "%2x", &v) != 1 || !isxdigit((unsigned char)hex[2 * i]) ||
        !isxdigit((unsigned char)hex[2 * i + 1]))
      return false;
    k[i] = uint8_t(v);
  }
  // The counter is deliberately kept: it must never go backwards.
  bool ok = prefs.putBytes("key", k, sizeof(k)) == sizeof(k);
  if (ok) snprintf(fp, sizeof(fp), "%08lx", (unsigned long)keys::fingerprint(k));
  crypto::wipe(k, sizeof(k));
  return ok;
}

void clearKey() {
  prefs.remove("key");
  crypto::wipe(key, sizeof(key));
  crypto::wipe(radio, sizeof(radio));
  crypto::wipe(logk, sizeof(logk));
  haveKey = false;
  strcpy(fp, "none");
}

bool nextCounter(uint32_t &out) {
  if (!counterKnown) {
    if (!timekeeping::valid()) return false;
    time_t now = time(nullptr);
    counter = reserved = uint32_t((now - COUNTER_EPOCH) * COUNTER_RATE);
    counterKnown = true;
    Serial.printf("security: counter started from clock at %lu\n", (unsigned long)counter);
  }
  if (counter == UINT32_MAX) return false;  // Exhausted (2060): re-key needed
  if (counter >= reserved) {
    uint32_t r = UINT32_MAX - counter < COUNTER_BLOCK ? UINT32_MAX : counter + COUNTER_BLOCK;
    // If this write fails we must not hand out values we could repeat.
    if (prefs.putUInt("ctr", r) != sizeof(uint32_t)) return false;
    reserved = r;
  }
  out = counter++;
  return true;
}

const uint8_t *radioKey() { return ready() && !role::receiver() ? radio : nullptr; }

const uint8_t *logKey() { return ready() && !role::receiver() ? logk : nullptr; }

Rx openPacket(const uint8_t *data, size_t len, packet::Header &h, packet::Position &p) {
  Rx r = Rx::Ok;
  uint8_t dev[16], rk[16];
  if (!ready()) {
    r = Rx::NoKey;
  } else if (!packet::readHeader(data, len, h)) {
    r = Rx::Malformed;
  } else if (!keys::deviceKey(key, h.node, dev) || !keys::radioKey(dev, rk) ||
             !packet::open(rk, data, len, h, p)) {
    r = Rx::BadAuth;  // Not ours, damaged, or forged
  } else {
    // Authentic. Only now touch the peer table, so forged packets cannot
    // evict real trackers from it.
    Peer &peer = peerFor(h.node);
    time_t now = time(nullptr);
    if (peer.persisted && h.counter <= peer.last) {
      r = Rx::Replay;
    } else if (p.unixTime && timekeeping::valid() && labs(long(now - time_t(p.unixTime))) > STALE_S) {
      r = Rx::Stale;
    } else {
      peer.last = h.counter;
      peer.seenMs = millis();
      if (millis() - peer.persistedMs >= PEER_PERSIST_MS) {
        char k[8];
        peerKeyName(h.node, k);
        prefs.putUInt(k, peer.last);
        peer.persisted = true;
        peer.persistedMs = millis();
      }
    }
  }
  crypto::wipe(dev, sizeof(dev));
  crypto::wipe(rk, sizeof(rk));
  if (r != Rx::Ok) {
    rejected++;
    p = packet::Position();
  }
  return r;
}

const char *rxName(Rx r) {
  switch (r) {
    case Rx::Ok:        return "ok";
    case Rx::NoKey:     return "no key";
    case Rx::Malformed: return "malformed";
    case Rx::BadAuth:   return "authentication failed";
    case Rx::Replay:    return "replay";
    case Rx::Stale:     return "stale";
  }
  return "?";
}

uint32_t rejectedCount() { return rejected; }

}  // namespace security
