// SPDX-License-Identifier: Apache-2.0
#include "display.h"

#include <Arduino.h>
#include <TinyGPSPlus.h>
#include <U8g2lib.h>
#include <Wire.h>

#include "board.h"
#include "config.h"
#include "gnss.h"
#include "lora_link.h"
#include "net.h"
#include "role.h"
#include "security.h"
#include "snapshot.h"
#include "storage.h"

namespace display {
namespace {

// U8g2 pulses RES# low, then sends the SSD1306 init sequence. Its "noname"
// sequence already uses the panel's internal DC/DC values from OLED §4.4:
// charge pump 8Dh 14h, contrast 81h CFh, pre-charge D9h F1h, then AFh.
U8G2_SSD1306_128X64_NONAME_F_HW_I2C oled(U8G2_R0, PIN_OLED_RES);
bool present = false;

void drawFixLines(const snapshot::Gnss &g) {
  char s[32];
  if (!gnss::linkAlive()) {
    snprintf(s, sizeof(s), "GNSS: no data");
  } else if (snapshot::fixFresh(g)) {
    snprintf(s, sizeof(s), "FIX  sats %2lu  h%.1f", (unsigned long)g.sats, g.hdop);
  } else {
    snprintf(s, sizeof(s), "no fix  sats %lu", (unsigned long)g.sats);
  }
  oled.drawStr(0, 9, s);

  if (g.timeValid) {
    snprintf(s, sizeof(s), "%02u:%02u:%02u UTC", g.hour, g.minute, g.second);
    oled.drawStr(0, 20, s);
  }
  if (gnss::ppsRecent()) oled.drawStr(104, 20, "PPS");
}

void drawSdLine() {
  char s[32];
  if (storage::state() == storage::State::Logging) {
    snprintf(s, sizeof(s), "SD %s %lu", storage::fileName(), (unsigned long)storage::records());
  } else if (storage::state() == storage::State::Ejected) {
    snprintf(s, sizeof(s), "SD safe to remove");
  } else {
    snprintf(s, sizeof(s), "SD %s", storage::stateName());
  }
  oled.drawStr(0, 53, s);
}

// Last line: WiFi status while in service mode, otherwise LoRa.
void drawRadioLine(bool receiver) {
  char s[40];
  if (net::radioOn()) {
    net::statusText(s, sizeof(s));
  } else if (!lora_link::ready()) {
    snprintf(s, sizeof(s), "LoRa: no radio");
  } else if (!security::ready()) {
    snprintf(s, sizeof(s), receiver ? "NO KEY: can't decrypt" : "NO KEY: LoRa off");
  } else if (receiver) {
    snprintf(s, sizeof(s), "LoRa ok %lu rej %lu",
             (unsigned long)(lora_link::frameCount() - security::rejectedCount()),
             (unsigned long)security::rejectedCount());
  } else {
    snprintf(s, sizeof(s), "LoRa tx %lu  %ddBm", (unsigned long)lora_link::sentCount(),
             LORA_POWER_DBM);
  }
  oled.drawStr(0, 64, s);
}

void renderTracker(const snapshot::Gnss &g) {
  char s[32];
  drawFixLines(g);
  if (snapshot::fixFresh(g)) {
    snprintf(s, sizeof(s), "%11.6f %c", fabs(g.lat), g.lat >= 0 ? 'N' : 'S');
    oled.drawStr(0, 31, s);
    snprintf(s, sizeof(s), "%11.6f %c %5.0fm", fabs(g.lon), g.lon >= 0 ? 'E' : 'W', g.altM);
    oled.drawStr(0, 42, s);
  }
  drawSdLine();
  drawRadioLine(false);
}

// Receiver: last packet heard, and distance to it if both ends have a fix.
void renderReceiver(const snapshot::Gnss &g) {
  char s[32];
  drawFixLines(g);
  snapshot::Rx rx = snapshot::rx();
  if (!rx.atMs) {
    oled.drawStr(0, 31, "waiting for tracker");
  } else {
    const packet::Position &p = rx.pos;
    snprintf(s, sizeof(s), "%04x #%lu %lus ago", rx.hdr.node, (unsigned long)(rx.hdr.counter % 100000),
             (unsigned long)((millis() - rx.atMs) / 1000));
    oled.drawStr(0, 31, s);
    if ((p.flags & packet::FLAG_FIX_VALID) && snapshot::fixFresh(g)) {
      double dist = TinyGPSPlus::distanceBetween(g.lat, g.lon, p.latE7 * 1e-7, p.lonE7 * 1e-7);
      double crs = TinyGPSPlus::courseTo(g.lat, g.lon, p.latE7 * 1e-7, p.lonE7 * 1e-7);
      if (dist < 10000) snprintf(s, sizeof(s), "%.0fm %s %.0fdBm", dist,
                                 TinyGPSPlus::cardinal(crs), rx.rssi);
      else snprintf(s, sizeof(s), "%.1fkm %s %.0fdBm", dist / 1000, TinyGPSPlus::cardinal(crs),
                    rx.rssi);
    } else {
      snprintf(s, sizeof(s), "%s %.0fdBm %.1fdB",
               (p.flags & packet::FLAG_FIX_VALID) ? "fix" : "no fix", rx.rssi, rx.snr);
    }
    oled.drawStr(0, 42, s);
  }
  drawSdLine();
  drawRadioLine(true);
}

}  // namespace

bool begin() {
  Wire.begin(PIN_OLED_SDA, PIN_OLED_SCL, 400000);

  // RES# low for >= 3 us after VDD is stable, so the controller answers I2C.
  pinMode(PIN_OLED_RES, OUTPUT);
  digitalWrite(PIN_OLED_RES, LOW);
  delayMicroseconds(10);
  digitalWrite(PIN_OLED_RES, HIGH);
  delay(1);

  Wire.beginTransmission(OLED_I2C_ADDR);
  present = Wire.endTransmission() == 0;
  if (!present) {
    Serial.println("oled: no panel at 0x3C");
    return false;
  }
  oled.setI2CAddress(OLED_I2C_ADDR << 1);
  oled.begin();
  oled.setBusClock(400000);
  oled.setFont(u8g2_font_6x10_tf);
  return true;
}

void message(const char *line1, const char *line2) {
  if (!present) return;
  oled.clearBuffer();
  oled.drawStr(0, 24, line1);
  if (line2) oled.drawStr(0, 40, line2);
  oled.sendBuffer();
}

void render() {
  if (!present) return;
  snapshot::Gnss g = snapshot::gnss();
  oled.clearBuffer();
  if (role::receiver()) renderReceiver(g);
  else renderTracker(g);
  oled.sendBuffer();
}

}  // namespace display
