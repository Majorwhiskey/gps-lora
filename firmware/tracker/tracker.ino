// SPDX-License-Identifier: Apache-2.0
// Theoros tracker (transmitter) firmware, ESP32-S3.
//
// Logs a record per GNSS epoch to microSD and sends position over LoRa every
// LORA_INTERVAL_MS. With a key installed, both are encrypted (AES-128-CCM);
// without one the tracker does not transmit, and logs plaintext with a
// warning. Shared runtime (button, LED, display, WiFi, OTA, security) is in
// firmware/lib/theoros-core. See firmware/README.md.
//
// Status LED:
//   5 fast blinks, repeating ... no card or card error
//   short blip every 2 s ...... card OK, waiting for a fix
//   blip on each record ....... logging
//   solid on .................. card ejected, safe to remove
//
// Eject button: short press toggles WiFi service mode; hold 1 s to eject the
// card; press again while ejected to resume.

#include <theoros.h>

namespace {

const char COLUMNS[] = "utc_date,utc_time,lat,lon,alt_m,speed_kmh,course_deg,sats,hdop";

uint32_t lastLoraMs = 0;

const char *logHeader() {
  static char h[200];
  if (security::ready()) {
    // tools/theoros.py reads node and key from the first line.
    snprintf(h, sizeof(h),
             "# theoros encrypted log v1 node=%04x key=%s\n"
             "# columns: %s\n"
             "# decrypt: tools/theoros.py decrypt-log MASTER_FILE <this file>\n",
             lora_link::nodeId(), security::keyFingerprint(), COLUMNS);
  } else {
    snprintf(h, sizeof(h), "%s\n", COLUMNS);
  }
  return h;
}

void logRecord(TinyGPSPlus &g, bool usable) {
  if (!usable) return;
  char plain[seclog::MAX_PLAIN + 1];
  snprintf(plain, sizeof(plain), "%04u-%02u-%02u,%02u:%02u:%02u,%.7f,%.7f,%.1f,%.2f,%.1f,%lu,%.1f",
           g.date.year(), g.date.month(), g.date.day(), g.time.hour(), g.time.minute(),
           g.time.second(), g.location.lat(), g.location.lng(), g.altitude.meters(),
           g.speed.kmph(), g.course.deg(), (unsigned long)g.satellites.value(), g.hdop.hdop());

  char line[256];
  if (security::ready()) {
    // Fail closed: with a key installed, nothing is ever written in clear.
    uint32_t ctr;
    if (!security::nextCounter(ctr) ||
        !seclog::sealLine(security::logKey(), lora_link::nodeId(), ctr, plain, line,
                          sizeof(line))) {
      Serial.println("log: cannot encrypt, record dropped");
      crypto::wipe(plain, sizeof(plain));
      return;
    }
  } else {
    snprintf(line, sizeof(line), "%s\n", plain);
  }
  crypto::wipe(plain, sizeof(plain));
  if (storage::append(line)) app::ledBlip(40);
}

void serviceLora() {
  if (millis() - lastLoraMs < LORA_INTERVAL_MS) return;
  if (!security::ready()) return;     // Never transmit in clear
  if (net::radioOn()) return;         // WiFi/LoRa TX interlock, see net.h
  if (!lora_link::canSend()) return;  // Don't spend a counter we can't use

  packet::Header h;
  h.node = lora_link::nodeId();
  if (!security::nextCounter(h.counter)) return;  // Waiting for a clock, see security.h

  snapshot::Gnss g = snapshot::gnss();
  packet::Position p;
  if (snapshot::fixFresh(g)) {
    p.flags |= packet::FLAG_FIX_VALID;
    p.latE7 = int32_t(lround(g.lat * 1e7));
    p.lonE7 = int32_t(lround(g.lon * 1e7));
    p.altM = int16_t(constrain(lround(g.altM), -32768L, 32767L));
    p.speedDkmh = uint16_t(constrain(lround(g.speedKmh * 10), 0L, 65535L));
  }
  p.unixTime = g.unixTime;
  p.sats = uint8_t(min<uint32_t>(g.sats, 255));
  p.hdopX10 = uint8_t(constrain(lround(g.hdop * 10), 0L, 255L));
  if (storage::state() == storage::State::Logging) p.flags |= packet::FLAG_SD_LOG;
  if (gnss::ppsRecent()) p.flags |= packet::FLAG_PPS;

  uint8_t pkt[packet::SIZE];
  if (packet::seal(security::radioKey(), h, p, pkt) && lora_link::send(pkt, sizeof(pkt)))
    lastLoraMs = millis();
}

}  // namespace

void setup() {
  app::begin(role::Role::Tracker, "LOG", logHeader, logRecord);
}

void loop() {
  app::service();
  serviceLora();
}
