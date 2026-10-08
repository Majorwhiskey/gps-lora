// SPDX-License-Identifier: Apache-2.0
// Theoros receiver firmware, ESP32-S3.
//
// Listens for trackers. Every packet is authenticated and decrypted with the
// master key (AES-128-CCM); forged, damaged, replayed and stale packets are
// dropped. Good packets are appended to RXnnnn.CSV, printed on USB as one
// JSON line, and shown on the OLED with distance and direction to the
// tracker. The radio never transmits. Shared runtime (button, LED, display,
// WiFi, OTA, security) is in firmware/lib/theoros-core. See
// firmware/README.md.
//
// Status LED:
//   5 fast blinks, repeating ... no card or card error
//   short blip every 2 s ...... card OK, waiting for a packet
//   blip on each packet ....... logging
//   solid on .................. card ejected, safe to remove
//
// Eject button: short press toggles WiFi service mode; hold 1 s to eject the
// card; press again while ejected to resume.

#include <theoros.h>

namespace {

// The receiver is the trusted end: its log holds decrypted positions.
const char RX_HEADER[] =
    "rx_utc,node,counter,unix_time,lat,lon,alt_m,speed_kmh,sats,hdop,flags,rssi_dbm,snr_db\n";

const char *logHeader() { return RX_HEADER; }

void serviceReceiver() {
  lora_link::Frame f;
  if (!lora_link::takeFrame(f)) return;

  snapshot::Rx rx;
  security::Rx result = security::openPacket(f.data, f.len, rx.hdr, rx.pos);
  if (result != security::Rx::Ok) {
    // Not printed as JSON: lines starting with '{' are good packets only.
    Serial.printf("rx: dropped %u-byte frame, %s, %.0f dBm\n", (unsigned)f.len,
                  security::rxName(result), f.rssi);
    return;
  }
  rx.atMs = millis();
  rx.rssi = f.rssi;
  rx.snr = f.snr;
  snapshot::publishRx(rx);

  const packet::Header &h = rx.hdr;
  const packet::Position &p = rx.pos;
  char rxUtc[24] = "";
  if (timekeeping::valid()) {
    time_t now = time(nullptr);
    struct tm t;
    gmtime_r(&now, &t);
    strftime(rxUtc, sizeof(rxUtc), "%Y-%m-%dT%H:%M:%SZ", &t);
  }
  char line[200];
  snprintf(line, sizeof(line), "%s,%04x,%lu,%lu,%.7f,%.7f,%d,%.1f,%u,%.1f,%u,%.1f,%.2f\n",
           rxUtc, h.node, (unsigned long)h.counter, (unsigned long)p.unixTime, p.latE7 * 1e-7,
           p.lonE7 * 1e-7, p.altM, p.speedDkmh / 10.0, p.sats, p.hdopX10 / 10.0, p.flags,
           f.rssi, f.snr);
  if (storage::append(line)) app::ledBlip(40);

  // JSON line for a host program; lines starting with '{' are packets.
  Serial.printf("{\"rx_utc\":\"%s\",\"node\":\"%04x\",\"counter\":%lu,\"unix_time\":%lu,"
                "\"fix\":%s,\"lat\":%.7f,\"lon\":%.7f,\"alt_m\":%d,\"speed_kmh\":%.1f,"
                "\"sats\":%u,\"hdop\":%.1f,\"flags\":%u,\"rssi_dbm\":%.1f,\"snr_db\":%.2f}\n",
                rxUtc, h.node, (unsigned long)h.counter, (unsigned long)p.unixTime,
                (p.flags & packet::FLAG_FIX_VALID) ? "true" : "false", p.latE7 * 1e-7,
                p.lonE7 * 1e-7, p.altM, p.speedDkmh / 10.0, p.sats, p.hdopX10 / 10.0,
                p.flags, f.rssi, f.snr);
}

}  // namespace

void setup() {
  // No epoch handler: the receiver logs packets, not its own track.
  app::begin(role::Role::Receiver, "RX", logHeader, nullptr);
  lora_link::startReceive();
}

void loop() {
  app::service();
  serviceReceiver();
}
